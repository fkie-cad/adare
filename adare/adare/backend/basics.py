# external imports
from pathlib import Path

# configure logging
import logging
log = logging.getLogger(__name__)


def __check_project_directory(project_directory: Path) -> bool:
    """
    check if the provided project directory is valid

    :param project_directory:
    :return:
    """
    if not project_directory.exists():
        log.error(f"provided project directory {project_directory} does not exist")
        return False
    if not project_directory.is_dir():
        log.error(f"provided project directory {project_directory} is not a directory")
        return False
    return True


def determine_projectdirectory(project_name: str) -> Path or None:
    from adare.database.api.project import ProjectDbApi
    if project_name:
        with ProjectDbApi() as db:
            if project := db.get_project(project_name):
                project_directory = Path(project.path)
                if __check_project_directory(project_directory):
                    return project_directory
            else:
                log.error(f"project {project_name} does not exist in database")
                return None

    project_directory = Path.cwd()
    with ProjectDbApi() as db:
        if db.get_project_by_path(project_directory):
            return project_directory
    return None
