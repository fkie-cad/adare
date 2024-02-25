# internal imports
from adare.config.database import get_database_location

# configure logging
import logging
log = logging.getLogger(__name__)


def exec_manage_reset(arguments):
    # get database location
    database_location = get_database_location()
    # remove database
    if database_location.exists():
        log.info(f'removing database {database_location}')
        database_location.unlink()

