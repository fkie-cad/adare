# external imports
from pathlib import Path


# internal imports
from adarelib.types import EnvironmentMetadata
from adare.database.api.environment import EnvironmentDbApi
from adare.database.models.experiments import Environment

# configure logging
import logging
log = logging.getLogger(__name__)


def update_environment(project_path: Path, environment_metadata: EnvironmentMetadata, environment_file: Path, sha256hash: str, force: bool = False) -> bool:
    with EnvironmentDbApi() as db:
        environments = db.get_environments_by_path(environment_file)
        if not environments:
            env, _ = db.get_or_create_environment(project_path, environment_metadata, environment_file, sha256hash)
            log.info(f'environment file {environment_file} loaded')
            return True
        for env in environments:
            if env.sha256hash == sha256hash:
                log.error(f'environment already exists (uuid: {env.uuid}) -> skipping')
                return False
        # check if the environment already has experiment runs
        latest_env = environments[-1]
        if latest_env.runs:
            if not force:
                log.error(f'environment file {environment_file} has already been used for experiments, so it cannot be updated because this would invalidate the results -> run with --force to delete all runs and update the environment')
                return False
            else:
                log.info(f'environment file {environment_file} has already been used for experiments -> deleting all runs')
                for run in latest_env.runs:
                    db.delete_experiment_run(run)
                    log.info(f'deleted run {run.uuid}')
                # update the environment
                db.update_environment(environment_metadata, environment_file, sha256hash)
                log.info(f'environment {environment_metadata.name} updated')
        else:
            log.info(f'environment file {environment_file} has already been loaded -> updating')
            success = db.update_environment(environment_metadata, environment_file, sha256hash)
            if not success:
                log.error(f'environment file {environment_file} could not be updated')
    return True


def delete_environment(environment_uuid: str, force: bool = False) -> bool:
    with EnvironmentDbApi() as db:
        environment = db.get_environment_by_uuid(environment_uuid)
        if not environment:
            log.error(f'environment {environment_uuid} does not exist')
            return False
        if environment.runs:
            if force:
                log.info(f'environment {environment.uuid} has already been used for experiments -> deleting all runs')
                for run in environment.runs:
                    db.delete_experiment_run(run)
                    log.info(f'deleted run {run.uuid}')
            else:
                log.error(f'environment {environment.uuid} has already been used for experiments, so it cannot be deleted because this would invalidate the results -> run with --force to delete all runs and the environment')
                return False
        db.delete_environment(environment)
        log.info(f'deleted environment {environment.uuid}')
    return True


def get_environments(project_path: Path = None) -> list[Environment]:
    with EnvironmentDbApi() as db:
        return db.get_environments(project_path)
