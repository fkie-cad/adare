# external imports
from pathlib import Path
from datetime import datetime

# internal imports
from adare.database.models.experiment import Project, Experiment, StageInRun
from adare.database.api.experiment import ExperimentApi
from adare.database.api.environment import EnvironmentDbApi
from adare.database.api.stage import StageDbApi
from adare.backend.experiment.directory import ExperimentDirectory, ExperimentRunDirectory
from adare.backend.experiment.exceptions import NoEnvironmentError, MultipleEnvironmentsError
from adarelib.types.stage import Stage as StageType

# configure logging
import logging
log = logging.getLogger(__name__)


def get_experiment_by_project_and_name(project_path: Path, experiment_name: str) -> str | None:
    with ExperimentApi() as api:
        experiment = api.get_experiment_by_project_and_name(project_path, experiment_name)
        if experiment is None:
            log.error('experiment not found')
            return None
        return experiment.uuid


def get_experiment_hashes(project_path: Path, experiment_name: str) -> dict:
    with ExperimentApi() as api:
        experiment = api.get_experiment_by_project_and_name(project_path, experiment_name)
        if experiment is None:
            log.error('experiment not found')
            raise ValueError('experiment not found')
        return {
            'experiment': experiment.sha256,
            'action': experiment.sha256_action,
            'testset': experiment.sha256_testset,
            'metadata': experiment.sha256_metadata,
        }


def get_experiment_run_count(project_path: Path, experiment_name: str) -> int:
    with ExperimentApi() as api:
        experiment = api.get_experiment_by_project_and_name(project_path, experiment_name)
        if experiment is None:
            log.error('experiment not found')
            raise ValueError('experiment not found')
        return len(experiment.runs)


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


def update_experiment_run(experiment_run_uuid: str, experiment_name: str, environment_name: str, project_name: str, experimentrun_directory: ExperimentRunDirectory) -> str:
    with ExperimentApi() as api:
        environment = api.get_environment(environment_name, project_name)
        experiment = api.get_experiment(experiment_name, environment)
        experiment_run = api.update_experiment_run(
            run_uuid=experiment_run_uuid,
            experiment=experiment,
            environment=environment,
            path=experimentrun_directory.path,
            logfile_vagrant=experimentrun_directory.vagrant_log,
            logfile_run_experiment=experimentrun_directory.run_log,
            logfile_installed_packages=experimentrun_directory.packagedump_log,
            logfile_postsetup_installations=experimentrun_directory.install_log,
            status='running',
        )
        return experiment_run.uuid


def initialize_experiment_run():
    with ExperimentApi() as api:
        return api.initialize_experiment_run().uuid


def update_experiment_run_start(experiment_run_uuid: str, timestamp: datetime):
    with ExperimentApi() as api:
        api.update_experiment_run_start(experiment_run_uuid, timestamp)


def get_experiment_testfunction_files(project_path: Path, experiment_name: str):
    testfunction_files = []
    with ExperimentApi() as api:
        experiment = api.get_experiment_by_project_and_name(project_path, experiment_name)
        for abs_test in experiment.abstract_tests:
            if abs_test.testfunction.file.name not in testfunction_files:
                testfunction_files.append(Path(abs_test.testfunction.file.path))
        return testfunction_files


def update_experiment_run_status(experiment_run_uuid: str, status: int):
    with ExperimentApi() as api:
        api.update_experiment_run_status(experiment_run_uuid, status)


def get_experiment_environment(project_path: Path, experiment_name: str):
    with ExperimentApi() as api:
        experiment = api.get_experiment_by_project_and_name(project_path, experiment_name)
        if experiment is None:
            log.error('experiment not found')
            raise ValueError('experiment not found')
        if len(experiment.environments) == 0:
            log.error('experiment has no environment')
            raise NoEnvironmentError(
                log,
                f'experiment {experiment} has no environment',
            )
        elif len(experiment.environments) > 1:
            raise MultipleEnvironmentsError(
                log,
                f'experiment {experiment} has multiple environments',
                possible_solutions=[
                    'specify the environment with -e <environment>'
                ]
            )
        return Path(experiment.environments[0].file)


def update_stage_in_run(stage: StageType, experimentrun_uuid: str):
    with StageDbApi() as db:
        db.update_stage_in_run(stage, experimentrun_uuid)
