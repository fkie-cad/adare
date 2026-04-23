# external imports
import logging
from datetime import UTC
from pathlib import Path

# internal imports
from adare.backend.experiment.directory import ExperimentDirectory
from adare.backend.experiment.exceptions import (
    ExperimentDirectoryDoesNotExistError,
)
from adare.webappaccess.login import is_logged_in
from adarelib.constants import StatusEnum

log = logging.getLogger(__name__)


class StageCtxManagerLite:
    """Lightweight StageCtxManager for VM tests - calls flow console directly (no database/events)."""

    # Class-level registry to track active parent stages for hierarchy validation
    _active_stages = {}  # stage_name -> stage_instance

    def __init__(self, stage, flow_console, level=0):
        self.stage = stage  # Reuse existing Stage classes
        self.flow_console = flow_console  # Direct flow console access
        self.level = level
        self.stage_id = f"{stage.name}_{int(__import__('time').time())}"
        self.start_time = None
        self.end_time = None

    async def __aenter__(self):
        from datetime import datetime

        # Validate parent stage hierarchy (like original StageCtxManager)
        if hasattr(self.stage, 'parent') and self.stage.parent:
            if self.stage.parent not in self._active_stages:
                # For VM tests, be more lenient - just log a warning instead of raising error
                log.warning(f"VM Test Stage '{self.stage.name}' expects parent '{self.stage.parent}' but no parent stage is active. Continuing anyway for VM tests.")

        # Add this stage to active stages registry
        self._active_stages[self.stage.name] = self.stage

        # Set stage start time (reuse Stage lifecycle logic)
        self.start_time = datetime.now(UTC)
        self.stage.start_time = self.start_time

        # Call flow console directly (no events needed)
        self.flow_console.log_spinner(
            identifier=self.stage_id,
            message=self.stage.msg,
            level=self.level,
            start_time=self.start_time
        )

        log.debug(f"Started VM test stage: {self.stage.name} - {self.stage.msg}")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        from datetime import datetime

        # Remove this stage from active stages registry
        self._active_stages.pop(self.stage.name, None)

        # Set stage end time and calculate duration
        self.end_time = datetime.now(UTC)
        self.stage.end_time = self.end_time
        duration = (self.end_time - self.start_time).total_seconds()

        # Determine status based on exception
        if exc_type:
            status = StatusEnum.FAILED
            message = f"{self.stage.msg} (failed)"
        else:
            status = StatusEnum.SUCCESS
            message = self.stage.msg

        # Update stage status
        self.stage.status = status

        # Call flow console directly (no events needed)
        self.flow_console.log_spinner_done(
            identifier=self.stage_id,
            status=status,
            message=message,
            duration=duration
        )

        log.debug(f"Completed VM test stage: {self.stage.name} - Status: {status.name}, Duration: {duration:.2f}s")

        # Don't suppress exceptions
        return False


def experiment_clean(project_path: Path, experiment_name: str):
    """Clean fake experiment runs for the specified experiment.

    This function removes all fake runs associated with an experiment,
    helping to clean up test runs that are preserved for debugging.

    Args:
        project_path: Path to the project directory
        experiment_name: Name of the experiment to clean fake runs for
    """
    from adare.console import print_success_message
    from adare.database.api.experiment import ExperimentApi

    log.info(f'Cleaning fake runs for experiment: {experiment_name}')

    try:
        with ExperimentApi(project_path) as api:
            removed_count = api.remove_fake_experiment_runs_by_experiment_name(project_path, experiment_name)

            if removed_count > 0:
                log.info(f'Removed {removed_count} fake run(s) for experiment "{experiment_name}"')
                print_success_message(
                    title=f'Experiment "{experiment_name}" cleaned successfully!',
                    location=f'Removed {removed_count} fake run(s)',
                    next_steps=[
                        'Fake runs have been permanently deleted from the database',
                        f'You can continue testing with: adare experiment test {experiment_name} -e <environment>'
                    ]
                )
            else:
                log.info(f'No fake runs found for experiment "{experiment_name}"')
                log.info(f'No fake runs found for experiment "{experiment_name}" - nothing to clean')

    except ValueError as e:
        from adare.exceptions import LoggedException
        raise LoggedException(log, str(e))
    except (OSError, KeyError) as e:
        from adare.exceptions import LoggedException
        raise LoggedException(log, f'Failed to clean experiment "{experiment_name}": {str(e)}')


