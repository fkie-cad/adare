# external imports
from pathlib import Path
import jinja2

# internal imports
from adare.backend.experiment.directory import ExperimentDirectory
import adare.backend.experiment.database as experiment_database
import adare.backend.project.database as project_database
from adare.backend.experiment.exceptions import ExperimentDirectoryAlreadyExistsError, ExperimentDirectoryDoesNotExistError, LoggedException
from adarelib.console import log_print


# configure logging
import logging
log = logging.getLogger(__name__)


def experiment_create(project_path: Path, experiment: str):

    experiment_directory = ExperimentDirectory(project_path, experiment)
    if experiment_directory.exists():
        raise ExperimentDirectoryAlreadyExistsError(
            log, f'experiment directory [b]{experiment_directory.path}[/b] already exists'
        )
    experiment_directory.create()
    log.info(f'experiment directory {experiment_directory.path} created')


def experiment_load(project_path: Path, experiment: str, force: bool = False):
    experiment_directory = ExperimentDirectory(project_path, experiment)
    if not experiment_directory.exists():
        raise ExperimentDirectoryDoesNotExistError(
            log, f'experiment directory [b]{experiment_directory.path}[/b] does not exist',
            possible_solutions=[
                'create the experiment directory with `adare experiment create`'
            ]
        )

    if experiment := experiment_database.get_latest_experiment_by_project_and_name(
        project_path, experiment
    ):
        # check if experiments files are the same or changed
        # if changed, create a new experiment entry with same name
        if experiment.sha256_hash == experiment_directory.sha256:
            raise LoggedException(log, f'experiment {experiment.name} has not changed')
        else:
            log.info(f'experiment {experiment.name} has changed')
            if not force:
                raise LoggedException(log, f'experiment {experiment.name} has changed, use --force to overwrite and delete all related experiment runs')
            else:
                # delete the experiment and all related experiment runs
                experiment_database.remove_experiment(experiment)
                log.info(f'experiment {experiment.name} removed')
                experiment_database.create_experiment(
                    name=experiment,
                    project_path=project_path,
                    experiment_directory=experiment_directory
                )
                log.info(f'experiment {experiment.name} created')

    else:
        # create a new experiment in the database
        experiment_database.create_experiment(
            name=experiment,
            project_path=project_path,
            experiment_directory=experiment_directory
        )















