# external imports
# configure logging
import asyncio
import logging
from pathlib import Path

import attrs

from adare.backend.environment.exceptions import (
    EnvironmentDeletionError,
    EnvironmentDiskChanged,
    EnvironmentDoesNotExistInDatabase,
)
from adare.database.api.environment import EnvironmentDbApi
from adare.database.exceptions import DatabaseError
from adare.database.models.global_models import Environment

# internal imports
from adare.types.environment import EnvironmentMetadata

log = logging.getLogger(__name__)


def _get_environment_or_raise(db, ulid: str, log, not_found_msg: str, fields: list[str] = None):
    """
    Get environment or raise exception if not found.

    Args:
        db: Database API instance
        ulid: Environment ULID
        log: Logger instance
        not_found_msg: Error message if not found
        fields: Optional list of fields to extract

    Returns:
        Environment object or dict with requested fields
    """
    environment = db.get_environment_by_ulid(ulid)
    if not environment:
        raise EnvironmentDoesNotExistInDatabase(log, not_found_msg)

    # If no fields specified, return full object (for backward compatibility)
    if fields is None:
        return environment

    # Extract requested fields
    result = {}
    for field in fields:
        if field == 'id':
            result['id'] = environment.id
        elif field == 'name':
            result['name'] = environment.name
        elif field == 'description':
            result['description'] = environment.description
        elif field == 'sha256hash':
            result['sha256hash'] = environment.sha256hash
        elif field == 'file':
            result['file'] = environment.file
        elif field == 'vm_id':
            result['vm_id'] = environment.vm_id
        elif field == 'installations':
            result['installations'] = environment.installations
        else:
            log.warning(
                f'Unknown field requested: {field}. Available: id, name, description, sha256hash, file, vm_id, installations'
            )

    return result


def get_environment_vm_file(environment_ulid: str) -> Path:
    """
    Get the VM file path for a given environment ULID.

    Args:
        environment_ulid: Environment ULID

    Returns:
        Path to the VM file
    """
    with EnvironmentDbApi() as db:
        env = db._session.query(Environment).filter_by(id=environment_ulid).first()
        return Path(env.vm.file) if env and env.vm and env.vm.file else None


def get_environment_os(environment_ulid: str) -> str:
    """
    Get the OS type for a given environment ULID.
    Falls back to parsing environment file if osinfo is not set.

    Args:
        environment_ulid: Environment ULID

    Returns:
        OS type as a string
    """
    with EnvironmentDbApi() as db:
        env = db._session.query(Environment).filter_by(id=environment_ulid).first()

        # Try osinfo first (fast path for VirtualBox and properly configured QEMU VMs)
        if env and env.vm and env.vm.osinfo:
            platform = env.vm.osinfo.platform
            log.info(f"Retrieved OS platform from database: {platform} (env={env.name}, vm={env.vm.name})")
            return platform

        # Fallback: Parse environment file for OS info (QEMU VMs without osinfo)
        if env and env.file:
            try:
                from adare.types.environment import parse_environment_file

                log.info(f"osinfo not available for environment {environment_ulid}, parsing environment file")
                env_metadata = parse_environment_file(Path(env.file))
                platform = env_metadata.os.platform
                log.info(f"Retrieved OS platform from environment file: {platform} (env={env.name})")
                return platform
            except (OSError, ValueError, KeyError, AttributeError) as e:
                log.warning(f"Failed to parse environment file for OS info: {e}")

        log.warning(f"Could not determine OS for environment {environment_ulid}")
        return None


def get_environment_hypervisor(environment_ulid: str) -> str:
    """
    Get the hypervisor type for a given environment ULID.

    Args:
        environment_ulid: Environment ULID

    Returns:
        Hypervisor type as a string (defaults to 'virtualbox' if not specified)
    """
    with EnvironmentDbApi() as db:
        env = db._session.query(Environment).filter_by(id=environment_ulid).first()
        return env.hypervisor if env else 'virtualbox'


