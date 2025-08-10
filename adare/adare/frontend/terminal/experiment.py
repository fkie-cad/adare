# external imports
import datetime
import pandas as pd
from rich.layout import Layout
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.rule import Rule

# internal imports
from adare.database.api.frontend import DataRetrievalApi
from adare.frontend.terminal.console import pad_string_to_length, DefaultConsole, TagsText

import logging
log = logging.getLogger(__name__)


class TestsPanel:
    tests_data: dict

    def __init__(self, tests_data: dict):
        self.tests_data = tests_data

    def __rich__(self) -> Panel:
        grid = Table.grid(expand=True)
        grid.add_column(justify="left", ratio=1)

        for test_data in self.tests_data.values():
            color = 'grey'
            grid.add_row(
                Rule(
                    title=f'[b {color}]{test_data["name"]} ([i]{test_data["testfunction_name"]}[/i])[/b {color}]',
                    style=color,
                    align='left',
                ),
            )
            grid.add_row(':gear: [b]parameters[/b]:')
            for parameter in test_data['parameters']:
                grid.add_row(
                    f'  {parameter["name"]} ([i]{parameter["dtype"]}[/i]): [b]{parameter["value"]}[/b]'
                )
            grid.add_row('')

        title = '[b light_steel_blue]tests[/b light_steel_blue]'
        return Panel(grid, title=title, border_style="blue",
                     title_align='left', style='')


class InfoPanel:
    experiment: pd.DataFrame

    def __init__(self, experiment: pd.DataFrame):
        self.experiment = experiment

    def __rich__(self) -> Panel:
        grid = Table.grid(expand=True)
        grid.add_column(justify="left")

        grid.add_row(
            f'{pad_string_to_length("name", 8)}: {self.experiment["name"].values[0]}',
        )
        grid.add_row(
            f'{pad_string_to_length("ulid", 8)}: {self.experiment["ulid"].values[0]}',
        )
        grid.add_row(
            f'{pad_string_to_length("created", 8)}: {self.experiment["created_at"].values[0]}',
        )

        title = f'[b medium_turquoise]info[/b medium_turquoise]'
        return Panel(grid, title=title, border_style="blue", title_align="left")


class ExperimentPanel:
    experiment: pd.DataFrame
    abstract_tests: dict

    def __init__(self, experiment: pd.DataFrame, abstract_tests: dict):
        self.experiment = experiment
        self.abstract_tests = abstract_tests

    def __rich__(self) -> Panel:
        layout = Layout()
        layout.split(
            Layout(name="tags", size=1),
            Layout(name="data"),
        )
        layout["data"].split_row(
            Layout(name="info", ratio=1),
            Layout(name="tests", ratio=2)
        )
        info = InfoPanel(self.experiment)
        tests = TestsPanel(self.abstract_tests)
        layout["data"]["info"].update(info)
        layout["tags"].update(TagsText(self.experiment['tags'].values[0]))
        layout["data"]["tests"].update(tests)
        title = f'[b gold3]{self.experiment["name"].values[0]}[/b gold3]'
        return Panel(layout, title=title, border_style="blue", title_align="left")


def print_experiment(dotnotation: str = None, ulid: str = None, project_name: str = None, environment_name: str = None, experiment_name: str = None):
    with DataRetrievalApi() as db:
        console = DefaultConsole()
        if dotnotation:
            experiment = db.get_experiment_by_dotnotation(dotnotation)
        elif ulid:
            experiment = db.get_experiment(ulid=ulid)
        elif project_name and environment_name and experiment_name:
            experiment = db.get_experiment(project_name, environment_name, experiment_name)
        else:
            from adare.exceptions import ArgumentsError
            raise ArgumentsError(log, 'Either dotnotation, ulid, or project_name/environment_name/experiment_name must be provided')
        
        ulid = experiment['ulid'].values[0]
        abstract_tests = db.get_abstract_tests(ulid)
        layout = Layout(name="root")
        panel = ExperimentPanel(experiment, abstract_tests)
        layout.update(panel)
        console.print(layout)
