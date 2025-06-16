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


def _filter_to_production_servers(
    servers: List[Tuple[str, str]],
) -> List[Tuple[str, str]]:
    """Filter to production servers, preferring lowest numbered servers."""
    # Group servers by project
    project_servers: Dict[str, List[Tuple[str, str]]] = {}

    for ip, hostname in servers:
        project = extract_project_from_hostname(hostname)
        if project:
            if project not in project_servers:
                project_servers[project] = []
            project_servers[project].append((ip, hostname))

    # Select best server for each project
    filtered_servers: List[Tuple[str, str]] = []

    for project, server_list in project_servers.items():
        # First try to find explicit production servers
        prod_servers = [
            (ip, hostname) for ip, hostname in server_list if "prod" in hostname.lower()
        ]

        if prod_servers:
            # Use production servers, prefer lowest numbered
            best_server = _get_lowest_numbered_server(prod_servers)
            filtered_servers.append(best_server)
        else:
            # No explicit prod servers, use lowest numbered available
            best_server = _get_lowest_numbered_server(server_list)
            filtered_servers.append(best_server)

    return filtered_servers


def _get_lowest_numbered_server(servers: List[Tuple[str, str]]) -> Tuple[str, str]:
    """Get the lowest numbered server from a list."""
    import re

    def extract_number(hostname: str) -> int:
        """Extract server number from hostname, return 999 if no number found."""
        match = re.search(r"-(\d+)(?:\s|$)", hostname)
        return int(match.group(1)) if match else 999

    # Sort by number and return the first (lowest numbered)
    sorted_servers = sorted(servers, key=lambda x: extract_number(x[1]))
    return sorted_servers[0]


def get_jenkins_servers() -> List[Tuple[str, str]]:
    """Get list of Jenkins servers from Tailscale network, filtering out sandbox servers."""
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

                    # Skip sandbox servers
                    if "sandbox" not in hostname.lower():
                        jenkins_servers.append((ip, hostname))

        # Filter to prefer lowest numbered servers for each project
        return _filter_to_production_servers(jenkins_servers)

    except Exception as e:
        raise TailscaleError(f"Error getting Jenkins servers: {e}")


def _filter_to_production_servers_with_status(
    servers: List[Tuple[str, str, str]],
) -> List[Tuple[str, str, str]]:
    """Filter to production servers with status, preferring lowest numbered servers."""
    # Group servers by project
    project_servers: Dict[str, List[Tuple[str, str, str]]] = {}

    for ip, hostname, status in servers:
        project = extract_project_from_hostname(hostname)
        if project:
            if project not in project_servers:
                project_servers[project] = []
            project_servers[project].append((ip, hostname, status))

    # Select best server for each project
    filtered_servers: List[Tuple[str, str, str]] = []

    for project, server_list in project_servers.items():
        # First try to find explicit production servers
        prod_servers = [
            (ip, hostname, status)
            for ip, hostname, status in server_list
            if "prod" in hostname.lower()
        ]

        if prod_servers:
            # Use production servers, prefer lowest numbered
            best_server = _get_lowest_numbered_server_with_status(prod_servers)
            filtered_servers.append(best_server)
        else:
            # No explicit prod servers, use lowest numbered available
            best_server = _get_lowest_numbered_server_with_status(server_list)
            filtered_servers.append(best_server)

    return filtered_servers


def _get_lowest_numbered_server_with_status(
    servers: List[Tuple[str, str, str]],
) -> Tuple[str, str, str]:
    """Get the lowest numbered server with status from a list."""
    import re

    def extract_number(hostname: str) -> int:
        """Extract server number from hostname, return 999 if no number found."""
        match = re.search(r"-(\d+)(?:\s|$)", hostname)
        return int(match.group(1)) if match else 999

    # Sort by number and return the first (lowest numbered)
    sorted_servers = sorted(servers, key=lambda x: extract_number(x[1]))
    return sorted_servers[0]


def get_all_jenkins_servers_with_status() -> List[Tuple[str, str, str]]:
    """Get list of all Jenkins servers from Tailscale network with status, filtering sandbox servers."""
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
                parts = line.split()
                if len(parts) >= 2:
                    ip = parts[0]
                    hostname = parts[1]
                    status = _extract_status_from_line(parts)

                    # Skip sandbox servers
                    if "sandbox" not in hostname.lower():
                        jenkins_servers.append((ip, hostname, status))

        # Filter to prefer lowest numbered servers for each project
        return _filter_to_production_servers_with_status(jenkins_servers)

    except Exception as e:
        raise TailscaleError(f"Error getting Jenkins servers: {e}")


def _extract_status_from_line(parts: List[str]) -> str:
    """Extract status from tailscale status line parts."""
    if len(parts) > 2 and parts[-1] in ["offline", "online", "-"]:
        return "online" if parts[-1] == "-" else parts[-1]
    return "online"


