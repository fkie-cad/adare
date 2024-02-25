# external imports
from pathlib import Path
import shutil
import jinja2

# internal imports
from adare.config.configdirectory import TEMPLATES_DIR
from adarelib.helperfunctions.hash import hash_file_sha256, combine_hashes
from adarelib.types import ExperimentMetadata, TestsetFile
from adare.backend.experiment.exceptions import ExperimentFileCreationError, ExperimentDirectoryCreationError, \
    ExperimentRemovalError
from adarelib.parsers import parse_metadata_file, parse_testsetfile

# configure logging
import logging
log = logging.getLogger(__name__)


class ExperimentDirectory:
    path: Path
    img_path: Path
    actionfile: Path
    testsetfile: Path
    metadatafile: Path
    bibtextfile: Path
    markdownfile: Path

    experiment: str

    def __init__(self, project: Path, experiment: str):
        self.experiment = experiment
        self.path = project / 'experiments' / experiment
        self.img_path = self.path / 'img'
        self.actionfile = self.path / 'action.py'
        self.testsetfile = self.path / 'testset.yml'
        self.metadatafile = self.path / 'metadata.yml'
        self.bibtextfile = self.path / 'bibtext.bib'
        self.markdownfile = self.path / 'details.md'

    def __create_experiment_files(self):
        actionfile_template = TEMPLATES_DIR / 'experiment' / 'action.py'
        testsetfile_template = TEMPLATES_DIR / 'experiment' / 'testset.yml'
        metadatafile_template = TEMPLATES_DIR / 'experiment' / 'metadata.yml'

        try:
            with open(self.actionfile, 'w') as f:
                f.write(jinja2.Template(actionfile_template.read_text()).render(
                    name=f'{self.experiment.capitalize()}',
                ))
        except OSError as e:
            raise ExperimentFileCreationError('action', self.actionfile, e.strerror) from e
        try:
            with open(self.testsetfile, 'w') as f:
                f.write(jinja2.Template(testsetfile_template.read_text()).render(
                    name=f'{self.experiment}',
                ))
        except OSError as e:
            raise ExperimentFileCreationError('testset', self.testsetfile, e.strerror) from e
        try:
            with open(self.metadatafile, 'w') as f:
                f.write(jinja2.Template(metadatafile_template.read_text()).render(experiment=self.experiment))
        except OSError as e:
            raise ExperimentFileCreationError('metadata', self.metadatafile, e.strerror) from e

    def create(self):
        try:
            self.path.mkdir()
            self.img_path.mkdir()
        except OSError as e:
            raise ExperimentDirectoryCreationError(self.path, e.strerror) from e
        self.__create_experiment_files()

    def remove(self) -> bool:
        try:
            shutil.rmtree(self.path)
        except FileNotFoundError or OSError as e:
            raise ExperimentRemovalError(self.path, e.strerror) from e
        return True

    def exists(self) -> bool:
        return bool(
            self.actionfile.exists()
            and self.testsetfile.exists()
            and self.metadatafile.exists()
        )

    def load_metadata(self) -> ExperimentMetadata:
        return parse_metadata_file(self.metadatafile)

    def load_testset(self) -> TestsetFile:
        return parse_testsetfile(self.testsetfile)

    @property
    def action_sha256(self) -> str:
        return hash_file_sha256(self.actionfile)

    @property
    def testset_sha256(self) -> str:
        return hash_file_sha256(self.testsetfile)

    @property
    def metadata_sha256(self) -> str:
        return hash_file_sha256(self.metadatafile)

    @property
    def bibtext_sha256(self) -> str:
        return hash_file_sha256(self.bibtextfile) if self.bibtextfile.exists() else ''

    @property
    def markdown_sha256(self) -> str:
        return hash_file_sha256(self.markdownfile) if self.markdownfile.exists() else ''

    @property
    def sha256(self) -> str:
        return combine_hashes([
            self.action_sha256,
            self.testset_sha256,
            self.metadata_sha256,
        ])
