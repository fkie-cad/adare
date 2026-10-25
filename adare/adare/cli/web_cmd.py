"""Web UI commands for ADARE (start, build, services)."""

import logging
import os
import signal
import sys

import click

from adare.cli.output import output_options

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
    from adare.webapi.vm_watch import SPICE_PORT_ENV

    # The live-view proxy and VM-name lookup run in the server: point them at this port.
    os.environ[SPICE_PORT_ENV] = str(spice_port)
    vs_manager = VirtualSpiceManager(port=spice_port)

    # Auto-provision from the pinned GitHub release if no binary was found by any
    # local tier (env var, ~/.local/bin, dev target, managed cache, PATH).
    if not vs_manager.available:
        console.print("[yellow]VirtualSpice binary not found; attempting download...[/yellow]")
        if _provision_virtualspice(console):
            vs_manager = VirtualSpiceManager(port=spice_port)

    if vs_manager.available:
        console.print(f"[green]Starting VirtualSpice on port {spice_port}...[/green]")
        if not vs_manager.start():
            console.print(f"[yellow]Warning: VirtualSpice failed to start ({vs_manager.error}).[/yellow]")
            console.print(f"[dim]Live VM views will be unavailable. Log: {vs_manager.log_file}[/dim]")
        elif vs_manager.reused:
            console.print(f"[green]VirtualSpice already running on port {spice_port}; using it.[/green]")
        else:
            console.print(f"[green]VirtualSpice started[/green] [dim]({vs_manager.binary_path})[/dim]")
    else:
        console.print("[yellow]VirtualSpice unavailable. VM features will be unavailable.[/yellow]")
        console.print("[dim]Set VIRTUALSPICE_BINARY env var, run 'adare ui install-spice', or build from source.[/dim]")

    # Open browser
    if not no_browser:
        import webbrowser

        url = f"http://{host}:{port}"
        console.print(f"[blue]Opening {url} in browser...[/blue]")
        webbrowser.open(url)

    console.print(f"[green]Starting ADARE web server on {host}:{port}...[/green]")
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
        console.print("[red]Error: uvicorn is required. Install with: pip install uvicorn[standard][/red]")
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
        console.print(f"[dim]Searched: {', '.join(candidates)}[/dim]")
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


@click.command("status")
@click.option("--port", default=8089, help="FastAPI server port to check")
@click.option("--spice-port", default=8081, help="VirtualSpice backend port")
@output_options
def web_services(port, spice_port):
    """Show status of the local web UI services (FastAPI, VirtualSpice, frontend build)."""
    import urllib.error
    import urllib.request

    from rich.table import Table

    from adare.cli.output import emit
    from adare.webapi.process_manager import VirtualSpiceManager

    # Check FastAPI
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=2)
        fastapi_running = True
    except (urllib.error.URLError, OSError, TimeoutError):
        fastapi_running = False

    # Check VirtualSpice
    spice_running = bool(VirtualSpiceManager(port=spice_port).health_check())

    # Check frontend build
    package_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    project_dir = os.path.dirname(package_dir)
    dist_candidates = [
        os.path.join(project_dir, "adare-web", "dist"),
        os.path.join(os.path.dirname(project_dir), "adare-web", "dist"),
    ]
    found_dist = next((c for c in dist_candidates if os.path.isdir(c)), None)

    services = [
        {
            "service": "fastapi",
            "status": "running" if fastapi_running else "stopped",
            "running": fastapi_running,
            "port": port,
            "details": f"Port {port}",
        },
        {
            "service": "virtualspice",
            "status": "running" if spice_running else "stopped",
            "running": spice_running,
            "port": spice_port,
            "details": f"Port {spice_port}",
        },
        {
            "service": "frontend_build",
            "status": "available" if found_dist else "not_built",
            "running": bool(found_dist),
            "port": None,
            "details": found_dist or "Run: adare ui build",
        },
    ]

    def _table():
        labels = {"fastapi": "FastAPI", "virtualspice": "VirtualSpice", "frontend_build": "Frontend Build"}
        colours = {"running": "green", "available": "green", "stopped": "red", "not_built": "yellow"}
        table = Table(title="ADARE Web Services")
        table.add_column("Service", style="bold")
        table.add_column("Status")
        table.add_column("Details")
        for svc in services:
            colour = colours[svc["status"]]
            status = svc["status"].replace("_", " ").capitalize()
            table.add_row(labels[svc["service"]], f"[{colour}]{status}[/{colour}]", svc["details"])
        return table

    emit({"services": services}, rich=_table)


@click.command("install-spice")
@click.option("--force", is_flag=True, help="Re-download even if already cached.")
def web_install_spice(force):
    """Download and verify the VirtualSpice (spice-client) binary."""
    from rich.console import Console

    console = Console()

    from adare.webapi import virtualspice_release as vsr

    console.print(f"[blue]VirtualSpice {vsr.VIRTUALSPICE_VERSION} ({vsr.VIRTUALSPICE_REPO})[/blue]")
    if _provision_virtualspice(console, force=force):
        console.print("[green]Done.[/green]")
    else:
        raise SystemExit(1)
