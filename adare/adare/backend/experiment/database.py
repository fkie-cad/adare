# external imports
from pathlib import Path

# internal imports
from adare.database.models.experiments import Project, Experiment
from adare.database.api.experiment import ExperimentApi
from adare.backend.experiment.directory import ExperimentDirectory


# configure logging
import logging
log = logging.getLogger(__name__)


def get_latest_experiment_by_project_and_name(project_path: Path, experiment_name: str) -> Experiment | None:
    with ExperimentApi() as api:
        experiment = api.get_latest_experiment_by_project_and_name(project_path, experiment_name)
    if experiment is None:
        log.error('experiment not found')
        return None
    return experiment


def create_experiment(name: str, project_path: Path, experiment_directory: ExperimentDirectory) -> Experiment:
    with ExperimentApi() as api:
        experiment = api.create_experiment(name, project_path, experiment_directory)
    return experiment


def remove_experiment(experiment: Experiment):
    with ExperimentApi() as api:
        api.remove_experiment(experiment)

