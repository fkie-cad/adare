from adare.backend.basics import determine_projectdirectory
from adare.backend.environment.commands import environment_download
from adare.backend.experiment.commands import experiment_download
from adare.backend.testfunction.commands import testfunction_download
from adarelib.exceptions import NoProjectFoundError
from adare.web.login import login, logout
from adare.backend.sync import sync
from adare.webappaccess.upload import publish_experiment_run

# configure logging
import logging
log = logging.getLogger(__name__)


def exec_web_login(arguments):
    login()


def exec_web_logout(arguments):
    logout()


def exec_download_environment(arguments):
    project_directory = determine_projectdirectory(arguments.project)
    if not project_directory:
        raise NoProjectFoundError(log, message='project directory not found')
    environment_download(project_directory, arguments.name)


def exec_download_experiment(arguments):
    project_directory = determine_projectdirectory(arguments.project)
    if not project_directory:
        raise NoProjectFoundError(log, message='project directory not found')
    experiment_download(project_directory, arguments.ulid)


def exec_download_testfunction(arguments):
    project_directory = determine_projectdirectory(arguments.project)
    if not project_directory:
        raise NoProjectFoundError(log, message='project directory not found')
    testfunction_download(project_directory, arguments.name)


def exec_web_sync(arguments):
    project_directory = determine_projectdirectory(arguments.project)
    sync(project_directory)


def exec_web_upload_experiment_run(arguments):
    publish_experiment_run(arguments.ulid)
