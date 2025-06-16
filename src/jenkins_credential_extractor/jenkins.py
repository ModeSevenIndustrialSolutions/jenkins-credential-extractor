# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

"""Jenkins automation for downloading credentials and decrypting passwords."""

import subprocess
from typing import List, Optional, Tuple

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
        
    def download_credentials_file(self, local_path: str = "credentials.xml") -> bool:
        """Download credentials.xml from Jenkins server via SCP."""
        remote_path = "/var/lib/jenkins/credentials.xml"
        
        try:
            console.print(f"[blue]Downloading credentials from {self.jenkins_ip}...[/blue]")
            
            # Use SCP command
            scp_command = [
                "scp",
                f"{self.jenkins_ip}:{remote_path}",
                local_path
            ]
            
            # Run SCP with user interaction for authentication
            result = subprocess.run(
                scp_command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            
            if result.returncode == 0:
                console.print(f"[green]✓ Downloaded credentials to {local_path}[/green]")
                return True
            else:
                console.print(f"[red]SCP failed: {result.stderr}[/red]")
                return False
                
        except Exception as e:
            console.print(f"[red]Error downloading credentials: {e}[/red]")
            return False
    
    def decrypt_password(self, encrypted_password: str) -> Optional[str]:
        """Decrypt a password using Jenkins script console."""
        script = f"""
encrypted_pw = '{{{encrypted_password}}}'
passwd = hudson.util.Secret.decrypt(encrypted_pw)
println(passwd)
"""
        
        console.print("[yellow]Decrypting password via Jenkins script console...[/yellow]")
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
    
    def batch_decrypt_passwords(self, credentials: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
        """Decrypt multiple passwords with user guidance."""
        decrypted_credentials: List[Tuple[str, str]] = []
        
        console.print(f"\n[bold]Decrypting {len(credentials)} passwords...[/bold]")
        console.print(f"[dim]Script console URL: {self.script_console_url}[/dim]\n")
        
        for i, (username, encrypted_password) in enumerate(credentials, 1):
            console.print(f"\n[bold]Credential {i}/{len(credentials)}: {username}[/bold]")
            
            script = f"""
encrypted_pw = '{{{encrypted_password}}}'
passwd = hudson.util.Secret.decrypt(encrypted_pw)
println(passwd)
"""
            
            console.print(f"[yellow]Script to run:[/yellow]\n[dim]{script}[/dim]")
            
            while True:
                decrypted = Prompt.ask("Enter the decrypted password (or 'skip' to skip)")
                if decrypted.lower() == 'skip':
                    console.print(f"[yellow]Skipped {username}[/yellow]")
                    break
                elif decrypted.strip():
                    decrypted_credentials.append((username, decrypted.strip()))
                    console.print(f"[green]✓ Added {username}[/green]")
                    break
                else:
                    console.print("[red]Please enter a password or 'skip'[/red]")
        
        return decrypted_credentials
    
    def save_credentials_file(self, credentials: List[Tuple[str, str]], 
                            output_file: str = "credentials.txt") -> bool:
        """Save decrypted credentials to a text file."""
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                for username, password in credentials:
                    f.write(f"{password} {username}\n")
                    
            console.print(f"[green]✓ Saved {len(credentials)} credentials to {output_file}[/green]")
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
                console.print(f"[yellow]Jenkins returned status {response.status_code}[/yellow]")
                return False
                
        except requests.exceptions.RequestException as e:
            console.print(f"[red]Cannot reach Jenkins server: {e}[/red]")
            return False
