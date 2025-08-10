# internal imports
from adare.backend.basics import determine_projectdirectory
from adare.exceptions import NoProjectFoundError

# configure logging
import logging
log = logging.getLogger(__name__)


def exec_show_runs(arguments):
    from adare.frontend.terminal.run_list import print_run_list

    project = ''
    if arguments.project:
        project = arguments.project
    elif project_path := determine_projectdirectory(arguments.project):
        project = project_path.name
    else:
        raise NoProjectFoundError(log, message='no project directory found')
    print_run_list(project)


def exec_show_run(arguments):
    from adare.frontend.terminal.run import print_run
    print_run(arguments.ulid)


def exec_show_testfunctions(arguments):
    from adare.frontend.terminal.testfunction_list import print_testfunction_list
    print_testfunction_list(testfunction_file=arguments.file_name)


def exec_show_testfunction(arguments):
    from adare.frontend.terminal.testfunction import print_testfunction
    print_testfunction(arguments.dotnotation, None)


def exec_show_experiment(arguments):
    from adare.frontend.terminal.experiment import print_experiment
    print_experiment(dotnotation=arguments.dotnotation, ulid=arguments.ulid)


def exec_show_experiments(arguments):
    from adare.frontend.terminal.experiment_list import print_experiment_list
    print_experiment_list()


def exec_show_projects(arguments):
    from adare.frontend.terminal.project_list import print_project_list
    print_project_list()


def exec_show_environments(arguments):
    from adare.frontend.terminal.environment_list import print_environment_list
    print_environment_list()


def exec_show_environment(arguments):
    from adare.frontend.terminal.environment import print_environment
    print_environment(arguments.dotnotation)


