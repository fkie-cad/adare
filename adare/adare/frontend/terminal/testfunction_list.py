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


class TestfunctionListPanel:
    testfunctions: pd.DataFrame
    testfunction_file: str

    def __init__(self, testfunctions: pd.DataFrame, testfunction_file: str):
        self.testfunctions = testfunctions
        self.testfunction_file = testfunction_file

    def __rich__(self) -> Panel:
        if not self.testfunction_file:
            title = '[b gold3]testfunctions[/b gold3]'
        else:
            title = f'[b gold3]testfunctions[/b gold3] from [b gold3]{self.testfunction_file}[/b gold3]'
        table = Table(expand=True)
        table.add_column("testfunction", justify="left", style="cyan", no_wrap=True)
        table.add_column("description", justify="left", style="cyan", no_wrap=True)
        table.add_column("#parameters", justify="left", style="cyan", no_wrap=True)

        for index, row in self.testfunctions.iterrows():
            table.add_row(
                row['name'] if self.testfunction_file else row['dotnotation'],
                row['description'],
                str(row['num_parameters']),
            )

        return Panel(table, border_style="blue", title_align='left', style='', title=title)


def print_testfunction_list(testfunction_file: str = None):

    with DataRetrievalApi() as api:
        testfunctions = api.get_testfunction_list()
        console = DefaultConsole()
        layout = Layout(name="root")
        panel = TestfunctionListPanel(testfunctions, testfunction_file)
        layout.update(panel)
        console.print(layout)
