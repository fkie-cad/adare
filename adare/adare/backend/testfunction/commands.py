# external imports
from pathlib import Path
import pandas as pd

# internal imports
import adare.backend.testfunction.database as testfunction_database
from adare.backend.testfunction.directory import TestfunctionDirectory
from adare.backend.testfunction.exceptions import TestfunctionMissingFileError
from adare.helperfunctions.cli import print_df
from adare.webappaccess.download import download_testfunction, sync
from adare.webappaccess.login import is_logged_in
from adare.exceptions import NotLoggedInError

# configure logging
import logging
log = logging.getLogger(__name__)


def testfunction_sync(testfunction_id: int):
    if not is_logged_in():
        log.info(f'sync is not possible because user is not logged in')
        return
    # get testfunction from database
    sha256 = testfunction_database.get_testfunction_file_hash(testfunction_id)
    # download testfunction from webapp
    metadata_remote = sync(sha256, 'testfunction')
    if not metadata_remote:
        log.info(f'testfunction {testfunction_id} does not exist remotely')
        return
    is_published = metadata_remote.get('published')
    remote_url = metadata_remote.get('gitea_url')
    remote_id = metadata_remote.get('id')
    testfunction_database.sync_testfunction_file(testfunction_id, remote_id, remote_url, is_published)
    log.info(f'testfunction {testfunction_id} synced')


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
    
    # Unprotect files before removal
    from adare.helperfunctions.integrity import unprotect_files_for_update
    testfunction_files = [testfunction_directory.pythonfile, testfunction_directory.requirements]
    unprotected_files = unprotect_files_for_update(testfunction_files)
    log.info(f'Unprotected {len(unprotected_files)} testfunction files for removal')
    
    testfunction_database.remove_testfunction_file(testfunction_directory.pythonfile)
    testfunction_directory.remove_testfunction()


def testfunction_load(project_path: Path, name: str):
    testfunction_directory = TestfunctionDirectory(project_path, name)
    if not testfunction_directory.testfunction_exists():
        raise TestfunctionMissingFileError(
            log,
            message=f'Testfunction {name} does not exist',
        )
    testfunction_id = testfunction_database.load_testfunction_file(project_path, testfunction_directory.pythonfile, testfunction_directory.requirements)
    testfunction_sync(testfunction_id)
    
    # Protect testfunction files after loading
    from adare.helperfunctions.integrity import protect_loaded_files
    testfunction_files = [testfunction_directory.pythonfile, testfunction_directory.requirements]
    protected_files = protect_loaded_files(testfunction_files)
    log.info(f'Protected {len(protected_files)} testfunction files for {name}')


def testfunction_list(testfunction_set: str = None):
    from adare.frontend.terminal.testfunction_list import TestfunctionListPanel
    from adare.frontend.terminal.console import DefaultConsole
    from adare.database.api.frontend import DataRetrievalApi
    from rich.layout import Layout

    # Use the same data source as the working testfunction show command
    with DataRetrievalApi() as api:
        testfunctions_df = api.get_testfunction_list()

    # Filter by testfunction set if specified
    if testfunction_set:
        # Filter based on file name (extracted from dotnotation or file_name column)
        if 'file_name' in testfunctions_df.columns:
            file_column = 'file_name'
        elif 'dotnotation' in testfunctions_df.columns:
            # Extract file name from dotnotation
            testfunctions_df = testfunctions_df.copy()
            testfunctions_df['file_name'] = testfunctions_df['dotnotation'].apply(
                lambda x: x.split('.', 1)[0] if '.' in str(x) else str(x)
            )
            file_column = 'file_name'
        else:
            file_column = None

        if file_column:
            # Filter by testfunction set
            mask = (
                testfunctions_df[file_column].str.contains(testfunction_set, na=False) |
                testfunctions_df[file_column].str.startswith(testfunction_set, na=False) |
                (testfunctions_df[file_column] == testfunction_set)
            )
            testfunctions_df = testfunctions_df[mask]

    if not testfunctions_df.empty:
        console = DefaultConsole()
        layout = Layout(name="root")
        panel = TestfunctionListPanel(testfunctions_df, testfunction_file=None)  # None means show all files
        layout.update(panel)
        console.print(layout)
    else:
        filter_msg = f" for set '{testfunction_set}'" if testfunction_set else ""
        print(f"No testfunctions found{filter_msg}")


def testfunction_download(project_path: Path, name: str):
    if not is_logged_in():
        raise NotLoggedInError(log)
    # check if testfunction already exists
    if testfunction_database.testfunction_exists(name):
        raise TestfunctionMissingFileError(
            log,
            message=f'Testfunction {name} already exists',
        )

    testfunction_directory = TestfunctionDirectory(project_path, name)
    if testfunction_directory.testfunction_exists():
        raise TestfunctionMissingFileError(
            log,
            message=f'Testfunction {name} already exists',
        )
    # create testfunction directory
    testfunction_directory.path.mkdir(parents=True, exist_ok=True)
    download_testfunction(name, testfunction_directory.path)
    log.info(f'Testfunction {name} downloaded')
