# external imports
import attrs
import sqlalchemy
from sqlalchemy.orm import sessionmaker
from pathlib import Path

# internal imports
import adare.config.database as config_database
from adare.database.models.experiments import Environment, OsInfo
from adare.database.api.database import DatabaseApi
from adare.backend.attrs_classes import EnvironmentConfiguration, OsInfo as OsInfoAttrs

# configure logging
import logging
log = logging.getLogger(__name__)


class EnvironmentDbApi(DatabaseApi):

    def __init__(self, db_path: Path = config_database.get_database_location()):
        super().__init__(db_path)

    def get_or_create_os_info(self, os_info_attrs: OsInfoAttrs) -> (OsInfo, bool):
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

    def get_or_create_environment(self, environment_configuration: EnvironmentConfiguration, environment_file: Path, sha256hash: str) -> (
    Environment, bool):
        environment = self._session.query(Environment).filter(Environment.sha256hash == sha256hash).first()
        if environment:
            return environment, False
        log.info(f"Environment with hash '{sha256hash}' not found in database -> creating new entry")
        os_info, _ = self.get_or_create_os_info(environment_configuration.os)
        environment = Environment(
            name=environment_configuration.name,
            description=environment_configuration.description,
            vagrantbox=environment_configuration.vagrantbox,
            osinfo=os_info,
            sha256hash=sha256hash,
            file=environment_file.as_posix(),
        )
        self._session.add(environment)
        self._session.commit()
        return environment, True

    def update_environment(self, environment_configuration: EnvironmentConfiguration, environment_file: Path, sha256hash: str) -> bool:
        environment = self._session.query(Environment).filter(Environment.sha256hash == sha256hash).first()
        if not environment:
            log.error(f"Environment with hash '{sha256hash}' not found in database -> cannot update")
            return False
        if environment.runs:
            log.error(f"Environment with hash '{sha256hash}' has already been used for experiments, so it cannot be updated because this would invalidate the results")
            return False
        os_info, _ = self.get_or_create_os_info(environment_configuration.os)
        environment.name = environment_configuration.name
        environment.description = environment_configuration.description
        environment.vagrantbox = environment_configuration.vagrantbox
        environment.osinfo = os_info
        environment.file = environment_file.as_posix()
        self._session.commit()
        log.info(f"Environment with hash '{sha256hash}' updated in database")