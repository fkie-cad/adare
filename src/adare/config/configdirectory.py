# external imports
from pathlib import Path
import platform
import os

# internal imports
from . import NAME

# configure logging
import logging
log = logging.getLogger(__name__)


def get_default_config_directory(create_if_missing: bool = False, program_name: str = NAME) -> Path or None:
    system = platform.system()
    if system == 'Windows':
        config_path = Path(os.getenv('APPDATA'))
    elif system == "Linux":
        config_path = Path('~/.config/')
    else:
        log.fatal(f'the os {system} is not supported by the tool')
        return None
    if config_path:
        config_path = config_path/program_name
        if create_if_missing:
            config_path.mkdir(parents=False, exist_ok=True)
    if not config_path.is_dir():
        log.error(f'the config directory ({config_path}) of the tool is missing')
        return None
    return config_path
