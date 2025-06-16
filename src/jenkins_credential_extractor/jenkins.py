# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

"""Jenkins automation for downloading credentials and decrypting passwords."""

import subprocess
from typing import Dict, List, Optional, Tuple

import requests
from rich.console import Console
from rich.prompt import Prompt

console = Console()


class JenkinsAutomation:
    """Handle Jenkins server interactions."""

    def __init__(self, jenkins_url: str, jenkins_ip: str) -> None:
        """Initialize with Jenkins server details."""
        self.jenkins_url = jenkins_url
        self.jenkins_ip = jenkins_ip
        self.script_console_url = f"{jenkins_url}/manage/script"
        self.session = requests.Session()
        self._authenticated = False

    def download_credentials_file(self, local_path: str = "credentials.xml") -> bool:
        """Download credentials.xml from Jenkins server via SCP."""
        remote_path = "/var/lib/jenkins/credentials.xml"

        try:
            console.print(
                f"[blue]Downloading credentials from {self.jenkins_ip}...[/blue]"
            )

            # Use SCP command
            scp_command = ["scp", f"{self.jenkins_ip}:{remote_path}", local_path]

            # Run SCP with user interaction for authentication
            result = subprocess.run(
                scp_command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            if result.returncode == 0:
                console.print(
                    f"[green]✓ Downloaded credentials to {local_path}[/green]"
                )
                return True
            else:
                console.print(f"[red]SCP failed: {result.stderr}[/red]")
                return False

        except Exception as e:
            console.print(f"[red]Error downloading credentials: {e}[/red]")
            return False

    def check_jenkins_authentication(self) -> bool:
        """Check if user is authenticated to Jenkins."""
        try:
            console.print(
                f"[blue]Checking authentication to {self.jenkins_url}...[/blue]"
            )

            # Try to access the script console
            response = self.session.get(self.script_console_url, timeout=10)

            # If we get a redirect to login or 403, we're not authenticated
            if (
                response.status_code in [302, 401, 403]
                or "login" in response.url.lower()
            ):
                console.print("[yellow]Not authenticated to Jenkins[/yellow]")
                return False
            elif response.status_code == 200:
                console.print("[green]✓ Authenticated to Jenkins[/green]")
                self._authenticated = True
                return True
            else:
                console.print(
                    f"[yellow]Unexpected response: {response.status_code}[/yellow]"
                )
                return False

        except requests.exceptions.RequestException as e:
            console.print(f"[red]Cannot reach Jenkins server: {e}[/red]")
            return False

    def prompt_for_authentication(self) -> bool:
        """Prompt user to authenticate to Jenkins."""
        console.print("\n[bold yellow]Authentication Required[/bold yellow]")
        console.print(f"Please log in to Jenkins at: [cyan]{self.jenkins_url}[/cyan]")
        console.print("Use your Linux Foundation Google SSO account")
        console.print("You may need to provide 2FA code")

        input("Press Enter after you have logged in...")

        return self.check_jenkins_authentication()

    def decrypt_password_automated(self, encrypted_password: str) -> Optional[str]:
        """Decrypt a password using Jenkins script console automatically."""
        if (
            not self._authenticated
            and not self.check_jenkins_authentication()
            and not self.prompt_for_authentication()
        ):
            console.print(
                "[red]Authentication failed. Cannot decrypt passwords automatically.[/red]"
            )
            return None

        script = f"""
encrypted_pw = '{{{encrypted_password}}}'
passwd = hudson.util.Secret.decrypt(encrypted_pw)
println(passwd)
"""

        try:
            # First, get the page to extract CSRF token if needed
            console.print("[blue]Getting script console page...[/blue]")
            response = self.session.get(self.script_console_url, timeout=10)

            if response.status_code != 200:
                console.print(
                    f"[red]Failed to access script console: {response.status_code}[/red]"
                )
                return None

            # Look for CSRF token in the form
            import re

            csrf_token = None
            token_match = re.search(
                r'name="Jenkins-Crumb" value="([^"]+)"', response.text
            )
            if token_match:
                csrf_token = token_match.group(1)
                console.print("[blue]Found CSRF token[/blue]")

            # Submit the script
            console.print("[blue]Submitting script for decryption...[/blue]")
            data = {"script": script, "Submit": "Run"}

            headers: Dict[str, str] = {}
            if csrf_token:
                headers["Jenkins-Crumb"] = csrf_token
                data["Jenkins-Crumb"] = csrf_token

            # Submit the script
            submit_response = self.session.post(
                f"{self.script_console_url}", data=data, headers=headers, timeout=30
            )

            if submit_response.status_code == 200:
                # Extract the result from the response
                result_match = re.search(
                    r"<h2>Result</h2>\s*<pre[^>]*>(.*?)</pre>",
                    submit_response.text,
                    re.DOTALL,
                )
                if result_match:
                    result = result_match.group(1).strip()
                    console.print("[green]✓ Password decrypted successfully[/green]")
                    return result
                else:
                    console.print(
                        "[yellow]Could not extract result from response[/yellow]"
                    )
                    # Fallback to manual process
                    return self._manual_decrypt_fallback(encrypted_password)
            else:
                console.print(
                    f"[red]Script submission failed: {submit_response.status_code}[/red]"
                )
                return self._manual_decrypt_fallback(encrypted_password)

        except Exception as e:
            console.print(f"[yellow]Automated decryption failed: {e}[/yellow]")
            console.print("[blue]Falling back to manual process...[/blue]")
            return self._manual_decrypt_fallback(encrypted_password)

    def _manual_decrypt_fallback(self, encrypted_password: str) -> Optional[str]:
        """Fallback to manual decryption process."""
        script = f"""
encrypted_pw = '{{{encrypted_password}}}'
passwd = hudson.util.Secret.decrypt(encrypted_pw)
println(passwd)
"""

        console.print("\n[bold]Manual decryption required:[/bold]")
        console.print(f"1. Open: [cyan]{self.script_console_url}[/cyan]")
        console.print(f"2. Paste this script:\n[dim]{script}[/dim]")
        console.print("3. Click 'Run'")
        console.print("4. Copy the output password")

        decrypted = Prompt.ask("\nEnter the decrypted password")
        return decrypted if decrypted.strip() else None

    def decrypt_password(self, encrypted_password: str) -> Optional[str]:
        """Decrypt a password using Jenkins script console."""
        script = f"""
encrypted_pw = '{{{encrypted_password}}}'
passwd = hudson.util.Secret.decrypt(encrypted_pw)
println(passwd)
"""

        console.print(
            "[yellow]Decrypting password via Jenkins script console...[/yellow]"
        )
        console.print(f"[dim]Script console URL: {self.script_console_url}[/dim]")

        # For security reasons, we'll guide the user through manual decryption
        # rather than automating HTTP requests to Jenkins
        console.print("\n[bold]To decrypt this password:[/bold]")
        console.print(f"1. Open: [cyan]{self.script_console_url}[/cyan]")
        console.print(f"2. Paste this script:\n[dim]{script}[/dim]")
        console.print("3. Click 'Run'")
        console.print("4. Copy the output password")

        decrypted = Prompt.ask("\nEnter the decrypted password")
        return decrypted if decrypted.strip() else None

    def batch_decrypt_passwords(
        self, credentials: List[Tuple[str, str]]
    ) -> List[Tuple[str, str]]:
        """Decrypt multiple passwords with automated and manual options."""
        decrypted_credentials: List[Tuple[str, str]] = []

        console.print(f"\n[bold]Decrypting {len(credentials)} passwords...[/bold]")

        # Check if automated decryption is possible
        use_automated = True
        if (
            not self.check_jenkins_authentication()
            and not self.prompt_for_authentication()
        ):
            console.print("[yellow]Falling back to manual decryption process[/yellow]")
            use_automated = False

        for i, (username, encrypted_password) in enumerate(credentials, 1):
            console.print(
                f"\n[bold]Credential {i}/{len(credentials)}: {username}[/bold]"
            )

            decrypted = None
            if use_automated:
                # Try automated decryption first
                decrypted = self.decrypt_password_automated(encrypted_password)

            if not decrypted:
                # Fall back to manual process
                decrypted = self._manual_decrypt_fallback(encrypted_password)

            if decrypted and decrypted.lower() != "skip":
                decrypted_credentials.append((username, decrypted))
                console.print(f"[green]✓ Added {username}[/green]")
            else:
                console.print(f"[yellow]Skipped {username}[/yellow]")

        return decrypted_credentials

    def save_credentials_file(
        self, credentials: List[Tuple[str, str]], output_file: str = "credentials.txt"
    ) -> bool:
        """Save decrypted credentials to a text file."""
        try:
            with open(output_file, "w", encoding="utf-8") as f:
                for username, password in credentials:
                    f.write(f"{password} {username}\n")

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
