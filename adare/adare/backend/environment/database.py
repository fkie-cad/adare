# external imports
from pathlib import Path
import attrs

# internal imports
from adare.types.environment import EnvironmentMetadata
from adare.database.api.environment import EnvironmentDbApi
from adare.database.models.global_models import Environment, Project
from adare.backend.environment.exceptions import EnvironmentDeletionError, EnvironmentDoesNotExistInDatabase, \
    EnvironmentAlreadyExists, EnvironmentUpdateError

# configure logging
import logging
log = logging.getLogger(__name__)


def _cleanup_vm_file_if_unused(vm_file_path: Path, project_path: Path, db):
    """
    Clean up VM file if it's not used by any other environments in the project.
    
    Args:
        vm_file_path: Path to the VM file that might need cleanup
        project_path: Path to the project directory
        db: Database API instance (already within context)
    """
    if not vm_file_path or not project_path:
        return
    
    # Only clean up files that are in the project's vm directory
    from adare.backend.project.directory import ProjectDirectory
    project_dir = ProjectDirectory(project_path)
    
    try:
        # Check if the VM file is within the project's vm directory
        vm_file_resolved = vm_file_path.resolve()
        project_vm_dir_resolved = project_dir.vm.resolve()
        
        # If the VM file is not within the project's vm directory, don't delete it
        # This protects VM files that are stored outside the project (e.g., global VMs)
        if not vm_file_resolved.is_relative_to(project_vm_dir_resolved):
            log.debug(f"VM file {vm_file_path} is outside project vm directory, skipping cleanup")
            return
        
        # Check if any other environments in this project are using the same VM file
        all_project_environments = db.get_environments(project_path)
        
        for env in all_project_environments:
            if env.vm and env.vm.file and Path(env.vm.file).resolve() == vm_file_resolved:
                log.debug(f"VM file {vm_file_path} still in use by environment {env.name}, skipping cleanup")
                return
        
        # No other environments are using this VM file, safe to delete
        if vm_file_path.exists():
            vm_file_path.unlink()
            log.info(f"Cleaned up unused VM file: {vm_file_path}")
        else:
            log.debug(f"VM file {vm_file_path} already deleted or doesn't exist")
            
    except (OSError, PermissionError) as e:
        log.warning(f"Failed to cleanup VM file {vm_file_path}: {e}")
    except ValueError as e:
        log.warning(f"Invalid path during VM file cleanup {vm_file_path}: {e}")



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
            log.warning(f'Unknown field requested: {field}. Available: id, name, description, sha256hash, file, vm_id, installations')
    
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
            except Exception as e:
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

