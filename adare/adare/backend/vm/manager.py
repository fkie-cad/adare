"""
VM file management and validation.

Handles VM file operations including validation, copying, and hash calculation.
Pure business logic with no database dependencies for easy testing.
"""

import logging
import threading
from pathlib import Path

from adare.backend.vm.exceptions import VMCopyError, VMValidationError
from adare.backend.vm.storage import generate_vm_filename, get_vm_storage_directory
from adare.helperfunctions.file.hash import file_sha256_with_progress, file_sha256_with_progress_async
from adare.helperfunctions.file.validation import validate_tarfile_with_progress
from adare.helperfunctions.integrity import IntegrityManager

log = logging.getLogger(__name__)


class VMFileManager:
    """
    Manages VM file operations including validation, copying, and hash calculation.

    This class is pure business logic with no database dependencies, making it easily testable.
    """

    def validate_vm_file(self, file_path: Path, quiet: bool = False) -> dict:
        """
        Validate VM file format and calculate metadata.

        Args:
            file_path: Path to VM file
            quiet: If True, suppress progress indicators

        Returns:
            Dictionary with file_size and file_hash

        Raises:
            VMValidationError: If validation fails
        """
        if not file_path.exists():
            raise VMValidationError(log, f"VM file {file_path} does not exist")

        if not file_path.suffix.lower() == '.ova':
            raise VMValidationError(log, f"VM file {file_path} is not an OVA file")

        # Validate OVA format with progress indication
        if not validate_tarfile_with_progress(
            file_path=file_path,
            description=f"Validating OVA format for {file_path.name}",
            quiet=quiet
        ):
            raise VMValidationError(log, f"VM file {file_path} is not a valid OVA file")

        # Calculate file size and hash
        file_size = file_path.stat().st_size
        file_hash = self.calculate_file_hash(file_path, quiet=quiet)

        log.info(f"VM file validation successful: {file_path}")
        return {
            'file_size': file_size,
            'file_hash': file_hash
        }

    def validate_vm_file_format_only(self, file_path: Path, quiet: bool = False) -> dict:
        """
        Validate VM file format without calculating hash (optimization for when hash is already known).

        Args:
            file_path: Path to VM file
            quiet: If True, suppress progress indicators

        Returns:
            Dictionary with file_size only

        Raises:
            VMValidationError: If validation fails
        """
        if not file_path.exists():
            raise VMValidationError(log, f"VM file {file_path} does not exist")

        if not file_path.suffix.lower() == '.ova':
            raise VMValidationError(log, f"VM file {file_path} is not an OVA file")

        # Validate OVA format with progress indication
        if not validate_tarfile_with_progress(
            file_path=file_path,
            description=f"Validating OVA format for {file_path.name}",
            quiet=quiet
        ):
            raise VMValidationError(log, f"VM file {file_path} is not a valid OVA file")

        # Only calculate file size, skip hash calculation
        file_size = file_path.stat().st_size

        log.info(f"VM file format validation successful: {file_path}")
        return {
            'file_size': file_size
        }

    def calculate_file_hash(self, file_path: Path, silent: bool = False, interrupt_event: threading.Event | None = None) -> str:
        """
        Calculate SHA256 hash of file with progress indication.

        Args:
            file_path: Path to file
            silent: If True, suppress progress bar
            interrupt_event: Optional event to check for user interruption

        Returns:
            SHA256 hash string
        """
        return file_sha256_with_progress(
            file_path=file_path,
            description=f"Calculating hash for {file_path.name}",
            silent=silent,
            interrupt_event=interrupt_event
        )

    async def calculate_file_hash_async(self, file_path: Path, silent: bool = False, interrupt_event: threading.Event | None = None) -> str:
        """
        Calculate SHA256 hash of file with progress indication (async version).

        Args:
            file_path: Path to file
            silent: If True, suppress progress bar
            interrupt_event: Optional event to check for user interruption

        Returns:
            SHA256 hash string
        """
        return await file_sha256_with_progress_async(
            file_path=file_path,
            description=f"Calculating hash for {file_path.name}",
            silent=silent,
            interrupt_event=interrupt_event
        )

    def copy_vm_file(self, source_path: Path, name: str, scope: str,
                    project_path: Path = None, silent: bool = False) -> Path:
        """
        Copy VM file to appropriate storage location.

        Args:
            source_path: Original VM file path
            name: VM name
            scope: 'global' or 'project'
            project_path: Required if scope is 'project'
            silent: If True, suppress progress indicators

        Returns:
            Path to copied VM file

        Raises:
            VMCopyError: If file copying fails
        """
        try:
            # Get target directory
            target_dir = get_vm_storage_directory(scope, project_path)

            # Generate unique target path
            target_path = generate_vm_filename(name, source_path, target_dir)

            if target_path.exists() and target_path.samefile(source_path):
                log.info(f"VM file already in target location: {target_path}")
                # Ensure existing file is also write-protected
                if IntegrityManager.protect_file(target_path):
                    log.info(f"Existing VM file write-protected for integrity: {target_path}")
                return target_path

            from adare.helperfunctions.file.copy import copy
            copy(
                src=source_path,
                dst=target_path,
                silent=silent,
            )

            # Make the copied VM file write-protected for integrity preservation
            if IntegrityManager.protect_file(target_path):
                log.info(f"VM file write-protected for integrity: {target_path}")
            else:
                log.warning(f"Failed to write-protect VM file: {target_path}")

            return target_path

        except OSError as e:
            raise VMCopyError(log, f"Failed to copy VM file: {e}")

    def ensure_vm_available(self, vm_path: Path, name: str, scope: str,
                           project_path: Path = None, silent: bool = False) -> tuple[Path, dict]:
        """
        Ensure VM file is available in proper storage location with validation.

        This is a convenience method that combines validation and copying.

        Args:
            vm_path: Path to VM file
            name: VM name
            scope: 'global' or 'project'
            project_path: Required if scope is 'project'
            silent: If True, suppress progress indicators

        Returns:
            Tuple of (target_file_path, validation_data)

        Raises:
            VMValidationError: If validation fails
            VMCopyError: If copying fails
        """
        # Validate VM file first
        validation_data = self.validate_vm_file(vm_path, quiet=silent)

        # Copy to appropriate storage location
        target_path = self.copy_vm_file(vm_path, name, scope, project_path, quiet=silent)

        return target_path, validation_data
