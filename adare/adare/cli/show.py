# internal imports
from adare.backend.project.show import print_project_list, print_project_details
from adare.backend.environment.show import print_environment_list, print_environment_details
from adare.backend.experiment.show import print_experiment_list, print_experiment_details, print_run_list, print_run_details
from adare.backend.basics import determine_projectdirectory
from adarelib.exceptions import NoProjectFoundError

# configure logging
import logging
log = logging.getLogger(__name__)


def exec_show_projects(arguments):
    """
    shows the information about projects

    :param arguments: arguments parsed via input
    """
    print_project_list()


def exec_show_project(arguments):
    """
    shows the information about projects

    :param arguments: arguments parsed via input
    """
    print_project_details(arguments.project)


def exec_show_environments(arguments):
    if arguments.project:
        project = arguments.project
    else:
        project_path = determine_projectdirectory(arguments.project)
        if not project_path:
            raise NoProjectFoundError(log, message='project directory not found')
        project = project_path.name
    print_environment_list(project)


def exec_show_environment(arguments):
    if arguments.project:
        project = arguments.project
    else:
        project_path = determine_projectdirectory(arguments.project)
        if not project_path:
            raise NoProjectFoundError(log, message='project directory not found')
        project = project_path.name
    print_environment_details(project, arguments.environment)


def exec_show_experiments(arguments):
    project = ''
    if arguments.project:
        project = arguments.project
    else:
        project_path = determine_projectdirectory(arguments.project)
        if project_path:
            project = project_path.name
    print_experiment_list(project, arguments.environment, arguments.environment_ulid)


def exec_show_experiment(arguments):
    project = ''
    if arguments.project:
        project = arguments.project
    else:
        project_path = determine_projectdirectory(arguments.project)
        if project_path:
            project = project_path.name
    print_experiment_details(project, arguments.environment, arguments.experiment, arguments.experiment_ulid)


def exec_show_runs(arguments):
    print_run_list()


def exec_show_run(arguments):
    print_run_details(arguments.run_ulid)
