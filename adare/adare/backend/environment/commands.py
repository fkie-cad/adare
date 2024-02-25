# external imports
from pathlib import Path
import jinja2
import pandas as pd

# internal imports
import adare.backend.environment.database as environment_database
from adarelib.types import EnvironmentMetadata
from adare.backend.project.directory import ProjectDirectory
from adarelib.helperfunctions.hash import hash_file_sha256
from adare.config.configdirectory import TEMPLATES_DIR
from adarelib.helperfunctions.cli import print_df
from adarelib.parsers import parse_environment_file


# configure logging
import logging
log = logging.getLogger(__name__)



def environment_load(project: Path, environment: str, force: bool = False):
    project_directory = ProjectDirectory(project)

    environment_file = project_directory.environments / f'{environment}.yml'
    if not environment_file.exists():
        environment_file = project_directory.environments / f'{environment}.yaml'
        if not environment_file.exists():
            log.error(f'environment file {environment_file} does not exist')
            exit(1)

    environment_file_sha256 = hash_file_sha256(environment_file)
    environment_configuration: EnvironmentMetadata = parse_environment_file(environment_file)

    if not environment_configuration:
        log.error(f'environment file {environment_file} could not be loaded')
        exit(1)

    environment_database.update_environment(project, environment_configuration, environment_file, environment_file_sha256, force=force)
    log.info(f'environment file {environment_file} loaded')


def environment_create(project: Path, environment: str):
    project_directory = ProjectDirectory(project)
    environment_file = project_directory.environments / f'{environment}.yml'
    environment_file2 = project_directory.environments / f'{environment}.yaml'
    if environment_file.is_file() or environment_file2.is_file():
        log.error(f'environment file {environment_file} already exists')
        exit(1)

    environment_file_template = TEMPLATES_DIR / 'environment' / 'environment.yml'
    if not environment_file_template.is_file():
        log.error(f'environment file template {environment_file_template} does not exist')
        exit(1)

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
