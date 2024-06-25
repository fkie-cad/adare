# external imports
import datetime
import pandas as pd
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule, ConsoleOptions, RenderResult, cell_len, set_cell_size, Measurement
from rich.text import Text

# internal imports
from adare.database.api.frontend import DataRetrievalApi
from adare.frontend.terminal.console import DefaultConsole


import logging
log = logging.getLogger(__name__)


class ParameterPanel:
    parameters: pd.DataFrame

    def __init__(self, parameters: pd.DataFrame):
        self.parameters = parameters

    def __rich__(self) -> Panel:
        title = '[b medium_turquoise]parameters[/b medium_turquoise]'
        table = Table(expand=True, header_style="bold")
        table.add_column("name", style="")
        table.add_column("datatype", style="")
        for index, row in self.parameters.iterrows():
            table.add_row(row['name'], row['dtype'])

        return Panel(table, title=title, border_style="blue", title_align='left')


class DescriptionPanel:
    description: str

    def __init__(self, description: str):
        self.description = description

    def __rich__(self) -> Panel:
        title = '[b light_steel_blue]description[/b light_steel_blue]'
        text = Text(self.description)
        return Panel(text, title=title, border_style="blue", title_align='left')


class TestfunctionPanel:
    testfunction_name: str
    testfunction: pd.DataFrame
    parameters: pd.DataFrame

    def __init__(self, testfunction_name: str, testfunction: pd.DataFrame, parameters: pd.DataFrame):
        self.testfunction_name = testfunction_name
        self.testfunction = testfunction
        self.parameters = parameters

    def __rich__(self) -> Panel:
        title = f'[b gold3]{self.testfunction_name}[/b gold3]'
        layout = Layout(name="testfunction")
        layout.split_row(
            Layout(name="description", ratio=1),
            Layout(name="parameters", ratio=2),
        )
        description = self.testfunction["description"].values[0]
        layout["description"].update(DescriptionPanel(description))
        layout["parameters"].update(ParameterPanel(self.parameters))
        return Panel(layout, title=title, border_style="blue", title_align='left')


def print_testfunction(dotnotation: str = None, testfunction_id: str = None):
    with DataRetrievalApi() as api:
        if dotnotation:
            testfunction_id = api.testfunction_dotnotation_to_id(dotnotation)
        else:
            testfunction_id = int(testfunction_id)
        testfunction, parameters = api.get_testfunction(testfunction_id)
        console = DefaultConsole()
        layout = Layout(name="root")

        panel = TestfunctionPanel(dotnotation, testfunction, parameters)
        layout.update(panel)
        console.print(layout)
