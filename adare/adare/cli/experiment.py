# internal imports
from adare.backend.basics import determine_projectdirectory
from adare.exceptions import NoProjectFoundError
from adare.helperfunctions.path_resolution import resolve_experiment_path, resolve_environment_path
from adare.api import AdareAPI
from adare.core.dto.experiment import (
    ExperimentCreateRequest,
    ExperimentCloneRequest,
    ExperimentRemoveRequest,
    ExperimentEnvModifyRequest,
    ExperimentLoadRequest,
)
from adare.console import print_success_message, print_error_message


# configure logging
import logging
log = logging.getLogger(__name__)


def _handle_api_error(result) -> None:
    """
    Handle an API error result by printing formatted error message and exiting.

    Args:
        result: Result object with error information
    """
    error = result.error
    print_error_message(
        title=f'{error.code}: {error.message}',
        next_steps=error.solutions
    )
    exit(1)


def _get_project_path(arguments):
    """Get project path from arguments or current directory."""
    project = getattr(arguments, 'project', None)
    project_directory = determine_projectdirectory(project)
    if not project_directory:
        raise NoProjectFoundError(log, message='no project directory found')
    return project_directory


def exec_experiment_load(arguments):
    """Load an experiment from files into the database using AdareAPI."""
    from adare.backend.project.directory import ProjectDirectory
    import shutil
    from pathlib import Path

    project_directory = _get_project_path(arguments)
    original_input = arguments.experiment
    project_dir_obj = ProjectDirectory(project_directory)

    # Determine if this is an external path that needs special handling
    is_external_path = False
    external_source_path = None
    potential_copied_name = None

    if ('/' in original_input or '\\' in original_input):
        input_path = Path(original_input)
        if input_path.is_absolute() or not (Path.cwd() / input_path).is_relative_to(project_dir_obj.experiments):
            # This is an external path
            if input_path.exists() and input_path.is_dir():
                is_external_path = True
                external_source_path = input_path.resolve()
                potential_copied_name = input_path.name

    # Track whether a copy was actually performed during path resolution
    copy_was_performed = False
    target_existed_before = False

    if is_external_path and potential_copied_name:
        target_path = project_dir_obj.experiments / potential_copied_name
        target_existed_before = target_path.exists()

    try:
        experiment_name = resolve_experiment_path(arguments.experiment, project_directory)

        # If external path and target existed before, check if we should overwrite
        if is_external_path and target_existed_before and external_source_path:
            target_path = project_dir_obj.experiments / experiment_name

            # Check if experiment has productive runs
            from adare.backend.experiment import database as experiment_database
            experiment_ulid = experiment_database.get_experiment_by_project_and_name(
                project_directory, experiment_name, trigger_error=False
            )

            has_productive_runs = False
            if experiment_ulid:
                run_count = experiment_database.get_experiment_run_count(experiment_ulid, exclude_fake=True)
                has_productive_runs = run_count > 0

            if not has_productive_runs:
                # No productive runs - safe to overwrite
                log.info(f'Overwriting experiment directory {target_path} with fresh copy from {external_source_path} (no productive runs found)')
                shutil.rmtree(target_path)
                shutil.copytree(external_source_path, target_path)
                copy_was_performed = True
            else:
                log.info(f'Using existing experiment directory {target_path} (has {run_count} productive runs, not overwriting)')

        # Use API for the actual load
        api = AdareAPI()
        result = api.experiment.load(ExperimentLoadRequest(
            project_path=project_directory,
            name=experiment_name,
            force=arguments.force,
            silent=False
        ))

        if result.success:
            print_success_message(
                title=f'Experiment "{result.data.name}" loaded successfully!',
                location=str(result.data.file_path) if result.data.file_path else None,
                next_steps=result.data.next_steps,
                tip=result.data.tip
            )
        else:
            _handle_api_error(result)

    except Exception as e:
        # Only cleanup if we actually copied during this run
        if copy_was_performed and potential_copied_name:
            copied_experiment_path = project_dir_obj.experiments / potential_copied_name
            if copied_experiment_path.exists():
                try:
                    shutil.rmtree(copied_experiment_path)
                    log.info(f'Cleaned up copied experiment {copied_experiment_path} after load failure')
                except OSError as cleanup_error:
                    log.warning(f'Failed to clean up copied experiment {copied_experiment_path}: {cleanup_error}')
        raise


