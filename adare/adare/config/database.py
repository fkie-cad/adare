# internal imports
from .configdirectory import APPDATA_DIR
from .exceptions import ConfigDirectoryError

# configure logging
import logging
log = logging.getLogger(__name__)


def get_database_location():
    if not APPDATA_DIR.is_dir():
        raise ConfigDirectoryError('the config directory could not be set')

    return APPDATA_DIR / 'adare.db.sqlite3'


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
