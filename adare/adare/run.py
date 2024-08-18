# external imports
import argparse
import sys
import time

# internal imports
from adare.cli.project import exec_create_project, exec_remove_project, exec_list_projects
from adare.cli.environment import exec_environment_load, exec_environment_create, \
    exec_environment_delete
from adare.cli.experiment import exec_experiment_create, exec_experiment_load, exec_experiment_run
from adare.cli.manage import exec_manage_reset
from adare.cli.gui import exec_gui
from adare.cli.help import exec_help_breakpoints
from adare.cli.showversion import exec_show_version
from adare.cli.show import exec_show_projects, exec_show_environment, exec_show_environments, exec_show_experiment, exec_show_runs, exec_show_run, exec_show_testfunctions, exec_show_testfunction, exec_show_experiments
from adare.cli.web import exec_web_login, exec_web_logout, exec_download_experiment, exec_download_testfunction, exec_download_environment, exec_web_sync, exec_web_upload_experiment_run
from adare.cli.testfunction import exec_create_testfunction, exec_remove_testfunction, exec_load_testfunction, exec_list_testfunctions
from adare.setup_logging import setup_logging
from adarelib.exceptions import LoggedException, LoggedErrorException


def exec_with_error_printing(func, *args, **kwargs):
    try:
        func(*args, **kwargs)
    except LoggedException as e:
        e.print()
        if isinstance(e, LoggedErrorException):
            exit(-1)
        else:
            exit(0)


