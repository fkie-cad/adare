"""
VM validation and file operation mixins.

Provides validation, hashing, and file management methods for VMs.
"""

import logging
from pathlib import Path

from adare.config.configdirectory import VMS_DIR
from adare.helperfunctions.file.hash import file_sha256_with_progress
from adare.validators.vm_validators import VMValidatorFactory

from .exceptions import VMLoadError, VMValidationError

log = logging.getLogger(__name__)


class VmValidationMixin:
    """Mixin providing VM file validation and file operation methods."""

    def validate_vm_file(self, file_path: Path, name: str = None, quiet: bool = False, hypervisor: str = 'virtualbox') -> dict:
        """
        Validate VM file using hypervisor-specific validator.

        Args:
            file_path: Path to VM file
            name: Optional name for better error messages
            quiet: If True, suppress progress bars
            hypervisor: Hypervisor type ('virtualbox', 'qemu') - default: 'virtualbox'

        Returns:
            Dictionary with file_size and file_hash

        Raises:
            VMValidationError: If validation fails
        """
        # Get validator for this hypervisor
        validator = VMValidatorFactory.get_validator(hypervisor)

        # Check file extension
        file_ext = file_path.suffix.lower()
        supported = validator.get_supported_extensions()

        if file_ext not in supported:
            raise VMValidationError(
                log,
                f"VM file {file_path} has unsupported extension '{file_ext}' for hypervisor '{hypervisor}'.\n"
                f"Supported extensions for {hypervisor}: {', '.join(supported)}\n"
                f"If using QEMU, ensure environment YAML specifies: hypervisor: qemu"
            )

        # Delegate validation to hypervisor-specific validator
        validator.validate_file(file_path, name or file_path.stem, quiet=quiet)

        log.debug(f"Successfully validated {hypervisor} VM file: {file_path}")

    def _calculate_file_hash(self, file_path: Path, quiet: bool = False) -> str:
        """
        Calculate SHA256 hash of file with progress indication.

        Args:
            file_path: Path to file
            quiet: If True, suppress progress bar

        Returns:
            SHA256 hash string
        """
        return file_sha256_with_progress(
            file_path=file_path,
            description=f"Calculating hash for {file_path.name}",
            quiet=quiet
        )

    def _copy_vm_file(self, source_path: Path, project_path: Path, name: str, silent: bool = False) -> Path:
        """
        Copy VM file to global storage location.

        Args:
            source_path: Original VM file path
            project_path: Not used (VMs are global now)
            name: VM name
            silent: If True, suppress progress indicators

        Returns:
            Path to copied VM file

        Raises:
            VMLoadError: If file copying fails
        """
        try:
            # Use global VM directory instead of project-specific directory
            target_dir = VMS_DIR
            target_dir.mkdir(parents=True, exist_ok=True)

            # Generate target filename with VM name
            target_filename = f"{name}{source_path.suffix}"
            target_path = target_dir / target_filename

            # Check if target already exists
            if target_path.exists():
                if target_path.samefile(source_path):
                    # Source and target are the same file, no need to copy
                    log.info(f"VM file already in target location: {target_path}")
                    return target_path
                raise VMLoadError(log, f"Target VM file {target_path} already exists and is different from source {source_path}")

            log.info(f"Copying VM file to {target_path}")
            from adare.helperfunctions.file.copy import copy
            copy(
                src=source_path,
                dst=target_path,
                silent=silent
            )
            log.info(f"Successfully copied VM file to {target_path}")

            return target_path

        except VMLoadError:
            raise  # Don't re-wrap our own errors
        except OSError as e:
            raise VMLoadError(log, f"Failed to copy VM file: {e}")

    def _is_file_managed(self, file_path: Path) -> bool:
        """
        Check if a VM file is in managed storage (VMS_DIR).

        Args:
            file_path: Path to check

        Returns:
            True if file is in managed storage, False otherwise
        """
        try:
            file_path.resolve().relative_to(VMS_DIR.resolve())
            return True
        except ValueError:
            return False
