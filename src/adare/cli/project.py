# internal imports
from adare.backend.basics import determine_projectdirectory
from adare.backend.project import Project

# configure logging
import logging
log = logging.getLogger(__name__)


def project_create(arguments):
    """
    creates a new project

    :param arguments: arguments parsed via input
    """
    Project(arguments.directory, create=True)


def project_remove(arguments):
    """
    removes a project

    :param arguments: arguments parsed via input
    """
    project_directory = determine_projectdirectory(arguments.directory)
    project = Project(project_directory)
    project.remove()
