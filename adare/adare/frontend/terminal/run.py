# external imports
import datetime
import pandas as pd
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table

# internal imports
from adare.database.api.frontend import DataRetrievalApi
from adare.frontend.terminal.console import pad_string_to_length, DefaultConsole, timedelta_to_str
from adare.config import TIMESTAMP_FORMAT, StatusEnum
from adare.frontend.terminal.console import TwoTitleRule
from rich.emoji import Emoji

import logging
log = logging.getLogger(__name__)


class ExperimentRunHeader:
    experiment_name: str
    experiment_ulid: str
    environment_name: str
    experiment_ulid: str
    project_name: str
    duration: str
    start_time: str
    end_time: str
    osinfo: str
    box: str
    published: bool

    def __init__(self, experiment_name: str, experiment_ulid: str, environment_ulid: str, environment_name: str,
                 project_name: str, duration: pd.Timedelta, start_time: str, end_time: str, box: str, osinfo: str, published: bool):
        self.experiment_name = experiment_name
        self.experiment_ulid = experiment_ulid
        self.environment_ulid = environment_ulid
        self.environment_name = environment_name
        self.project_name = project_name
        self.duration = f'{timedelta_to_str(duration)}' if duration else '...'
        self.start_time = start_time or '...'
        self.end_time = end_time or '...'
        self.box = box
        self.osinfo = osinfo
        self.published = published

    def __rich__(self) -> Panel:
        title = f'[b medium_turquoise]info[/b medium_turquoise]'
        grid = Table.grid(expand=True)
        grid.add_column(justify="left", ratio=1)
        grid.add_column(justify="right")
        grid.add_row(
            f"{pad_string_to_length('experiment', 11)}: [b]{self.experiment_name}[/b] ([i]{self.experiment_ulid}[/i])",
            f"start: {self.start_time}",
        )
        grid.add_row(
            f"{pad_string_to_length('environment', 11)}: [b]{self.environment_name}[/b] ([i]{self.environment_ulid}[/i])",
            f"end: {self.end_time}",
        )
        grid.add_row(
            f"{pad_string_to_length('project', 11)}: [b]{self.project_name}[/b]",
            f"duration: {self.duration}",
        )
        grid.add_row(
            f"{pad_string_to_length('osinfo', 11)}: [b]{self.osinfo}[/b]",
            f"box: {self.box}",
        )
        published_str = "published" if self.published else "not published"
        grid.add_row("", published_str)
        return Panel(grid, title=title, border_style="blue", title_align='left', style='')


class ExperimentRunTestsPanel:
    tests_data: dict
    test_overall_result: int

    def __init__(self, test_overall_result: int, tests_data: dict):
        self.tests_data = tests_data
        self.test_overall_result = test_overall_result

    def __rich__(self) -> Panel:
        grid = Table.grid(expand=True)
        grid.add_column(justify="left", ratio=1)

        for test_data in self.tests_data.values():
            color = StatusEnum.get_color(test_data['result_status'])
            grid.add_row(
                TwoTitleRule(
                    title=f'[b {color}]{test_data["name"]} ([i]{test_data["testfunction_name"]}[/i])[/b {color}]',
                    style=color,
                    align='around',
                    title_right=f'[b {color}]{test_data["result_status_name"]}[/b {color}]',
                ),
            )
            if test_data['result_details']:
                grid.add_row(':pencil: [b]details[/b]:')
                grid.add_row(f'  {test_data["result_details"]}')
            grid.add_row(':gear: [b]parameters[/b]:')
            for parameter in test_data['parameters']:
                grid.add_row(
                    f'  {parameter["name"]} ([i]{parameter["dtype"]}[/i]): [b]{parameter["value"]}[/b]'
                )

        title = '[b light_steel_blue]tests[/b light_steel_blue]'
        title = f'{title} {StatusEnum.get_icon(self.test_overall_result, color=True)}'
        return Panel(grid, title=title, border_style="blue",
                     title_align='left', style='')


