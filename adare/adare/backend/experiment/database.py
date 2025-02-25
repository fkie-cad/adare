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
from adarelib.config import StatusEnum

# configure logging
import logging
log = logging.getLogger(__name__)


def get_experiment_by_project_and_name(project_path: Path, experiment_name: str) -> str | None:
    with ExperimentApi() as api:
        experiment = api.get_experiment_by_project_and_name(project_path, experiment_name)
        if experiment is None:
            log.error('experiment not found')
            return None
        return experiment.ulid


def get_experiment_by_ulid(experiment_ulid: str) -> Experiment:
    with ExperimentApi() as api:
        return api.get_experiment_by_ulid(experiment_ulid)


def get_experiment_hashes(project_path: Path, environment_name: str, experiment_name: str) -> dict:
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


def get_experiment_run_count(project_path: Path, environment_name: str, experiment_name: str) -> int:
    with ExperimentApi() as api:
        experiment = api.get_experiment_by_project_and_name(project_path,  experiment_name)
        if experiment is None:
            log.error('experiment not found')
            raise ValueError('experiment not found')
        return len(experiment.runs)


def create_experiment(name: str, experiment_directory: ExperimentDirectory) -> str:
    with ExperimentApi() as api:
        experiment = api.create_experiment(name, experiment_directory)
        print(experiment.ulid)
        return experiment.ulid


def remove_experiment(experiment_ulid: str):
    with ExperimentApi() as api:
        api.remove_experiment_by_ulid(experiment_ulid)


def check_for_experiment_change(experiment_ulid: str, sha256: str) -> bool:
    with ExperimentApi() as api:
        return not api.experiment_sha256_equals(experiment_ulid, sha256)


def get_environment_installations(environment_ulid: str):
    with EnvironmentDbApi() as api:
        return api.get_environment_installations(environment_ulid)


def get_environment_platform(environment_ulid: str):
    with EnvironmentDbApi() as api:
        return api.get_environment_platform(environment_ulid)


def get_environment_ulid(project_path: Path, experiment_name: str):
    with EnvironmentDbApi() as api:
        return api.get_environment(experiment_name, project_path.name).ulid if api.get_environment(experiment_name, project_path.name) else None


def get_environment_vagrant_box(environment_ulid: str):
    with EnvironmentDbApi() as api:
        return api.get_environment_vagrant_box(environment_ulid)


def update_experiment_run(experiment_run_ulid: str, experiment_name: str, environment_name: str, project_name: str, experimentrun_directory: ExperimentRunDirectory) -> str:
    with ExperimentApi() as api:
        environment = api.get_environment(environment_name, project_name)
        experiment = api.get_experiment(experiment_name, environment)
        experiment_run = api.update_experiment_run(
            run_ulid=experiment_run_ulid,
            experiment=experiment,
            environment=environment,
            path=experimentrun_directory.path,
            logfile_vagrant=experimentrun_directory.vagrant_log_file,
            logfile_adarevm=experimentrun_directory.adarevm_log_file,
            status=StatusEnum.RUNNING,
        )
        return experiment_run.ulid


def initialize_experiment_run():
    with ExperimentApi() as api:
        return api.initialize_experiment_run().ulid


def update_experiment_run_start(experiment_run_ulid: str, timestamp: datetime):
    with ExperimentApi() as api:
        api.update_experiment_run_start(experiment_run_ulid, timestamp)

def update_experiment_run_end(experiment_run_ulid: str, timestamp: datetime):
    with ExperimentApi() as api:
        api.update_experiment_run_end(experiment_run_ulid, timestamp)


def get_experiment_testfunction_files(project_path: Path, environment_name: str,  experiment_name: str):
    testfunction_files = []
    with ExperimentApi() as api:
        experiment = api.get_experiment_by_project_and_name(project_path, experiment_name)
        for abs_test in experiment.abstract_tests:
            if abs_test.testfunction.file.name not in testfunction_files:
                testfunction_files.append(Path(abs_test.testfunction.file.path))
        return testfunction_files


def update_experiment_run_status(experiment_run_ulid: str, status: int):
    with ExperimentApi() as api:
        api.update_experiment_run_status(experiment_run_ulid, status)


def get_experiment_environment(project_path: Path, environment_name: str,  experiment_name: str):
    with ExperimentApi() as api:
        # todo: fix
        experiment = api.get_experiment_by_project_and_name(project_path,  experiment_name)
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


def update_stage_in_run(stage: StageType, experimentrun_ulid: str):
    with StageDbApi() as db:
        db.update_stage_in_run(stage, experimentrun_ulid)


def sync_experiment(ulid: str, remote_ulid: str, abstract_tests_ulids: dict, remote_url: str, is_published: bool):
    with ExperimentApi() as api:
        api.sync_experiment(ulid, remote_ulid, abstract_tests_ulids, remote_url, is_published)


def get_experiment_hash(ulid: str):
    with ExperimentApi() as api:
        return api.get_experiment_by_ulid(ulid).sha256


def get_experiments_ulids(project_path: Path):
    with ExperimentApi() as api:
        return [
            experiment.ulid
            for experiment in api.get_experiments(project_path)
        ]

