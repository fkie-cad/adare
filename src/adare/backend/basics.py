# external imports
from pathlib import Path

# internal imports
import adare.config as config
from adare.backend.exceptions import NoProjectFoundException

# configure logging
import logging
log = logging.getLogger(__name__)


def check_if_projectdirectory_is_valid(directory: str):
    """
    check if a given directory is a valid project directory

    :param directory: possible project path

    :return: True: path $directory is a valid project directory
             False: path $directory is NOT a valid project directory
    """
    if directory[-1] == "/":
        directory = directory[:-1]
    if not Path(directory).is_dir():
        log.warning("provided base directory ("+directory+") isn't a directory")
        return False
    necessary_subdirectories = ["programs"]
    missing_subdir = False
    for subdir in necessary_subdirectories:
        if not Path(directory + "/" + subdir).is_dir():
            missing_subdir = True
            log.warning("provided base directory ("+directory+") is missing the necessary folder " + str(subdir))

    if missing_subdir:
        return False

    return True


def determine_projectdirectory(chosen_projectdirectory: str):
    """
    determine the directory of the project

    :param chosen_projectdirectory: path of the project path given by the user

    :return: project path: a valid project path
    """
    tested_project_paths = []
    if chosen_projectdirectory:
        if check_if_projectdirectory_is_valid(chosen_projectdirectory):
            return Path(chosen_projectdirectory).as_posix()
        else:
            log.warning("provided project path (" + str(chosen_projectdirectory) + ") isn't a valid project directory")
        tested_project_paths.append(chosen_projectdirectory)
    else:
        if check_if_projectdirectory_is_valid(config.BASEDIR):
            return Path(config.BASEDIR).as_posix()
        tested_project_paths.append(config.BASEDIR)
    raise NoProjectFoundException(tested_project_paths)
