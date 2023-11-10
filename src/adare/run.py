# external imports
import argparse
import sys
import time

# internal imports
from adare.cli.environment import exec_run_experiment, exec_env_list, exec_env_create, exec_add_experiment, exec_remove_experiment
from adare.cli.project import exec_create_project, exec_remove_project
from adare.cli.gui import exec_gui
from adare.cli.showversion import exec_show_version
from adare.setup_logging import setup_logging


def run():
    start_time = time.time()

    parser = argparse.ArgumentParser()
    parser.add_argument('-v', '--version', action='store_true', help='display program version')
    parser.add_argument('-l', '--logfile', help='path to logfile')
    parser.add_argument('-llf', '--log-level-file', help='loglevel for logfile')
    parser.add_argument('-llc', '--log-level-console', help='loglevel for console')
    parser.add_argument('-lfc', '--log-format-console', type=bool, default=False, help='log format for logging to console (e.g. %(levelprefix)s %(name)s - %(message)s)')
    parser.set_defaults(func=lambda args: exec_show_version(args, parser))

    subparsers = parser.add_subparsers()

    # commands: adare proj ....
    project = subparsers.add_parser('proj', help='wrapper for needed project commands')
    project.set_defaults(func=lambda args: project.print_help())
    project_subparsers = project.add_subparsers()

    project_create = project_subparsers.add_parser('create')
    project_create.add_argument('directory')
    project_create.set_defaults(func=exec_create_project)

    project_remove = project_subparsers.add_parser('remove')
    project_remove.add_argument('directory')
    project_remove.set_defaults(func=exec_remove_project)

    # commands: adare env ...
    environment = subparsers.add_parser('env', help='wrapper for needed environment commands')
    environment.set_defaults(func=lambda args: environment.print_help())
    environment_subparsers = environment.add_subparsers()

    environment_create = environment_subparsers.add_parser('create')
    environment_create.add_argument('config', help='path to the environment config file')
    environment_create.add_argument('--name', '-n', required=False, help='name of the environment')
    environment_create.add_argument('--project', '-p', required=False, help='name of the project to add the environment to')
    environment_create.set_defaults(func=exec_env_create)

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

    experiment_remove = experiment_subparsers.add_parser('remove', help='remove the skeleton for an experiment from an environment')
    experiment_remove.add_argument('experiment', help='name of the experimenttestenv_windows10_new to remove')
    experiment_remove.add_argument('--environment', '-env', required=True, help='name of the environment to remove the experiment from')
    experiment_remove.set_defaults(func=exec_remove_experiment)

    # commands: adare show ...
    show = subparsers.add_parser('show', help='wrapper for needed show commands')
    show.set_defaults(func=lambda args: show.print_help())
    show_subparsers = show.add_subparsers()

    show_env = show_subparsers.add_parser('env', help='show the environments of a project')
    show_env.add_argument('--project', '-p', required=False, help='name of the project to show the environments of')
    show_env.add_argument('--details', '-d', action='store_true', help='show details of the environments')
    show_env.set_defaults(func=exec_env_list)

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


    # probably not needed
    # vgbox_subparsers = vgbox.add_subparsers(help='wrapper for needed vagrant commands')
    #
    # sp_vgbox_add = vgbox_subparsers.add_parser('add', help='add a .box image to vagrant')
    # sp_vgbox_add.add_argument('target')
    # sp_vgbox_add.add_argument('name')
    # sp_vgbox_add.set_defaults(func=vgbox_add)
    #
    # sp_vgbox_remove = vgbox_subparsers.add_parser('remove', help='remove a box from vagrant by chosen name')
    # sp_vgbox_remove.add_argument('name')
    # sp_vgbox_remove.set_defaults(func=vgbox_remove)
    #
    # sp_vgbox_list = vgbox_subparsers.add_parser('list', help='list all vagrant boxes available')
    # sp_vgbox_list.set_defaults(func=vgbox_list)

    # env = subparsers.add_parser('env')
    # env.add_argument('--project')
    # env.set_defaults(func=lambda args: env.print_help())
    #
    # env_subparsers = env.add_subparsers()
    #
    # sp_env_create = env_subparsers.add_parser('create')
    # sp_env_create.add_argument('conf')
    # sp_env_create.add_argument('--name')
    # sp_env_create.set_defaults(func=env_create)
    #
    # sp_env_list = env_subparsers.add_parser('list')
    # sp_env_list.add_argument('--details', '-d', action='store_true')
    # sp_env_list.set_defaults(func=env_list)
    #
    # sp_env_run = env_subparsers.add_parser('run')
    # sp_env_run.add_argument('name')
    # sp_env_run.add_argument('experiment')
    # sp_env_run.add_argument('--debugmode', action='store_true')
    # sp_env_run.set_defaults(func=env_run)
    #
    # sp_env_remove = env_subparsers.add_parser('remove')
    # sp_env_remove.add_argument('name')
    # sp_env_remove.set_defaults(func=env_remove)


    # sp_env_addguiexperiment = env_subparsers.add_parser('createexperiment')
    # sp_env_addguiexperiment.add_argument('name')
    # sp_env_addguiexperiment.add_argument('experiment')
    # sp_env_addguiexperiment.add_argument('--networkdrive')
    # sp_env_addguiexperiment.add_argument('--usb')
    # # sp_env_addguiexperiment.add_argument('--category', '-c')
    # sp_env_addguiexperiment.set_defaults(func=env_create_experiment)
    #
    # sp_env_addusb = env_subparsers.add_parser('addusb')
    # sp_env_addusb.add_argument('name')
    # sp_env_addusb.add_argument('details', type=ast.literal_eval)
    # sp_env_addusb.set_defaults(func=env_addusb)
    #
    # sp_env_addnetworkdrive = env_subparsers.add_parser('addnetworkdrive')
    # sp_env_addnetworkdrive.add_argument('name')
    # sp_env_addnetworkdrive.add_argument('details', type=ast.literal_eval)
    # sp_env_addnetworkdrive.set_defaults(func=env_addnetworkdrive)
    #
    # sp_env_removeguiexperiment = env_subparsers.add_parser('removeexperiment')
    # sp_env_removeguiexperiment.add_argument('name')
    # sp_env_removeguiexperiment.add_argument('experiment')
    # # sp_env_addguiexperiment.add_argument('--category', '-c')
    # sp_env_removeguiexperiment.set_defaults(func=env_remove_experiment)

    # sp_env_addinput = env_subparsers.add_parser('addinput')
    # sp_env_addinput.add_argument('name')
    # sp_env_addinput.add_argument('input')
    # sp_env_addinput.set_defaults(func=env_add_inputfiles)


