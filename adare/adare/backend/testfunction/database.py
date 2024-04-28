# external imports
from pathlib import Path

# internal imports
from adare.database.api.testfunction import TestfunctionDbApi
from adare.backend.testfunction.exceptions import TestfunctionUpdatedError


# configure logging
import logging
log = logging.getLogger(__name__)


def load_testfunction_file(project_path: Path, testfunction_file: Path):
    with TestfunctionDbApi() as api:
        if not api.testfunction_file_obj_exists(testfunction_file):
            # create a new one
            api.create_testfunction_file_obj(project_path, testfunction_file)
        else:
            # update the existing one but only add new test - never change existing ones
            api.update_testfunction_file_obj(testfunction_file)


def remove_testfunction_file(testfunction_file: Path):
    with TestfunctionDbApi() as api:
        if not api.testfunction_file_obj_exists(testfunction_file):
            raise TestfunctionUpdatedError(
                log,
                message=f'Testfunction {testfunction_file} does not exist',
            )
        api.remove_testfunction_file_obj(testfunction_file)
        log.info(f'removed testfunction {testfunction_file}')
        return True
    return False


def list_testfunctions():
    with TestfunctionDbApi() as api:
        return api.get_testfunctions_by_file()