def register_environment_version(
    environment_metadata: EnvironmentMetadata,
    environment_file: Path,
    sha256hash: str,
    vm_id: str | None,
) -> str:
    """Record a loaded environment file as the new current version of its name.

    A previous current version is kept (superseded), never deleted: experiment
    runs reference environments by ULID and must keep resolving to the exact
    file and disk they ran against.

    Returns:
        ULID of the new version.
    """
    vm_hash = None
    if vm_id:
        from adare.database.api.vm import VmApi

        with VmApi() as vm_api:
            vm = vm_api.get_vm_by_id(vm_id)
            vm_hash = vm.hash if vm else None

    with EnvironmentDbApi() as db:
        environment = db.create_environment_version(
            name=environment_metadata.name,
            description=environment_metadata.description,
            vm_id=vm_id,
            vm_hash=vm_hash,
            tags=environment_metadata.tags,
            installations=[attrs.asdict(inst) for inst in environment_metadata.postsetupinstallations],
            environment_file=environment_file,
            sha256hash=sha256hash,
            hypervisor=environment_metadata.hypervisor,
        )
        environment_id: str = environment.id
        log.info(f'environment {environment_metadata.name} loaded as version {environment_id}')
        return environment_id


def resolve_environment_identifier(identifier: str, trigger_exception: bool = True) -> str | None:
    """
    Resolve environment identifier (name or ULID) to ULID.

    Args:
        identifier: Environment name or ULID
        trigger_exception: If True (default), raise when not found. If False,
            return None instead — lets callers probe for existence without the
            noisy error log + transaction rollback that an exception triggers.

    Returns:
        Environment ULID, or None when not found and trigger_exception is False.

    Raises:
        EnvironmentDoesNotExistInDatabase: If environment not found and
            trigger_exception is True.
    """

    with EnvironmentDbApi() as db:
        # First try as ULID (check if it exists)
        env = db.get_environment_by_ulid(identifier)
        if env:
            return env.id

        # Try as name (global environments) -> the current version
        env = db.get_current_environment(identifier)
        if env:
            return env.id

        # Not found by either method
        if not trigger_exception:
            return None

        raise EnvironmentDoesNotExistInDatabase(
            log,
            f'Environment "{identifier}" not found (tried as both ULID and name)',
            possible_solutions=[
                'Check if the environment name is spelled correctly',
                'List available environments with: adare env list',
                'Load the environment first with: adare env load <path>',
            ],
        )


def _find_environment_references(version_ids: set[str]) -> tuple[dict[Path, int], list[tuple[Path, str]]]:
    """Scan every registered project for runs and experiments using ``version_ids``.

    Returns:
        (run count per project path, [(project path, experiment name)] for
        experiments that use no other environment)
    """
    from adare.database.api.base import GlobalDatabaseApi, ProjectDatabaseApi
    from adare.database.models.global_models import Project
    from adare.database.models.project_models import Experiment, ExperimentRun

    with GlobalDatabaseApi() as global_api:
        project_paths = [Path(project.path) for project in global_api._session.query(Project).all() if project.path]

    runs_per_project: dict[Path, int] = {}
    orphaned: list[tuple[Path, str]] = []
    for project_path in project_paths:
        if not project_path.exists():
            continue
        try:
            with ProjectDatabaseApi(project_path) as project_api:
                run_count = (
                    project_api._session.query(ExperimentRun)
                    .filter(ExperimentRun.environment_id.in_(version_ids))
                    .count()
                )
                if run_count:
                    runs_per_project[project_path] = run_count
                for experiment in project_api._session.query(Experiment).all():
                    env_ids = set(experiment.environment_ids or [])
                    if env_ids and env_ids <= version_ids:
                        orphaned.append((project_path, experiment.name))
        except (OSError, DatabaseError) as e:
            log.warning(f"Error checking project {project_path}: {e}")
    return runs_per_project, orphaned


def _detach_environment_references(version_ids: set[str], runs_per_project: dict[Path, int]) -> None:
    """Delete runs of ``version_ids`` and drop the ids from experiments (``--force``)."""
    from adare.database.api.base import GlobalDatabaseApi, ProjectDatabaseApi
    from adare.database.models.global_models import Project
    from adare.database.models.project_models import Experiment, ExperimentRun

    with GlobalDatabaseApi() as global_api:
        project_paths = [Path(project.path) for project in global_api._session.query(Project).all() if project.path]

    for project_path in project_paths:
        if not project_path.exists():
            continue
        try:
            with ProjectDatabaseApi(project_path) as project_api:
                if project_path in runs_per_project:
                    for run in (
                        project_api._session.query(ExperimentRun)
                        .filter(ExperimentRun.environment_id.in_(version_ids))
                        .all()
                    ):
                        project_api._session.delete(run)
                        log.info(f'deleted run {run.id} from project {project_path.name}')
                for experiment in project_api._session.query(Experiment).all():
                    env_ids = experiment.environment_ids or []
                    if any(env_id in version_ids for env_id in env_ids):
                        # Reassign (not mutate) so SQLAlchemy sees the JSON change.
                        experiment.environment_ids = [env_id for env_id in env_ids if env_id not in version_ids]
                        log.info(f'detached environment from experiment {experiment.name} ({project_path.name})')
                project_api._session.commit()
        except (OSError, DatabaseError) as e:
            log.error(f"Error detaching environment from project {project_path}: {e}")


