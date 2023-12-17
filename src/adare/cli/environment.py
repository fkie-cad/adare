# internal imports
from adare.backend.basics import determine_projectdirectory
from adare.backend.project import Project
from adare.backend.environment import Environment

# configure logging
import logging
log = logging.getLogger(__name__)


def exec_env_create(arguments):
    """
    creates a new environment

    :param arguments: arguments parsed via input
    """
    project_directory = determine_projectdirectory(arguments.project)
    project = Project(project_directory)
    project.add_environment(arguments.config, name=arguments.name)


def exec_env_remove(arguments):
    """
    removes the chosen environment

    :param arguments: arguments parsed via input
    """
    # determine the project directory
    project_directory = determine_projectdirectory(arguments.project)
    if not project_directory:
        log.error('no project directory found')
        exit(1)

    # load the environment
    env = Environment(arguments.environment, project_directory)
    env.remove()



# def exec_env_addusb(arguments):
#     """
#     adds a usb device to an environment
#
#     :param arguments: arguments parsed via input
#     :return:
#     """
#     project_directory = determine_projectdirectory(arguments.project)
#     project = Project(project_directory)
#     project.add_usb_to_environment(arguments.name, arguments.details)
#
#
# def exec_env_addnetworkdrive(arguments):
#     """
#     adds a network drive to an environment
#
#     :param arguments: arguments parsed via input
#     :return:
#     """
#     project_directory = determine_projectdirectory(arguments.project)
#     project = Project(project_directory)
#     project.add_networkdrive_to_environment(arguments.name, arguments.details)


# def env_add_inputfiles(arguments):
#     """
#     add a input files provided in a file or directory to an environment
#
#     :param arguments:  arguments parsed via input
#     """
#     project_directory = determine_projectdirectory(arguments.project)
#     project = Project(project_directory)
#     project.add_input_to_environment(arguments.name, arguments.input)

# # todo: test if it works properly
# def env_remove_input(arguments):
#     """
#     remove input file provided from an environment
#
#     :param arguments:  arguments parsed via input
#     """
#     project_directory = determine_projectdirectory(arguments.project)
#     project = Project(project_directory)
#     project.remove_input_from_environment(arguments.name, arguments.input)
