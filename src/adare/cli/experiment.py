# internal imports
from adare.backend.basics import determine_projectdirectory
from adare.backend.project import Project
from adare.backend.environment import Environment

# configure logging
import logging
log = logging.getLogger(__name__)



def exec_exp_run(arguments):
    """
    run the provided experiment in the given environment

    :param arguments: arguments parsed via input
    """

    # determine the project directory
    project_directory = determine_projectdirectory(arguments.project)

    # load the environment
    env = Environment(arguments.environment, project_directory)

    env.run(arguments.experiment, arguments.debugmode)


def exec_exp_create(arguments):
    """
    create experiment skeleton files [input file, gui experiment file] (in order to write your own experiment)

    :param arguments:  arguments parsed via input
    """
    # determine the project directory
    project_directory = determine_projectdirectory(arguments.project)
    if not project_directory:
        log.error('no project directory found')
        exit(1)

    # smb_drives, nfs_drives = [], []
    # if arguments.networkdrive:
    #     log.info('network drive provided')
    #     smb_drives, nfs_drives = load_networkdrive_setupfile(arguments.networkdrive)
    #
    #
    # usb = None
    # if arguments.usb:
    #     log.info('usb provided')
    #     usb = load_usb_setupfile(arguments.usb)

    # load the environment
    env = Environment(arguments.environment, project_directory)
    env.create_experiment(arguments.experiment)


def exec_exp_remove(arguments):
    """
    remove experiment skeleton files [input file, gui experiment file] (in order to write your own experiment)

    :param arguments:  arguments parsed via input
    """
    # determine the project directory
    project_directory = determine_projectdirectory(arguments.project)
    if not project_directory:
        log.error('no project directory found')
        exit(1)

    # load the environment
    env = Environment(arguments.environment, project_directory)
    env.remove_experiment(arguments.experiment)