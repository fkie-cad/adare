# external imports
import pandas as pd
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table

# internal imports
from adare.database.api.frontend import DataRetrievalApi
from adare.frontend.terminal.console import DefaultConsole

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


def print_experiment_list():
    with DataRetrievalApi() as db:
        console = DefaultConsole()
        experiments = db.get_experiments()
        layout = Layout(name="root")
        panel = ExperimentTablePanel(experiments)
        layout.update(panel)
        console.print(layout)
