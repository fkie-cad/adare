# external imports
from pathlib import Path

# internal imports
from adare.backend.basics import determine_projectdirectory, determine_projectdirectory_for_removal

# configure logging
import logging
log = logging.getLogger(__name__)


def exec_create_project(arguments):
    """
    creates a new project

    :param arguments: arguments parsed via input
    """
    from adare.backend.project.commands import project_create
    path = Path.cwd() / arguments.name
    description = arguments.description or ""
    project_create(path, path.name, description)


def exec_remove_project(arguments):
    """
    removes a project

    :param arguments: arguments parsed via input
    """
    from adare.backend.project.commands import project_remove
    path = determine_projectdirectory_for_removal(arguments.name)
    if not path:
        log.error("no valid project found in database")
        exit(1)
    project_remove(path)




def exec_list_projects(arguments):
    from adare.backend.project.commands import project_list
    """
    lists all projects

    :param arguments: arguments parsed via input
    """
    project_list()

