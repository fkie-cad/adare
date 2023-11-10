# internal imports
from adare.backend.basics import determine_projectdirectory
from adare.backend.project import Project

# configure logging
import logging
log = logging.getLogger(__name__)


def exec_create_project(arguments):
    """
    creates a new project

    :param arguments: arguments parsed via input
    """
    Project(arguments.directory, create=True)


def exec_remove_project(arguments):
    """
    removes a project

    :param arguments: arguments parsed via input
    """
    project_directory = determine_projectdirectory(arguments.directory)
    project = Project(project_directory)
    project.remove()
