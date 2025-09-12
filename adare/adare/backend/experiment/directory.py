# external imports
from pathlib import Path
import shutil
import jinja2
from datetime import datetime, timezone
import cattrs


# internal imports
from adarelib.testset.type import TestsetFile
from adare.config.configdirectory import TEMPLATES_DIR, EXAMPLES_DIR
import adare
from adare.helperfunctions.hash import hash_file_sha256, combine_hashes
from adare.types.experiment import ExperimentMetadata
from adare.backend.experiment.exceptions import ExperimentFileCreationError, ExperimentDirectoryCreationError, \
    ExperimentRemovalError, ExperimentFileMissingError
from adare.parsers import parse_metadata_file
from adare.backend.project.directory import ProjectDirectory
from adare.backend.directory import Directory
from adare.exceptions import DataStructuringError

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
        self.mcp_gui_log_file = self.log_directory / 'mcp_gui.log'
        self.experiment_debug_log_file = self.log_directory / 'experiment_debug.log'
        self.screenshots_directory = self.path / 'screenshots'


    def create(self):
        self.path.parent.mkdir(parents=False, exist_ok=True)
        self.path.mkdir(parents=False)
        self.log_directory.mkdir(parents=False)
        self.screenshots_directory.mkdir(parents=False, exist_ok=True)


    def clean(self):
        # todo: implement clean method (think what needs to be cleaned)
        pass


class ExperimentDirectory(Directory):
    path: Path
    img: Path
    playbookfile: Path
    metadatafile: Path
    bibtexfile: Path
    markdownfile: Path
    shared: Path
    shared_tools: Path
    shared_data: Path

    experiment: str

    def __init__(self, project: Path, experiment: str):
        self.experiment = experiment
        super().__init__(project / 'experiments' / experiment)
        self.img = self.path / 'img'
        self.shared = self.path / 'shared'
        self.shared_tools = self.shared / 'tools'
        self.shared_data = self.shared / 'data'
        self.playbookfile = self.path / 'playbook.yml'
        self.metadatafile = self.path / 'metadata.yml'
        self.bibtexfile = self.path / 'bibtext.bib'
        self.markdownfile = self.path / 'details.md'

    def __create_experiment_files(self):
        # Use YAML-first templates from package directory
        package_templates_dir = Path(adare.__file__).parent.parent / 'appdata' / 'templates'
        playbookfile_template = package_templates_dir / 'experiment' / 'playbook.yml'
        metadatafile_template = package_templates_dir / 'experiment' / 'metadata.yml'

        # Testset configuration is now integrated into playbook.yml
        # No separate testset file needed anymore

        # Create YAML playbook file (now contains integrated tests)
        try:
            with open(self.playbookfile, 'w') as f:
                f.write(jinja2.Template(playbookfile_template.read_text()).render(
                    name=f'{self.experiment}',
                ))
        except OSError as e:
            raise ExperimentFileCreationError(
                log,
                message=f'Failed to create playbook file for experiment {self.experiment}: {e.strerror}'
            ) from e

        # Create metadata
        try:
            with open(self.metadatafile, 'w') as f:
                f.write(jinja2.Template(metadatafile_template.read_text()).render(experiment=self.experiment))
        except OSError as e:
            raise ExperimentFileCreationError(
                log,
                message=f'Failed to create metadata file for experiment {self.experiment}: {e.strerror}'
            ) from e

    def create(self, empty: bool = False):
        try:
            self.path.mkdir(parents=True, exist_ok=True)
            self.img.mkdir(exist_ok=True)
            self.shared.mkdir(exist_ok=True)
            self.shared_tools.mkdir(exist_ok=True)
            self.shared_data.mkdir(exist_ok=True)
        except OSError as e:
            raise ExperimentDirectoryCreationError(
                log,
                message=f'Failed to create experiment directory {self.path}: {e.strerror}'
            ) from e
        
        if not empty:
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
            for f in [self.metadatafile]
            if not f.exists()
        ]:
            missing_files_str = ','.join(missing_files)
            raise ExperimentFileMissingError(
                log,
                f'experiment [b]{self.path.name}[/b] is missing the following files: {missing_files_str}',
            )

    def retrieve_example(self, experiment: str):
        example_dir = EXAMPLES_DIR/'experiments'/experiment
        shutil.copytree(example_dir, self.path)

    def load_metadata(self) -> ExperimentMetadata:
        return parse_metadata_file(self.metadatafile)

    def load_testset(self) -> TestsetFile:
        # Load tests from playbook instead of separate testset file
        from adare.types.playbook import parse_playbook
        from adarelib.testset.type import TestsetFile
        
        # Use default auto-detection for OS and user since we don't have context here
        playbook = parse_playbook(self.playbookfile)
        
        # Return TestsetFile constructed from playbook tests
        return TestsetFile(name=self.experiment, tests=playbook.tests)




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
    def sha256_playbook(self) -> str:
        return hash_file_sha256(self.playbookfile)

    @property
    def sha256(self) -> str:
        # Since testset is now part of playbook, only use playbook hash
        # to avoid double-counting the same content
        return self.sha256_playbook
