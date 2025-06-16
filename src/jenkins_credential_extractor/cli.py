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

# Enhanced automation imports
from jenkins_credential_extractor.enhanced_jenkins import EnhancedJenkinsAutomation
from jenkins_credential_extractor.projects import (
    PROJECT_MAPPINGS,
    find_project_by_alias,
    get_projects_with_jenkins,
)
from jenkins_credential_extractor.tailscale import (
    check_tailscale_status,
    display_compact_jenkins_servers,
    get_jenkins_server_for_project,
    parse_lf_inventory,
    rebuild_server_list,
)

app = typer.Typer(
    name="jenkins-credential-extractor",
    help="Extract credentials from Jenkins servers in Linux Foundation projects",
    rich_markup_mode="rich",
)
console = Console()


# Constants for error messages
ERROR_DOWNLOAD_FAILED = "[red]❌ Failed to download credentials file[/red]"
ERROR_PARSE_FAILED = "[red]❌ Failed to parse credentials file[/red]"
WARNING_NO_CREDENTIALS = "[yellow]⚠️  No credentials were decrypted[/yellow]"


def _extract_with_enhanced_automation(
    jenkins_url: str,
    jenkins_ip: str,
    credentials_file: str,
    description_pattern: Optional[str],
    use_batch_optimization: bool,
    output: str,
) -> bool:
    """Extract credentials using enhanced automation. Returns True if successful."""
    try:
        # Initialize enhanced Jenkins automation
        jenkins = EnhancedJenkinsAutomation(jenkins_url, jenkins_ip)

        # Validate Jenkins access and permissions
        if not jenkins.validate_jenkins_access():
            console.print("[yellow]⚠️  Enhanced automation validation failed[/yellow]")
            return False

        # Download credentials file if needed
        if not Path(credentials_file).exists():
            console.print(f"[blue]Downloading credentials file to {credentials_file}...[/blue]")
            # Use traditional method for file download
            traditional_jenkins = JenkinsAutomation(jenkins_url, jenkins_ip)
            if not traditional_jenkins.download_credentials_file(credentials_file):
                console.print(ERROR_DOWNLOAD_FAILED)
                raise typer.Exit(1)

        # Parse credentials
        parser = CredentialsParser(credentials_file)
        if not parser.parse():
            console.print(ERROR_PARSE_FAILED)
            raise typer.Exit(1)

        # Extract and decrypt credentials automatically
        if description_pattern:
            console.print(f"[cyan]Using description pattern: '{description_pattern}'[/cyan]")
            decrypted_credentials = parser.extract_and_decrypt_credentials_automated(
                jenkins, description_pattern, use_batch_optimization
            )
        else:
            decrypted_credentials = parser.interactive_automated_extraction(jenkins)

        if not decrypted_credentials:
            console.print(WARNING_NO_CREDENTIALS)
            raise typer.Exit(1)

        # Save decrypted credentials
        _save_credentials(decrypted_credentials, output, "Enhanced automation", use_batch_optimization)
        return True

    except ImportError:
        console.print("[yellow]⚠️  Enhanced automation dependencies missing[/yellow]")
        return False
    except Exception as e:
        console.print(f"[red]❌ Enhanced automation failed: {e}[/red]")
        return False


