"""
Testfunction Manager for Global Resource Management.

Handles copying and managing testfunctions in the global STATE_DIR/testfunctions directory.
Provides clean separation between file operations and database operations.
"""

import logging
import shutil
from pathlib import Path

from adare.backend.testfunction.exceptions import TestfunctionMissingFileError
from adare.config.configdirectory import STATE_DIR

log = logging.getLogger(__name__)


class TestfunctionManager:
    """
    Manager for global testfunction file operations.

    Handles installation and management of testfunctions in the global directory,
    following the same pattern as SnapshotManager and other managers in the codebase.
    """

    def __init__(self):
        self.global_testfunctions_dir = STATE_DIR / 'testfunctions'

    def install_testfunction(self, source_python_file: Path, source_requirements_file: Path, name: str) -> tuple[Path, Path]:
        """
        Install a testfunction to the global directory.

        Args:
            source_python_file: Path to source Python file
            source_requirements_file: Path to source requirements.txt
            name: Name of the testfunction (used for directory name)

        Returns:
            Tuple of (target_python_path, target_requirements_path)

        Raises:
            TestfunctionMissingFileError: If source files don't exist
        """
        if not source_python_file.exists():
            raise TestfunctionMissingFileError(
                log,
                message=f'Source Python file does not exist: {source_python_file}'
            )

        # Create target directory structure
        target_dir = self.global_testfunctions_dir / name
        target_dir.mkdir(parents=True, exist_ok=True)

        # Define target paths
        target_python_file = target_dir / source_python_file.name
        target_requirements_file = target_dir / 'requirements.txt'

        # Copy Python file (only if it doesn't exist to avoid overwrites)
        if not target_python_file.exists():
            shutil.copy2(source_python_file, target_python_file)
            log.info(f'Copied testfunction Python file: {source_python_file} -> {target_python_file}')
        else:
            log.debug(f'Testfunction Python file already exists, skipping copy: {target_python_file}')

        # Copy requirements.txt if it exists in source (only if target doesn't exist)
        if source_requirements_file.exists():
            if not target_requirements_file.exists():
                shutil.copy2(source_requirements_file, target_requirements_file)
                log.info(f'Copied requirements file: {source_requirements_file} -> {target_requirements_file}')
            else:
                log.debug(f'Requirements file already exists, skipping copy: {target_requirements_file}')
        else:
            # Create empty requirements.txt if source doesn't have one but target doesn't exist
            if not target_requirements_file.exists():
                target_requirements_file.touch()
                log.debug(f'Created empty requirements file: {target_requirements_file}')

        return target_python_file, target_requirements_file

    def testfunction_exists_in_global_dir(self, name: str) -> bool:
        """
        Check if a testfunction already exists in the global directory.

        Args:
            name: Name of the testfunction

        Returns:
            True if testfunction directory and Python file exist
        """
        target_dir = self.global_testfunctions_dir / name
        if not target_dir.exists():
            return False

        # Look for any Python file in the directory
        python_files = list(target_dir.glob('*.py'))
        return len(python_files) > 0

    def get_testfunction_paths(self, name: str) -> tuple[Path | None, Path | None]:
        """
        Get the paths for a testfunction in the global directory.

        Args:
            name: Name of the testfunction

        Returns:
            Tuple of (python_file_path, requirements_file_path) or (None, None) if not found
        """
        target_dir = self.global_testfunctions_dir / name
        if not target_dir.exists():
            return None, None

        # Find Python file (there should be only one per testfunction)
        python_files = list(target_dir.glob('*.py'))
        if not python_files:
            return None, None

        python_file = python_files[0]  # Take the first (should be only) Python file
        requirements_file = target_dir / 'requirements.txt'

        return python_file, requirements_file

    def cleanup_testfunction(self, name: str) -> bool:
        """
        Remove a testfunction from the global directory.

        Args:
            name: Name of the testfunction to remove

        Returns:
            True if successfully removed, False if didn't exist
        """
        target_dir = self.global_testfunctions_dir / name
        if not target_dir.exists():
            log.warning(f'Testfunction directory does not exist: {target_dir}')
            return False

        try:
            shutil.rmtree(target_dir)
            log.info(f'Removed testfunction directory: {target_dir}')
            return True
        except OSError as e:
            log.error(f'Failed to remove testfunction directory {target_dir}: {e}')
            return False

    def ensure_global_directory_exists(self):
        """Ensure the global testfunctions directory exists."""
        self.global_testfunctions_dir.mkdir(parents=True, exist_ok=True)
        log.debug(f'Ensured global testfunctions directory exists: {self.global_testfunctions_dir}')
