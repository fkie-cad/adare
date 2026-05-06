# external imports
# configure logging
import logging
import shutil
from pathlib import Path

# internal imports
import adare.backend.testfunction.database as testfunction_database
from adare.backend.testfunction.directory import TestfunctionDirectory
from adare.backend.testfunction.exceptions import TestfunctionMissingFileError
from adare.exceptions import NotLoggedInError
from adare.webappaccess.download import download_testfunction, sync
from adare.webappaccess.login import is_logged_in

log = logging.getLogger(__name__)


def testfunction_sync(testfunction_id: int):
    if not is_logged_in():
        log.info('sync is not possible because user is not logged in')
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


def testfunction_remove(name: str):
    """Remove a testfunction file by name (e.g., 'xml', 'json', 'csv')."""
    # Check if testfunction file exists
    if not testfunction_database.testfunction_file_exists(name):
        log.error(f'Testfunction "{name}" does not exist')
        return

    # Check usage across all projects
    usage = testfunction_database.get_testfunction_usage(name)

    # Display what will be deleted
    print(f'\n⚠️  About to delete testfunction: "{name}"')
    print('   This action cannot be undone!\n')

    if usage['projects_affected']:
        print('   📊 Usage Statistics:')
        print(f'      • Used in {len(usage["projects_affected"])} project(s)')
        print(f'      • {len(usage["experiments"])} experiment(s) use this testfunction')
        print(f'      • {len(usage["runs"])} experiment run(s) will be affected\n')

        print('   📁 Projects affected:')
        for proj in usage['projects_affected']:
            print(f'      • {proj["name"]}')

        if usage['experiments']:
            print('\n   🧪 Experiments using this testfunction:')
            for exp in usage['experiments'][:10]:  # Show first 10
                print(f'      • {exp["project"]}.{exp["name"]}')
            if len(usage['experiments']) > 10:
                print(f'      ... and {len(usage["experiments"]) - 10} more')

        if usage['runs']:
            print(f'\n   ⚠️  WARNING: {len(usage["runs"])} experiment run(s) will lose data!')

        print()
    else:
        print('   ✓ Testfunction is not used in any projects\n')

    # Ask for confirmation
    response = input(f'Are you sure you want to delete testfunction "{name}"? (y/N): ').strip().lower()

    if response != 'y':
        log.info('Deletion cancelled by user')
        print('Deletion cancelled.')
        return

    # Remove testfunction file from database by name
    testfunction_database.remove_testfunction_file(name)
    log.info(f'Successfully deleted testfunction "{name}"')


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

    if usage['exists'] and not usage['can_safely_delete']:
        if not force:
            log.info(f'Testfunction "{testfunction_name}" is currently used by {len(usage["experiments"])} experiments with {len(usage["runs"])} runs')
            log.info('Use --force to overwrite and delete associated experiment runs')
            log.info(f'Experiments affected: {", ".join([exp["name"] for exp in usage["experiments"]])}')
            return usage['testfunction_file_id']  # Return existing ID without updating
        # Force mode - ask for confirmation
        print(f'\n⚠️  WARNING: Testfunction "{testfunction_name}" is currently in use!')
        print(f'   • Used by {len(usage["experiments"])} experiments: {", ".join([exp["name"] for exp in usage["experiments"]])}')
        print(f'   • Would delete {len(usage["runs"])} experiment runs')
        print('   • This action cannot be undone!')

        response = input('\nContinue and delete all associated experiment runs? (y/N): ').strip().lower()

        if response != 'y':
            log.info('Operation cancelled by user')
            return usage['testfunction_file_id']

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
    from rich.layout import Layout

    from adare.database.api.frontend import DataRetrievalApi
    from adare.frontend.terminal.console import DefaultConsole
    from adare.frontend.terminal.testfunction_list import TestfunctionListPanel

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


def testfunction_download(project_path: Path, name: str, version: int = None):
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
    download_testfunction(name, testfunction_directory.path, version=version)
    log.info(f'Testfunction {name} downloaded')


def _refresh_global_testfunction(manager, source_py: Path, source_req: Path, name: str) -> tuple[Path, Path]:
    """Make sure the global STATE_DIR copy mirrors the source files.

    Why: install_testfunction is a no-op when targets exist, so source edits would not propagate.
    """
    from adare.helperfunctions.hash import combine_hashes, hash_file_sha256
    from adare.helperfunctions.integrity import unprotect_files_for_update

    target_dir = manager.global_testfunctions_dir / name
    target_py = target_dir / source_py.name
    target_req = target_dir / 'requirements.txt'

    if not target_py.exists():
        return manager.install_testfunction(
            source_python_file=source_py,
            source_requirements_file=source_req,
            name=name,
        )

    src_files = [source_py, source_req] if source_req.exists() else [source_py]
    tgt_files = [target_py, target_req] if target_req.exists() else [target_py]
    if len(src_files) == len(tgt_files):
        if combine_hashes([hash_file_sha256(f) for f in src_files]) == \
                combine_hashes([hash_file_sha256(f) for f in tgt_files]):
            return target_py, target_req

    unprotect_files_for_update([target_py, target_req])
    target_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_py, target_py)
    if source_req.exists():
        shutil.copy2(source_req, target_req)
    elif not target_req.exists():
        target_req.touch()
    return target_py, target_req


def testfunction_sync_all(root: Path, skip_names: tuple[str, ...] = ('visual',)) -> dict:
    """Walk root/<name>/ dirs and upsert each testfunction by hash."""
    from adare.backend.testfunction.manager import TestfunctionManager
    from adare.database.api.testfunction import TestfunctionDbApi
    from adare.helperfunctions.integrity import protect_loaded_files

    manager = TestfunctionManager()
    manager.ensure_global_directory_exists()

    summary: dict[str, list[str]] = {'created': [], 'updated': [], 'unchanged': [], 'skipped': []}

    with TestfunctionDbApi() as api:
        for sub in sorted(p for p in root.iterdir() if p.is_dir()):
            if sub.name in skip_names:
                summary['skipped'].append(sub.name)
                continue
            py_files = list(sub.glob('*.py'))
            if not py_files:
                continue
            source_py = py_files[0]
            source_req = sub / 'requirements.txt'

            target_py, target_req = _refresh_global_testfunction(manager, source_py, source_req, sub.name)
            action, _ = api.upsert_testfunction_file_obj(target_py, target_req)
            summary[action].append(sub.name)
            if action in ('created', 'updated'):
                protect_loaded_files([target_py, target_req])

    return summary
