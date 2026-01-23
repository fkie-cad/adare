"""
Abstract VM class for hypervisor implementations.

All hypervisor implementations must provide a VM class that implements
these operations for consistent VM management across different hypervisors.
"""
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional, Dict, Any

import logging
log = logging.getLogger(__name__)


class AbstractVM(ABC):
    """
    Abstract base class for VM operations.

    All hypervisor implementations MUST provide these operations.
    Some operations may be optional and can raise UnsupportedFeatureException.
    """

    def __init__(
        self,
        vm_name: str,
        guest_os: str,
        manager,  # AbstractHypervisorManager
        username: str,
        password: str,
        **kwargs
    ):
        """
        Initialize VM instance.

        Args:
            vm_name: Name of the VM
            guest_os: Guest OS type (platform-specific)
            manager: Hypervisor manager instance
            username: Username for guest control
            password: Password for guest control
            **kwargs: Additional hypervisor-specific parameters (cpus, ram, network, etc.)
        """
        self.vm_name = vm_name
        self.guest_os = guest_os
        self.username = username
        self.password = password
        self.manager = manager

    # ==================== VM Lifecycle ====================

    @abstractmethod
    async def create(
        self,
        ctx_manager=None,
        stop_event: Optional[threading.Event] = None,
        log_file: Optional[Path] = None,
        silent: bool = False
    ):
        """
        Create a new VM with the specified configuration.

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
    async def start(
        self,
        ctx_manager=None,
        raise_if_running: bool = False,
        stop_event: Optional[threading.Event] = None,
        log_file: Optional[Path] = None,
        silent: bool = False
    ):
        """
        Start the VM.

        Args:
            ctx_manager: Optional context manager for status updates
            raise_if_running: If True, raise exception if VM is already running
            stop_event: Optional threading event to signal cancellation
            log_file: Optional path to log file for command output
            silent: If True, suppress log output

        Returns:
            Return code (0 for success, non-zero for failure)

        Raises:
            VMAlreadyRunningException: If raise_if_running is True and VM is running
        """
        pass

    @abstractmethod
    async def stop(
        self,
        ctx_manager=None,
        log_file: Optional[Path] = None,
        silent: bool = False,
        force: bool = False
    ):
        """
        Stop the VM.

        Args:
            ctx_manager: Optional context manager for status updates
            log_file: Optional path to log file for command output
            silent: If True, suppress log output

        Returns:
            Return code (0 for success, non-zero for failure)
        """
        pass

    @abstractmethod
    async def destroy(
        self,
        ctx_manager=None,
        stop_event: Optional[threading.Event] = None,
        log_file: Optional[Path] = None,
        silent: bool = False
    ):
        """
        Destroy the VM completely (unregister and delete).

        Args:
            ctx_manager: Optional context manager for status updates
            stop_event: Optional threading event to signal cancellation
            log_file: Optional path to log file for command output
            silent: If True, suppress log output

        Returns:
            Return code (0 for success, non-zero for failure)
        """
        pass

    # ==================== VM State ====================

    @abstractmethod
    def get_state(self) -> str:
        """
        Get the current state of the VM.

        Returns:
            String representing VM state (e.g., "running", "poweroff", "paused")

        Raises:
            VMNotFoundException: If VM doesn't exist
        """
        pass

    @abstractmethod
    def vm_exists(self) -> bool:
        """
        Check if the VM exists.

        Returns:
            True if VM exists, False otherwise
        """
        pass

    # ==================== Guest Control ====================

    @abstractmethod
    async def run_command(
        self,
        command: str,
        background: bool = False,
        silent: bool = False,
        stop_event: Optional[threading.Event] = None,
        cwd: Optional[str] = None,
        **kwargs
    ):
        """
        Run a command inside the VM guest.

        Args:
            command: Command to execute in guest
            background: If True, run command in background
            silent: If True, suppress log output
            stop_event: Optional threading event to signal cancellation
            cwd: Optional working directory for command execution
            **kwargs: Hypervisor-specific parameters

        Returns:
            CommandResult with returncode, stdout, stderr
        """
        pass

    @abstractmethod
    async def copy_from_guest(
        self,
        guest_path: str,
        host_path: str,
        recursive: bool = True
    ) -> bool:
        """
        Copy files/directories from guest to host.

        Args:
            guest_path: Path in guest VM
            host_path: Path on host
            recursive: If True, copy directories recursively

        Returns:
            True if successful, False otherwise
        """
        pass

    # ==================== Import/Export ====================

    @abstractmethod
    async def create_from_ovf_or_ova(
        self,
        file_path: Path,
        try_extract: bool = True,
        ctx_manager=None,
        stop_event: Optional[threading.Event] = None,
        log_file: Optional[Path] = None,
        silent: bool = False
    ):
        """
        Create VM by importing from OVF or OVA file.

        Args:
            file_path: Path to OVF/OVA file
            try_extract: If True, attempt to extract OVA files
            ctx_manager: Optional context manager for status updates
            stop_event: Optional threading event to signal cancellation
            log_file: Optional path to log file for command output
            silent: If True, suppress log output

        Returns:
            Tuple of (return_code, output)
        """
        pass

    # ==================== Configuration ====================

    def set_video_mode_hint(
        self,
        width: int = 1920,
        height: int = 1080,
        depth: int = 32,
        ctx_manager=None,
        stop_event: Optional[threading.Event] = None,
        log_file: Optional[Path] = None,
        silent: bool = False
    ):
        """
        Set video mode hint for the VM (OPTIONAL feature).

        This is an optional feature that not all hypervisors support.
        Default implementation raises UnsupportedFeatureException.
        Hypervisors that support this should override.

        Args:
            width: Screen width in pixels
            height: Screen height in pixels
            depth: Color depth in bits
            ctx_manager: Optional context manager for status updates
            stop_event: Optional threading event to signal cancellation
            log_file: Optional path to log file for command output
            silent: If True, suppress log output

        Raises:
            UnsupportedFeatureException: If hypervisor doesn't support video mode hints
        """
        from adare.hypervisor.exceptions import UnsupportedFeatureException
        raise UnsupportedFeatureException(
            f"{self.__class__.__name__} does not support video mode hints"
        )

    # ==================== Utility Methods ====================

    @abstractmethod
    async def wait_until_fully_booted(
        self,
        timeout: int = 300,
        ctx_manager=None,
        stop_event: Optional[threading.Event] = None
    ):
        """
        Wait until VM is fully booted and accessible.

        Args:
            timeout: Maximum time to wait in seconds
            ctx_manager: Optional context manager for status updates
            stop_event: Optional threading event to signal cancellation

        Returns:
            True if VM is booted, False if timeout or cancelled
        """
        pass

    @abstractmethod
    def queue_command(self, command: str, description: str = None):
        """
        Add a command to the queue for batch execution.

        Args:
            command: Command to queue
            description: Optional description of the command
        """
        pass

    @abstractmethod
    async def execute_queued_commands(
        self,
        ctx_manager=None,
        stop_event: Optional[threading.Event] = None,
        log_file: Optional[Path] = None,
        silent: bool = False,
        **kwargs
    ):
        """
        Execute all queued commands in a single batch.

        Args:
            ctx_manager: Optional context manager for status updates
            stop_event: Optional threading event to signal cancellation
            log_file: Optional path to log file for command output
            silent: If True, suppress log output
            **kwargs: Hypervisor-specific parameters

        Returns:
            Return code (0 for success, non-zero for failure)
        """
        pass

    @abstractmethod
    def cleanup_background_processes(self):
        """
        Kill all tracked background processes in the guest.

        This should clean up any processes started with background=True.
        """
        pass

    # ==================== Static/Class Methods ====================

    @classmethod
    @abstractmethod
    def get_vm_by_name(cls, vm_name: str, manager=None):
        """
        Get VM information by name and create a VM instance.

        Args:
            vm_name: Name of the VM to retrieve
            manager: Optional hypervisor manager instance

        Returns:
            VM instance if found, None otherwise
        """
        pass

    @staticmethod
    @abstractmethod
    def get_vm_uuid_by_name(vm_name: str) -> Optional[str]:
        """
        Get VM UUID/identifier by name.

        Args:
            vm_name: Name of the VM

        Returns:
            VM UUID/identifier if found, None otherwise
        """
        pass

    @staticmethod
    @abstractmethod
    def verify_vm_exists_by_uuid(uuid: str) -> bool:
        """
        Verify if a VM exists by its UUID/identifier.

        Args:
            uuid: VM UUID/identifier

        Returns:
            True if VM exists, False otherwise
        """
        pass

    @staticmethod
    @abstractmethod
    def get_vm_info_by_uuid(uuid: str) -> Optional[Dict[str, Any]]:
        """
        Get VM information by UUID/identifier.

        Args:
            uuid: VM UUID/identifier

        Returns:
            Dictionary of VM information if found, None otherwise
        """
        pass

    @staticmethod
    @abstractmethod
    def get_vm_name_by_uuid(uuid: str) -> Optional[str]:
        """
        Get VM name by UUID/identifier.

        Args:
            uuid: VM UUID/identifier

        Returns:
            VM name if found, None otherwise
        """
        pass

    # ==================== VM Identifier Property ====================

    @property
    def vm_identifier(self) -> str:
        """
        Get hypervisor-specific VM identifier.

        This could be a UUID (VirtualBox), domain name (libvirt/QEMU), etc.
        Default implementation returns vm_name.
        Hypervisors should override if they use different identifiers.

        Returns:
            VM identifier string
        """
        return self.vm_name
