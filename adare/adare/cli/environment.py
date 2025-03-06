from adare.backend.basics import determine_projectdirectory
from adarelib.exceptions import NoProjectFoundError

# configure logging
import logging
log = logging.getLogger(__name__)


def exec_environment_load(arguments):
    from adare.backend.environment.commands import environment_load
    project_directory = determine_projectdirectory(arguments.project)
    if not project_directory:
        raise NoProjectFoundError(log, message='project directory not found')
    environment_load(project_directory, arguments.environment, force=arguments.force)

def exec_environment_example(arguments):
    from adare.backend.environment.commands import environment_example, environment_load
    project_directory = determine_projectdirectory(arguments.project)
    if not project_directory:
        raise NoProjectFoundError(log, message='project directory not found')
    environment_example(project_directory, arguments.environment)
    environment_load(project_directory, arguments.environment, force=False)



def exec_environment_create(arguments):
    from adare.backend.environment.commands import environment_create
    project_directory = determine_projectdirectory(arguments.project)
    if not project_directory:
        raise NoProjectFoundError(log, message='project directory not found')
    environment_create(project_directory, arguments.name)


def exec_environment_delete(arguments):
    from adare.backend.environment.commands import environment_delete
    environment_delete(arguments.ulid, force=arguments.force)



