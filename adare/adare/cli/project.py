# external imports
from pathlib import Path

# internal imports
from adare.backend.basics import determine_projectdirectory
from adare.backend.project.commands import project_create, project_remove, project_add_tessdata, project_list

# configure logging
import logging
log = logging.getLogger(__name__)


def exec_create_project(arguments):
    """
    creates a new project

    :param arguments: arguments parsed via input
    """
    path = Path.cwd() / arguments.name
    description = arguments.description or ""
    project_create(path, path.name, description)


def exec_remove_project(arguments):
    """
    removes a project

    :param arguments: arguments parsed via input
    """
    path = determine_projectdirectory(arguments.name)
    if not path:
        log.error("no valid project directory provided")
        exit(1)
    if not path:
        log.error("no valid project directory provided")
        exit(1)
    project_remove(path)


def exec_download_tessdata(arguments):
    """
    downloads the tessdata for the given language

    :param arguments: arguments parsed via input
    """
    path = determine_projectdirectory(arguments.name)
    if not path:
        log.error("no valid project directory provided")
        exit(1)
    project_add_tessdata(path, arguments.language)


def exec_list_projects(arguments):
    """
    lists all projects

    :param arguments: arguments parsed via input
    """
    project_list()

