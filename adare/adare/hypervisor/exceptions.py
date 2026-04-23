"""
Hypervisor-agnostic exceptions.

All hypervisor implementations should use these exceptions for consistent error handling.
This module defines a comprehensive exception hierarchy following the pattern:

    HypervisorException (base)
    ├── VMOperationException (VM lifecycle operations)
    │   ├── VMNotFoundException
    │   ├── VMImportException
    │   ├── VMStartException
    │   ├── VMStopException
    │   ├── VMAlreadyRunningException
    │   └── GuestAgentTimeoutException
    ├── SnapshotOperationException (snapshot operations)
    │   ├── SnapshotNotFoundException
    │   ├── SnapshotCreationException
    │   └── SnapshotRestoreException
    ├── InstanceOperationException (VM instance management)
    │   ├── PortAllocationException
    │   ├── InstanceNotFoundException
    │   └── InstanceStateException
    ├── DiskOperationException (disk operations)
    │   ├── DiskConversionException
    │   └── DiskNotFoundException
    └── UnsupportedFeatureException

Usage:
    try:
        vm.start()
    except VMStartException as e:
        # Handle specific VM start failure
    except VMOperationException as e:
        # Handle any VM operation failure
    except HypervisorException as e:
        # Handle any hypervisor error
"""
import logging

from adare.exceptions import LoggedErrorException

log = logging.getLogger(__name__)


class HypervisorException(LoggedErrorException):
    """Base exception for all hypervisor operations."""
    def __init__(self, message: str):
        super().__init__(log, message)


# =============================================================================
# VM Operation Exceptions
# =============================================================================

class VMOperationException(HypervisorException):
    """
    Base exception for VM lifecycle operations.

    Attributes:
        vm_identifier: The VM name, UUID, or other identifier
        operation: The operation that failed (e.g., 'start', 'stop', 'import')
        reason: Detailed reason for the failure
    """
    def __init__(
        self,
        vm_identifier: str,
        operation: str,
        reason: str,
        message: str | None = None
    ):
        self.vm_identifier = vm_identifier
        self.operation = operation
        self.reason = reason
        if message is None:
            message = f"VM '{vm_identifier}': {operation} failed - {reason}"
        super().__init__(message)


class VMNotFoundException(VMOperationException):
    """Raised when a VM cannot be found."""
    def __init__(self, vm_identifier: str, reason: str = "VM not found"):
        super().__init__(vm_identifier, "lookup", reason)


class VMImportException(VMOperationException):
    """Raised when VM import fails."""
    def __init__(self, vm_identifier: str, reason: str):
        super().__init__(vm_identifier, "import", reason)


class VMStartException(VMOperationException):
    """Raised when VM fails to start."""
    def __init__(self, vm_identifier: str, reason: str):
        super().__init__(vm_identifier, "start", reason)


class VMStopException(VMOperationException):
    """Raised when VM fails to stop gracefully."""
    def __init__(self, vm_identifier: str, reason: str):
        super().__init__(vm_identifier, "stop", reason)


class VMAlreadyRunningException(VMOperationException):
    """Raised when attempting to start a VM that is already running."""
    def __init__(self, vm_identifier: str):
        super().__init__(vm_identifier, "start", "VM is already running")


class GuestAgentTimeoutException(VMOperationException):
    """Raised when guest agent doesn't respond within timeout."""
    def __init__(self, vm_identifier: str, timeout_seconds: float):
        super().__init__(
            vm_identifier,
            "guest_agent_connect",
            f"Guest agent did not respond within {timeout_seconds}s"
        )
        self.timeout_seconds = timeout_seconds


# =============================================================================
# Snapshot Operation Exceptions
# =============================================================================

