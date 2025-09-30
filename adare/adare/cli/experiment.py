# internal imports
from adare.backend.basics import determine_projectdirectory
from adare.exceptions import NoProjectFoundError
from adare.helperfunctions.path_resolution import resolve_experiment_path, resolve_environment_path


# configure logging
import logging
log = logging.getLogger(__name__)


def exec_experiment_load(arguments):
    from adare.backend.experiment.commands import experiment_load
    from adare.backend.project.directory import ProjectDirectory
    import shutil
    from pathlib import Path

    # if not arguments.environment:
    #     raise ArgumentsError(log, message='no environment given', possible_solutions=['use -e to specify the environment'])
    if project_directory := determine_projectdirectory(arguments.project):
        # Track if we copied an external experiment for cleanup on failure
        original_input = arguments.experiment
        project_dir_obj = ProjectDirectory(project_directory)

        # Determine if this might result in copying an external experiment
        might_copy_external = False
        potential_copied_name = None
        if ('/' in original_input or '\\' in original_input):
            input_path = Path(original_input)
            if input_path.is_absolute() or not (Path.cwd() / input_path).is_relative_to(project_dir_obj.experiments):
                # This is an external path that might get copied
                if input_path.exists() and input_path.is_dir():
                    might_copy_external = True
                    potential_copied_name = input_path.name

        try:
            experiment_name = resolve_experiment_path(arguments.experiment, project_directory)
            experiment_load(project_directory, experiment_name, force=arguments.force)
        except Exception as e:
            # If we might have copied an external experiment and loading failed, try to clean it up
            if might_copy_external and potential_copied_name:
                copied_experiment_path = project_dir_obj.experiments / potential_copied_name
                if copied_experiment_path.exists():
                    try:
                        shutil.rmtree(copied_experiment_path)
                        log.info(f'CLAUDE: Cleaned up copied experiment {copied_experiment_path} after load failure')
                    except OSError as cleanup_error:
                        log.warning(f'CLAUDE: Failed to clean up copied experiment {copied_experiment_path}: {cleanup_error}')
            raise
    else:
        raise NoProjectFoundError(log, message='no project directory found')


def exec_experiment_create(arguments):
    from adare.backend.experiment.commands import experiment_create
    if project_directory := determine_projectdirectory(arguments.project):
        experiment_name = resolve_experiment_path(arguments.experiment, project_directory)
        experiment_create(project_directory, experiment_name)
    else:
        raise NoProjectFoundError(log, message='no project directory found')

def exec_experiment_example(arguments):
    from adare.backend.experiment.commands import experiment_example
    if project_directory := determine_projectdirectory(arguments.project):
        experiment_name = resolve_experiment_path(arguments.experiment, project_directory)
        experiment_example(project_directory, experiment_name)
    else:
        raise NoProjectFoundError(log, message='no project directory found')


def _handle_environment_interruption(environments, current_index, results):
    """
    Handle interruption logic and prompt user whether to continue with remaining environments.

    Returns:
        bool: True if user wants to continue, False if user wants to stop
    """
    remaining_envs = environments[current_index:]
    if not remaining_envs:
        return False  # No remaining environments

    print(f"\n{len(remaining_envs)} environment(s) remaining: {', '.join([env.name for env in remaining_envs])}")
    while True:
        choice = input("Continue with remaining environments? [y/n] (y=yes, n=no): ").lower().strip()
        if choice in ['y', 'yes']:
            print("Continuing with next environment...\n")
            return True
        elif choice in ['n', 'no']:
            print("Terminating all remaining environments...\n")
            # Mark remaining environments as skipped
            for remaining_env in remaining_envs:
                results.append({
                    'environment': remaining_env.name,
                    'status': 'SKIPPED',
                    'duration': 0,
                    'error': 'Skipped due to user termination'
                })
            return False
        else:
            print("Please enter 'y' (yes) or 'n' (no)")


