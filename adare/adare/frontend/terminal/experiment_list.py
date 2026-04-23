# external imports
import logging

import pandas as pd
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table

# internal imports
from adare.database.api.frontend import DataRetrievalApi
from adare.frontend.terminal.console import DefaultConsole

log = logging.getLogger(__name__)


class ExperimentTablePanel:
    experiments: pd.DataFrame

    def __init__(self, experiments: pd.DataFrame):
        self.experiments = experiments

    def __rich__(self) -> Panel:
        table = Table(expand=True)
        table.add_column("name", style="cyan", no_wrap=True)
        table.add_column("ulid", style="cyan", no_wrap=True)
        table.add_column("environments", style="cyan", no_wrap=True)
        table.add_column("description", style="cyan", no_wrap=True)
        table.add_column("tags", style="magenta", no_wrap=False)
        table.add_column("web status", style="cyan", no_wrap=True)

        for _i, row in self.experiments.iterrows():
            published = row['published'] == 'True'
            in_request = row['in_request'] == 'True'
            web_status = 'NOT published'
            if published:
                web_status = 'published'
            if in_request:
                web_status = 'in request'

            tags = row.get('tags', '') if 'tags' in row.index else ''

            table.add_row(
                row['display_name'],
                row['ulid'],
                row['environments_names'],
                row['description'],
                tags,
                web_status,
            )
        return Panel(table, title="[b gold3]experiments[/b gold3]", border_style="blue", title_align="left")


def print_experiment_list(formatter=None, output_file=None, dual_output=False):
    """Print experiment list in the configured output format."""

    # Get data from database
    with DataRetrievalApi() as db:
        experiments = db.get_experiments()

    # Get formatter if not provided
    if formatter is None:
        from adare.run import get_formatter_from_context
        formatter, output_file, dual_output = get_formatter_from_context()

    if dual_output or formatter.format_type.value != 'rich':
        # Use StructuredDataApi for JSON/YAML output
        from adare.database.api.structured_data import StructuredDataApi
        with StructuredDataApi() as api:
            experiments_structured = api.get_experiments_structured()
            experiment_list = [exp.to_dict() for exp in experiments_structured]
            formatter.print_or_save({'experiments': experiment_list}, output_file, dual_output)
    else:
        # Use existing Rich formatting
        console = DefaultConsole()
        layout = Layout(name="root")
        panel = ExperimentTablePanel(experiments)
        layout.update(panel)
        console.print(layout)
