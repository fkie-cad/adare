# external imports
import sqlalchemy
from sqlalchemy.orm import sessionmaker
from pathlib import Path

# internal imports
import adare.config.database as config_database
from adare.database.models.global_models import Project, Environment, OsInfo
from adare.database.api.base import GlobalDatabaseApi
from adare.database.exceptions import DatabaseProjectCreationError

# configure logging
import logging
log = logging.getLogger(__name__)


class ProjectDbApi(GlobalDatabaseApi):

    def __init__(self):
        super().__init__()
        self._start_session()

    def add_project(self, name: str, path: Path, description: str = None) -> Project:
        project = self._session.query(Project).filter(Project.name == name).first()
        if project:
            raise DatabaseProjectCreationError(
                log,
                f"Project [i]{name}[/i] already exists in database"
            )
        project = Project(name=name, path=path.as_posix(), description=description)
        self._session.add(project)
        return project

    def remove_project_by_path(self, path: Path) -> None:
        if (
            project := self._session.query(Project)
            .filter(Project.path == path.as_posix())
            .first()
        ):
            self._session.delete(project)
        else:
            raise sqlalchemy.orm.exc.NoResultFound(f"Project '{path.as_posix()}' not found in database")

    def get_projects(self) -> list[Project]:
        projects = self._session.query(Project).all()
        self.expunge_all()
        return projects

    def get_project(self, name: str) -> Project | None:
        project = self._session.query(Project).filter(Project.name == name).first()
        if not project:
            log.error(f"Project '{name}' not found in database")
            return None
        return project

    def get_project_by_path(self, path: Path, silent: bool = False) -> Project | None:
        project = self._session.query(Project).filter(Project.path == path.as_posix()).first()
        if not project:
            if not silent:
                log.error(f"Project with path '{path}' not found in database")
            return None
        return project

    def get_environment(self, name: str, project_name: str) -> Environment | None:
        project = self._session.query(Project).filter(Project.name == project_name).first()
        if not project:
            raise sqlalchemy.orm.exc.NoResultFound(f"Project '{project_name}' not found in database")
        environment = self._session.query(Environment).filter(Environment.name == name,
                                                              Environment.project == project).first()
        if not environment:
            log.error(f"Environment '{name}' not found in database")
            return None
        return environment

    def add_environment(self, name: str, path: Path, project_name: str, os_info: dict, vagrant_box: str,
                        description: str = None) -> Environment:
        project = self._session.query(Project).filter(Project.name == project_name).first()
        if not project:
            raise sqlalchemy.orm.exc.NoResultFound(f"Project '{project_name}' not found in database")

        # create or get os info entry
        os_info_obj = self._session.query(OsInfo).filter_by(**os_info).first()
        if not os_info_obj:
            os_info_obj = OsInfo(**os_info)
            self._session.add(os_info_obj)

        environment = Environment(
            name=name,
            path=path.as_posix(),
            description=description,
            project=project,
            vagrant_box=vagrant_box,
            osinfo=os_info_obj
        )
        self._session.add(environment)
        return environment

    def remove_environment(self, name: str, project_name: str) -> None:
        project = self._session.query(Project).filter(Project.name == project_name).first()
        if not project:
            raise sqlalchemy.orm.exc.NoResultFound(f"Project '{project_name}' not found in database")
        if (
            environment := self._session.query(Environment)
            .filter(Environment.name == name, Environment.project == project)
            .first()
        ):
            self._delete_commit(environment)
        else:
            raise sqlalchemy.orm.exc.NoResultFound(f"Environment '{name}' not found in database")

    def get_environments(self, project_name: str = None) -> list[Environment]:
        if not project_name:
            return self._session.query(Environment).all()
        if (
            project := self._session.query(Project)
            .filter(Project.name == project_name)
            .first()
        ):
            return self._session.query(Environment).filter(Environment.project == project).all()
        else:
            raise sqlalchemy.orm.exc.NoResultFound(f"Project '{project_name}' not found in database")
