import shutil
from pathlib import Path
import os
import platform


def __get_default_appdata_directory(create_if_missing: bool = False, program_name: str = 'adare') -> Path | None:
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

IGNORE_PATTERNS = [
    'venv',
    'build',
    '.idea',
    '*.egg-info',
    '__pycache__',
    '*.pyc',
    '.git',
    'uv.lock',
]


if __name__ == '__main__':

    adare = Path('../')

    # copy all files and folders from appdata_local to appdata_dir with progress bar and actual file that is copied
    # (if a file or directory already exists, it will be overwritten)
    shutil.copytree(adare, APPDATA_DIR / 'adare', dirs_exist_ok=True, ignore=shutil.ignore_patterns(*IGNORE_PATTERNS))

    # move all files from adare/adare/appdata to appdata root (except testfunctions)
    for file in (APPDATA_DIR / 'adare' / 'adare' / 'appdata').iterdir():
        if file.name != 'testfunctions':  # Skip testfunctions - we'll load directly from source
            shutil.copytree(file, APPDATA_DIR / file.name, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns(*IGNORE_PATTERNS))
