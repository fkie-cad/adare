# external imports
import pandas as pd

# internal imports
from adarelib.helperfunctions.cli import print_df, print_dict
from adare.database.api.dataframe import DataRetrievalApi

import logging
log = logging.getLogger(__name__)


def print_environment_list(project: str):
    with DataRetrievalApi() as api:
        environments_data: pd.DataFrame = api.get_environments_by_project(project)
    visible_columns = [
        'ulid',
        'name',
        'vagrantbox',
        'description',
    ]
    print_df(environments_data[visible_columns], 'Environments')


def print_environment_details(project: str, environment: str):
    with DataRetrievalApi() as api:
        environment_data: pd.DataFrame = api.get_environment_details(project, environment)
    print_df(environment_data, 'Environment Metadata')

