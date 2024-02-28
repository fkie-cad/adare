# external imports
from pathlib import Path
import shutil

# internal imports

# configure logging
import logging
log = logging.getLogger(__name__)


class Directory:
    path: Path

    def __init__(self, path: Path):
        self.path = path

    def get_path_relative_to_shared_directory(self, variable: str, shared_directory_host: Path, shared_directory_vm: Path) -> Path:
        try:
            var: Path = getattr(self, variable)
        except AttributeError as e:
            raise AttributeError(
                f'Variable {variable} does not exist in {self.__class__.__name__}'
            ) from e
        relative_path = var.relative_to(shared_directory_host)
        return shared_directory_vm / relative_path

    def clean(self):
        shutil.rmtree(self.path)




