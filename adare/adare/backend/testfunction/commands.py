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
    from adare.backend.testfunction.manager import TestfunctionManager

    testfunction_directory = TestfunctionDirectory(project_path, name)
    if not testfunction_directory.testfunction_exists():
        raise TestfunctionMissingFileError(
            log,
            message=f'Testfunction {name} does not exist',
        )

    # Use TestfunctionManager to install to global directory
    manager = TestfunctionManager()
    manager.ensure_global_directory_exists()

    # Install testfunction to global directory (copies files if they don't exist)
    target_python_file, target_requirements_file = manager.install_testfunction(
        source_python_file=testfunction_directory.pythonfile,
        source_requirements_file=testfunction_directory.requirements,
        name=name
    )

    # Load testfunction using the global paths
    testfunction_id = testfunction_database.load_testfunction_file(project_path, target_python_file, target_requirements_file)
    testfunction_sync(testfunction_id)

    # Protect testfunction files after loading (protect the global copies)
    from adare.helperfunctions.integrity import protect_loaded_files
    testfunction_files = [target_python_file, target_requirements_file]
    protected_files = protect_loaded_files(testfunction_files)
    log.info(f'Protected {len(protected_files)} testfunction files for {name}')


def testfunction_load_global(testfunction_path: Path, force: bool = False):
    """Load a testfunction from an absolute path, independent of project structure."""
    if not testfunction_path.exists():
        raise TestfunctionMissingFileError(
            log,
            message=f'Testfunction file {testfunction_path} does not exist',
        )

    # Determine if it's a python file or a directory containing a testfunction
    if testfunction_path.is_file() and testfunction_path.suffix == '.py':
        # Direct python file
        python_file = testfunction_path
        requirements_file = testfunction_path.parent / 'requirements.txt'
        # Use parent directory as a "fake" project path for database purposes
        project_path = testfunction_path.parent
        testfunction_name = python_file.stem
    elif testfunction_path.is_dir():
        # Directory containing testfunction - look for .py file inside
        python_files = list(testfunction_path.glob('*.py'))
        if not python_files:
            raise TestfunctionMissingFileError(
                log,
                message=f'No Python file found in testfunction directory {testfunction_path}',
            )
        if len(python_files) > 1:
            # Look for a main file or use the first one
            main_files = [f for f in python_files if f.stem in ['main', 'testfunction', testfunction_path.name]]
            python_file = main_files[0] if main_files else python_files[0]
        else:
            python_file = python_files[0]

        requirements_file = testfunction_path / 'requirements.txt'
        project_path = testfunction_path
        testfunction_name = testfunction_path.name
    else:
        raise TestfunctionMissingFileError(
            log,
            message=f'Testfunction path {testfunction_path} must be a Python file or directory',
        )

    # Check if testfunction already exists and is being used
    usage = testfunction_database.get_testfunction_usage(testfunction_name)

    if usage['exists'] and not usage['can_safely_update']:
        if not force:
            log.info(f'Testfunction "{testfunction_name}" is currently used by {len(usage["experiments"])} experiments with {len(usage["runs"])} runs')
            log.info(f'Use --force to overwrite and delete associated experiment runs')
            log.info(f'Experiments affected: {", ".join([exp["name"] for exp in usage["experiments"]])}')
            return usage['testfunction_id']  # Return existing ID without updating
        else:
            # Force mode - ask for confirmation
            print(f'\n⚠️  WARNING: Testfunction "{testfunction_name}" is currently in use!')
            print(f'   • Used by {len(usage["experiments"])} experiments: {", ".join([exp["name"] for exp in usage["experiments"]])}')
            print(f'   • Would delete {len(usage["runs"])} experiment runs')
            print(f'   • This action cannot be undone!')

            response = input('\nContinue and delete all associated experiment runs? (y/N): ').strip().lower()

            if response != 'y':
                log.info('Operation cancelled by user')
                return usage['testfunction_id']

            # Delete associated experiment runs
            deleted_count = testfunction_database.delete_experiment_runs_for_testfunction(testfunction_name)
            log.info(f'Deleted {deleted_count} experiment runs for testfunction "{testfunction_name}"')

    # Use TestfunctionManager to install to global directory
    from adare.backend.testfunction.manager import TestfunctionManager
    manager = TestfunctionManager()
    manager.ensure_global_directory_exists()

    # Install testfunction to global directory (copies files if they don't exist)
    target_python_file, target_requirements_file = manager.install_testfunction(
        source_python_file=python_file,
        source_requirements_file=requirements_file,
        name=testfunction_name
    )

    # Load the testfunction into the global database using global paths
    testfunction_id = testfunction_database.load_testfunction_file(project_path, target_python_file, target_requirements_file)
    testfunction_sync(testfunction_id)

    # Protect testfunction files after loading (protect the global copies)
    from adare.helperfunctions.integrity import protect_loaded_files
    testfunction_files = [target_python_file]
    if target_requirements_file.exists():
        testfunction_files.append(target_requirements_file)
    protected_files = protect_loaded_files(testfunction_files)
    log.info(f'Protected {len(protected_files)} testfunction files for {python_file.name}')

    return testfunction_id


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
