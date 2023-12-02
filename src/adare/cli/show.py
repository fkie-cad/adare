# external imports
import pandas as pd
from pathlib import Path
import rich

# internal imports
from adare.backend.basics import determine_projectdirectory
from adare.backend.project import Project
from adare.helperFunctions.cli import print_df, print_dict
from adare.database.api.project import ProjectManagementApi
from adare.backend.environment import Environment

import logging
log = logging.getLogger(__name__)




def exec_show_project(arguments):
    """
    shows the information about projects

    :param arguments: arguments parsed via input
    """
    with ProjectManagementApi() as api:
        projects = api.get_projects()
        columns = ['name', 'path', 'description']
        projects_data = [[project.name, project.path, project.description] for project in projects]
    df_projects = pd.DataFrame(projects_data, columns=columns)
    print_df(df_projects, 'Projects')


def exec_show_env(arguments):
    """
    shows the information about environments of a given project

    :param arguments: arguments parsed via input
    """
    show_details = False
    if arguments.details:
        show_details = True

    project_path = determine_projectdirectory(arguments.project)

    with ProjectManagementApi() as api:
        project = api.get_project_by_path(project_path)

        # update experiments for all environments
        if project:
            for env in project.environments:
                Environment(env.name, Path(project.path))

            columns = ['name', 'description', 'path', 'experiments']
            env_data = []
            if project.environments:
                for env in project.environments:
                    env_data.append([env.name, env.description, env.path, "\n".join([exp.name for exp in env.experiments])])
            df_env = pd.DataFrame(env_data, columns=columns)

            if not show_details:
                df_env = df_env.drop(columns=['experiments'])

            print_df(df_env, f'Environments (project {project.name})')
        else:
            if arguments.project:
                print(f'Project {arguments.project} not found.')
            else:
                print(f'Project in cwd ({Path().cwd()}) not found.')


def exec_show_experiment(arguments):
    """
    shows the information about a specific experiment

    :param arguments: arguments parsed via input
    """
    project_path = determine_projectdirectory(arguments.project)
    if not project_path:
        print(f'Project {arguments.project} not found.')
        exit(-1)
    project_name = Path(project_path).name

    with ProjectManagementApi() as db:
        exp = db.get_experiment_in_env(project_name=project_name, env_name=arguments.environment, experiment_name=arguments.experiment)
        if not exp:
            print(f'Experiment {arguments.experiment} not found.')
            exit(-1)
        else:
            # print metadata such as name, description and run count in a rich table
            metadata = {
                'name': exp.name,
                'description': exp.description,
                'run count': len(exp.runs)
            }
            print_dict(metadata, 'Experiment Metadata')


def exec_show_runs(arguments):
    """
    shows the information about experiment runs of a given project

    :param arguments: arguments parsed via input
    """
    project_path = determine_projectdirectory(arguments.project)
    if not project_path:
        print(f'Project {arguments.project} not found.')
        exit(-1)
    project_name = Path(project_path).name

    with ProjectManagementApi() as db:
        runs = db.get_experiment_runs(project_name=project_name, env_name=arguments.environment, experiment_name=arguments.experiment)
        if not runs:
            print(f'No runs found.')
            exit(-1)
        else:
            # print metadata such as name, description and run count in a rich table
            columns = ['uuid', 'experiment',  'status', 'published']
            run_data = [[run.uuid, run.experiment.name, run.status.name, run.publish_status.name] for run in runs]
            df_runs = pd.DataFrame(run_data, columns=columns)
            print_df(df_runs, 'Runs')


def exec_show_run_result(arguments):
    """
    shows the information about experiment run results of a given project
    :param arguments:
    :return:
    """
    raise NotImplementedError