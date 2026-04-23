# external imports
import logging
from pathlib import Path

import adare.backend.experiment.database as experiment_database

# internal imports
from adare.backend.experiment.commands.validate import __validate_testset_compatibility
from adare.backend.experiment.directory import ExperimentDirectory
from adare.backend.experiment.exceptions import (
    ExperimentAlreadyExistsError,
    ExperimentDirectoryDoesNotExistError,
    ExperimentNotChanged,
)
from adare.backend.project.directory import ProjectDirectory
from adare.exceptions import LoggedException, NotLoggedInError
from adare.webappaccess.download import download_experiment, sync
from adare.webappaccess.login import is_logged_in

log = logging.getLogger(__name__)


def experiment_sync(project_path: Path, experiment_ulid: str):
    if not is_logged_in():
        log.info('sync is not possible because user is not logged in')
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

    # Log user-friendly message about environment changes
    if env_changes_detected:
        log.info(f'Experiment {experiment_name} (ulid: {ulid}) was loaded successfully')
        if added_envs or removed_envs:
            log.info('  Environment changes detected:')
            if added_envs:
                log.info(f'    + Added: {", ".join(added_envs)}')
            if removed_envs:
                log.info(f'    - Removed: {", ".join(removed_envs)}')
    else:
        log.info(f'Experiment {experiment_name} (ulid: {ulid}) was loaded successfully')


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
        except ExperimentNotChanged:
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
    log.info(f'experiment {experiment_name} ({experiment_ulid}) downloaded successfully')