def update_environment(project_path: Path, environment_metadata: EnvironmentMetadata, environment_file: Path, sha256hash: str, vm_id: str, force: bool = False):    
    
    # Now handle environment operations in separate session
    with EnvironmentDbApi() as db:
        environments = db.get_environments_by_path(environment_file)
        if not environments:
            environment, _ = db.get_or_create_environment(
                project_path=project_path,
                name=environment_metadata.name,
                description=environment_metadata.description,
                vm_id=vm_id,
                tags=environment_metadata.tags,
                installations=[attrs.asdict(inst) for inst in environment_metadata.postsetupinstallations],
                environment_file=environment_file,
                sha256hash=sha256hash,
                hypervisor=environment_metadata.hypervisor
            )
            # Extract ID while session is still active to avoid DetachedInstanceError
            environment_id = environment.id
            log.info(f'environment file {environment_file} loaded')
            return environment_id
        for env in environments:
            if env.sha256hash == sha256hash:
                if not force:
                    raise EnvironmentAlreadyExists(
                        log,
                        f'environment file {environment_file} already exists in the database',
                        possible_solutions=[
                            'delete the environment from the database',
                            'use a different environment file',
                            'use --force flag to update the existing environment'
                        ])
                else:
                    log.info(f'Environment with hash {sha256hash[:16]}... already exists, but force=True - updating VM association')
                    # Update the existing environment with new VM reference
                    with db:
                        env.vm_id = vm_id
                        env.hypervisor = environment_metadata.hypervisor
                        env.name = environment_metadata.name
                        env.description = environment_metadata.description
                        # Commit happens automatically when context exits
                    log.info(f'Updated environment {env.id} with VM {vm_id}')
                    return env.id

        latest_env = environments[-1]
        if latest_env.runs:
            if not force:
                raise EnvironmentUpdateError(
                    log,
                    f'environment file {environment_file} has already been used for experiments, so it cannot be updated because this would invalidate the results',
                    possible_solutions=[
                        'run with --force to delete all runs and update the environment',
                    ])
            log.info(f'environment file {environment_file} has already been used for experiments -> deleting all runs')
            for run in latest_env.runs:
                db.delete_experiment_run(run)
                log.info(f'deleted run {run.id}')
            environment = db.update_environment(
                name=environment_metadata.name,
                description=environment_metadata.description,
                vm_id=vm_id,
                environment_file=environment_file,
                sha256hash=sha256hash,
                hypervisor=environment_metadata.hypervisor
            )
            if not environment:
                raise EnvironmentUpdateError(
                    log,
                    f'Failed to update environment for file {environment_file}',
                    possible_solutions=[
                        'Check if the environment file is valid',
                        'Try recreating the environment',
                    ])
            # Extract ID while session is still active
            environment_id = environment.id
            log.info(f'environment {environment_metadata.name} updated')
        else:
            log.info(f'environment file {environment_file} has already been loaded -> updating')
            environment = db.update_environment(
                name=environment_metadata.name,
                description=environment_metadata.description,
                vm_id=vm_id,
                environment_file=environment_file,
                sha256hash=sha256hash,
                hypervisor=environment_metadata.hypervisor
            )
            if not environment:
                raise EnvironmentUpdateError(
                    log,
                    f'Failed to update environment for file {environment_file}',
                    possible_solutions=[
                        'Check if the environment file is valid',
                        'Try recreating the environment',
                    ])
            # Extract ID while session is still active
            environment_id = environment.id
            log.info(f'environment {environment_metadata.name} updated')

        return environment_id


def resolve_environment_identifier(identifier: str) -> str:
    """
    Resolve environment identifier (name or ULID) to ULID.

    Args:
        identifier: Environment name or ULID

    Returns:
        Environment ULID

    Raises:
        EnvironmentDoesNotExistInDatabase: If environment not found
    """
    from adare.database.models.global_models import Environment

    with EnvironmentDbApi() as db:
        # First try as ULID (check if it exists)
        env = db.get_environment_by_ulid(identifier)
        if env:
            return env.id

        # Try as name (global environments)
        env = db._session.query(Environment).filter_by(name=identifier).first()
        if env:
            return env.id

        # Not found by either method
        raise EnvironmentDoesNotExistInDatabase(
            log,
            f'Environment "{identifier}" not found (tried as both ULID and name)',
            possible_solutions=[
                'Check if the environment name is spelled correctly',
                'List available environments with: adare env list',
                'Load the environment first with: adare env load <path>'
            ]
        )


