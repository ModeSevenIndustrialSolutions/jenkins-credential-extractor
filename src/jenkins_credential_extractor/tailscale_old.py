# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

"""Tailscale integration for discovering Jenkins servers."""

import platform
import re
import requests
import subprocess
from typing import Dict, List, Optional, Set, Tuple

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
            [tailscale_cmd, "status"], capture_output=True, text=True, timeout=10
        )

        if result.returncode != 0:
            console.print(
                "[red]Error: Tailscale is not running or not logged in ❌[/red]"
            )
            return False

        # Check if we're actually logged in (not just running)
        if "Logged out" in result.stdout:
            console.print("[red]Error: Tailscale is running but not logged in ❌[/red]")
            return False

        console.print("[green]✓ Tailscale is running and logged in[/green]")
        return True

    except FileNotFoundError:
        console.print("[red]Error: Tailscale command not found ❌[/red]")
        return False
    except subprocess.TimeoutExpired:
        console.print("[red]Error: Tailscale command timed out ❌[/red]")
        return False
    except Exception as e:
        console.print(f"[red]Error checking Tailscale status: {e} ❌[/red]")
        return False


def get_jenkins_servers() -> List[Tuple[str, str]]:
    """Get list of Jenkins servers from Tailscale network."""
    try:
        tailscale_cmd = get_tailscale_command()
        result = subprocess.run(
            [tailscale_cmd, "status"], capture_output=True, text=True, timeout=10
        )

        if result.returncode != 0:
            raise TailscaleError(f"Failed to get Tailscale status: {result.stderr}")

        jenkins_servers: List[Tuple[str, str]] = []
        for line in result.stdout.split("\n"):
            if "jenkins" in line.lower():
                # Parse line format: IP    hostname tags...
                parts = line.split()
                if len(parts) >= 2:
                    ip = parts[0]
                    hostname = parts[1]
                    jenkins_servers.append((ip, hostname))

        return jenkins_servers

    except Exception as e:
        raise TailscaleError(f"Error getting Jenkins servers: {e}")


def get_all_jenkins_servers_with_status() -> List[Tuple[str, str, str]]:
    """Get list of all Jenkins servers from Tailscale network with status."""
    try:
        tailscale_cmd = get_tailscale_command()
        result = subprocess.run(
            [tailscale_cmd, "status"], capture_output=True, text=True, timeout=10
        )

        if result.returncode != 0:
            raise TailscaleError(f"Failed to get Tailscale status: {result.stderr}")

        jenkins_servers: List[Tuple[str, str, str]] = []
        for line in result.stdout.split("\n"):
            if "jenkins" in line.lower():
                # Parse line format: IP    hostname tags... status
                parts = line.split()
                if len(parts) >= 2:
                    ip = parts[0]
                    hostname = parts[1]
                    # Status is usually the last part, or "online" if not specified
                    status = (
                        parts[-1]
                        if len(parts) > 2 and parts[-1] in ["offline", "online", "-"]
                        else "online"
                    )
                    if status == "-":
                        status = "online"
                    jenkins_servers.append((ip, hostname, status))

        return jenkins_servers

    except Exception as e:
        raise TailscaleError(f"Error getting Jenkins servers: {e}")


def extract_project_from_hostname(hostname: str) -> Optional[str]:
    """Extract project identifier from Jenkins hostname."""
    hostname_lower = hostname.lower()

    # Map hostname patterns to project keys
    hostname_patterns = {
        "agl": ["agl"],
        "akraino": ["akraino"],
        "edgex": ["edgex"],
        "fdio": ["fd.io", "fdio"],
        "lf-broadband": ["cord", "opencord", "voltha"],
        "onap": ["onap", "ecomp"],
        "opendaylight": ["odl", "opendaylight"],
        "o-ran-sc": ["oran", "o-ran"],
        "lfit": ["lfit"],  # Linux Foundation IT
    }

    for project_key, patterns in hostname_patterns.items():
        for pattern in patterns:
            if pattern in hostname_lower:
                return project_key

    return None