def main():
    start_time = time.time()

    parser = argparse.ArgumentParser(add_help=True,
                                     description='Adare - A tool to run experiments in virtual environments')
    parser.add_argument('-V', '--version', action='store_true', help='display program version')
    parser.add_argument('-log', '--logfile', help='path to logfile')
    parser.add_argument('-v', '--verbose', action='store_true', help='verbose output (loglevel=INFO)')
    parser.add_argument('-vv', '--very-verbose', action='store_true', help='very verbose output (loglevel=DEBUG)')
    parser.add_argument('-loglvl', '--log-level', help='loglevel for logfile')
    parser.set_defaults(func=lambda args: exec_show_version(args, parser))

    subparsers = parser.add_subparsers()

    # commands: adare manage ...
    manage = subparsers.add_parser('manage', help='wrapper for needed manage commands')
    manage.set_defaults(func=lambda args: manage.print_help())
    manage_subparsers = manage.add_subparsers()

    manage_reset = manage_subparsers.add_parser('reset', help='remove database (use with caution)')
    manage_reset.set_defaults(func=lambda args: exec_with_error_printing(exec_manage_reset, args))

    # commands: adare proj ....
    project = subparsers.add_parser('project', help='wrapper for needed project commands')
    project.set_defaults(func=lambda args: project.print_help())
    project_subparsers = project.add_subparsers()

    project_create = project_subparsers.add_parser('create')
    project_create.add_argument('name', help='name of the project')
    project_create.add_argument('--description', '-d', required=False, help='description of the project')
    project_create.set_defaults(func=lambda args: exec_with_error_printing(exec_create_project, args))

    project_remove = project_subparsers.add_parser('remove')
    project_remove.add_argument('name', help='name of the project to remove')
    project_remove.set_defaults(func=lambda args: exec_with_error_printing(exec_remove_project, args))

    project_list = project_subparsers.add_parser('list')
    project_list.set_defaults(func=lambda args: exec_with_error_printing(exec_list_projects, args))

    # commands: adare env ...
    environment = subparsers.add_parser('env', help='wrapper for needed environment commands')
    environment.set_defaults(func=lambda args: environment.print_help())
    environment_subparsers = environment.add_subparsers()

    environment_load = environment_subparsers.add_parser('load')
    environment_load.add_argument('environment', help='name of the environment to load')
    environment_load.add_argument('--project', '-p', required=False,
                                  help='name of the project to load the environment to')
    environment_load.add_argument('--force', '-f', action='store_true', help='force the update of the environment')
    environment_load.set_defaults(func=lambda args: exec_with_error_printing(exec_environment_load, args))

    environment_create = environment_subparsers.add_parser('create')
    environment_create.add_argument('name', help='name of the environment')
    environment_create.add_argument('--project', '-p', required=False,
                                    help='name of the project to add the environment to')
    environment_create.set_defaults(func=lambda args: exec_with_error_printing(exec_environment_create, args))

    environment_delete = environment_subparsers.add_parser('delete')
    environment_delete.add_argument('ulid', help='ulid of the environment')
    environment_delete.add_argument('--force', '-f', action='store_true', help='force the deletion of the environment')
    environment_delete.set_defaults(func=lambda args: exec_with_error_printing(exec_environment_delete, args))

    # commands: adare exp ...
    experiment = subparsers.add_parser('exp', help='wrapper for needed experiment commands')
    experiment.add_argument('--project', '-p', required=False, help='name of the project')
    experiment.set_defaults(func=lambda args: experiment.print_help())
    experiment_subparsers = experiment.add_subparsers()

    experiment_create = experiment_subparsers.add_parser('create',
                                                         help='create the skeleton for new experiment to an environment')
    experiment_create.add_argument('experiment', help='name of the experiment to add')
    experiment_create.set_defaults(func=lambda args: exec_with_error_printing(exec_experiment_create, args))

    experiment_load = experiment_subparsers.add_parser('load', help='load the experiment')
    experiment_load.add_argument('experiment', help='name of the experiment to load')
    experiment_load.add_argument('-e', '--environment', help='name of the environment where the experiment should be loaded')
    experiment_load.add_argument('--force', '-f', action='store_true', help='force the update of the experiment')
    experiment_load.set_defaults(func=lambda args: exec_with_error_printing(exec_experiment_load, args))

    experiment_run = experiment_subparsers.add_parser('run', help='run the experiment in a given environment')
    experiment_run.add_argument('experiment', help='name of the experiment to run')
    experiment_run.add_argument('-e', '--environment', help='name of the environment where the experiment should be run')
    experiment_run.add_argument('--breakpoints', '-b', nargs='*', default=[],
                                help='name of the breakpoints to stop the experiment at')
    experiment_run.add_argument('--debug', '-d', action='store_true', help='run the experiment in debug mode (stop at all breakpoints)')
    experiment_run.set_defaults(func=lambda args: exec_with_error_printing(exec_experiment_run, args))

    # commands: adare testfunction ...
    testfunction = subparsers.add_parser('testfunction', help='wrapper for needed testfunction commands')
    testfunction.add_argument('--project', '-p', required=False, help='name of the project')
    testfunction.set_defaults(func=lambda args: testfunction.print_help())
    testfunction_subparsers = testfunction.add_subparsers()

    testfunction_create = testfunction_subparsers.add_parser('create', help='create a new testfunction')
    testfunction_create.add_argument('name', help='name of the testfunction to create')
    testfunction_create.set_defaults(func=lambda args: exec_with_error_printing(exec_create_testfunction, args))

    testfunction_remove = testfunction_subparsers.add_parser('remove', help='remove a testfunction')
    testfunction_remove.add_argument('name', help='name of the testfunction to remove')
    testfunction_remove.set_defaults(func=lambda args: exec_with_error_printing(exec_remove_testfunction, args))

    testfunction_load = testfunction_subparsers.add_parser('load', help='load a testfunction')
    testfunction_load.add_argument('name', help='name of the testfunction to load')
    testfunction_load.set_defaults(func=lambda args: exec_with_error_printing(exec_load_testfunction, args))

    testfunction_list = testfunction_subparsers.add_parser('list', help='list all testfunctions')
    testfunction_list.set_defaults(func=lambda args: exec_with_error_printing(exec_list_testfunctions, args))

    # commands: adare web ...
    web = subparsers.add_parser('web', help='wrapper for needed web commands')
    web.set_defaults(func=lambda args: web.print_help())
    web_subparsers = web.add_subparsers()

    web_login = web_subparsers.add_parser('login', help='login to the web interface')
    web_login.set_defaults(func=lambda args: exec_with_error_printing(exec_web_login, args))

    web_logout = web_subparsers.add_parser('logout', help='logout from the web interface')
    web_logout.set_defaults(func=lambda args: exec_with_error_printing(exec_web_logout, args))

    web_download = web_subparsers.add_parser('download', help='download an experiment or testfunction from the web interface')
    web_download.add_argument('--project', '-p', required=False, help='name of the project')
    web_download.set_defaults(func=lambda args: web_download.print_help())
    web_download_subparsers = web_download.add_subparsers()

    web_download_experiment = web_download_subparsers.add_parser('experiment', help='download an experiment')
    web_download_experiment.add_argument('ulid', help='ulid of the experiment to download')
    web_download_experiment.set_defaults(func=lambda args: exec_with_error_printing(exec_download_experiment, args))

    web_download_testfunction = web_download_subparsers.add_parser('testfunction', help='download a testfunction')
    web_download_testfunction.add_argument('name', help='name of the testfunction to download')
    web_download_testfunction.set_defaults(func=lambda args: exec_with_error_printing(exec_download_testfunction, args))

    web_download_environment = web_download_subparsers.add_parser('environment', help='download an environment')
    web_download_environment.add_argument('name', help='name of the environment to download')
    web_download_environment.set_defaults(func=lambda args: exec_with_error_printing(exec_download_environment, args))

    web_publish = web_subparsers.add_parser('publish', help='publish an experiment run to the web interface')
    web_publish.add_argument('ulid', help='ulid of the experiment run to publish')
    web_publish.set_defaults(func=lambda args: exec_with_error_printing(exec_web_upload_experiment_run, args))

    web_sync = web_subparsers.add_parser('sync', help='sync all environments and experiments with the web interface')
    web_sync.add_argument('--project', '-p', required=False, help='name of the project')
    web_sync.set_defaults(func=lambda args: exec_with_error_printing(exec_web_sync, args))

    # commands: adare help
    help_sp = subparsers.add_parser('help', help='show help for special options')
    help_sp.set_defaults(func=lambda args: help_sp.print_help())
    help_subparsers = help_sp.add_subparsers()
    help_breakpoints = help_subparsers.add_parser('breakpoints', help='show help for breakpoints')
    help_breakpoints.add_argument('--breakpoint', '-b', required=False, help='name of the breakpoint to show the help of')
    help_breakpoints.set_defaults(func=lambda args: exec_help_breakpoints(args))

    # command: adare show
    show = subparsers.add_parser('show', help='show information')
    show.set_defaults(func=lambda args: show.print_help())
    show_subparsers = show.add_subparsers()

    show_projects = show_subparsers.add_parser('projects', help='show a list of projects')
    show_projects.set_defaults(func=lambda args: exec_with_error_printing(exec_show_projects, args))

    show_environments = show_subparsers.add_parser('environments', help='show all environments in a project')
    show_environments.set_defaults(func=lambda args: exec_with_error_printing(exec_show_environments, args))

    show_environment = show_subparsers.add_parser('environment', help='show an environment')
    show_environment.add_argument('-env', '--environment-name', help='name of the environment')
    show_environment.add_argument('-proj', '--project-name', help='name of the project')
    show_environment.add_argument('-ulid', '--ulid', help='ulid of the environment')
    show_environment.set_defaults(func=lambda args: exec_with_error_printing(exec_show_environment, args))

    show_experiments = show_subparsers.add_parser('experiments', help='show all experiments in an environment')
    show_experiments.set_defaults(func=lambda args: exec_with_error_printing(exec_show_experiments, args))

    show_experiment = show_subparsers.add_parser('experiment', help='show an experiment')
    show_experiment.add_argument('-env', '--environment-name', help='name of the environment')
    show_experiment.add_argument('-proj', '--project-name', help='name of the project')
    show_experiment.add_argument('-exp', '--experiment-name', help='name of the experiment')
    show_experiment.add_argument('-ulid', '--ulid', help='ulid of the experiment')
    show_experiment.set_defaults(func=lambda args: exec_with_error_printing(exec_show_experiment, args))

    show_runs = show_subparsers.add_parser('runs', help='show all runs')
    show_runs.add_argument('-proj', '--project', help='name of the project')
    show_runs.set_defaults(func=lambda args: exec_with_error_printing(exec_show_runs, args))

    show_run = show_subparsers.add_parser('run', help='show a run')
    show_run.add_argument('-run-id', '--run-ulid', help='ulid of the run')
    show_run.set_defaults(func=lambda args: exec_with_error_printing(exec_show_run, args))

    show_testfunctions = show_subparsers.add_parser('testfunctions', help='show all testfunctions')
    show_testfunctions.add_argument('-f', '--file-name', help='name of the file')
    show_testfunctions.set_defaults(func=lambda args: exec_with_error_printing(exec_show_testfunctions, args))

    show_testfunction = show_subparsers.add_parser('testfunction', help='show a testfunction')
    show_testfunction.add_argument('dotnotation', help='dotnotation(name) of the testfunction')
    show_testfunction.set_defaults(func=lambda args: exec_with_error_printing(exec_show_testfunction, args))


    # parse arguments
    args = parser.parse_args()

    # setup logging
    setup_logging(args, sys.argv)

    # configure logging
    import logging
    log = logging.getLogger(__name__)

    # execute function
    args.func(args)

    log.debug(f"---  Runtime {(time.time() - start_time) / 60} minutes ---")
    logging.shutdown()
