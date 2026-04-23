"""
Abstract networking operations mixin for hypervisor VMs.

All hypervisor implementations must provide networking functionality.
"""
import logging
from abc import ABC, abstractmethod
from pathlib import Path

log = logging.getLogger(__name__)


class AbstractNetworkingMixin(ABC):
    """
    Abstract mixin class defining networking operations for VMs.

    All hypervisor implementations must implement these networking operations.
    """

    # ==================== Port Forwarding ====================

    @abstractmethod
    async def list_port_forwarding_rules(
        self,
        ctx_manager=None,
        stop_event=None,
        log_file: Path | None = None,
        silent: bool = False
    ):
        """
        List all port forwarding rules for the VM.

        Args:
            ctx_manager: Optional context manager for status updates
            stop_event: Optional threading event to signal cancellation
            log_file: Optional path to log file for command output
            silent: If True, suppress log output

        Returns:
            Dict mapping rule names to PortForwardingRule objects
        """
        pass

    @abstractmethod
    async def add_port_forwarding(
        self,
        name: str,
        protocol: str,
        host_port: int,
        guest_port: int,
        host_ip: str = "",
        guest_ip: str = "",
        ctx_manager=None,
        stop_event=None,
        log_file: Path | None = None,
        silent: bool = False
    ) -> int:
        """
        Add a port forwarding rule to the VM.

        Args:
            name: Name for the port forwarding rule
            protocol: Protocol ('tcp' or 'udp')
            host_port: Port on the host machine
            guest_port: Port in the guest VM
            host_ip: Host IP address (empty string for all interfaces)
            guest_ip: Guest IP address (empty string for default)
            ctx_manager: Optional context manager for status updates
            stop_event: Optional threading event to signal cancellation
            log_file: Optional path to log file for command output
            silent: If True, suppress log output

        Returns:
            Return code (0 for success, non-zero for failure)
        """
        pass

    @abstractmethod
    async def remove_port_forwarding(
        self,
        name: str,
        ctx_manager=None,
        stop_event=None,
        log_file: Path | None = None,
        silent: bool = False
    ) -> int:
        """
        Remove a port forwarding rule from the VM.

        Args:
            name: Name of the port forwarding rule to remove
            ctx_manager: Optional context manager for status updates
            stop_event: Optional threading event to signal cancellation
            log_file: Optional path to log file for command output
            silent: If True, suppress log output

        Returns:
            Return code (0 for success, non-zero for failure)
        """
        pass

    # ==================== Shared Folders ====================

    @abstractmethod
    async def add_shared_folder(
        self,
        name: str,
        host_path: Path,
        readonly: bool = False,
        ctx_manager=None,
        stop_event=None,
        log_file: Path | None = None,
        silent: bool = False
    ):
        """
        Add a shared folder to the VM configuration.

        Args:
            name: Name of the shared folder
            host_path: Path on the host machine
            readonly: If True, share is read-only
            ctx_manager: Optional context manager for status updates
            stop_event: Optional threading event to signal cancellation
            log_file: Optional path to log file for command output
            silent: If True, suppress log output

        Returns:
            Return code (0 for success, non-zero for failure)
        """
        pass

    @abstractmethod
    async def mount_shared_folder(
        self,
        name: str,
        mountpoint: Path,
        ctx_manager=None,
        stop_event=None,
        log_file: Path | None = None,
        silent: bool = False
    ):
        """
        Mount a shared folder inside the guest VM.

        Args:
            name: Name of the shared folder
            mountpoint: Where to mount the folder in the guest
            ctx_manager: Optional context manager for status updates
            stop_event: Optional threading event to signal cancellation
            log_file: Optional path to log file for command output
            silent: If True, suppress log output

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    async def list_shared_folders(
        self,
        ctx_manager=None,
        stop_event=None,
        log_file: Path | None = None,
        silent: bool = False
    ):
        """
        List all shared folders configured for the VM.

        Args:
            ctx_manager: Optional context manager for status updates
            stop_event: Optional threading event to signal cancellation
            log_file: Optional path to log file for command output
            silent: If True, suppress log output

        Returns:
            Dict mapping folder names to SharedFolderConfig objects
        """
        pass

    @abstractmethod
    async def remove_shared_folder(
        self,
        name: str,
        mountpoint: str | None = None,
        ctx_manager=None,
        stop_event=None,
        log_file: Path | None = None,
        silent: bool = False
    ):
        """
        Remove a shared folder from the VM.

        Args:
            name: Name of the shared folder to remove
            mountpoint: Optional mountpoint to unmount (guest-specific)
            ctx_manager: Optional context manager for status updates
            stop_event: Optional threading event to signal cancellation
            log_file: Optional path to log file for command output
            silent: If True, suppress log output

        Returns:
            Return code (0 for success, non-zero for failure)
        """
        pass

    @abstractmethod
    async def remove_all_shared_folders(
        self,
        ctx_manager=None,
        stop_event=None,
        log_file: Path | None = None,
        silent: bool = False
    ):
        """
        Remove all shared folders from the VM.

        Args:
            ctx_manager: Optional context manager for status updates
            stop_event: Optional threading event to signal cancellation
            log_file: Optional path to log file for command output
            silent: If True, suppress log output

        Returns:
            Return code (0 for success, non-zero for failure)
        """
        pass

    @abstractmethod
    def queue_mount_shared_folder(self, name: str, mountpoint: Path):
        """
        Queue a shared folder mount operation for batch execution.

        Args:
            name: Name of the shared folder
            mountpoint: Where to mount the folder in the guest
        """
        pass

    @abstractmethod
    async def mount_multiple_shared_folders(
        self,
        folders: dict,
        ctx_manager=None,
        stop_event=None,
        log_file: Path | None = None,
        silent: bool = False
    ):
        """
        Mount multiple shared folders in the guest VM.

        Args:
            folders: Dict mapping folder names to mountpoints
            ctx_manager: Optional context manager for status updates
            stop_event: Optional threading event to signal cancellation
            log_file: Optional path to log file for command output
            silent: If True, suppress log output

        Returns:
            True if all mounts successful, False otherwise
        """
        pass
