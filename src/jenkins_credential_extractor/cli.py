# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

"""Main CLI application for Jenkins Credential Extractor."""

from pathlib import Path
from typing import Any, List, Optional, Tuple

import typer
try:
    from fuzzywuzzy import fuzz
except ImportError:
    fuzz = None
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from jenkins_credential_extractor.credentials import CredentialsParser
from jenkins_credential_extractor.jenkins import JenkinsAutomation
from jenkins_credential_extractor.projects import (
    PROJECT_MAPPINGS,
    ProjectInfo,
    find_project_by_alias,
    get_projects_with_jenkins,
)
from jenkins_credential_extractor.tailscale import (
    check_tailscale_status,
    display_jenkins_servers,
    get_jenkins_server_for_project,
)

app = typer.Typer(
    name="jenkins-credential-extractor",
    help="Extract credentials from Jenkins servers in Linux Foundation projects",
    rich_markup_mode="rich",
)
console = Console()


@app.command()
def extract(
    project: Optional[str] = typer.Argument(None, help="Project name (optional)"),
    output: str = typer.Option("credentials.txt", help="Output file for credentials"),
    credentials_file: str = typer.Option("credentials.xml", help="Local credentials file path"),
    description_pattern: Optional[str] = typer.Option(None, "--pattern", help="Description pattern to filter credentials"),
) -> None:
    """Extract credentials from a Jenkins server."""
    console.print("[bold blue]Jenkins Credential Extractor[/bold blue]\n")

    # Check Tailscale status
    if not check_tailscale_status():
        console.print("[red]❌ Tailscale check failed. Please ensure Tailscale is running and logged in.[/red]")
        raise typer.Exit(1)

    # Get project selection
    selected_project = project or select_project()
    if not selected_project:
        console.print("[red]❌ No project selected.[/red]")
        raise typer.Exit(1)

    console.print(f"[green]Selected project: {selected_project}[/green]")

    # Get Jenkins server for project
    jenkins_info = get_jenkins_server_for_project(selected_project)
    if not jenkins_info:
        console.print(f"[red]❌ No Jenkins server found for project '{selected_project}'[/red]")
        raise typer.Exit(1)

    jenkins_ip, jenkins_hostname = jenkins_info
    project_info = PROJECT_MAPPINGS[selected_project]
    jenkins_url = project_info["jenkins_url"]

    if not jenkins_url:
        console.print(f"[red]❌ No Jenkins URL configured for project '{selected_project}'[/red]")
        raise typer.Exit(1)

    console.print(f"[cyan]Jenkins server: {jenkins_hostname} ({jenkins_ip})[/cyan]")
    console.print(f"[cyan]Jenkins URL: {jenkins_url}[/cyan]")

    # Initialize Jenkins automation
    jenkins = JenkinsAutomation(jenkins_url, jenkins_ip)

    # Test connectivity
    if not jenkins.test_jenkins_connectivity():
        console.print("[yellow]⚠️  Jenkins server may not be accessible via HTTP[/yellow]")
        if not Confirm.ask("Continue anyway?"):
            raise typer.Exit(1)

    # Download credentials file
    if not jenkins.download_credentials_file(credentials_file):
        console.print("[red]❌ Failed to download credentials file[/red]")
        raise typer.Exit(1)

    # Parse credentials
    parser = CredentialsParser(credentials_file)
    if not parser.parse():
        console.print("[red]❌ Failed to parse credentials file[/red]")
        raise typer.Exit(1)

    # Extract repository credentials with user choice or specified pattern
    if description_pattern:
        console.print(f"[cyan]Using description pattern: '{description_pattern}'[/cyan]")
        repo_credentials = parser.extract_credentials_by_description(description_pattern)
    else:
        repo_credentials = parser.extract_credentials_by_pattern_choice()
    
    if not repo_credentials:
        console.print("[yellow]⚠️  No repository credentials found[/yellow]")
        raise typer.Exit(1)

    # Decrypt passwords
    decrypted_credentials = jenkins.batch_decrypt_passwords(repo_credentials)

    if not decrypted_credentials:
        console.print("[yellow]⚠️  No credentials were decrypted[/yellow]")
        raise typer.Exit(1)

    # Save results
    if jenkins.save_credentials_file(decrypted_credentials, output):
        console.print(f"\n[bold green]✅ Successfully extracted {len(decrypted_credentials)} credentials to {output}[/bold green]")
    else:
        console.print("[red]❌ Failed to save credentials file[/red]")
        raise typer.Exit(1)


