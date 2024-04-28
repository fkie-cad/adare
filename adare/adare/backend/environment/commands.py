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
from adarelib.helperfunctions.cli import print_df
from adarelib.parsers import parse_environment_file
from adarelib.exceptions import TemplateMissingError
from adare.backend.environment.exceptions import EnvironmentLoadFailed, EnvironmentFileAlreadyExists


# configure logging
import logging
log = logging.getLogger(__name__)


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

    environment_database.update_environment(project, environment_configuration, environment_file, environment_file_sha256, force=force)
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


def environment_delete(environment_uuid: str, force: bool = False):
    environment_database.delete_environment(environment_uuid, force=force)
    log.info('environment deleted')


def environment_list(project: Path):

    environments = environment_database.get_environments(project)

    columns = ['name', 'description', 'experiments']
    env_data = []
    if environments:
        env_data.extend(
            [
                env.get('name'),
                env.get('description'),
                "\n".join(
                    [
                        f"{exp.get('name')} ({exp.get('runs')} runs)"
                        for exp in env.get('experiments')
                    ]),
            ]
            for env in environments
        )
    df_env = pd.DataFrame(env_data, columns=columns)

    title = f'Environments (project {project})' if project else 'Environments'
    print_df(df_env, title)
