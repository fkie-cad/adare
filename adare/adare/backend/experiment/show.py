# external imports
import pandas as pd

# internal imports
from adarelib.helperfunctions.cli import print_df, print_dict
from adare.database.api.dataframe import DataRetrievalApi
from adarelib.exceptions import ArgumentsError

import logging
log = logging.getLogger(__name__)


def print_experiment_list(project: str = None, environment: str = None, environment_uuid: str = None):
    if not environment_uuid and not (project and environment):
        raise ArgumentsError(log, message='either environment_uuid OR project and environment name must be provided', possible_solutions=[
            'provide the environment_uuid (-env-id $ENVIRONMENT_UUID)',
            'provide the project and environment name (-proj $PROJECT -env $ENVIRONMENT)',
        ])
    with DataRetrievalApi() as api:
        if environment_uuid:
            experiment_data: pd.DataFrame = api.get_experiments_by_environmentuuid(environment_uuid)
        else:
            experiment_data: pd.DataFrame = api.get_experiments_by_projectenvironment(project, environment)
    visible_columns = [
        'uuid',
        'name',
        'description',
    ]
    print_df(experiment_data[visible_columns], 'Experiments')


def print_experiment_details(project: str, environment: str, experiment: str, experiment_uuid: str = None):
    if not experiment_uuid and not (project and environment and experiment):
        raise ArgumentsError(log, message='either experiment_uuid OR project, environment and experiment name must be provided', possible_solutions=[
            'provide the experiment_uuid (-exp-id $EXPERIMENT_UUID)',
            'provide the project, environment and experiment name (-proj $PROJECT -env $ENVIRONMENT -exp $EXPERIMENT)',
        ])

    with DataRetrievalApi() as api:
        if experiment_uuid:
            df_experiment = api.get_experiment_details_by_uuid(experiment_uuid)
        else:
            df_experiment = api.get_experiment_details(project, environment, experiment)

        runs = api.get_experiment_runs(df_experiment['uuid'].values[0])
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
        'uuid',
        'experiment_id',
        'environment_id',
        'status',
    ]
    print_df(run_data[visible_columns], 'Runs')


def print_run_details(run_uuid: str):
    with DataRetrievalApi() as api:
        df_run: pd.DataFrame = api.get_run_details(run_uuid)
    visible_columns = [
        'uuid',
        'experiment_id',
        'environment_id',
        'status',
    ]
    print_df(df_run[visible_columns], 'Run Details')