def exec_experiment_create(arguments):
    """Create a new experiment using AdareAPI."""
    project_directory = _get_project_path(arguments)
    experiment_name = resolve_experiment_path(arguments.experiment, project_directory)

    api = AdareAPI()
    result = api.experiment.create(ExperimentCreateRequest(
        project_path=project_directory,
        name=experiment_name
    ))

    if result.success:
        print_success_message(
            title=f'Experiment "{result.data.name}" created successfully!',
            location=str(result.data.file_path) if result.data.file_path else None,
            next_steps=result.data.next_steps,
            tip=result.data.tip
        )
    else:
        _handle_api_error(result)


def exec_experiment_example(arguments):
    """Create an example experiment using AdareAPI."""
    project_directory = _get_project_path(arguments)
    experiment_name = resolve_experiment_path(arguments.experiment, project_directory)

    api = AdareAPI()
    result = api.experiment.example(project_directory, experiment_name)

    if result.success:
        print_success_message(
            title=f'Example experiment "{result.data.name}" created successfully!',
            location=str(result.data.file_path) if result.data.file_path else None,
            next_steps=result.data.next_steps,
            tip=result.data.tip
        )
    else:
        _handle_api_error(result)


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
                vm_cpus=arguments.vm_cpus,
                diff=getattr(arguments, 'diff', None),
                diff_mode=getattr(arguments, 'diff_mode', 'auto')
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
                    vm_cpus=arguments.vm_cpus,
                    gui_mode=arguments.gui_mode,
                    test_exec_mode=getattr(arguments, 'test_mode', None),
                    diff=getattr(arguments, 'diff', None),
                    diff_mode=getattr(arguments, 'diff_mode', 'auto')
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

                # Try WITH environment validation first
                experiment = api.get_experiment(experiment_name, environment.id)

                # If not found, try WITHOUT environment validation
                if experiment is None:
                    experiment = api.get_experiment_by_project_and_name(project_directory, experiment_name)
                    if experiment is None:
                        raise ExperimentNotFoundError(log, f'experiment {experiment_name} not found',
                            possible_solutions=[
                                f'Check if experiment name "{experiment_name}" is spelled correctly',
                                'List available experiments with: adare experiment list',
                            ])

                    # Environment is unlisted - print warning but continue
                    log.warning(f'WARNING: environment "{environment_name}" is not listed in {experiment_name}/metadata.yml')
                    log.warning(f'         Running experiment anyway as explicitly requested via -e flag')

            was_interrupted, was_successful = asyncio.run(experiment_run(project_directory, experiment_name, environment_name, disable_printing=disable_printing, test=arguments.test, debug_screenshots=arguments.debug_screenshots, preserve_snapshot=arguments.preserve_snapshot, runlog=arguments.runlog, vm_memory=arguments.vm_memory, vm_cpus=arguments.vm_cpus, gui_mode=arguments.gui_mode, test_exec_mode=getattr(arguments, 'test_mode', None), diff=getattr(arguments, 'diff', None), diff_mode=getattr(arguments, 'diff_mode', 'auto')))

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
    """Run experiment tests (dry-run) using AdareAPI."""
    project_directory = _get_project_path(arguments)
    experiment_name = resolve_experiment_path(arguments.experiment, project_directory)
    environment_name = resolve_environment_path(arguments.environment, project_directory)

    # Load experiment first
    api = AdareAPI()
    load_result = api.experiment.load(ExperimentLoadRequest(
        project_path=project_directory,
        name=experiment_name,
        force=False,
        silent=True
    ))

    if not load_result.success:
        _handle_api_error(load_result)

    # Run test
    result = api.experiment.test(project_directory, experiment_name, environment_name)

    if result.success:
        print_success_message(
            title=f'Experiment "{experiment_name}" test completed successfully!'
        )
    else:
        _handle_api_error(result)


