# external imports
from pathlib import Path
import shutil
import pandas as pd

# internal imports
import adare.backend.testfunction.database as testfunction_database
from adare.backend.testfunction.directory import TestfunctionDirectory


# configure logging
import logging
log = logging.getLogger(__name__)


def testfunction_create(project_path: Path, name: str):
    testfunction_directory = TestfunctionDirectory(project_path)
    testfunction_directory.create_testfunction(name)


def testfunction_remove(project_path: Path, name: str):
    testfunction_directory = TestfunctionDirectory(project_path)
    testfunction_directory.remove_testfunction(name)


def testfunction_load(project_path: Path):
    pass