def get_enhanced_jenkins_server_for_project(
    project_key: str,
) -> Optional[Tuple[str, str]]:
    """Get the Jenkins server for a project with enhanced matching."""
    jenkins_servers = get_jenkins_servers()

    # First try exact project match in hostname
    for ip, hostname in jenkins_servers:
        extracted_project = extract_project_from_hostname(hostname)
        if extracted_project == project_key:
            # Prefer production servers
            if "prod" in hostname.lower():
                return (ip, hostname)

    # If no prod server found, try any server for the project
    for ip, hostname in jenkins_servers:
        extracted_project = extract_project_from_hostname(hostname)
        if extracted_project == project_key:
            return (ip, hostname)

    # Fallback to old logic
    for ip, hostname in jenkins_servers:
        if project_key.lower() in hostname.lower():
            return (ip, hostname)

    return None


def parse_lf_inventory() -> Dict[str, Set[str]]:
    """Parse Linux Foundation infrastructure inventory for Jenkins servers."""
    inventory_url = (
        "https://docs.releng.linuxfoundation.org/en/latest/infra/inventory.html"
    )

    try:
        response = requests.get(inventory_url, timeout=30)
        if response.status_code == 200:
            # Extract Jenkins server information from the HTML
            content = response.text
            jenkins_pattern = r"(\w+)-jenkins(?:-\w+)?(?:-\d+)?"

            # Find all Jenkins server references
            jenkins_matches = re.findall(jenkins_pattern, content, re.IGNORECASE)

            # Group by project
            project_servers: Dict[str, Set[str]] = {}
            for match in jenkins_matches:
                project = match.lower()
                if project not in project_servers:
                    project_servers[project] = set()
                project_servers[project].add(match)

            return project_servers

    except Exception as e:
        console.print(f"[yellow]Warning: Could not parse LF inventory: {e}[/yellow]")

    return {}


def display_jenkins_servers() -> None:
    """Display available Jenkins servers in a nice format."""
    try:
        servers = get_jenkins_servers()
        if not servers:
            console.print(
                "[yellow]No Jenkins servers found in Tailscale network[/yellow]"
            )
            return

        console.print("\n[bold]Available Jenkins servers:[/bold]")
        for ip, hostname in servers:
            console.print(f"  [cyan]{ip}[/cyan] → [green]{hostname}[/green]")

    except TailscaleError as e:
        console.print(f"[red]Error: {e}[/red]")


def display_enhanced_jenkins_servers() -> None:
    """Display all Jenkins servers with enhanced information."""
    try:
        servers = get_all_jenkins_servers_with_status()
        if not servers:
            console.print(
                "[yellow]No Jenkins servers found in Tailscale network[/yellow]"
            )
            return

        console.print("\n[bold]Available Jenkins servers:[/bold]")

        # Group by project
        project_servers: Dict[str, List[Tuple[str, str, str]]] = {}
        unknown_servers: List[Tuple[str, str, str]] = []

        for ip, hostname, status in servers:
            project = extract_project_from_hostname(hostname)
            if project:
                if project not in project_servers:
                    project_servers[project] = []
                project_servers[project].append((ip, hostname, status))
            else:
                unknown_servers.append((ip, hostname, status))

        # Display grouped servers
        for project, server_list in sorted(project_servers.items()):
            console.print(f"\n[bold cyan]{project.upper()}:[/bold cyan]")
            for ip, hostname, status in server_list:
                status_color = "green" if status == "online" else "red"
                console.print(
                    f"  [cyan]{ip}[/cyan] → [white]{hostname}[/white] [{status_color}]{status}[/{status_color}]"
                )

        if unknown_servers:
            console.print("\n[bold yellow]Other Jenkins servers:[/bold yellow]")
            for ip, hostname, status in unknown_servers:
                status_color = "green" if status == "online" else "red"
                console.print(
                    f"  [cyan]{ip}[/cyan] → [white]{hostname}[/white] [{status_color}]{status}[/{status_color}]"
                )

    except TailscaleError as e:
        console.print(f"[red]Error: {e} ❌[/red]")