def _delete_managed_file(path: Path, managed_dir: Path) -> None:
    """Delete ``path`` only if it lives inside ``managed_dir`` (never user files)."""
    try:
        if not path.exists():
            return
        if path.resolve().is_relative_to(managed_dir.resolve()):
            path.unlink()
            log.info(f'Deleted managed file: {path}')
        else:
            log.info(f'Skipping deletion of file outside managed storage: {path}')
    except (OSError, ValueError) as e:
        log.warning(f'Failed to delete {path}: {e}')


def delete_environment(environment_ulid: str, force: bool = False, cleanup_vm: bool = True):
    """Delete an environment -- every version of its name.

    Refuses while runs or single-environment experiments reference any version,
    unless ``force``: then those runs are deleted and the experiments are
    detached from the environment (left with no environment, not deleted).
    A VM no longer referenced by any environment is torn down when ``cleanup_vm``.
    """
    from adare.config.configdirectory import ENVIRONMENTS_DIR, VMS_DIR

    with EnvironmentDbApi() as db:
        environment = _get_environment_or_raise(
            db,
            environment_ulid,
            log,
            f'environment with ulid {environment_ulid} does not exist in the database',
        )
        name = environment.name
        versions = db.get_environment_versions(name)
        version_ids = {version.id for version in versions}
        vm_ids = {version.vm_id for version in versions if version.vm_id}

    runs_per_project, orphaned = _find_environment_references(version_ids)
    total_runs = sum(runs_per_project.values())
    if orphaned and not force:
        experiments_list = ', '.join(f'{exp} (project: {path.name})' for path, exp in orphaned)
        raise EnvironmentDeletionError(
            log,
            f'environment {name} cannot be deleted because these experiments use no other environment: {experiments_list}',
            possible_solutions=[
                'run with --force to delete the environment and its runs (the experiments are kept, without an environment)',
                'add other environments to the experiments first',
            ],
        )
    if total_runs and not force:
        raise EnvironmentDeletionError(
            log,
            f'environment {name} has {total_runs} experiment run(s) across {len(runs_per_project)} project(s), so it cannot be deleted because this would invalidate the results',
            possible_solutions=['run with --force to delete all runs and the environment'],
        )
    if force and (total_runs or orphaned):
        log.info(f'environment {name}: deleting {total_runs} run(s) and detaching experiments (--force)')
        _detach_environment_references(version_ids, runs_per_project)

    with EnvironmentDbApi() as db:
        for version in db.get_environment_versions(name):
            env_file = Path(version.file) if version.file else None
            db.delete_environment(version)
            log.info(f'deleted environment {name} version {version.id}')
            if force and env_file:
                _delete_managed_file(env_file, ENVIRONMENTS_DIR)

    if not cleanup_vm:
        return
    from adare.backend.vm import commands as vm_commands
    from adare.database.api.vm import VmApi

    for vm_id in vm_ids:
        try:
            with EnvironmentDbApi() as db:
                if any(env.vm_id == vm_id for env in db.get_environments(include_superseded=True)):
                    log.info(f'VM {vm_id} is still used by other environments, skipping cleanup')
                    continue
            with VmApi() as vm_api:
                vm = vm_api.get_vm_by_id(vm_id)
                vm_file_path = Path(vm.file) if vm and vm.file else None
            log.info(f'VM {vm_id} is not used by any other environment, cleaning up...')
            # Tears down hypervisor state (instances, domains, overlays) and the
            # VM database record. Sync entry point: the CLI, and the web API runs
            # it in a worker thread.
            asyncio.run(vm_commands.delete_vm(vm_id, force=force))
            log.info(f'Deleted VM (hypervisor + database record): {vm_id}')
            if vm_file_path:
                _delete_managed_file(vm_file_path, VMS_DIR)
        except (OSError, DatabaseError, ValueError) as e:
            log.warning(f'Failed to cleanup VM {vm_id}: {e}')


def get_environments_ulids(project_path: Path = None) -> list[str]:
    with EnvironmentDbApi() as db:
        return [environment.id for environment in db.get_environments(project_path)]


