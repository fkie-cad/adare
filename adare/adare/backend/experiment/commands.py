# external imports
from pathlib import Path

# internal imports
from adare.backend.experiment.directory import ExperimentDirectory
import adare.backend.experiment.database as experiment_database
from adare.backend.experiment.exceptions import ExperimentDirectoryAlreadyExistsError, \
    ExperimentDirectoryDoesNotExistError, ExperimentIntegrityError, ExperimentAlreadyExistsError, ExperimentNotChanged
from adare.exceptions import LoggedException
from adare.backend.project.directory import ProjectDirectory
from adarelib.constants import StatusEnum
from adare.webappaccess.download import download_experiment, sync
from adare.webappaccess.login import is_logged_in
from adare.exceptions import NotLoggedInError

# configure logging
import logging
log = logging.getLogger(__name__)


def _get_testfunction_data_from_database():
    """
    Get testfunction data from the global database.

    Returns:
        list: List of (name, path) tuples for testfunction files
    """
    try:
        from adare.database.api.testfunction import TestfunctionDbApi

        with TestfunctionDbApi() as api:
            testfunction_files = api.get_testfunction_files()
            return [(tf_file.name, tf_file.path) for tf_file in testfunction_files]
    except Exception as e:
        log.warning(f"Failed to query testfunction files from database: {e}")
        return []


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
        from datetime import datetime, timezone
        
        # Validate parent stage hierarchy (like original StageCtxManager)
        if hasattr(self.stage, 'parent') and self.stage.parent:
            if self.stage.parent not in self._active_stages:
                # For VM tests, be more lenient - just log a warning instead of raising error
                log.warning(f"VM Test Stage '{self.stage.name}' expects parent '{self.stage.parent}' but no parent stage is active. Continuing anyway for VM tests.")
        
        # Add this stage to active stages registry
        self._active_stages[self.stage.name] = self.stage
        
        # Set stage start time (reuse Stage lifecycle logic)
        self.start_time = datetime.now(timezone.utc)
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
        from datetime import datetime, timezone
        
        # Remove this stage from active stages registry
        self._active_stages.pop(self.stage.name, None)
        
        # Set stage end time and calculate duration
        self.end_time = datetime.now(timezone.utc)
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


def experiment_sync(project_path: Path, experiment_ulid: str):
    if not is_logged_in():
        log.info(f'sync is not possible because user is not logged in')
        return
    # get experiment from database
    sha256 = experiment_database.get_experiment_hash(project_path, experiment_ulid)
    # download experiment from webapp
    metadata_remote = sync(sha256, 'experiment')
    if not metadata_remote:
        log.info(f'experiment {experiment_ulid} does not exist remotely')
        return
    is_published = metadata_remote.get('published')
    remote_url = metadata_remote.get('gitea_url')
    remote_ulid = metadata_remote.get('ulid')
    abstract_tests_ulids = metadata_remote.get('abstract_tests_ulids')
    experiment_database.sync_experiment(project_path, experiment_ulid, remote_ulid, abstract_tests_ulids, remote_url, is_published)
    log.info(f'experiment {experiment_ulid} synced')


def experiment_create(project_path: Path, experiment: str):
    from adare.console import print_success_message

    experiment_directory = ExperimentDirectory(project_path, experiment)
    if experiment_directory.exists():
        raise ExperimentDirectoryAlreadyExistsError(
            log, f'experiment directory [b]{experiment_directory.path}[/b] already exists'
        )
    experiment_directory.create()
    log.info(f'experiment directory {experiment_directory.path} created')

    # Provide clear user feedback with next steps
    next_steps = [
        f'Edit {experiment_directory.playbookfile.name} to define a sequence of gui actions and tests',
        f'Edit {experiment_directory.metadatafile.name} to add experiment details, such as possible environments, tags, and more',
        f'Before run load the experiment with: adare experiment load {experiment}',
        f'Run the experiment with: adare experiment run {experiment} -e <environment>'
    ]

    print_success_message(
        title=f'Experiment "{experiment}" created successfully!',
        location=str(experiment_directory.path),
        next_steps=next_steps,
        tip='See documentation for an tutorial on how write an experiment here: https://adare.seclab-bonn.de/docs/gettingstarted/index.html#create-an-experiment'
    )


