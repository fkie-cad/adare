# external imports
import datetime
import pandas as pd
from rich.layout import Layout
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule, ConsoleOptions, RenderResult, cell_len, set_cell_size, Measurement
from rich.text import Text
import numpy as np

# internal imports
from adarelib.helperfunctions.cli import print_df, print_dict
from adare.database.api.frontend import DataRetrievalApi
from adarelib.exceptions import ArgumentsError
from adare.frontend.terminal.console import pad_string_to_length, DefaultConsole, timedelta_to_str
from adarelib.config import TIMESTAMP_FORMAT, StatusEnum
from adare.frontend.terminal.console import TwoTitleRule

import logging
log = logging.getLogger(__name__)


class EnvironmentTablePanel:
    def __init__(self, projects: pd.DataFrame):
        self.projects = projects

    def __rich__(self) -> Panel:
        table = Table(expand=True)
        table.add_column("name", style="cyan", no_wrap=True)
        table.add_column("ulid", style="cyan", no_wrap=True)
        table.add_column("box", style="cyan", no_wrap=True)
        table.add_column("os", style="cyan", no_wrap=True)
        table.add_column("web status", style="cyan", no_wrap=True)

        for i, row in self.projects.iterrows():
            published = True if row['published'] == 'True' else False
            in_request = True if row['in_request'] == 'True' else False
            web_status = 'NOT published'
            if published:
                web_status = 'published'
            if in_request:
                web_status = 'in request'

            table.add_row(
                row['dotnotation'],
                row['ulid'],
                row['vagrantbox'],
                row['osinfo'],
                web_status,
            )
        return Panel(table, title="[b gold3]environments[/b gold3]", border_style="blue", title_align="left")


def print_environment_list():
    with DataRetrievalApi() as db:
        console = DefaultConsole()
        projects = db.get_environments()
        layout = Layout(name="root")
        panel = EnvironmentTablePanel(projects)
        layout.update(panel)
        console.print(layout)
