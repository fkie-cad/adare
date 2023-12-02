# external imports
from pathlib import Path
import cattrs

# internal imports
from adare.helperFunctions.yaml import yaml_to_dict
from adare.backend.attrs_classes import EnvironmentSetup

# setup logging
import logging
log = logging.getLogger(__name__)


def load_setupfile(setup_file: Path) -> EnvironmentSetup or None:
    """
    loads the setup file for the environment
    :param setup_file: path to the setup file
    :return:
    """
    try:
        setup_dict = yaml_to_dict(setup_file)
    except FileNotFoundError:
        log.error(f'setup file {setup_file} for the environment not found')
        return None
    log.debug(f'read setup file ({setup_file}) to dictionary was successful')
    try:
        setup = cattrs.structure(setup_dict, EnvironmentSetup)
    except cattrs.BaseValidationError as e:
        log.error(f'parsing errors while parsing environment setup file {setup_file}:')
        exec_msgs = cattrs.transform_error(e)
        for msg in exec_msgs:
            log.error(msg)
        return None
    log.debug(f'environment setup file {setup_file} got successfully parsed')
    return setup