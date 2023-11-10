# external imports
from pathlib import Path
import platform
import os

# internal imports
from . import NAME

# configure logging
import logging
log = logging.getLogger(__name__)


def __get_default_appdata_directory(create_if_missing: bool = False, program_name: str = NAME) -> Path or None:
    """
    get the default config directory for the tool

    :param create_if_missing: if True, the directory will be created if it does not exist
    :param program_name: the name of the program
    :return:
    """
    system = platform.system()
    if system == 'Windows':
        appdata_path = Path(os.getenv('APPDATA'))
    elif system == "Linux":
        appdata_path = Path(f'~/.{program_name}/')
    else:
        log.fatal(f'the os {system} is not supported by the tool')
        return None
    if appdata_path:
        appdata_path = appdata_path/program_name
        if create_if_missing:
            appdata_path.mkdir(parents=False, exist_ok=True)
    if not appdata_path.is_dir():
        log.error(f'the appdata directory ({appdata_path}) of the tool is missing')
        return None
    return appdata_path


APPDATA_DIR: Path = __get_default_appdata_directory(create_if_missing=True)
WEBAPP_FILES: Path = APPDATA_DIR/'webapp'
WEBAPP_STATIC_FILES: Path = WEBAPP_FILES/'static'

EXAMPLES_DIR: Path = APPDATA_DIR/'examples'
PROGRAMS_DIR: Path = APPDATA_DIR/'programs'
PROG_PARSEANDTEST_DIR: Path = PROGRAMS_DIR/'ParseAndTest'

TEMPLATES_DIR: Path = APPDATA_DIR/'templates'
NETWORKDRIVE_TEMPLATES_DIR: Path = APPDATA_DIR/'networkdrive'/'templates'
VAGRANTFILE_TEMPLATE: Path = APPDATA_DIR/'VagrantfileTemplate'/'Vagrantfile'
