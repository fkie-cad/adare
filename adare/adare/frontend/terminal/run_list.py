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
from adare.frontend.terminal.console import pad_string_to_length, DefaultConsole, TwoTitleRule, timedelta_to_str
from adarelib.config import TIMESTAMP_FORMAT, StatusEnum
from adare.frontend.terminal.console import TwoTitleRule

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
        table.add_column("flow status", justify="left", style="cyan", no_wrap=True)
        table.add_column("tests status", justify="left", style="cyan", no_wrap=True)
        table.add_column("duration", justify="left", style="cyan", no_wrap=True)

        for index, row in self.runs.iterrows():
            table.add_row(
                row['ulid'],
                row['experiment_dotnotation'],
                StatusEnum.get_icon(row['status'], color=True),
                StatusEnum.get_icon(row['result_status'], color=True),
                timedelta_to_str(row['duration']) if row['duration'] else '...',
            )

        return Panel(table, border_style="blue", title_align='left', style='', title=title)


def print_run_list(project: str):
    console = DefaultConsole()

    with DataRetrievalApi() as api:
        runs = api.get_runs(project_name=project)
        layout = Layout(name="root")
        panel = RunListPanel(runs)
        layout.update(panel)
        console.print(layout)


