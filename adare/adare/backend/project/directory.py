# external imports
# configure logging
import logging
import shutil
from pathlib import Path

from adare.backend.directory import Directory
from adare.backend.project.exceptions import (
    ProjectDirectoryCopyError,
    ProjectDirectoryCreationError,
    ProjectDirectoryRemovalError,
)

# internal imports
from adare.config.configdirectory import (
    ADARELIB_DIR,
    ADAREVM_DIR,
    ENVIRONMENTS_DIR,
    VMS_DIR,
)
from adare.helperfunctions.hash import combine_hashes, hash_file_sha256
from adare.helperfunctions.web.download import download

log = logging.getLogger(__name__)


class ProjectDirectory(Directory):
    def __init__(self, path: Path):
        super().__init__(path)

    @property
    def environments(self) -> Path:
        return ENVIRONMENTS_DIR

    @property
    def experiments(self) -> Path:
        return self.path / 'experiments'

    @property
    def testfunctions(self) -> Path:
        return self.path / 'testfunctions'

    @property
    def shared(self) -> Path:
        return self.path / 'shared'

    @property
    def shared_tools(self) -> Path:
        return self.shared / 'tools'

    @property
    def shared_data(self) -> Path:
        return self.shared / 'data'

    @property
    def vm(self) -> Path:
        return VMS_DIR

    @property
    def vm_runtime(self) -> Path:
        return self.path / 'vm_runtime'

    @property
    def run(self) -> Path:
        return self.path / 'run'

    @property
    def adare_config(self) -> Path:
        return self.path / '.adare'

    def create(self):
        try:
            self._create_project_directories()
        except OSError as e:
            raise ProjectDirectoryCreationError(
                log,
                message=f'project directory ({self.path}) creation failed: {e.strerror}',
            ) from e

    def remove(self):
        try:
            shutil.rmtree(self.path)
        except FileNotFoundError or OSError as e:
            raise ProjectDirectoryRemovalError(
                log,
                message=f'project directory ({self.path}) removal failed: {e.strerror}',
            ) from e

    def get_environment_hash(self, environment_file: Path) -> str:
        if not environment_file.relative_to(self.environments):
            raise ValueError(
                f'environment file {environment_file} is not in environments directory {self.environments}')
        return hash_file_sha256(environment_file)

    def get_testfunction_hash(self, testfunction_file: Path, requirements_file: Path) -> str:
        if not testfunction_file.relative_to(self.testfunctions):
            raise ValueError(
                f'testfunction file {testfunction_file} is not in testfunctions directory {self.testfunctions}')
        if not requirements_file.relative_to(self.testfunctions):
            raise ValueError(
                f'requirements file {requirements_file} is not in testfunctions directory {self.testfunctions}')
        return combine_hashes([hash_file_sha256(testfunction_file), hash_file_sha256(requirements_file)])

    def exists(self) -> bool:
        # check if all project paths exist (environments and vm are global, not checked here)
        return all(
            [self.path.exists(), self.experiments.exists(),
             self.shared.exists(), self.vm_runtime.exists(), self.run.exists(), self.adare_config.exists()])

    def _create_project_directories(self):
        self.path.mkdir()
        # environments and vm directories are now global - not created per project
        self.experiments.mkdir()
        # Testfunctions are now global - no need for project-specific directory
        self.shared.mkdir()
        self.shared_tools.mkdir()
        self.shared_data.mkdir()
        self.vm_runtime.mkdir()
        self.run.mkdir()
        self.adare_config.mkdir()


    def download_tool(self, url: str, zipped: bool):
        log.info('download tool from url into shared tools directory')
        file = self.shared_tools / Path(url).name
        if file.exists():
            log.info('tool already exists in shared tools directory')
            return
        download(url, file, quiet=True)
        if zipped:
            log.info('unzip tool')
            shutil.unpack_archive(file, self.shared_tools)
            file.unlink()
        log.info('download of tool was successful')



    def copy_vm_runtime_files(self):
        """Copy adarevm and adarelib to project vm_runtime directory for caching."""
        try:
            from adare.helperfunctions.file.copy import copytree_with_progress

            # Copy adarevm
            if ADAREVM_DIR.exists():
                copytree_with_progress(
                    src=ADAREVM_DIR,
                    dst=self.vm_runtime / 'adarevm',
                    preserve_metadata=True,
                    dirs_exist_ok=True,
                )
                log.info('copied adarevm to project vm_runtime')
            else:
                log.warning(f'adarevm directory not found at {ADAREVM_DIR}')

            # Copy adarelib
            if ADARELIB_DIR.exists():
                copytree_with_progress(
                    src=ADARELIB_DIR,
                    dst=self.vm_runtime / 'adarelib',
                    preserve_metadata=True,
                    dirs_exist_ok=True,
                )
                log.info('copied adarelib to project vm_runtime')
            else:
                log.warning(f'adarelib directory not found at {ADARELIB_DIR}')

        except OSError as e:
            raise ProjectDirectoryCopyError(
                log,
                message=f'VM runtime files could not be copied to project directory ({self.vm_runtime}): {e.strerror}',
            ) from e
