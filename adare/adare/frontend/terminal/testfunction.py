# external imports
import logging

import pandas as pd
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# internal imports
from adare.database.api.frontend import DataRetrievalApi
from adare.frontend.terminal.console import DefaultConsole

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
        for _index, row in self.parameters.iterrows():
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


def print_testfunction(dotnotation: str = None, testfunction_id: str = None, formatter=None, output_file=None, dual_output=False):
    # Get formatter if not provided
    if formatter is None:
        from adare.run import get_formatter_from_context
        formatter, output_file, dual_output = get_formatter_from_context()

    with DataRetrievalApi() as api:
        testfunction_id = api.testfunction_dotnotation_to_id(dotnotation) if dotnotation else int(testfunction_id)
        testfunction, parameters = api.get_testfunction(testfunction_id)

        # Check if structured output is needed
        if dual_output or formatter.format_type.value != 'rich':
            structured_data = {
                'dotnotation': dotnotation,
                'id': testfunction_id,
                'description': testfunction['description'].values[0] if not testfunction.empty else None,
                'parameters': parameters.to_dict('records') if not parameters.empty else []
            }
            formatter.print_or_save(structured_data, output_file, dual_output)

            if not dual_output:
                return

        console = DefaultConsole()
        layout = Layout(name="root")

        panel = TestfunctionPanel(dotnotation, testfunction, parameters)
        layout.update(panel)
        console.print(layout)
