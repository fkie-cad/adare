"""
Project Service - Business logic for project operations.

This service handles all project-related operations and returns Result[T] objects
that can be consumed by any frontend (CLI, Web UI, REST API).
"""
from pathlib import Path
from typing import List

import logging

import adare.backend.project.database as project_database
from adare.backend.project.directory import ProjectDirectory
from adare.backend.project.exceptions import (
    ProjectDirectoryCreationError,
    ProjectDirectoryRemovalError,
    ProjectDirectoryCopyError,
    ProjectMissingInDatabaseError,
)
from adare.database.exceptions import DatabaseProjectCreationError
from adare.database.init import ensure_project_database_exists, DatabaseInitializationError
from adare.database.fixtures import fixture_stages, fixture_status
from adare.core.result import Result
from adare.core.dto.project import (
    ProjectCreateRequest,
    ProjectInfo,
    ProjectListItem,
    ProjectRemoveRequest,
)

log = logging.getLogger(__name__)


class ProjectService:
    """
    Service for project management operations.

    All methods return Result[T] objects for consistent error handling
    across different frontends.
    """

    def create(self, request: ProjectCreateRequest) -> Result[ProjectInfo]:
        """
        Create a new project.

        Args:
            request: ProjectCreateRequest with name, path, and optional description

        Returns:
            Result[ProjectInfo] with project data and next steps on success,
            or error information on failure.
        """
        project_directory = ProjectDirectory(request.path)

        # Step 1: Create project directory
        try:
            project_directory.create()
        except ProjectDirectoryCreationError as e:
            return Result.from_exception(e)

        # Step 2: Add to global database
        try:
            project_database.add_project(request.name, request.description, request.path)
        except DatabaseProjectCreationError as e:
            project_directory.remove()
            log.info(f'project directory {request.path} removed, since project could not be added to database')
            return Result.from_exception(e)

        # Step 3: Initialize project database
        try:
            ensure_project_database_exists(request.path)
            log.info(f'project database initialized for {request.path}')
        except DatabaseInitializationError as e:
            self._cleanup_failed_project(project_directory, request.path, "project database could not be initialized")
            return Result.from_exception(e)

        # Step 4: Load fixtures
        try:
            from adare.database.api.base import ProjectDatabaseApi
            with ProjectDatabaseApi(request.path) as project_api:
                fixture_status(project_api._session)
                fixture_stages(project_api._session)
            log.info(f'project fixtures loaded for {request.path}')
        except DatabaseInitializationError as e:
            self._cleanup_failed_project(project_directory, request.path, "project fixtures could not be loaded")
            return Result.from_exception(e)

        # Step 5: Copy VM runtime files
        try:
            project_directory.copy_vm_runtime_files()
        except ProjectDirectoryCopyError as e:
            self._cleanup_failed_project(project_directory, request.path, "vm runtime files could not be copied")
            return Result.from_exception(e)

        log.info(f'project in path {request.path} created')

        # Get the created project's ID
        project_data = project_database.get_project_by_path(request.path, fields=['id'])
        project_id = project_data.get('id', '') if project_data else ''

        # Build next steps - data only, no presentation
        next_steps = [
            f'Create an environment with: adare environment create <environment_name>',
            f'Create an experiment with: adare experiment create <experiment_name>',
            f'Use all available testfunction sets: files, json, csv, sqlite, linux, windows',
            f'Run your first experiment with: adare experiment run <experiment> -e <environment>'
        ]

        return Result.ok(ProjectInfo(
            id=project_id,
            name=request.name,
            path=request.path,
            description=request.description,
            next_steps=next_steps,
            tip='All testfunction sets loaded with file operations, data validation (JSON, CSV, SQLite), system analysis (Linux, Windows), and forensic capabilities'
        ))

    def _cleanup_failed_project(self, project_directory: ProjectDirectory, path: Path, reason: str) -> None:
        """Clean up a partially created project after a failure."""
        project_directory.remove()
        project_database.remove_project(path)
        log.error(f'project directory {path} removed, since {reason}')

    def remove(self, request: ProjectRemoveRequest) -> Result[None]:
        """
        Remove a project.

        Args:
            request: ProjectRemoveRequest with path to remove

        Returns:
            Result[None] on success, or error information on failure.
        """
        # Verify project exists in database
        if not project_database.get_project_by_path(request.path):
            return Result.fail(
                code="ProjectMissingInDatabaseError",
                message=f'project in path {request.path} does not exist in database',
                solutions=[
                    'Use `adare project list` to see available projects',
                    'Check if the project path is correct',
                ]
            )

        project_directory = ProjectDirectory(request.path)

        # Remove directory if it exists
        if project_directory.exists():
            try:
                project_directory.remove()
            except ProjectDirectoryRemovalError as e:
                return Result.from_exception(e)
        else:
            log.info(f'project directory {request.path} already deleted, skipping directory removal')

        # Remove from database
        project_database.remove_project(request.path)

        return Result.ok(None)

    def list_all(self) -> Result[List[ProjectListItem]]:
        """
        List all projects.

        Returns:
            Result[List[ProjectListItem]] with all projects, or empty list if none exist.
        """
        projects_data = project_database.get_all_projects()

        if not projects_data:
            return Result.ok([])

        projects = [
            ProjectListItem(
                id=p['id'],
                name=p['name'],
                path=Path(p['path']),
                description=p.get('description', ''),
            )
            for p in projects_data
        ]

        return Result.ok(projects)

    def get_by_path(self, path: Path) -> Result[ProjectListItem]:
        """
        Get a project by its path.

        Args:
            path: Path to the project

        Returns:
            Result[ProjectListItem] with project data, or error if not found.
        """
        project_data = project_database.get_project_by_path(path, fields=['id', 'name', 'path', 'description'])

        if not project_data:
            return Result.fail(
                code="ProjectNotFoundError",
                message=f'Project at path {path} not found',
                solutions=[
                    'Use `adare project list` to see available projects',
                    'Check if the project path is correct',
                ]
            )

        return Result.ok(ProjectListItem(
            id=project_data['id'],
            name=project_data['name'],
            path=Path(project_data['path']),
            description=project_data.get('description', ''),
        ))
