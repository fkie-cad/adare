# external imports
from pathlib import Path


# internal imports
from adare.backend.attrs_classes import EnvironmentConfiguration
from adare.database.api.environment import EnvironmentDbApi

# configure logging
import logging
log = logging.getLogger(__name__)


class EnvironmentDatabase:
    project_path: Path

    def __init__(self, project_path: Path):
        self.project_path = project_path

    def update_environment(self, environment_configuration: EnvironmentConfiguration, environment_file: Path, sha256hash: str, force: bool = False) -> bool:
        with EnvironmentDbApi() as db:
            environments = db.get_environments_by_path(environment_file)
            if not environments:
                env, _ = db.get_or_create_environment(environment_configuration, environment_file, sha256hash)
                log.info(f'environment file {environment_file} loaded')
                return True
            latest_env = environments[-1]
            if latest_env.sha256hash == sha256hash:
                log.info(f'environment file {environment_file} already loaded')
                return True
            else:
                # check if the environment already has experiment runs
                if latest_env.runs:
                    if not force:
                        log.error(f'environment file {environment_file} has already been used for experiments, so it cannot be updated because this would invalidate the results -> run with --force to delete all runs and update the environment')
                        return False
                    else:
                        log.info(f'environment file {environment_file} has already been used for experiments -> deleting all runs')
                        for run in latest_env.runs:
                            # todo: implement run deletion
                            pass
                else:
                    log.info(f'environment file {environment_file} has already been loaded -> updating')
                    success = db.update_environment(environment_configuration, environment_file, sha256hash)
                    if not success:
                        log.error(f'environment file {environment_file} could not be updated')

        return True