def exec_experiment_clean(arguments):
    """Execute experiment clean command to remove fake runs using AdareAPI."""
    project_directory = _get_project_path(arguments)
    experiment_name = resolve_experiment_path(arguments.experiment, project_directory)

    api = AdareAPI()
    result = api.experiment.clean(project_directory, experiment_name)

    if result.success:
        if result.data.deleted_count > 0:
            print_success_message(
                title=f'Cleaned {result.data.deleted_count} fake run(s) from experiment "{result.data.experiment_name}"'
            )
        else:
            print_success_message(
                title=f'No fake runs to clean for experiment "{result.data.experiment_name}"'
            )
    else:
        _handle_api_error(result)


def exec_experiment_remove(arguments):
    """Execute experiment remove command to delete an experiment using AdareAPI."""
    project_directory = _get_project_path(arguments)
    experiment_name = resolve_experiment_path(arguments.experiment, project_directory)

    api = AdareAPI()
    result = api.experiment.remove(ExperimentRemoveRequest(
        project_path=project_directory,
        name=experiment_name,
        force=arguments.force,
        keep_files=arguments.keep_files
    ))

    if result.success:
        print_success_message(
            title=f'Experiment "{result.data.experiment_name}" removed successfully!'
        )
    else:
        _handle_api_error(result)


def exec_experiment_add_env(arguments):
    """Execute experiment add-env command to add environments to experiments using AdareAPI."""
    project_directory = _get_project_path(arguments)
    experiment_pattern = resolve_experiment_path(arguments.experiment_pattern, project_directory)
    # Resolve environment names
    environment_names = [resolve_environment_path(env, project_directory) for env in arguments.environments]

    api = AdareAPI()
    result = api.experiment.add_environments(ExperimentEnvModifyRequest(
        project_path=project_directory,
        experiment_pattern=experiment_pattern,
        environments=environment_names,
        force=arguments.force
    ))

    if result.success:
        affected = ', '.join(result.data.affected_experiments) if result.data.affected_experiments else 'none'
        print_success_message(
            title=f'Environments added to experiments: {affected}'
        )
    else:
        _handle_api_error(result)


def exec_experiment_remove_env(arguments):
    """Execute experiment remove-env command to remove environments from experiments using AdareAPI."""
    project_directory = _get_project_path(arguments)
    experiment_pattern = resolve_experiment_path(arguments.experiment_pattern, project_directory)
    # Resolve environment names
    environment_names = [resolve_environment_path(env, project_directory) for env in arguments.environments]

    api = AdareAPI()
    result = api.experiment.remove_environments(ExperimentEnvModifyRequest(
        project_path=project_directory,
        experiment_pattern=experiment_pattern,
        environments=environment_names,
        force=arguments.force
    ))

    if result.success:
        affected = ', '.join(result.data.affected_experiments) if result.data.affected_experiments else 'none'
        print_success_message(
            title=f'Environments removed from experiments: {affected}'
        )
    else:
        _handle_api_error(result)


def exec_experiment_clone(arguments):
    """Execute experiment clone command to create experiment variations using AdareAPI."""
    project_directory = _get_project_path(arguments)
    source_experiment = resolve_experiment_path(arguments.source_experiment, project_directory)
    target_experiment = resolve_experiment_path(arguments.target_experiment, project_directory)

    environments = None
    if hasattr(arguments, 'environments') and arguments.environments:
        environments = [resolve_environment_path(env, project_directory) for env in arguments.environments]

    api = AdareAPI()
    result = api.experiment.clone(ExperimentCloneRequest(
        project_path=project_directory,
        source_experiment=source_experiment,
        target_experiment=target_experiment,
        environments=environments
    ))

    if result.success:
        print_success_message(
            title=f'Experiment "{result.data.name}" cloned successfully!',
            location=str(result.data.file_path) if result.data.file_path else None,
            next_steps=result.data.next_steps,
            tip=result.data.tip
        )
    else:
        _handle_api_error(result)