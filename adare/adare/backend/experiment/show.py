# external imports
import datetime
import pandas as pd
from rich.layout import Layout
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# internal imports
from adarelib.helperfunctions.cli import print_df, print_dict
from adare.database.api.dataframe import DataRetrievalApi
from adarelib.exceptions import ArgumentsError
from adarelib.config import TIMESTAMP_FORMAT

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
        raise ArgumentsError(log, message='either environment_ulid OR project and environment name must be provided', possible_solutions=[
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
        raise ArgumentsError(log, message='either experiment_ulid OR project, environment and experiment name must be provided', possible_solutions=[
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
    duration: datetime.timedelta
    start_time: str
    end_time: str

    def __init__(self, experiment_name: str, experiment_ulid: str, environment_ulid: str, environment_name: str, project_name: str, duration_in_seconds: int, start_time: str, end_time: str):
        self.experiment_name = experiment_name
        self.experiment_ulid = experiment_ulid
        self.environment_ulid = environment_ulid
        self.environment_name = environment_name
        self.project_name = project_name
        self.duration = datetime.timedelta(seconds=duration_in_seconds) if duration_in_seconds else None
        self.start_time = start_time
        self.end_time = end_time

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


def print_run_details(run_ulid: str):
    console = Console()
    # Get the size of the terminal
    terminal_size = console.size
    # Set the height as terminal height minus 10
    desired_height = terminal_size.height - 10 if terminal_size.height > 10 else 1
    console = Console(height=desired_height)

    with DataRetrievalApi() as api:
        data: pd.DataFrame = api.get_run_details(run_ulid)

        layout = Layout(name='root')
        header = Layout(name='header', size=5)
        body = Layout(name='body')
        metadata = Layout(name='flow', ratio=2)
        tests = Layout(name='tests', ratio=3)

        layout.split(
            header,
            body,
        )
        layout['body'].split_row(
            metadata,
            tests,
        )

        title = f'{data["experiment_name"].values[0]} - {run_ulid}'
        header.update(ExperimentRunHeader(
            experiment_name=data['experiment_name'].values[0],
            experiment_ulid=run_ulid,
            environment_name=data['environment_name'].values[0],
            environment_ulid=data['environment_id'].values[0],
            project_name=data['project_name'].values[0],
            duration_in_seconds=data['duration'].values[0],
            start_time=data['timestamp_start'].values[0],
            end_time=data['timestamp_end'].values[0]
        ))



        # table_metadata = Table()
        # table_metadata.add_column('key')
        # table_metadata.add_column('value')
        # table_metadata.add_row('ulid', df_run['ulid'].values[0])
        # table_metadata.add_row('experiment', df_run['experiment_name'].values[0])
        #
        # layout['body']['metadata'].update(Panel(table_metadata, title=df_run['ulid'].values[0]))
        console.print(layout)




