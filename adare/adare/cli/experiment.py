# internal imports
from adare.backend.basics import determine_projectdirectory
from adare.exceptions import NoProjectFoundError


# configure logging
import logging
log = logging.getLogger(__name__)


def exec_experiment_load(arguments):
    from adare.backend.experiment.commands import experiment_load
    # if not arguments.environment:
    #     raise ArgumentsError(log, message='no environment given', possible_solutions=['use -e to specify the environment'])
    if project_directory := determine_projectdirectory(arguments.project):
        experiment_load(project_directory, arguments.experiment, force=arguments.force)
    else:
        raise NoProjectFoundError(log, message='no project directory found')


def exec_experiment_create(arguments):
    from adare.backend.experiment.commands import experiment_create
    if project_directory := determine_projectdirectory(arguments.project):
        experiment_create(project_directory, arguments.experiment)
    else:
        raise NoProjectFoundError(log, message='no project directory found')

def exec_experiment_example(arguments):
    from adare.backend.experiment.commands import experiment_example
    if project_directory := determine_projectdirectory(arguments.project):
        experiment_example(project_directory, arguments.experiment)
    else:
        raise NoProjectFoundError(log, message='no project directory found')


def exec_experiment_run(arguments):
    from adare.backend.experiment.commands import experiment_run, experiment_load

    disable_printing = False
    if arguments.verbose or arguments.very_verbose:
        disable_printing = True

    if project_directory := determine_projectdirectory(arguments.project):
        import asyncio
        try:
            experiment_load(project_directory, arguments.experiment, force=False)
            asyncio.run(experiment_run(project_directory, arguments.experiment, arguments.environment, disable_printing=disable_printing, test=arguments.test, debug_screenshots=arguments.debug_screenshots))
        except KeyboardInterrupt:
            log.info("Keyboard interrupt received, shutting down gracefully...")
    else:
        raise NoProjectFoundError(log, message='no project directory found')

def exec_experiment_test(arguments):
    from adare.backend.experiment.commands import experiment_test, experiment_load
    if project_directory := determine_projectdirectory(arguments.project):
        try:
            experiment_load(project_directory, arguments.experiment, force=False)
            experiment_test(project_directory, arguments.experiment, arguments.environment)
        except KeyboardInterrupt:
            log.info("Keyboard interrupt received, shutting down gracefully...")
    else:
        raise NoProjectFoundError(log, message='no project directory found')