# external imports
from pathlib import Path

# internal imports
from adare.database.models.experiments import Project, Experiment
from adare.database.api.experiment import ExperimentApi
from adare.database.api.environment import EnvironmentDbApi
from adare.backend.experiment.directory import ExperimentDirectory

# configure logging
import logging

log = logging.getLogger(__name__)


def get_latest_experiment_by_project_and_name(project_path: Path, experiment_name: str) -> str | None:
    with ExperimentApi() as api:
        experiment = api.get_latest_experiment_by_project_and_name(project_path, experiment_name)
        if experiment is None:
            log.error('experiment not found')
            return None
        return experiment.uuid


def create_experiment(name: str, project_path: Path, experiment_directory: ExperimentDirectory) -> Experiment:
    with ExperimentApi() as api:
        experiment = api.create_experiment(name, project_path, experiment_directory)
    return experiment


def remove_experiment(experiment_uuid: str):
    with ExperimentApi() as api:
        api.remove_experiment_by_uuid(experiment_uuid)


def check_for_experiment_change(experiment_uuid: str, sha256: str) -> bool:
    with ExperimentApi() as api:
        return not api.experiment_sha256_equals(experiment_uuid, sha256)


def get_environment_installations(environment_uuid: str):
    with EnvironmentDbApi() as api:
        return api.get_environment_installations(environment_uuid)


def get_environment_platform(environment_uuid: str):
    with EnvironmentDbApi() as api:
        return api.get_environment_platform(environment_uuid)


def get_environment_uuid(project_path: Path, experiment_name: str):
    with EnvironmentDbApi() as api:
        return api.get_environment(experiment_name, project_path.name).uuid if api.get_environment(experiment_name, project_path.name) else None


def get_environment_vagrant_box(environment_uuid: str):
    with EnvironmentDbApi() as api:
        return api.get_environment_vagrant_box(environment_uuid)
