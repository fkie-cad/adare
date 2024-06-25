# internal imports
from adare.frontend.terminal.testfunction_list import print_testfunction_list
from adare.frontend.terminal.testfunction import print_testfunction
from adare.backend.basics import determine_projectdirectory
from adare.frontend.terminal.run_list import print_run_list
from adare.frontend.terminal.run import print_run
from adare.frontend.terminal.project_list import print_project_list
from adare.frontend.terminal.environment_list import print_environment_list
from adare.frontend.terminal.environment import print_environment
from adare.frontend.terminal.experiment import print_experiment
from adare.frontend.terminal.experiment_list import print_experiment_list

# configure logging
import logging
log = logging.getLogger(__name__)


def exec_show_runs(arguments):
    project = ''
    if arguments.project:
        project = arguments.project
    elif project_path := determine_projectdirectory(arguments.project):
        project = project_path.name
    print_run_list(project)


def exec_show_run(arguments):
    print_run(arguments.run_ulid)


def exec_show_testfunctions(arguments):
    print_testfunction_list(testfunction_file=arguments.file_name)


def exec_show_testfunction(arguments):
    print_testfunction(arguments.dotnotation, None)


def exec_show_experiment(arguments):
    print_experiment(arguments.project_name, arguments.environment_name, arguments.experiment_name, arguments.ulid)


def exec_show_experiments(arguments):
    print_experiment_list()


def exec_show_projects(arguments):
    print_project_list()


def exec_show_environments(arguments):
    print_environment_list()


def exec_show_environment(arguments):
    print_environment(arguments.environment_name, arguments.project_name, arguments.ulid)


