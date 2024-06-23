# external imports
import datetime
import pandas as pd
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule, ConsoleOptions, RenderResult, cell_len, set_cell_size, Measurement
from rich.text import Text

# internal imports
from adare.database.api.dataframe import DataRetrievalApi
from adare.frontend.terminal.console import DefaultConsole

import logging
log = logging.getLogger(__name__)


class TestfunctionPanel:
    testfunction: pd.DataFrame
    parameters: pd.DataFrame

    def __init__(self, testfunction: pd.DataFrame, parameters: pd.DataFrame):
        self.testfunction = testfunction
        self.parameters = parameters

    def __rich__(self) -> Panel:
        title = '[b gold3]testfunction[/b gold3]'
        grid = Table.grid(expand=True)


def print_testfunction(dotnotation: str = None):
    with DataRetrievalApi() as api:
        testfunction_id = api.testfunction_dotnotation_to_id(dotnotation)
        testfunction, parameters = api.get_testfunction(testfunction_id)
        console = DefaultConsole()
        layout = Layout(name="root")
        panel = TestfunctionPanel(testfunction, parameters)
        layout.update(panel)
        console.print(layout)
