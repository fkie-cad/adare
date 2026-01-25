# external imports
import pandas as pd
from rich.panel import Panel
from rich.table import Table

# internal imports
import logging
log = logging.getLogger(__name__)


class DevSessionTablePanel:
    def __init__(self, sessions: pd.DataFrame):
        self.sessions = sessions

    def __rich__(self) -> Panel:
        table = Table(expand=True)
        table.add_column("status", style="cyan", no_wrap=True)
        table.add_column("session id", style="green", no_wrap=True)
        table.add_column("experiment", style="white", no_wrap=True)
        table.add_column("environment", style="white", no_wrap=True)
        table.add_column("vm", style="cyan", no_wrap=True)
        table.add_column("actions", style="magenta", no_wrap=True)
        table.add_column("created", style="blue", no_wrap=True)

        for i, row in self.sessions.iterrows():
            # Status formatting
            status = row.get('status', 'unknown')
            if status == 'running':
                status_display = "[green]●[/green] running"
            elif status == 'stopped':
                status_display = "[yellow]⏸[/yellow] stopped"
            elif status == 'crashed':
                status_display = "[red]✗[/red] crashed"
            else:
                status_display = f"[white]?[/white] {status}"

            # VM status
            vm_running = row.get('vm_running', False)
            vm_display = "[green]active[/green]" if vm_running else "[dim]off[/dim]"

            table.add_row(
                status_display,
                str(row.get('session_id', 'N/A')),
                str(row.get('experiment_name', 'N/A')),
                str(row.get('environment_name', 'N/A')),
                vm_display,
                str(row.get('actions_executed', 0)),
                str(row.get('created_at', 'N/A')),
            )
        
        return Panel(table, title="[b gold3]dev sessions[/b gold3]", border_style="blue", title_align="left")
