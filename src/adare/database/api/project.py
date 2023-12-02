# external imports
import sqlalchemy
from sqlalchemy.orm import sessionmaker
from pathlib import Path


# internal imports
import adare.config.database as config_database
from adare.database.models.experiments import OsInfo, Project, Environment, Base as ExperimentBase
from adare.database.api.experiment import ExperimentApi

# configure logging
import logging
log = logging.getLogger(__name__)



class ProjectManagementApi(ExperimentApi):

    def __init__(self, db_path: Path = config_database.get_database_location()):
        super().__init__(db_path)
        ExperimentBase.metadata.create_all(self.engine)
        
    def add_project(self, name: str, path: Path, description: str = None) -> Project:
        # check if project already exists
        project = self._session.query(Project).filter(Project.name == name).first()
        if project:
            log.error(f"Project '{name}' already exists in database ({project.path})")
            return project
        project = Project(name=name, path=path.as_posix(), description=description)
        self._session.add(project)
        self._session.commit()
        return project

    def remove_project(self, name: str) -> None:
        project = self._session.query(Project).filter(Project.name == name).first()
        if not project:
            raise sqlalchemy.orm.exc.NoResultFound(f"Project '{name}' not found in database")
        self._session.delete(project)
        self._session.commit()

    def get_projects(self) -> list[Project]:
        return self._session.query(Project).all()

    def get_project(self, name: str) -> Project or None:
        project = self._session.query(Project).filter(Project.name == name).first()
        if not project:
            log.error(f"Project '{name}' not found in database")
            return None
        return project

    def get_project_by_path(self, path: Path) -> Project or None:
        project = self._session.query(Project).filter(Project.path == path.as_posix()).first()
        if not project:
            log.error(f"Project with path '{path}' not found in database")
            return None
        return project

    def get_environment(self, name: str, project_name: str) -> Environment or None:
        project = self._session.query(Project).filter(Project.name == project_name).first()
        if not project:
            raise sqlalchemy.orm.exc.NoResultFound(f"Project '{project_name}' not found in database")
        environment = self._session.query(Environment).filter(Environment.name == name, Environment.project == project).first()
        if not environment:
            log.error(f"Environment '{name}' not found in database")
            return None
        return environment

    def add_environment(self, name: str, path: Path, project_name: str, os_info: dict, vagrant_box: str, description: str = None) -> Environment:
        project = self._session.query(Project).filter(Project.name == project_name).first()
        if not project:
            raise sqlalchemy.orm.exc.NoResultFound(f"Project '{project_name}' not found in database")

        # create or get os info entry
        os_info_obj = self._session.query(OsInfo).filter_by(**os_info).first()
        if not os_info_obj:
            os_info_obj = OsInfo(**os_info)
            self._session.add(os_info_obj)
        self._session.commit()


        environment = Environment(
            name=name,
            path=path.as_posix(),
            description=description,
            project=project,
            vagrant_box=vagrant_box,
            osinfo=os_info_obj
        )
        self._session.add(environment)
        self._session.commit()
        return environment

    def remove_environment(self, name: str, project_name: str) -> None:
        project = self._session.query(Project).filter(Project.name == project_name).first()
        if not project:
            raise sqlalchemy.orm.exc.NoResultFound(f"Project '{project_name}' not found in database")
        # get environment from project
        environment = self._session.query(Environment).filter(Environment.name == name, Environment.project == project).first()
        if not environment:
            raise sqlalchemy.orm.exc.NoResultFound(f"Environment '{name}' not found in database")
        self._session.delete(environment)
        self._session.commit()

    def get_environments(self, project_name: str = None) -> list[Environment]:
        if project_name:
            project = self._session.query(Project).filter(Project.name == project_name).first()
            if not project:
                raise sqlalchemy.orm.exc.NoResultFound(f"Project '{project_name}' not found in database")
            return self._session.query(Environment).filter(Environment.project == project).all()
        else:
            return self._session.query(Environment).all()