class SnapshotOperationException(HypervisorException):
    """
    Base exception for snapshot operations.

    Attributes:
        vm_identifier: The VM name or UUID
        snapshot_name: The snapshot name
        operation: The operation that failed
        reason: Detailed reason for the failure
    """
    def __init__(
        self,
        vm_identifier: str,
        snapshot_name: str,
        operation: str,
        reason: str,
        message: str | None = None
    ):
        self.vm_identifier = vm_identifier
        self.snapshot_name = snapshot_name
        self.operation = operation
        self.reason = reason
        if message is None:
            message = f"Snapshot '{snapshot_name}' on VM '{vm_identifier}': {operation} failed - {reason}"
        super().__init__(message)


class SnapshotNotFoundException(SnapshotOperationException):
    """Raised when a snapshot cannot be found."""
    def __init__(self, vm_identifier: str, snapshot_name: str):
        super().__init__(vm_identifier, snapshot_name, "lookup", "Snapshot not found")


class SnapshotCreationException(SnapshotOperationException):
    """Raised when snapshot creation fails."""
    def __init__(self, vm_identifier: str, snapshot_name: str, reason: str):
        super().__init__(vm_identifier, snapshot_name, "create", reason)


class SnapshotRestoreException(SnapshotOperationException):
    """Raised when snapshot restoration fails."""
    def __init__(self, vm_identifier: str, snapshot_name: str, reason: str):
        super().__init__(vm_identifier, snapshot_name, "restore", reason)


# =============================================================================
# Instance Management Exceptions
# =============================================================================

class InstanceOperationException(HypervisorException):
    """
    Base exception for VM instance management operations.

    These are database-level operations for tracking VM instances,
    separate from hypervisor-level VM operations.
    """
    pass


class PortAllocationException(InstanceOperationException):
    """Raised when port allocation fails (no ports available or race condition)."""
    def __init__(self, reason: str, port_range: tuple[int, int] | None = None):
        self.port_range = port_range
        if port_range:
            message = f"Port allocation failed in range {port_range[0]}-{port_range[1]}: {reason}"
        else:
            message = f"Port allocation failed: {reason}"
        super().__init__(message)


class InstanceNotFoundException(InstanceOperationException):
    """Raised when a VM instance cannot be found in the database."""
    def __init__(self, instance_identifier: str):
        self.instance_identifier = instance_identifier
        super().__init__(f"VM instance '{instance_identifier}' not found in database")


class InstanceStateException(InstanceOperationException):
    """Raised when an instance is in an unexpected state for the requested operation."""
    def __init__(self, instance_identifier: str, current_state: str, expected_states: list[str]):
        self.instance_identifier = instance_identifier
        self.current_state = current_state
        self.expected_states = expected_states
        expected_str = ", ".join(expected_states)
        super().__init__(
            f"VM instance '{instance_identifier}' is in state '{current_state}', "
            f"but expected one of: {expected_str}"
        )


# =============================================================================
# Disk Operation Exceptions
# =============================================================================

class DiskOperationException(HypervisorException):
    """Base exception for disk operations."""
    def __init__(self, disk_path: str, operation: str, reason: str):
        self.disk_path = disk_path
        self.operation = operation
        self.reason = reason
        super().__init__(f"Disk '{disk_path}': {operation} failed - {reason}")


class DiskConversionException(DiskOperationException):
    """Raised when disk format conversion fails."""
    def __init__(self, disk_path: str, source_format: str, target_format: str, reason: str):
        self.source_format = source_format
        self.target_format = target_format
        super().__init__(
            disk_path,
            f"convert ({source_format} -> {target_format})",
            reason
        )


class DiskNotFoundException(DiskOperationException):
    """Raised when a disk file cannot be found."""
    def __init__(self, disk_path: str):
        super().__init__(disk_path, "lookup", "Disk file not found")


# =============================================================================
# Feature Support Exceptions
# =============================================================================

class UnsupportedFeatureException(HypervisorException):
    """Raised when a hypervisor doesn't support a specific feature."""
    def __init__(self, hypervisor: str, feature: str):
        self.hypervisor = hypervisor
        self.feature = feature
        super().__init__(f"Hypervisor '{hypervisor}' does not support feature: {feature}")
