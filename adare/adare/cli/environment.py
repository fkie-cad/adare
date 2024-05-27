from adare.backend.basics import determine_projectdirectory
from adare.backend.environment.commands import environment_load, environment_create, environment_delete
from adarelib.exceptions import NoProjectFoundError

# configure logging
import logging
log = logging.getLogger(__name__)


def exec_environment_load(arguments):
    project_directory = determine_projectdirectory(arguments.project)
    if not project_directory:
        raise NoProjectFoundError(log, message='project directory not found')
    environment_load(project_directory, arguments.environment, force=arguments.force)


def exec_environment_create(arguments):
    project_directory = determine_projectdirectory(arguments.project)
    if not project_directory:
        raise NoProjectFoundError(log, message='project directory not found')
    environment_create(project_directory, arguments.name)


def exec_environment_delete(arguments):
    environment_delete(arguments.uuid, force=arguments.force)



