# external imports

# internal imports
from adare.backend.basics import determine_projectdirectory
from adare.backend.project import Project

# configure logging
import logging
log = logging.getLogger(__name__)


# # todo: find a way how to clean up virtualbox vms, vagrant boxes, files, ...
# def handler(signum, frame):
#     msg = "Ctrl-c was pressed. Do you really want to exit? y/n "
#     print(msg, end="", flush=True)
#     res = readchar.readchar()
#     if res == 'y':
#         print("")
#         exit(1)
#     else:
#         print("", end="\r", flush=True)
#         print(" " * len(msg), end="", flush=True)  # clear the printed line
#         print("    ", end="\r", flush=True)


def env_create(arguments):
    """
    creates a new environment

    :param arguments: arguments parsed via input
    """
    project_directory = determine_projectdirectory(arguments.project)
    project = Project(project_directory)
    project.add_environment(arguments.conf, name=arguments.name)


def env_list(arguments):
    """
    shows the information about environments of a project

    :param arguments: arguments parsed via input
    """
    show_details = False
    if arguments.details:
        show_details = True

    project_directory = determine_projectdirectory(arguments.project)
    project = Project(project_directory)
    project.list_environments(details=show_details)


def env_run(arguments):
    """
    run the provided scenario in the given environment

    :param arguments: arguments parsed via input
    """
    # todo: implement to run multiple scenarios or one scenario multiple times
    # todo: check if env name existing and if its correct?

    project_directory = determine_projectdirectory(arguments.project)
    # function_description = f'''
    #     run the scenario {arguments.name} in the environment {arguments.name}
    #     (which itself can be found in the project directory with path {project_directory})
    # '''
    # log.info(function_description)

    project = Project(project_directory)
    project.run_scenario(arguments.name, arguments.scenario, arguments.debugmode)


def env_remove(arguments):
    """
    removes the chosen environment

    :param arguments: arguments parsed via input
    """
    project_directory = determine_projectdirectory(arguments.project)
    project = Project(project_directory)
    project.remove_environment(arguments.name)


def env_create_scenario(arguments):
    """
    create scenario skeleton files [input file, gui scenario file] (in order to write your own scenario)

    :param arguments:  arguments parsed via input
    """
    project_directory = determine_projectdirectory(arguments.project)
    project = Project(project_directory)
    project.create_scenario(arguments.name, arguments.scenario, networkdrive=arguments.networkdrive, usb=arguments.usb)


def env_remove_scenario(arguments):
    """
    remove scenario skeleton files [input file, gui scenario file] (in order to write your own scenario)

    :param arguments:  arguments parsed via input
    """
    project_directory = determine_projectdirectory(arguments.project)
    project = Project(project_directory)
    project.remove_scenario(arguments.name, arguments.scenario)


def env_addusb(arguments):
    """
    adds a usb device to an environment

    :param arguments: arguments parsed via input
    :return:
    """
    project_directory = determine_projectdirectory(arguments.project)
    project = Project(project_directory)
    project.add_usb_to_environment(arguments.name, arguments.details)


def env_addnetworkdrive(arguments):
    """
    adds a network drive to an environment

    :param arguments: arguments parsed via input
    :return:
    """
    project_directory = determine_projectdirectory(arguments.project)
    project = Project(project_directory)
    project.add_networkdrive_to_environment(arguments.name, arguments.details)


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