@app.command()
def list_projects() -> None:
    """List all available projects with Jenkins servers."""
    console.print("[bold blue]Projects with Jenkins servers:[/bold blue]\n")

    projects = get_projects_with_jenkins()

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Key", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Full Name", style="white")
    table.add_column("Jenkins URL", style="blue")
    table.add_column("Aliases", style="yellow")

    for key, project in projects:
        aliases = ", ".join(project["aliases"])
        table.add_row(
            key,
            project["name"],
            project["full_name"],
            project["jenkins_url"] or "N/A",
            aliases
        )

    console.print(table)


@app.command()
def list_servers() -> None:
    """List Jenkins servers available in Tailscale network."""
    console.print("[bold blue]Checking Tailscale network for Jenkins servers...[/bold blue]\n")

    if not check_tailscale_status():
        console.print("[red]❌ Tailscale check failed[/red]")
        raise typer.Exit(1)

    display_jenkins_servers()


@app.command()
def parse_local(
    credentials_file: str = typer.Argument(..., help="Path to local credentials.xml file"),
    output: str = typer.Option("credentials.txt", help="Output file for credentials"),
    description_pattern: Optional[str] = typer.Option(None, "--pattern", help="Description pattern to filter credentials"),
) -> None:
    """Parse a local credentials.xml file without downloading from Jenkins."""
    console.print(f"[bold blue]Parsing local credentials file: {credentials_file}[/bold blue]\n")

    if not Path(credentials_file).exists():
        console.print(f"[red]❌ File not found: {credentials_file}[/red]")
        raise typer.Exit(1)

    # Parse credentials
    parser = CredentialsParser(credentials_file)
    if not parser.parse():
        console.print("[red]❌ Failed to parse credentials file[/red]")
        raise typer.Exit(1)

    # Extract and display repository credentials
    if description_pattern:
        console.print(f"[cyan]Using description pattern: '{description_pattern}'[/cyan]")
        repo_credentials = parser.extract_credentials_by_description(description_pattern)
    else:
        repo_credentials = parser.extract_credentials_by_pattern_choice()
    
    if not repo_credentials:
        console.print("[yellow]⚠️  No repository credentials found[/yellow]")
        return

    console.print(f"\n[bold]Found {len(repo_credentials)} repository credentials:[/bold]")
    for username, encrypted_password in repo_credentials:
        console.print(f"  [cyan]{username}[/cyan]: [dim]{encrypted_password[:20]}...[/dim]")

    console.print("\n[yellow]To decrypt these passwords, you'll need to use the Jenkins script console.[/yellow]")
    console.print("[dim]Use the 'extract' command for full automation.[/dim]")


def select_project() -> Optional[str]:
    """Interactive project selection with fuzzy matching."""
    projects = get_projects_with_jenkins()

    if not projects:
        console.print("[red]No projects with Jenkins servers found[/red]")
        return None

    console.print("[bold]Available projects:[/bold]")
    for i, (key, project) in enumerate(projects, 1):
        console.print(f"  {i}. [cyan]{project['name']}[/cyan] ({key}) - {project['full_name']}")

    while True:
        choice = Prompt.ask("\nEnter project number, name, or alias")

        # Try numeric selection
        result = _try_numeric_selection(choice, projects)
        if result:
            return result

        # Try exact match
        project_key = find_project_by_alias(choice)
        if project_key:
            return project_key

        # Try fuzzy matching if available
        if fuzz:
            result = _try_fuzzy_matching(choice, projects)
            if result:
                return result

        console.print("[red]Invalid selection. Please try again.[/red]")


def _try_numeric_selection(choice: str, projects: List[Tuple[str, Any]]) -> Optional[str]:
    """Try to parse choice as a number and return corresponding project."""
    try:
        index = int(choice) - 1
        if 0 <= index < len(projects):
            return projects[index][0]
    except ValueError:
        pass
    return None


def _try_fuzzy_matching(choice: str, projects: List[Tuple[str, Any]]) -> Optional[str]:
    """Try fuzzy matching against project names and aliases."""
    if not fuzz:
        return None

    best_match = None
    best_score = 0

    for key, project in projects:
        candidates = [key, project["name"]] + project["aliases"]
        for candidate in candidates:
            score = fuzz.ratio(choice.lower(), candidate.lower())
            if score and score > best_score:
                best_score = score
                best_match = key

    if best_match and best_score > 70:
        project_info = PROJECT_MAPPINGS[best_match]
        if Confirm.ask(f"Did you mean '[cyan]{project_info['name']}[/cyan]' ({best_match})?"):
            return best_match

    return None


if __name__ == "__main__":
    app()
