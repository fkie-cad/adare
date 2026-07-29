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


def determine_projectdirectory(project: str, silent: bool = False) -> Path | None:
    """Resolve ``-p/--project`` to a project directory, or fall back to the cwd.

    Accepts a project **name or path**, which is what ``--project``'s help text
    promises and what the "Use full path: 'adare -p /path/to/project'" hint in the
    not-found error tells users to try. Only the name lookup was implemented, so a
    path — even the exact one `adare project list` prints — failed with
    "does not exist in database".
    """
    from adare.database.api.project import ProjectDbApi
    if project:
        with ProjectDbApi() as db:
            # Quiet on the name miss when a path attempt still follows, so a
            # successful path resolution does not log an error on the way.
            path_shaped = _looks_like_path(project)
            record = db.get_project(project, silent=path_shaped)
            if not record and path_shaped:
                record = db.get_project_by_path(Path(project).expanduser(), silent=True)
            if record:
                project_directory = Path(record.path)
                if __check_project_directory(project_directory):
                    return project_directory
                # Registered but its directory is gone: unchanged behaviour — fall
                # through to the cwd lookup below.
            else:
                log.error(f"project {project} does not exist in database")
                return None

    project_directory = Path.cwd()
    with ProjectDbApi() as db:
        if db.get_project_by_path(project_directory, silent=silent):
            return project_directory
    return None


def _looks_like_path(value: str) -> bool:
    """True when *value* is meant as a filesystem path rather than a project name.

    A separator or a leading ``~`` is the signal. Project names are bare words, so
    this never turns a name into a stray path lookup.
    """
    return '/' in value or value.startswith('~')


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