async def exec_experiment_run_all_environments(project_directory, arguments, disable_printing):
    """Run experiment across all environments supported by the experiment and provide a summary."""
    from adare.backend.experiment.commands import experiment_load
    from adare.backend.experiment.run import experiment_run
    from adare.database.api.experiment import ExperimentApi
    from adare.exceptions import LoggedErrorException
    from datetime import datetime, timezone

    # Resolve experiment path to name
    experiment_name = resolve_experiment_path(arguments.experiment, project_directory)

    # Get environments supported by the experiment (from experiment's metadata.yml)
    with ExperimentApi(project_directory) as api:
        experiment = api.get_experiment_by_project_and_name(project_directory, experiment_name)
        if not experiment:
            raise LoggedErrorException(log,
                f'Experiment "{experiment_name}" not found in project "{project_directory.name}". '
                'Please load the experiment first.',
                possible_solutions=[
                    f'Load the experiment with: adare experiment load {experiment_name}',
                    'Check if you are in the correct project directory',
                    'List available experiments with: adare experiment list'
                ]
            )
        environments = experiment.environments

    if not environments:
        raise LoggedErrorException(log,
            f'No environments configured for experiment "{experiment_name}". '
            'The experiment metadata.yml has no environments specified.',
            possible_solutions=[
                f'Add environments to experiment with: adare experiment add-env {experiment_name} <env_name>',
                f'Edit the experiment metadata.yml file to specify environments',
                'Check if the experiment was loaded correctly'
            ]
        )

    # Load experiment once before running on all environments
    if not arguments.test:  # Production mode
        from adare.backend.experiment import database as experiment_database
        experiment_ulid = experiment_database.get_experiment_by_project_and_name(
            project_directory, experiment_name, trigger_error=False
        )
        if experiment_ulid:
            run_count = experiment_database.get_experiment_run_count(experiment_ulid, exclude_fake=True)
            if run_count > 0:
                # In production mode with existing runs, load without force (strict integrity)
                experiment_load(project_directory, experiment_name, force=False, silent=True)
            else:
                # No existing runs, can force load
                experiment_load(project_directory, experiment_name, force=True, silent=True)
        else:
            experiment_load(project_directory, experiment_name, force=False, silent=True)
    else:  # Test mode (default)
        # Allow force loading in test mode to handle file changes during development
        experiment_load(project_directory, experiment_name, force=True, silent=True)

    print(f"Running experiment '{experiment_name}' on {len(environments)} environment(s)...")
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
            was_interrupted, was_successful = await experiment_run(
                project_directory,
                experiment_name,
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

            if was_interrupted:
                results.append({
                    'environment': env_name,
                    'status': 'INTERRUPTED',
                    'duration': duration,
                    'error': 'User interrupted'
                })
                print(f"⏸️  Environment '{env_name}' interrupted by user ({duration:.1f}s)")

                # Handle interruption and check if user wants to continue
                if not _handle_environment_interruption(environments, i, results):
                    break  # Exit the main environment loop

            elif was_successful:
                results.append({
                    'environment': env_name,
                    'status': 'SUCCESS',
                    'duration': duration,
                    'error': None
                })
                print(f"✅ Environment '{env_name}' completed successfully ({duration:.1f}s)")
            else:
                results.append({
                    'environment': env_name,
                    'status': 'FAILED',
                    'duration': duration,
                    'error': 'Experiment tests failed'
                })
                print(f"❌ Environment '{env_name}' failed - tests did not pass ({duration:.1f}s)")

        except KeyboardInterrupt:
            env_end_time = datetime.now(timezone.utc)
            duration = (env_end_time - env_start_time).total_seconds()

            results.append({
                'environment': env_name,
                'status': 'INTERRUPTED',
                'duration': duration,
                'error': 'User interrupted (Ctrl-C)'
            })

            print(f"⏸️  Environment '{env_name}' interrupted by user ({duration:.1f}s)")

            # Handle interruption and check if user wants to continue
            if not _handle_environment_interruption(environments, i, results):
                break  # Exit the main environment loop

        except Exception as e:
            env_end_time = datetime.now(timezone.utc)
            duration = (env_end_time - env_start_time).total_seconds()
            error_msg = str(e)
            log.error(f"Environment '{env_name}' failed with unexpected error: {e}", exc_info=True)

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


    # Create and use flow console for beautiful summary
    from adare.backend.experiment.print import ExperimentFlowConsole
    import time

    # Create a flow console just for summary display
    summary_console = ExperimentFlowConsole(disable=False)
    summary_console.start()

    # Give it a moment to initialize
    time.sleep(0.2)

    # Log the beautiful multi-experiment summary
    summary_console.log_multi_experiment_summary(
        experiment_name=experiment_name,
        environments=environments,
        results=results,
        total_duration=total_duration
    )

    # Let it display for a moment, then stop
    time.sleep(3)
    summary_console.stop()

    # Summary complete - no need to raise exception for failures
    # The summary already shows the failure status clearly


def exec_experiment_run(arguments):
    from adare.backend.experiment.run import experiment_run
    from adare.backend.experiment.commands import experiment_load
    from adare.exceptions import LoggedException, LoggedErrorException
    import sys

    disable_printing = False
    if arguments.verbose or arguments.very_verbose:
        disable_printing = True

    if project_directory := determine_projectdirectory(arguments.project):
        import asyncio

        # Resolve experiment and environment paths to names
        experiment_name = resolve_experiment_path(arguments.experiment, project_directory)
        environment_name = resolve_environment_path(arguments.environment, project_directory) if arguments.environment else None

        # Check if we need batch execution (multiple environments OR glob patterns)
        from adare.backend.experiment.batch_runner import has_glob_patterns, run_batch_experiments

        # If no environment specified, run on ALL environments (use "*" pattern)
        environment_pattern = environment_name if environment_name else "*"

        # Use batch runner if: no environment specified OR glob patterns detected
        if not environment_name or has_glob_patterns(experiment_name, environment_pattern):
            # Load experiment if needed (similar to old exec_experiment_run_all_environments logic)
            from adare.backend.experiment.commands import experiment_load
            if not environment_name:  # Only auto-load for "all environments" case
                experiment_load(project_directory, experiment_name, force=False, silent=True)

            try:
                summary = asyncio.run(run_batch_experiments(
                    project_path=project_directory,
                    experiment_pattern=experiment_name,
                    environment_pattern=environment_pattern,
                    show_flow_console=True,  # Always show flow console for better user experience
                    test=arguments.test,
                    debug_screenshots=arguments.debug_screenshots,
                    preserve_snapshot=arguments.preserve_snapshot,
                    runlog=arguments.runlog,
                    vm_memory=arguments.vm_memory,
                    vm_cpus=arguments.vm_cpus
                ))

                # Print summary using configured output format
                from adare.run import get_formatter_from_context
                formatter, output_file, dual_output = get_formatter_from_context()

                if dual_output or formatter.format_type.value != 'rich':
                    # Use new formatter system (handles both dual and structured output)
                    formatter.print_or_save(summary.to_dict(), output_file, dual_output)
                else:
                    # Use existing Rich formatting for pure Rich output
                    summary.print_summary()

                # Exit with appropriate code
                if summary.failed_runs > 0:
                    sys.exit(-1)
                else:
                    sys.exit(0)

            except LoggedException as e:
                e.print()
                if isinstance(e, LoggedErrorException):
                    sys.exit(-1)
                else:
                    sys.exit(0)
            except KeyboardInterrupt:
                log.info("Batch execution interrupted by user")
                sys.exit(0)
            return

        # Single environment run (existing logic)
        try:
            # In production mode, use strict loading; in test mode, allow modifications
            if not arguments.test:  # Production mode
                from adare.backend.experiment import database as experiment_database
                experiment_ulid = experiment_database.get_experiment_by_project_and_name(
                    project_directory, experiment_name, trigger_error=False
                )
                if experiment_ulid:
                    run_count = experiment_database.get_experiment_run_count(experiment_ulid, exclude_fake=True)
                    if run_count > 0:
                        # Production mode with existing runs - strict integrity
                        experiment_load(project_directory, experiment_name, force=False, silent=True)
                    else:
                        # No existing runs, can force load
                        experiment_load(project_directory, experiment_name, force=True, silent=True)
                else:
                    experiment_load(project_directory, experiment_name, force=False, silent=True)
            else:  # Test mode (default)
                # Allow force loading in test mode to handle file changes during development
                experiment_load(project_directory, experiment_name, force=True, silent=True)

            # Validate environment and experiment compatibility before starting execution
            from adare.database.api.experiment import ExperimentApi
            from adare.exceptions import EnvironmentNotFoundError, ExperimentNotFoundError
            with ExperimentApi(project_directory) as api:
                environment = api.get_environment(environment_name, project_directory.name)
                if environment is None:
                    raise EnvironmentNotFoundError(log, f'environment {environment_name} does not exist in project {project_directory.name}',
                        possible_solutions=[
                            f'Check if environment name "{environment_name}" is spelled correctly',
                            'List available environments with: adare environment list',
                            'If not found via list, create or load: adare environment create <name> OR adare environment load <path>'
                        ])
                experiment = api.get_experiment(experiment_name, environment.id)
                if experiment is None:
                    raise ExperimentNotFoundError(log, f'experiment {experiment_name} is not available for environment {environment_name}',
                        possible_solutions=[
                            f'Check if experiment name "{experiment_name}" is spelled correctly',
                            'List available experiments with: adare experiment list',
                            f'Check if experiment "{experiment_name}" supports environment "{environment_name}"',
                            'List available environments for this experiment or create a compatible one'
                        ])

            was_interrupted, was_successful = asyncio.run(experiment_run(project_directory, experiment_name, environment_name, disable_printing=disable_printing, test=arguments.test, debug_screenshots=arguments.debug_screenshots, preserve_snapshot=arguments.preserve_snapshot, runlog=arguments.runlog, vm_memory=arguments.vm_memory, vm_cpus=arguments.vm_cpus))

            # Handle output formatting for single runs
            from adare.run import get_formatter_from_context
            from adare.backend.experiment.batch_runner import ExperimentResult, BatchRunSummary
            from datetime import datetime, timedelta
            from adarelib.constants import StatusEnum

            formatter, output_file, dual_output = get_formatter_from_context()

            if dual_output or formatter.format_type.value != 'rich':
                # Create a summary for single run (similar to batch run format)
                if was_interrupted:
                    status = StatusEnum.INTERRUPTED
                    error_msg = "User interrupted"
                elif was_successful:
                    status = StatusEnum.SUCCESS
                    error_msg = None
                else:
                    status = StatusEnum.FAILED
                    error_msg = "Experiment tests failed"

                # Create a single result entry
                single_result = ExperimentResult(
                    environment=environment_name,
                    experiment=experiment_name,
                    status=status,
                    duration=timedelta(seconds=0),  # We don't have duration from single run
                    error_message=error_msg,
                    run_ulid=None,  # Would need to get this from the experiment run
                    start_time=None,
                    end_time=None
                )

                # Create summary with single result
                summary = BatchRunSummary(
                    results=[single_result],
                    total_combinations=1,
                    total_duration=timedelta(seconds=0)
                )

                # Output using formatter
                formatter.print_or_save(summary.to_dict(), output_file, dual_output)
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
            experiment_name = resolve_experiment_path(arguments.experiment, project_directory)
            environment_name = resolve_environment_path(arguments.environment, project_directory)
            experiment_load(project_directory, experiment_name, force=False, silent=True)
            experiment_test(project_directory, experiment_name, environment_name)
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
            experiment_name = resolve_experiment_path(arguments.experiment, project_directory)
            experiment_clean(project_directory, experiment_name)
        except LoggedException as e:
            e.print()
            if isinstance(e, LoggedErrorException):
                sys.exit(-1)
            else:
                sys.exit(0)
    else:
        raise NoProjectFoundError(log, message='no project directory found')


def exec_experiment_add_env(arguments):
    """Execute experiment add-env command to add environments to experiments."""
    from adare.backend.experiment.commands import experiment_add_environments
    from adare.exceptions import LoggedException, LoggedErrorException
    import sys

    if project_directory := determine_projectdirectory(arguments.project):
        try:
            experiment_pattern = resolve_experiment_path(arguments.experiment_pattern, project_directory)
            # Resolve environment names
            environment_names = [resolve_environment_path(env, project_directory) for env in arguments.environments]
            experiment_add_environments(
                project_directory,
                experiment_pattern,
                environment_names,
                force=arguments.force
            )
        except LoggedException as e:
            e.print()
            if isinstance(e, LoggedErrorException):
                sys.exit(-1)
            else:
                sys.exit(0)
    else:
        raise NoProjectFoundError(log, message='no project directory found')


def exec_experiment_remove_env(arguments):
    """Execute experiment remove-env command to remove environments from experiments."""
    from adare.backend.experiment.commands import experiment_remove_environments
    from adare.exceptions import LoggedException, LoggedErrorException
    import sys

    if project_directory := determine_projectdirectory(arguments.project):
        try:
            experiment_pattern = resolve_experiment_path(arguments.experiment_pattern, project_directory)
            # Resolve environment names
            environment_names = [resolve_environment_path(env, project_directory) for env in arguments.environments]
            experiment_remove_environments(
                project_directory,
                experiment_pattern,
                environment_names,
                force=arguments.force
            )
        except LoggedException as e:
            e.print()
            if isinstance(e, LoggedErrorException):
                sys.exit(-1)
            else:
                sys.exit(0)
    else:
        raise NoProjectFoundError(log, message='no project directory found')