def delete_environment(environment_ulid: str, force: bool = False):
    from adare.database.reference_manager import reference_manager
    from adare.database.api.base import ProjectDatabaseApi
    from adare.database.models.project_models import ExperimentRun, Experiment

    with EnvironmentDbApi() as db:
        environment = _get_environment_or_raise(
            db,
            environment_ulid,
            log,
            f'environment with ulid {environment_ulid} does not exist in the database',
        )

        # Store VM info before deletion for cleanup
        vm_id = None
        vm_file_path = None
        if environment.vm:
            vm_id = environment.vm.id
            if environment.vm.file:
                vm_file_path = Path(environment.vm.file)

        # Check for runs using this environment across all projects
        projects_using_env = reference_manager.get_projects_using_environment(environment_ulid)

        if projects_using_env:
            # Count runs across all projects
            total_runs = 0
            orphaned_experiments = []

            for project_path_str in projects_using_env:
                project_path = Path(project_path_str)
                try:
                    with ProjectDatabaseApi(project_path) as project_api:
                        # Get runs using this environment
                        runs = project_api._session.query(ExperimentRun).filter(
                            ExperimentRun.environment_id == environment_ulid
                        ).all()
                        total_runs += len(runs)

                        # Check for experiments that would be orphaned
                        experiments = project_api._session.query(Experiment).all()
                        for exp in experiments:
                            if exp.environment_ids and environment_ulid in exp.environment_ids:
                                if len(exp.environment_ids) == 1:
                                    orphaned_experiments.append(f"{exp.name} (project: {project_path.name})")
                except Exception as e:
                    log.warning(f"Error checking project {project_path}: {e}")

            # Check for orphaned experiments
            if orphaned_experiments and not force:
                experiments_list = ', '.join(orphaned_experiments)
                raise EnvironmentDeletionError(
                    log,
                    f'environment {environment.id} cannot be deleted because the following experiments would become orphaned (they only use this environment): {experiments_list}',
                    possible_solutions=[
                        'run with --force to delete the environment and all runs',
                        'add other environments to the experiments first',
                    ])

            # Check for existing runs
            if total_runs > 0 and not force:
                raise EnvironmentDeletionError(
                    log,
                    f'environment {environment.id} has {total_runs} experiment run(s) across {len(projects_using_env)} project(s), so it cannot be deleted because this would invalidate the results',
                    possible_solutions=[
                        'run with --force to delete all runs and the environment',
                    ])

            # Delete runs if force is used
            if total_runs > 0 and force:
                log.info(f'environment {environment.id} has {total_runs} run(s) -> deleting with --force')
                for project_path_str in projects_using_env:
                    project_path = Path(project_path_str)
                    try:
                        with ProjectDatabaseApi(project_path) as project_api:
                            runs = project_api._session.query(ExperimentRun).filter(
                                ExperimentRun.environment_id == environment_ulid
                            ).all()
                            for run in runs:
                                project_api._session.delete(run)
                                log.info(f'deleted run {run.id} from project {project_path.name}')
                            project_api._session.commit()
                    except Exception as e:
                        log.error(f"Error deleting runs from project {project_path}: {e}")

        db.delete_environment(environment)
        log.info(f'deleted environment {environment.id}')

        # Delete the environment file from disk if force is used
        # IMPORTANT: Only delete files within managed storage (ENVIRONMENTS_DIR)
        if force and environment.file:
            env_file = Path(environment.file)
            if env_file.exists():
                # Safety check: Only delete files in managed storage
                from adare.config.configdirectory import ENVIRONMENTS_DIR
                try:
                    env_file_resolved = env_file.resolve()
                    environments_dir_resolved = ENVIRONMENTS_DIR.resolve()

                    # Check if file is within managed environments directory
                    if env_file_resolved.is_relative_to(environments_dir_resolved):
                        try:
                            env_file.unlink()
                            log.info(f'Deleted managed environment file: {env_file}')
                        except (OSError, PermissionError) as e:
                            log.warning(f'Failed to delete environment file {env_file}: {e}')
                    else:
                        log.warning(f'Skipping deletion of environment file outside managed storage: {env_file}')
                        log.warning(f'Only files in {ENVIRONMENTS_DIR} are automatically deleted')
                except ValueError as e:
                    log.warning(f'Could not verify environment file path {env_file}: {e}')

    # Clean up VM if force is used and VM is not used by other environments
    if force and vm_id:
        try:
            # Check if VM is still used by any other environments
            with EnvironmentDbApi() as db:
                all_environments = db.get_environments()
                vm_still_in_use = any(env.vm_id == vm_id for env in all_environments)

            if not vm_still_in_use:
                log.info(f'VM {vm_id} is not used by any other environment, cleaning up...')

                # Delete VM database record
                import adare.backend.vm.database as vm_database
                vm_database.delete_vm(vm_id)
                log.info(f'Deleted VM database record: {vm_id}')

                # Delete VM file from disk - ONLY if it's in managed storage
                if vm_file_path and vm_file_path.exists():
                    try:
                        from adare.config.configdirectory import VMS_DIR
                        
                        # Resolve paths to handle symlinks and relative paths
                        vm_file_resolved = vm_file_path.resolve()
                        vms_dir_resolved = VMS_DIR.resolve()
                        
                        # Check if file is within managed VMs directory
                        if vm_file_resolved.is_relative_to(vms_dir_resolved):
                            vm_file_path.unlink()
                            log.info(f'Deleted managed VM file: {vm_file_path}')
                        else:
                            log.info(f'Skipping deletion of external VM file: {vm_file_path}')
                            
                    except (OSError, PermissionError) as e:
                        log.warning(f'Failed to delete VM file {vm_file_path}: {e}')
                    except ValueError:
                         # Handle cases where paths are on different drives/mounts (Windows)
                         log.info(f'Skipping deletion of external VM file (path error): {vm_file_path}')
            else:
                log.info(f'VM {vm_id} is still used by other environments, skipping cleanup')
        except Exception as e:
            log.warning(f'Failed to cleanup VM {vm_id}: {e}')


