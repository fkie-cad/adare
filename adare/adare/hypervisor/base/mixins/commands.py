"""
Abstract command execution mixin for hypervisor VMs.

All hypervisor implementations must provide command execution functionality.
"""
import logging
import threading
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional

log = logging.getLogger(__name__)


class AbstractCommandMixin(ABC):
    """
    Abstract mixin class defining command execution operations for VMs.

    All hypervisor implementations must implement these command execution operations.
    These are typically low-level operations used by higher-level VM methods.
    """

    @abstractmethod
    async def _execute_streaming_command_async(
        self,
        args: List[str],
        log_file: Optional[Path] = None,
        stop_event: Optional[threading.Event] = None,
        silent: bool = False,
        ctx_manager=None,
        operation_name: str = "command execution"
    ):
        """
        Execute a hypervisor command asynchronously with streaming output.

        This is a low-level method used by other VM operations to execute
        hypervisor-specific commands (e.g., VBoxManage, qemu commands).

        Args:
            args: Command arguments list (excluding the executable)
            log_file: Optional path to log file for command output
            stop_event: Optional threading event to signal cancellation
            silent: If True, suppress log output
            ctx_manager: Optional context manager for status updates
            operation_name: Description of the operation for logging

        Returns:
            Tuple of (return_code, stdout, stderr)
        """
        pass

    @abstractmethod
    def _execute_streaming_command(
        self,
        args: List[str],
        log_file: Optional[Path] = None,
        stop_event: Optional[threading.Event] = None,
        silent: bool = False,
        ctx_manager=None,
        operation_name: str = "command execution",
        timeout: Optional[int] = None
    ) -> int:
        """
        Execute a hypervisor command synchronously with streaming output.

        This is a low-level method used by other VM operations to execute
        hypervisor-specific commands in a synchronous context.

        Args:
            args: Command arguments list (excluding the executable)
            log_file: Optional path to log file for command output
            stop_event: Optional threading event to signal cancellation
            silent: If True, suppress log output
            ctx_manager: Optional context manager for status updates
            operation_name: Description of the operation for logging
            timeout: Optional timeout in seconds

        Returns:
            Return code from command execution
        """
        pass

    @abstractmethod
    def _build_guest_command_args(
        self,
        command: str,
        background: bool = False,
        cwd: Optional[str] = None,
        win_noprofile: bool = True,
        use_cmd: bool = False,
        admin: bool = False
    ) -> List[str]:
        """
        Build hypervisor-specific command arguments for guest execution.

        This method constructs the command-line arguments needed to execute
        a command inside the guest VM using the hypervisor's guest control mechanism.

        Args:
            command: Command to execute in guest
            background: If True, run command in background
            cwd: Optional working directory for command execution
            win_noprofile: Windows-specific: use -NoProfile for PowerShell
            use_cmd: Windows-specific: use cmd.exe instead of PowerShell
            admin: If True, run with elevated privileges

        Returns:
            List of command arguments
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
