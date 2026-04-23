"""Web UI commands for ADARE (start, build, services)."""

import logging
import os
import signal
import sys

import click

logger = logging.getLogger(__name__)


@click.command("start")
@click.option("--port", default=8089, help="Main server port")
@click.option("--host", default="127.0.0.1", help="Host to bind to")
@click.option("--dev", is_flag=True, help="Development mode with auto-reload")
@click.option("--no-browser", is_flag=True, help="Don't open browser")
@click.option("--spice-port", default=8081, help="VirtualSpice backend port")
@click.pass_context
def web_start(ctx, port, host, dev, no_browser, spice_port):
    """Start the ADARE web UI (FastAPI + VirtualSpice)."""
    from rich.console import Console

    console = Console()

    # Start VirtualSpice if available
    from adare.webapi.process_manager import VirtualSpiceManager

    vs_manager = VirtualSpiceManager(port=spice_port)

    if vs_manager.available:
        console.print(
            f"[green]Starting VirtualSpice on port {spice_port}...[/green]"
        )
        if vs_manager.start():
            console.print("[green]VirtualSpice started.[/green]")
        else:
            console.print(
                "[yellow]Warning: VirtualSpice failed to start. "
                "VM features will be unavailable.[/yellow]"
            )
    else:
        console.print(
            "[yellow]VirtualSpice binary not found. "
            "VM features will be unavailable.[/yellow]"
        )
        console.print(
            "[dim]Set VIRTUALSPICE_BINARY env var or "
            "install virtualspice to PATH.[/dim]"
        )

    # Open browser
    if not no_browser:
        import webbrowser

        url = f"http://{host}:{port}"
        console.print(f"[blue]Opening {url} in browser...[/blue]")
        webbrowser.open(url)

    console.print(
        f"[green]Starting ADARE web server on {host}:{port}...[/green]"
    )
    if dev:
        console.print("[dim]Development mode: auto-reload enabled[/dim]")

    # Handle graceful shutdown
    def shutdown_handler(signum, frame):
        console.print("\n[yellow]Shutting down...[/yellow]")
        vs_manager.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    # Start FastAPI
    try:
        import uvicorn
    except ImportError as e:
        console.print(
            "[red]Error: uvicorn is required. "
            "Install with: pip install uvicorn[standard][/red]"
        )
        vs_manager.stop()
        raise SystemExit(1) from e

    try:
        uvicorn.run(
            "adare.webapi.main:app",
            host=host,
            port=port,
            reload=dev,
            log_level="info",
        )
    finally:
        vs_manager.stop()


@click.command("build")
def web_build():
    """Build the ADARE web frontend (pnpm build in adare-web)."""
    import subprocess

    from rich.console import Console

    console = Console()

    # Try to find adare-web relative to this file's package location
    package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    project_dir = os.path.dirname(package_dir)

    candidates = [
        os.path.join(project_dir, "adare-web"),
        os.path.join(os.path.dirname(project_dir), "adare-web"),
    ]

    web_dir = None
    for candidate in candidates:
        if os.path.isdir(candidate):
            web_dir = candidate
            break

    if web_dir is None:
        console.print("[red]Error: adare-web directory not found.[/red]")
        console.print(
            f"[dim]Searched: {', '.join(candidates)}[/dim]"
        )
        sys.exit(1)

    console.print(f"[blue]Building frontend in {web_dir}...[/blue]")

    result = subprocess.run(
        ["pnpm", "run", "build"],
        cwd=web_dir,
        capture_output=False,
    )

    if result.returncode != 0:
        console.print("[red]Build failed.[/red]")
        sys.exit(1)

    console.print("[green]Build complete.[/green]")


@click.command("services")
@click.option("--port", default=8089, help="FastAPI server port to check")
@click.option("--spice-port", default=8081, help="VirtualSpice backend port")
def web_services(port, spice_port):
    """Show status of ADARE web services (FastAPI, VirtualSpice, frontend build)."""
    import urllib.error
    import urllib.request

    from rich.console import Console
    from rich.table import Table

    console = Console()

    table = Table(title="ADARE Web Services")
    table.add_column("Service", style="bold")
    table.add_column("Status")
    table.add_column("Details")

    # Check FastAPI
    try:
        req = urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/health", timeout=2
        )
        table.add_row("FastAPI", "[green]Running[/green]", f"Port {port}")
    except (urllib.error.URLError, OSError, TimeoutError):
        table.add_row("FastAPI", "[red]Stopped[/red]", f"Port {port}")

    # Check VirtualSpice
    from adare.webapi.process_manager import VirtualSpiceManager

    vs = VirtualSpiceManager(port=spice_port)
    if vs.health_check():
        table.add_row(
            "VirtualSpice", "[green]Running[/green]", f"Port {spice_port}"
        )
    else:
        table.add_row(
            "VirtualSpice", "[red]Stopped[/red]", f"Port {spice_port}"
        )

    # Check frontend build
    package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    project_dir = os.path.dirname(package_dir)
    dist_candidates = [
        os.path.join(project_dir, "adare-web", "dist"),
        os.path.join(os.path.dirname(project_dir), "adare-web", "dist"),
    ]

    found_dist = None
    for candidate in dist_candidates:
        if os.path.isdir(candidate):
            found_dist = candidate
            break

    if found_dist:
        table.add_row(
            "Frontend Build", "[green]Available[/green]", found_dist
        )
    else:
        table.add_row(
            "Frontend Build",
            "[yellow]Not built[/yellow]",
            "Run: adare web build",
        )

    console.print(table)
