# internal imports
# configure logging
import logging

from adare.api import AdareAPI
from adare.backend.basics import determine_projectdirectory
from adare.console import print_error_message, print_success_message
from adare.core.dto.testfunction import TestfunctionCreateRequest, TestfunctionLoadRequest
from adare.exceptions import NoProjectFoundError, TestFunctionNotFoundError
from adare.helperfunctions.path_resolution import resolve_testfunction_path

log = logging.getLogger(__name__)


def _handle_api_error(result) -> None:
    """
    Handle an API error result by printing formatted error message and exiting.

    Args:
        result: Result object with error information
    """
    error = result.error
    print_error_message(
        title=f'{error.code}: {error.message}',
        next_steps=error.solutions
    )
    exit(1)


def exec_create_testfunction(arguments):
    """Create a new testfunction using AdareAPI."""
    if project_directory := determine_projectdirectory(arguments.project):
        testfunction_name = resolve_testfunction_path(arguments.name, project_directory)

        api = AdareAPI()
        result = api.testfunction.create(TestfunctionCreateRequest(
            project_path=project_directory,
            name=testfunction_name
        ))

        if result.success:
            print_success_message(
                title=f'Testfunction "{result.data.name}" created successfully!',
                location=str(result.data.file_path) if result.data.file_path else None,
                next_steps=result.data.next_steps,
                tip=result.data.tip
            )
        else:
            _handle_api_error(result)
    else:
        raise NoProjectFoundError(log, message='no project directory found')


def exec_remove_testfunction(arguments):
    """Remove a testfunction using AdareAPI."""
    api = AdareAPI()

    # Check if force flag is set
    force = getattr(arguments, 'force', False)

    result = api.testfunction.remove(arguments.name, force=force)

    if result.success:
        print_success_message(
            title=f'Testfunction "{result.data.name}" removed successfully!'
        )
    else:
        _handle_api_error(result)


def exec_load_testfunction(arguments):
    """Load a testfunction using AdareAPI."""
    from pathlib import Path

    # Get force flag if provided
    force = getattr(arguments, 'force', False)

    # Resolve the testfunction path
    testfunction_path = Path(arguments.name)

    # If it's an absolute path or exists as given, use it directly
    if testfunction_path.is_absolute() or testfunction_path.exists():
        resolved_path = testfunction_path
    else:
        resolved_path = None

        # Try to find in adare appdata testfunctions directory
        try:
            from adare.config.configdirectory import get_config_directory
            config_dir = get_config_directory()
            appdata_testfunction_path = config_dir / 'appdata' / 'testfunctions' / arguments.name
            if appdata_testfunction_path.exists():
                resolved_path = appdata_testfunction_path
        except Exception as e:
            log.debug(f'Could not check appdata testfunctions: {e}')

        # Handle special case for "examples/testfunctions/xxx" pattern
        if resolved_path is None and arguments.name.startswith('examples/testfunctions/'):
            testfunction_name = arguments.name.split('/')[-1]  # Get the last part (e.g., "json")
            try:
                from adare.config.configdirectory import get_config_directory
                config_dir = get_config_directory()
                appdata_testfunction_path = config_dir / 'appdata' / 'testfunctions' / testfunction_name
                if appdata_testfunction_path.exists():
                    resolved_path = appdata_testfunction_path
            except Exception as e:
                log.debug(f'Could not check appdata testfunctions with examples pattern: {e}')

        # Last fallback - try to resolve as relative to current directory
        if resolved_path is None:
            cwd_path = Path.cwd() / arguments.name
            if cwd_path.exists():
                resolved_path = cwd_path

    # If we couldn't resolve the path, error out
    if resolved_path is None:
        raise TestFunctionNotFoundError(log, message=f'testfunction "{arguments.name}" not found in any accessible location')

    # Use the API to load
    api = AdareAPI()
    result = api.testfunction.load(TestfunctionLoadRequest(
        path=resolved_path,
        force=force
    ))

    if result.success:
        print_success_message(
            title=f'Testfunction "{result.data.name}" loaded successfully!',
            next_steps=result.data.next_steps,
            tip=result.data.tip
        )
    else:
        _handle_api_error(result)


def exec_list_testfunctions(arguments):
    """List testfunctions in the configured output format."""
    from adare.frontend.terminal.testfunction_list import print_testfunction_list
    from adare.run import get_formatter_from_context

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
    """Check if a testfunction exists in the database using AdareAPI."""
    from pathlib import Path

    # Extract testfunction name from path if it's a directory
    if Path(arguments.name).is_dir():
        testfunction_name = Path(arguments.name).name
    else:
        testfunction_name = arguments.name

    api = AdareAPI()
    result = api.testfunction.exists(testfunction_name)

    if result.success:
        if result.data.exists:
            print("exists")
            exit(0)
        else:
            print("not_found")
            exit(1)
    else:
        _handle_api_error(result)
