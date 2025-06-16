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
            stored_key = keyring.get_password("jenkins-credential-extractor", key_name)
            if stored_key:
                return stored_key.encode()
        except Exception:
            pass

        # Generate new key
        key = Fernet.generate_key()
        try:
            keyring.set_password("jenkins-credential-extractor", key_name, key.decode())
        except Exception:
            console.print("[yellow]Warning: Could not store encryption key in keyring[/yellow]")

        return key

    def _get_cached_session(self) -> Optional[Dict[str, Any]]:
        """Get cached session data if valid."""
        cache_file = self.token_cache_dir / f"session_{urlparse(self.jenkins_url).hostname}.enc"

        if not cache_file.exists():
            return None

        try:
            with open(cache_file, "rb") as f:
                encrypted_data = f.read()

            decrypted_data = self.cipher.decrypt(encrypted_data)
            session_data = json.loads(decrypted_data.decode())

            # Check if session is still valid (not expired)
            if session_data.get("expires_at", 0) > time.time():
                return session_data
        except Exception as e:
            console.print(f"[yellow]Could not load cached session: {e}[/yellow]")

        return None

    def _cache_session(self, session_data: Dict[str, Any]) -> None:
        """Cache session data securely."""
        cache_file = self.token_cache_dir / f"session_{urlparse(self.jenkins_url).hostname}.enc"

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
            console.print("[red]Google OAuth not available - install google-auth-oauthlib[/red]")
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
                redirect_uri="http://localhost:8080/callback"
            )

            # Get authorization URL
            auth_url, _ = flow.authorization_url(
                access_type="offline",
                include_granted_scopes="true"
            )

            console.print("[blue]Please visit this URL to authorize the application:[/blue]")
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
                "auth_type": "google_oauth"
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
                    "auth_type": "api_token"
                }
            else:
                console.print(f"[red]Authentication failed: {response.status_code}[/red]")
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
                    self.session.auth = (cached_session["username"], cached_session["api_token"])
                # Add other auth types as needed
                return True

        console.print("\n[bold]Choose authentication method:[/bold]")
        console.print("1. Jenkins API Token (recommended)")
        console.print("2. Google OAuth2 (if configured)")
        console.print("3. Manual browser authentication")

        choice = Prompt.ask("Select method", choices=["1", "2", "3"], default="1")

        session_data = None

        if choice == "1":
            session_data = self._authenticate_with_jenkins_token()
        elif choice == "2":
            session_data = self._authenticate_with_google_oauth()
        elif choice == "3":
            session_data = self._authenticate_manual_browser()

        if session_data:
            self._cache_session(session_data)
            return True

        return False

    def _authenticate_manual_browser(self) -> Optional[Dict[str, Any]]:
        """Manual browser authentication with session extraction."""
        console.print("\n[bold]Manual Browser Authentication[/bold]")
        console.print(f"1. Open your browser and navigate to: [cyan]{self.jenkins_url}[/cyan]")
        console.print("2. Log in with your credentials")
        console.print("3. Open browser developer tools (F12)")
        console.print("4. Go to Application/Storage > Cookies")
        console.print("5. Find the Jenkins session cookie (usually 'JSESSIONID')")

        if not Confirm.ask("Have you completed the login process?"):
            return None

        session_cookie = Prompt.ask("Enter the JSESSIONID cookie value")
        if not session_cookie:
            return None

        # Test the session cookie
        self.session.cookies.set("JSESSIONID", session_cookie)
        test_url = urljoin(self.jenkins_url, API_JSON_ENDPOINT)

        try:
            response = self.session.get(test_url, timeout=10)
            if response.status_code == 200:
                console.print("[green]✓ Session cookie authentication successful[/green]")
                return {
                    "session_cookie": session_cookie,
                    "auth_type": "session_cookie"
                }
            else:
                console.print(f"[red]Session validation failed: {response.status_code}[/red]")
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
        cache_file = self.token_cache_dir / f"session_{urlparse(self.jenkins_url).hostname}.enc"
        if cache_file.exists():
            cache_file.unlink()
            console.print("[green]✓ Cached session cleared[/green]")
        else:
            console.print("[yellow]No cached session found[/yellow]")
