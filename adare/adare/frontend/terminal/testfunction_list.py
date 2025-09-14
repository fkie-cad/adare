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

        # Add file column if not filtering by specific file
        if not self.testfunction_file:
            table.add_column("file", justify="left", style="cyan", no_wrap=True)

        table.add_column("testfunction", justify="left", style="cyan", no_wrap=True)
        table.add_column("description", justify="left", style="cyan", no_wrap=True)
        table.add_column("#parameters", justify="left", style="cyan", no_wrap=True)

        for _, row in self.testfunctions.iterrows():
            # For name, remove file prefix if showing file column separately
            if self.testfunction_file:
                display_name = row['name']
            else:
                display_name = row['dotnotation']
                if '.' in display_name:
                    display_name = display_name.split('.', 1)[1]  # Keep everything after the first dot

            row_data = []

            # Add file column data if not filtering by specific file
            if not self.testfunction_file:
                # Extract file name from dotnotation or file_name column if available
                if 'file_name' in row:
                    file_name = row['file_name'].replace('.py', '') if row['file_name'].endswith('.py') else row['file_name']
                elif 'dotnotation' in row and '.' in row['dotnotation']:
                    file_name = row['dotnotation'].split('.', 1)[0]
                else:
                    file_name = 'unknown'
                row_data.append(file_name)

            row_data.extend([
                display_name,
                row['description'],
                str(row['num_parameters']),
            ])

            table.add_row(*row_data)

        return Panel(table, border_style="blue", title_align='left', style='', title=title)


def print_testfunction_list(testfunction_file: str = None):

    with DataRetrievalApi() as api:
        testfunctions = api.get_testfunction_list()
        console = DefaultConsole()
        layout = Layout(name="root")
        panel = TestfunctionListPanel(testfunctions, testfunction_file)
        layout.update(panel)
        console.print(layout)
