import shutil
from pathlib import Path
import tqdm

from adare.config.configdirectory import get_default_config_directory

if __name__ == '__main__':
    appdata_dir = get_default_config_directory(create_if_missing=True)

    appdata_local = Path('./appdata')

    # copy all files and folders from appdata_local to appdata_dir with progress bar and actual file that is copied
    # (if a file or directory already exists, it will be overwritten)
    for file in tqdm.tqdm(appdata_local.iterdir(), desc='copying appdata files'):
        shutil.copytree(file, appdata_dir/file.name, dirs_exist_ok=True)