def experiment_clone(project_path: Path, source_experiment: str, target_experiment: str, environments: list[str] = None):
    """Clone an existing experiment to create a variation.

    Args:
        project_path: Path to the project directory
        source_experiment: Name of the experiment to clone from
        target_experiment: Name for the cloned experiment
        environments: Optional list of environments to override in the clone
    """
    from adare.console import print_success_message
    import shutil

    source_dir = ExperimentDirectory(project_path, source_experiment)
    target_dir = ExperimentDirectory(project_path, target_experiment)

    if not source_dir.exists():
        raise ExperimentDirectoryDoesNotExistError(
            log,
            f'source experiment directory [b]{source_dir.path}[/b] does not exist',
            possible_solutions=[
                f'check if experiment name "{source_experiment}" is correct',
                'list available experiments with: adare experiment list'
            ]
        )

    if target_dir.exists():
        raise ExperimentDirectoryAlreadyExistsError(
            log,
            f'target experiment directory [b]{target_dir.path}[/b] already exists',
            possible_solutions=[
                f'choose a different name for the cloned experiment',
                f'remove existing experiment with: rm -rf {target_dir.path}'
            ]
        )

    log.info(f'cloning experiment {source_experiment} to {target_experiment}')

    try:
        shutil.copytree(source_dir.path, target_dir.path)
        log.info(f'copied experiment directory from {source_dir.path} to {target_dir.path}')
    except OSError as e:
        raise ExperimentDirectoryCreationError(
            log,
            message=f'failed to clone experiment directory: {e.strerror}'
        )

    if environments:
        metadata = target_dir.load_metadata()
        metadata.environments = environments
        target_dir.save_metadata(metadata)
        log.info(f'updated cloned experiment environments to: {", ".join(environments)}')

    experiment_load(project_path, target_experiment, force=False, silent=True)
    log.info(f'loaded cloned experiment {target_experiment} into database')

    source_metadata = source_dir.load_metadata()
    target_metadata = target_dir.load_metadata()

    next_steps = [
        f'Edit cloned experiment files in: {target_dir.path}',
        f'Run the cloned experiment with: adare experiment run {target_experiment} -e <environment>'
    ]

    if environments:
        env_info = f'Cloned with custom environments: {", ".join(environments)}'
    else:
        env_info = f'Cloned with original environments: {", ".join(source_metadata.environments)}'

    print_success_message(
        title=f'Experiment "{target_experiment}" cloned from "{source_experiment}" successfully!',
        location=str(target_dir.path),
        next_steps=next_steps,
        tip=env_info
    )


def experiment_example(project_path: Path, experiment: str):
    experiment_directory = ExperimentDirectory(project_path, experiment)
    if experiment_directory.exists():
        raise ExperimentDirectoryAlreadyExistsError(
            log, f'experiment directory [b]{experiment_directory.path}[/b] already exists'
        )
    experiment_directory.retrieve_example(experiment)
    log.info(f'experiment directory {experiment_directory.path} created')
    # todo: make this available in metadata of the experiment (or user need to manually download it)
    project_directory = ProjectDirectory(project_path)
    project_directory.download_tool('https://download.ericzimmermanstools.com/RBCmd.zip', zipped=True)


