# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

"""Jenkins automation with script console and batch password decryption."""

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple, Any
from urllib.parse import urljoin

import requests
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn

from .auth import JenkinsAuthManager
from .error_handling import (
    NetworkError,
    AuthenticationError,
    ScriptExecutionError,
    default_rate_limiter,
    validate_jenkins_response,
)

console = Console()


class JenkinsAutomation:
    """Unified Jenkins automation with comprehensive credential extraction and decryption."""

    def __init__(
        self,
        jenkins_url: str,
        jenkins_ip: str,
        client_secrets_file: Optional[str] = None,
        auth_manager: Optional[JenkinsAuthManager] = None,
    ):
        """Initialize Jenkins automation."""
        self.jenkins_url = jenkins_url
        self.jenkins_ip = jenkins_ip

        # Use provided auth manager or create new one
        if auth_manager:
            self.auth_manager = auth_manager
        else:
            self.auth_manager = JenkinsAuthManager(jenkins_url, client_secrets_file)

        self.script_console_url = urljoin(jenkins_url, "/manage/script")
        self.session: Optional[requests.Session] = None

    def ensure_authentication(self) -> bool:
        """Ensure we have valid authentication."""
        if self.session is None:
            self.session = self.auth_manager.get_authenticated_session()
            return self.session is not None

        # Check if current session is still valid
        if not self.auth_manager.is_authenticated():
            console.print("[yellow]Session expired, re-authenticating...[/yellow]")
            self.session = self.auth_manager.get_authenticated_session()
            return self.session is not None

        return True

    def _get_csrf_token(self) -> Optional[str]:
        """Get CSRF token from Jenkins."""
        try:
            if not self.session:
                return None

            response = self.session.get(self.script_console_url, timeout=10)
            if response.status_code != 200:
                return None

            # Look for CSRF token
            token_match = re.search(
                r'name="Jenkins-Crumb" value="([^"]+)"', response.text
            )
            if token_match:
                return token_match.group(1)

            # Alternative CSRF token location
            token_match = re.search(r'"crumb":"([^"]+)"', response.text)
            if token_match:
                return token_match.group(1)

            return None
        except Exception:
            return None

    def _decrypt_password_with_retry(
        self, encrypted_password: str, max_retries: int = 3
    ) -> Optional[str]:
        """Internal method to decrypt password with comprehensive retry logic."""
        if not self.ensure_authentication():
            raise AuthenticationError("Failed to authenticate with Jenkins")

        script = f"""
encrypted_pw = '{{{encrypted_password}}}'
passwd = hudson.util.Secret.decrypt(encrypted_pw)
println(passwd)
"""

        for attempt in range(max_retries):
            try:
                # Rate limiting
                default_rate_limiter.wait_if_needed()

                # Get CSRF token
                csrf_token = self._get_csrf_token()

                # Prepare request data
                data = {"script": script, "Submit": "Run"}
                headers: Dict[str, str] = {}

                if csrf_token:
                    headers["Jenkins-Crumb"] = csrf_token
                    data["Jenkins-Crumb"] = csrf_token

                # Submit script
                if not self.session:
                    raise AuthenticationError("No valid session")

                response = self.session.post(
                    self.script_console_url, data=data, headers=headers, timeout=30
                )

                # Validate response
                validate_jenkins_response(response)

                # Extract result
                result = self._extract_script_result(response.text)
                if result:
                    return result
                else:
                    if attempt < max_retries - 1:
                        console.print(
                            f"[yellow]No result found, retrying... ({attempt + 1}/{max_retries})[/yellow]"
                        )
                        time.sleep(2**attempt)  # Exponential backoff
                        continue
                    else:
                        raise ScriptExecutionError(
                            "No result found in Jenkins response"
                        )

            except (requests.RequestException, NetworkError) as e:
                if attempt < max_retries - 1:
                    delay = 2**attempt
                    console.print(
                        f"[yellow]Network error, retrying in {delay}s: {e}[/yellow]"
                    )
                    time.sleep(delay)
                else:
                    raise NetworkError(
                        f"Network operation failed after {max_retries} attempts: {e}"
                    )

            except AuthenticationError as e:
                # Check if this is a permission issue vs authentication issue
                if "Access forbidden" in str(e) or "check permissions" in str(e):
                    console.print(
                        "[yellow]⚠️  Script console permissions insufficient[/yellow]"
                    )
                    console.print("[yellow]💡 Enhanced automation requires:[/yellow]")
                    console.print(
                        "[yellow]   • Overall/Administer permission, or[/yellow]"
                    )
                    console.print("[yellow]   • Hudson/RunScripts permission[/yellow]")
                    raise AuthenticationError(
                        "Script console permissions insufficient for enhanced automation"
                    )

                # Try to re-authenticate once for actual auth failures
                if attempt == 0:
                    console.print(
                        "[yellow]Authentication failed, attempting to re-authenticate...[/yellow]"
                    )
                    self.session = None
                    if not self.ensure_authentication():
                        raise AuthenticationError("Re-authentication failed")
                else:
                    raise

        return None

    def _extract_script_result(self, response_text: str) -> Optional[str]:
        """Extract script execution result from Jenkins response."""
        # Try primary result extraction
        result_match = re.search(
            r"<h2>Result</h2>\s*<pre[^>]*>(.*?)</pre>",
            response_text,
            re.DOTALL,
        )
        if result_match:
            result = result_match.group(1).strip()
            # Clean up HTML entities
            result = (
                result.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
            )
            return result

        # Try alternative result extraction
        result_match = re.search(
            r'<div class="console-output"[^>]*>(.*?)</div>',
            response_text,
            re.DOTALL,
        )
        if result_match:
            result = result_match.group(1).strip()
            return result

        return None

    def decrypt_single_password(
        self, encrypted_password: str, max_retries: int = 3
    ) -> Optional[str]:
        """Decrypt a single password with retry logic and proper error handling."""
        return self._decrypt_password_with_retry(encrypted_password, max_retries)

    def batch_decrypt_passwords_parallel(
        self, credentials: List[Tuple[str, str]], max_workers: Optional[int] = None
    ) -> List[Tuple[str, str]]:
        """Decrypt passwords in parallel with proper error handling and performance tracking."""
        if not self.ensure_authentication():
            console.print("[red]Authentication failed[/red]")
            return []

        if max_workers is None:
            max_workers = min(10, len(credentials))

        decrypted_credentials: List[Tuple[str, str]] = []

        console.print(
            f"[bold]Decrypting {len(credentials)} passwords in parallel ({max_workers} workers)...[/bold]"
        )

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
        ) as progress:
            task = progress.add_task("Decrypting passwords...", total=len(credentials))

            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all tasks
                future_to_cred = {
                    executor.submit(
                        self._decrypt_password_with_retry, encrypted_password
                    ): (username, encrypted_password)
                    for username, encrypted_password in credentials
                }

                # Collect results
                for future in as_completed(future_to_cred):
                    username, _ = future_to_cred[future]
                    try:
                        decrypted_password = future.result()
                        if decrypted_password:
                            decrypted_credentials.append((username, decrypted_password))
                        else:
                            console.print(
                                f"[red]Failed to decrypt password for {username}[/red]"
                            )
                    except Exception as e:
                        console.print(f"[red]Error decrypting {username}: {e}[/red]")

                    progress.advance(task)

        console.print(
            f"[green]Successfully decrypted {len(decrypted_credentials)}/{len(credentials)} passwords[/green]"
        )
        return decrypted_credentials

    def batch_decrypt_passwords_optimized(
        self, credentials: List[Tuple[str, str]]
    ) -> List[Tuple[str, str]]:
        """Decrypt passwords using a single optimized batch script."""
        if not self.ensure_authentication():
            console.print("[red]Authentication failed[/red]")
            return []

        console.print(
            f"[bold]Decrypting {len(credentials)} passwords with optimized batch script...[/bold]"
        )

        # Build batch script
        script_lines = ["import groovy.json.JsonBuilder"]
        script_lines.append("def results = [:]")

        for username, encrypted_password in credentials:
            script_lines.append("try {")
            script_lines.append(f"  encrypted_pw = '{{{encrypted_password}}}'")
            script_lines.append("  passwd = hudson.util.Secret.decrypt(encrypted_pw)")
            script_lines.append(f"  results['{username}'] = passwd")
            script_lines.append("} catch (Exception e) {")
            script_lines.append(f"  results['{username}'] = 'ERROR: ' + e.message")
            script_lines.append("}")

        script_lines.append("def json = new JsonBuilder(results)")
        script_lines.append("println json.toPrettyString()")

        batch_script = "\n".join(script_lines)

        try:
            # Get CSRF token
            csrf_token = self._get_csrf_token()

            # Prepare request data
            data = {"script": batch_script, "Submit": "Run"}
            headers: Dict[str, str] = {}

            if csrf_token:
                headers["Jenkins-Crumb"] = csrf_token
                data["Jenkins-Crumb"] = csrf_token

            # Submit batch script
            if not self.session:
                raise AuthenticationError("No valid session")

            response = self.session.post(
                self.script_console_url,
                data=data,
                headers=headers,
                timeout=120,  # Longer timeout for batch operation
            )

            validate_jenkins_response(response)

            # Extract and parse JSON result
            result_text = self._extract_script_result(response.text)
            if result_text:
                import json

                try:
                    result_data = json.loads(result_text)
                    decrypted_credentials = []

                    for username, password in result_data.items():
                        if not password.startswith("ERROR:"):
                            decrypted_credentials.append((username, password))
                        else:
                            console.print(
                                f"[red]Failed to decrypt {username}: {password}[/red]"
                            )

                    console.print(
                        f"[green]Successfully decrypted {len(decrypted_credentials)}/{len(credentials)} passwords[/green]"
                    )
                    return decrypted_credentials

                except json.JSONDecodeError as e:
                    console.print(f"[red]Failed to parse batch results: {e}[/red]")
                    return []
            else:
                console.print("[red]No result from batch script[/red]")
                return []

        except Exception as e:
            console.print(f"[red]Batch decryption failed: {e}[/red]")
            return []

    def batch_decrypt_passwords(
        self, credentials: List[Tuple[str, str]], use_batch_optimization: bool = True
    ) -> List[Tuple[str, str]]:
        """
        Main entry point for batch password decryption.
        Automatically chooses between script console automation and manual fallback.
        """
        if not credentials:
            console.print("[yellow]No credentials to decrypt[/yellow]")
            return []

        console.print(f"[bold]Processing {len(credentials)} credentials...[/bold]")

        # Try automated script console access first
        if self._check_script_console_permissions():
            console.print(
                "[green]✓ Script console access available - using automated decryption[/green]"
            )

            # Choose optimal automated method based on credential count
            if len(credentials) > 50 and use_batch_optimization:
                return self.batch_decrypt_passwords_optimized(credentials)
            elif len(credentials) > 10:
                return self.batch_decrypt_passwords_parallel(credentials)
            else:
                # Sequential for small numbers
                decrypted = []
                for username, encrypted_password in credentials:
                    result = self.decrypt_single_password(encrypted_password)
                    if result:
                        decrypted.append((username, result))
                return decrypted
        else:
            console.print(
                "[yellow]⚠️  Script console access not available - using manual decryption[/yellow]"
            )
            return self._manual_batch_decrypt_fallback(credentials)

    def _manual_batch_decrypt_fallback(
        self, credentials: List[Tuple[str, str]]
    ) -> List[Tuple[str, str]]:
        """Manual decryption fallback when script console access is not available."""
        console.print(
            f"[bold]Manual decryption mode for {len(credentials)} credentials[/bold]"
        )
        console.print(
            "[yellow]You'll need to manually decrypt each password using the Jenkins script console[/yellow]"
        )

        decrypted_credentials = []

        for i, (username, encrypted_password) in enumerate(credentials, 1):
            console.print(
                f"\n[cyan]Credential {i}/{len(credentials)}: {username}[/cyan]"
            )
            decrypted_password = self._manual_decrypt_fallback(encrypted_password)

            if decrypted_password and decrypted_password.lower() != "skip":
                decrypted_credentials.append((username, decrypted_password))
                console.print(f"[green]✓ Added {username}[/green]")
            else:
                console.print(f"[yellow]Skipped {username}[/yellow]")

        return decrypted_credentials

    def _manual_decrypt_fallback(self, encrypted_password: str) -> Optional[str]:
        """Fallback to manual password decryption via script console."""
        console.print("\n[yellow]Manual decryption required:[/yellow]")
        console.print(f"1. Open: [cyan]{self.script_console_url}[/cyan]")
        console.print("2. Paste this script:")
        console.print()
        console.print(f"[dim]encrypted_pw = '{{{encrypted_password}}}'[/dim]")
        console.print("[dim]passwd = hudson.util.Secret.decrypt(encrypted_pw)[/dim]")
        console.print("[dim]println(passwd)[/dim]")
        console.print()
        console.print("3. Click 'Run'")
        console.print("4. Copy the output password")
        console.print()

        from rich.prompt import Prompt

        password = Prompt.ask(
            "Enter the decrypted password (or 'skip' to skip)", default=""
        )

        if password.lower() == "skip" or not password:
            return None

        return password

    def _select_processing_method(self, credentials: List[Tuple[str, str]]) -> str:
        """Select optimal processing method based on credential count."""
        credential_count = len(credentials)

        if credential_count <= 5:
            return "sequential"
        elif credential_count <= 50:
            return "parallel"
        else:
            return "optimized"

    def _calculate_optimal_threads(self, credential_count: int) -> int:
        """Calculate optimal thread count based on credential count."""
        if credential_count <= 10:
            return min(3, credential_count)
        elif credential_count <= 50:
            return min(10, credential_count)
        else:
            return min(20, credential_count)

    def check_script_console_permissions(self) -> bool:
        """Public method to check if script console permissions are available."""
        return self._check_script_console_permissions()

    def _check_script_console_permissions(self) -> bool:
        """Check if we have permissions to access the script console."""
        try:
            if not self.session:
                return False

            # Try to access the script console page
            response = self.session.get(self.script_console_url, timeout=10)

            # If we get 403, we don't have script console permissions
            if response.status_code == 403:
                return False
            elif response.status_code == 200:
                # Check if the page contains the script execution form
                return (
                    "Jenkins-Crumb" in response.text
                    or "script" in response.text.lower()
                )
            else:
                # Other status codes indicate different issues
                return False

        except Exception:
            return False

    def validate_jenkins_access(self) -> bool:
        """Validate that Jenkins is accessible and working."""
        try:
            if not self.ensure_authentication():
                console.print("[yellow]⚠️  Authentication failed[/yellow]")
                return False

            if not self.session:
                console.print("[yellow]⚠️  No active session[/yellow]")
                return False

            # Test basic connectivity using API endpoint (more reliable than script console)
            api_url = urljoin(self.jenkins_url, "/api/json")
            response = self.session.get(api_url, timeout=10)

            if response.status_code != 200:
                console.print(
                    f"[yellow]⚠️  API endpoint returned {response.status_code}[/yellow]"
                )
                return False

            # Check script console permissions for enhanced automation
            if not self._check_script_console_permissions():
                console.print("[yellow]⚠️  Script console access not available[/yellow]")
                console.print(
                    "[yellow]💡 Enhanced automation requires script console permissions:[/yellow]"
                )
                console.print("[yellow]   • Overall/Administer permission, or[/yellow]")
                console.print("[yellow]   • Hudson/RunScripts permission[/yellow]")
                console.print(
                    "[yellow]🔄 Falling back to legacy automation...[/yellow]"
                )
                return False

            return True

        except Exception as e:
            console.print(f"[red]Jenkins access validation failed: {e}[/red]")
            return False

    def get_jenkins_info(self) -> dict[str, Any] | None:
        """Get Jenkins server information."""
        try:
            if not self.ensure_authentication():
                return None

            if not self.session:
                return None

            api_url = urljoin(self.jenkins_url, "/api/json")
            response = self.session.get(api_url, timeout=10)

            if response.status_code == 200:
                result: dict[str, Any] = response.json()
                return result
            else:
                return None

        except Exception as e:
            console.print(f"[red]Failed to get Jenkins info: {e}[/red]")
            return None

    def download_credentials_file(self, output_file: str) -> bool:
        """Download credentials.xml from Jenkins server via SCP."""
        console.print(f"[blue]Downloading credentials from {self.jenkins_ip}...[/blue]")

        try:
            import subprocess

            cmd = [
                "scp",
                f"{self.jenkins_ip}:/var/lib/jenkins/credentials.xml",
                output_file,
            ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode == 0:
                console.print(
                    f"[green]✓ Downloaded credentials to {output_file}[/green]"
                )
                return True
            else:
                console.print(f"[red]SCP failed: {result.stderr}[/red]")
                return False

        except subprocess.TimeoutExpired:
            console.print("[red]SCP operation timed out[/red]")
            return False
        except Exception as e:
            console.print(f"[red]Error downloading credentials: {e}[/red]")
            return False

    def save_credentials_file(
        self, credentials: List[Tuple[str, str]], output_file: str
    ) -> bool:
        """Save decrypted credentials to file."""
        try:
            with open(output_file, "w") as f:
                f.write("# Decrypted Jenkins Credentials\n")
                f.write("# Format: username=password\n\n")

                for username, password in credentials:
                    f.write(f"{username}={password}\n")

            console.print(
                f"[green]✓ Saved {len(credentials)} credentials to {output_file}[/green]"
            )
            return True

        except Exception as e:
            console.print(f"[red]Error saving credentials: {e}[/red]")
            return False

    def test_jenkins_connectivity(self) -> bool:
        """Test if Jenkins server is accessible."""
        try:
            console.print(f"[blue]Testing connectivity to {self.jenkins_url}...[/blue]")

            response = requests.get(f"{self.jenkins_url}/api/json", timeout=10)
            if response.status_code == 200:
                console.print("[green]✓ Jenkins server is accessible[/green]")
                return True
            else:
                console.print(
                    f"[yellow]Jenkins returned status {response.status_code}[/yellow]"
                )
                return False

        except requests.exceptions.RequestException as e:
            console.print(f"[red]Cannot reach Jenkins server: {e}[/red]")
            return False

    def batch_decrypt_passwords_intelligently(
        self, credentials: List[Tuple[str, str]]
    ) -> List[Tuple[str, str]]:
        """Intelligently choose the best batch decryption method based on credential count."""
        if not credentials:
            return []

        method = self._select_processing_method(credentials)
        console.print(
            f"[blue]Using {method} processing for {len(credentials)} credentials[/blue]"
        )

        if method == "sequential":
            # For small batches, use the legacy manual method
            return self.batch_decrypt_passwords(credentials)
        elif method == "parallel":
            # For medium batches, use parallel processing
            return self.batch_decrypt_passwords_parallel(credentials)
        else:  # optimized
            # For large batches, use the optimized single-script method
            return self.batch_decrypt_passwords_optimized(credentials)
