# external imports
from pathlib import Path
import shutil
import jinja2
from datetime import datetime, timezone
import attrs

# internal imports
from adare.config.configdirectory import TEMPLATES_DIR
from adarelib.helperfunctions.hash import hash_file_sha256, combine_hashes, hash_dict_sha256
from adarelib.types.backend import ExperimentMetadata
from adarelib.types.testset import TestsetFile
from adare.backend.experiment.exceptions import ExperimentFileCreationError, ExperimentDirectoryCreationError, \
    ExperimentRemovalError, ExperimentFileMissingError
from adarelib.parsers import parse_metadata_file, parse_testsetfile
from adare.backend.project.directory import ProjectDirectory
from adare.backend.directory import Directory
from adarelib.experimentconfig import ExperimentConfig
from adarelib.helperfunctions.yaml import dict_to_yaml

# configure logging
import logging

log = logging.getLogger(__name__)


class ExperimentRunDirectory(Directory):
    path: Path
    log_directory: Path
    vagrant_log_file: Path
    adarevm_log_file: Path

    def __init__(self, project_directory: ProjectDirectory, experiment: str):
        super().__init__(project_directory.run / experiment / datetime.now(timezone.utc).strftime('%Y-%m-%d_%H-%M-%S'))
        self.log_directory = self.path / 'logs'
        self.vagrant_log_file = self.log_directory / 'vagrant.log'
        self.adarevm_log_file = self.log_directory / 'adarevm.log'


    def create(self):
        self.path.parent.mkdir(parents=False, exist_ok=True)
        self.path.mkdir(parents=False)
        self.log_directory.mkdir(parents=False)


    def clean(self):
        # todo: implement clean method (think what needs to be cleaned)
        pass


class ExperimentDirectory(Directory):
    path: Path
    img: Path
    actionfile: Path
    testsetfile: Path
    metadatafile: Path
    bibtexfile: Path
    markdownfile: Path

    experiment: str

    def __init__(self, project: Path, experiment: str):
        self.experiment = experiment
        super().__init__(project / 'experiments' / experiment)
        self.img = self.path / 'img'
        self.actionfile = self.path / 'action.py'
        self.testsetfile = self.path / 'testset.yml'
        self.metadatafile = self.path / 'metadata.yml'
        self.bibtexfile = self.path / 'bibtext.bib'
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
            raise ExperimentFileCreationError(
                log,
                message=f'Failed to create action file for experiment {self.experiment}: {e.strerror}'
            ) from e

        try:
            with open(self.testsetfile, 'w') as f:
                f.write(jinja2.Template(testsetfile_template.read_text()).render(
                    name=f'{self.experiment}',
                ))
        except OSError as e:
            raise ExperimentFileCreationError(
                log,
                message=f'Failed to create testset file for experiment {self.experiment}: {e.strerror}'
            ) from e
        try:
            with open(self.metadatafile, 'w') as f:
                f.write(jinja2.Template(metadatafile_template.read_text()).render(experiment=self.experiment))
        except OSError as e:
            raise ExperimentFileCreationError(
                log,
                message=f'Failed to create metadata file for experiment {self.experiment}: {e.strerror}'
            ) from e

    def create(self):
        try:
            self.path.mkdir()
            self.img.mkdir()
        except OSError as e:
            raise ExperimentDirectoryCreationError(
                log,
                message=f'Failed to create experiment directory {self.path}: {e.strerror}'
            ) from e
        self.__create_experiment_files()

    def remove(self) -> bool:
        try:
            shutil.rmtree(self.path)
        except FileNotFoundError or OSError as e:
            raise ExperimentRemovalError(
                log,
                message=f'Failed to remove experiment directory {self.path}: {e.strerror}'
            ) from e
        return True

    def exists(self) -> bool:
        return self.path.exists()

    def check_for_missing_files(self):
        if missing_files := [
            f.name
            for f in [self.actionfile, self.testsetfile, self.metadatafile]
            if not f.exists()
        ]:
            missing_files_str = ','.join(missing_files)
            raise ExperimentFileMissingError(
                log,
                f'experiment [b]{self.path.name}[/b] is missing the following files: {missing_files_str}',
            )

    def load_metadata(self) -> ExperimentMetadata:
        return parse_metadata_file(self.metadatafile)

    def load_testset(self) -> TestsetFile:
        return parse_testsetfile(self.testsetfile)

    @property
    def sha256_action(self) -> str:
        return hash_file_sha256(self.actionfile)

    @property
    def sha256_testset(self) -> str:
        return hash_file_sha256(self.testsetfile)

    @property
    def sha256_metadata(self) -> str:
        return hash_file_sha256(self.metadatafile)

    @property
    def sha256_bibtex(self) -> str:
        return hash_file_sha256(self.bibtexfile) if self.bibtexfile.exists() else ''

    @property
    def sha256_markdown(self) -> str:
        return hash_file_sha256(self.markdownfile) if self.markdownfile.exists() else ''

    @property
    def sha256(self) -> str:
        return combine_hashes([
            self.sha256_action,
            self.sha256_testset,
        ])
