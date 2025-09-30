# internal imports
from adare.backend.basics import determine_projectdirectory
from adare.exceptions import NoProjectFoundError, TestFunctionNotFoundError
from adare.helperfunctions.path_resolution import resolve_testfunction_path

# configure logging
import logging
log = logging.getLogger(__name__)


def exec_create_testfunction(arguments):
    from adare.backend.testfunction.commands import testfunction_create
    if project_directory := determine_projectdirectory(arguments.project):
        testfunction_name = resolve_testfunction_path(arguments.name, project_directory)
        testfunction_create(
            project_directory,
            testfunction_name
        )
    else:
        raise NoProjectFoundError(log, message='no project directory found')


def exec_remove_testfunction(arguments):
    from adare.backend.testfunction.commands import testfunction_remove
    # Remove testfunction file by name (not path-based)
    testfunction_remove(arguments.name)


def exec_load_testfunction(arguments):
    from adare.backend.testfunction.commands import testfunction_load_global
    from pathlib import Path

    # Get force flag if provided
    force = getattr(arguments, 'force', False)

    # Try to load testfunction globally (independent of project)
    testfunction_path = Path(arguments.name)

    # If it's an absolute path or exists as given, use it directly
    if testfunction_path.is_absolute() or testfunction_path.exists():
        testfunction_load_global(testfunction_path, force=force)
        return

    # Try to find in adare appdata testfunctions directory
    try:
        from adare.config.configdirectory import get_config_directory
        config_dir = get_config_directory()
        appdata_testfunction_path = config_dir / 'appdata' / 'testfunctions' / arguments.name
        if appdata_testfunction_path.exists():
            testfunction_load_global(appdata_testfunction_path, force=force)
            return
    except Exception as e:
        log.debug(f'Could not check appdata testfunctions: {e}')

    # Handle special case for "examples/testfunctions/xxx" pattern
    if arguments.name.startswith('examples/testfunctions/'):
        testfunction_name = arguments.name.split('/')[-1]  # Get the last part (e.g., "json")

        # Try appdata with the extracted name
        try:
            from adare.config.configdirectory import get_config_directory
            config_dir = get_config_directory()
            appdata_testfunction_path = config_dir / 'appdata' / 'testfunctions' / testfunction_name
            if appdata_testfunction_path.exists():
                testfunction_load_global(appdata_testfunction_path, force=force)
                return
        except Exception as e:
            log.debug(f'Could not check appdata testfunctions with examples pattern: {e}')

    # Last fallback - try to resolve as relative to current directory
    cwd_path = Path.cwd() / arguments.name
    if cwd_path.exists():
        testfunction_load_global(cwd_path, force=force)
        return

    # If we get here, nothing worked
    raise TestFunctionNotFoundError(log, message=f'testfunction "{arguments.name}" not found in any accessible location')


def exec_list_testfunctions(arguments):
    """List testfunctions in the configured output format."""
    from adare.run import get_formatter_from_context
    from adare.frontend.terminal.testfunction_list import print_testfunction_list

    # Get formatter from CLI context
    formatter, output_file, dual_output = get_formatter_from_context()

    # Call enhanced frontend function with output format support
    testfunction_set = getattr(arguments, 'set', None)
    # Handle string 'None' that might come from Click
    if testfunction_set == 'None':
        testfunction_set = None
    print_testfunction_list(
        testfunction_file=testfunction_set,
        formatter=formatter,
        output_file=output_file,
        dual_output=dual_output
    )


def exec_check_testfunction_exists(arguments):
    """Check if a testfunction exists in the database."""
    from adare.backend.testfunction.database import testfunction_exists
    from pathlib import Path

    # Extract testfunction name from path if it's a directory
    if Path(arguments.name).is_dir():
        testfunction_name = Path(arguments.name).name
    else:
        testfunction_name = arguments.name

    exists = testfunction_exists(testfunction_name)
    if exists:
        print("exists")
        exit(0)
    else:
        print("not_found")
        exit(1)
