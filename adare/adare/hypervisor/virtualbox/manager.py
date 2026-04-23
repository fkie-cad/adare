"""
VirtualBox Manager for handling VirtualBox operations in a thread-safe manner.

Implements AbstractHypervisorManager for VirtualBox-specific operations.
"""
import logging
import queue
from collections.abc import Callable
from pathlib import Path
from typing import Any

from adare.hypervisor.base.manager import AbstractHypervisorManager

log = logging.getLogger(__name__)


class VirtualBoxManager(AbstractHypervisorManager):
    """Thread-safe manager for VirtualBox operations."""

    def __init__(self):
        super().__init__()
        from adare.config import HYPERVISOR_CONFIGS
        from adare.hypervisor.executable_manager import ExecutableManager

        vbox_config = HYPERVISOR_CONFIGS.get('virtualbox', {})

        # Initialize executable manager (validates executables exist)
        self.executables = ExecutableManager('virtualbox', vbox_config)

        # Store defaults from config
        self.default_graphics = vbox_config.get('default_graphics', 'vmsvga')
        self.default_vram = vbox_config.get('default_vram', 128)

        log.info("Initialized VirtualBoxManager")

    def _worker_loop(self):
        """Main worker loop for executing queued functions."""
        log.debug("VirtualBoxManager worker loop started.")
        while True:
            func, args, kwargs, result_queue = self._cmd_queue.get()
            try:
                log.debug(f"Executing function {func.__name__} with args={args} kwargs={kwargs}")
                result = func(*args, **kwargs)
                result_queue.put((result, None))
            except Exception as e:
                log.error(f"Exception in worker loop for function {func.__name__}: {e}")
                result_queue.put((None, e))

    def run(self, func: Callable, *args, **kwargs) -> Any:
        """Execute a function in the worker thread and return its result."""
        log.debug(f"Queueing function {func.__name__} for execution.")
        result_queue = queue.Queue()
        self._cmd_queue.put((func, args, kwargs, result_queue))
        result, error = result_queue.get()
        if error:
            log.error(f"Error running function {func.__name__}: {error}")
            raise error
        log.debug(f"Function {func.__name__} executed successfully.")
        return result

    async def run_async(self, func: Callable, *args, **kwargs) -> Any:
        """Run an async function directly without the worker thread."""
        log.debug(f"Executing async function {func.__name__} with args={args} kwargs={kwargs}")
        try:
            result = await func(*args, **kwargs)
            log.debug(f"Async function {func.__name__} executed successfully.")
            return result
        except Exception as e:
            log.error(f"Error running async function {func.__name__}: {e}")
            raise e

    async def import_vm_async(self, vm_file_path: Path, vm_name: str, environment_ulid: str | None = None):
        """
        Import a VM from OVF/OVA file asynchronously.

        Args:
            vm_file_path: Path to the OVF/OVA file
            vm_name: Name for the imported VM
            environment_ulid: Optional environment ULID for context

        Returns:
            VirtualBoxVM: The imported VM instance

        Raises:
            VMImportException: If import fails
        """
        # Import here to avoid circular dependency
        from adare.config import get_vm_credentials
        from adare.hypervisor.virtualbox.vm import VirtualBoxVM

        log.info(f"Importing VM '{vm_name}' from '{vm_file_path}' (environment: {environment_ulid})")

        # Detect guest OS from file extension or assume Linux as default
        # This is a simple heuristic - could be enhanced with OVF parsing
        guest_os = "Linux_64"  # Default guest OS type for VirtualBox

        # Get credentials based on guest OS
        username, password = get_vm_credentials(guest_os)

        # Create VirtualBoxVM instance
        vm = VirtualBoxVM(
            vm_name=vm_name,
            guest_os=guest_os,
            manager=self,
            username=username,
            password=password,
            executables=self.executables
        )

        try:
            # Import the VM from OVF/OVA file
            return_code, stdout = await vm.create_from_ovf_or_ova(
                file_path=vm_file_path,
                silent=False
            )

            if return_code != 0:
                error_msg = f"VM import failed with return code {return_code}"
                if stdout:
                    error_msg += f": {stdout}"
                log.error(error_msg)
                raise Exception(error_msg)

            log.info(f"Successfully imported VM '{vm_name}' from '{vm_file_path}'")
            return vm

        except Exception as e:
            log.error(f"Failed to import VM '{vm_name}' from '{vm_file_path}': {e}")
            raise
