# external imports
import argparse
import sys
import ast
import time

# internal imports
from adare.cli.environment import env_create, env_list, env_run, env_remove, env_create_scenario, \
    env_remove_scenario, env_addusb, env_addnetworkdrive
from adare.cli.project import project_create, project_remove
from adare.cli.webapp import webapp
# from adare.cli.vagrant import vgbox_add, vgbox_list, vgbox_remove
from adare.setup_logging import setup_logging

def run():
    # function()
    start_time = time.time()

    parser = argparse.ArgumentParser()
    parser.add_argument('--logfile')
    parser.add_argument('--loglevelfile')
    parser.add_argument('--loglevelconsole')
    parser.add_argument('--logdetailsconsole', type=bool, default=False)
    parser.set_defaults(func=lambda args: parser.print_help())

    subparsers = parser.add_subparsers()

    project = subparsers.add_parser('proj')
    project.set_defaults(func=lambda args: project.print_help())

    project_subparsers = project.add_subparsers()

    sp_project_create = project_subparsers.add_parser('create')
    sp_project_create.add_argument('directory')
    sp_project_create.set_defaults(func=project_create)

    sp_project_remove = project_subparsers.add_parser('remove')
    sp_project_remove.add_argument('directory')
    sp_project_remove.set_defaults(func=project_remove)

    # sp_project_replaceprog = project_subparsers.add_parser('replaceprog')
    # sp_project_replaceprog.add_argument('--project')
    # sp_project_replaceprog.add_argument('path')
    # sp_project_replaceprog.set_defaults(func=project_replaceprog)

    vgbox = subparsers.add_parser('vgbox')
    vgbox.set_defaults(func=lambda args: vgbox.print_help())

    sp_webapi = subparsers.add_parser('webapp')
    sp_webapi.add_argument('-p', '--port', type=int, required=False)
    # sp_webapi.add_argument('--host', type=str, required=False)
    sp_webapi.set_defaults(func=webapp)

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

    env = subparsers.add_parser('env')
    env.add_argument('--project')
    env.set_defaults(func=lambda args: env.print_help())

    env_subparsers = env.add_subparsers()

    sp_env_create = env_subparsers.add_parser('create')
    sp_env_create.add_argument('conf')
    sp_env_create.add_argument('--name')
    sp_env_create.set_defaults(func=env_create)

    sp_env_list = env_subparsers.add_parser('list')
    sp_env_list.add_argument('--details', '-d', action='store_true')
    sp_env_list.set_defaults(func=env_list)

    sp_env_run = env_subparsers.add_parser('run')
    sp_env_run.add_argument('name')
    sp_env_run.add_argument('scenario')
    sp_env_run.add_argument('--debugmode', action='store_true')
    sp_env_run.set_defaults(func=env_run)

    sp_env_remove = env_subparsers.add_parser('remove')
    sp_env_remove.add_argument('name')
    sp_env_remove.set_defaults(func=env_remove)

    sp_env_addguiscenario = env_subparsers.add_parser('createscenario')
    sp_env_addguiscenario.add_argument('name')
    sp_env_addguiscenario.add_argument('scenario')
    sp_env_addguiscenario.add_argument('--networkdrive')
    sp_env_addguiscenario.add_argument('--usb')
    # sp_env_addguiscenario.add_argument('--category', '-c')
    sp_env_addguiscenario.set_defaults(func=env_create_scenario)

    sp_env_addusb = env_subparsers.add_parser('addusb')
    sp_env_addusb.add_argument('name')
    sp_env_addusb.add_argument('details', type=ast.literal_eval)
    sp_env_addusb.set_defaults(func=env_addusb)

    sp_env_addnetworkdrive = env_subparsers.add_parser('addnetworkdrive')
    sp_env_addnetworkdrive.add_argument('name')
    sp_env_addnetworkdrive.add_argument('details', type=ast.literal_eval)
    sp_env_addnetworkdrive.set_defaults(func=env_addnetworkdrive)

    sp_env_removeguiscenario = env_subparsers.add_parser('removescenario')
    sp_env_removeguiscenario.add_argument('name')
    sp_env_removeguiscenario.add_argument('scenario')
    # sp_env_addguiscenario.add_argument('--category', '-c')
    sp_env_removeguiscenario.set_defaults(func=env_remove_scenario)

    # sp_env_addinput = env_subparsers.add_parser('addinput')
    # sp_env_addinput.add_argument('name')
    # sp_env_addinput.add_argument('input')
    # sp_env_addinput.set_defaults(func=env_add_inputfiles)

    args = parser.parse_args()

    # setup logging
    setup_logging(args, sys.argv)

    # configure logging
    import logging
    log = logging.getLogger(__name__)

    args.func(args)

    log.debug(f"---  Runtime {(time.time() - start_time) / 60} minutes ---")
    logging.shutdown()

