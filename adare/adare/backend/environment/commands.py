# external imports
from pathlib import Path
import jinja2
import pandas as pd

# internal imports
import adare.backend.environment.database as environment_database
from adare.types.environment import EnvironmentMetadata, parse_environment_file
from adare.backend.project.directory import ProjectDirectory
from adare.helperfunctions.hash import hash_file_sha256
from adare.helperfunctions.file.hash import file_sha256_with_progress
from adare.config.configdirectory import TEMPLATES_DIR, ENVIRONMENTS_DIR, VMS_DIR
from adare.exceptions import TemplateMissingError
from adare.backend.environment.exceptions import EnvironmentLoadFailed, EnvironmentFileAlreadyExists, \
    EnvironmentDoesNotExistInDatabase
from adare.webappaccess.download import download_environment, sync
from adare.webappaccess.login import is_logged_in
from adare.exceptions import NotLoggedInError
from adare.helperfunctions.web.download import download
from urllib.parse import urlparse
import hashlib
from adare.console import print_success_message

# configure logging
import logging
log = logging.getLogger(__name__)


def _copy_environment_file(source_path: Path, environment_name: str, file_hash: str) -> Path:
    """
    Copy environment file to managed storage location.

    Args:
        source_path: Original environment file path
        environment_name: Environment name
        file_hash: SHA256 hash of the environment file (first 8 chars used in filename)

    Returns:
        Path to copied environment file in managed storage

    Raises:
        EnvironmentLoadFailed: If file copying fails
    """
    try:
        # Ensure global environments directory exists
        ENVIRONMENTS_DIR.mkdir(parents=True, exist_ok=True)

        # Generate target filename with environment name and hash prefix for uniqueness
        hash_prefix = file_hash[:8]
        target_filename = f"{environment_name}_{hash_prefix}{source_path.suffix}"
        target_path = ENVIRONMENTS_DIR / target_filename

        # Check if target already exists
        if target_path.exists():
            if target_path.samefile(source_path):
                # Source and target are the same file, no need to copy
                log.info(f"Environment file already in managed storage: {target_path}")
                return target_path
            else:
                # File exists but is different - this is fine, we'll overwrite with the new version
                log.info(f"Updating environment file in managed storage: {target_path}")

        log.info(f"Copying environment file to managed storage: {target_path}")

        # Simple file copy for YAML files (small, no progress bar needed)
        import shutil
        shutil.copy2(source_path, target_path)

        log.info(f"Successfully copied environment file to {target_path}")
        return target_path

    except OSError as e:
        raise EnvironmentLoadFailed(
            log,
            f"Failed to copy environment file to managed storage: {e}",
            possible_solutions=[
                'Check file system permissions',
                'Ensure sufficient disk space',
                'Verify the source file is accessible'
            ]
        )


def resolve_vm_from_url(url: str) -> Path:
    """
    Download and cache an OVA file from URL using the global vm directory.

    Args:
        url: URL to the OVA file

    Returns:
        Path to the downloaded/cached OVA file

    Raises:
        EnvironmentLoadFailed: If download fails
    """
    # Use global VM directory
    vm_dir = VMS_DIR

    # Ensure global VM directory exists
    vm_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate filename from URL
    parsed_url = urlparse(url)
    original_filename = Path(parsed_url.path).name
    
    # Create hash-based filename to avoid conflicts and enable caching
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
    
    if original_filename and original_filename.lower().endswith(('.ova', '.ovf')):
        filename = f"{url_hash}_{original_filename}"
    else:
        filename = f"{url_hash}_downloaded.ova"
    
    cached_file_path = vm_dir / filename
    
    # Check if already cached
    if cached_file_path.exists() and cached_file_path.stat().st_size > 0:
        log.info(f"Using cached VM file: {cached_file_path}")
        return cached_file_path
    
    # Download the file
    try:
        log.info(f"Downloading VM from URL: {url}")
        download(url, cached_file_path, quiet=False)
        
        if not cached_file_path.exists() or cached_file_path.stat().st_size == 0:
            raise EnvironmentLoadFailed(
                log,
                f'Downloaded VM file {cached_file_path} is empty or missing',
                possible_solutions=['Check if the URL is valid', 'Check network connectivity']
            )
        
        log.info(f"Successfully downloaded VM to: {cached_file_path}")
        return cached_file_path
        
    except Exception as e:
        # Clean up failed download
        if cached_file_path.exists():
            cached_file_path.unlink()
            
        raise EnvironmentLoadFailed(
            log,
            f'Failed to download VM from URL {url}: {e}',
            possible_solutions=[
                'Check if the URL is accessible',
                'Check network connectivity', 
                'Ensure the URL points to a valid OVA/OVF file'
            ]
        ) from e


