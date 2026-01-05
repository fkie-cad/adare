"""
Hypervisor-agnostic exceptions.

All hypervisor implementations should use these exceptions for consistent error handling.
"""
from adare.exceptions import LoggedErrorException
import logging

log = logging.getLogger(__name__)


class HypervisorException(LoggedErrorException):
    """Base exception for all hypervisor operations."""
    def __init__(self, message: str):
        super().__init__(log, message)


class VMImportException(HypervisorException):
    """Raised when VM import fails."""
    pass


class VMAlreadyRunningException(HypervisorException):
    """Raised when attempting to start a VM that is already running."""
    pass


class VMNotFoundException(HypervisorException):
    """Raised when a VM cannot be found."""
    pass


class SnapshotNotFoundException(HypervisorException):
    """Raised when a snapshot cannot be found."""
    pass


class UnsupportedFeatureException(HypervisorException):
    """Raised when a hypervisor doesn't support a specific feature."""
    pass


class VMStartException(HypervisorException):
    """Raised when VM fails to start via libvirt."""
    pass
