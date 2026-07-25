"""Web UI commands for ADARE (start, build, services)."""

import logging
import os
import signal
import sys

import click

logger = logging.getLogger(__name__)


def _provision_virtualspice(console, *, force: bool = False) -> bool:
    """Download + verify the VirtualSpice binary with a Rich progress bar.

    Returns True on success (or already-cached), False on any provisioning
    failure. Never raises — failures are reported and VM features degrade.
    """
    from rich.progress import (
        BarColumn,
        DownloadColumn,
        Progress,
        TextColumn,
        TransferSpeedColumn,
    )

    from adare.webapi import virtualspice_release as vsr

    if not vsr.is_platform_supported():
        console.print(
            "[yellow]No VirtualSpice release asset for this platform; "
            "build from source or set VIRTUALSPICE_BINARY.[/yellow]"
        )
        return False

    with Progress(
        TextColumn("[blue]Downloading VirtualSpice[/blue]"),
        BarColumn(),
        DownloadColumn(),
        TransferSpeedColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("download", total=None)

        def _cb(downloaded: int, total: int) -> None:
            progress.update(task, completed=downloaded, total=total or None)

        try:
            path = vsr.ensure_binary(progress_cb=_cb, force=force)
        except vsr.VirtualSpiceProvisionError as exc:
            console.print(f"[red]VirtualSpice provisioning failed: {exc}[/red]")
            return False

    console.print(f"[green]VirtualSpice binary ready:[/green] [dim]{path}[/dim]")
    return True


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

    # Auto-provision from the pinned GitHub release if no binary was found by any
    # local tier (env var, ~/.local/bin, dev target, managed cache, PATH).
    if not vs_manager.available:
        console.print(
            "[yellow]VirtualSpice binary not found; attempting download...[/yellow]"
        )
        if _provision_virtualspice(console):
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
            "[yellow]VirtualSpice unavailable. "
            "VM features will be unavailable.[/yellow]"
        )
        console.print(
            "[dim]Set VIRTUALSPICE_BINARY env var, run 'adare web "
            "install-spice', or build from source.[/dim]"
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

    # Ensure dependencies are installed before building.
    # --ignore-workspace: a pnpm-workspace.yaml may exist in an ancestor directory
    # (e.g. the legacy sibling layout). Without this flag, pnpm would install into
    # the outer workspace root instead of adare-web/node_modules, and tsc/vite
    # would not be found on PATH during the build step.
    if not os.path.isdir(os.path.join(web_dir, "node_modules")):
        console.print("[yellow]node_modules not found. Running pnpm install...[/yellow]")
        install_result = subprocess.run(
            ["pnpm", "install", "--ignore-workspace"],
            cwd=web_dir,
            capture_output=False,
        )
        if install_result.returncode != 0:
            console.print("[red]pnpm install failed.[/red]")
            sys.exit(1)

    result = subprocess.run(
        ["pnpm", "--ignore-workspace", "run", "build"],
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
        urllib.request.urlopen(
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


@click.command("install-spice")
@click.option(
    "--force", is_flag=True, help="Re-download even if already cached."
)
def web_install_spice(force):
    """Download and verify the VirtualSpice (spice-client) binary."""
    from rich.console import Console

    console = Console()

    from adare.webapi import virtualspice_release as vsr

    console.print(
        f"[blue]VirtualSpice {vsr.VIRTUALSPICE_VERSION} "
        f"({vsr.VIRTUALSPICE_REPO})[/blue]"
    )
    if _provision_virtualspice(console, force=force):
        console.print("[green]Done.[/green]")
    else:
        raise SystemExit(1)
