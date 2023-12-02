# external imports
import argparse
import sys
import time

# internal imports
from adare.cli.environment import exec_run_experiment, exec_env_create, exec_add_experiment, exec_remove_experiment, exec_env_remove
from adare.cli.project import exec_create_project, exec_remove_project
from adare.cli.gui import exec_gui
from adare.cli.showversion import exec_show_version
from adare.cli.show import exec_show_env, exec_show_experiment, exec_show_runs, exec_show_run_result, exec_show_project
from adare.setup_logging import setup_logging


def run():
    start_time = time.time()

    parser = argparse.ArgumentParser(add_help=True, description='Adare - A tool to run experiments in virtual environments')
    parser.add_argument('-V', '--version', action='store_true', help='display program version')
    parser.add_argument('-l', '--logfile', help='path to logfile')
    parser.add_argument('-v', '--verbose', action='store_true', help='verbose output (loglevel=INFO)')
    parser.add_argument('-vv', '--very-verbose', action='store_true', help='very verbose output (loglevel=DEBUG)')
    parser.add_argument('-log', '--log', type=str, help='logfile')
    parser.add_argument('-loglvl', '--log-level', help='loglevel for logfile')
    parser.set_defaults(func=lambda args: exec_show_version(args, parser))

    subparsers = parser.add_subparsers()

    # commands: adare proj ....
    project = subparsers.add_parser('project', help='wrapper for needed project commands')
    project.set_defaults(func=lambda args: project.print_help())
    project_subparsers = project.add_subparsers()

    project_create = project_subparsers.add_parser('create')
    project_create.add_argument('name', help='name of the project')
    project_create.set_defaults(func=exec_create_project)

    project_remove = project_subparsers.add_parser('remove')
    project_remove.add_argument('name', help='name of the project to remove')
    project_remove.set_defaults(func=exec_remove_project)

    # commands: adare env ...
    environment = subparsers.add_parser('env', help='wrapper for needed environment commands')
    environment.set_defaults(func=lambda args: environment.print_help())
    environment_subparsers = environment.add_subparsers()

    environment_create = environment_subparsers.add_parser('create')
    environment_create.add_argument('config', help='path to the environment config file')
    environment_create.add_argument('--name', required=False, help='name of the environment')
    environment_create.add_argument('--project', '-p', required=False, help='name of the project to add the environment to')
    environment_create.set_defaults(func=exec_env_create)

    environment_remove = environment_subparsers.add_parser('remove')
    environment_remove.add_argument('environment', help='name of the environment to remove')
    environment_remove.add_argument('--project', '-p', required=False, help='name of the project to remove the environment from (if not given, the environment will be removed the current working directory project)')
    environment_remove.set_defaults(func=exec_env_remove)


    # commands: adare gui ...
    gui = subparsers.add_parser('gui', help='starts a webgui for adare')
    gui.add_argument('-p', '--port', type=int, required=False, help='port to run the webgui on')
    gui.set_defaults(func=exec_gui)

    # commands: adare exp ...
    experiment = subparsers.add_parser('exp', help='wrapper for needed experiment commands')
    experiment.add_argument('--project', '-p', required=False, help='name of the project to add the environment to')
    experiment.set_defaults(func=lambda args: experiment.print_help())
    experiment_subparsers = experiment.add_subparsers()

    experiment_run = experiment_subparsers.add_parser('run', help='run the experiment in a given environment')
    experiment_run.add_argument('experiment', help='name of the experiment to run')
    experiment_run.add_argument('--environment', '-env', required=True, help='name of the environment where the experiment should be run')
    experiment_run.add_argument('--debugmode', action='store_true', help='run the experiment in debug mode')
    experiment_run.set_defaults(func=exec_run_experiment)

    experiment_create = experiment_subparsers.add_parser('create', help='create the skeleton for new experiment to an environment')
    experiment_create.add_argument('experiment', help='name of the experiment to add')
    experiment_create.add_argument('--environment', '-env', required=True, help='name of the environment to add the experiment to')
    experiment_create.add_argument('--networkdrive')
    experiment_create.add_argument('--usb')
    experiment_create.set_defaults(func=exec_add_experiment)

    experiment_remove = experiment_subparsers.add_parser('remove', help='delete an experiment from an environment')
    experiment_remove.add_argument('experiment', help='name of the experimenttestenv_windows10_new to remove')
    experiment_remove.add_argument('--environment', '-env', required=True, help='name of the environment to remove the experiment from')
    experiment_remove.set_defaults(func=exec_remove_experiment)

    # commands: adare show ...
    show = subparsers.add_parser('show', help='wrapper for needed show commands')
    show.set_defaults(func=lambda args: show.print_help())
    show_subparsers = show.add_subparsers()

    show_project = show_subparsers.add_parser('project', help='show a list of projects')
    show_project.set_defaults(func=exec_show_project)

    show_env = show_subparsers.add_parser('env', help='show the environments of a project')
    show_env.add_argument('--project', '-p', required=False, help='name of the project to show the environments of')
    show_env.add_argument('--details', '-d', action='store_true', help='show details of the environments')
    show_env.set_defaults(func=exec_show_env)

    show_exp = show_subparsers.add_parser('exp', help='show a list of experiments')
    show_exp.add_argument('experiment', help='name of the experiment to show the information of')
    show_exp.add_argument('environment', help='name of the environment to show the experiments of')
    show_exp.add_argument('--project', '-p', required=False, help='name of the project to show the experiments of')
    show_exp.set_defaults(func=exec_show_experiment)

    show_runs = show_subparsers.add_parser('runs', help='show a list of experiment runs')
    show_runs.add_argument('experiment', help='name of the experiment to show the information of')
    show_runs.add_argument('environment', help='name of the environment to show the experiments of')
    show_runs.add_argument('--project', '-p', required=False, help='name of the project to show the experiments of')
    show_runs.set_defaults(func=exec_show_runs)


    show_run_result = show_subparsers.add_parser('result', help='show the results of an experiment run')
    show_run_result.add_argument('run', help='uuid of the experiment run to show the results of')
    show_run_result.set_defaults(func=exec_show_run_result)


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
