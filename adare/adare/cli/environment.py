from adare.backend.basics import determine_projectdirectory
from adare.exceptions import NoProjectFoundError

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
        raise NoProjectFoundError(log, message='project directory not found', possible_solutions=['use -p to specify the project directory', 'navigate to a project directory with cd'])
    environment_example(project_directory, arguments.environment)
    environment_load(project_directory, arguments.environment, force=False)


def exec_environment_create(arguments):
    from adare.backend.environment.commands import environment_create
    from pathlib import Path
    
    project_directory = determine_projectdirectory(arguments.project)
    if not project_directory:
        raise NoProjectFoundError(log, specified_project=getattr(arguments, 'project', None))
    
    # Handle --with-vm option
    vm_path = None
    if hasattr(arguments, 'with_vm') and arguments.with_vm:
        vm_path = Path(arguments.with_vm)
    
    environment_create(project_directory, arguments.name, vm_path=vm_path)


def exec_environment_delete(arguments):
    from adare.backend.environment.commands import environment_delete
    environment_delete(arguments.ulid, force=arguments.force)



