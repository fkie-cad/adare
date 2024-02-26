# external imports
from pathlib import Path
import shutil
import pandas as pd

# internal imports
import adare.backend.testfunction.database as testfunction_database
from adare.backend.testfunction.directory import TestfunctionDirectory
from adare.backend.testfunction.exceptions import TestfunctionMissingFileError
from adarelib.helperfunctions.cli import print_df


# configure logging
import logging
log = logging.getLogger(__name__)


def testfunction_create(project_path: Path, name: str):
    testfunction_directory = TestfunctionDirectory(project_path, name)
    testfunction_directory.create_testfunction()


def testfunction_remove(project_path: Path, name: str):
    testfunction_directory = TestfunctionDirectory(project_path, name)
    if not testfunction_directory.testfunction_exists():
        raise TestfunctionMissingFileError(
            log,
            message=f'Testfunction {name} does not exist',
        )
    testfunction_database.remove_testfunction_file(testfunction_directory.pythonfile)
    testfunction_directory.remove_testfunction()


def testfunction_load(project_path: Path, name: str):
    testfunction_directory = TestfunctionDirectory(project_path, name)
    if not testfunction_directory.testfunction_exists():
        raise TestfunctionMissingFileError(
            log,
            message=f'Testfunction {name} does not exist',
        )
    testfunction_database.load_testfunction_file(testfunction_directory.pythonfile)


def testfunction_list():
    testfunction_by_file = testfunction_database.list_testfunctions()
    for file, data in testfunction_by_file.items():
        print_df(pd.DataFrame(data), title=str(file))

