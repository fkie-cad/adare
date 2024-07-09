# internal imports
from adare.backend.basics import determine_projectdirectory
from adare.backend.experiment.commands import experiment_create, experiment_load, experiment_run
from adarelib.exceptions import NoProjectFoundError, ArgumentsError
from adarelib.breakpoint import BREAKPOINTS
from adarelib.breakpoint import resolve_breakpoints

# configure logging
import logging
log = logging.getLogger(__name__)


def exec_experiment_load(arguments):
    if not arguments.environment:
        raise ArgumentsError(log, message='no environment given', possible_solutions=['use -e to specify the environment'])
    if project_directory := determine_projectdirectory(arguments.project):
        experiment_load(project_directory, arguments.environment, arguments.experiment, force=arguments.force)
    else:
        raise NoProjectFoundError(log, message='no project directory found')


def exec_experiment_create(arguments):
    if project_directory := determine_projectdirectory(arguments.project):
        experiment_create(project_directory, arguments.experiment)
    else:
        raise NoProjectFoundError(log, message='no project directory found')


def exec_experiment_run(arguments):
    if arguments.debug:
        breakpoints = BREAKPOINTS
    else:
        breakpoints = resolve_breakpoints(arguments.breakpoints)

    if project_directory := determine_projectdirectory(arguments.project):
        experiment_run(project_directory, arguments.experiment, arguments.environment, breakpoints)
    else:
        raise NoProjectFoundError(log, message='no project directory found')