def _extract_with_legacy_automation(
    jenkins_url: str,
    jenkins_ip: str,
    credentials_file: str,
    description_pattern: Optional[str],
    output: str,
) -> None:
    """Extract credentials using legacy automation."""
    console.print("[yellow]Using legacy automation mode...[/yellow]")

    # Initialize legacy Jenkins automation
    jenkins = JenkinsAutomation(jenkins_url, jenkins_ip)

    # Test connectivity
    if not jenkins.test_jenkins_connectivity():
        console.print("[yellow]⚠️  Jenkins server may not be accessible via HTTP[/yellow]")
        if not Confirm.ask("Continue anyway?"):
            raise typer.Exit(1)

    # Download credentials file
    if not jenkins.download_credentials_file(credentials_file):
        console.print(ERROR_DOWNLOAD_FAILED)
        raise typer.Exit(1)

    # Parse credentials
    parser = CredentialsParser(credentials_file)
    if not parser.parse():
        console.print(ERROR_PARSE_FAILED)
        raise typer.Exit(1)

    # Extract repository credentials
    if description_pattern:
        console.print(f"[cyan]Using description pattern: '{description_pattern}'[/cyan]")
        repo_credentials = parser.extract_credentials_by_description(description_pattern)
    else:
        repo_credentials = parser.extract_credentials_by_pattern_choice()

    if not repo_credentials:
        console.print("[yellow]⚠️  No repository credentials found[/yellow]")
        raise typer.Exit(1)

    # Decrypt passwords using legacy method
    decrypted_credentials = jenkins.batch_decrypt_passwords(repo_credentials)

    if not decrypted_credentials:
        console.print(WARNING_NO_CREDENTIALS)
        raise typer.Exit(1)

    # Save results
    if jenkins.save_credentials_file(decrypted_credentials, output):
        console.print(
            f"\n[bold green]✅ Successfully extracted {len(decrypted_credentials)} credentials to {output}[/bold green]"
        )
        console.print("• Mode: Legacy automation")
    else:
        console.print("[red]❌ Failed to save credentials file[/red]")
        raise typer.Exit(1)


def _save_credentials(
    credentials: List[Tuple[str, str]],
    output: str,
    mode: str,
    batch_optimization: bool = False
) -> None:
    """Save decrypted credentials to file and display summary."""
    try:
        with open(output, "w", encoding="utf-8") as f:
            for username, password in credentials:
                f.write(f"{password} {username}\n")

        console.print(
            f"[green]✅ Saved {len(credentials)} decrypted credentials to {output}[/green]"
        )

        # Display summary
        console.print("\n[bold]Summary:[/bold]")
        console.print(f"• Processed credentials: {len(credentials)}")
        console.print(f"• Output file: {output}")
        console.print(f"• Mode: {mode}")
        if batch_optimization is not None:
            console.print(f"• Batch optimization: {'Enabled' if batch_optimization else 'Disabled'}")

    except Exception as e:
        console.print(f"[red]❌ Error saving credentials: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def extract(
    project: Optional[str] = typer.Argument(None, help="Project name (optional)"),
    output: str = typer.Option("credentials.txt", help="Output file for credentials"),
    credentials_file: str = typer.Option(
        "credentials.xml", help="Local credentials file path"
    ),
    description_pattern: Optional[str] = typer.Option(
        None, "--pattern", help="Description pattern to filter credentials"
    ),
    use_batch_optimization: bool = typer.Option(
        True, "--batch/--no-batch", help="Use batch optimization for large datasets"
    ),
    max_workers: int = typer.Option(
        5, "--workers", help="Maximum concurrent workers for parallel processing"
    ),
    legacy_mode: bool = typer.Option(
        False, "--legacy", help="Use legacy automation (for debugging/fallback)"
    ),
) -> None:
    """Extract credentials from a Jenkins server."""
    console.print("[bold blue]🚀 Jenkins Credential Extractor[/bold blue]\n")

    # Check Tailscale status
    if not check_tailscale_status():
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
        console.print(
            f"[red]❌ No Jenkins server found for project '{selected_project}'[/red]"
        )
        raise typer.Exit(1)

    jenkins_ip, jenkins_hostname = jenkins_info
    project_info = PROJECT_MAPPINGS[selected_project]
    jenkins_url = project_info["jenkins_url"]

    if not jenkins_url:
        console.print(
            f"[red]❌ No Jenkins URL configured for project '{selected_project}'[/red]"
        )
        raise typer.Exit(1)

    console.print(f"[cyan]Jenkins server: {jenkins_hostname} ({jenkins_ip})[/cyan]")
    console.print(f"[cyan]Jenkins URL: {jenkins_url}[/cyan]")

    # Try enhanced automation first, fall back to legacy if needed
    if not legacy_mode:
        console.print("[blue]Using enhanced automation...[/blue]")
        success = _extract_with_enhanced_automation(
            jenkins_url, jenkins_ip, credentials_file, description_pattern,
            use_batch_optimization, output
        )
        if success:
            return

    # Use legacy automation
    _extract_with_legacy_automation(
        jenkins_url, jenkins_ip, credentials_file, description_pattern, output
    )


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
            aliases,
        )

    console.print(table)


