# external imports
import attrs
import sqlalchemy
from pathlib import Path

# internal imports
import adare.config.database as config_database
from adare.database.models.experiment import Environment, OsInfo, Project, PostSetupInstallation
from adare.types.environment import EnvironmentMetadata, OsInfo as OsInfoAttrs, PostsetupInstallations as PostsetupInstallationsAttrs
from adare.database.api.experiment import ExperimentApi
from adare.database.exceptions import DatabaseProjectNotFoundError

# configure logging
import logging

log = logging.getLogger(__name__)


class EnvironmentDbApi(ExperimentApi):

    def __init__(self, db_path: Path = config_database.get_database_location()):
        super().__init__(db_path)

    def get_or_create_os_info(self, os_info_attrs: OsInfoAttrs) -> tuple[OsInfo, bool]:
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

    def get_environment_by_ulid(self, ulid: str) -> Environment:
        return self._session.query(Environment).filter(Environment.id == ulid).first()
    
    def get_environment_by_hash(self, sha256hash: str) -> Environment:
        return self._session.query(Environment).filter(Environment.sha256hash == sha256hash).first()

    def __get_or_create_installations(self, installations: list[PostsetupInstallationsAttrs]) -> list[PostSetupInstallation]:
        installation_objects = []
        for installation in installations:
            installation_obj, created = self.get_or_create(PostSetupInstallation, **attrs.asdict(installation))
            installation_objects.append(installation_obj)
        return installation_objects

    def get_or_create_environment(self, project_path: Path, name: str, description: str, 
                                  vm_id: str, tags: list[str],
                                  installations: list[dict], environment_file: Path,
                                  sha256hash: str) -> tuple[Environment, bool]:
        environment = self._session.query(Environment).join(Project).filter(Environment.sha256hash == sha256hash,
                                                                            Project.path == project_path.as_posix()).first()
        if environment:
            log.info(f'Environment with hash {sha256hash} already exists in database')
            return environment, False
        log.info(f"Environment with hash '{sha256hash}' not found in database -> creating new entry")
        # OS info is now stored in the VM, not separately
        project = self._session.query(Project).filter(Project.path == project_path.as_posix()).first()
        if not project:
            raise DatabaseProjectNotFoundError(
                log,
                f"Project with path '{project_path}' not found in database -> cannot create environment"
            )
        tag_objects = self.get_or_create_tags(tags)
        environment = Environment(
            name=name,
            project=project,
            description=description,
            vm_id=vm_id,
            sha256hash=sha256hash,
            file=environment_file.as_posix(),
            tags=tag_objects
        )
        installation_objects = []
        for install_dict in installations:
            install_obj, _ = self.get_or_create(PostSetupInstallation, **install_dict)
            installation_objects.append(install_obj)
        environment.installations = installation_objects
        self._session.add(environment)
        self._session.commit()
        return environment, True

    def update_environment(self, name: str, description: str, vm_id: str, 
                          environment_file: Path, sha256hash: str) -> Environment | None:
        environment = self._session.query(Environment).filter(Environment.sha256hash == sha256hash).first()
        if not environment:
            log.error(f"Environment with hash '{sha256hash}' not found in database -> cannot update")
            return None
        if environment.runs:
            log.error(
                f"Environment with hash '{sha256hash}' has already been used for experiments, so it cannot be updated because this would invalidate the results")
            return None
        # OS info is now stored in the VM, not separately
        environment.name = name
        environment.description = description
        environment.vm_id = vm_id
        environment.file = environment_file.as_posix()
        self._session.commit()
        log.info(f"Environment with hash '{sha256hash}' updated in database")
        return environment

    def delete_environment(self, environment: Environment):
        self._delete_commit(environment)
        log.info(f"Environment with hash '{environment.sha256hash}' deleted from database")

    def get_environments(self, project_path: Path = None) -> list[Environment]:
        # retrieve all environments and expunge them from the session
        if project_path:
            projects = self._session.query(Project).filter(Project.path == project_path.as_posix()).all()
            environments = [env for project in projects for env in project.environments]
        else:
            environments = self._session.query(Environment).all()
        return environments



    # def get_environments(self, project_path: Path = None) -> list:
    #     # retrieve all environments and expunge them from the session
    #     if project_path:
    #         projects = self._session.query(Project).filter(Project.path == project_path.as_posix()).all()
    #         environments = [env for project in projects for env in project.environments]
    #     else:
    #         environments = self._session.query(Environment).all()
    #
    #     # get all experiment with at least one run in the environment.runs list
    #     experiment_per_env = {}
    #     for environment in environments:
    #         experiments = {run.experiment.name for run in environment.runs}
    #         experiment_per_env[environment.id] = [
    #             {
    #                 'name': experiment.name,
    #                 'runs': len([run for run in environment.runs if run.experiment.name == experiment.name])
    #             }
    #             for experiment in experiments
    #         ]
    #
    #     # get count of runs for each environment for each experiment
    #     for env in environments:
    #         self._expunge_multiple(env.runs)
    #     self._expunge_multiple(environments)
    #
    #     return [
    #         {
    #             'name': env.name,
    #             'description': env.description,
    #             'experiments': experiment_per_env[env.id],
    #         }
    #         for env in environments
    #     ]

    def get_environment_installations(self, environment_ulid: str):
        if (
            env := self._session.query(Environment)
            .filter_by(ulid=environment_ulid)
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
            raise ValueError(f'environment {environment_ulid} not found in database')

    def get_environment_platform(self, environment_ulid: str):
        if (
            env := self._session.query(Environment)
            .filter_by(ulid=environment_ulid)
            .first()
        ):
            return env.osinfo.platform
        else:
            raise ValueError(f'environment {environment_ulid} not found in database')

    def get_environment(self, name: str, project_name: str) -> Environment:
        if (
            env := self._session.query(Environment)
            .filter_by(name=name)
            .join(Project)
            .filter(Project.name == project_name)
            .first()
        ):
            return env
        log.error(f'environment {name} not found in database')
        raise None

    def get_environment_vm(self, environment_ulid: str) -> str:
        if (
            env := self._session.query(Environment)
            .filter_by(ulid=environment_ulid)
            .first()
        ):
            return env.vm.name if env.vm else None
        else:
            raise ValueError(f'environment {environment_ulid} not found in database')

    def get_environment_by_project_and_name(self, project_path: Path, environment_name: str) -> Environment:
        if (
            project := self._session.query(Project)
            .filter(Project.path == project_path.as_posix())
            .first()
        ):
            return self._session.query(Environment).filter_by(name=environment_name, project=project).first()
        else:
            raise DatabaseProjectNotFoundError(
                log,
                f"Project with path '{project_path}' not found in database -> cannot get environment"
            )

    def sync_environment(self, ulid: str, remote_ulid: str, remote_url: str, is_published: bool):
        environment = self.get_environment_by_ulid(ulid)
        environment.remote_ulid = remote_ulid
        environment.remote_url = remote_url
        environment.published = is_published
        environment.in_request = True if not is_published else False
        self._session.commit()
