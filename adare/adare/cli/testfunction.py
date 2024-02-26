# external imports
from pathlib import Path

# internal imports
from adare.backend.testfunction.commands import testfunction_create, testfunction_remove, testfunction_load, testfunction_list
from adare.backend.basics import determine_projectdirectory
from adarelib.exceptions import NoProjectFoundError

# configure logging
import logging
log = logging.getLogger(__name__)


def exec_create_testfunction(arguments):
    if project_directory := determine_projectdirectory(arguments.project):
        testfunction_create(
            project_directory,
            arguments.name
        )
    else:
        raise NoProjectFoundError(log, message='no project directory found')


def exec_remove_testfunction(arguments):
    if project_directory := determine_projectdirectory(arguments.project):
        testfunction_remove(
            project_directory,
            arguments.name
        )
    else:
        raise NoProjectFoundError(log, message='no project directory found')


def exec_load_testfunction(arguments):
    if project_directory := determine_projectdirectory(arguments.project):
        testfunction_load(
            project_directory,
            arguments.name
        )
    else:
        raise NoProjectFoundError(log, message='no project directory found')


def exec_list_testfunctions(arguments):
    testfunction_list()