@app.command()
def list_servers() -> None:
    """List Jenkins servers available in Tailscale network."""
    console.print(
        "[bold blue]Checking Tailscale network for Jenkins servers...[/bold blue]\n"
    )

    if not check_tailscale_status():
        raise typer.Exit(1)

    display_compact_jenkins_servers()


@app.command()
def parse_local(
    credentials_file: str = typer.Argument(
        ..., help="Path to local credentials.xml file"
    ),
    output: str = typer.Option("credentials.txt", help="Output file for credentials"),
    description_pattern: Optional[str] = typer.Option(
        None, "--pattern", help="Description pattern to filter credentials"
    ),
) -> None:
    """Parse a local credentials.xml file without downloading from Jenkins."""
    console.print(
        f"[bold blue]Parsing local credentials file: {credentials_file}[/bold blue]\n"
    )

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
        console.print(
            f"[cyan]Using description pattern: '{description_pattern}'[/cyan]"
        )
        repo_credentials = parser.extract_credentials_by_description(
            description_pattern
        )
    else:
        repo_credentials = parser.extract_credentials_by_pattern_choice()

    if not repo_credentials:
        console.print("[yellow]⚠️  No repository credentials found[/yellow]")
        return

    console.print(
        f"\n[bold]Found {len(repo_credentials)} repository credentials:[/bold]"
    )
    for username, encrypted_password in repo_credentials:
        console.print(
            f"  [cyan]{username}[/cyan]: [dim]{encrypted_password[:20]}...[/dim]"
        )

    console.print(
        "\n[yellow]To decrypt these passwords, you'll need to use the Jenkins script console.[/yellow]"
    )
    console.print("[dim]Use the 'extract' command for full automation.[/dim]")


@app.command("rebuild-projects")
def rebuild_projects() -> None:
    """Rebuild and refresh the project list from all sources."""
    console.print("[bold blue]Rebuilding project list...[/bold blue]\n")

    # Get projects with Jenkins from our mappings
    projects = get_projects_with_jenkins()
    console.print(
        f"[green]✓ Found {len(projects)} projects with Jenkins servers in mappings[/green]"
    )

    # Parse LF inventory for additional projects
    try:
        lf_projects = parse_lf_inventory()
        console.print(
            f"[green]✓ Found {len(lf_projects)} project groups in LF inventory[/green]"
        )

        # Show comparison
        mapped_keys = {key for key, _ in projects}
        inventory_keys = set(lf_projects.keys())

        missing_from_mapping = inventory_keys - mapped_keys
        missing_from_inventory = mapped_keys - inventory_keys

        if missing_from_mapping:
            console.print(
                "\n[yellow]Projects in inventory but not in mappings:[/yellow]"
            )
            for project in sorted(missing_from_mapping):
                console.print(f"  - {project}")

        if missing_from_inventory:
            console.print(
                "\n[yellow]Projects in mappings but not in inventory:[/yellow]"
            )
            for project in sorted(missing_from_inventory):
                console.print(f"  - {project}")

        console.print("\n[bold green]✓ Project list analysis complete[/bold green]")

    except Exception as e:
        console.print(f"[yellow]Warning: Could not parse LF inventory: {e}[/yellow]")


