# external imports
from pathlib import Path

# internal imports
from adare.database.api.project import ProjectDbApi
from adare.database.models.experiments import Project


# configure logging
import logging
log = logging.getLogger(__name__)


def get_project_by_path(project_path: Path) -> Project or None:
    with ProjectDbApi() as api:
        project = api.get_project_by_path(project_path)
        if project is None:
            log.error(f'project {project_path} not found')
            return None
    return project


def get_all_projects() -> list[Project]:
    with ProjectDbApi() as api:
        projects = api.get_projects()
    return projects or []


def add_project(name: str, description: str, path: Path):
    with ProjectDbApi() as api:
        api.add_project(name, path, description)


def remove_project(project_path: Path):
    with ProjectDbApi() as api:
        api.remove_project_by_path(project_path)

