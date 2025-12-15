"""
QEMU Manager for handling QEMU operations in a thread-safe manner.

Implements AbstractHypervisorManager for QEMU-specific operations.
"""
import asyncio
import logging
import queue
import shutil
import threading
from pathlib import Path
from typing import Any, Callable, Optional

from adare.hypervisor.base.manager import AbstractHypervisorManager
from adare.hypervisor.exceptions import VMImportException

log = logging.getLogger(__name__)


class QEMUManager(AbstractHypervisorManager):
    """Thread-safe manager for QEMU operations."""

    def __init__(self):
        super().__init__()
        self._check_qemu_availability()
        log.debug("QEMUManager initialized and worker thread started.")

    def _check_qemu_availability(self):
        """Check if required QEMU binaries are available."""
        from adare.config import HYPERVISOR_CONFIGS

        qemu_config = HYPERVISOR_CONFIGS.get('qemu', {})
        qemu_system_exe = qemu_config.get('qemu_system_exe', 'qemu-system-x86_64')
        qemu_img_exe = qemu_config.get('qemu_img_exe', 'qemu-img')

        # Check for QEMU system executable
        if not shutil.which(qemu_system_exe):
            log.warning(f"CLAUDE: QEMU system executable '{qemu_system_exe}' not found in PATH. "
                       f"QEMU VMs may fail to start.")

        # Check for qemu-img
        if not shutil.which(qemu_img_exe):
            log.warning(f"CLAUDE: qemu-img executable '{qemu_img_exe}' not found in PATH. "
                       f"VM import and snapshot operations may fail.")

        # Check for libguestfs (python bindings)
        try:
            import guestfs
            log.debug("CLAUDE: libguestfs Python bindings available.")
        except ImportError:
            log.warning("CLAUDE: libguestfs Python bindings not available. "
                       "File operations when VM is stopped will not work. "
                       "Install python3-guestfs or python-guestfs package.")

    def _worker_loop(self):
        """Main worker loop for executing queued functions."""
        log.debug("QEMUManager worker loop started.")
        while True:
            func, args, kwargs, result_queue = self._cmd_queue.get()
            try:
                log.debug(f"CLAUDE: Executing function {func.__name__} with args={args} kwargs={kwargs}")
                result = func(*args, **kwargs)
                result_queue.put((result, None))
            except Exception as e:
                log.error(f"CLAUDE: Exception in worker loop for function {func.__name__}: {e}")
                result_queue.put((None, e))

    def run(self, func: Callable, *args, **kwargs) -> Any:
        """Execute a function in the worker thread and return its result."""
        log.debug(f"CLAUDE: Queueing function {func.__name__} for execution.")
        result_queue = queue.Queue()
        self._cmd_queue.put((func, args, kwargs, result_queue))
        result, error = result_queue.get()
        if error:
            log.error(f"CLAUDE: Error running function {func.__name__}: {error}")
            raise error
        log.debug(f"CLAUDE: Function {func.__name__} executed successfully.")
        return result

    async def run_async(self, func: Callable, *args, **kwargs) -> Any:
        """Run an async function directly without the worker thread."""
        log.debug(f"CLAUDE: Executing async function {func.__name__} with args={args} kwargs={kwargs}")
        try:
            result = await func(*args, **kwargs)
            log.debug(f"CLAUDE: Async function {func.__name__} executed successfully.")
            return result
        except Exception as e:
            log.error(f"CLAUDE: Error running async function {func.__name__}: {e}")
            raise e

    async def import_vm_async(self, vm_file_path: Path, vm_name: str, environment_ulid: Optional[str] = None):
        """
        Import a VM from OVF/OVA file asynchronously.

        Converts VM disk to qcow2 format and creates QEMU VM configuration.

        Args:
            vm_file_path: Path to the OVF/OVA file
            vm_name: Name for the imported VM
            environment_ulid: Optional environment ULID for context

        Returns:
            QEMUVM: The imported VM instance

        Raises:
            VMImportException: If import fails
        """
        # Import here to avoid circular dependency
        from adare.hypervisor.qemu.vm import QEMUVM
        from adare.config import get_vm_credentials

        log.info(f"CLAUDE: Importing QEMU VM '{vm_name}' from '{vm_file_path}' (environment: {environment_ulid})")

        # Detect guest OS from file extension or assume Linux as default
        # This is a simple heuristic - could be enhanced with OVF parsing
        guest_os = "linux"  # Default guest OS

        # Get credentials based on guest OS
        username, password = get_vm_credentials(guest_os)

        # Create QEMUVM instance
        vm = QEMUVM(
            vm_name=vm_name,
            guest_os=guest_os,
            manager=self,
            username=username,
            password=password
        )

        try:
            # Import the VM from OVF/OVA file (converts to qcow2)
            return_code, stdout = await vm.create_from_ovf_or_ova(
                file_path=vm_file_path,
                silent=False
            )

            if return_code != 0:
                error_msg = f"QEMU VM import failed with return code {return_code}"
                if stdout:
                    error_msg += f": {stdout}"
                log.error(f"CLAUDE: {error_msg}")
                raise VMImportException(error_msg)

            log.info(f"CLAUDE: Successfully imported QEMU VM '{vm_name}' from '{vm_file_path}'")
            return vm

        except Exception as e:
            log.error(f"CLAUDE: Failed to import QEMU VM '{vm_name}' from '{vm_file_path}': {e}")
            raise VMImportException(f"QEMU VM import failed: {e}")
