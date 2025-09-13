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
    testfunction_by_file = testfunction_database.list_testfunctions()
    
    # Combine all testfunctions into a single list
    all_testfunctions = []
    for file, data in testfunction_by_file.items():
        for tf in data:
            # Add file information to each testfunction
            tf_with_file = tf.copy()
            tf_with_file['file'] = Path(file).stem
            all_testfunctions.append(tf_with_file)
    
    # Filter by testfunction set if specified
    if testfunction_set:
        filtered_testfunctions = []
        for tf in all_testfunctions:
            # Check if the testfunction belongs to the specified set
            file_path = tf['file']
            # Extract the base filename without extension
            file_base = Path(file_path).stem
            
            # Check if the testfunction set matches the file base name or is contained in the path
            if (testfunction_set == file_base or 
                testfunction_set in file_path or 
                file_path.startswith(testfunction_set)):
                filtered_testfunctions.append(tf)
        all_testfunctions = filtered_testfunctions
    
    if all_testfunctions:
        df = pd.DataFrame(all_testfunctions)
        # Reorder columns to show file first
        if 'file' in df.columns:
            cols = ['file'] + [col for col in df.columns if col != 'file']
            df = df[cols]
        title = f"All testfunctions" + (f" (set: {testfunction_set})" if testfunction_set else "")
        print_df(df, title=title)
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
