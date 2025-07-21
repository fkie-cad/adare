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