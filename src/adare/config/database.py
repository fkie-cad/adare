# internal imports
from .configdirectory import get_default_config_directory
from .exceptions import ConfigDirectoryError

# configure logging
import logging
log = logging.getLogger(__name__)


def get_database_location():
    try:
        CONFIG_DIR = get_default_config_directory(create_if_missing=True)
    except (FileNotFoundError, FileExistsError, NotADirectoryError, IsADirectoryError) as e:
        CONFIG_DIR = None

    if not CONFIG_DIR:
        raise ConfigDirectoryError(f'the config directory could not be set')

    return CONFIG_DIR / 'adare.db.sqlite3'


DB_STATUS_LIST = [
    'success',
    'failed',
]