def __experiment_update(project_path: Path, experiment_ulid, experiment_name, experiment_directory, force):
    from adare.database.api.experiment import ExperimentApi

    # Detect environment changes before updating
    env_changes_detected = False
    added_envs = []
    removed_envs = []

    try:
        with ExperimentApi(project_path) as api:
            # Get current environments from database
            old_env_names = api.get_experiment_environment_names(experiment_ulid)

            # Get new environments from metadata.yml
            new_metadata = experiment_directory.load_metadata()
            new_env_names = new_metadata.environments

            # Calculate diff
            old_set = set(old_env_names)
            new_set = set(new_env_names)
            added_envs = list(new_set - old_set)
            removed_envs = list(old_set - new_set)

            if added_envs or removed_envs:
                env_changes_detected = True
                log.info(f'Detected environment changes for experiment {experiment_name}')
                if added_envs:
                    log.info(f'  + Added: {", ".join(added_envs)}')
                if removed_envs:
                    log.info(f'  - Removed: {", ".join(removed_envs)}')
    except Exception as e:
        log.warning(f'Failed to detect environment changes: {e}')

    if not force and not experiment_database.check_for_experiment_change(project_path, experiment_ulid, experiment_directory.sha256):
        raise ExperimentNotChanged(log, f'experiment [i]{experiment_ulid}[/i] has not changed')
    log.info(f'experiment {experiment_ulid} has changed')
    num_runs = experiment_database.get_experiment_run_count(project_path, experiment_ulid, exclude_fake=True)
    if not force and num_runs > 0:
        raise LoggedException(log,
                              f'experiment [i]{experiment_ulid}[/i] has changed, use --force to overwrite and delete all related experiment runs')
    # delete the experiment and all related experiment runs
    experiment_database.remove_experiment(project_path, experiment_ulid)
    log.info(f'experiment {experiment_ulid} removed')
    ulid = experiment_database.create_experiment(
        name=experiment_name,
        experiment_directory=experiment_directory
    )
    log.info(f'experiment {experiment_ulid} created')

    # Print user-friendly message about environment changes
    if env_changes_detected:
        print(f'Experiment {experiment_name} (ulid: {ulid}) was loaded successfully')
        if added_envs or removed_envs:
            print(f'  Environment changes detected:')
            if added_envs:
                print(f'    + Added: {", ".join(added_envs)}')
            if removed_envs:
                print(f'    - Removed: {", ".join(removed_envs)}')
    else:
        print(f'Experiment {experiment_name} (ulid: {ulid}) was loaded successfully')


def __validate_testset_compatibility(experiment_directory: ExperimentDirectory):
    """Validate testset against available testfunctions during experiment loading."""
    playbook_path = experiment_directory.path / "playbook.yml"
    if not playbook_path.exists():
        log.info("No playbook.yml found - skipping testset validation")
        return  # No playbook to validate

    # Use global testfunctions directory only
    from adare.config.configdirectory import STATE_DIR
    testfunctions_dir = STATE_DIR / 'testfunctions'

    if not testfunctions_dir.exists():
        log.warning(f"Global testfunctions directory not found: {testfunctions_dir} - skipping validation")
        log.info("Load testfunctions using 'adare testfunction load-global <path>' to enable validation")
        return

    log.debug(f"Using global testfunctions directory: {testfunctions_dir}")

    try:
        from adarelib.testset.testfunction import import_basictest_subclasses, get_missing_testfunctions

        log.info("Validating testset compatibility with available testfunctions...")

        # Load testset from playbook
        testsetfile = experiment_directory.load_testset()

        # Try database-driven approach first, fallback to directory scanning
        supported_tests = None
        try:
            # Get testfunction data from database
            testfunction_source = _get_testfunction_data_from_database()
            if testfunction_source:
                log.debug("Using database-driven testfunction loading")
                supported_tests = import_basictest_subclasses(source=testfunction_source)
        except Exception as e:
            log.warning(f"Database-driven testfunction loading failed: {e}")

        # Fallback to directory scanning if database approach failed
        if not supported_tests:
            log.debug("Using directory-based testfunction loading")
            supported_tests = import_basictest_subclasses(directory=testfunctions_dir)

        # Check for missing testfunctions
        missing = get_missing_testfunctions(testsetfile, supported_tests)

        if missing:
            raise ExperimentIntegrityError(
                log,
                f"Testset contains unsupported testfunctions: {missing}",
                possible_solutions=[
                    "Load missing testfunction implementations using 'adare testfunction load-global <path>'",
                    "Remove invalid tests from testset.yml",
                    "Check testfunction naming matches class names",
                    "Ensure testfunction files are properly structured"
                ]
            )

        log.info(f"Testset validation passed - all {len(testsetfile.tests)} tests have valid testfunctions")
        
    except ImportError as e:
        log.warning(f"Could not import testset validation modules: {e}")
        log.warning("Skipping testset validation - validation will occur at runtime")
    except Exception as e:
        log.error(f"Testset validation error: {e}", exc_info=True)
        raise ExperimentIntegrityError(
            log,
            f"Testset validation failed: {str(e)}",
            possible_solutions=[
                "Check testset.yml syntax and structure",
                "Verify testfunctions directory structure",
                "Ensure all required testfunction dependencies are available"
            ]
        )


