"""
Environment Service - Business logic for environment operations.

This service handles all environment-related operations and returns Result[T] objects
that can be consumed by any frontend (CLI, Web UI, REST API).
"""
from pathlib import Path
from typing import List

import logging

import adare.backend.environment.database as environment_database
from adare.backend.environment.commands import (
    environment_load as backend_environment_load,
    environment_create as backend_environment_create,
    environment_delete as backend_environment_delete,
)
from adare.backend.environment.exceptions import (
    EnvironmentLoadFailed,
    EnvironmentFileAlreadyExists,
    EnvironmentDoesNotExistInDatabase,
    EnvironmentDeletionError,
    EnvironmentAlreadyExists,
    EnvironmentUpdateError,
)
from adare.database.api.environment import EnvironmentDbApi
from adare.core.result import Result
from adare.core.dto.environment import (
    EnvironmentLoadRequest,
    EnvironmentCreateRequest,
    EnvironmentDeleteRequest,
    EnvironmentInfo,
    EnvironmentListItem,
)

log = logging.getLogger(__name__)


class EnvironmentService:
    """
    Service for environment management operations.

    All methods return Result[T] objects for consistent error handling
    across different frontends.
    """

    def load(self, request: EnvironmentLoadRequest) -> Result[EnvironmentInfo]:
        """
        Load an environment from a YAML file.

        Args:
            request: EnvironmentLoadRequest with environment path/name and options

        Returns:
            Result[EnvironmentInfo] with environment data on success,
            or error information on failure.
        """
        try:
            # Call existing backend command
            backend_environment_load(
                request.environment,
                force=request.force,
                no_copy=request.no_copy
            )

            # Get the loaded environment info
            # The environment name is derived from the filename
            env_path = Path(request.environment)
            if env_path.suffix in ['.yml', '.yaml']:
                env_name = env_path.stem
            else:
                env_name = request.environment

            # Try to get the environment from database
            try:
                ulid = environment_database.resolve_environment_identifier(env_name)
                env_data = environment_database.get_environment_data(ulid)

                if env_data:
                    next_steps = [
                        f'Run experiments in this environment with: adare experiment run <experiment> -e {env_name}',
                        f'List available environments with: adare environment list',
                        f'View environment details with: adare environment show {env_name}'
                    ]

                    return Result.ok(EnvironmentInfo(
                        id=env_data.get('id', ''),
                        name=env_data.get('name', env_name),
                        description=env_data.get('description', ''),
                        vm_name=env_data.get('vm_name'),
                        hypervisor=env_data.get('hypervisor', 'virtualbox') if 'hypervisor' in env_data else 'virtualbox',
                        os_platform=env_data.get('vm_os_type'),
                        file_path=Path(env_data['file']) if env_data.get('file') else None,
                        next_steps=next_steps,
                        tip=f'Environment "{env_name}" is now ready for experiments',
                    ))
            except EnvironmentDoesNotExistInDatabase:
                pass

            # Fallback if we couldn't get full info
            return Result.ok(EnvironmentInfo(
                id='',
                name=env_name,
                description='',
                vm_name=None,
                hypervisor='virtualbox',
                os_platform=None,
                file_path=None,
                next_steps=[f'Environment "{env_name}" loaded'],
            ))

        except EnvironmentLoadFailed as e:
            return Result.from_exception(e)
        except EnvironmentAlreadyExists as e:
            return Result.from_exception(e)
        except EnvironmentUpdateError as e:
            return Result.from_exception(e)

    def create(self, request: EnvironmentCreateRequest) -> Result[EnvironmentInfo]:
        """
        Create a new environment template file.

        Args:
            request: EnvironmentCreateRequest with project path, name, and optional VM

        Returns:
            Result[EnvironmentInfo] with created environment info on success,
            or error information on failure.
        """
        try:
            # Call existing backend command
            backend_environment_create(
                request.project_path,
                request.name,
                vm_path=request.vm_path
            )

            next_steps = [
                f'Edit the environment file to configure VM and OS settings',
                f'Load the environment with: adare environment load {request.name}',
            ]

            return Result.ok(EnvironmentInfo(
                id='',  # Not yet in database (just a template file)
                name=request.name,
                description='',
                vm_name=None,
                hypervisor='virtualbox',
                os_platform=None,
                file_path=request.project_path / 'environments' / f'{request.name}.yml',
                next_steps=next_steps,
                tip=f'Environment template created. Edit the file and load it to register.',
            ))

        except EnvironmentFileAlreadyExists as e:
            return Result.from_exception(e)

    def delete(self, identifier: str, force: bool = False) -> Result[None]:
        """
        Delete an environment.

        Args:
            identifier: Environment name or ULID
            force: Force deletion even if environment has runs

        Returns:
            Result[None] on success, or error information on failure.
        """
        try:
            # Resolve name/ULID to ULID
            environment_ulid = environment_database.resolve_environment_identifier(identifier)

            # Call existing backend command
            backend_environment_delete(environment_ulid, force=force)

            return Result.ok(None)

        except EnvironmentDoesNotExistInDatabase as e:
            return Result.from_exception(e)
        except EnvironmentDeletionError as e:
            return Result.from_exception(e)

    def list_all(self) -> Result[List[EnvironmentListItem]]:
        """
        List all environments.

        Returns:
            Result[List[EnvironmentListItem]] with all environments.
        """
        try:
            with EnvironmentDbApi() as db:
                environments = db.get_environments()

                items = []
                for env in environments:
                    vm_name = None
                    os_platform = None

                    if hasattr(env, 'vm') and env.vm:
                        vm_name = env.vm.name
                        if hasattr(env.vm, 'osinfo') and env.vm.osinfo:
                            os_platform = env.vm.osinfo.platform

                    items.append(EnvironmentListItem(
                        id=env.id,
                        name=env.name,
                        description=env.description or "",
                        vm_name=vm_name,
                        hypervisor=env.hypervisor or "virtualbox",
                        os_platform=os_platform,
                    ))

                return Result.ok(items)

        except Exception as e:
            log.error(f"Failed to list environments: {e}")
            return Result.fail(
                code="EnvironmentListError",
                message=f"Failed to list environments: {e}",
                solutions=['Check database connectivity', 'Try again']
            )

    def get_by_id(self, ulid: str) -> Result[EnvironmentInfo]:
        """
        Get an environment by its ULID.

        Args:
            ulid: Environment ULID

        Returns:
            Result[EnvironmentInfo] with environment data, or error if not found.
        """
        try:
            env_data = environment_database.get_environment_data(ulid)

            if not env_data:
                return Result.fail(
                    code="EnvironmentNotFoundError",
                    message=f'Environment with ID {ulid} not found',
                    solutions=[
                        'Use `adare environment list` to see available environments',
                        'Check if the environment ID is correct',
                    ]
                )

            return Result.ok(EnvironmentInfo(
                id=env_data.get('id', ''),
                name=env_data.get('name', ''),
                description=env_data.get('description', ''),
                vm_name=env_data.get('vm_name'),
                hypervisor=environment_database.get_environment_hypervisor(ulid),
                os_platform=env_data.get('vm_os_type'),
                file_path=Path(env_data['file']) if env_data.get('file') else None,
            ))

        except EnvironmentDoesNotExistInDatabase as e:
            return Result.from_exception(e)

    def get_by_name(self, name: str) -> Result[EnvironmentInfo]:
        """
        Get an environment by its name.

        Args:
            name: Environment name

        Returns:
            Result[EnvironmentInfo] with environment data, or error if not found.
        """
        try:
            ulid = environment_database.resolve_environment_identifier(name)
            return self.get_by_id(ulid)
        except EnvironmentDoesNotExistInDatabase as e:
            return Result.from_exception(e)
