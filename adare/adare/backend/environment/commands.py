# external imports
from pathlib import Path
import shutil
import cattrs
import jinja2

# internal imports
from adare.backend.environment.database import EnvironmentDatabase
from adare.backend.attrs_classes import EnvironmentConfiguration
from adare.backend.project.directory import ProjectDirectory
from adarelib.helperfunctions.yaml import yaml_to_dict
from adarelib.helperfunctions.hash import hash_file_sha256
from adare.config.configdirectory import TEMPLATES_DIR


# configure logging
import logging
log = logging.getLogger(__name__)


def _load_environment_from_file(environment_file: Path) -> EnvironmentConfiguration|None:
    environment_dict = yaml_to_dict(environment_file)
    try:
        environment = cattrs.structure(environment_dict, EnvironmentConfiguration)
    except cattrs.BaseValidationError as e:
        log.error(f'environment file {environment_file} could not be loaded')
        log.error(e, exc_info=True)
        return None
    return environment


def environment_load(project: Path, environment: str, force: bool = False):
    project_directory = ProjectDirectory(project)
    environment_database = EnvironmentDatabase(project)

    environment_file = project_directory.environments / f'{environment}.yml'
    if not environment_file.exists():
        environment_file = project_directory.environments / f'{environment}.yaml'
        if not environment_file.exists():
            log.error(f'environment file {environment_file} does not exist')
            exit(1)

    environment_file_sha256 = hash_file_sha256(environment_file)
    environment_configuration: EnvironmentConfiguration = _load_environment_from_file(environment_file)

    if not environment_configuration:
        log.error(f'environment file {environment_file} could not be loaded')
        exit(1)

    environment_database.update_environment(environment_configuration, environment_file, environment_file_sha256, force=force)
    log.info(f'environment file {environment_file} loaded')


def environment_create(project: Path, environment: str):
    project_directory = ProjectDirectory(project)
    environment_file = project_directory.environments / f'{environment}.yml'
    environment_file2 = project_directory.environments / f'{environment}.yaml'
    if environment_file.is_file() or environment_file2.is_file():
        log.error(f'environment file {environment_file} already exists')
        exit(1)

    environment_file_template = TEMPLATES_DIR / 'environment.yml'
    if not environment_file_template.is_file():
        log.error(f'environment file template {environment_file_template} does not exist')
        exit(1)

    environment_file_template_content = environment_file_template.read_text()
    environment_file_content = jinja2.Template(environment_file_template_content).render(environment=environment)
    environment_file.write_text(environment_file_content)

    environment_file_sha256 = hash_file_sha256(environment_file)
    environment_configuration: EnvironmentConfiguration = _load_environment_from_file(environment_file)

    if not environment_configuration:
        log.error(f'environment file {environment_file} could not be loaded')
        exit(1)

    environment_database = EnvironmentDatabase(project)
    environment_database.update_environment(environment_configuration, environment_file, environment_file_sha256)
    log.info(f'environment file {environment_file} created')
