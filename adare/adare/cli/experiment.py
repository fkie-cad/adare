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
    from adare.exceptions import LoggedException, LoggedErrorException
    import sys

    disable_printing = False
    if arguments.verbose or arguments.very_verbose:
        disable_printing = True

    if project_directory := determine_projectdirectory(arguments.project):
        import asyncio
        try:
            # In test mode, check for existing runs before allowing force update
            if arguments.test:
                from adare.backend.experiment import database as experiment_database
                experiment_ulid = experiment_database.get_experiment_by_project_and_name(
                    project_directory, arguments.experiment, trigger_error=False
                )
                if experiment_ulid:
                    run_count = experiment_database.get_experiment_run_count(experiment_ulid)
                    if run_count > 0:
                        raise LoggedErrorException(log, 
                            f'Cannot run test mode on experiment "{arguments.experiment}" with existing runs ({run_count} runs found).\n'
                            f'Test mode with file modifications could overwrite real experiment data.\n'
                            f'Use a different experiment name for testing or remove existing runs first.',
                            possible_solutions=[
                                f'Create a new experiment: adare experiment create {arguments.experiment}_test',
                                f'Remove existing runs (if safe): adare run list --filter {arguments.experiment}',
                                'Use --force flag only if you understand the risks'
                            ]
                        )
                # Allow force loading in test mode to handle file changes during development
                experiment_load(project_directory, arguments.experiment, force=True, silent=True)
            else:
                # Normal mode - no force loading
                experiment_load(project_directory, arguments.experiment, force=False, silent=True)
                
            asyncio.run(experiment_run(project_directory, arguments.experiment, arguments.environment, disable_printing=disable_printing, test=arguments.test, debug_screenshots=arguments.debug_screenshots, preserve_snapshot=arguments.preserve_snapshot, runlog=arguments.runlog, vm_memory=arguments.vm_memory, vm_cpus=arguments.vm_cpus))
        except LoggedException as e:
            e.print()
            if isinstance(e, LoggedErrorException):
                sys.exit(-1)
            else:
                sys.exit(0)
        except KeyboardInterrupt:
            log.info("Keyboard interrupt received, shutting down gracefully...")
    else:
        raise NoProjectFoundError(log, message='no project directory found')

def exec_experiment_test(arguments):
    from adare.backend.experiment.commands import experiment_test, experiment_load
    from adare.exceptions import LoggedException, LoggedErrorException
    import sys

    if project_directory := determine_projectdirectory(arguments.project):
        try:
            experiment_load(project_directory, arguments.experiment, force=False, silent=True)
            experiment_test(project_directory, arguments.experiment, arguments.environment)
        except LoggedException as e:
            e.print()
            if isinstance(e, LoggedErrorException):
                sys.exit(-1)
            else:
                sys.exit(0)
        except KeyboardInterrupt:
            log.info("Keyboard interrupt received, shutting down gracefully...")
    else:
        raise NoProjectFoundError(log, message='no project directory found')


def exec_experiment_clean(arguments):
    """Execute experiment clean command to remove fake runs."""
    from adare.backend.experiment.commands import experiment_clean
    from adare.exceptions import LoggedException, LoggedErrorException
    import sys

    if project_directory := determine_projectdirectory(arguments.project):
        try:
            experiment_clean(project_directory, arguments.experiment)
        except LoggedException as e:
            e.print()
            if isinstance(e, LoggedErrorException):
                sys.exit(-1)
            else:
                sys.exit(0)
    else:
        raise NoProjectFoundError(log, message='no project directory found')