# external imports
# configure logging
import logging
from pathlib import Path

from adare.database.api.environment import EnvironmentDbApi

# pandas import removed - not used
# internal imports
from adare.database.api.project import ProjectDbApi
from adare.database.api.testfunction import TestfunctionDbApi

log = logging.getLogger(__name__)


def get_project_by_path(project_path: Path, fields: list[str] = None) -> str | dict | None:
    """
    Get project by path.

    Args:
        project_path: Path to the project
        fields: Optional list of fields to extract. If None, returns only ID.
                Available fields: 'id', 'name', 'path', 'description'

    Returns:
        str: Project ID if fields=None
        dict: Project data if fields specified
        None: If project not found
    """
    with ProjectDbApi() as api:
        project = api.get_project_by_path(project_path)
        if project is None:
            log.error(f'project {project_path} not found')
            return None

        if fields is None:
            return project.id

        # Extract requested fields
        result = {}
        for field in fields:
            if field == 'id':
                result['id'] = project.id
            elif field == 'name':
                result['name'] = project.name
            elif field == 'path':
                result['path'] = str(project.path)
            elif field == 'description':
                result['description'] = project.description
            else:
                log.warning(f'Unknown field requested: {field}. Available: id, name, path, description')

        return result


def get_project_by_name(project_name: str, fields: list[str] = None) -> str | dict | None:
    """
    Get project by name.

    Args:
        project_name: Name of the project
        fields: Optional list of fields to extract. If None, returns only ID.

    Returns:
        str: Project ID if fields=None
        dict: Project data if fields specified
        None: If project not found
    """
    with ProjectDbApi() as api:
        project = api.get_project(project_name)
        if project is None:
            log.error(f'project {project_name} not found')
            return None

        if fields is None:
            return project.id

        # Extract requested fields
        result = {}
        for field in fields:
            if field == 'id':
                result['id'] = project.id
            elif field == 'name':
                result['name'] = project.name
            elif field == 'path':
                result['path'] = str(project.path)
            elif field == 'description':
                result['description'] = project.description
            else:
                log.warning(f'Unknown field requested: {field}. Available: id, name, path, description')

        return result


def get_all_projects() -> list[dict]:
    with ProjectDbApi() as api:
        projects = api.get_projects()
        if not projects:
            return []
        # Extract data while session is active
        return [
            {
                'id': project.id,
                'name': project.name,
                'path': str(project.path),
                'description': project.description
            }
            for project in projects
        ]


def add_project(name: str, description: str, path: Path):
    with ProjectDbApi() as api:
        api.add_project(name, path, description)


def remove_project(project_path: Path):
    with ProjectDbApi() as api:
        api.remove_project_by_path(project_path)


def get_global_testfunction_hashes() -> list:
    with TestfunctionDbApi() as api:
        # Get all global test function files since they are no longer project-specific
        testfunction_files = api.get_testfunction_files()
        hashes = [
            {
                "hash": testfunction_file.sha256hash,
                "file": testfunction_file.path,
                "requirements": testfunction_file.requirements_path,
            }
            for testfunction_file in testfunction_files
        ]
        return hashes


def get_project_data(project_path: Path) -> dict | None:
    """Get full project data - convenience function for common case."""
    return get_project_by_path(project_path, fields=['id', 'name', 'path', 'description'])


def get_project_summary(project_path: Path) -> dict | None:
    """Get basic project info - lighter version."""
    return get_project_by_path(project_path, fields=['id', 'name', 'description'])


def get_global_environment_hashes() -> dict:
    with EnvironmentDbApi() as api:
        # Get all global environments since they are no longer project-specific
        environments = api.get_environments()
        hashes = {
            environment.file: environment.sha256hash
            for environment in environments
            if environment.file and environment.sha256hash  # Only include environments with file and hash
        }
        return hashes

