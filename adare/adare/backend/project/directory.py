# external imports
from pathlib import Path
import shutil

# internal imports
from adare.config.configdirectory import ADARE_DIR, APPDATA_DIR, ADAREVM_DIR, ADARELIB_DIR
from adare.helperfunctions.web.download import download
from adare.backend.project.exceptions import ProjectDirectoryCreationError, ProjectDirectoryRemovalError, ProjectDirectoryCopyError
from adare.backend.directory import Directory
from adare.helperfunctions.hash import hash_file_sha256, combine_hashes

# configure logging
import logging
log = logging.getLogger(__name__)


class ProjectDirectory(Directory):
    def __init__(self, path: Path):
        super().__init__(path)

    @property
    def environments(self) -> Path:
        return self.path / 'environments'

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
        return self.path / 'vm'

    @property
    def vm_runtime(self) -> Path:
        return self.path / 'vm_runtime'

    @property
    def run(self) -> Path:
        return self.path / 'run'

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
        # check if all paths exist
        return all(
            [self.path.exists(), self.environments.exists(), self.experiments.exists(), self.testfunctions.exists(),
             self.shared.exists(), self.vm.exists(), self.vm_runtime.exists(), self.run.exists()])

    def _create_project_directories(self):
        self.path.mkdir()
        self.environments.mkdir()
        self.experiments.mkdir()
        self.testfunctions.mkdir()
        self.shared.mkdir()
        self.shared_tools.mkdir()
        self.shared_data.mkdir()
        self.vm.mkdir()
        self.vm_runtime.mkdir()
        self.run.mkdir()


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


    def copy_all_testfunctions(self):
        try:
            from adare.helperfunctions.file.copy import copytree_with_progress
            appdata_testfunctions = APPDATA_DIR / 'testfunctions'

            # Copy all testfunction directories from appdata to project
            for testfunction_dir in appdata_testfunctions.iterdir():
                if testfunction_dir.is_dir():
                    copytree_with_progress(
                        src=testfunction_dir,
                        dst=self.testfunctions / testfunction_dir.name,
                        preserve_metadata=True,
                        dirs_exist_ok=True,
                    )
                    log.info(f'copied testfunction set: {testfunction_dir.name}')

        except OSError as e:
            raise ProjectDirectoryCopyError(
                log,
                message=f'testfunctions directory ([i]{APPDATA_DIR/"testfunctions"}[/i]) could not be copied to project directory ({self.testfunctions}): {e.strerror}',
            ) from e

    def copy_standard_testfunction(self):
        # Keep for backward compatibility - redirect to copy_all_testfunctions
        self.copy_all_testfunctions()

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
