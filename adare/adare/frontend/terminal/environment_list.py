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


class EnvironmentTablePanel:
    def __init__(self, environments: pd.DataFrame):
        self.environments = environments

    def __rich__(self) -> Panel:
        table = Table(expand=True)
        table.add_column("name", style="cyan", no_wrap=True)
        table.add_column("ulid", style="cyan", no_wrap=True)
        table.add_column("vm", style="cyan", no_wrap=True)
        table.add_column("os", style="cyan", no_wrap=True)
        table.add_column("web status", style="cyan", no_wrap=True)

        for i, row in self.environments.iterrows():
            published = True if row['published'] == 'True' else False
            in_request = True if row['in_request'] == 'True' else False
            web_status = 'NOT published'
            if published:
                web_status = 'published'
            if in_request:
                web_status = 'in request'

            table.add_row(
                row['dotnotation'],
                row['id'],
                row['vm_name'] if 'vm_name' in row and row['vm_name'] else 'No VM',
                row['osinfo'] if 'osinfo' in row and row['osinfo'] else 'Unknown',
                web_status,
            )
        return Panel(table, title="[b gold3]environments[/b gold3]", border_style="blue", title_align="left")


def print_environment_list():
    with DataRetrievalApi() as db:
        console = DefaultConsole()
        environments = db.get_environments()
        layout = Layout(name="root")
        panel = EnvironmentTablePanel(environments)
        layout.update(panel)
        console.print(layout)
