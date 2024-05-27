# external imports
from pathlib import Path

import pandas as pd

# internal imports
from adare.database.api.project import ProjectDbApi
from adare.database.models.experiment import Project


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


def get_project_by_name(project_name: str) -> Project or None:
    with ProjectDbApi() as api:
        project = api.get_project(project_name)
        if project is None:
            log.error(f'project {project_name} not found')
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


def get_project_testfunction_hashes(project_path: Path) -> dict:
    with ProjectDbApi() as api:
        project = api.get_project_by_path(project_path)
        hashes = {
            testfunction_file.path: testfunction_file.sha256hash
            for testfunction_file in project.testfunction_files
        }
    return hashes


def get_project_environment_hashes(project_path: Path) -> dict:
    with ProjectDbApi() as api:
        project = api.get_project_by_path(project_path)
        hashes = {
            environment_file.file: environment_file.sha256hash
            for environment_file in project.environments
        }
    return hashes

