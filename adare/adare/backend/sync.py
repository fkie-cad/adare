# configure logging
import logging
from pathlib import Path

from adare.backend.environment.commands import environment_sync
from adare.backend.environment.database import get_environments_ulids
from adare.backend.experiment.commands import experiment_sync
from adare.backend.experiment.database import get_experiments_ulids
from adare.backend.testfunction.commands import testfunction_sync
from adare.backend.testfunction.database import get_testfunction_files_ids
from adare.console import log_print
from adare.web.login import is_logged_in

log = logging.getLogger(__name__)


def sync_environments_all(project: Path = None):
    ulids = get_environments_ulids(project)
    for ulid in ulids:
        environment_sync(ulid)


def sync_experiments_all(project: Path = None):
    ulids = get_experiments_ulids(project)
    for ulid in ulids:
        experiment_sync(ulid)


def sync_testfunctions_all(project: Path = None):
    testfunction_ids = get_testfunction_files_ids(project)
    for tid in testfunction_ids:
        testfunction_sync(tid)


def sync(project: Path = None):
    if not is_logged_in(silent=True):
        log_print(log, 'You need to be logged in to sync')
        return
    log.info('syncing environments ...')
    sync_environments_all(project)
    log.info('syncing experiments ...')
    sync_experiments_all(project)
    log.info('syncing testfunctions ...')
    sync_testfunctions_all(project)

    log_print(log, 'Sync done')