def experiment_remove(project_path: Path, experiment_name: str, force: bool = False, keep_files: bool = False):
    """Remove an experiment from the database and optionally from the filesystem.

    This function removes an experiment from the database, including all associated
    runs and data. Optionally deletes the experiment directory from the filesystem.

    Args:
        project_path: Path to the project directory
        experiment_name: Name of the experiment to remove
        force: Force removal even if experiment has productive runs
        keep_files: Keep experiment directory on filesystem (only remove from database)
    """
    import shutil

    from adare.console import print_success_message
    from adare.database.api.experiment import ExperimentApi
    from adare.exceptions import LoggedErrorException

    log.info(f'Removing experiment: {experiment_name}')

    # Get experiment directory
    experiment_directory = ExperimentDirectory(project_path, experiment_name)

    if not experiment_directory.exists():
        raise ExperimentDirectoryDoesNotExistError(
            log,
            f'experiment directory [b]{experiment_directory.path}[/b] does not exist',
            possible_solutions=[
                f'check if experiment name "{experiment_name}" is correct',
                'list available experiments with: adare experiment list'
            ]
        )

    try:
        with ExperimentApi(project_path) as api:
            # Get experiment from database
            experiment = api.get_experiment_by_project_and_name(project_path, experiment_name)

            if not experiment:
                # Experiment exists on filesystem but not in database
                log.warning(f'Experiment "{experiment_name}" exists on filesystem but not in database')

                if not force:
                    raise LoggedErrorException(
                        log,
                        f'experiment "{experiment_name}" not found in database',
                        possible_solutions=[
                            'use --force to remove the experiment directory anyway',
                            f'load the experiment first with: adare experiment load {experiment_name}'
                        ]
                    )

                # Force removal of directory only
                if not keep_files:
                    try:
                        shutil.rmtree(experiment_directory.path)
                        log.info(f'Removed experiment directory: {experiment_directory.path}')
                        print_success_message(
                            title=f'Experiment "{experiment_name}" directory removed!',
                            location=str(experiment_directory.path),
                            next_steps=[
                                'Experiment directory has been deleted from filesystem',
                                'Experiment was not found in database (already removed or never loaded)'
                            ]
                        )
                        return
                    except OSError as e:
                        raise LoggedErrorException(
                            log,
                            f'failed to remove experiment directory: {e}',
                            possible_solutions=[
                                'check file permissions',
                                f'manually delete directory: rm -rf {experiment_directory.path}'
                            ]
                        )
                else:
                    raise LoggedErrorException(
                        log,
                        f'experiment "{experiment_name}" not in database and --keep-files specified',
                        possible_solutions=[
                            f'load the experiment first with: adare experiment load {experiment_name}',
                            'remove --keep-files flag to delete the directory'
                        ]
                    )

            # Count productive runs
            productive_run_count = len([run for run in experiment.runs if not run.fake])
            total_run_count = len(experiment.runs)

            # Check if experiment has productive runs and force flag not set
            if productive_run_count > 0 and not force:
                raise LoggedErrorException(
                    log,
                    f'experiment "{experiment_name}" has {productive_run_count} productive run(s)',
                    possible_solutions=[
                        'use --force to remove the experiment and all its runs',
                        f'clean fake runs only with: adare experiment clean {experiment_name}',
                        'back up important run data before removal'
                    ]
                )

            # Remove experiment from database (cascades to all runs and related data)
            experiment_ulid = experiment.id
            api.remove_experiment(experiment)
            api._session.commit()
            log.info(f'Removed experiment "{experiment_name}" (ulid: {experiment_ulid}) from database')

            # Optionally remove experiment directory
            if not keep_files:
                try:
                    shutil.rmtree(experiment_directory.path)
                    log.info(f'Removed experiment directory: {experiment_directory.path}')
                    files_status = 'Experiment directory deleted from filesystem'
                except OSError as e:
                    log.warning(f'Failed to remove experiment directory: {e}')
                    files_status = f'Failed to remove directory: {e}'
            else:
                files_status = 'Experiment directory preserved on filesystem'

            # Success message
            next_steps = [
                f'Removed experiment from database (ulid: {experiment_ulid})',
                f'Deleted {total_run_count} run(s) ({productive_run_count} productive, {total_run_count - productive_run_count} fake)',
                files_status
            ]

            if keep_files:
                next_steps.append(f'You can reload the experiment with: adare experiment load {experiment_name}')
            else:
                next_steps.append(f'You can recreate the experiment with: adare experiment create {experiment_name}')

            print_success_message(
                title=f'Experiment "{experiment_name}" removed successfully!',
                location=str(experiment_directory.path),
                next_steps=next_steps
            )

    except LoggedErrorException:
        raise
    except ValueError as e:
        raise LoggedErrorException(log, str(e))
    except (OSError, KeyError) as e:
        log.error(f'Failed to remove experiment "{experiment_name}": {e}', exc_info=True)
        raise LoggedErrorException(
            log,
            f'failed to remove experiment "{experiment_name}": {str(e)}',
            possible_solutions=[
                'check database connectivity',
                'ensure you have write permissions',
                'check the log output for specific error details'
            ]
        )


