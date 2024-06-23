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
from adare.database.api.dataframe import DataRetrievalApi
from adarelib.exceptions import ArgumentsError
from adarelib.config import TIMESTAMP_FORMAT, StatusEnum

import logging

log = logging.getLogger(__name__)


def pad_string_to_length(string: str, length: int, right: bool = True) -> str:
    if len(string) > length:
        return string
    if right:
        return string + ' ' * (length - len(string))
    return ' ' * (length - len(string)) + string


def print_experiment_list(project: str = None, environment: str = None, environment_ulid: str = None):
    if not environment_ulid and not (project and environment):
        raise ArgumentsError(log, message='either environment_ulid OR project and environment name must be provided',
                             possible_solutions=[
                                 'provide the environment_ulid (-env-id $ENVIRONMENT_ulid)',
                                 'provide the project and environment name (-proj $PROJECT -env $ENVIRONMENT)',
                             ])
    with DataRetrievalApi() as api:
        if environment_ulid:
            experiment_data: pd.DataFrame = api.get_experiments_by_environmentulid(environment_ulid)
        else:
            experiment_data: pd.DataFrame = api.get_experiments_by_projectenvironment(project, environment)
    visible_columns = [
        'ulid',
        'name',
        'description',
    ]
    print_df(experiment_data[visible_columns], 'Experiments')


def print_experiment_details(project: str, environment: str, experiment: str, experiment_ulid: str = None):
    if not experiment_ulid and not (project and environment and experiment):
        raise ArgumentsError(log,
                             message='either experiment_ulid OR project, environment and experiment name must be provided',
                             possible_solutions=[
                                 'provide the experiment_ulid (-exp-id $EXPERIMENT_ulid)',
                                 'provide the project, environment and experiment name (-proj $PROJECT -env $ENVIRONMENT -exp $EXPERIMENT)',
                             ])

    with DataRetrievalApi() as api:
        if experiment_ulid:
            df_experiment = api.get_experiment_details_by_ulid(experiment_ulid)
        else:
            df_experiment = api.get_experiment_details(project, environment, experiment)

        runs = api.get_experiment_runs(df_experiment['ulid'].values[0])
        run_columns = [
            col for col in runs.columns if col not in ['experiment_id', 'environment_id']
        ]

    print_dict(
        df_experiment.to_dict(orient='records')[0],
        'Experiment Details'
    )
    print_df(runs[run_columns], 'Experiment Runs')


def print_run_list():
    with DataRetrievalApi() as api:
        run_data: pd.DataFrame = api.get_runs()
    visible_columns = [
        'ulid',
        'experiment_id',
        'environment_id',
        'status',
    ]
    print_df(run_data[visible_columns], 'Runs')


class ExperimentRunHeader:
    experiment_name: str
    experiment_ulid: str
    environment_name: str
    experiment_ulid: str
    project_name: str
    duration: str
    start_time: str
    end_time: str

    def __init__(self, experiment_name: str, experiment_ulid: str, environment_ulid: str, environment_name: str,
                 project_name: str, duration: np.timedelta64, start_time: str, end_time: str):
        self.experiment_name = experiment_name
        self.experiment_ulid = experiment_ulid
        self.environment_ulid = environment_ulid
        self.environment_name = environment_name
        self.project_name = project_name
        if not duration:
            self.duration = '...'
        else:
            duration_datetime: datetime.timedelta = duration.item()
            self.duration = f'{str(duration_datetime)}'
        self.start_time = start_time or '...'
        self.end_time = end_time or '...'

    def __rich__(self) -> Panel:
        title = f'[b gold3]{self.project_name}.{self.environment_name}.{self.experiment_name} - [i]{self.experiment_ulid}[/i][/b gold3]'
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
        return Panel(grid, title=title, border_style="blue", title_align='left', style='')


