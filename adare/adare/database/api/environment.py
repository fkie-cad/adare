# external imports
import attrs
import sqlalchemy
from pathlib import Path

# internal imports
import adare.config.database as config_database
from adare.database.models.experiment import Environment, OsInfo, Experiment, ExperimentRun, Project, PostSetupInstallation
from adare.database.api.database import DatabaseApi
from adarelib.types.backend import EnvironmentMetadata, OsInfo as OsInfoAttrs, PostsetupInstallations as PostsetupInstallationsAttrs
from adare.database.api.experiment import ExperimentApi
from adare.database.exceptions import DatabaseProjectNotFoundError

# configure logging
import logging

log = logging.getLogger(__name__)


class EnvironmentDbApi(ExperimentApi):

    def __init__(self, db_path: Path = config_database.get_database_location()):
        super().__init__(db_path)

    def get_or_create_os_info(self, os_info_attrs: OsInfoAttrs) -> (OsInfo, bool):
        os_info_dict = attrs.asdict(os_info_attrs)
        os_info = self._session.query(OsInfo).filter_by(**os_info_dict).first()
        if os_info:
            return os_info, False
        os_info = OsInfo(**os_info_dict)
        self._add_commit(os_info)
        return os_info, True

    def get_environments_by_path(self, path: Path) -> list[Environment]:
        """ returns a list of environments with the given path sorted by creation date"""
        return self._session.query(Environment).filter(Environment.file == path.as_posix()).order_by(
            sqlalchemy.desc(Environment.created_at)).all()

    def get_environment_by_uuid(self, uuid: str) -> Environment:
        return self._session.query(Environment).filter(Environment.uuid == uuid).first()

    def __get_or_create_installations(self, installations: list[PostsetupInstallationsAttrs]) -> list[PostSetupInstallation]:
        installation_objects = []
        for installation in installations:
            installation_obj, created = self.get_or_create(PostSetupInstallation, **attrs.asdict(installation))
            installation_objects.append(installation_obj)
        return installation_objects

    def get_or_create_environment(self, project_path: Path, environment_metadata: EnvironmentMetadata, environment_file:Path,
                                  sha256hash: str) -> Environment:
        environment = self._session.query(Environment).filter(Environment.sha256hash == sha256hash).first()
        if environment:
            return environment
        log.info(f"Environment with hash '{sha256hash}' not found in database -> creating new entry")
        os_info, _ = self.get_or_create_os_info(environment_metadata.os)
        project = self._session.query(Project).filter(Project.path == project_path.as_posix()).first()
        if not project:
            raise DatabaseProjectNotFoundError(
                log,
                f"Project with path '{project_path}' not found in database -> cannot create environment"
            )
        environment = Environment(
            name=environment_metadata.name,
            project=project,
            description=environment_metadata.description,
            vagrantbox=environment_metadata.vagrantbox,
            osinfo=os_info,
            sha256hash=sha256hash,
            file=environment_file.as_posix(),
        )
        environment.installations = self.__get_or_create_installations(environment_metadata.postsetupinstallations)
        self._session.add(environment)
        self._session.commit()
        return environment

    def update_environment(self, environment_metadata: EnvironmentMetadata, environment_file: Path,
                           sha256hash: str) -> bool:
        environment = self._session.query(Environment).filter(Environment.sha256hash == sha256hash).first()
        if not environment:
            log.error(f"Environment with hash '{sha256hash}' not found in database -> cannot update")
            return False
        if environment.runs:
            log.error(
                f"Environment with hash '{sha256hash}' has already been used for experiments, so it cannot be updated because this would invalidate the results")
            return False
        os_info, _ = self.get_or_create_os_info(environment_metadata.os)
        environment.name = environment_metadata.name
        environment.description = environment_metadata.description
        environment.vagrantbox = environment_metadata.vagrantbox
        environment.osinfo = os_info
        environment.file = environment_file.as_posix()
        self._session.commit()
        log.info(f"Environment with hash '{sha256hash}' updated in database")

    def delete_environment(self, environment: Environment):
        self._delete_commit(environment)
        log.info(f"Environment with hash '{environment.sha256hash}' deleted from database")

    def get_environments(self, project_path: Path = None) -> list:
        # retrieve all environments and expunge them from the session
        if project_path:
            projects = self._session.query(Project).filter(Project.path == project_path.as_posix()).all()
            environments = [env for project in projects for env in project.environments]
        else:
            environments = self._session.query(Environment).all()

        # get all experiment with at least one run in the environment.runs list
        experiment_per_env = {}
        for environment in environments:
            experiments = {run.experiment.name for run in environment.runs}
            experiment_per_env[environment.uuid] = [
                {
                    'name': experiment.name,
                    'runs': len([run for run in environment.runs if run.experiment.name == experiment.name])
                }
                for experiment in experiments
            ]

        # get count of runs for each environment for each experiment
        for env in environments:
            self._expunge_multiple(env.runs)
        self._expunge_multiple(environments)

        return [
            {
                'name': env.name,
                'description': env.description,
                'experiments': experiment_per_env[env.uuid],
            }
            for env in environments
        ]

    def get_environment_installations(self, environment_uuid: str):
        if (
            env := self._session.query(Environment)
            .filter_by(uuid=environment_uuid)
            .first()
        ):
            return [
                PostsetupInstallationsAttrs(
                    name=installation.name,
                    command=installation.command,
                    description=installation.description
                ) for installation in env.installations
            ]
        else:
            raise ValueError(f'environment {environment_uuid} not found in database')

    def get_environment_platform(self, environment_uuid: str):
        if (
            env := self._session.query(Environment)
            .filter_by(uuid=environment_uuid)
            .first()
        ):
            return env.osinfo.platform
        else:
            raise ValueError(f'environment {environment_uuid} not found in database')

    def get_environment(self, name: str, project_name: str):
        if (
            env := self._session.query(Environment)
            .filter_by(name=name)
            .join(Project)
            .filter(Project.name == project_name)
            .first()
        ):
            return env
        else:
            raise ValueError(f'environment {name} not found in database')

    def get_environment_vagrant_box(self, environment_uuid: str):
        if (
            env := self._session.query(Environment)
            .filter_by(uuid=environment_uuid)
            .first()
        ):
            return env.vagrantbox
        else:
            raise ValueError(f'environment {environment_uuid} not found in database')
