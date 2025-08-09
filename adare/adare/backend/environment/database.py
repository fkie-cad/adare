# external imports
from pathlib import Path
import attrs

# internal imports
from adare.types.environment import EnvironmentMetadata
from adare.database.api.environment import EnvironmentDbApi
from adare.database.models.experiment import Environment, Project
from adare.backend.environment.exceptions import EnvironmentDeletionError, EnvironmentDoesNotExistInDatabase, \
    EnvironmentAlreadyExists, EnvironmentUpdateError

# configure logging
import logging
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
        elif field == 'project_id':
            result['project_id'] = environment.project_id
        elif field == 'installations':
            result['installations'] = environment.installations
        else:
            log.warning(f'Unknown field requested: {field}. Available: id, name, description, sha256hash, file, vm_id, project_id, installations')
    
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
    
    Args:
        environment_ulid: Environment ULID
    
    Returns:
        OS type as a string
    """
    with EnvironmentDbApi() as db:
        env = db._session.query(Environment).filter_by(id=environment_ulid).first()
        return env.vm.osinfo.platform if env and env.vm and env.vm.osinfo else None

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
                sha256hash=sha256hash
            )
            # Extract ID while session is still active to avoid DetachedInstanceError
            environment_id = environment.id
            log.info(f'environment file {environment_file} loaded')
            return environment_id
        for env in environments:
            if env.sha256hash == sha256hash:
                raise EnvironmentAlreadyExists(
                    log,
                    f'environment file {environment_file} already exists in the database',
                    possible_solutions=[
                        'delete the environment from the database',
                        'use a different environment file',
                    ])

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
                sha256hash=sha256hash
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
                sha256hash=sha256hash
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


def delete_environment(environment_ulid: str, force: bool = False):
    with EnvironmentDbApi() as db:
        environment = _get_environment_or_raise(
            db,
            environment_ulid,
            log,
            f'environment with ulid {environment_ulid} does not exist in the database',
        )
        if environment.runs:
            if not force:
                raise EnvironmentDeletionError(
                    log,
                    f'environment {environment.id} has already been used for experiments, so it cannot be deleted because this would invalidate the results',
                    possible_solutions=[
                        'run with --force to delete all runs and the environment',
                        'create a new environment with a new name',
                    ])
            log.info(f'environment {environment.id} has already been used for experiments -> deleting all runs')
            for run in environment.runs:
                db.delete_experiment_run(run)
                log.info(f'deleted run {run.id}')
        db.delete_environment(environment)
        log.info(f'deleted environment {environment.id}')


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
                Available fields: 'id', 'name', 'description', 'sha256hash', 'file', 'vm_id', 'project_id', 'installations'
                Relationship fields: 'vm_name', 'vm_os_type', 'vm_file_path', 'project_name', 'project_path', 'tags'
    
    Returns:
        Environment: Full object if fields=None
        dict: Environment data if fields specified
        None: If environment not found
    """
    from sqlalchemy.orm import joinedload, selectinload
    from adare.database.models.experiment import Project, Vm
    
    # Define which fields require which relationships
    RELATIONSHIP_REQUIREMENTS = {
        'vm_name': 'vm',
        'vm_id': 'vm',
        'vm_os_type': 'vm',
        'vm_file_path': 'vm',
        'vm_description': 'vm',
        'vm_architecture': 'vm',
        'project_name': 'project',
        'project_path': 'project',
        'project_description': 'project',
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
            if 'project' in needed_relationships:
                environment = environment.options(joinedload(Environment.project))
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
                elif field == 'project_id':
                    result['project_id'] = environment.project_id
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
                elif field == 'project_name':
                    result['project_name'] = environment.project.name if environment.project else None
                elif field == 'project_path':
                    result['project_path'] = str(environment.project.path) if environment.project else None
                elif field == 'project_description':
                    result['project_description'] = environment.project.description if environment.project else None
                elif field == 'tags':
                    result['tags'] = [tag.name for tag in environment.tags] if hasattr(environment, 'tags') else []
                elif field == 'runs_count':
                    result['runs_count'] = len(environment.runs) if hasattr(environment, 'runs') else 0
                else:
                    log.warning(f'Unknown field requested: {field}. Available: id, name, description, sha256hash, file, vm_id, project_id, installations, vm_name, vm_os_type, project_name, project_path, tags, runs_count')
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
            elif field == 'project_id':
                result['project_id'] = environment.project_id
            elif field == 'installations':
                result['installations'] = environment.installations
            else:
                log.warning(f'Unknown field requested: {field}. Available: id, name, description, sha256hash, file, vm_id, project_id, installations')
        
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
    return get_environment_by_ulid(ulid, fields=['id', 'name', 'description', 'sha256hash', 'file', 'vm_id', 'vm_name', 'vm_os_type', 'project_id', 'project_name', 'project_path'])


def get_environment_summary(ulid: str) -> dict | None:
    """Get basic environment info with key relationships - lighter version."""
    return get_environment_by_ulid(ulid, fields=['id', 'name', 'description', 'vm_name', 'project_name'])


def get_environment_with_vm_details(ulid: str) -> dict | None:
    """Get environment with comprehensive VM information."""
    return get_environment_by_ulid(ulid, fields=['id', 'name', 'vm_name', 'vm_os_type', 'vm_file_path', 'vm_description', 'vm_architecture'])


def get_environment_with_relationships(ulid: str) -> dict | None:
    """Get environment with all relationships loaded."""
    return get_environment_by_ulid(ulid, fields=['id', 'name', 'description', 'vm_name', 'vm_os_type', 'project_name', 'project_path', 'tags', 'runs_count'])


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

