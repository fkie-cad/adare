# internal imports
from adare.backend.basics import determine_projectdirectory
from adare.exceptions import NoProjectFoundError

# configure logging
import logging
log = logging.getLogger(__name__)


def exec_create_testfunction(arguments):
    from adare.backend.testfunction.commands import testfunction_create
    if project_directory := determine_projectdirectory(arguments.project):
        testfunction_create(
            project_directory,
            arguments.name
        )
    else:
        raise NoProjectFoundError(log, message='no project directory found')


def exec_remove_testfunction(arguments):
    from adare.backend.testfunction.commands import testfunction_remove
    if project_directory := determine_projectdirectory(arguments.project):
        testfunction_remove(
            project_directory,
            arguments.name
        )
    else:
        raise NoProjectFoundError(log, message='no project directory found')


def exec_load_testfunction(arguments):
    from adare.backend.testfunction.commands import testfunction_load
    if project_directory := determine_projectdirectory(arguments.project):
        testfunction_load(
            project_directory,
            arguments.name
        )
    else:
        raise NoProjectFoundError(log, message='no project directory found')


def exec_list_testfunctions(arguments):
    """List testfunctions in the configured output format."""
    from adare.run import get_formatter_from_context
    from adare.frontend.terminal.testfunction_list import print_testfunction_list

    # Get formatter from CLI context
    formatter, output_file, dual_output = get_formatter_from_context()

    # Call enhanced frontend function with output format support
    testfunction_set = getattr(arguments, 'set', None)
    print_testfunction_list(
        testfunction_file=testfunction_set,
        formatter=formatter,
        output_file=output_file,
        dual_output=dual_output
    )
