# internal imports
from .configdirectory import APPDATA_DIR, STATE_DIR
from .exceptions import ConfigDirectoryError
from pathlib import Path

# configure logging
import logging
log = logging.getLogger(__name__)


def get_database_location():
    """Legacy function - returns global database location for backward compatibility."""
    return get_global_database_location()


def get_global_database_location():
    """Get the location of the global database containing VMs, environments, test functions, and project metadata."""
    if not APPDATA_DIR.is_dir():
        raise ConfigDirectoryError('the config directory could not be set')

    # Ensure state directory exists
    STATE_DIR.mkdir(exist_ok=True, parents=True)

    return STATE_DIR / 'global.db.sqlite3'


def get_project_database_location(project_path: Path):
    """Get the location of the project database for a specific project."""
    if not isinstance(project_path, Path):
        project_path = Path(project_path)

    project_db_dir = project_path / '.adare'
    project_db_dir.mkdir(exist_ok=True, parents=True)

    return project_db_dir / 'project.db.sqlite3'


DB_STATUS_LIST = [
    'in progress',
    'success',
    'failed',
    'warning',
    'not reached',
]

DB_PUBLISH_STATUS_LIST = [
    'unknown',
    'published',
    'in request',
    'not published'
]
