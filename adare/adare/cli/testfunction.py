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
    from adare.backend.testfunction.commands import testfunction_list
    testfunction_list(testfunction_set=getattr(arguments, 'set', None))
