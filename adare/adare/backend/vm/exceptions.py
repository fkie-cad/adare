"""
VM-specific exceptions for the ADARE VM management system.
"""

from adare.exceptions import LoggedErrorException


class VMError(LoggedErrorException):
    """Base class for VM-related errors."""

    pass


class VMNotFoundError(VMError):
    """VM not found in database or filesystem."""

    pass


class AmbiguousVmTargetError(VMError):
    """A name matches both a registered VM and a VM instance."""

    pass


class VMRemovalError(VMError):
    """A registered VM cannot be removed (an experiment runs on it, or removal would take more along)."""

    pass


class VMInUseByEnvironmentError(VMRemovalError):
    """A registered VM is still what environments run on."""

    pass


class VMValidationError(VMError):
    """VM validation failed."""

    pass


class VMLoadError(VMError):
    """Failed to load VM into system."""

    pass


class VMCopyError(VMError):
    """Failed to copy VM file."""

    pass


class VMStorageError(VMError):
    """VM storage directory issues."""

    pass


class VMImportError(VMError):
    """VirtualBox import operation failed."""

    pass
