# internal imports
from adare.config.database import get_database_location


# configure logging
import logging
log = logging.getLogger(__name__)


def db_exists():
    return get_database_location().is_file()