def extract_project_from_hostname(hostname: str) -> Optional[str]:
    """Extract project identifier from Jenkins hostname."""
    hostname_lower = hostname.lower()

    # Map hostname patterns to project keys (only for actual projects, not infrastructure)
    hostname_patterns = {
        "agl": ["agl"],
        "akraino": ["akraino"],
        "edgex": ["edgex"],
        "fdio": ["fd.io", "fdio"],
        "lf-broadband": ["cord", "opencord", "voltha"],
        "onap": ["onap", "ecomp"],
        "opendaylight": ["odl", "opendaylight"],
        "o-ran-sc": ["oran", "o-ran"],
        # Note: "lfit" is infrastructure, not a user project
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

    # First try exact project match in hostname with preference for prod
    prod_match = _find_production_server(jenkins_servers, project_key)
    if prod_match:
        return prod_match

    # Try any server for the project
    any_match = _find_any_project_server(jenkins_servers, project_key)
    if any_match:
        return any_match

    # Fallback to old logic
    return _find_fallback_server(jenkins_servers, project_key)


def _find_production_server(
    servers: List[Tuple[str, str]], project_key: str
) -> Optional[Tuple[str, str]]:
    """Find production server for project."""
    for ip, hostname in servers:
        extracted_project = extract_project_from_hostname(hostname)
        if extracted_project == project_key and "prod" in hostname.lower():
            return (ip, hostname)
    return None


def _find_any_project_server(
    servers: List[Tuple[str, str]], project_key: str
) -> Optional[Tuple[str, str]]:
    """Find any server for project."""
    for ip, hostname in servers:
        extracted_project = extract_project_from_hostname(hostname)
        if extracted_project == project_key:
            return (ip, hostname)
    return None


def _find_fallback_server(
    servers: List[Tuple[str, str]], project_key: str
) -> Optional[Tuple[str, str]]:
    """Fallback server matching."""
    for ip, hostname in servers:
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
            content = response.text
            jenkins_pattern = r"(\w+)-jenkins(?:-\w+)?(?:-\d+)?"
            jenkins_matches = re.findall(jenkins_pattern, content, re.IGNORECASE)

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


def get_jenkins_server_for_project(project_key: str) -> Optional[Tuple[str, str]]:
    """Get the Jenkins server IP and hostname for a specific project."""
    return get_enhanced_jenkins_server_for_project(project_key)


def rebuild_server_list() -> Dict[str, List[str]]:
    """Rebuild the comprehensive server list from all sources."""
    console.print("[blue]Rebuilding server list from all sources...[/blue]")

    # Get servers from Tailscale
    tailscale_servers: Dict[str, List[str]] = {}
    try:
        servers = get_all_jenkins_servers_with_status()
        for ip, hostname, status in servers:
            project = extract_project_from_hostname(hostname)
            if project:
                if project not in tailscale_servers:
                    tailscale_servers[project] = []
                tailscale_servers[project].append(f"{hostname} ({ip}) [{status}]")

        console.print(
            f"[green]✓ Found {len(servers)} Jenkins servers in Tailscale[/green]"
        )

    except Exception as e:
        console.print(f"[yellow]Warning: Could not get Tailscale servers: {e}[/yellow]")

    # Get servers from LF inventory
    lf_servers = parse_lf_inventory()
    if lf_servers:
        console.print(
            f"[green]✓ Found {len(lf_servers)} project groups in LF inventory[/green]"
        )

    # Combine results
    all_servers: Dict[str, List[str]] = {}

    # Add Tailscale servers
    for project, server_list in tailscale_servers.items():
        if project not in all_servers:
            all_servers[project] = []
        all_servers[project].extend(server_list)

    # Add LF inventory servers
    for project, server_set in lf_servers.items():
        if project not in all_servers:
            all_servers[project] = []
        for server in server_set:
            if server not in [s.split()[0] for s in all_servers[project]]:
                all_servers[project].append(f"{server} (from inventory)")

    console.print(
        f"[bold green]✓ Rebuilt server list with {len(all_servers)} projects[/bold green]"
    )
    return all_servers


def display_compact_jenkins_servers() -> None:
    """Display all Jenkins servers in a compact column-aligned format."""
    try:
        servers = get_all_jenkins_servers_with_status()
        if not servers:
            console.print(
                "[yellow]No Jenkins servers found in Tailscale network[/yellow]"
            )
            return

        console.print("\n[bold]Available Jenkins servers:[/bold]")

        # Calculate column widths for alignment
        max_ip_width = max(len(ip) for ip, _, _ in servers) if servers else 15
        max_status_width = (
            max(len(status) for _, _, status in servers) if servers else 7
        )

        # Sort servers by project name for better organization
        all_server_data: List[Tuple[str, str, str, str]] = []
        for ip, hostname, status in servers:
            project = extract_project_from_hostname(hostname)
            project_display = project.upper() if project else "OTHER"
            all_server_data.append((ip, status, hostname, project_display))

        # Sort by project, then by hostname
        all_server_data.sort(key=lambda x: (x[3], x[2]))

        # Display each server in column-aligned format
        for ip, status, hostname, project_display in all_server_data:
            status_color = "green" if status == "online" else "red"
            console.print(
                f"[cyan]{ip:<{max_ip_width}}[/cyan]  "
                f"[{status_color}]{status:<{max_status_width}}[/{status_color}]  "
                f"[white]{hostname}[/white] → [bold cyan]{project_display}[/bold cyan]"
            )

    except TailscaleError as e:
        console.print(f"[red]Error: {e} ❌[/red]")
