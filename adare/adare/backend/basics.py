# external imports
from pathlib import Path

# internal imports
from adare.database.api.project import ProjectManagementApi

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


def determine_projectdirectory(project_name: str = None) -> Path or None:
    """
    determine the directory of the project

    :param project_name: name of the project

    :return: project path: a valid project path
    """
    if project_name:
        with ProjectManagementApi() as db:
            project = db.get_project(project_name)
            if not project:
                log.warning(f"provided {project_name} does not exist -> try cwd instead")
            else:
                project_directory = Path(project.path)
                return project_directory
    if not project_name:
        project_directory = Path.cwd()
        if __check_project_directory(project_directory):
            return project_directory

    return None