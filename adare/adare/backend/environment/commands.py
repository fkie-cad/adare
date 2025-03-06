# external imports
from pathlib import Path
import jinja2
import pandas as pd

# internal imports
import adare.backend.environment.database as environment_database
from adarelib.types.backend import EnvironmentMetadata
from adare.backend.project.directory import ProjectDirectory
from adarelib.helperfunctions.hash import hash_file_sha256
from adare.config.configdirectory import TEMPLATES_DIR
from adarelib.parsers import parse_environment_file
from adarelib.exceptions import TemplateMissingError
from adare.backend.environment.exceptions import EnvironmentLoadFailed, EnvironmentFileAlreadyExists, \
    EnvironmentDoesNotExistInDatabase, ExampleEnvironmentDoesNotExist
from adare.webappaccess.download import download_environment, sync
from adare.webappaccess.login import is_logged_in
from adarelib.exceptions import NotLoggedInError

# configure logging
import logging
log = logging.getLogger(__name__)


def environment_sync(environment_ulid: str):
    if not is_logged_in():
        log.info(f'sync not possible because user is not logged in')
        return
    # get environment from database
    sha256 = environment_database.get_environment_hash(environment_ulid)
    # download environment from webapp
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

    environment_file = project_directory.environments / f'{environment}.yml'
    if not environment_file.exists():
        environment_file = project_directory.environments / f'{environment}.yaml'
        if not environment_file.exists():
            raise EnvironmentLoadFailed(
                log,
                f'environment file {environment_file} does not exist',
                possible_solutions=[
                    'Did you create the environment file?',
                    'If not, try to create the environment file via [i]adare env create[/i].',
                ]
            )

    environment_file_sha256 = hash_file_sha256(environment_file)
    environment_configuration: EnvironmentMetadata = parse_environment_file(environment_file)

    # check if file name equals environment name
    if environment != environment_configuration.name:
        raise EnvironmentLoadFailed(
            log,
            f'environment name in file {environment_configuration.name} does not match the file name {environment}',
            possible_solutions=[
                'rename the file or change the environment name in the file and try again',
            ]
        )

    environment_ulid = environment_database.update_environment(project, environment_configuration, environment_file, environment_file_sha256, force=force)
    if not environment_ulid:
        log.error(f'environment update failed')
        return
    environment_sync(environment_ulid)
    log.info(f'environment file {environment_file} loaded')


def environment_create(project: Path, environment: str):
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

    environment_file_template_content = environment_file_template.read_text()
    environment_file_content = jinja2.Template(environment_file_template_content).render(environment=environment)
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



#
# def environment_list(project: Path):
#
#     environments = environment_database.get_environments(project)
#
#     columns = ['name', 'description', 'experiments']
#     env_data = []
#     if environments:
#         env_data.extend(
#             [
#                 env.get('name'),
#                 env.get('description'),
#                 "\n".join(
#                     [
#                         f"{exp.get('name')} ({exp.get('runs')} runs)"
#                         for exp in env.get('experiments')
#                     ]),
#             ]
#             for env in environments
#         )
#     df_env = pd.DataFrame(env_data, columns=columns)
#
#     title = f'Environments (project {project})' if project else 'Environments'
#     print_df(df_env, title)
