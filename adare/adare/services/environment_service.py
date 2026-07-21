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
from adare.hypervisor.qemu.vm_creator.os_catalog import (
    SetupLevel,
    get_os_definition,
    list_os_definitions,
)
from adare.services.environment_recipe import (
    build_baked_url_environment_file,
    build_recipe_environment_file,
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

        if request.vm_url:
            return self._create_baked_url(request)

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

    def _create_baked_url(self, request: EnvironmentCreateRequest) -> Result[EnvironmentInfo]:
        """
        Write a publish-ready baked environment descriptor for a hosted VM URL.

        No VM is loaded into the database here (that would require a local disk):
        we only emit a baked-URL YAML (``vm: <url>``, ``vm_type: url``,
        ``vm_sha256``). The disk is downloaded, cached, and verified against
        ``vm_sha256`` later, on ``environment load`` (see
        ``backend.environment.commands.resolve_vm_from_url``).
        """
        if not request.vm_sha256:
            return Result.fail(
                code='MissingVmSha256Error',
                message='A baked VM URL requires an explicit vm_sha256.',
                solutions=[
                    'Provide the SHA256 of the hosted disk image',
                    'Compute it with: shasum -a 256 <disk-image>',
                ],
            )

        env_file_path = build_baked_url_environment_file(
            vm_url=request.vm_url,
            vm_sha256=request.vm_sha256,
            env_name=request.name,
            project_path=request.project_path,
            vm_format=request.vm_format,
        )

        next_steps = [
            f'Load the environment with: adare environment load {env_file_path}',
            f'Verify the VM is ready: adare env verify {request.name}',
        ]

        return Result.ok(EnvironmentInfo(
            id='',  # Not yet in database (just a descriptor file)
            name=request.name,
            description='',
            vm_name=None,
            hypervisor='qemu',
            os_platform=None,
            file_path=env_file_path,
            next_steps=next_steps,
            tip='Baked-URL environment created. The disk is downloaded and '
                'verified against vm_sha256 on first load.',
        ))

    def _create_recipe(self, request: EnvironmentCreateRequest) -> Result[EnvironmentInfo]:
        """
        Write a declarative recipe environment descriptor (no VM build).

        The heavy QEMU disk build happens later, once, on `environment load`;
        this only resolves the OS profile, determines the ISO's sha256, and
        writes the recipe YAML into the project's environments directory.

        The ISO source is either a local path (CLI — hashed here) or a published
        URL + provided sha256 (web — nothing local to hash; the ISO is
        downloaded and verified on load).
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

        if request.setup_level is not None:
            try:
                setup_level = SetupLevel(request.setup_level)
            except ValueError:
                return Result.fail(
                    code='InvalidSetupLevelError',
                    message=f'Invalid setup_level: {request.setup_level}',
                    solutions=['setup_level must be one of 0 (bare), 1 (base), 2 (full), 3 (agent)'],
                )
        else:
            setup_level = SetupLevel.FULL

        # Determine the ISO source + its sha256. A URL is the web variant's
        # publish-ready model: nothing local to hash, so the analyst-supplied
        # sha256 is required and the ISO is verified after download on load.
        if request.iso_url:
            if not request.iso_sha256:
                return Result.fail(
                    code='MissingIsoSha256Error',
                    message='A recipe ISO URL requires an explicit iso_sha256.',
                    solutions=[
                        'Provide the SHA256 of the hosted ISO',
                        'Compute it with: shasum -a 256 <iso>',
                    ],
                )
            iso_source: str | Path = request.iso_url
            iso_sha256 = request.iso_sha256
        else:
            iso_source = request.iso_path
            iso_sha256 = hash_file_sha256(request.iso_path)

        env_file_path = build_recipe_environment_file(
            os_name=request.os_profile,
            os_def=os_def,
            iso_path=iso_source,
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

    def publish_prepare(
        self,
        project_path: Path,
        name: str,
        vm_url: str,
        vm_format: str | None = None,
        verify_url: bool = False,
    ) -> Result[EnvironmentInfo]:
        """Convert a local-path baked environment into a publish-ready URL one.

        Hashes the local disk referenced by ``vm:``, then rewrites the descriptor
        to ``vm: <vm_url>``, ``vm_type: url``, ``vm_format: <fmt>`` and
        ``vm_sha256: <hash of the exact local bytes>``. The sha computed here is
        the integrity anchor consumers re-verify after downloading from the URL.

        With ``verify_url`` the hosted object is downloaded and hashed, confirming
        it matches the local disk — this catches a wrong/HTML share link or an
        upload whose bytes differ from the local disk.
        """
        from adare.helperfunctions.file.hash import file_sha256_with_progress
        from adarelib.helper.yaml import dict_to_yaml, yaml_to_dict

        target = self._resolve_publish_target(project_path, name, vm_url, vm_format)
        if not target.success:
            return target
        descriptor, metadata, disk, fmt = target.data

        vm_sha256 = file_sha256_with_progress(
            disk, description=f'Hashing local disk {disk.name}', silent=False,
        )

        if verify_url:
            verify_result = self._verify_hosted_url_matches(vm_url, vm_sha256)
            if not verify_result.success:
                return verify_result

        # Rewrite the descriptor in place, preserving all other fields.
        raw = yaml_to_dict(descriptor)
        raw['vm'] = vm_url
        raw['vm_type'] = 'url'
        raw['vm_sha256'] = vm_sha256
        if fmt is not None:
            raw['vm_format'] = fmt
        dict_to_yaml(descriptor, raw)

        return Result.ok(EnvironmentInfo(
            id='',
            name=name,
            description='',
            vm_name=None,
            hypervisor=metadata.hypervisor or 'qemu',
            os_platform=metadata.os.platform if metadata.os else None,
            file_path=descriptor,
            next_steps=[
                f'Submit for sharing: adare web submit environment {name}',
                f'Or load locally to verify: adare environment load {descriptor}',
            ],
            tip=f'Descriptor rewritten to URL + vm_sha256 ({vm_sha256[:12]}…). '
                'Consumers re-verify this hash after downloading.',
        ))

    def _resolve_publish_target(
        self, project_path: Path, name: str, vm_url: str, vm_format: str | None,
    ) -> "Result[tuple]":
        """Validate inputs and resolve the descriptor, local disk, and format.

        Returns ``Result.ok((descriptor, metadata, disk, fmt))`` or a failing
        ``Result`` describing why the environment cannot be prepared. Kept
        separate from :meth:`publish_prepare` so the conversion itself (hash →
        verify → rewrite) stays flat.
        """
        from urllib.parse import urlparse

        from adare.backend.project.directory import ProjectDirectory
        from adare.types.environment import parse_environment_file

        _VM_FORMATS = ('qcow2', 'ova', 'vmdk', 'vdi', 'img', 'raw')
        _DISK_EXTENSIONS = ('.ova', '.qcow2', '.vmdk', '.vdi', '.img', '.raw')

        if urlparse(vm_url).scheme not in ('http', 'https'):
            return Result.fail(
                code='InvalidVmUrl',
                message=f'--vm-url must be an http(s) URL (got {vm_url!r}).',
                solutions=['Host the disk image and pass its http(s) URL'],
            )
        if vm_format is not None and vm_format not in _VM_FORMATS:
            return Result.fail(
                code='InvalidVmFormat',
                message='--vm-format must be one of: ' + ', '.join(_VM_FORMATS),
                solutions=['Pass a supported disk format'],
            )

        # Resolve the descriptor from the project's environments directory (the
        # env need not be loaded into the database yet).
        env_dir = ProjectDirectory(project_path).environments
        descriptor: Path | None = None
        for candidate in (env_dir / f'{name}.yml', env_dir / f'{name}.yaml', Path(name)):
            if candidate.is_file():
                descriptor = candidate
                break
        if descriptor is None:
            return Result.fail(
                code='EnvironmentFileNotFound',
                message=f'Environment descriptor not found for {name!r} in {env_dir}.',
                solutions=['Check the environment name', 'Create it first with: adare env create'],
            )

        metadata = parse_environment_file(descriptor)
        if metadata is None or metadata.is_recipe_environment or not metadata.vm:
            return Result.fail(
                code='NotABakedEnvironment',
                message='publish-prepare only applies to a baked disk environment (a "vm:" source).',
                solutions=['Recipe environments already publish their ISO by URL + iso_sha256'],
            )
        if urlparse(metadata.vm).scheme in ('http', 'https'):
            return Result.fail(
                code='AlreadyUrlEnvironment',
                message=f'{name!r} already references a URL ({metadata.vm}); nothing local to hash.',
                solutions=['Edit the descriptor directly if you need to change the URL/sha'],
            )

        # Resolve the local disk (absolute, or relative to the descriptor).
        disk = Path(metadata.vm)
        if not disk.is_absolute():
            disk = descriptor.parent / metadata.vm
        if not disk.is_file():
            return Result.fail(
                code='VmDiskNotFound',
                message=f'Local VM disk not found: {disk}',
                solutions=['Fix the "vm:" path in the descriptor', 'Use an absolute path'],
            )

        # Determine the format: explicit flag wins, else infer from the disk
        # suffix; required when the URL carries no recognized disk extension.
        fmt = vm_format
        if fmt is None:
            inferred = disk.suffix.lower().lstrip('.')
            if inferred in _VM_FORMATS:
                fmt = inferred
        url_has_ext = urlparse(vm_url).path.lower().endswith(_DISK_EXTENSIONS)
        if fmt is None and not url_has_ext:
            return Result.fail(
                code='MissingVmFormat',
                message='Could not infer the disk format; pass --vm-format explicitly.',
                solutions=['--vm-format one of: ' + ', '.join(_VM_FORMATS)],
            )

        return Result.ok((descriptor, metadata, disk, fmt))

    def _verify_hosted_url_matches(self, vm_url: str, expected_sha256: str) -> Result[None]:
        """Download the hosted URL and confirm it hashes to ``expected_sha256``.

        Catches a wrong/HTML share link or an upload whose bytes differ from the
        local disk. The download goes to a temp file that is always cleaned up.
        """
        import tempfile

        from adare.helperfunctions.file.hash import file_sha256_with_progress
        from adare.helperfunctions.web.download import download

        tmp = Path(tempfile.mkdtemp(prefix='adare-verify-')) / 'hosted.bin'
        try:
            log.info(f'Verifying hosted URL bytes against local disk: {vm_url}')
            download(vm_url, tmp, quiet=False)
            if not tmp.is_file() or tmp.stat().st_size == 0:
                return Result.fail(
                    code='VerifyUrlFailed',
                    message=f'Downloaded nothing from {vm_url} (empty response).',
                    solutions=['Check the URL is a direct download link, not an HTML page'],
                )
            hosted_sha256 = file_sha256_with_progress(
                tmp, description='Hashing hosted object', silent=False,
            )
            if hosted_sha256.lower() != expected_sha256.lower():
                return Result.fail(
                    code='VerifyUrlMismatch',
                    message=(
                        f'Hosted object does not match the local disk: expected {expected_sha256} '
                        f'but the URL returned bytes hashing to {hosted_sha256}.'
                    ),
                    solutions=[
                        'The share link may return an HTML page — use a direct "download" link',
                        'Re-upload the exact local disk, then retry',
                    ],
                )
            log.info('Hosted URL matches the local disk hash')
            return Result.ok(None)
        except (OSError, ConnectionError, TimeoutError, ValueError) as e:
            return Result.fail(
                code='VerifyUrlFailed',
                message=f'Could not verify hosted URL {vm_url}: {e}',
                solutions=['Check network connectivity', 'Check the URL is reachable'],
            )
        finally:
            try:
                if tmp.exists():
                    tmp.unlink()
                tmp.parent.rmdir()
            except OSError:
                pass

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

    def list_os_profiles(self) -> Result[list[dict]]:
        """
        List available OS profiles for building recipe environments.

        Returns:
            Result[list[dict]] with one summary dict per catalog entry.
        """
        profiles = [
            {
                'name': os_def.name,
                'display_name': os_def.display_name,
                'platform': os_def.platform,
                'distribution': os_def.distribution,
                'version': os_def.version,
                'architecture': os_def.architecture,
                'default_disk_size': os_def.default_disk_size,
                'default_ram_mb': os_def.default_ram_mb,
                'default_cpus': os_def.default_cpus,
            }
            for os_def in list_os_definitions()
        ]
        return Result.ok(profiles)
