"""
Environment Service - Business logic for environment operations.

This service handles all environment-related operations and returns Result[T] objects
that can be consumed by any frontend (CLI, Web UI, REST API).
"""
import logging
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

import adare.backend.environment.database as environment_database
from adare.backend.environment.commands import (
    environment_create as backend_environment_create,
)
from adare.backend.environment.commands import (
    environment_delete as backend_environment_delete,
)
from adare.backend.environment.commands import (
    environment_load as backend_environment_load,
)
from adare.backend.environment.exceptions import (
    EnvironmentAlreadyExists,
    EnvironmentDeletionError,
    EnvironmentDoesNotExistInDatabase,
    EnvironmentFileAlreadyExists,
    EnvironmentLoadFailed,
    EnvironmentUpdateError,
)
from adare.backend.environment.extend import (
    environment_extend as backend_environment_extend,
)
from adare.core.dto.environment import (
    EnvironmentCreateRequest,
    EnvironmentExtendRequest,
    EnvironmentInfo,
    EnvironmentListItem,
    EnvironmentLoadRequest,
)
from adare.core.result import Result
from adare.database.api.environment import EnvironmentDbApi
from adare.helperfunctions.hash import hash_file_sha256
from adare.hypervisor.exceptions import HypervisorException
from adare.hypervisor.qemu.vm_creator.os_catalog import SetupLevel, get_os_definition
from adare.services.environment_recipe import build_recipe_environment_file

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
            # Call existing backend command. It returns the real ULID and
            # whether a new environment was created (created=False means the
            # .yml was byte-identical to an existing environment and was reused).
            environment_ulid, created = backend_environment_load(
                request.environment,
                force=request.force,
                no_copy=request.no_copy
            )
            reused_existing = not created

            # Derive a fallback display name from the filename in case the
            # database lookup somehow comes up empty.
            env_path = Path(request.environment)
            env_name = env_path.stem if env_path.suffix in ['.yml', '.yaml'] else request.environment

            # We hold the real ULID, so this lookup can't miss and gives us the
            # real stored name (e.g. the original environment on a reuse).
            env_data = environment_database.get_environment_data(environment_ulid)

            if env_data:
                stored_name = env_data.get('name', env_name)
                next_steps = [
                    f'Verify the VM is ready: adare env verify {stored_name}',
                    f'Run experiments in this environment with: adare experiment run <experiment> -e {stored_name}',
                    'List available environments with: adare environment list',
                    f'View environment details with: adare environment show {stored_name}'
                ]
                if reused_existing:
                    tip = (
                        f'No new environment was created — the file content matches '
                        f'the existing environment "{stored_name}".'
                    )
                else:
                    tip = f'Environment "{stored_name}" is now ready for experiments'

                return Result.ok(EnvironmentInfo(
                    id=env_data.get('id', ''),
                    name=stored_name,
                    description=env_data.get('description', ''),
                    vm_name=env_data.get('vm_name'),
                    hypervisor=env_data.get('hypervisor', 'virtualbox') if 'hypervisor' in env_data else 'virtualbox',
                    os_platform=env_data.get('vm_os_type'),
                    file_path=Path(env_data['file']) if env_data.get('file') else None,
                    next_steps=next_steps,
                    tip=tip,
                    reused_existing=reused_existing,
                ))

            # True error path: the load reported success but the row is missing.
            log.error(f'environment {environment_ulid} not found after load')
            return Result.ok(EnvironmentInfo(
                id=environment_ulid,
                name=env_name,
                description='',
                vm_name=None,
                hypervisor='virtualbox',
                os_platform=None,
                file_path=None,
                next_steps=[f'Environment "{env_name}" loaded'],
                reused_existing=reused_existing,
            ))

        except EnvironmentLoadFailed as e:
            return Result.from_exception(e)
        except EnvironmentAlreadyExists as e:
            return Result.from_exception(e)
        except EnvironmentUpdateError as e:
            return Result.from_exception(e)

    def extend(self, request: EnvironmentExtendRequest) -> Result[EnvironmentInfo]:
        """
        Extend a source environment (or VM) into a new environment that
        reuses the same base disk plus additional post-setup installations.

        Args:
            request: EnvironmentExtendRequest with source, new name, and
                declarative install options.

        Returns:
            Result[EnvironmentInfo] with the new environment's data on
            success, or error information on failure.
        """
        try:
            environment_ulid, created = backend_environment_extend(request)

            # Interactive mode: the user discarded the session, so nothing was
            # flattened or registered. Report a neutral "discarded" result.
            if environment_ulid is None:
                return Result.ok(EnvironmentInfo(
                    id='',
                    name=request.name,
                    description='',
                    vm_name=None,
                    hypervisor='qemu',
                    os_platform=None,
                    file_path=None,
                    discarded=True,
                    next_steps=[
                        'Nothing was created. Re-run the extend to try again: '
                        f'adare env extend {request.source} {request.name} --interactive',
                        'List available environments with: adare environment list',
                    ],
                    tip='Session discarded — no environment was created.',
                ))

            reused_existing = not created

            env_data = environment_database.get_environment_data(environment_ulid)

            if env_data:
                stored_name = env_data.get('name', request.name)
                next_steps = [
                    f'Verify the VM is ready: adare env verify {stored_name}',
                    f'Run experiments in this environment with: adare experiment run <experiment> -e {stored_name}',
                    'List available environments with: adare environment list',
                ]
                tip = (
                    f'No new environment was created — the generated file matches '
                    f'an existing environment "{stored_name}".'
                    if reused_existing else
                    f'Environment "{stored_name}" reuses the same base VM as "{request.source}"'
                )

                return Result.ok(EnvironmentInfo(
                    id=env_data.get('id', ''),
                    name=stored_name,
                    description=env_data.get('description', ''),
                    vm_name=env_data.get('vm_name'),
                    hypervisor=environment_database.get_environment_hypervisor(environment_ulid),
                    os_platform=env_data.get('vm_os_type'),
                    file_path=Path(env_data['file']) if env_data.get('file') else None,
                    next_steps=next_steps,
                    tip=tip,
                    reused_existing=reused_existing,
                ))

            # True error path: the extend reported success but the row is missing.
            log.error(f'environment {environment_ulid} not found after extend')
            return Result.ok(EnvironmentInfo(
                id=environment_ulid,
                name=request.name,
                description='',
                vm_name=None,
                hypervisor='virtualbox',
                os_platform=None,
                file_path=None,
                next_steps=[f'Environment "{request.name}" extended'],
                reused_existing=reused_existing,
            ))

        except EnvironmentLoadFailed as e:
            return Result.from_exception(e)
        except EnvironmentAlreadyExists as e:
            return Result.from_exception(e)
        except EnvironmentUpdateError as e:
            return Result.from_exception(e)
        except EnvironmentDoesNotExistInDatabase as e:
            return Result.from_exception(e)
        except HypervisorException as e:
            # Interactive mode: QEMU-only guard, Apple-Silicon guard, and any
            # overlay/boot/flatten failure surface as HypervisorException.
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
        if request.is_recipe:
            return self._create_recipe(request)

        try:
            # Call existing backend command
            backend_environment_create(
                request.project_path,
                request.name,
                vm_path=request.vm_path
            )

            next_steps = [
                'Edit the environment file to configure VM and OS settings',
                f'Load the environment with: adare environment load {request.name}',
                f'Verify the VM is ready: adare env verify {request.name}',
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
                tip='Environment template created. Edit the file and load it to register.',
            ))

        except EnvironmentFileAlreadyExists as e:
            return Result.from_exception(e)

    def _create_recipe(self, request: EnvironmentCreateRequest) -> Result[EnvironmentInfo]:
        """
        Write a declarative recipe environment descriptor (no VM build).

        The heavy QEMU disk build happens later, once, on `environment load`;
        this only resolves the OS profile, hashes the ISO, and writes the
        recipe YAML into the project's environments directory.
        """
        try:
            os_def = get_os_definition(request.os_profile)
        except KeyError:
            return Result.fail(
                code='UnknownOsProfileError',
                message=f'Unknown OS profile: {request.os_profile}',
                solutions=[
                    'Run: adare manage os-profile list',
                    'Check the os_profile value for typos',
                ]
            )

        iso_sha256 = hash_file_sha256(request.iso_path)
        setup_level = SetupLevel(request.setup_level) if request.setup_level is not None else SetupLevel.FULL

        env_file_path = build_recipe_environment_file(
            os_name=request.os_profile,
            os_def=os_def,
            iso_path=request.iso_path,
            iso_sha256=iso_sha256,
            setup_level=setup_level,
            disk_size=request.disk_size,
            ram=request.ram_mb,
            cpus=request.cpus,
            arch=request.arch,
            env_name=request.name,
            project_path=request.project_path,
        )

        next_steps = [
            f'Build the disk on load: adare environment load {env_file_path}',
            f'Verify the VM is ready: adare env verify {request.name}',
        ]

        return Result.ok(EnvironmentInfo(
            id='',  # Not yet in database (just a recipe descriptor file)
            name=request.name,
            description='',
            vm_name=None,
            hypervisor='qemu',
            os_platform=os_def.platform,
            file_path=env_file_path,
            next_steps=next_steps,
            tip='Recipe environment created. The disk is built once from the ISO on first load.',
        ))

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

    def list_all(self) -> Result[list[EnvironmentListItem]]:
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

        except (SQLAlchemyError, OSError) as e:
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