@app.command("rebuild-servers")
def rebuild_servers() -> None:
    """Rebuild and refresh the Jenkins server list from all sources."""
    console.print("[bold blue]Rebuilding Jenkins server list...[/bold blue]\n")

    if not check_tailscale_status():
        raise typer.Exit(1)

    # Rebuild comprehensive server list
    all_servers = rebuild_server_list()

    # Display results
    console.print("\n[bold]Comprehensive Jenkins server list:[/bold]")

    if not all_servers:
        console.print("[yellow]No Jenkins servers found[/yellow]")
        return

    for project, servers in sorted(all_servers.items()):
        console.print(f"\n[bold cyan]{project.upper()}:[/bold cyan]")
        for server in servers:
            console.print(f"  {server}")

    console.print(
        f"\n[bold green]✓ Found servers for {len(all_servers)} projects[/bold green]"
    )



@app.command()
def setup_auth(
    jenkins_url: Optional[str] = typer.Option(None, help="Jenkins URL"),
    auth_method: Optional[str] = typer.Option(
        None, help="Authentication method: 'api-token', 'oauth', 'browser'"
    ),
) -> None:
    """Set up authentication for automated Jenkins access."""
    console.print("[bold blue]🔧 Authentication Setup[/bold blue]\n")

    try:
        from jenkins_credential_extractor.config import JenkinsConfigManager

        config_manager = JenkinsConfigManager()

        if not jenkins_url:
            jenkins_url = Prompt.ask("Jenkins URL (e.g., https://jenkins.example.com)")

        if not jenkins_url.startswith(("http://", "https://")):
            jenkins_url = f"https://{jenkins_url}"

        console.print(f"[cyan]Setting up authentication for: {jenkins_url}[/cyan]")

        # Initialize authentication manager
        from jenkins_credential_extractor.auth import JenkinsAuthManager

        auth_manager = JenkinsAuthManager(jenkins_url)

        if auth_method == "api-token" or not auth_method:
            console.print("\n[bold]Jenkins API Token Setup[/bold]")
            console.print("1. Log in to Jenkins")
            console.print("2. Go to your user profile > Configure")
            console.print("3. Generate a new API token")
            console.print("4. Copy the token value")

            if auth_manager.authenticate():
                console.print(
                    "[green]✅ API token authentication configured successfully[/green]"
                )
            else:
                console.print("[red]❌ API token authentication failed[/red]")

        elif auth_method == "oauth":
            console.print("\n[bold]Google OAuth Setup[/bold]")
            oauth_file = config_manager.setup_google_oauth()
            if oauth_file:
                auth_manager = JenkinsAuthManager(jenkins_url, oauth_file)
                if auth_manager.authenticate():
                    console.print(
                        "[green]✅ Google OAuth configured successfully[/green]"
                    )
                else:
                    console.print("[red]❌ Google OAuth authentication failed[/red]")
            else:
                console.print("[red]❌ Google OAuth setup failed[/red]")

        elif auth_method == "browser":
            console.print("\n[bold]Browser Session Setup[/bold]")
            if auth_manager.authenticate():
                console.print(
                    "[green]✅ Browser session authentication configured[/green]"
                )
            else:
                console.print("[red]❌ Browser session authentication failed[/red]")

        else:
            console.print(f"[red]❌ Unknown authentication method: {auth_method}[/red]")
            console.print("Available methods: api-token, oauth, browser")

    except ImportError as e:
        console.print(f"[red]❌ Enhanced authentication not available: {e}[/red]")
        console.print("Please ensure all dependencies are installed")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]❌ Authentication setup failed: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def config(
    show: bool = typer.Option(False, "--show", help="Show current configuration"),
    reset: bool = typer.Option(False, "--reset", help="Reset configuration"),
) -> None:
    """Manage Jenkins automation configuration."""
    console.print("[bold blue]⚙️  Configuration Management[/bold blue]\n")

    try:
        from jenkins_credential_extractor.config import JenkinsConfigManager

        config_manager = JenkinsConfigManager()

        if reset:
            if Confirm.ask("Are you sure you want to reset all configuration?"):
                import shutil

                shutil.rmtree(config_manager.config_dir, ignore_errors=True)
                console.print("[green]✅ Configuration reset successfully[/green]")
            return

        if show:
            config = config_manager.load_config()
            if not config:
                console.print("[yellow]No configuration found[/yellow]")
                return

            # Display current configuration
            table = Table(title="Current Configuration")
            table.add_column("Setting", style="cyan")
            table.add_column("Value", style="green")

            # Jenkins settings
            jenkins_config = config.get("jenkins", {})
            if jenkins_config:
                table.add_row("Jenkins URL", jenkins_config.get("url", "Not set"))
                table.add_row("Jenkins IP", jenkins_config.get("ip", "Not set"))

            # Auth settings
            auth_config = config.get("auth_preferences", {})
            if auth_config:
                table.add_row(
                    "Preferred Auth Method",
                    auth_config.get("preferred_method", "Not set"),
                )
                table.add_row(
                    "Session Caching", str(auth_config.get("cache_sessions", False))
                )
                table.add_row(
                    "Session Timeout (hours)",
                    str(auth_config.get("session_timeout_hours", 24)),
                )

            # OAuth settings
            oauth_config = config.get("google_oauth", {})
            if oauth_config:
                table.add_row(
                    "Google OAuth",
                    "Enabled" if oauth_config.get("enabled") else "Disabled",
                )
                table.add_row(
                    "Client Secrets File",
                    oauth_config.get("client_secrets_file", "Not set"),
                )

            console.print(table)
            return

        # Interactive configuration setup
        console.print("Running interactive configuration setup...")
        config_manager.setup_initial_configuration()

    except ImportError:
        console.print("[red]❌ Configuration management not available[/red]")
        console.print("Please ensure all dependencies are installed")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]❌ Configuration management failed: {e}[/red]")
        raise typer.Exit(1)


