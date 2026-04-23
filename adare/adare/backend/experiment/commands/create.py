# external imports
import logging
from pathlib import Path

# internal imports
from adare.backend.experiment.directory import ExperimentDirectory
from adare.backend.experiment.exceptions import (
    ExperimentDirectoryAlreadyExistsError,
    ExperimentDirectoryCreationError,
    ExperimentDirectoryDoesNotExistError,
)
from adare.backend.project.directory import ProjectDirectory

log = logging.getLogger(__name__)


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
    import shutil

    from adare.backend.experiment.commands.load import experiment_load
    from adare.console import print_success_message

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
                'choose a different name for the cloned experiment',
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
