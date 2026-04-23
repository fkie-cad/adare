# external imports
# configure logging
import logging
from pathlib import Path

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


def determine_projectdirectory(project_name: str, silent: bool = False) -> Path | None:
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
        if db.get_project_by_path(project_directory, silent=silent):
            return project_directory
    return None


def determine_projectdirectory_for_removal(project_name: str) -> Path | None:
    """
    determine project directory for removal operations - skips directory existence check

    :param project_name: name of the project
    :return: project directory path or None if not found in database
    """
    from adare.database.api.project import ProjectDbApi
    if project_name:
        with ProjectDbApi() as db:
            if project := db.get_project(project_name):
                return Path(project.path)
            log.error(f"project {project_name} does not exist in database")
            return None

    # For removal, we still check current directory exists since it's being passed implicitly
    project_directory = Path.cwd()
    with ProjectDbApi() as db:
        if db.get_project_by_path(project_directory, silent=False):
            return project_directory
    return None
