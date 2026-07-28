"""Status command - quick overview of ADARE system state."""

import logging

log = logging.getLogger(__name__)


def exec_status(arguments):
    """Show quick overview of current ADARE state."""
    from rich.console import Console

    from adare.api import AdareAPI

    console = Console()
    api = AdareAPI()

    console.print("\n[bold]ADARE Status[/bold]\n")

    # Current project
    try:
        from adare.database.utils.display_helpers import get_current_project_name
        project_name = get_current_project_name()
        if project_name:
            console.print(f"  Project:    [green]{project_name}[/green]")
        else:
            console.print("  Project:    [dim]none selected[/dim]")
    except Exception:
        console.print("  Project:    [dim]unknown[/dim]")

    # Active dev sessions
    try:
        from adare.backend.basics import determine_projectdirectory
        from adare.core.dto.devmode import DevSessionListRequest

        project_directory = determine_projectdirectory(None, silent=True)
        result = api.devmode.list_sessions(DevSessionListRequest(project_path=project_directory))
        if result.success and result.data:
            active = [s for s in result.data if s.status == 'running']
            stopped = [s for s in result.data if s.status == 'stopped']
            console.print(f"  Sessions:   [green]{len(active)} running[/green], {len(stopped)} stopped")
        else:
            console.print("  Sessions:   [dim]0[/dim]")
    except Exception:
        console.print("  Sessions:   [dim]unavailable[/dim]")

    # VM count
    try:
        result = api.vm.list_instances()
        if result.success and result.data:
            console.print(f"  VMs:        {len(result.data)} instances")
        else:
            console.print("  VMs:        [dim]0[/dim]")
    except Exception:
        console.print("  VMs:        [dim]unavailable[/dim]")

    # Database status
    try:
        result = api.manage.get_db_status()
        if result.success and result.data.valid:
            console.print("  Database:   [green]initialized[/green]")
        else:
            console.print("  Database:   [yellow]not initialized[/yellow]")
    except Exception:
        console.print("  Database:   [dim]unavailable[/dim]")

    console.print()
