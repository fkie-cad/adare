# external imports
import pandas as pd

# internal imports
from adarelib.helperfunctions.cli import print_df, print_dict
from adare.database.api.dataframe import DataRetrievalApi

import logging
log = logging.getLogger(__name__)


def print_project_list():
    with DataRetrievalApi() as api:
        projects_data: pd.DataFrame = api.get_projects()
    print_df(projects_data, 'Projects')


def print_project_details(project_name: str):
    with DataRetrievalApi() as api:
        df_project, df_environments, df_experiments = api.get_project_details(project_name)
    # only take name, path and description from environment and experiment
    df_environments = df_environments[['ulid', 'name', 'file', 'description']]
    df_experiments = df_experiments[['ulid', 'name', 'description']]

    # convert df_project to dict (since it has only one row)
    project_dict = df_project.to_dict('records')[0]

    print_dict(project_dict, 'Project Metadata')
    print_df(df_environments, 'Environments')
    print_df(df_experiments, 'Experiments')