def experiment_load(project_path: Path, experiment_name: str, force: bool = False, silent: bool = False):
    from adare.console import print_success_message
    
    # todo: fix bug that we can have two identical experiments
    experiment_directory = ExperimentDirectory(project_path, experiment_name)
    if not experiment_directory.exists():
        raise ExperimentDirectoryDoesNotExistError(
            log, f'experiment directory [b]{experiment_directory.path}[/b] does not exist',
            possible_solutions=[
                f'copy the experiment directory to [b]{experiment_directory.path.parent}[/b]',
                'create the experiment directory with `adare experiment create`'
            ]
        )
    experiment_directory.check_for_missing_files()

    # Validate testset compatibility with available testfunctions
    __validate_testset_compatibility(experiment_directory)
    
    was_updated = False
    if experiment_ulid := experiment_database.get_experiment_by_project_and_name(
            project_path, experiment_name, trigger_error=False
    ):
        try:
            __experiment_update(
                project_path, experiment_ulid, experiment_name, experiment_directory, force
            )
            was_updated = True
        except ExperimentNotChanged as e:
            experiment_sync(project_path, experiment_ulid)
    else:
        # Create experiment atomically (playbook population is now part of the transaction)
        experiment_ulid = experiment_database.create_experiment(
            name=experiment_name,
            experiment_directory=experiment_directory,
            project_path=project_path
        )
        log.info(f'experiment {experiment_name} created')

    experiment_sync(project_path, experiment_ulid)
    
    # Protect experiment files after loading
    from adare.helperfunctions.integrity import protect_loaded_files
    experiment_files = [experiment_directory.playbookfile]
    if experiment_directory.metadatafile.exists():
        experiment_files.append(experiment_directory.metadatafile)
    protected_files = protect_loaded_files(experiment_files)
    log.info(f'Protected {len(protected_files)} experiment files')
    
    # Provide clear user feedback only if not in silent mode
    if not silent:
        action = "updated" if was_updated else "loaded"
        next_steps = [
            f'Run the experiment with: adare experiment run {experiment_name} -e <environment>',
        ]
        
        print_success_message(
            title=f'Experiment "{experiment_name}" {action} successfully!',
            location=str(experiment_directory.path),
            next_steps=next_steps,
            tip=f'show the experiment info with `adare experiment info {experiment_name}` to see the details',
        )




def experiment_download(project: Path, experiment_ulid: str):
    if not is_logged_in():
        raise NotLoggedInError(log)
    # check if experiment exists in database
    exp = experiment_database.get_experiment_by_ulid(experiment_ulid)
    if exp:
        raise ExperimentAlreadyExistsError(
            log,
            f'experiment {exp} already exists',
        )

    # download experiment from webapp
    project = ProjectDirectory(project)
    experiment_name = download_experiment(experiment_ulid, project.experiments)
    log.info(f'experiment {experiment_ulid} downloaded')
    print(f'experiment {experiment_name} ({experiment_ulid}) downloaded successfully')



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
                print(f'No fake runs found for experiment "{experiment_name}" - nothing to clean')

    except ValueError as e:
        from adare.exceptions import LoggedException
        raise LoggedException(log, str(e))
    except Exception as e:
        from adare.exceptions import LoggedException
        raise LoggedException(log, f'Failed to clean experiment "{experiment_name}": {str(e)}')


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



