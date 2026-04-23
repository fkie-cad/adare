# external imports
# configure logging
import logging
from pathlib import Path

# internal imports
import adare.backend.project.database as project_database
from adare.backend.project.directory import ProjectDirectory
from adare.backend.project.exceptions import (
    NoProjectsFoundMessage,
    ProjectDirectoryCopyError,
    ProjectMissingInDatabaseError,
)
from adare.console import print_success_message
from adare.database.exceptions import DatabaseProjectCreationError
from adare.database.fixtures import fixture_stages, fixture_status

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

    # Initialize project database
    try:
        from adare.database.init import ensure_project_database_exists
        ensure_project_database_exists(path)
        log.info(f'project database initialized for {path}')
    except (OSError, ValueError) as e:
        project_directory.remove()
        project_database.remove_project(path)
        log.error(f'project directory {path} removed, since project database could not be initialized: {e}')
        raise e

    # Load stage and status fixtures for the project
    try:
        from adare.database.api.base import ProjectDatabaseApi
        with ProjectDatabaseApi(path) as project_api:
            fixture_status(project_api._session)
            fixture_stages(project_api._session)
        log.info(f'project fixtures loaded for {path}')
    except (OSError, ValueError) as e:
        project_directory.remove()
        project_database.remove_project(path)
        log.error(f'project directory {path} removed, since project fixtures could not be loaded: {e}')
        raise e

    # Testfunctions are now global - no need to copy to individual projects
    log.debug('Skipping testfunction copying - testfunctions are global resources')

    try:
        project_directory.copy_vm_runtime_files()
    except ProjectDirectoryCopyError as e:
        project_directory.remove()
        project_database.remove_project(path)
        log.info(f'project directory {path} removed, since vm runtime files could not be copied')
        raise e

    # Testfunctions are now global - they are loaded once and shared across all projects
    log.debug('Skipping testfunction loading - testfunctions are global resources')

    log.info(f'project in path {path} created')

    # Provide clear user feedback with loaded testfunction sets and next steps
    next_steps = [
        'Create an environment with: adare environment create <environment_name>',
        'Create an experiment with: adare experiment create <experiment_name>',
        'Use all available testfunction sets: files, json, csv, sqlite, linux, windows',
        'Run your first experiment with: adare experiment run <experiment> -e <environment>'
    ]

    print_success_message(
        title=f'Project "{name}" created successfully!',
        location=str(path),
        next_steps=next_steps,
        tip='All testfunction sets loaded with file operations, data validation (JSON, CSV, SQLite), system analysis (Linux, Windows), and forensic capabilities'
    )


def project_remove(path: Path):
    if not project_database.get_project_by_path(path):
        raise ProjectMissingInDatabaseError(log, message=f'project in path [i]{path}[/i] does not exist in database')

    project_directory = ProjectDirectory(path)

    # Remove directory if it exists, but don't fail if it's already gone
    if project_directory.exists():
        project_directory.remove()
    else:
        log.info(f'project directory [i]{path}[/i] already deleted, skipping directory removal')

    # Always clean up database entry regardless of directory state
    project_database.remove_project(path)


def project_list():
    projects = project_database.get_all_projects()
    if not projects:
        raise NoProjectsFoundMessage(log, message='no projects found')

    from adare.frontend.terminal.project_list import print_project_list
    print_project_list()


