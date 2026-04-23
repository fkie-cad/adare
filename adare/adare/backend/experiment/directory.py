# external imports
# configure logging
import logging
import shutil
from datetime import UTC, datetime
from pathlib import Path

import jinja2

import adare
from adare.backend.directory import Directory
from adare.backend.experiment.exceptions import (
    ExperimentDirectoryCreationError,
    ExperimentFileCreationError,
    ExperimentFileMissingError,
    ExperimentRemovalError,
)
from adare.backend.project.directory import ProjectDirectory
from adare.config.configdirectory import EXAMPLES_DIR
from adare.helperfunctions.hash import hash_file_sha256
from adare.parsers import parse_metadata_file
from adare.types.experiment import ExperimentMetadata

# internal imports
from adarelib.testset.type import TestsetFile

log = logging.getLogger(__name__)


class ExperimentRunDirectory(Directory):
    log_directory: Path
    adare_log_file: Path
    adarevm_log_file: Path

    def __init__(self, project_directory: ProjectDirectory, experiment: str):
        super().__init__(project_directory.run / experiment / datetime.now(UTC).strftime('%Y-%m-%d_%H-%M-%S'))
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
        """Create run directory structure with all subdirectories.

        Creates:
            - Run directory (timestamped)
            - logs/ - For adare.log and adarevm.log
            - reporting/ - For forensic reports
            - reporting/screenshots/ - For GUI action screenshots
            - .tmp/ - For temporary files

        Raises:
            LoggedException: If directory creation fails
        """
        try:
            # Create run directory path
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.mkdir(parents=False)

            # CRITICAL: Create logs directory (ALWAYS, regardless of runlog flag)
            self.log_directory.mkdir(parents=False, exist_ok=True)
            log.info(f"Created logs directory: {self.log_directory}")

            # Create other directories with exist_ok for safety
            self.reporting_directory.mkdir(parents=False, exist_ok=True)
            self.screenshots_directory.mkdir(parents=False, exist_ok=True)
            self.tmp_directory.mkdir(parents=False, exist_ok=True)

        except OSError as e:
            error_msg = f"Failed to create run directory structure at {self.path}: {e}"
            log.error(error_msg)
            from adare.exceptions import LoggedException
            raise LoggedException(log, message=error_msg) from e


    def clean(self):
        """Clean up temporary files and directories after experiment run.

        Note: This only removes the .tmp directory, preserving logs and reports for forensic analysis.
        """
        try:
            if self.tmp_directory.exists():
                shutil.rmtree(self.tmp_directory)
                log.debug(f"Cleaned up temporary directory: {self.tmp_directory}")
        except OSError as e:
            log.warning(f"Failed to clean up temporary directory {self.tmp_directory}: {e}")


class DiffRunDirectory(Directory):
    """Directory structure for diff mode runs (stored under /diff instead of /run)."""
    log_directory: Path
    adare_log_file: Path
    mcp_gui_log_file: Path
    reporting_directory: Path
    screenshots_directory: Path
    tmp_directory: Path
    artifacts_directory: Path
    diff_directory: Path

    def __init__(self, project_directory: ProjectDirectory, experiment: str):
        # Use 'diff' instead of 'run'
        diff_dir = project_directory.path / 'diff'
        super().__init__(diff_dir / experiment / datetime.now(UTC).strftime('%Y-%m-%d_%H-%M-%S'))
        self.log_directory = self.path / 'logs'
        self.adare_log_file = self.log_directory / 'adare.log'
        self.mcp_gui_log_file = self.log_directory / 'mcp_gui.log'
        self.reporting_directory = self.path / 'reporting'
        self.screenshots_directory = self.reporting_directory / 'screenshots'
        self.tmp_directory = self.path / '.tmp'
        self.artifacts_directory = self.path / 'artifacts'
        self.diff_directory = self.artifacts_directory / 'diff'

    def create(self):
        """Create diff run directory structure with all subdirectories.

        Creates:
            - Diff run directory (timestamped)
            - logs/ - For adare.log and mcp_gui.log
            - reporting/ - For forensic reports
            - reporting/screenshots/ - For GUI action screenshots
            - .tmp/ - For temporary files
            - artifacts/ - For diff artifacts
            - artifacts/diff/ - For diff results

        Raises:
            LoggedException: If directory creation fails
        """
        try:
            # Create diff parent directory if needed
            self.path.parent.parent.mkdir(parents=True, exist_ok=True)
            self.path.parent.mkdir(parents=False, exist_ok=True)
            self.path.mkdir(parents=False)

            # CRITICAL: Create logs directory (ALWAYS)
            self.log_directory.mkdir(parents=False, exist_ok=True)
            log.info(f"Created logs directory: {self.log_directory}")

            # Create other directories with exist_ok for safety
            self.reporting_directory.mkdir(parents=False, exist_ok=True)
            self.screenshots_directory.mkdir(parents=False, exist_ok=True)
            self.tmp_directory.mkdir(parents=False, exist_ok=True)
            self.artifacts_directory.mkdir(parents=False, exist_ok=True)
            self.diff_directory.mkdir(parents=False, exist_ok=True)

        except OSError as e:
            error_msg = f"Failed to create diff run directory structure at {self.path}: {e}"
            log.error(error_msg)
            from adare.exceptions import LoggedException
            raise LoggedException(log, message=error_msg) from e


    def clean(self):
        """Clean up temporary files and directories after experiment run."""
        try:
            if self.tmp_directory.exists():
                shutil.rmtree(self.tmp_directory)
                log.debug(f"Cleaned up temporary directory: {self.tmp_directory}")
        except OSError as e:
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
        self._cached_playbook = None
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

        # Cache parsed playbook to avoid redundant parsing (and duplicate warnings)
        if self._cached_playbook is None:
            self._cached_playbook = parse_playbook(self.playbookfile)

        # Return TestsetFile constructed from playbook tests
        return TestsetFile(name=self.experiment, tests=self._cached_playbook.tests)




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
        import yaml

        from adarelib.testset.yaml.customloader import get_custom_loader

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
