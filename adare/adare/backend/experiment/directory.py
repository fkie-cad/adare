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
    log_directory: Path
    adare_log_file: Path
    adarevm_log_file: Path

    def __init__(self, project_directory: ProjectDirectory, experiment: str):
        super().__init__(project_directory.run / experiment / datetime.now(timezone.utc).strftime('%Y-%m-%d_%H-%M-%S'))
        self.log_directory = self.path / 'logs'
        self.adare_log_file = self.log_directory / 'adare.log'
        self.adarevm_log_file = self.log_directory / 'adarevm.log'
        self.mcp_gui_log_file = self.log_directory / 'mcp_gui.log'
        self.experiment_debug_log_file = self.log_directory / 'experiment_debug.log'
        self.serial_console_log_file = self.log_directory / 'serial_console.log'
        self.qemu_debug_log_file = self.log_directory / 'qemu_debug.log'
        self.system_info_file = self.path / 'system-info.yml'
        self.reporting_directory = self.path / 'reporting'
        self.screenshots_directory = self.reporting_directory / 'screenshots'
        self.forensic_log_file = self.reporting_directory / 'forensic_log.yml'
        self.tmp_directory = self.path / '.tmp'


    def create(self):
        self.path.parent.mkdir(parents=False, exist_ok=True)
        self.path.mkdir(parents=False)
        self.log_directory.mkdir(parents=False)
        self.reporting_directory.mkdir(parents=False, exist_ok=True)
        self.screenshots_directory.mkdir(parents=False, exist_ok=True)
        self.tmp_directory.mkdir(parents=False, exist_ok=True)


    def clean(self):
        """Clean up temporary files and directories after experiment run."""
        try:
            if self.tmp_directory.exists():
                shutil.rmtree(self.tmp_directory)
                log.debug(f"Cleaned up temporary directory: {self.tmp_directory}")
        except Exception as e:
            log.warning(f"Failed to clean up temporary directory {self.tmp_directory}: {e}")


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

    def save_metadata(self, metadata: ExperimentMetadata):
        """Save metadata to the metadata.yml file."""
        import yaml

        # Convert ExperimentMetadata to dictionary
        metadata_dict = {
            'environments': metadata.environments,
            'description': metadata.description,
        }

        # Add optional fields if they exist
        if metadata.tags:
            metadata_dict['tags'] = metadata.tags
        if metadata.smb:
            metadata_dict['smb'] = metadata.smb
        if metadata.nfs:
            metadata_dict['nfs'] = metadata.nfs
        if metadata.usb:
            metadata_dict['usb'] = metadata.usb
        if metadata.disk:
            metadata_dict['disk'] = metadata.disk

        try:
            with open(self.metadatafile, 'w') as f:
                yaml.dump(metadata_dict, f, default_flow_style=False, sort_keys=False)
        except OSError as e:
            raise ExperimentFileCreationError(
                log,
                message=f'Failed to save metadata file for experiment {self.experiment}: {e.strerror}'
            ) from e

    def load_testset(self) -> TestsetFile:
        # Load tests from playbook instead of separate testset file
        from adare.types.playbook import parse_playbook
        from adarelib.testset.type import TestsetFile

        # Parse playbook without automatic variables
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
    def sha256_playbook_full(self) -> str:
        """Full playbook hash including all actions for development/loading purposes."""
        return hash_file_sha256(self.playbookfile)

    @property
    def sha256_for_loading(self) -> str:
        """Hash used for loading decisions - includes pause/pull for development workflow."""
        return self.sha256_playbook_full  # Use full hash for loading decisions

    @property
    def sha256_for_integrity(self) -> str:
        """Hash for experiment integrity/reproducibility - excludes infrastructure actions."""
        return self.sha256_playbook_semantic

    @property
    def sha256_playbook_semantic(self) -> str:
        """
        Hash playbook based on semantic content, excluding infrastructure actions
        that don't affect the core experimental logic.
        """
        # Parse the playbook to get structured data
        from adare.types.playbook import parse_playbook
        from adarelib.testset.yaml.customloader import get_custom_loader
        import yaml
        
        with self.playbookfile.open('r') as f:
            playbook_data = yaml.load(f, Loader=get_custom_loader())
        
        # Create a copy to avoid modifying original
        semantic_data = playbook_data.copy() if playbook_data else {}
        
        # Define infrastructure actions to exclude from integrity hash
        infrastructure_actions = {'pull'}
        
        # Filter actions to keep only core experimental actions
        if 'actions' in semantic_data:
            filtered_actions = []
            for action in semantic_data['actions']:
                # Check if this is an infrastructure action
                is_infrastructure = any(action_type in action for action_type in infrastructure_actions)
                
                # Keep non-infrastructure actions
                if not is_infrastructure:
                    filtered_actions.append(action)
            
            semantic_data['actions'] = filtered_actions
        
        # Hash the semantic content using existing utility
        from adare.helperfunctions.hash import hash_dict_sha256
        return hash_dict_sha256(semantic_data)

    @property
    def sha256(self) -> str:
        # Since testset is now part of playbook, only use playbook hash
        # to avoid double-counting the same content
        # Use full hash for experiment loading/development workflow
        return self.sha256_playbook_full
