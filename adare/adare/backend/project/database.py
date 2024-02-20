# external imports
from pathlib import Path

# internal imports
from adare.database.api.project import ProjectDbApi
from adare.database.models.experiments import Project


# configure logging
import logging
log = logging.getLogger(__name__)


class ProjectDatabase:
    project_path: Path

    def __init__(self, project_path: Path):
        self.project_path = project_path

    def add(self, name: str, description: str = None) -> (Project, bool):
        with ProjectDbApi() as db:
            return db.add_project(name, self.project_path, description)

    def remove(self) -> None:
        with ProjectDbApi() as db:
            db.remove_project_by_path(self.project_path)

    def get(self) -> Project or None:
        with ProjectDbApi() as db:
            return db.get_project_by_path(self.project_path)

    def get_all(self) -> list[Project]:
        with ProjectDbApi() as db:
            return db.get_projects()