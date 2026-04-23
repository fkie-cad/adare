# external imports
# configure logging
import logging
from pathlib import Path

import sqlalchemy

# internal imports
from adare.database.api.base import GlobalDatabaseApi
from adare.database.exceptions import DatabaseProjectCreationError
from adare.database.models.global_models import Environment, OsInfo, Project

log = logging.getLogger(__name__)


class ProjectDbApi(GlobalDatabaseApi):
    """Database API for managing projects and their environments in the global database."""

    def __init__(self):
        super().__init__()
        self._start_session()

    def add_project(self, name: str, path: Path, description: str = None) -> Project:
        """Add a new project to the global database.

        Raises:
            DatabaseProjectCreationError: If a project with the same name already exists.
        """
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
        """Remove a project from the database by its filesystem path.

        Raises:
            NoResultFound: If no project exists at the given path.
        """
        if (
            project := self._session.query(Project)
            .filter(Project.path == path.as_posix())
            .first()
        ):
            self._session.delete(project)
        else:
            raise sqlalchemy.orm.exc.NoResultFound(f"Project '{path.as_posix()}' not found in database")

    def get_projects(self) -> list[Project]:
        """Get all projects from the database."""
        projects = self._session.query(Project).all()
        self.expunge_all()
        return projects

    def get_project(self, name: str) -> Project | None:
        """Get a project by name, or None if not found."""
        project = self._session.query(Project).filter(Project.name == name).first()
        if not project:
            log.error(f"Project '{name}' not found in database")
            return None
        return project

    def get_project_by_path(self, path: Path, silent: bool = False) -> Project | None:
        """Get a project by its filesystem path, or None if not found."""
        project = self._session.query(Project).filter(Project.path == path.as_posix()).first()
        if not project:
            if not silent:
                log.error(f"Project with path '{path}' not found in database")
            return None
        return project

    def get_environment(self, name: str, project_name: str) -> Environment | None:
        """Get an environment by name within a specific project.

        Raises:
            NoResultFound: If the project does not exist.
        """
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
        """Add a new environment to a project.

        Creates the associated OsInfo record if it does not already exist.

        Args:
            name: Environment name.
            path: Filesystem path to the environment definition.
            project_name: Name of the parent project.
            os_info: Dictionary of OS metadata used to find or create an OsInfo record.
            vagrant_box: Vagrant box identifier for the environment.
            description: Optional human-readable description.

        Returns:
            The newly created Environment instance.

        Raises:
            NoResultFound: If the project does not exist.
        """
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
        """Remove an environment by name from a project.

        Raises:
            NoResultFound: If the project or environment does not exist.
        """
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
        """Get all environments, optionally filtered by project name.

        Raises:
            NoResultFound: If the specified project does not exist.
        """
        if not project_name:
            return self._session.query(Environment).all()
        if (
            project := self._session.query(Project)
            .filter(Project.name == project_name)
            .first()
        ):
            return self._session.query(Environment).filter(Environment.project == project).all()
        raise sqlalchemy.orm.exc.NoResultFound(f"Project '{project_name}' not found in database")