# Enhanced automation commands


@app.command()
def benchmark(
    jenkins_url: str = typer.Option(..., help="Jenkins server URL"),
    jenkins_ip: str = typer.Option(..., help="Jenkins server IP"),
    test_methods: str = typer.Option(
        "sequential,parallel,optimized", help="Comma-separated list of methods to test"
    ),
    sample_size: int = typer.Option(10, help="Number of test credentials to use"),
    credentials_file: str = typer.Option(
        "credentials.xml", help="Credentials file path"
    ),
    output_report: Optional[str] = typer.Option(
        None, help="Output benchmark report file"
    ),
) -> None:
    """Benchmark different credential extraction methods."""
    console.print("[bold blue]🏁 Jenkins Credential Extraction Benchmark[/bold blue]")

    try:
        from jenkins_credential_extractor.enhanced_jenkins import (
            EnhancedJenkinsAutomation,
        )
        from jenkins_credential_extractor.performance import (
            benchmark_automation_methods,
        )

        # Parse credentials file to get test data
        parser = CredentialsParser(credentials_file)
        if not parser.parse():
            console.print("[red]❌ Failed to parse credentials file[/red]")
            raise typer.Exit(1)

        credentials = parser.extract_nexus_credentials()
        if not credentials:
            console.print("[red]❌ No credentials found in file[/red]")
            raise typer.Exit(1)

        # Limit to sample size
        test_credentials = credentials[:sample_size]
        console.print(f"[blue]Testing with {len(test_credentials)} credentials[/blue]")

        # Initialize automation
        automation = EnhancedJenkinsAutomation(jenkins_url, jenkins_ip)

        # Parse methods to test
        methods_to_test = [m.strip() for m in test_methods.split(",")]

        # Run benchmark
        results = benchmark_automation_methods(
            automation, test_credentials, methods_to_test
        )

        # Display results comparison
        if len(results) > 1:
            console.print("\n[bold green]📊 Benchmark Results Comparison[/bold green]")

            table = Table(title="Method Performance Comparison")
            table.add_column("Method", style="cyan")
            table.add_column("Duration", style="green")
            table.add_column("Throughput", style="magenta")
            table.add_column("Success Rate", style="blue")
            table.add_column("Recommendation", style="yellow")

            for method, result in results.items():
                success_rate = (
                    (result.successful_items / result.total_items) * 100
                    if result.total_items > 0
                    else 0
                )

                # Generate recommendation
                if result.throughput_per_second >= 2.0 and success_rate >= 95:
                    recommendation = "✅ Excellent"
                elif result.throughput_per_second >= 1.0 and success_rate >= 90:
                    recommendation = "⚠️ Good"
                else:
                    recommendation = "❌ Needs improvement"

                table.add_row(
                    method,
                    f"{result.total_duration:.1f}s",
                    f"{result.throughput_per_second:.2f}/s",
                    f"{success_rate:.1f}%",
                    recommendation,
                )

            console.print(table)

            # Best performing method
            best_method = max(results.items(), key=lambda x: x[1].throughput_per_second)
            console.print(
                f"\n[bold green]🏆 Best performing method: {best_method[0]}[/bold green]"
            )

        # Save report if requested
        if output_report:
            from jenkins_credential_extractor.performance import global_benchmark

            report_path = global_benchmark.generate_csv_report(
                "password_decryption", Path(output_report)
            )
            console.print(f"[green]📄 Benchmark report saved: {report_path}[/green]")

    except ImportError as e:
        console.print(f"[red]❌ Missing dependency: {e}[/red]")
        console.print(
            "[yellow]💡 Run 'pdm install' to install all dependencies[/yellow]"
        )
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]❌ Benchmark failed: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def health_check(
    jenkins_url: str = typer.Option(..., help="Jenkins server URL"),
    jenkins_ip: str = typer.Option(..., help="Jenkins server IP"),
    client_secrets: Optional[str] = typer.Option(
        None, help="OAuth client secrets file"
    ),
    verbose: bool = typer.Option(False, help="Verbose output"),
) -> None:
    """Check Jenkins server health and connectivity."""
    console.print("[bold blue]🏥 Jenkins Health Check[/bold blue]")

    try:
        from jenkins_credential_extractor.enhanced_jenkins import (
            EnhancedJenkinsAutomation,
        )

        automation = EnhancedJenkinsAutomation(jenkins_url, jenkins_ip, client_secrets)

        # Test basic connectivity
        console.print("[blue]🔗 Testing connectivity...[/blue]")
        if automation.validate_jenkins_access():
            console.print("[green]✅ Jenkins server is accessible[/green]")
        else:
            console.print("[red]❌ Jenkins server is not accessible[/red]")
            raise typer.Exit(1)

        # Test authentication
        console.print("[blue]🔐 Testing authentication...[/blue]")
        if automation.ensure_authentication():
            console.print("[green]✅ Authentication successful[/green]")
        else:
            console.print("[red]❌ Authentication failed[/red]")
            raise typer.Exit(1)

        # Get server information
        console.print("[blue]ℹ️ Getting server information...[/blue]")
        jenkins_info = automation.get_jenkins_info()
        if jenkins_info:
            console.print("[green]✅ Server information retrieved[/green]")
            if verbose:
                table = Table(title="Jenkins Server Information")
                table.add_column("Property", style="cyan")
                table.add_column("Value", style="green")

                for key, value in jenkins_info.items():
                    if isinstance(value, (str, int, float, bool)):
                        table.add_row(key, str(value))

                console.print(table)
        else:
            console.print("[yellow]⚠️ Could not retrieve server information[/yellow]")

        # Error statistics
        from jenkins_credential_extractor.error_handling import error_recovery

        error_stats = error_recovery.get_error_statistics()

        if error_stats["error_counts"]:
            console.print("\n[yellow]⚠️ Error Statistics:[/yellow]")
            for operation, count in error_stats["error_counts"].items():
                console.print(f"  {operation}: {count} errors")
        else:
            console.print("[green]✅ No errors recorded[/green]")

        console.print(
            "\n[bold green]🎉 Health check completed successfully![/bold green]"
        )

    except ImportError as e:
        console.print(f"[red]❌ Missing dependency: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]❌ Health check failed: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def auth_status(
    jenkins_url: str = typer.Option(..., help="Jenkins server URL"),
    show_details: bool = typer.Option(
        False, help="Show detailed authentication information"
    ),
) -> None:
    """Check authentication status for a Jenkins server."""
    console.print("[bold blue]🔐 Authentication Status[/bold blue]")

    try:
        from jenkins_credential_extractor.auth import JenkinsAuthManager

        auth_manager = JenkinsAuthManager(jenkins_url)

        # Check if authenticated
        if auth_manager.is_authenticated():
            console.print(f"[green]✅ Authenticated with {jenkins_url}[/green]")

            if show_details:
                # Show authentication details (without sensitive data)
                table = Table(title="Authentication Details")
                table.add_column("Property", style="cyan")
                table.add_column("Value", style="green")

                table.add_row("Jenkins URL", jenkins_url)
                table.add_row(
                    "Authentication Method", auth_manager.get_auth_method() or "Unknown"
                )
                table.add_row(
                    "Session Valid", "Yes" if auth_manager.is_authenticated() else "No"
                )

                console.print(table)
        else:
            console.print(f"[red]❌ Not authenticated with {jenkins_url}[/red]")
            console.print(
                "[yellow]💡 Run 'jce setup-auth' to configure authentication[/yellow]"
            )
            raise typer.Exit(1)

    except ImportError as e:
        console.print(f"[red]❌ Missing dependency: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]❌ Authentication status check failed: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def clear_cache(
    jenkins_url: Optional[str] = typer.Option(
        None, help="Jenkins server URL (clears all if not specified)"
    ),
    confirm: bool = typer.Option(False, "--yes", help="Skip confirmation prompt"),
) -> None:
    """Clear authentication cache and stored credentials."""
    if not confirm:
        if jenkins_url:
            message = f"Clear authentication cache for {jenkins_url}?"
        else:
            message = "Clear all authentication cache and stored credentials?"

        if not Confirm.ask(message):
            console.print("[yellow]Operation cancelled[/yellow]")
            return

    try:
        from jenkins_credential_extractor.auth import JenkinsAuthManager
        from jenkins_credential_extractor.error_handling import error_recovery

        if jenkins_url:
            # Clear cache for specific server
            auth_manager = JenkinsAuthManager(jenkins_url)
            auth_manager.clear_cached_session()
            console.print(f"[green]✅ Cache cleared for {jenkins_url}[/green]")
        else:
            # Clear all cache (would need to implement in auth manager)
            console.print(
                "[yellow]⚠️ Global cache clearing not yet implemented[/yellow]"
            )
            console.print(
                "[blue]💡 You can clear individual server caches by specifying --jenkins-url[/blue]"
            )

        # Reset error statistics
        error_recovery.reset_statistics()
        console.print("[green]✅ Error statistics reset[/green]")

    except ImportError as e:
        console.print(f"[red]❌ Missing dependency: {e}[/red]")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]❌ Cache clearing failed: {e}[/red]")
        raise typer.Exit(1)


def select_project() -> Optional[str]:
    """Interactive project selection with fuzzy matching."""
    projects = get_projects_with_jenkins()

    if not projects:
        console.print("[red]No projects with Jenkins servers found[/red]")
        return None

    console.print("[bold]Available projects:[/bold]")
    for i, (key, project) in enumerate(projects, 1):
        console.print(
            f"  {i}. [cyan]{project['name']}[/cyan] ({key}) - {project['full_name']}"
        )

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


def _try_numeric_selection(
    choice: str, projects: List[Tuple[str, Any]]
) -> Optional[str]:
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
        if Confirm.ask(
            f"Did you mean '[cyan]{project_info['name']}[/cyan]' ({best_match})?"
        ):
            return best_match

    return None


if __name__ == "__main__":
    app()
