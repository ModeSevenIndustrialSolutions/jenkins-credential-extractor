# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

"""Authentication and session management for Jenkins automation."""

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urljoin, urlparse

import keyring
import requests
from cryptography.fernet import Fernet
from rich.console import Console
from rich.prompt import Confirm, Prompt

# Optional Google OAuth imports
try:
    from google_auth_oauthlib.flow import Flow

    GOOGLE_AUTH_AVAILABLE = True
except ImportError:
    GOOGLE_AUTH_AVAILABLE = False

console = Console()

# Constants
API_JSON_ENDPOINT = "/api/json"


class JenkinsAuthManager:
    """Manage Jenkins authentication with Google SSO integration."""

    def __init__(self, jenkins_url: str, client_secrets_file: Optional[str] = None):
        """Initialize authentication manager."""
        self.jenkins_url = jenkins_url
        self.client_secrets_file = client_secrets_file
        self.session = requests.Session()
        self.token_cache_dir = Path.home() / ".jenkins-credential-extractor"
        self.token_cache_dir.mkdir(exist_ok=True)

        # Generate or load encryption key for token storage
        self.encryption_key = self._get_or_create_encryption_key()
        self.cipher = Fernet(self.encryption_key)

    def _get_or_create_encryption_key(self) -> bytes:
        """Get or create encryption key for secure token storage."""
        key_name = f"jenkins-cred-extractor-{urlparse(self.jenkins_url).hostname}"

        try:
            # Try to get existing key from keyring
            stored_key: str | None = keyring.get_password(
                "jenkins-credential-extractor", key_name
            )
            if stored_key:
                return stored_key.encode()
        except Exception:
            pass

        # Generate new key
        key = Fernet.generate_key()
        try:
            keyring.set_password("jenkins-credential-extractor", key_name, key.decode())
        except Exception:
            console.print(
                "[yellow]Warning: Could not store encryption key in keyring[/yellow]"
            )

        return key

    def _get_cached_session(self) -> dict[str, Any] | None:
        """Get cached session data if valid."""
        cache_file = (
            self.token_cache_dir / f"session_{urlparse(self.jenkins_url).hostname}.enc"
        )

        if not cache_file.exists():
            return None

        try:
            with open(cache_file, "rb") as f:
                encrypted_data = f.read()

            decrypted_data = self.cipher.decrypt(encrypted_data)
            session_data: dict[str, Any] = json.loads(decrypted_data.decode())

            # Check if session is still valid (not expired)
            if session_data.get("expires_at", 0) > time.time():
                return session_data
        except Exception as e:
            console.print(f"[yellow]Could not load cached session: {e}[/yellow]")

        return None

    def _cache_session(self, session_data: Dict[str, Any]) -> None:
        """Cache session data securely."""
        cache_file = (
            self.token_cache_dir / f"session_{urlparse(self.jenkins_url).hostname}.enc"
        )

        try:
            # Add expiration timestamp (24 hours from now)
            session_data["expires_at"] = time.time() + (24 * 60 * 60)

            json_data = json.dumps(session_data).encode()
            encrypted_data = self.cipher.encrypt(json_data)

            with open(cache_file, "wb") as f:
                f.write(encrypted_data)

            console.print("[green]✓ Session cached securely[/green]")
        except Exception as e:
            console.print(f"[yellow]Could not cache session: {e}[/yellow]")

    def _authenticate_with_google_oauth(self) -> Optional[Dict[str, Any]]:
        """Authenticate using Google OAuth2 flow."""
        if not GOOGLE_AUTH_AVAILABLE:
            console.print(
                "[red]Google OAuth not available - install google-auth-oauthlib[/red]"
            )
            return None

        if not self.client_secrets_file or not os.path.exists(self.client_secrets_file):
            console.print("[red]Google OAuth client secrets file not found[/red]")
            console.print("You need to:")
            console.print("1. Go to Google Cloud Console")
            console.print("2. Create OAuth 2.0 credentials")
            console.print("3. Download the client secrets JSON file")
            return None

        try:
            # Configure OAuth flow
            flow = Flow.from_client_secrets_file(
                self.client_secrets_file,
                scopes=["openid", "email", "profile"],
                redirect_uri="http://localhost:8080/callback",
            )

            # Get authorization URL
            auth_url, _ = flow.authorization_url(
                access_type="offline", include_granted_scopes="true"
            )

            console.print(
                "[blue]Please visit this URL to authorize the application:[/blue]"
            )
            console.print(f"[cyan]{auth_url}[/cyan]")

            # Get authorization code from user
            auth_code = Prompt.ask("Enter the authorization code")

            # Exchange code for tokens
            flow.fetch_token(code=auth_code)

            return {
                "access_token": flow.credentials.token,
                "refresh_token": flow.credentials.refresh_token,
                "token_uri": flow.credentials.token_uri,
                "client_id": flow.credentials.client_id,
                "client_secret": flow.credentials.client_secret,
                "auth_type": "google_oauth",
            }

        except Exception as e:
            console.print(f"[red]OAuth authentication failed: {e}[/red]")
            return None

    def _authenticate_with_jenkins_token(self) -> Optional[Dict[str, Any]]:
        """Authenticate using Jenkins API token."""
        console.print("[bold]Jenkins API Token Authentication[/bold]")
        console.print("You can generate an API token from Jenkins user settings")

        username = Prompt.ask("Jenkins username")
        api_token = Prompt.ask("Jenkins API token", password=True)

        if not username or not api_token:
            return None

        # Test the credentials
        auth = (username, api_token)
        test_url = urljoin(self.jenkins_url, API_JSON_ENDPOINT)

        try:
            response = requests.get(test_url, auth=auth, timeout=10)
            if response.status_code == 200:
                console.print("[green]✓ API token authentication successful[/green]")
                return {
                    "username": username,
                    "api_token": api_token,
                    "auth_type": "api_token",
                }
            else:
                console.print(
                    f"[red]Authentication failed: {response.status_code}[/red]"
                )
                return None
        except Exception as e:
            console.print(f"[red]Authentication test failed: {e}[/red]")
            return None

    def authenticate(self, force_reauth: bool = False) -> bool:
        """Authenticate to Jenkins with multiple methods."""
        if not force_reauth:
            # Try cached session first
            cached_session = self._get_cached_session()
            if cached_session:
                console.print("[green]✓ Using cached authentication[/green]")
                if cached_session.get("auth_type") == "api_token":
                    self.session.auth = (
                        cached_session["username"],
                        cached_session["api_token"],
                    )
                elif cached_session.get("auth_type") == "browser_session":
                    # Apply cached browser cookies to session
                    cookies = cached_session.get("cookies", {})
                    for name, value in cookies.items():
                        self.session.cookies.set(name, value)
                elif cached_session.get("auth_type") == "session_cookie":
                    # Apply cached session cookie with correct name
                    session_cookie = cached_session.get("session_cookie")
                    cookie_name = cached_session.get(
                        "session_cookie_name", "JSESSIONID"
                    )
                    if session_cookie:
                        self.session.cookies.set(cookie_name, session_cookie)
                return True

        console.print("\n[bold]Choose authentication method:[/bold]")
        console.print(
            "1. Browser Session Extraction (recommended for script console access)"
        )
        console.print("2. Jenkins API Token (traditional)")
        console.print("3. Google OAuth2 (if configured)")

        choice = Prompt.ask("Select method", choices=["1", "2", "3"], default="1")

        session_data = None

        if choice == "1":
            session_data = self._authenticate_with_browser_session()
        elif choice == "2":
            session_data = self._authenticate_with_jenkins_token()
        elif choice == "3":
            session_data = self._authenticate_with_google_oauth()

        if session_data:
            self._cache_session(session_data)

            # Apply authentication to current session based on type
            if session_data.get("auth_type") == "browser_session":
                cookies = session_data.get("cookies", {})
                for name, value in cookies.items():
                    self.session.cookies.set(name, value)
            elif session_data.get("auth_type") == "session_cookie":
                session_cookie = session_data.get("session_cookie")
                cookie_name = session_data.get("session_cookie_name", "JSESSIONID")
                if session_cookie:
                    self.session.cookies.set(cookie_name, session_cookie)
            elif session_data.get("auth_type") == "api_token":
                self.session.auth = (
                    session_data["username"],
                    session_data["api_token"],
                )

            return True

        return False

    def _authenticate_with_browser_session(self) -> Optional[Dict[str, Any]]:
        """Enhanced browser session authentication with automatic cookie detection."""
        console.print("\n[bold]Browser Session Authentication[/bold]")

        # Try to automatically extract browser cookies first
        extracted_cookies = self._extract_browser_cookies()

        if extracted_cookies:
            console.print("[green]✓ Found valid browser session automatically[/green]")
            return {
                "cookies": extracted_cookies,
                "auth_type": "browser_session",
                "auto_extracted": True,
            }

        # Fall back to manual extraction if automatic fails
        console.print(
            "[yellow]Automatic cookie extraction failed, using manual method...[/yellow]"
        )
        return self._authenticate_manual_browser()

    def _extract_browser_cookies(self) -> Optional[Dict[str, str]]:
        """Automatically extract Jenkins session cookies from popular browsers."""
        jenkins_domain = urlparse(self.jenkins_url).hostname
        if not jenkins_domain:
            return None

        # Try Chrome first (most common)
        cookies = self._extract_chrome_cookies(jenkins_domain)
        if cookies and self._validate_browser_cookies(cookies):
            console.print("[green]✓ Found valid Chrome session[/green]")
            return cookies

        # Try Firefox
        cookies = self._extract_firefox_cookies(jenkins_domain)
        if cookies and self._validate_browser_cookies(cookies):
            console.print("[green]✓ Found valid Firefox session[/green]")
            return cookies

        # Try Edge
        cookies = self._extract_edge_cookies(jenkins_domain)
        if cookies and self._validate_browser_cookies(cookies):
            console.print("[green]✓ Found valid Edge session[/green]")
            return cookies

        # Safari is more complex, just indicate it's available
        if self._has_safari_cookies(jenkins_domain):
            console.print(
                "[yellow]Safari cookies detected but require manual extraction[/yellow]"
            )

        return None

    def _extract_chrome_cookies(self, domain: str) -> Optional[Dict[str, str]]:
        """Extract cookies from Chrome browser."""
        from pathlib import Path

        chrome_paths = [
            Path.home()
            / "Library/Application Support/Google/Chrome/Default/Cookies",  # macOS
            Path.home() / ".config/google-chrome/Default/Cookies",  # Linux
            Path.home()
            / "AppData/Local/Google/Chrome/User Data/Default/Cookies",  # Windows
        ]

        for cookie_path in chrome_paths:
            if cookie_path.exists():
                cookies = self._query_chromium_database(cookie_path, domain)
                if cookies:
                    return cookies

        return None

    def _query_chromium_database(
        self, cookie_path: Path, domain: str
    ) -> Optional[Dict[str, str]]:
        """Query Chromium-based browser cookie database."""
        import sqlite3
        import shutil
        from pathlib import Path

        temp_db = Path("/tmp/chromium_cookies_temp.db")
        try:
            shutil.copy2(cookie_path, temp_db)

            conn = sqlite3.connect(str(temp_db))
            cursor = conn.cursor()

            # Query for Jenkins session cookies (including suffixed ones like JSESSIONID.e1b01059)
            cursor.execute(
                """
                SELECT name, value
                FROM cookies
                WHERE host_key LIKE ?
                AND (name LIKE 'JSESSIONID%' OR name LIKE '%session%' OR name LIKE '%jenkins%')
                AND expires_utc > ?
            """,
                (f"%{domain}%", int(time.time() * 1000000)),
            )

            cookies = {}
            for name, value in cursor.fetchall():
                if (
                    value and len(value) > 10
                ):  # Valid session cookies are usually longer
                    cookies[name] = value

            conn.close()
            return cookies if cookies else None

        except Exception as e:
            console.print(f"[dim]Chrome cookie extraction error: {e}[/dim]")
            return None
        finally:
            temp_db.unlink(missing_ok=True)

    def _extract_firefox_cookies(self, domain: str) -> Optional[Dict[str, str]]:
        """Extract cookies from Firefox browser."""
        from pathlib import Path

        firefox_dirs = [
            Path.home() / ".mozilla/firefox",
            Path.home() / "Library/Application Support/Firefox/Profiles",  # macOS
        ]

        for firefox_dir in firefox_dirs:
            if firefox_dir.exists():
                # Find default profile
                for profile_dir in firefox_dir.iterdir():
                    if profile_dir.is_dir() and "default" in profile_dir.name.lower():
                        cookie_db = profile_dir / "cookies.sqlite"
                        if cookie_db.exists():
                            return self._query_firefox_database(cookie_db, domain)
        return None

    def _query_firefox_database(
        self, cookie_db: Path, domain: str
    ) -> Optional[Dict[str, str]]:
        """Query Firefox cookie database."""
        import sqlite3

        try:
            conn = sqlite3.connect(str(cookie_db))
            cursor = conn.cursor()

            cursor.execute(
                """
                SELECT name, value
                FROM moz_cookies
                WHERE host LIKE ?
                AND (name LIKE 'JSESSIONID%' OR name LIKE '%session%' OR name LIKE '%jenkins%')
                AND expiry > ?
            """,
                (f"%{domain}%", int(time.time())),
            )

            cookies = {}
            for name, value in cursor.fetchall():
                if value and len(value) > 10:
                    cookies[name] = value

            conn.close()
            return cookies if cookies else None

        except Exception as e:
            console.print(f"[dim]Firefox cookie extraction error: {e}[/dim]")
            return None

    def _extract_edge_cookies(self, domain: str) -> Optional[Dict[str, str]]:
        """Extract cookies from Microsoft Edge browser."""
        from pathlib import Path

        edge_paths = [
            Path.home()
            / "AppData/Local/Microsoft/Edge/User Data/Default/Cookies",  # Windows
            Path.home()
            / "Library/Application Support/Microsoft Edge/Default/Cookies",  # macOS
        ]

        for cookie_path in edge_paths:
            if cookie_path.exists():
                # Edge uses the same format as Chrome
                cookies = self._query_chromium_database(cookie_path, domain)
                if cookies:
                    return cookies

        return None

    def _has_safari_cookies(self, domain: str) -> bool:
        """Check if Safari has Jenkins cookies (without parsing binary format)."""
        from pathlib import Path

        safari_paths = [
            Path.home() / "Library/Cookies/Cookies.binarycookies",
            Path.home()
            / "Library/Containers/com.apple.Safari/Data/Library/Cookies/Cookies.binarycookies",
        ]

        for cookie_path in safari_paths:
            if cookie_path.exists():
                try:
                    with open(cookie_path, "rb") as f:
                        data = f.read()

                    domain_bytes = domain.encode("utf-8")
                    jsessionid_bytes = b"JSESSIONID"

                    return domain_bytes in data and jsessionid_bytes in data

                except Exception:
                    continue

        return False

    def _validate_browser_cookies(self, cookies: Dict[str, str]) -> bool:
        """Validate extracted browser cookies by testing Jenkins API access."""
        try:
            # Create a test session with the cookies
            test_session = requests.Session()
            for name, value in cookies.items():
                test_session.cookies.set(name, value)

            # Test API access
            test_url = urljoin(self.jenkins_url, API_JSON_ENDPOINT)
            response = test_session.get(test_url, timeout=10)

            return response.status_code == 200

        except Exception:
            return False

    def _authenticate_manual_browser(self) -> Optional[Dict[str, Any]]:
        """Manual browser authentication with session extraction (fallback method)."""
        console.print("\n[bold]Manual Browser Authentication[/bold]")
        console.print(
            f"1. Open your browser and navigate to: [cyan]{self.jenkins_url}[/cyan]"
        )
        console.print("2. Log in with your credentials")
        console.print("3. Open browser developer tools (F12)")
        console.print("4. Go to Application/Storage > Cookies")
        console.print(
            "5. Find the Jenkins session cookie (usually 'JSESSIONID' or 'JSESSIONID.xxxx')"
        )

        if not Confirm.ask("Have you completed the login process?"):
            return None

        console.print("\n[bold]Cookie Information[/bold]")
        console.print("Please provide both the cookie name and value:")

        cookie_name = Prompt.ask(
            "Cookie name (e.g., 'JSESSIONID.e1b01059')", default="JSESSIONID"
        )
        cookie_value = Prompt.ask("Cookie value")

        if not cookie_name or not cookie_value:
            return None

        # Test the session cookie
        self.session.cookies.set(cookie_name, cookie_value)
        test_url = urljoin(self.jenkins_url, API_JSON_ENDPOINT)

        try:
            response = self.session.get(test_url, timeout=10)
            if response.status_code == 200:
                console.print(
                    "[green]✓ Session cookie authentication successful[/green]"
                )
                return {
                    "session_cookie": cookie_value,
                    "session_cookie_name": cookie_name,
                    "auth_type": "session_cookie",
                    "auto_extracted": False,
                }
            else:
                console.print(
                    f"[red]Session validation failed: {response.status_code}[/red]"
                )
                return None
        except Exception as e:
            console.print(f"[red]Session test failed: {e}[/red]")
            return None

    def is_authenticated(self) -> bool:
        """Check if current session is authenticated."""
        test_url = urljoin(self.jenkins_url, API_JSON_ENDPOINT)

        try:
            response = self.session.get(test_url, timeout=10)
            return response.status_code == 200
        except Exception:
            return False

    def get_authenticated_session(self) -> Optional[requests.Session]:
        """Get authenticated requests session."""
        if self.is_authenticated():
            return self.session

        if self.authenticate():
            return self.session

        return None

    def get_auth_method(self) -> Optional[str]:
        """Get the current authentication method."""
        cached_session = self._get_cached_session()
        if cached_session:
            return cached_session.get("auth_type")
        return None

    def clear_cached_session(self) -> None:
        """Clear cached authentication session."""
        cache_file = (
            self.token_cache_dir / f"session_{urlparse(self.jenkins_url).hostname}.enc"
        )
        if cache_file.exists():
            cache_file.unlink()
            console.print("[green]✓ Cached session cleared[/green]")
        else:
            console.print("[yellow]No cached session found[/yellow]")
