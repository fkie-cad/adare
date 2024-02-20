# external imports
from pathlib import Path
import shutil

# internal imports
from adare.backend.project.database import ProjectDatabase
from adare.backend.project.directory import ProjectDirectory


# configure logging
import logging
log = logging.getLogger(__name__)


def project_create(path: Path, name: str, description: str = ''):
    project_db = ProjectDatabase(path)
    project_directory = ProjectDirectory(path)
    
    if not project_directory.create():
        exit(-1)

    if not project_db.add(name, description):
        project_directory.remove()
        log.info(f'project directory {path} removed, since project could not be added to database')
        exit(-1)

    if not project_directory.copy_adare_to_adare_dir():
        project_directory.remove()
        project_db.remove()
        log.info(f'project directory {path} removed, since adare could not be copied to adare directory')
        exit(-1)

    if not project_directory.copy_standard_testfunction():
        project_directory.remove()
        project_db.remove()
        log.info(f'project directory {path} removed, since standard testfunction could not be copied')
        exit(-1)

    log.info(f'project in path {path} created')


def project_remove(path: Path):
    project_db = ProjectDatabase(path)
    if not project_db.get():
        log.error(f'project in path {path} does not exist in database')
        exit(-1)

    if not path.exists():
        log.error(f'project in path {path} does not exist')
        exit(-1)

    try:
        shutil.rmtree(path)
        log.info(f'project in path {path} removed')
    except FileNotFoundError or OSError as e:
        log.error(e, exc_info=True)
        log.error(f'project ({path}) removal failed')
        exit(-1)

    project_db.remove()


def project_add_tessdata(path: Path, abbreviation: str):
    project_db = ProjectDatabase(path)
    project = project_db.get()

    if not project:
        log.error(f'project in path {path} does not exist in database')
        exit(-1)

    project_directory = ProjectDirectory(path)
    if not project_directory.exists():
        log.error(f'project directory {path} does not exist')
        exit(-1)

    project_directory.download_tessdata(abbreviation)