def experiment_remove_environments(project_path: Path, experiment_pattern: str, environment_names: list[str], force: bool = False):
    """Remove environments from experiments matching the pattern."""
    from adare.console import print_success_message
    import glob

    # Find matching experiments using glob
    project_directory = ProjectDirectory(project_path)
    experiments_dir = project_directory.experiments

    # Use glob to find matching experiment directories
    pattern_path = experiments_dir / experiment_pattern
    matching_paths = glob.glob(str(pattern_path))

    if not matching_paths:
        from adare.exceptions import LoggedErrorException
        raise LoggedErrorException(
            log,
            f'No experiments found matching pattern: {experiment_pattern}',
            possible_solutions=[
                f'Check if pattern "{experiment_pattern}" is correct',
                'List experiments with: adare experiment list',
                'Use exact experiment name if no pattern matching needed'
            ]
        )

    # Extract experiment names from paths
    experiment_names = [Path(p).name for p in matching_paths]

    print(f"Found {len(experiment_names)} experiment(s) matching pattern '{experiment_pattern}':")
    for exp_name in experiment_names:
        print(f"  - {exp_name}")
    print(f"Removing environment(s): {', '.join(environment_names)}")
    print()

    # Process each experiment
    updated_experiments = []
    failed_experiments = []

    for exp_name in experiment_names:
        try:
            exp_dir = ExperimentDirectory(project_path, exp_name)
            if not exp_dir.exists():
                log.warning(f"Experiment directory not found: {exp_name}, skipping")
                failed_experiments.append(exp_name)
                continue

            # Load current metadata
            metadata = exp_dir.load_metadata()
            original_envs = set(metadata.environments)

            # Remove specified environments
            envs_to_remove = set(environment_names)
            updated_envs = original_envs - envs_to_remove

            # Check if anything actually changed
            if updated_envs == original_envs:
                log.info(f"Experiment '{exp_name}' doesn't have any of the specified environments, skipping")
                continue

            # Validate that we're not removing all environments
            if not updated_envs:
                if not force:
                    log.warning(f"Cannot remove all environments from experiment '{exp_name}' without --force flag")
                    failed_experiments.append(exp_name)
                    continue
                else:
                    log.warning(f"Removing ALL environments from experiment '{exp_name}' due to --force flag")

            # Update metadata
            metadata.environments = sorted(list(updated_envs))

            # Save updated metadata
            exp_dir.save_metadata(metadata)
            log.info(f"Updated metadata for experiment: {exp_name}")

            # Reload experiment to update database (if it still has environments)
            if updated_envs:
                experiment_load(project_path, exp_name, force=True, silent=True)
                log.info(f"Reloaded experiment: {exp_name}")
            else:
                log.warning(f"Experiment '{exp_name}' now has no environments and may become inaccessible")

            updated_experiments.append(exp_name)

        except Exception as e:
            log.error(f"Failed to update experiment '{exp_name}': {e}")
            failed_experiments.append(exp_name)

    # Print summary
    if updated_experiments:
        print_success_message(
            title=f"Successfully removed environments from {len(updated_experiments)} experiment(s)",
            location=f"Experiments: {', '.join(updated_experiments)}",
            next_steps=[
                f"Removed environments: {', '.join(environment_names)}",
                "Experiments have been reloaded automatically",
                "Check remaining environments with: adare experiment info <name>"
            ]
        )

    if failed_experiments:
        log.warning(f"Failed to update {len(failed_experiments)} experiment(s): {', '.join(failed_experiments)}")


