"""
VM file validators using Strategy Pattern.
Each hypervisor has its own validation strategy.
"""
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List

from adare.backend.vm.exceptions import VMValidationError
from adare.helperfunctions.file.validation import validate_tarfile_with_progress

log = logging.getLogger(__name__)


class VMFileValidator(ABC):
    """Abstract base class for hypervisor-specific VM file validators."""

    @abstractmethod
    def get_supported_extensions(self) -> List[str]:
        """Return list of supported file extensions for this hypervisor."""
        pass

    @abstractmethod
    def validate_file(self, file_path: Path, name: str, quiet: bool = False) -> None:
        """
        Validate VM file format and structure.

        Args:
            file_path: Path to VM file
            name: VM name for error messages
            quiet: If True, suppress progress output

        Raises:
            VMValidationError: If validation fails
        """
        pass

    def _validate_file_exists(self, file_path: Path) -> None:
        """Common validation: Check file exists and is readable."""
        if not file_path.exists():
            raise VMValidationError(log, f"VM file {file_path} does not exist")

        if not file_path.is_file():
            raise VMValidationError(log, f"VM file {file_path} is not a regular file")


class VirtualBoxValidator(VMFileValidator):
    """Validator for VirtualBox VMs (OVA format)."""

    def get_supported_extensions(self) -> List[str]:
        return ['.ova']

    def validate_file(self, file_path: Path, name: str, quiet: bool = False) -> None:
        """Validate OVA file as tar archive."""
        self._validate_file_exists(file_path)

        # Validate OVA format (tar archive)
        if not validate_tarfile_with_progress(
            file_path=file_path,
            description=f"Validating OVA format for {file_path.name}",
            quiet=quiet
        ):
            raise VMValidationError(
                log,
                f"VM file {file_path} is not a valid OVA (tar archive) file"
            )

        log.debug(f"Successfully validated VirtualBox OVA file: {file_path}")


class QEMUValidator(VMFileValidator):
    """Validator for QEMU VMs (qcow2, raw, vmdk, etc.)."""

    def get_supported_extensions(self) -> List[str]:
        return ['.qcow2', '.img', '.raw', '.vmdk', '.vdi']

    def validate_file(self, file_path: Path, name: str, quiet: bool = False) -> None:
        """Validate QEMU disk image file."""
        self._validate_file_exists(file_path)

        # Validate qcow2 magic bytes for extra safety
        if file_path.suffix.lower() == '.qcow2':
            self._validate_qcow2_magic(file_path)

        log.debug(f"Successfully validated QEMU disk file: {file_path}")

    def _validate_qcow2_magic(self, file_path: Path) -> None:
        """Validate qcow2 file magic bytes (QFI\xfb)."""
        try:
            with open(file_path, 'rb') as f:
                magic = f.read(4)
                if magic != b'QFI\xfb':
                    log.warning(
                        f"VM file {file_path} does not have valid qcow2 magic bytes "
                        f"(expected b'QFI\\xfb', got {magic!r}), but proceeding anyway"
                    )
        except IOError as e:
            raise VMValidationError(log, f"Cannot read VM file {file_path}: {e}")


class VMValidatorFactory:
    """Factory to get appropriate validator for hypervisor type."""

    # Singleton validator instances (stateless, can be reused)
    _validators = {
        'virtualbox': VirtualBoxValidator(),
        'qemu': QEMUValidator()
    }
    @classmethod
    def get_validator(cls, hypervisor: str) -> VMFileValidator:
        """
        Get validator for specified hypervisor.

        Args:
            hypervisor: Hypervisor type ('virtualbox', 'qemu')

        Returns:
            VMFileValidator instance

        Note: Defaults to VirtualBox validator for backwards compatibility.
        """
        validator = cls._validators.get(hypervisor.lower())

        if validator is None:
            log.warning(
                f"Unknown hypervisor '{hypervisor}', defaulting to VirtualBox validator. "
                f"Supported: {', '.join(cls._validators.keys())}"
            )
            return cls._validators['virtualbox']

        return validator