def get_environment_by_ulid(ulid: str, fields: list[str] = None) -> Environment | dict | None:
    """
    Get environment by ULID with intelligent relationship loading.

    Args:
        ulid: Environment ULID
        fields: Optional list of fields to extract. If None, returns full object.
                Available fields: 'id', 'name', 'description', 'sha256hash', 'file', 'vm_id', 'installations'
                Relationship fields: 'vm_name', 'vm_os_type', 'vm_file_path', 'tags'

    Returns:
        Environment: Full object if fields=None
        dict: Environment data if fields specified
        None: If environment not found
    """
    from sqlalchemy.orm import joinedload, selectinload

    # Define which fields require which relationships
    RELATIONSHIP_REQUIREMENTS = {
        'vm_name': 'vm',
        'vm_id': 'vm',
        'vm_os_type': 'vm',
        'vm_file_path': 'vm',
        'vm_description': 'vm',
        'vm_architecture': 'vm',
        'tags': 'tags',
    }

    with EnvironmentDbApi() as db:
        # Add eager loading based on requested fields
        if fields:
            needed_relationships = set()
            for field in fields:
                if field in RELATIONSHIP_REQUIREMENTS:
                    needed_relationships.add(RELATIONSHIP_REQUIREMENTS[field])

            # Build query with necessary eager loading
            environment = db._session.query(Environment).filter_by(id=ulid)

            # Apply eager loading selectively
            if 'vm' in needed_relationships:
                environment = environment.options(joinedload(Environment.vm))
            if 'tags' in needed_relationships:
                environment = environment.options(selectinload(Environment.tags))

            environment = environment.first()
        else:
            # Simple query for backward compatibility
            environment = db.get_environment_by_ulid(ulid)

        if not environment:
            return None

        # Return full object for backward compatibility
        if fields is None:
            return environment

        # Extract requested fields safely
        result = {}
        for field in fields:
            try:
                if field == 'id':
                    result['id'] = environment.id
                elif field == 'name':
                    result['name'] = environment.name
                elif field == 'description':
                    result['description'] = environment.description
                elif field == 'sha256hash':
                    result['sha256hash'] = environment.sha256hash
                elif field == 'file':
                    result['file'] = environment.file
                elif field == 'vm_id':
                    result['vm_id'] = environment.vm_id
                elif field == 'installations':
                    result['installations'] = environment.installations
                # Foreign key fields - safely loaded with eager loading
                elif field == 'vm_name':
                    result['vm_name'] = environment.vm.name if environment.vm else None
                elif field == 'vm_os_type':
                    result['vm_os_type'] = (
                        environment.vm.osinfo.os if environment.vm and environment.vm.osinfo else None
                    )
                elif field == 'vm_file_path':
                    result['vm_file_path'] = environment.vm.file if environment.vm else None
                elif field == 'vm_description':
                    result['vm_description'] = environment.vm.description if environment.vm else None
                elif field == 'vm_architecture':
                    result['vm_architecture'] = (
                        environment.vm.osinfo.architecture if environment.vm and environment.vm.osinfo else None
                    )
                elif field == 'tags':
                    result['tags'] = [tag.name for tag in environment.tags] if hasattr(environment, 'tags') else []
                else:
                    log.warning(
                        f'Unknown field requested: {field}. Available: id, name, description, sha256hash, file, vm_id, installations, vm_name, vm_os_type, tags'
                    )
            except AttributeError as e:
                log.warning(f"Could not access field '{field}': {e}")
                result[field] = None

        return result


def get_environment_by_hash(
    sha256hash: str, trigger_exception: bool = True, fields: list[str] = None
) -> Environment | dict | None:
    """
    Get environment by hash.

    Args:
        sha256hash: Environment file hash
        trigger_exception: Whether to raise exception if not found
        fields: Optional list of fields to extract

    Returns:
        Environment: Full object if fields=None
        dict: Environment data if fields specified
        None: If environment not found and trigger_exception=False
    """
    with EnvironmentDbApi() as db:
        environment = db.get_environment_by_hash(sha256hash)
        if not environment:
            if not trigger_exception:
                return None
            raise EnvironmentDoesNotExistInDatabase(
                log,
                f'environment with hash {sha256hash} does not exist in the database',
            )

        # Return full object for backward compatibility
        if fields is None:
            return environment

        # Extract requested fields
        result = {}
        for field in fields:
            if field == 'id':
                result['id'] = environment.id
            elif field == 'name':
                result['name'] = environment.name
            elif field == 'description':
                result['description'] = environment.description
            elif field == 'sha256hash':
                result['sha256hash'] = environment.sha256hash
            elif field == 'file':
                result['file'] = environment.file
            elif field == 'vm_id':
                result['vm_id'] = environment.vm_id
            elif field == 'installations':
                result['installations'] = environment.installations
            else:
                log.warning(
                    f'Unknown field requested: {field}. Available: id, name, description, sha256hash, file, vm_id, installations'
                )

        return result


