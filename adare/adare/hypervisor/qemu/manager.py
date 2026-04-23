"""
QEMU Manager for handling QEMU operations in a thread-safe manner.

Implements AbstractHypervisorManager for QEMU-specific operations.
"""
import logging
import platform
import queue
import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

try:
    import libvirt
except ImportError:
    libvirt = None

from adare.hypervisor.base.manager import AbstractHypervisorManager
from adare.hypervisor.exceptions import HypervisorException, VMImportException

log = logging.getLogger(__name__)


class QEMUManager(AbstractHypervisorManager):
    """Thread-safe manager for QEMU operations."""

    def __init__(self):
        super().__init__()
        from adare.config import HYPERVISOR_CONFIGS
        from adare.hypervisor.executable_manager import ExecutableManager

        qemu_config = HYPERVISOR_CONFIGS.get('qemu', {})

        # Apple Silicon note: aarch64 guests use HVF acceleration.
        # x86_64 guests on Apple Silicon are blocked in lifecycle.py (per-VM check).
        if platform.system() == 'Darwin' and platform.machine() == 'arm64':
            log.info("QEMU on Apple Silicon — HVF acceleration available for aarch64 guests")

        # Initialize executable manager (validates executables exist)
        self.executables = ExecutableManager('qemu', qemu_config)

        # Store defaults from config
        self.default_machine = qemu_config.get('default_machine', 'pc')
        self.default_accel = qemu_config.get('default_accel', 'kvm')
        self.default_drive_format = qemu_config.get('default_drive_format', 'qcow2')

        # Check for guestfish CLI tool
        if shutil.which('guestfish'):
            log.debug("guestfish CLI tool available.")
        else:
            log.warning("guestfish command not found. "
                       "File operations when VM is stopped will not work. "
                       "Install with: sudo apt install libguestfs-tools")

        # Initialize libvirt connection
        self.libvirt_conn = None
        use_libvirt = qemu_config.get('use_libvirt', True)

        if use_libvirt:
            try:
                import libvirt
                libvirt_uri = qemu_config.get('libvirt_uri', 'qemu:///session')
                # NOTE: No stderr redirect here - connection errors should be visible during initialization.
                # LibvirtStderrRedirect requires an experiment log file, which doesn't exist during manager init.
                # If libvirtd is not running, we want the error to fail loudly.
                self.libvirt_conn = libvirt.open(libvirt_uri)

                if not self.libvirt_conn:
                    from adare.hypervisor.exceptions import HypervisorException
                    raise HypervisorException(f"Failed to connect to libvirt at {libvirt_uri}")

                log.info(f"Connected to libvirt ({libvirt_uri})")

                # Validate virsh executable availability
                if shutil.which('virsh'):
                    log.debug("virsh command available")
                else:
                    log.warning("virsh command not found. Install libvirt-clients package.")

            except ImportError:
                from adare.hypervisor.exceptions import HypervisorException
                raise HypervisorException(
                    "libvirt Python bindings not found. "
                    "Install with: pip install libvirt-python"
                ) from None
            except libvirt.libvirtError as e:
                from adare.hypervisor.exceptions import HypervisorException
                if platform.system() == 'Darwin':
                    raise HypervisorException(
                        f"Failed to connect to libvirt daemon: {e}. "
                        f"On macOS, install with: brew install libvirt && brew services start libvirt"
                    ) from e
                raise HypervisorException(
                    f"Failed to connect to libvirt daemon: {e}. "
                    f"Ensure libvirtd is running: sudo systemctl start libvirtd"
                ) from e
        else:
            log.info("libvirt integration disabled in config (use_libvirt=False)")

        log.info("Initialized QEMUManager")

    def __del__(self):
        """Cleanup: close libvirt connection on manager destruction."""
        if hasattr(self, 'libvirt_conn') and self.libvirt_conn:
            try:
                self.libvirt_conn.close()
                log.debug("Closed libvirt connection")
            except libvirt.libvirtError as e:
                log.warning(f"Error closing libvirt connection: {e}")

    def _worker_loop(self):
        """Main worker loop for executing queued functions."""
        log.debug("QEMUManager worker loop started.")
        while True:
            func, args, kwargs, result_queue = self._cmd_queue.get()
            try:
                result = func(*args, **kwargs)
                result_queue.put((result, None))
            except Exception as e:
                # Intentional: worker must catch all exceptions to relay to caller
                log.error(f"Exception in worker loop for function {func.__name__}: {e}")
                result_queue.put((None, e))

    def run(self, func: Callable, *args, **kwargs) -> Any:
        """Execute a function in the worker thread and return its result."""
        result_queue = queue.Queue()
        self._cmd_queue.put((func, args, kwargs, result_queue))
        result, error = result_queue.get()
        if error:
            log.error(f"Error running function {func.__name__}: {error}")
            raise error
        return result

    async def run_async(self, func: Callable, *args, **kwargs) -> Any:
        """Run an async function directly without the worker thread."""
        try:
            return await func(*args, **kwargs)
        except Exception as e:
            # Intentional: async executor must catch all exceptions to log and relay to caller
            log.error(f"Error running async function {func.__name__}: {e}")
            raise e

    async def import_vm_async(self, vm_file_path: Path, vm_name: str, environment_ulid: str | None = None):
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
        from adare.config import get_vm_credentials
        from adare.hypervisor.qemu.vm import QEMUVM

        log.info(f"Importing QEMU VM '{vm_name}' from '{vm_file_path}' (environment: {environment_ulid})")

        # Detect guest OS from file extension or assume Linux as default
        # This is a simple heuristic - could be enhanced with OVF parsing
        guest_os = "linux"  # Default guest OS

        # Get credentials based on guest OS
        username, password = get_vm_credentials(guest_os)

        # Determine if this is an external VM and set disk_path accordingly
        from adare.backend.vm.commands import _is_vm_managed

        is_external = not _is_vm_managed(vm_file_path)
        disk_path = None
        detected_format = None

        if is_external:
            # Detect format for external VMs
            detected_format = QEMUVM._detect_disk_format_static(
                vm_file_path,
                self.executables.qemu_img
            )
            log.debug(f"External VM detected, format: {detected_format}")

            if detected_format == 'qcow2':
                # Use original file directly
                disk_path = str(vm_file_path.resolve())
                log.debug(f"External qcow2 VM - using original: {disk_path}")
            else:
                # Will convert next to original
                disk_path = str(vm_file_path.parent / f"{vm_file_path.stem}_adare_converted.qcow2")
                log.debug(f"External non-qcow2 VM - will convert to: {disk_path}")

        # Create QEMUVM instance
        vm = QEMUVM(
            vm_name=vm_name,
            guest_os=guest_os,
            manager=self,
            username=username,
            password=password,
            executables=self.executables,
            disk_path=disk_path  # Pass disk_path for external VMs
        )

        try:
            # Skip conversion for external qcow2 files
            if is_external and detected_format == 'qcow2':
                log.info(f"Skipping conversion for external qcow2: {vm_file_path}")
                vm._save_vm_config()
                return vm

            # Import the VM from OVF/OVA file (converts to qcow2)
            return_code, stdout = await vm.create_from_ovf_or_ova(
                file_path=vm_file_path,
                silent=False
            )

            if return_code != 0:
                error_msg = f"QEMU VM import failed with return code {return_code}"
                if stdout:
                    error_msg += f": {stdout}"
                log.error(f"{error_msg}")
                raise VMImportException(vm_name, error_msg)

            log.info(f"Successfully imported QEMU VM '{vm_name}' from '{vm_file_path}'")
            return vm

        except (VMImportException, HypervisorException, subprocess.CalledProcessError, OSError) as e:
            log.error(f"Failed to import QEMU VM '{vm_name}' from '{vm_file_path}': {e}")
            raise VMImportException(vm_name, f"QEMU VM import failed: {e}") from e
