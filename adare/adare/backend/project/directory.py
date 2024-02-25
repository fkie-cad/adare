# external imports
from pathlib import Path
import shutil

# internal imports
from adare.config.configdirectory import ADARE_DIR, APPDATA_DIR
from adarelib.helperfunctions.web.download import download
from adare.backend.project.exceptions import ProjectDirectoryCreationError, ProjectDirectoryRemovalError, ProjectDirectoryCopyError


# configure logging
import logging
log = logging.getLogger(__name__)


class ProjectDirectory:
    path: Path
    tessdata: Path
    environments: Path
    experiments: Path
    testfunctions: Path
    shared: Path
    shared_tools: Path
    shared_data: Path
    adare: Path
    run: Path

    def __init__(self, path: Path):
        self.path = path
        self.environments = path / 'environments'
        self.experiments = path / 'experiments'
        self.testfunctions = path / 'testfunctions'
        self.shared = path / 'shared'
        self.shared_tools = self.shared / 'tools'
        self.shared_data = self.shared / 'data'
        self.adare = path / 'adare'
        self.tessdata = path / '.tessdata'
        self.run = path / '.run'

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

    def exists(self) -> bool:
        # check if all paths exist
        return all(
            [self.path.exists(), self.environments.exists(), self.experiments.exists(), self.testfunctions.exists(),
             self.shared.exists(), self.adare.exists(), self.tessdata.exists(), self.run.exists()])

    def _create_project_directories(self):
        self.path.mkdir()
        self.environments.mkdir()
        self.experiments.mkdir()
        self.testfunctions.mkdir()
        self.shared.mkdir()
        self.adare.mkdir()
        self.tessdata.mkdir()
        self.run.mkdir()

    def download_tessdata(self, abbreviation: str):
        log.info('download tessdata training data for text recognition in gui automation')
        tessdata_github_link = fr'https://github.com/tesseract-ocr/tessdata/blob/main/{abbreviation}.traineddata?raw=true'
        tessdata_file = self.tessdata / f'{abbreviation}.traineddata'
        if tessdata_file.exists():
            log.info(
                'tessdata training data for text recognition in gui automation already exists in project directory'
            )
            return
        download(tessdata_github_link, tessdata_file, quiet=True)
        log.info('download of tessdata training data for text recognition in gui automation was successful')

    def copy_adare_to_adare_dir(self):
        try:
            shutil.copytree(ADARE_DIR.as_posix(), self.adare, dirs_exist_ok=True, ignore=shutil.ignore_patterns('*.pyc', '__pycache__'))
        except OSError as e:
            raise ProjectDirectoryCopyError(
                log,
                message=f'adare directory ([i]{ADARE_DIR}[/i]) could not be copied to project directory ({self.adare}): {e.strerror}',
            ) from e

    def copy_standard_testfunction(self):
        try:
            shutil.copy(APPDATA_DIR/'testfunctions'/'standard.py', self.testfunctions/'standard.py')
        except OSError as e:
            raise ProjectDirectoryCopyError(
                log,
                message=f'standard testfunction ([i]{APPDATA_DIR/"testfunctions"/"standard.py"}[/i]) could not be copied to project directory ({self.testfunctions}): {e.strerror}',
            ) from e

