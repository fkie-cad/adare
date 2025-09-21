# external imports
import pandas as pd
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table

# internal imports
from adare.database.api.frontend import DataRetrievalApi
from adare.frontend.terminal.console import DefaultConsole
from adare.types.output_models import ExperimentInfo

import logging
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
        table.add_column("web status", style="cyan", no_wrap=True)

        for i, row in self.experiments.iterrows():
            published = True if row['published'] == 'True' else False
            in_request = True if row['in_request'] == 'True' else False
            web_status = 'NOT published'
            if published:
                web_status = 'published'
            if in_request:
                web_status = 'in request'

            table.add_row(
                row['display_name'],
                row['ulid'],
                row['environments_names'],
                row['description'],
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
        # Convert to structured data
        experiment_list = []
        for _, row in experiments.iterrows():
            published = True if row.get('published') == 'True' else False
            in_request = True if row.get('in_request') == 'True' else False
            web_status = 'NOT published'
            if published:
                web_status = 'published'
            if in_request:
                web_status = 'in request'

            experiment_info = ExperimentInfo(
                name=row['display_name'],
                ulid=row['ulid'],
                project=row.get('project', ''),
                environment=row.get('environments_names', ''),
                description=row.get('description', ''),
                tags=row.get('tags', '').split(',') if row.get('tags') else []
            )
            exp_dict = experiment_info.to_dict()
            exp_dict['web_status'] = web_status
            experiment_list.append(exp_dict)

        # Output structured data
        formatter.print_or_save({'experiments': experiment_list}, output_file, dual_output)
    else:
        # Use existing Rich formatting
        console = DefaultConsole()
        layout = Layout(name="root")
        panel = ExperimentTablePanel(experiments)
        layout.update(panel)
        console.print(layout)
