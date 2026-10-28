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
        self.result: bool | None = None

    def set_result(self, result: bool) -> None:
        """Override the exit glyph: when False and no exception, finalize as ✖ FAILED.
        Leave as None for phase-level stages (setup/compat/cleanup) that have no boolean result.
        """
        self.result = bool(result)

    def set_status(self, status: int) -> None:
        """StageCtxManager API (connect_websocket): show the stage's sub-message as its progress."""
        self.stage.set_status(status)
        sub_msg = self.stage.sub_msg
        self.flow_console.change_log_message(
            self.stage_id, f"{self.stage.msg}: {sub_msg}" if sub_msg else self.stage.msg
        )

    async def __aenter__(self):
        from datetime import datetime

        # Validate parent stage hierarchy (like original StageCtxManager)
        if hasattr(self.stage, 'parent') and self.stage.parent:
            if self.stage.parent not in self._active_stages:
                # For VM tests, be more lenient - just log a warning instead of raising error
                log.warning(
                    f"VM Test Stage '{self.stage.name}' expects parent '{self.stage.parent}' but no parent stage is active. Continuing anyway for VM tests."
                )

        # Add this stage to active stages registry
        self._active_stages[self.stage.name] = self.stage

        # Set stage start time (reuse Stage lifecycle logic)
        self.start_time = datetime.now(UTC)
        self.stage.start_time = self.start_time

        # Call flow console directly (no events needed)
        self.flow_console.log_spinner(
            identifier=self.stage_id, message=self.stage.msg, level=self.level, start_time=self.start_time
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

        # Determine status based on exception and explicit result
        if exc_type or self.result is False:
            status = StatusEnum.FAILED
            message = f"{self.stage.msg} (failed)"
        else:
            status = StatusEnum.SUCCESS
            message = self.stage.msg

        # Update stage status
        self.stage.status = status

        # Call flow console directly (no events needed)
        self.flow_console.log_spinner_done(identifier=self.stage_id, status=status, message=message, duration=duration)

        log.debug(f"Completed VM test stage: {self.stage.name} - Status: {status.name}, Duration: {duration:.2f}s")

        # Don't suppress exceptions
        return False


def _folder_summary(removals) -> str:
    """One line on what happened to the run folders of deleted runs."""
    deleted = sum(1 for removal in removals if removal.removed)
    kept = [removal for removal in removals if not removal.removed and not removal.missing]
    summary = f'Deleted {deleted} run folder(s)'
    if kept:
        reasons = '; '.join(f'{removal.path.name}: {removal.reason}' for removal in kept[:3])
        more = f' (+{len(kept) - 3} more)' if len(kept) > 3 else ''
        summary += f', kept {len(kept)} ({reasons}{more})'
    return summary


def experiment_clean(project_path: Path, experiment_name: str) -> int:
    """Clean fake experiment runs for the specified experiment.

    Removes the finished fake runs of the experiment: their database rows and their
    run folders (each only if it passes the run-folder safety test, see
    ``backend/experiment/run_folders.py``). Fake runs that are still pending or
    running and dev sessions' runs are kept.

    Args:
        project_path: Path to the project directory
        experiment_name: Name of the experiment to clean fake runs for

    Returns:
        Number of fake runs removed.
    """
    from adare.backend.experiment.run_folders import RunReferencesUnavailableError, remove_db_run_folders
    from adare.console import print_success_message
    from adare.database.api.experiment import ExperimentApi

    log.info(f'Cleaning fake runs for experiment: {experiment_name}')

    try:
        with ExperimentApi(project_path) as api:
            removed: tuple[int, list[str]] = api.remove_fake_runs_of_experiment(project_path, experiment_name)
        removed_count, paths = removed
    except (ValueError, RunReferencesUnavailableError) as e:
        from adare.exceptions import LoggedException

        raise LoggedException(log, str(e)) from e
    except (OSError, KeyError) as e:
        from adare.exceptions import LoggedException

        raise LoggedException(log, f'Failed to clean experiment "{experiment_name}": {str(e)}') from e

    if removed_count == 0:
        log.info(f'No fake runs found for experiment "{experiment_name}" - nothing to clean')
        return 0

    removals = remove_db_run_folders(project_path, paths)
    log.info(f'Removed {removed_count} fake run(s) for experiment "{experiment_name}"')
    print_success_message(
        title=f'Experiment "{experiment_name}" cleaned successfully!',
        location=f'Removed {removed_count} fake run(s)',
        next_steps=[
            'Fake runs have been permanently deleted from the database',
            _folder_summary(removals),
            f'You can continue testing with: adare experiment run {experiment_name} -e <environment>',
        ],
    )
    return removed_count


def _remove_empty_run_parent(project_path: Path, experiment_name: str) -> None:
    """Remove ``run/<experiment>`` once it is empty (never a symlink, never a non-empty directory)."""
    if Path(experiment_name).name != experiment_name or experiment_name in ('', '.', '..'):
        return
    run_parent = project_path / 'run' / experiment_name
    if run_parent.is_symlink() or not run_parent.is_dir():
        return
    try:
        run_parent.rmdir()
    except OSError:
        log.debug(f'kept {run_parent}: not empty')


def experiment_remove(project_path: Path, experiment_name: str, force: bool = False, keep_files: bool = False):
    """Remove an experiment from the database and optionally from the filesystem.

    This function removes an experiment from the database, including all associated
    runs and data. Unless ``keep_files``, it also deletes the runs' folders (each only
    if it passes the run-folder safety test, see ``backend/experiment/run_folders.py``)
    and the experiment directory.

    Args:
        project_path: Path to the project directory
        experiment_name: Name of the experiment to remove
        force: Force removal even if experiment has productive runs
        keep_files: Keep the experiment directory and the run folders (only remove from database)
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
                'list available experiments with: adare experiment list',
            ],
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
                            f'load the experiment first with: adare experiment load {experiment_name}',
                        ],
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
                                'Experiment was not found in database (already removed or never loaded)',
                            ],
                        )
                        return
                    except OSError as e:
                        raise LoggedErrorException(
                            log,
                            f'failed to remove experiment directory: {e}',
                            possible_solutions=[
                                'check file permissions',
                                f'manually delete directory: rm -rf {experiment_directory.path}',
                            ],
                        ) from e
                else:
                    raise LoggedErrorException(
                        log,
                        f'experiment "{experiment_name}" not in database and --keep-files specified',
                        possible_solutions=[
                            f'load the experiment first with: adare experiment load {experiment_name}',
                            'remove --keep-files flag to delete the directory',
                        ],
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
                        'back up important run data before removal',
                    ],
                )

            # Read the dev sessions before the runs are gone: a dev session's run (id =
            # session id) keeps its folder even when the session has no folder recorded.
            dev_sessions = None
            if not keep_files:
                from adare.backend.experiment.run_folders import DevSessionRefs, try_load_dev_session_refs

                refs = try_load_dev_session_refs()
                if isinstance(refs, DevSessionRefs):
                    refs = refs.with_run_paths([run.path for run in experiment.runs if refs.refers_to(run_id=run.id)])
                dev_sessions = refs

            # Remove experiment from database (and all its runs with every row they own)
            experiment_ulid = experiment.id
            run_paths = api.remove_experiment(experiment)
            api._session.commit()
            log.info(f'Removed experiment "{experiment_name}" (ulid: {experiment_ulid}) from database')

            # Optionally remove the runs' folders and the experiment directory
            if not keep_files:
                from adare.backend.experiment.run_folders import remove_db_run_folders

                runs_status = _folder_summary(remove_db_run_folders(project_path, run_paths, dev_sessions=dev_sessions))
                _remove_empty_run_parent(project_path, experiment_name)
                try:
                    shutil.rmtree(experiment_directory.path)
                    log.info(f'Removed experiment directory: {experiment_directory.path}')
                    files_status = 'Experiment directory deleted from filesystem'
                except OSError as e:
                    log.warning(f'Failed to remove experiment directory: {e}')
                    files_status = f'Failed to remove directory: {e}'
            else:
                files_status = 'Experiment directory preserved on filesystem'
                runs_status = 'Run folders preserved on filesystem'

            # Success message
            next_steps = [
                f'Removed experiment from database (ulid: {experiment_ulid})',
                f'Deleted {total_run_count} run(s) ({productive_run_count} productive, {total_run_count - productive_run_count} fake)',
                runs_status,
                files_status,
            ]

            if keep_files:
                next_steps.append(f'You can reload the experiment with: adare experiment load {experiment_name}')
            else:
                next_steps.append(f'You can recreate the experiment with: adare experiment create {experiment_name}')

            print_success_message(
                title=f'Experiment "{experiment_name}" removed successfully!',
                location=str(experiment_directory.path),
                next_steps=next_steps,
            )

    except LoggedErrorException:
        raise
    except ValueError as e:
        raise LoggedErrorException(log, str(e)) from e
    except (OSError, KeyError) as e:
        log.error(f'Failed to remove experiment "{experiment_name}": {e}', exc_info=True)
        raise LoggedErrorException(
            log,
            f'failed to remove experiment "{experiment_name}": {str(e)}',
            possible_solutions=[
                'check database connectivity',
                'ensure you have write permissions',
                'check the log output for specific error details',
            ],
        ) from e


async def ova_test(
    ova_file_path: Path, guest_platform: str, verbose: bool = False, vm_cleanup_mode: str = 'prompt'
) -> bool:
    """
    Test OVA file compatibility with ADARE.

    Thin wrapper around the implementation in vm_test_ova.py.

    Args:
        ova_file_path: Path to the .ova file to test
        guest_platform: Platform type ('windows' or 'linux') - required
        verbose: Enable verbose logging
        vm_cleanup_mode: VM cleanup mode ('keep' or 'prompt')

    Returns:
        True if VM is compatible with ADARE, False otherwise
    """
    from adare.backend.experiment.vm_test_ova import ova_test as vm_ova_test

    return await vm_ova_test(ova_file_path, guest_platform, verbose, vm_cleanup_mode)


async def vm_test_registered(
    vm_name: str,
    disk_path: str,
    guest_platform: str,
    architecture: str = 'x86_64',
    verbose: bool = False,
    vm_cleanup_mode: str = 'prompt',
) -> bool:
    """
    Test a registered QEMU VM's compatibility with ADARE.

    Thin wrapper around the implementation in vm_test_qemu.py.

    Args:
        vm_name: Registered VM name
        disk_path: Path to the VM's immutable base disk (vm.file)
        guest_platform: Platform type ('windows' or 'linux')
        architecture: Guest CPU architecture (e.g. 'x86_64', 'aarch64')
        verbose: Enable verbose logging
        vm_cleanup_mode: VM cleanup mode ('keep' or 'prompt')

    Returns:
        True if VM is compatible with ADARE, False otherwise
    """
    from adare.backend.experiment.vm_test_qemu import vm_test_registered as vm_test_registered_impl

    return await vm_test_registered_impl(vm_name, disk_path, guest_platform, architecture, verbose, vm_cleanup_mode)


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
    from adare.database.models.project_models import ExperimentRun
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
        raise NotLoggedInError(log, 'You are not logged in to the server.', possible_solutions=['Run: adare web login'])

    # Validate run exists locally
    with ExperimentApi(project_directory) as exp_api:
        # `ExperimentApi` has no run-specific getter; the generic ULID lookup on the
        # base API is the one that exists. (`get_run_by_ulid` never did.)
        run = exp_api.get_by_ulid(ExperimentRun, run_ulid)
        if not run:
            from adare.exceptions import ExperimentRunNotFoundError

            raise ExperimentRunNotFoundError(
                log,
                f'Experiment run {run_ulid} not found in project database.',
                possible_solutions=['Check the run ULID', 'List runs with: adare runs list'],
            )

        experiment = run.experiment
        if not experiment:
            from adare.exceptions import ExperimentNotFoundError as LocalExpNotFound

            raise LocalExpNotFound(
                log,
                f'Experiment associated with run {run_ulid} not found.',
                possible_solutions=['Check database integrity'],
            )
        # Read the identity fields while the session is open — the objects are
        # detached afterwards. The *server's* ULID is what the server can be asked
        # about; the local one is meaningless to it.
        experiment_name = experiment.name
        experiment_local_ulid = experiment.id
        experiment_remote_ulid = experiment.remote_ulid

    if not experiment_remote_ulid:
        raise ExperimentNotFoundError(
            log,
            f'Experiment {experiment_name} (local ULID: {experiment_local_ulid}) has no '
            f'server ULID recorded, so it has not been published from this machine.',
            possible_solutions=[
                'Publish the experiment first: adare web submit experiment <name>',
                'Already published elsewhere? Fetch its server identity: adare web sync',
            ],
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
        # Task 1: Check experiment exists on server — by its REMOTE ULID. Asking
        # about the local one always answered "no", which is what made publish
        # abort with "not published on the server" for published experiments.
        task1 = progress.add_task("[cyan]Checking experiment on server...", total=1)
        try:
            exp_exists = client.check_experiment_exists(experiment_remote_ulid)
            if not exp_exists:
                progress.update(task1, completed=1)
                raise ExperimentNotFoundError(
                    log,
                    f'Experiment {experiment_name} (server ULID: {experiment_remote_ulid}) is not '
                    f'published on the server.',
                    possible_solutions=[
                        'Publish the experiment first with: adare web submit experiment <name>',
                        'Refresh the local view of the server: adare web sync',
                    ],
                )
            progress.update(task1, completed=1, description=f"[green]Experiment {experiment_name} verified on server")
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
            result = client.publish_experiment_run(run_ulid, project_directory)
            progress.update(task3, completed=1, description="[green]Run published successfully")

            # Update local database to mark as published
            with ExperimentApi(project_directory) as exp_api:
                exp_api.mark_run_as_published(run_ulid)

            console.print(f"\n[green]Successfully published run {run_ulid}![/green]")
            console.print(f"Experiment: {experiment_name}")
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