def experiment_add_environments(project_path: Path, experiment_pattern: str, environment_names: list[str], force: bool = False):
    """Add environments to experiments matching the pattern."""
    from adare.console import print_success_message
    import glob

    # Find matching experiments using glob
    project_directory = ProjectDirectory(project_path)
    experiments_dir = project_directory.experiments

    # Use glob to find matching experiment directories
    pattern_path = experiments_dir / experiment_pattern
    matching_paths = glob.glob(str(pattern_path))

    if not matching_paths:
        from adare.exceptions import LoggedErrorException
        raise LoggedErrorException(
            log,
            f'No experiments found matching pattern: {experiment_pattern}',
            possible_solutions=[
                f'Check if pattern "{experiment_pattern}" is correct',
                'List experiments with: adare experiment list',
                'Use exact experiment name if no pattern matching needed'
            ]
        )

    # Extract experiment names from paths
    experiment_names = [Path(p).name for p in matching_paths]

    # Validate all environments exist in project before proceeding
    from adare.database.api.environment import EnvironmentDbApi
    with EnvironmentDbApi() as env_db:
        project_environments = {env.name for env in env_db.get_environments(project_path)}

    missing_envs = [env for env in environment_names if env not in project_environments]
    if missing_envs:
        from adare.exceptions import LoggedErrorException
        raise LoggedErrorException(
            log,
            f'Environment(s) not found in project: {", ".join(missing_envs)}',
            possible_solutions=[
                'Create missing environments with: adare environment create <name>',
                'Load existing environments with: adare environment load <file>',
                'List available environments with: adare environment list'
            ]
        )

    print(f"Found {len(experiment_names)} experiment(s) matching pattern '{experiment_pattern}':")
    for exp_name in experiment_names:
        print(f"  - {exp_name}")
    print(f"Adding environment(s): {', '.join(environment_names)}")
    print()

    # Process each experiment
    updated_experiments = []
    failed_experiments = []
    skipped_experiments = []  # Track experiments that already have the environments
    environment_missing_experiments = []  # Track experiments where environments aren't in global database

    for exp_name in experiment_names:
        try:
            exp_dir = ExperimentDirectory(project_path, exp_name)
            if not exp_dir.exists():
                log.warning(f"Experiment directory not found: {exp_name}, skipping")
                failed_experiments.append(exp_name)
                continue

            # Load current metadata
            metadata = exp_dir.load_metadata()
            original_envs = set(metadata.environments)

            # Add new environments (avoid duplicates)
            new_envs = set(environment_names)
            updated_envs = original_envs | new_envs

            # Check if anything actually changed
            if updated_envs == original_envs:
                log.info(f"Experiment '{exp_name}' already has all specified environments, skipping")
                skipped_experiments.append(exp_name)
                continue

            # Update metadata
            metadata.environments = sorted(list(updated_envs))

            # Save updated metadata
            exp_dir.save_metadata(metadata)
            log.info(f"Updated metadata for experiment: {exp_name}")

            # Reload experiment to update database
            experiment_load(project_path, exp_name, force=True, silent=True)
            log.info(f"Reloaded experiment: {exp_name}")

            updated_experiments.append(exp_name)

        except Exception as e:
            from adare.database.exceptions import EnvironmentMissingError
            if isinstance(e, EnvironmentMissingError):
                log.error(f"Environment(s) not found in global database for experiment '{exp_name}': {', '.join(environment_names)}")
                environment_missing_experiments.append(exp_name)
            else:
                log.error(f"Failed to update experiment '{exp_name}': {e}")
                failed_experiments.append(exp_name)

    # Print comprehensive summary
    total_processed = len(updated_experiments) + len(skipped_experiments) + len(failed_experiments) + len(environment_missing_experiments)

    if updated_experiments:
        print_success_message(
            title=f"Successfully added environments to {len(updated_experiments)} experiment(s)",
            next_steps=[
                f"Run experiment in new environments with: adare experiment run <name> -e <environment>",
            ]
        )

    if skipped_experiments:
        print(f"\n✓ {len(skipped_experiments)} experiment(s) already had the specified environment(s): {', '.join(skipped_experiments)}")

    if environment_missing_experiments:
        from adare.console import print_error_message
        print_error_message(
            title=f"Environment(s) not found in global database for {len(environment_missing_experiments)} experiment(s)",
            details=f"Experiments: {', '.join(environment_missing_experiments)}\nEnvironment(s): {', '.join(environment_names)}",
            possible_solutions=[
                "Check if environment names are spelled correctly",
                "Load environments to global database with: adare environment load <environment_file>",
                "Create environments with: adare environment create <name>",
                "List available environments with: adare environment list"
            ]
        )

    if failed_experiments:
        from adare.console import print_error_message
        print_error_message(
            title=f"Failed to update {len(failed_experiments)} experiment(s)",
            details=f"Experiments: {', '.join(failed_experiments)}",
            possible_solutions=[
                "Check experiment metadata.yml files for syntax errors",
                "Ensure experiment directories exist and are accessible",
                "Check log output above for specific error details"
            ]
        )

    # Final status summary
    if total_processed == 0:
        print("\nNo experiments were processed.")
    elif updated_experiments or skipped_experiments:
        print(f"\nSummary: {len(updated_experiments)} updated, {len(skipped_experiments)} already had environments, {len(environment_missing_experiments)} missing environments, {len(failed_experiments)} failed.")
    else:
        print(f"\nNo experiments were successfully updated. See error details above.")
