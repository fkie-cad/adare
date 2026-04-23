# internal imports
# configure logging
import logging

from adare.config.database import get_database_location

log = logging.getLogger(__name__)


def db_exists():
    return get_database_location().is_file()
