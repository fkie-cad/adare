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


async def exec_experiment_run_all_environments(project_directory, arguments, disable_printing):
    """Run experiment across all environments in the project and provide a summary."""
    from adare.backend.experiment.commands import experiment_run, experiment_load
    from adare.database.api.environment import EnvironmentDbApi
    from adare.exceptions import LoggedErrorException
    from datetime import datetime, timezone

    # Get all environments for the project
    with EnvironmentDbApi() as db:
        environments = db.get_environments(project_directory)

    if not environments:
        raise LoggedErrorException(log,
            f'No environments found in project "{project_directory.name}". '
            'Please create at least one environment before running experiments.',
            possible_solutions=[
                'Create an environment with: adare environment create <name>',
                'Load an existing environment with: adare environment load <file>',
                'Check if you are in the correct project directory'
            ]
        )

    # Load experiment once before running on all environments
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
        experiment_load(project_directory, arguments.experiment, force=True, silent=True)
    else:
        experiment_load(project_directory, arguments.experiment, force=False, silent=True)

    print(f"Running experiment '{arguments.experiment}' on {len(environments)} environment(s)...")
    print(f"Environments: {', '.join([env.name for env in environments])}")
    print()

    # Track results
    results = []
    start_time = datetime.now(timezone.utc)

    # Run experiment on each environment
    for i, environment in enumerate(environments, 1):
        env_name = environment.name
        print(f"[{i}/{len(environments)}] Running on environment: {env_name}")

        env_start_time = datetime.now(timezone.utc)

        try:
            await experiment_run(
                project_directory,
                arguments.experiment,
                env_name,
                disable_printing=disable_printing,
                test=arguments.test,
                debug_screenshots=arguments.debug_screenshots,
                preserve_snapshot=arguments.preserve_snapshot,
                runlog=arguments.runlog,
                vm_memory=arguments.vm_memory,
                vm_cpus=arguments.vm_cpus
            )

            env_end_time = datetime.now(timezone.utc)
            duration = (env_end_time - env_start_time).total_seconds()
            results.append({
                'environment': env_name,
                'status': 'SUCCESS',
                'duration': duration,
                'error': None
            })

            print(f"✅ Environment '{env_name}' completed successfully ({duration:.1f}s)")

        except Exception as e:
            env_end_time = datetime.now(timezone.utc)
            duration = (env_end_time - env_start_time).total_seconds()
            error_msg = str(e)

            results.append({
                'environment': env_name,
                'status': 'FAILED',
                'duration': duration,
                'error': error_msg
            })

            print(f"❌ Environment '{env_name}' failed ({duration:.1f}s): {error_msg}")

        print()  # Add spacing between environments

    # Print summary
    end_time = datetime.now(timezone.utc)
    total_duration = (end_time - start_time).total_seconds()

    successful_runs = [r for r in results if r['status'] == 'SUCCESS']
    failed_runs = [r for r in results if r['status'] == 'FAILED']

    print("=" * 60)
    print(f"EXPERIMENT SUMMARY: {arguments.experiment}")
    print("=" * 60)
    print(f"Total environments: {len(environments)}")
    print(f"Successful runs: {len(successful_runs)}")
    print(f"Failed runs: {len(failed_runs)}")
    print(f"Total duration: {total_duration:.1f}s")
    print()

    if successful_runs:
        print("✅ SUCCESSFUL ENVIRONMENTS:")
        for result in successful_runs:
            print(f"  - {result['environment']} ({result['duration']:.1f}s)")
        print()

    if failed_runs:
        print("❌ FAILED ENVIRONMENTS:")
        for result in failed_runs:
            print(f"  - {result['environment']} ({result['duration']:.1f}s): {result['error']}")
        print()

    # Exit with appropriate code
    if failed_runs:
        if len(successful_runs) == 0:
            raise LoggedErrorException(log,
                f"All {len(environments)} environment runs failed. See details above.")
        else:
            print(f"⚠️  {len(failed_runs)} out of {len(environments)} environments failed.")
            print(f"✅ {len(successful_runs)} environments completed successfully.")


def exec_experiment_run(arguments):
    from adare.backend.experiment.commands import experiment_run, experiment_load
    from adare.exceptions import LoggedException, LoggedErrorException
    import sys

    disable_printing = False
    if arguments.verbose or arguments.very_verbose:
        disable_printing = True

    if project_directory := determine_projectdirectory(arguments.project):
        import asyncio

        # If no environment specified, run on all environments
        if not arguments.environment:
            try:
                asyncio.run(exec_experiment_run_all_environments(
                    project_directory, arguments, disable_printing
                ))
            except LoggedException as e:
                e.print()
                if isinstance(e, LoggedErrorException):
                    sys.exit(-1)
                else:
                    sys.exit(0)
            except KeyboardInterrupt:
                log.info("Keyboard interrupt received, shutting down gracefully...")
            return

        # Single environment run (existing logic)
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