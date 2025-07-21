# external imports
from pathlib import Path
import jinja2
import pandas as pd

# internal imports
import adare.backend.environment.database as environment_database
from adare.types.environment import EnvironmentMetadata, parse_environment_file
from adare.backend.project.directory import ProjectDirectory
from adare.helperfunctions.hash import hash_file_sha256
from adare.config.configdirectory import TEMPLATES_DIR
from adare.exceptions import TemplateMissingError
from adare.backend.environment.exceptions import EnvironmentLoadFailed, EnvironmentFileAlreadyExists, \
    EnvironmentDoesNotExistInDatabase, ExampleEnvironmentDoesNotExist
from adare.webappaccess.download import download_environment, sync
from adare.webappaccess.login import is_logged_in
from adare.exceptions import NotLoggedInError

# configure logging
import logging
log = logging.getLogger(__name__)


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


def environment_load(project: Path, environment: str, force: bool = False):
    project_directory = ProjectDirectory(project)

    for ext in ('.yml', '.yaml'):
        environment_file = project_directory.environments / f'{environment}{ext}'
        if environment_file.exists():
            break
    else:
        raise EnvironmentLoadFailed(
            log,
            f'environment file {project_directory.environments / f"{environment}.yml"} or .yaml does not exist',
            possible_solutions=[
                'Did you create the environment file?',
                'If not, try to create the environment file via [i]adare env create[/i].',
            ]
        )

    environment_file_sha256 = hash_file_sha256(environment_file)

    # checks if environment with same hash already exists in the database
    existing_environment_id = environment_database.get_environment_by_hash(environment_file_sha256, trigger_exception=False)
    if existing_environment_id:
        if not force:
            log.info(f'Environment with hash {environment_file_sha256} already exists in database')
            return existing_environment_id
        else:
            log.info(f'Environment with hash {environment_file_sha256} exists, but force=True, so updating')

    if not existing_environment_id:
        log.info(f'Environment with hash {environment_file_sha256} not found, creating new one')
    
    environment_metadata: EnvironmentMetadata = parse_environment_file(environment_file)

    # todo: maybe add validation for environment configuration semantic 

    # check if file name equals environment name
    if environment != environment_metadata.name:
        raise EnvironmentLoadFailed(
            log,
            f'environment name in file {environment_metadata.name} does not match the file name {environment}',
            possible_solutions=[
                'rename the file or change the environment name in the file and try again',
            ]
        )

    # check if vm is available for environment
    from adare.backend.vm.commands import ensure_vm_available_for_environment
    vm_id = ensure_vm_available_for_environment(
        project_path=project,
        environment_metadata=environment_metadata,
    )

    environment_ulid = environment_database.update_environment(project, environment_metadata, environment_file, environment_file_sha256, vm_id, force=force)
    if not environment_ulid:
        log.error(f'environment update failed')
        return
    
    environment_sync(environment_ulid)
    log.info(f'environment file {environment_file} loaded')


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


def environment_example(project: Path, environment: str):
    from adare.config.configdirectory import EXAMPLES_DIR
    import shutil

    project_directory = ProjectDirectory(project)

    environment_file_src = EXAMPLES_DIR / 'environments' / f'{environment}.yml'

    if not environment_file_src.exists():
        raise ExampleEnvironmentDoesNotExist(
            log,
            f'example environment file {environment_file_src} does not exist',
            possible_solutions=[]
        )
    environment_file_dst = project_directory.environments
    shutil.copy(environment_file_src, environment_file_dst)



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
    