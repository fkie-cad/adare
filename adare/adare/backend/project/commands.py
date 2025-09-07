# external imports
from pathlib import Path
import pandas as pd

# internal imports
import adare.backend.project.database as project_database
from adare.backend.project.directory import ProjectDirectory
from adare.helperfunctions.cli import print_df
from adare.backend.project.exceptions import ProjectDirectoryCreationError, ProjectDirectoryRemovalError, \
    ProjectDirectoryCopyError, ProjectDirectoryMissingError, ProjectMissingInDatabaseError, NoProjectsFoundMessage
from adare.database.exceptions import DatabaseProjectCreationError

# configure logging
import logging
log = logging.getLogger(__name__)


def project_create(path: Path, name: str, description: str = ''):
    project_directory = ProjectDirectory(path)

    project_directory.create()

    try:
        project_database.add_project(name, description, path)
    except DatabaseProjectCreationError as e:
        project_directory.remove()
        log.info(f'project directory {path} removed, since project could not be added to database')
        raise e

    try:
        project_directory.copy_standard_testfunction()
    except ProjectDirectoryCopyError as e:
        project_directory.remove()
        project_database.remove_project(path)
        log.info(f'project directory {path} removed, since standard testfunction could not be copied')
        raise e

    log.info(f'project in path {path} created')


def project_remove(path: Path):
    if not project_database.get_project_by_path(path):
        raise ProjectMissingInDatabaseError(log, message=f'project in path [i]{path}[/i] does not exist in database')

    project_directory = ProjectDirectory(path)
    if not project_directory.exists():
        raise ProjectDirectoryMissingError(log, message=f'project directory [i]{path}[/i] does not exist')

    project_directory.remove()

    project_database.remove_project(path)


def project_list():
    projects = project_database.get_all_projects()
    if not projects:
        raise NoProjectsFoundMessage(log, message='no projects found')

    columns = ['name', 'path', 'description', 'environments']
    projects_data = [(project.name, project.path, project.description, "\n".join([env.name for env in project.environments])) for project in projects]
    df_env = pd.DataFrame(projects_data, columns=columns)
    print_df(df_env, 'Projects:')