def environment_sync(environment_ulid: str):
    if not is_logged_in():
        log.info(f'sync not possible because user is not logged in')
        return
    # get environment from database
    sha256 = environment_database.get_environment_hash(environment_ulid)
    # download environment from webappclea
    metadata_remote = sync(sha256, 'environment')
    if not metadata_remote:
        log.info(f'environment {environment_ulid} does not exist remotely')
        return
    is_published = metadata_remote.get('published')
    remote_url = metadata_remote.get('gitea_url')
    remote_ulid = metadata_remote.get('ulid')
    environment_database.sync_environment(environment_ulid, remote_ulid, remote_url, is_published)
    log.info(f'environment {environment_ulid} synced')


def environment_load(environment: str, force: bool = False, no_copy: bool = False):
    """
    Load environment from YAML file.

    Args:
        environment: Environment name or path
        force: Force reload even if already exists
        no_copy: Keep VM file at original location (local files only)
    """
    import time
    start_time = time.time()

    # Ensure global environments directory exists
    ENVIRONMENTS_DIR.mkdir(parents=True, exist_ok=True)

    # Check if environment is a full path (external file) or just a name
    if environment.startswith('/') or Path(environment).suffix in ['.yml', '.yaml']:
        # It's a full path to an external file
        environment_file = Path(environment)
        if not environment_file.exists():
            raise EnvironmentLoadFailed(
                log,
                f'environment file {environment_file} does not exist'
            )
    else:
        # It's a name, look in global environments directory
        for ext in ('.yml', '.yaml'):
            environment_file = ENVIRONMENTS_DIR / f'{environment}{ext}'
            if environment_file.exists():
                break
        else:
            raise EnvironmentLoadFailed(
                log,
                f'environment file {ENVIRONMENTS_DIR / f"{environment}.yml"} or .yaml does not exist',
                possible_solutions=[
                    'Did you create the environment file?',
                    'If not, try to create the environment file via [i]adare env create[/i].',
                    f'Check if the environment file exists in {ENVIRONMENTS_DIR}',
                ]
            )

    # CLAUDE: Calculate environment file hash with progress bar for better UX
    log.info(f'Calculating environment file hash...')
    environment_file_sha256 = file_sha256_with_progress(
        environment_file,
        description=f"Hashing environment file {environment_file.name}",
        silent=False
    )
    log.info(f'Environment file hash: {environment_file_sha256}')

    # Parse environment metadata to get the name
    environment_metadata: EnvironmentMetadata = parse_environment_file(environment_file)
    # Override environment name with filename without extension (ignore name in file)
    environment_name = environment_file.stem

    # Copy environment file to managed storage BEFORE checking if it exists
    # This ensures the file is always in a safe location under our control
    log.info(f'Copying environment file to managed storage...')
    managed_environment_file = _copy_environment_file(environment_file, environment_name, environment_file_sha256)
    log.info(f'Environment file stored at: {managed_environment_file}')

    # CLAUDE: Early check - if environment already exists by hash, skip VM processing entirely
    existing_environment_id = environment_database.get_environment_by_hash(environment_file_sha256, trigger_exception=False)
    if existing_environment_id:
        if not force:
            elapsed_time = time.time() - start_time
            log.info(f'Environment with hash {environment_file_sha256} already exists in database - skipping all VM processing!')
            log.info(f'Optimization: No file copying or VM processing needed!')
            log.info(f'Total time: {elapsed_time:.1f} seconds (vs potentially minutes for full VM processing)')
            return existing_environment_id
        else:
            log.info(f'Environment with hash {environment_file_sha256} exists, but force=True, so updating')

    if not existing_environment_id:
        log.info(f'Environment with hash {environment_file_sha256} not found, creating new one')

    # Override environment name with filename without extension (ignore name in file)
    environment_metadata.name = environment_name

    # todo: maybe add validation for environment configuration semantic

    # Handle VM file copying and hashing during environment load (heavy file operations)
    vm_id = None
    created_vm_id = None  # Track newly created VM for cleanup on failure
    vm_path = None  # Track VM path for success message
    is_url = False  # Track if VM was loaded from URL

    try:
        if environment_metadata.vm:
            # Determine how to handle the VM specification
            is_url = False
        
            if environment_metadata.vm_type == "auto":
                # Auto-detect URL vs local path
                is_url = environment_metadata.vm.startswith(('http://', 'https://'))
            elif environment_metadata.vm_type == "url":
                # Force treat as URL (even if it doesn't start with http)
                is_url = True
            elif environment_metadata.vm_type == "path":
                # Force treat as local path
                is_url = False
        
            if is_url:
                # Download VM from URL and cache in global vm directory
                # NOTE: URLs ALWAYS download to managed storage, ignoring --no-copy
                log.info(f'Processing URL-based VM: {environment_metadata.vm}')
                if no_copy:
                    log.info(f'Note: --no-copy flag is ignored for URL-based VMs (always downloaded to managed storage)')
                try:
                    vm_path = resolve_vm_from_url(environment_metadata.vm)
                    log.info(f'VM downloaded from URL and cached: {vm_path}')
                except Exception as e:
                    log.error(f'Failed to download VM from URL {environment_metadata.vm}: {e}')
                    raise
            else:
                # Handle local file path - support both relative and absolute paths
                vm_path = Path(environment_metadata.vm)
                if not vm_path.is_absolute():
                    # Try relative to environment file first
                    vm_path = environment_file.parent / environment_metadata.vm

                if not vm_path.exists():
                    raise EnvironmentLoadFailed(
                        log,
                        f'VM file not found: {vm_path}',
                        possible_solutions=[
                            'Check if the VM file path is correct',
                            'Use absolute path for VM file',
                            'Ensure VM file exists in the specified location'
                        ]
                    )
        
            if vm_path.exists():
                from adare.backend.vm.commands import load_vm_file_for_environment
                log.info(f'Processing VM file during environment load: {vm_path}')

                # CLAUDE: Removed duplicate hash calculation - let load_vm_file_for_environment handle it
                import adare.backend.vm.database as vm_database

                # Call load_vm_file_for_environment which handles hash calculation and duplicate checking
                vm_result = load_vm_file_for_environment(
                    project_path=None,  # VMs are now global, no specific project
                    vm_path=vm_path,
                    environment_metadata=environment_metadata,
                    no_copy=no_copy if not is_url else False  # Pass the flag (but never for URLs)
                )

                # Handle both old return format (vm_id) and new return format (dict with vm_id and was_existing)
                if isinstance(vm_result, dict):
                    vm_id = vm_result['vm_id']
                    was_existing = vm_result['was_existing']
                    # If VM didn't exist before, mark it for potential cleanup
                    if not was_existing:
                        created_vm_id = vm_id
                else:
                    # Legacy return format (just vm_id)
                    vm_id = vm_result
                    # Check if this was an existing VM for cleanup purposes
                    existing_vm = vm_database.get_vm_by_id(vm_id)
                    if existing_vm and existing_vm.created_at:
                        # This is a heuristic - if VM was created very recently, it's probably new
                        import datetime
                        now = datetime.datetime.utcnow()
                        creation_time = existing_vm.created_at
                        if isinstance(creation_time, str):
                            creation_time = datetime.datetime.fromisoformat(creation_time.replace('Z', '+00:00'))
                        time_diff = (now - creation_time).total_seconds()
                        if time_diff < 60:  # Created within last minute
                            created_vm_id = vm_id

                log.info(f'VM file processed and stored in database with ID: {vm_id}')
            else:
                raise EnvironmentLoadFailed(
                    log,
                    f'VM file specified but not found: {vm_path}',
                    possible_solutions=[
                        'Check if the VM file path is correct',
                        'Ensure the VM file exists at the specified location',
                        'If using a URL, check if the download completed successfully',
                        'Check file permissions and accessibility'
                    ]
                )

        # Try to create environment - if this fails, cleanup VM if we created it
        # Use the managed file path (in .adare/environments/) instead of the original user file
        environment_ulid = environment_database.update_environment(None, environment_metadata, managed_environment_file, environment_file_sha256, vm_id=vm_id, force=force)
        if not environment_ulid:
            log.error(f'environment update failed')
            raise EnvironmentLoadFailed(log, 'Failed to create environment in database')

    except Exception as e:
        # If environment creation failed and we created a new VM, clean it up
        if created_vm_id:
            log.warning(f'Environment creation failed, cleaning up newly created VM {created_vm_id}')
            try:
                import adare.backend.vm.database as vm_database
                vm_database.delete_vm(created_vm_id)
                log.info(f'Successfully cleaned up VM {created_vm_id}')
            except Exception as cleanup_error:
                log.error(f'Failed to cleanup VM {created_vm_id}: {cleanup_error}')

        # Re-raise the original exception
        raise e
    
    environment_sync(environment_ulid)

    # Protect environment file after loading (protect the managed copy, not the original)
    from adare.helperfunctions.integrity import protect_loaded_files
    protected_files = protect_loaded_files([managed_environment_file])
    log.info(f'Protected {len(protected_files)} environment files')
    
    log.info(f'environment file {environment_file} loaded and copied to managed storage')

    # Generate next steps based on environment configuration
    next_steps = [
        f'Run experiments in this environment with: adare experiment run <experiment> -e {environment_name}',
        f'List available environments with: adare environment list',
        f'View environment details with: adare environment show {environment_name}'
    ]

    # Add VM-specific info if VM was processed
    if vm_id:
        next_steps.insert(1, f'VM successfully configured and ready for use')

    # Create tip based on environment features
    tip = f'Environment "{environment_name}" is now ready for experiments'
    if environment_metadata.vm:
        tip += f' with VM "{environment_metadata.vm}"'
    if hasattr(environment_metadata, 'description') and environment_metadata.description:
        tip += f' - {environment_metadata.description}'

    # Add note about file being copied to managed storage OR external reference
    if no_copy and not is_url and vm_path:
        tip += f'\n\nNote: VM file is referenced at original location: {vm_path}'
        tip += f'\n[bold red]IMPORTANT: Do not move or delete this file![/bold red]'
        tip += f'\n\nOriginal file: {environment_file}\nManaged copy: {managed_environment_file}'
    else:
        tip += f'\n\nOriginal file: {environment_file}\nManaged copy: {managed_environment_file}'

    print_success_message(
        title=f'Environment "{environment_name}" loaded successfully!',
        location=str(managed_environment_file),
        next_steps=next_steps,
        tip=tip
    )


