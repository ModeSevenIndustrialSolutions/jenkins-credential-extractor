# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

"""Jenkins credentials.xml parser for extracting repository credentials."""

import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

from rich.console import Console
from rich.prompt import Prompt

console = Console()

# Constants
USERNAME_PASSWORD_XPATH = (
    ".//com.cloudbees.plugins.credentials.impl.UsernamePasswordCredentialsImpl"
)
SYSTEM_CREDENTIAL_IDS = {
    "jenkins-ssh",
    "jenkins",
    "jenkins-log-archives",
    "docker",
    "os-cloud",
    "lftoolsini-nexus",
    "nonrtric-onap-nexus",
}
SYSTEM_USERNAMES = {"jenkins", "logs", "docker"}


class CredentialsParser:
    """Parser for Jenkins credentials.xml files."""

    def __init__(self, credentials_file: str) -> None:
        """Initialize with credentials file path."""
        self.credentials_file = credentials_file
        self.root: Optional[ET.Element] = None

    def parse(self) -> bool:
        """Parse the credentials XML file."""
        try:
            tree = ET.parse(self.credentials_file)
            self.root = tree.getroot()
            console.print(
                f"[green]✓ Successfully parsed {self.credentials_file}[/green]"
            )
            return True
        except ET.ParseError as e:
            console.print(f"[red]Error parsing XML: {e}[/red]")
            return False
        except FileNotFoundError:
            console.print(
                f"[red]Credentials file not found: {self.credentials_file}[/red]"
            )
            return False
        except Exception as e:
            console.print(f"[red]Unexpected error parsing credentials: {e}[/red]")
            return False

    def extract_nexus_credentials(self) -> List[Tuple[str, str]]:
        """Extract repository credentials."""
        if self.root is None:
            console.print("[red]No parsed XML available. Call parse() first.[/red]")
            return []

        credentials: List[Tuple[str, str]] = []

        for cred in self.root.findall(USERNAME_PASSWORD_XPATH):
            credential_tuple = self._extract_single_credential(cred)
            if credential_tuple:
                credentials.append(credential_tuple)

        console.print(f"[green]Found {len(credentials)} repository credentials[/green]")
        return credentials

    def _extract_single_credential(self, cred: ET.Element) -> Optional[Tuple[str, str]]:
        """Extract a single credential from an XML element."""
        username_elem = cred.find("username")
        password_elem = cred.find("password")
        id_elem = cred.find("id")

        if username_elem is None or password_elem is None or id_elem is None:
            return None

        username = username_elem.text or ""
        password = password_elem.text or ""
        cred_id = id_elem.text or ""

        if not self._is_repository_credential(cred_id, username):
            return None

        if password.startswith("{") and password.endswith("}"):
            encrypted_password = password[1:-1]
            return (username, encrypted_password)

        return None

    def _is_repository_credential(self, cred_id: str, username: str) -> bool:
        """Determine if this credential is for a repository."""
        return cred_id not in SYSTEM_CREDENTIAL_IDS and username not in SYSTEM_USERNAMES

    def get_credential_by_id(self, cred_id: str) -> Optional[Tuple[str, str]]:
        """Get a specific credential by ID."""
        if self.root is None:
            return None

        for cred in self.root.findall(USERNAME_PASSWORD_XPATH):
            id_elem = cred.find("id")
            if id_elem is not None and id_elem.text == cred_id:
                return self._extract_credential_data(cred)

        return None

    def _extract_credential_data(self, cred: ET.Element) -> Optional[Tuple[str, str]]:
        """Extract username and password from credential element."""
        username_elem = cred.find("username")
        password_elem = cred.find("password")

        if username_elem is None or password_elem is None:
            return None

        username = username_elem.text or ""
        password = password_elem.text or ""

        if password.startswith("{") and password.endswith("}"):
            encrypted_password = password[1:-1]
            return (username, encrypted_password)

        return None

    def list_all_credentials(self) -> List[Dict[str, str]]:
        """List all credentials with their metadata."""
        if self.root is None:
            return []

        all_creds: List[Dict[str, str]] = []

        for cred in self.root.findall(USERNAME_PASSWORD_XPATH):
            cred_info: Dict[str, str] = {}

            for field in ["id", "description", "username"]:
                elem = cred.find(field)
                cred_info[field] = elem.text if elem is not None and elem.text else ""

            cred_info["type"] = "UsernamePassword"
            all_creds.append(cred_info)

        return all_creds

    def extract_credentials_by_description(
        self, description_pattern: str
    ) -> List[Tuple[str, str]]:
        """Extract credentials that match a description pattern."""
        if self.root is None:
            console.print("[red]No parsed XML available. Call parse() first.[/red]")
            return []

        credentials: List[Tuple[str, str]] = []
        pattern_lower = description_pattern.lower()

        for cred in self.root.findall(USERNAME_PASSWORD_XPATH):
            desc_elem = cred.find("description")
            if desc_elem is not None and desc_elem.text:
                description = desc_elem.text.lower()
                if pattern_lower in description:
                    credential_tuple = self._extract_single_credential(cred)
                    if credential_tuple:
                        credentials.append(credential_tuple)

        console.print(
            f"[green]Found {len(credentials)} credentials matching '{description_pattern}'[/green]"
        )
        return credentials

    def get_unique_description_patterns(self) -> List[str]:
        """Get unique description patterns to help user choose what to extract."""
        if self.root is None:
            return []

        descriptions: set[str] = set()
        for cred in self.root.findall(USERNAME_PASSWORD_XPATH):
            desc_elem = cred.find("description")
            if desc_elem is not None and desc_elem.text:
                descriptions.add(desc_elem.text)

        return sorted(list(descriptions))

    def extract_credentials_by_pattern_choice(self) -> List[Tuple[str, str]]:
        """Interactive method to let user choose description pattern."""
        patterns = self.get_unique_description_patterns()

        if not patterns:
            console.print("[yellow]No credential descriptions found[/yellow]")
            return self.extract_nexus_credentials()  # Fallback to default method

        console.print("\n[bold]Available credential description patterns:[/bold]")
        console.print("  0. [yellow]Enter a substring to match credentials[/yellow]")
        for i, pattern in enumerate(patterns, 1):
            console.print(f"  {i}. [cyan]{pattern}[/cyan]")

        console.print(
            f"  {len(patterns) + 1}. [yellow]Extract all repository credentials[/yellow]"
        )

        while True:
            choice = Prompt.ask(f"\nSelect pattern (0-{len(patterns) + 1})")

            try:
                index = int(choice)
                if index == 0:
                    # User chose substring matching
                    substring = Prompt.ask("Enter string")
                    if substring.strip():
                        console.print(
                            f"[green]Searching for credentials matching: '{substring}'[/green]"
                        )
                        return self.extract_credentials_by_description(
                            substring.strip()
                        )
                    else:
                        console.print("[red]Please enter a valid search string.[/red]")
                        continue
                elif index == len(patterns) + 1:
                    # User chose to extract all
                    return self.extract_nexus_credentials()
                elif 1 <= index <= len(patterns):
                    selected_pattern = patterns[index - 1]
                    console.print(
                        f"[green]Selected pattern: '{selected_pattern}'[/green]"
                    )
                    return self.extract_credentials_by_description(selected_pattern)
                else:
                    console.print("[red]Invalid selection. Please try again.[/red]")
            except ValueError:
                # Try as description pattern search
                return self.extract_credentials_by_description(choice)
