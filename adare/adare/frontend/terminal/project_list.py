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
from adare.helperfunctions.cli import print_df, print_dict
from adare.database.api.frontend import DataRetrievalApi
from adare.exceptions import ArgumentsError
from adare.frontend.terminal.console import pad_string_to_length, DefaultConsole, timedelta_to_str
from adare.config import TIMESTAMP_FORMAT, StatusEnum
from adare.frontend.terminal.console import TwoTitleRule

import logging
log = logging.getLogger(__name__)


class ProjectTablePanel:
    def __init__(self, projects: pd.DataFrame):
        self.projects = projects

    def __rich__(self) -> Panel:
        table = Table(expand=True)
        table.add_column("name", style="cyan", no_wrap=True)
        table.add_column("path", style="cyan", no_wrap=True)
        table.add_column("environments", style="cyan", no_wrap=True)

        for i, row in self.projects.iterrows():
            table.add_row(
                row['name'],
                row['path'],
                row['environments_names']
            )
        return Panel(table, title="[b gold3]projects[/b gold3]", border_style="blue", title_align="left")


def print_project_list():
    with DataRetrievalApi() as db:
        console = DefaultConsole()
        projects = db.get_projects()
        layout = Layout(name="root")
        panel = ProjectTablePanel(projects)
        layout.update(panel)
        console.print(layout)
