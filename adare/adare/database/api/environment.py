# external imports
# configure logging
import logging
from pathlib import Path

import attrs
import sqlalchemy

# internal imports
from adare.database.api.base import GlobalDatabaseApi
from adare.database.models.global_models import Environment, OsInfo, PostSetupInstallation, Tag
from adare.types.environment import OsInfo as OsInfoAttrs
from adare.types.environment import PostsetupInstallations as PostsetupInstallationsAttrs

log = logging.getLogger(__name__)


class EnvironmentDbApi(GlobalDatabaseApi):

    def __init__(self):
        super().__init__()
        self._start_session()

    def get_or_create_os_info(self, os_info_attrs: OsInfoAttrs) -> tuple[OsInfo, bool]:
        os_info_dict = attrs.asdict(os_info_attrs)
        os_info = self._session.query(OsInfo).filter_by(**os_info_dict).first()
        if os_info:
            return os_info, False
        os_info = OsInfo(**os_info_dict)
        self._session.add(os_info)
        self._session.commit()
        return os_info, True

    def get_environments_by_path(self, path: Path) -> list[Environment]:
        """ returns a list of environments with the given path sorted by creation date"""
        return self._session.query(Environment).filter(Environment.file == path.as_posix()).order_by(
            sqlalchemy.desc(Environment.created_at)).all()

    def get_or_create_tags(self, tag_names: list[str]) -> list:
        """
        Get or create multiple tags.

        Args:
            tag_names: List of tag names

        Returns:
            List of Tag instances
        """
        tags = []
        for name in tag_names:
            if name and name.strip():
                tag, _ = self.get_or_create(Tag, name=name.strip().lower())
                tags.append(tag)
        return tags

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
                                  sha256hash: str, hypervisor: str = 'virtualbox') -> tuple[Environment, bool]:
        # For global environments, check by hash only (no project dependency)
        environment = self._session.query(Environment).filter(Environment.sha256hash == sha256hash).first()
        if environment:
            log.info(f'Environment with hash {sha256hash} already exists in database')
            return environment, False
        log.info(f"Environment with hash '{sha256hash}' not found in database -> creating new entry")

        tag_objects = self.get_or_create_tags(tags)
        environment = Environment(
            name=name,
            description=description,
            vm_id=vm_id,
            sha256hash=sha256hash,
            hypervisor=hypervisor,
            file=environment_file.resolve().as_posix(),  # Store absolute path
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
                          environment_file: Path, sha256hash: str, hypervisor: str = 'virtualbox') -> Environment | None:
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
        environment.hypervisor = hypervisor
        environment.file = environment_file.resolve().as_posix()  # Store absolute path
        self._session.commit()
        log.info(f"Environment with hash '{sha256hash}' updated in database")
        return environment

    def delete_environment(self, environment: Environment):
        self._session.delete(environment)
        self._session.commit()
        log.info(f"Environment with hash '{environment.sha256hash}' deleted from database")

    def get_environments(self, project_path: Path = None) -> list[Environment]:
        # retrieve all environments and expunge them from the session
        # Since environments are now global, we return all environments regardless of project_path
        return self._session.query(Environment).all()



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
        raise ValueError(f'environment {environment_ulid} not found in database')

    def get_environment_platform(self, environment_ulid: str):
        if (
            env := self._session.query(Environment)
            .filter_by(ulid=environment_ulid)
            .first()
        ):
            return env.vm.osinfo.platform
        raise ValueError(f'environment {environment_ulid} not found in database')

    def get_environment(self, name: str, project_name: str) -> Environment | None:
        # Since environments are now global, we just search by name (project_name is ignored)
        env = self._session.query(Environment).filter_by(name=name).first()
        if env:
            return env
        log.error(f'environment {name} does not exist in the database')
        return None

    def get_environment_vm(self, environment_ulid: str) -> str:
        if (
            env := self._session.query(Environment)
            .filter_by(ulid=environment_ulid)
            .first()
        ):
            return env.vm.name if env.vm else None
        raise ValueError(f'environment {environment_ulid} not found in database')

    def get_environment_by_project_and_name(self, project_path: Path, environment_name: str) -> Environment:
        # Since environments are now global, we just search by name
        return self._session.query(Environment).filter_by(name=environment_name).first()

    def sync_environment(self, ulid: str, remote_ulid: str, remote_url: str, is_published: bool):
        environment = self.get_environment_by_ulid(ulid)
        environment.remote_ulid = remote_ulid
        environment.remote_url = remote_url
        environment.published = is_published
        environment.in_request = bool(not is_published)
        self._session.commit()