def get_environments_ulids(project_path: Path = None) -> list[str]:
    with EnvironmentDbApi() as db:
        return [
            environment.id
            for environment in db.get_environments(project_path)
        ]


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
        'runs_count': 'runs'
    }
    
    with EnvironmentDbApi() as db:
        # Start with base query
        query = db._session.query(db._session.query(Environment).filter_by(id=ulid).first().__class__).filter_by(id=ulid)
        
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
            if 'runs' in needed_relationships:
                environment = environment.options(selectinload(Environment.runs))
            
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
                    result['vm_os_type'] = environment.vm.osinfo.os if environment.vm and environment.vm.osinfo else None
                elif field == 'vm_file_path':
                    result['vm_file_path'] = environment.vm.file if environment.vm else None
                elif field == 'vm_description':
                    result['vm_description'] = environment.vm.description if environment.vm else None
                elif field == 'vm_architecture':
                    result['vm_architecture'] = environment.vm.osinfo.architecture if environment.vm and environment.vm.osinfo else None
                elif field == 'tags':
                    result['tags'] = [tag.name for tag in environment.tags] if hasattr(environment, 'tags') else []
                elif field == 'runs_count':
                    result['runs_count'] = len(environment.runs) if hasattr(environment, 'runs') else 0
                else:
                    log.warning(f'Unknown field requested: {field}. Available: id, name, description, sha256hash, file, vm_id, installations, vm_name, vm_os_type, tags, runs_count')
            except AttributeError as e:
                log.warning(f"Could not access field '{field}': {e}")
                result[field] = None
        
        return result
    
def get_environment_by_hash(sha256hash: str, trigger_exception: bool = True, fields: list[str] = None) -> Environment | dict | None:
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
                log.warning(f'Unknown field requested: {field}. Available: id, name, description, sha256hash, file, vm_id, installations')
        
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
    return get_environment_by_ulid(ulid, fields=['id', 'name', 'description', 'sha256hash', 'file', 'vm_id', 'vm_name', 'vm_os_type'])


def get_environment_summary(ulid: str) -> dict | None:
    """Get basic environment info with key relationships - lighter version."""
    return get_environment_by_ulid(ulid, fields=['id', 'name', 'description', 'vm_name'])


def get_environment_with_vm_details(ulid: str) -> dict | None:
    """Get environment with comprehensive VM information."""
    return get_environment_by_ulid(ulid, fields=['id', 'name', 'vm_name', 'vm_os_type', 'vm_file_path', 'vm_description', 'vm_architecture'])


def get_environment_with_relationships(ulid: str) -> dict | None:
    """Get environment with all relationships loaded."""
    return get_environment_by_ulid(ulid, fields=['id', 'name', 'description', 'vm_name', 'vm_os_type', 'tags', 'runs_count'])


def sync_environments_all(project: str = None):
    with EnvironmentDbApi() as db:
        db.sync_environments_all(project)


def get_environment_path_by_project_and_name(project_path: Path, environment_name: str) -> Path:
    with EnvironmentDbApi() as db:
        environment = db.get_environment_by_project_and_name(
            project_path, environment_name
        )
        if environment:
            return Path(environment.file)
        else:
            raise EnvironmentDoesNotExistInDatabase(
                log,
                f'environment {environment_name} does not exist in the database',
                possible_solutions=[
                    f'Check if environment name "{environment_name}" is spelled correctly',
                    'List available environments with: adare environment list',
                    'If not found via list, create or load: adare environment create <name> OR adare environment load <path>'
                ]
            )

def update_environment_vm_id(environment_ulid: str, vm_id: str):
    """Update the VM ID for an environment (for lazy loading)."""
    with EnvironmentDbApi() as db:
        environment = _get_environment_or_raise(
            db,
            environment_ulid,
            log,
            f'environment with ulid {environment_ulid} does not exist in the database',
        )
        environment.vm_id = vm_id
        db._session.commit()
        log.info(f'Updated environment {environment_ulid} with VM ID {vm_id}')


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
    except Exception as e:
        log.error(f"Failed to get VM IDs for environment {environment_ulid}: {e}")
        return []