def environment_create(project: Path, environment: str, vm_path: Path = None):
    project_directory = ProjectDirectory(project)
    environment_file = project_directory.environments / f'{environment}.yml'
    environment_file2 = project_directory.environments / f'{environment}.yaml'
    if environment_file.is_file() or environment_file2.is_file():
        raise EnvironmentFileAlreadyExists(
            log,
            f'environment file {environment_file} already exists',
            possible_solutions=[
                'Did you want to update the environment?',
                'If yes, try to update the environment via [i]adare env load[/i].',
                'If not, try to create the environment with a different name.',
            ]
        )

    environment_file_template = TEMPLATES_DIR / 'environment' / 'environment.yml'
    if not environment_file_template.is_file():
        raise TemplateMissingError(
            log,
            f'environment file template [i]{environment_file_template}[/i] does not exist',
            possible_solutions=[
                'Did the installation was done via make install?',
                'If not, try to reinstall adare via make install.',
                'If the problem persists, please open an issue on GitHub.'
            ]
        )

    # Prepare template variables
    template_vars = {'environment': environment}
    
    # Handle VM loading if --with-vm was provided
    if vm_path:
        from adare.database.api.vm import load_vm_from_file
        from adare.database.api.project import ProjectDbApi
        from rich import print as rprint
        
        # Get project ID for VM loading
        project_id = None
        if project:
            project_api = ProjectDbApi()
            project_obj = project_api.get_project_by_directory(project)
            if project_obj:
                project_id = project_obj.id
        
        # Load VM into database
        vm_name = vm_path.stem
        rprint(f"[blue]Loading VM into database: {vm_name}[/blue]")
        
        try:
            scope = 'project' if project_id else 'global'
            load_vm_from_file(
                project_path=project,
                file_path=vm_path,
                name=vm_name,
                description=f'Loaded via environment create --with-vm',
                scope=scope,
                project_id=project_id,
                silent=False
            )
            rprint(f"[green]VM loaded successfully: {vm_name}[/green]")
            
            # Use the VM name in the template instead of placeholder
            template_vars['vm_name'] = vm_name
            
        except Exception as e:
            log.error(f'Failed to load VM {vm_name}: {e}')
            rprint(f"[red]Failed to load VM {vm_name}: {e}[/red]")
            # Continue with placeholder if VM loading fails
            template_vars['vm_name'] = None
    else:
        template_vars['vm_name'] = None
    
    environment_file_template_content = environment_file_template.read_text()
    environment_file_content = jinja2.Template(environment_file_template_content).render(**template_vars)
    environment_file.write_text(environment_file_content)
    log.info(f'environment file {environment_file} created')





def environment_delete(environment_ulid: str, force: bool = False):
    environment_database.delete_environment(environment_ulid, force=force)
    log.info('environment deleted')


def environment_download(project: Path, environment_name: str):
    if not is_logged_in():
        raise NotLoggedInError(log)
    # check if environment exists in database
    try:
        env = environment_database.get_environment_path_by_project_and_name(project, environment_name)
        raise EnvironmentFileAlreadyExists(
            log,
            f'environment file {env} already exists',
        )
    except EnvironmentDoesNotExistInDatabase:
        pass

    # download environment from webapp
    project_directory = ProjectDirectory(project)
    download_environment(environment_name, Path(f'{project_directory.environments}/{environment_name}.yml'))
    print(f'environment {environment_name} downloaded successfully')
    log.info(f'environment {environment_name} downloaded')
    