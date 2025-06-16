# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

"""Tailscale integration for discovering Jenkins servers."""

import platform
import subprocess
from typing import List, Optional, Tuple

from rich.console import Console

console = Console()


class TailscaleError(Exception):
    """Custom exception for Tailscale-related errors."""
    pass


def get_tailscale_command() -> str:
    """Get the appropriate Tailscale command for the current platform."""
    system = platform.system().lower()
    
    if system == "darwin":  # macOS
        return "/Applications/Tailscale.app/Contents/MacOS/Tailscale"
    elif system == "linux":
        return "tailscale"
    else:
        raise TailscaleError(f"Unsupported platform: {system}")


def check_tailscale_status() -> bool:
    """Check if Tailscale is running and logged in."""
    try:
        tailscale_cmd = get_tailscale_command()
        result = subprocess.run(
            [tailscale_cmd, "status"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            console.print("[red]Tailscale is not running or not logged in[/red]")
            console.print(f"[yellow]Error: {result.stderr.strip()}[/yellow]")
            return False
            
        # Check if we're actually logged in (not just running)
        if "Logged out" in result.stdout:
            console.print("[red]Tailscale is running but not logged in[/red]")
            return False
            
        console.print("[green]✓ Tailscale is running and logged in[/green]")
        return True
        
    except FileNotFoundError:
        console.print("[red]Tailscale command not found[/red]")
        console.print("[yellow]Please ensure Tailscale is installed and accessible[/yellow]")
        return False
    except subprocess.TimeoutExpired:
        console.print("[red]Tailscale command timed out[/red]")
        return False
    except Exception as e:
        console.print(f"[red]Error checking Tailscale status: {e}[/red]")
        return False


def get_jenkins_servers() -> List[Tuple[str, str]]:
    """Get list of Jenkins servers from Tailscale network."""
    try:
        tailscale_cmd = get_tailscale_command()
        result = subprocess.run(
            [tailscale_cmd, "status"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0:
            raise TailscaleError(f"Failed to get Tailscale status: {result.stderr}")
            
        jenkins_servers: List[Tuple[str, str]] = []
        for line in result.stdout.split('\n'):
            if 'jenkins' in line.lower() and 'prod' in line.lower():
                # Parse line format: IP    hostname tags...
                parts = line.split()
                if len(parts) >= 2:
                    ip = parts[0]
                    hostname = parts[1]
                    jenkins_servers.append((ip, hostname))
                    
        return jenkins_servers
        
    except Exception as e:
        raise TailscaleError(f"Error getting Jenkins servers: {e}")


def get_jenkins_server_for_project(project_key: str) -> Optional[Tuple[str, str]]:
    """Get the Jenkins server IP and hostname for a specific project."""
    jenkins_servers = get_jenkins_servers()
    
    # Look for server matching the project
    for ip, hostname in jenkins_servers:
        if project_key.lower() in hostname.lower() and 'prod' in hostname.lower():
            return (ip, hostname)
    
    return None


def display_jenkins_servers() -> None:
    """Display available Jenkins servers in a nice format."""
    try:
        servers = get_jenkins_servers()
        if not servers:
            console.print("[yellow]No Jenkins servers found in Tailscale network[/yellow]")
            return
            
        console.print("\n[bold]Available Jenkins servers:[/bold]")
        for ip, hostname in servers:
            console.print(f"  [cyan]{ip}[/cyan] → [green]{hostname}[/green]")
            
    except TailscaleError as e:
        console.print(f"[red]Error: {e}[/red]")