def get_environment_hash(ulid: str) -> str:
    with EnvironmentDbApi() as db:
        environment = _get_environment_or_raise(
            db,
            ulid,
            log,
            f'environment with ulid {ulid} does not exist in the database',
        )
        return environment.sha256hash


def get_environment_installations(ulid: str) -> list:
    with EnvironmentDbApi() as db:
        environment = _get_environment_or_raise(
            db,
            ulid,
            log,
            f'environment with ulid {ulid} does not exist in the database',
        )
        return environment.installations


def sync_environment(ulid: str, remote_ulid: str, remote_url: str, is_published: bool) -> dict:
    with EnvironmentDbApi() as db:
        return db.sync_environment(ulid, remote_ulid, remote_url, is_published)


def get_environment_data(ulid: str) -> dict | None:
    """Get full environment data with relationships - convenience function for common case."""
    return get_environment_by_ulid(
        ulid, fields=['id', 'name', 'description', 'sha256hash', 'file', 'vm_id', 'vm_name', 'vm_os_type']
    )


def get_environment_summary(ulid: str) -> dict | None:
    """Get basic environment info with key relationships - lighter version."""
    return get_environment_by_ulid(ulid, fields=['id', 'name', 'description', 'vm_name'])


def get_environment_with_vm_details(ulid: str) -> dict | None:
    """Get environment with comprehensive VM information."""
    return get_environment_by_ulid(
        ulid, fields=['id', 'name', 'vm_name', 'vm_os_type', 'vm_file_path', 'vm_description', 'vm_architecture']
    )


def get_environment_path_by_project_and_name(project_path: Path, environment_name: str) -> Path:
    with EnvironmentDbApi() as db:
        environment = db.get_environment_by_project_and_name(project_path, environment_name)
        if environment:
            return Path(environment.file)
        raise EnvironmentDoesNotExistInDatabase(
            log,
            f'environment {environment_name} does not exist in the database',
            possible_solutions=[
                f'Check if environment name "{environment_name}" is spelled correctly',
                'List available environments with: adare environment list',
                'If not found via list, create or load: adare environment create <name> OR adare environment load <path>',
            ],
        )


def verify_environment_vm(environment_ulid: str) -> None:
    """Fail if the environment and its (shared) VM no longer agree.

    Several environments can share one VM row. A forced reload of one of them
    may replace that VM's disk, so each environment version pins the disk hash
    it was loaded with. Run setup reads the hypervisor from the environment and
    instance management reads it from the VM, so the two must match as well
    (loads enforce this; rows from before that check may not).
    """
    with EnvironmentDbApi() as db:
        env = db.get_environment_by_ulid(environment_ulid)
        if not env or not env.vm:
            return
        name, vm_name = env.name, env.vm.name
        pinned, registered = env.vm_hash, env.vm.hash
        env_hypervisor, vm_hypervisor = env.hypervisor, env.vm.hypervisor
    if pinned and pinned != registered:
        raise EnvironmentDiskChanged(
            log,
            f"Environment '{name}' was loaded against disk {pinned[:16]}..., but VM '{vm_name}' "
            f"now has disk {registered[:16]}... (replaced by a forced reload of another environment)",
            possible_solutions=[f'Reload the environment to accept the new disk: adare env load --force {name}'],
        )
    if env_hypervisor != vm_hypervisor:
        raise EnvironmentDiskChanged(
            log,
            f"Environment '{name}' declares hypervisor '{env_hypervisor}', but its VM '{vm_name}' "
            f"is registered for '{vm_hypervisor}'",
            possible_solutions=[
                f'Set "hypervisor: {vm_hypervisor}" in the environment file and reload it with --force',
                'Or remove the environment and load it with a separate disk',
            ],
        )


def get_environment_vm_ids(environment_ulid: str) -> list:
    """
    Get VM IDs associated with an environment.

    Args:
        environment_ulid: Environment ULID

    Returns:
        List of VM IDs (usually just one VM per environment)
    """
    try:
        with EnvironmentDbApi() as db:
            environment = db.get_environment_by_ulid(environment_ulid)
            if not environment or not environment.vm_id:
                return []
            return [environment.vm_id]
    except (OSError, DatabaseError) as e:
        log.error(f"Failed to get VM IDs for environment {environment_ulid}: {e}")
        return []