async def ova_test(ova_file_path: Path, guest_platform: str, verbose: bool = False, vm_cleanup_mode: str = 'prompt') -> bool:
    """
    Test OVA file compatibility with ADARE.

    This function has been moved to vm_test.py for better code organization.

    Args:
        ova_file_path: Path to the .ova file to test
        guest_platform: Platform type ('windows' or 'linux') - required
        verbose: Enable verbose logging
        vm_cleanup_mode: VM cleanup mode ('keep' or 'prompt')

    Returns:
        True if VM is compatible with ADARE, False otherwise
    """
    from adare.backend.experiment.vm_test import ova_test as vm_ova_test
    return await vm_ova_test(ova_file_path, guest_platform, verbose, vm_cleanup_mode)


def publish_run_command(project_directory: Path, run_ulid: str):
    """
    Publish an experiment run to the server with validation and progress tracking.

    Args:
        project_directory: Path to the project directory
        run_ulid: ULID of the experiment run to publish

    Raises:
        Various exceptions from webappaccess.exceptions for different error conditions
    """
    from rich.console import Console
    from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn

    from adare.database.api.experiment import ExperimentApi
    from adare.webappaccess.api_client import ApiClient
    from adare.webappaccess.exceptions import (
        ApiConnectionError,
        ExperimentNotFoundError,
        NotLoggedInError,
        RunAlreadyExistsError,
    )

    console = Console()

    # Validate login status
    if not is_logged_in():
        raise NotLoggedInError(
            log,
            'You are not logged in to the server.',
            possible_solutions=['Run: adare web login']
        )

    # Validate run exists locally
    with ExperimentApi(project_directory) as exp_api:
        run = exp_api.get_run_by_ulid(run_ulid)
        if not run:
            from adare.exceptions import ExperimentRunNotFoundError
            raise ExperimentRunNotFoundError(
                log,
                f'Experiment run {run_ulid} not found in project database.',
                possible_solutions=['Check the run ULID', 'List runs with: adare run list']
            )

        experiment = run.experiment
        if not experiment:
            from adare.exceptions import ExperimentNotFoundError as LocalExpNotFound
            raise LocalExpNotFound(
                log,
                f'Experiment associated with run {run_ulid} not found.',
                possible_solutions=['Check database integrity']
            )

    # Create API client
    client = ApiClient()

    # Show progress with rich
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        # Task 1: Check experiment exists on server
        task1 = progress.add_task("[cyan]Checking experiment on server...", total=1)
        try:
            exp_exists = client.check_experiment_exists(experiment.id)
            if not exp_exists:
                progress.update(task1, completed=1)
                raise ExperimentNotFoundError(
                    log,
                    f'Experiment {experiment.name} (ULID: {experiment.id}) is not published on the server.',
                    possible_solutions=['Publish the experiment first with: adare web publish <experiment>']
                )
            progress.update(task1, completed=1, description=f"[green]Experiment {experiment.name} verified on server")
        except ApiConnectionError:
            progress.update(task1, completed=1)
            raise

        # Task 2: Check if run already exists
        task2 = progress.add_task("[cyan]Checking run status...", total=1)
        try:
            run_exists = client.check_run_exists(run_ulid)
            if run_exists:
                progress.update(task2, completed=1, description="[yellow]Run already exists on server")
                console.print(f"[yellow]Run {run_ulid} already published to server. No action needed.[/yellow]")
                return
            progress.update(task2, completed=1, description="[green]Run not yet published")
        except ApiConnectionError:
            progress.update(task2, completed=1)
            raise

        # Task 3: Upload run
        task3 = progress.add_task("[cyan]Uploading experiment run...", total=1)
        try:
            result = client.publish_experiment_run(run_ulid)
            progress.update(task3, completed=1, description="[green]Run published successfully")

            # Update local database to mark as published
            with ExperimentApi(project_directory) as exp_api:
                exp_api.mark_run_as_published(run_ulid)

            console.print(f"\n[green]Successfully published run {run_ulid}![/green]")
            console.print(f"Experiment: {experiment.name}")
            console.print(f"Server ULID: {result.get('ulid', run_ulid)}")

        except RunAlreadyExistsError:
            progress.update(task3, completed=1)
            console.print(f"[yellow]Run {run_ulid} already exists on server (concurrent upload?).[/yellow]")
        except ExperimentNotFoundError as e:
            progress.update(task3, completed=1)
            console.print(f"[red]Failed: {e.message}[/red]")
            raise
        except ApiConnectionError as e:
            progress.update(task3, completed=1)
            console.print(f"[red]Upload failed: {e.message}[/red]")
            raise
