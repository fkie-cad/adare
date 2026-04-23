# external imports
import logging

import pandas as pd
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table

# internal imports
from adare.database.api.frontend import DataRetrievalApi
from adare.frontend.terminal.console import DefaultConsole, timedelta_to_str
from adarelib.constants import StatusEnum

log = logging.getLogger(__name__)


class RunListPanel:

    def __init__(self, runs: pd.DataFrame, project: str = None):
        self.runs = runs
        self.project = project

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

            # Show context-aware experiment name
            experiment_display = row['experiment_dotnotation']
            if self.project and experiment_display.startswith(f"{self.project}."):
                # Remove project prefix when we're in project context
                experiment_display = experiment_display[len(self.project) + 1:]

            table.add_row(
                row['id'],
                experiment_display,
                run_type,
                StatusEnum.get_icon(row['status'], color=True),
                StatusEnum.get_icon(row['result_status'], color=True),
                timedelta_to_str(row['duration']) if row['duration'] else '...',
            )

        return Panel(table, border_style="blue", title_align='left', style='', title=title)


def print_run_list(project: str, environment: str = None, experiment: str = None, formatter=None, output_file=None, dual_output=False):
    """Print run list in the configured output format."""

    # Get data from database
    with DataRetrievalApi() as api:
        runs = api.get_runs(project_name=project, environment_name=environment, experiment_name=experiment)

    # Get formatter if not provided
    if formatter is None:
        from adare.run import get_formatter_from_context
        formatter, output_file, dual_output = get_formatter_from_context()

    if dual_output or formatter.format_type.value != 'rich':
        # Use StructuredDataApi for JSON/YAML output
        from adare.database.api.structured_data import StructuredDataApi
        with StructuredDataApi() as api:
            runs_structured = api.get_runs_structured(
                project_name=project,
                environment_name=environment,
                experiment_name=experiment
            )
            run_list = [run.to_dict() for run in runs_structured]
            formatter.print_or_save({'runs': run_list}, output_file, dual_output)
    else:
        # Use existing Rich formatting
        console = DefaultConsole()
        layout = Layout(name="root")
        panel = RunListPanel(runs, project=project)
        layout.update(panel)
        console.print(layout)


