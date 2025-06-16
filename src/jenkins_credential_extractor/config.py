# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

"""Configuration and setup utilities for Jenkins automation."""

import json
import os
from pathlib import Path
from typing import Dict, Optional

from rich.console import Console
from rich.prompt import Confirm, Prompt

console = Console()


class JenkinsConfigManager:
    """Manage configuration for Jenkins automation."""

    def __init__(self):
        """Initialize configuration manager."""
        self.config_dir = Path.home() / ".jenkins-credential-extractor"
        self.config_dir.mkdir(exist_ok=True)
        self.config_file = self.config_dir / "config.json"

    def load_config(self) -> Dict:
        """Load configuration from file."""
        if self.config_file.exists():
            try:
                with open(self.config_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                console.print(f"[yellow]Could not load config: {e}[/yellow]")

        return {}

    def save_config(self, config: Dict) -> None:
        """Save configuration to file."""
        try:
            with open(self.config_file, "w") as f:
                json.dump(config, f, indent=2)
            console.print("[green]✓ Configuration saved[/green]")
        except Exception as e:
            console.print(f"[red]Could not save config: {e}[/red]")

    def setup_google_oauth(self) -> Optional[str]:
        """Guide user through Google OAuth setup."""
        console.print("\n[bold]Google OAuth Setup[/bold]")
        console.print("To enable Google OAuth authentication, you need to:")
        console.print("1. Go to the Google Cloud Console")
        console.print("2. Create a new project or select existing one")
        console.print("3. Enable the Google+ API")
        console.print("4. Create OAuth 2.0 credentials (Web application)")
        console.print("5. Add authorized redirect URI: http://localhost:8080/callback")
        console.print("6. Download the client secrets JSON file")

        if not Confirm.ask("\nHave you completed these steps?"):
            return None

        # Get the client secrets file path
        secrets_file = Prompt.ask(
            "Enter path to your client secrets JSON file",
            default=str(self.config_dir / "client_secrets.json")
        )

        if not os.path.exists(secrets_file):
            console.print(f"[red]File not found: {secrets_file}[/red]")
            return None

        # Validate the file
        try:
            with open(secrets_file, "r") as f:
                secrets = json.load(f)

            if "web" not in secrets and "installed" not in secrets:
                console.print("[red]Invalid client secrets file format[/red]")
                return None

            console.print("[green]✓ Client secrets file validated[/green]")

            # Save to config
            config = self.load_config()
            config["google_oauth"] = {
                "client_secrets_file": secrets_file,
                "enabled": True
            }
            self.save_config(config)

            return secrets_file

        except Exception as e:
            console.print(f"[red]Error validating client secrets: {e}[/red]")
            return None

    def get_google_oauth_config(self) -> Optional[str]:
        """Get Google OAuth configuration."""
        config = self.load_config()
        oauth_config = config.get("google_oauth", {})

        if oauth_config.get("enabled") and oauth_config.get("client_secrets_file"):
            secrets_file = oauth_config["client_secrets_file"]
            if os.path.exists(secrets_file):
                return secrets_file

        return None

    def setup_jenkins_connection(self, jenkins_url: str, jenkins_ip: str) -> None:
        """Setup and save Jenkins connection details."""
        config = self.load_config()

        config["jenkins"] = {
            "url": jenkins_url,
            "ip": jenkins_ip,
            "last_used": True
        }

        self.save_config(config)

    def get_jenkins_connections(self) -> Dict:
        """Get saved Jenkins connections."""
        config = self.load_config()
        return config.get("jenkins", {})

    def setup_initial_configuration(self) -> Dict:
        """Interactive setup for initial configuration."""
        console.print("\n[bold]Jenkins Credential Extractor Setup[/bold]")

        # Jenkins connection details
        jenkins_url = Prompt.ask("Jenkins URL (e.g., https://jenkins.example.com)")
        jenkins_ip = Prompt.ask("Jenkins IP (for SCP, e.g., jenkins.example.com)")

        self.setup_jenkins_connection(jenkins_url, jenkins_ip)

        # Optional Google OAuth setup
        if Confirm.ask("\nWould you like to set up Google OAuth for automatic authentication?"):
            oauth_file = self.setup_google_oauth()
            if oauth_file:
                console.print("[green]✓ Google OAuth configured[/green]")
            else:
                console.print("[yellow]Google OAuth setup skipped[/yellow]")

        # Authentication preferences
        config = self.load_config()
        config["auth_preferences"] = {
            "preferred_method": "api_token",  # Default to API token
            "cache_sessions": True,
            "session_timeout_hours": 24
        }

        self.save_config(config)

        console.print("\n[green]✓ Initial configuration completed![/green]")
        console.print("You can modify these settings later by running the setup command again.")

        return config
