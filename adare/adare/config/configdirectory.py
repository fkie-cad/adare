# external imports
from pathlib import Path
import platform
import os

# internal imports
from . import NAME

# configure logging
import logging
log = logging.getLogger(__name__)


def __get_default_appdata_directory(create_if_missing: bool = False, program_name: str = 'adare') -> Path or None:
    """
    get the default config directory for the tool

    :param create_if_missing: if True, the directory will be created if it does not exist
    :param program_name: the name of the program
    :return:
    """
    system = platform.system()
    if system == 'Windows':
        appdata_path = Path(os.getenv('APPDATA'))
        appdata_path = appdata_path / program_name.lower()
    elif system == "Linux":
        appdata_path = Path(f'~/.{program_name.lower()}/').expanduser()
        if not appdata_path.exists():
            appdata_path.mkdir(parents=False)
    else:
        print(f'the os {system} is not supported by the tool')
        return None
    if create_if_missing:
        appdata_path.mkdir(parents=False, exist_ok=True)
    if not appdata_path.is_dir():
        print(f'the appdata directory ({appdata_path}) of the tool is missing')
        return None
    return appdata_path


APPDATA_DIR: Path = __get_default_appdata_directory(create_if_missing=True)
ADARE_DIR = APPDATA_DIR/'adare'
WEBAPP_FILES: Path = APPDATA_DIR/'webapp'
WEBAPP_STATIC_FILES: Path = WEBAPP_FILES/'static'

EXAMPLES_DIR: Path = APPDATA_DIR/'examples'
PROGRAMS_DIR: Path = APPDATA_DIR/'programs'
PROG_PARSEANDTEST_DIR: Path = PROGRAMS_DIR/'ParseAndTest'

TEMPLATES_DIR: Path = APPDATA_DIR/'templates'
NETWORKDRIVE_TEMPLATES_DIR: Path = APPDATA_DIR/'networkdrive'/'templates'
VAGRANTFILE_TEMPLATE: Path = APPDATA_DIR/'VagrantfileTemplate'/'VagrantfileMultiMachine'