class CustomRule(Rule):
    title_right: str
    align: str

    def __init__(self, title: str, style: str, align: str, title_right: str = ''):
        super().__init__(title=title, style=style)
        self.title_right = title_right
        self.align = align

    def __rich_console__(
            self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        width = options.max_width

        characters = (
            "-"
            if (options.ascii_only and not self.characters.isascii())
            else self.characters
        )

        chars_len = cell_len(characters)
        if not self.title:
            yield self._rule_line(chars_len, width)
            return

        if isinstance(self.title, Text):
            title_text = self.title
        else:
            title_text = console.render_str(self.title, style="rule.text")

        if isinstance(self.title_right, Text):
            title_right_text = self.title_right
        else:
            title_right_text = console.render_str(self.title_right, style="rule.text")

        title_text.plain = title_text.plain.replace("\n", " ")
        title_text.expand_tabs()

        title_right_text.plain = title_right_text.plain.replace("\n", " ")
        title_right_text.expand_tabs()

        required_space = 4 if self.align == "center" else 2
        truncate_width = max(0, width - required_space)
        if not truncate_width:
            yield self._rule_line(chars_len, width)
            return

        rule_text = Text(end=self.end)
        if self.align == "center":
            title_text.truncate(truncate_width, overflow="ellipsis")
            side_width = (width - cell_len(title_text.plain)) // 2
            left = Text(characters * (side_width // chars_len + 1))
            left.truncate(side_width - 1)
            right_length = width - cell_len(left.plain) - cell_len(title_text.plain)
            right = Text(characters * (side_width // chars_len + 1))
            right.truncate(right_length)
            rule_text.append(left.plain + " ", self.style)
            rule_text.append(title_text)
            rule_text.append(" " + right.plain, self.style)
        elif self.align == "left":
            title_text.truncate(truncate_width, overflow="ellipsis")
            rule_text.append(title_text)
            rule_text.append(" ")
            rule_text.append(characters * (width - rule_text.cell_len), self.style)
        elif self.align == "right":
            title_text.truncate(truncate_width, overflow="ellipsis")
            rule_text.append(characters * (width - title_text.cell_len - 1), self.style)
            rule_text.append(" ")
            rule_text.append(title_text)
        elif self.align == "around":
            # place title_text on the left and title_right_text on the right
            title_text.truncate(truncate_width, overflow="ellipsis")
            title_right_text.truncate(truncate_width, overflow="ellipsis")
            rule_text.append(title_text)
            rule_text.append(" ")
            rule_text.append(characters * (width - title_text.cell_len - title_right_text.cell_len - 2), self.style)
            rule_text.append(" ")
            rule_text.append(title_right_text)

        rule_text.plain = set_cell_size(rule_text.plain, width)
        yield rule_text

    def _rule_line(self, chars_len: int, width: int) -> Text:
        rule_text = Text(self.characters * ((width // chars_len) + 1), self.style)
        rule_text.truncate(width)
        rule_text.plain = set_cell_size(rule_text.plain, width)
        return rule_text

    def __rich_measure__(
            self, console: Console, options: ConsoleOptions
    ) -> Measurement:
        return Measurement(1, 1)


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
                CustomRule(
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


def print_run_details(run_ulid: str):
    console = Console()
    # Get the size of the terminal
    terminal_size = console.size
    # Set the height as terminal height minus 10
    desired_height = terminal_size.height - 10 if terminal_size.height > 10 else 1
    console = Console(height=desired_height)

    with DataRetrievalApi() as api:
        data: pd.DataFrame = api.get_run_details(run_ulid)
        stages: pd.DataFrame = api.get_run_stages(run_ulid)
        tests_data: dict = api.get_tests(run_ulid)

        layout = Layout(name='root')
        header = Layout(name='header', size=5)
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

        header.update(ExperimentRunHeader(
            experiment_name=data['experiment_name'].values[0],
            experiment_ulid=run_ulid,
            environment_name=data['environment_name'].values[0],
            environment_ulid=data['environment_id'].values[0],
            project_name=data['project_name'].values[0],
            duration=data['duration'].values[0],
            start_time=data['timestamp_start'].values[0],
            end_time=data['timestamp_end'].values[0]
        ))

        tests.update(ExperimentRunTestsPanel(data['result_status'].values[0], tests_data))
        flow.update(ExperimentRunFlowPanel(data['status'].values[0], stages))

        # table_metadata = Table()
        # table_metadata.add_column('key')
        # table_metadata.add_column('value')
        # table_metadata.add_row('ulid', df_run['ulid'].values[0])
        # table_metadata.add_row('experiment', df_run['experiment_name'].values[0])
        #
        # layout['body']['metadata'].update(Panel(table_metadata, title=df_run['ulid'].values[0]))
        console.print(layout)