class ExperimentRunFlowPanel:
    stages: pd.DataFrame
    status: int

    def __init__(self, status: int, stages: pd.DataFrame):
        self.stages = stages
        self.status = status

    @staticmethod
    def __generate_line(row: pd.Series) -> str:
        icon = StatusEnum.get_icon(row['status'], color=True)
        message = row['msg']
        if row['sub_msg']:
            message = f'{message}: {row["sub_msg"]}'
        level_offset = 2 * ' ' * row['level']
        line = f'{level_offset}{icon} {message}'
        if row['result_status'] != 'nan':
            line = f'{line} {StatusEnum.get_icon(row["result_status"], color=True)}'
        return line

    def __rich__(self) -> Panel:
        grid = Table.grid(expand=True)
        grid.add_column(justify="left", ratio=1)
        # iterate over the rows of the stages dataframe
        for index, row in self.stages.iterrows():
            grid.add_row(
                self.__generate_line(row)
            )
        grid.add_row('')
        title = '[b honeydew2]flow[/b honeydew2]'
        title = f'{title} {StatusEnum.get_icon(self.status, color=True)}'
        return Panel(grid, title=title, border_style="blue", title_align='left', style='')

# from textual.widget import Widget
# from textual.geometry import Size
# from textual.app import RenderResult
#
# class ExperimentRunFlowWidget(Widget):
#     stages: pd.DataFrame
#
#     def __init__(self, stages: pd.DataFrame, *children: Widget):
#         super().__init__(*children)
#         self.stages = stages
#
#     @staticmethod
#     def __generate_line(row: pd.Series) -> str:
#         from rich.text import Text
#         icon = StatusEnum.get_icon(row['status'], color=True)
#         message = row['msg']
#         if row['sub_msg']:
#             message = f"{message}: {row['sub_msg']}"
#         level_offset = 2 * ' ' * row['level']
#         line = f"{level_offset}{icon} {message}"
#         if row['result_status'] != 'nan':
#             line = f"{line} {StatusEnum.get_icon(row['result_status'], color=True)}"
#         return line
#
#     def render(self) -> RenderResult:
#         grid = Table.grid(expand=True)
#         grid.add_column(justify="left", ratio=1)
#         for index, row in self.stages.iterrows():
#             grid.add_row(self.__generate_line(row))
#         grid.add_row('')  # extra row if needed
#         return grid
#
#     def get_content_height(self, container: Size, viewport: Size, width: int) -> int:
#         # Return height based on number of rows in the dataframe plus one extra line.
#         return len(self.stages.index) + 1


def print_run(run_ulid: str):
    console = DefaultConsole()

    with DataRetrievalApi() as api:
        data: pd.DataFrame = api.get_run(run_ulid)
        stages: pd.DataFrame = api.get_run_stages(run_ulid)
        tests_data: dict = api.get_tests(run_ulid)

        layout = Layout(name='root')
        header = Layout(name='header', size=7)
        body = Layout(name='body')
        flow = Layout(name='flow', ratio=2)
        tests = Layout(name='tests', ratio=3)

        layout.split(
            header,
            body,
        )
        layout['body'].split_row(
            flow,
            tests,
        )

        project_name = data['project_name'].values[0]
        environment_name = data['environment_name'].values[0]
        experiment_name = data['experiment_name'].values[0]
        experiment_ulid = run_ulid
        header.update(ExperimentRunHeader(
            experiment_name=experiment_name,
            experiment_ulid=run_ulid,
            environment_name=environment_name,
            environment_ulid=data['environment_id'].values[0],
            project_name=project_name,
            duration=data['duration'][0],
            start_time=data['timestamp_start'].values[0],
            end_time=data['timestamp_end'].values[0],
            box=data['box'].values[0],
            osinfo=data['osinfo'].values[0],
            published=data['published'].values[0],
        ))

        title = f'[b gold3]{project_name}.{environment_name}.{experiment_name} - [i]{experiment_ulid}[/i][/b gold3]'
        panel = Panel(layout, title=title, border_style='blue', title_align='left')

        tests.update(ExperimentRunTestsPanel(data['result_status'].values[0], tests_data))
        flow.update(ExperimentRunFlowPanel(data['status'].values[0], stages))

        console.print(panel)

