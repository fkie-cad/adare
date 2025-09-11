# external imports
import pandas as pd
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table

# internal imports
from adare.database.api.frontend import DataRetrievalApi
from adare.frontend.terminal.console import DefaultConsole, timedelta_to_str
from adarelib.constants import StatusEnum

import logging
log = logging.getLogger(__name__)


class RunListPanel:

    def __init__(self, runs: pd.DataFrame):
        self.runs = runs

    def __rich__(self) -> Panel:
        title = '[b gold3]runs[/b gold3]'
        table = Table()
        table.add_column("ulid", justify="left", style="cyan", no_wrap=True)
        table.add_column("experiment", justify="left", style="cyan", no_wrap=True)
        table.add_column("type", justify="left", style="cyan", no_wrap=True)
        table.add_column("flow status", justify="left", style="cyan", no_wrap=True)
        table.add_column("tests status", justify="left", style="cyan", no_wrap=True)
        table.add_column("duration", justify="left", style="cyan", no_wrap=True)

        for _, row in self.runs.iterrows():
            # Determine if run is fake or real
            run_type = "[red]fake[/red]" if row.get('fake', False) else "[green]real[/green]"
            
            table.add_row(
                row['id'],
                row['experiment_dotnotation'],
                run_type,
                StatusEnum.get_icon(row['status'], color=True),
                StatusEnum.get_icon(row['result_status'], color=True),
                timedelta_to_str(row['duration']) if row['duration'] else '...',
            )

        return Panel(table, border_style="blue", title_align='left', style='', title=title)


def print_run_list(project: str, environment: str = None, experiment: str = None):
    console = DefaultConsole()

    with DataRetrievalApi() as api:
        runs = api.get_runs(project_name=project, environment_name=environment, experiment_name=experiment)
        layout = Layout(name="root")
        panel = RunListPanel(runs)
        layout.update(panel)
        console.print(layout)


