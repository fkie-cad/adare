# external imports
from pathlib import Path

# internal imports
from adare.database.api.testfunction import TestfunctionDbApi
from adare.backend.testfunction.exceptions import TestfunctionUpdatedError


# configure logging
import logging
log = logging.getLogger(__name__)


def load_testfunction_file(project_path: Path, testfunction_file: Path, requirements_file: Path) -> int:
    with TestfunctionDbApi() as api:
        if not api.testfunction_file_obj_exists(testfunction_file):
            # create a new one
            return api.create_testfunction_file_obj(project_path, testfunction_file, requirements_file).id
        else:
            # update the existing one but only add new test - never change existing ones
            return api.update_testfunction_file_obj(testfunction_file, requirements_file).id


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


def testfunction_exists(name: str):
    with TestfunctionDbApi() as api:
        return api.testfunction_exists(name)


def get_testfunction_file_hash(testfunction_id: int):
    with TestfunctionDbApi() as api:
        return api.get_testfunction_file_hash(testfunction_id)


def sync_testfunction_file(testfunction_id: int, remote_id: int, remote_url: str, is_published: bool):
    with TestfunctionDbApi() as api:
        api.sync_testfunction_file(testfunction_id, remote_id, remote_url, is_published)


def get_testfunction_files_ids(project_path: Path = None):
    with TestfunctionDbApi() as api:
        return [
            testfunction.id for testfunction in api.get_testfunction_files(project_path)
        ]
