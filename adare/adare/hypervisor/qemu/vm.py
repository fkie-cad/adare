"""
QEMU VM - Main VM class with modular operations.

Implements AbstractVM for QEMU-specific VM management using:
- Direct QEMU command-line execution
- libguestfs for file operations when VM is stopped
- QEMU Guest Agent for runtime command execution
- qcow2 internal snapshots
"""
import asyncio
import json
import logging
import os
import platform
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

try:
    import libvirt
except ImportError:
    libvirt = None

from adare.hypervisor.base.vm import AbstractVM
from adare.hypervisor.exceptions import (
    VMImportException,
    VMAlreadyRunningException,
    HypervisorException,
    VMStartException
)
from adare.hypervisor.qemu.manager import QEMUManager
from adare.hypervisor.qemu.mixins.configuration import ConfigurationMixin
from adare.hypervisor.qemu.mixins.disk import DiskManagementMixin
from adare.hypervisor.qemu.mixins.commands import CommandExecutionMixin
from adare.hypervisor.qemu.mixins.snapshots import SnapshotMixin
from adare.hypervisor.qemu.mixins.networking import NetworkingMixin
from adare.hypervisor.qemu.mixins.registry import RegistryMixin
from adare.hypervisor.qemu.models import QEMUVMConfig, CommandResult
from adare.hypervisor.qemu.libvirt_stderr_redirect import (
    LibvirtStderrRedirect,
    get_experiment_log_file
)

log = logging.getLogger(__name__)


class QEMUVM(RegistryMixin, ConfigurationMixin, DiskManagementMixin, CommandExecutionMixin, SnapshotMixin, NetworkingMixin, AbstractVM):
    """
    QEMU VM management class with modular operations.
    Inherits from mixins for registry, configuration, disk management, command execution, snapshots, and networking.
    """

    def __init__(
        self,
        vm_name: str,
        guest_os: str,
        manager: 'QEMUManager',
        username: str,
        password: str,
        executables: 'ExecutableManager',
        cpus: int = 2,
        ram: int = 2048,
        machine: str = 'pc',
        accel: str = 'kvm',
        drive_format: str = 'qcow2',
        disk_path: Optional[str] = None,
        architecture: str = 'x86_64'
    ):
        self.vm_name = vm_name
        self.guest_os = guest_os
        self.architecture = architecture
        self.username = username
        self.password = password
        self.cpus = cpus
        self.ram = ram
        self.machine = machine
        self.accel = accel
        self.drive_format = drive_format
        self.host_os = platform.system().lower()
        self.manager = manager
        self.executables = executables  # Store executable manager
        self._background_pids = []
        self._command_queue = []
        self._qemu_process = None  # Running QEMU process
        self._external_disk_path = disk_path  # Optional external disk path for --no-copy mode

        # libvirt integration
        self._libvirt_conn = None  # Lazy initialization - will use manager's connection
        self._libvirt_domain = None  # libvirt domain object

        # PATH discovery cache
        self._cached_guest_path = None  # Cached PATH from guest discovery
        self._path_discovery_attempted = False  # Track if we've tried discovery to prevent retries

        # Screen resolution tracking for coordinate normalization (USB tablet uses 0-32767 range)
        self._screen_width = None   # Current screen width in pixels
        self._screen_height = None  # Current screen height in pixels
        self._resolution_last_updated = None  # Timestamp of last resolution update

        # USB tablet activation tracking (ensures BTN events route to correct device)
        self._tablet_activated = False

        # Load or create VM config
        self.config = self._load_or_create_vm_config()

        log.debug(f"Initialized QEMUVM for '{self.vm_name}' ({self.guest_os})")

    def _ensure_libvirt_domain(self):
        """
        Ensure libvirt domain object is available, looking it up if needed.

        This is the single point of lazy initialization for _libvirt_domain.
        All code paths that need the domain object should call this method
        instead of performing ad-hoc lookups.

        Returns:
            libvirt.virDomain: The domain object

        Raises:
            HypervisorException: If domain cannot be found or connection fails
        """
        if self._libvirt_domain:
            return self._libvirt_domain

        conn = self._get_libvirt_connection()
        if not conn:
            raise HypervisorException(
                f"Cannot look up domain '{self.vm_name}': libvirt connection not available"
            )

        log_file = get_experiment_log_file()
        try:
            with LibvirtStderrRedirect(log_file=log_file, suppress_console=True):
                self._libvirt_domain = conn.lookupByName(self.vm_name)
        except libvirt.libvirtError as e:
            raise HypervisorException(
                f"Cannot look up domain '{self.vm_name}': {e}"
            )

        return self._libvirt_domain

    async def create(
        self,
        ctx_manager=None,
        stop_event=None,
        log_file: Optional[Path] = None,
        silent: bool = False
    ) -> int:
        """
        Create a new QEMU VM disk.

        Args:
            ctx_manager: Optional context manager for status updates
            stop_event: Optional threading event to signal cancellation
            log_file: Optional path to log file
            silent: If True, suppress log output

        Returns:
            Return code (0 for success, non-zero for failure)
        """
        async def _create_async():
            if not silent:
                log.debug(f"Creating QEMU VM '{self.vm_name}' with "
                        f"{self.cpus} CPUs, {self.ram}MB RAM")

            qemu_img_exe = self.executables.qemu_img

            # Create qcow2 disk (default 50GB)
            disk_path = self.config.disk_path
            args = [qemu_img_exe, 'create', '-f', 'qcow2', disk_path, '50G']

            returncode, stdout, stderr = await self._execute_streaming_command_async(
                args,
                log_file=log_file,
                stop_event=stop_event,
                silent=silent,
                ctx_manager=ctx_manager,
                operation_name="disk creation"
            )

            if returncode == 0:
                if not silent:
                    log.debug(f"VM '{self.vm_name}' disk created at {disk_path}")
                # Save config
                self._save_vm_config()
            else:
                log.error(f"Failed to create VM disk: {stderr}")

            return returncode

        return await self.manager.run_async(_create_async)

    def _get_libvirt_connection(self):
        """
        Get thread-safe libvirt connection (creates new connection per instance).

        Instead of using the manager's shared connection, creates a new connection
        for this QEMUVM instance. This ensures thread-safety when parallel tasks
        check instance states concurrently - each thread gets its own QEMUVM instance
        with an isolated libvirt connection.
        """
        if not self._libvirt_conn:
            try:
                import libvirt
                from adare.config import HYPERVISOR_CONFIGS

                qemu_config = HYPERVISOR_CONFIGS.get('qemu', {})
                libvirt_uri = qemu_config.get('libvirt_uri', 'qemu:///session')

                # Create new connection for this QEMUVM instance (thread-safe)
                # Don't use self.manager.libvirt_conn to avoid shared connection issues
                self._libvirt_conn = libvirt.open(libvirt_uri)
                log.debug(f"Created thread-local libvirt connection for {self.vm_name}")
            except libvirt.libvirtError as e:
                log.warning(f"Failed to create libvirt connection: {e}")
                return None

        return self._libvirt_conn

    def _define_libvirt_domain(self):
        """
        Define libvirt domain from XML configuration.

        Creates a libvirt domain definition that makes the VM visible in
        virsh and virt-manager while preserving all ADARE functionality.

        Returns:
            libvirt.virDomain: Domain object

        Raises:
            HypervisorException: If domain definition fails
        """
        from adare.hypervisor.qemu.libvirt_xml import generate_domain_xml
        import libvirt

        log.debug(f"Defining libvirt domain for VM: {self.vm_name}")

        # Generate XML domain definition
        # Include virtiofs shares if configured AND supported (avoid session mode)
        virtiofs_shares = None
        
        # Check if virtiofs is supported (requires system mode, not session)
        from adare.config import HYPERVISOR_CONFIGS
        qemu_config = HYPERVISOR_CONFIGS.get('qemu', {})
        libvirt_uri = qemu_config.get('libvirt_uri', 'qemu:///session')
        is_session_mode = 'session' in libvirt_uri
        
        if self.config.virtiofs_enabled and self.config.virtiofs_shares:
            if is_session_mode:
                log.warning(f"Disabling virtiofs shares for {self.vm_name} "
                           f"(not supported in session mode: {libvirt_uri}). "
                           f"Falling back to libguestfs file transfer.")
                virtiofs_shares = None
            else:
                virtiofs_shares = self.config.virtiofs_shares
                log.debug(f"Including {len(virtiofs_shares)} virtio-fs shares in domain")

        xml = generate_domain_xml(
            self.config,
            display_enabled=self.config.display_enabled,
            vnc_port=self.config.vnc_port,
            virtiofs_shares=virtiofs_shares
        )

        log.debug(f"Generated libvirt XML for {self.vm_name}")

        # Get libvirt connection
        conn = self._get_libvirt_connection()

        if not conn:
            raise HypervisorException(
                "libvirt connection not available. Ensure libvirtd is running and "
                "libvirt integration is enabled in config."
            )

        # Check if domain already exists
        log_file = get_experiment_log_file()
        try:
            with LibvirtStderrRedirect(log_file=log_file, suppress_console=True):
                existing_domain = conn.lookupByName(self.vm_name)
                log.debug(f"Domain '{self.vm_name}' already exists, undefining...")
                # Undefine existing domain (will redefine with new XML)
                if existing_domain.isActive():
                    log.warning(f"Domain '{self.vm_name}' is running, destroying first...")
                    existing_domain.destroy()
                existing_domain.undefine()
        except libvirt.libvirtError as e:
            # Domain doesn't exist, which is fine
            if 'Domain not found' not in str(e):
                log.warning(f"Error checking for existing domain: {e}")

        # Define the domain
        try:
            with LibvirtStderrRedirect(log_file=log_file, suppress_console=True):
                domain = conn.defineXML(xml)
            log.debug(f"Defined libvirt domain '{self.vm_name}' (visible in virsh/virt-manager)")

            # Update config with libvirt domain name
            self.config.libvirt_domain_name = self.vm_name
            self._save_vm_config()

            return domain

        except libvirt.libvirtError as e:
            raise HypervisorException(
                f"Failed to define libvirt domain '{self.vm_name}': {e}"
            )

    def _build_qemu_command(self) -> List[str]:
        """
        Build QEMU command line for starting VM.

        Supports both BIOS and UEFI boot modes. For UEFI, uses OVMF firmware
        and q35 machine type for better compatibility with modern Windows VMs.

        Returns:
            List of command arguments
        """
        qemu_system_exe = self.executables.qemu_system

        # Determine machine type (use q35 for UEFI if currently pc)
        machine_type = self.machine
        if self.config.boot_mode == 'uefi' and self.machine == 'pc':
            machine_type = 'q35'

        cmd = [
            qemu_system_exe,
            '-name', self.vm_name,
            '-machine', f"{machine_type},accel={self.accel}",
            '-cpu', 'host',
            '-smp', str(self.cpus),
            '-m', str(self.ram),
        ]

        # Add UEFI firmware if boot mode is uefi
        if self.config.boot_mode == 'uefi':
            from adare.hypervisor.qemu.firmware import find_ovmf_firmware, create_nvram_for_vm
            ovmf_code, _ = find_ovmf_firmware(self.architecture)

            # Create/get NVRAM for this VM
            vm_config_dir = Path(self.config.disk_path).parent
            nvram_path = create_nvram_for_vm(self.vm_name, vm_config_dir, architecture=self.architecture)

            # Add OVMF firmware drives
            cmd.extend([
                '-drive', f'if=pflash,format=raw,readonly=on,file={ovmf_code}',
                '-drive', f'if=pflash,format=raw,file={nvram_path}'
            ])

        # Add main disk
        cmd.extend([
            '-drive', f"file={self.config.disk_path},format={self.drive_format},if=virtio",
            # '-display', 'none',  # Headless
            '-daemonize',  # Run as daemon
            '-pidfile', self.config.pid_file_path
        ])

        from adare.config import HYPERVISOR_CONFIGS
        
        # Always redirect QEMU debug/serial logs to /tmp to avoid permission issues
        # (QEMU process user vs Experiment runner user)
        # This is safer than relying on config checks or permission inheritance
        if self.config.qemu_debug_log_path:
             log_path = f"/tmp/adare_qemu_debug_{self.vm_name}.log"
             cmd.extend(['-D', log_path])
             cmd.extend(['-d', 'guest_errors,cpu_reset,unimp'])

        # Add serial console redirect if configured
        if self.config.serial_console_log_path:
            serial_path = f"/tmp/adare_serial_{self.vm_name}.log"
            cmd.extend([
                '-chardev', f'file,id=serial0,path={serial_path}',
                '-serial', 'chardev:serial0'
            ])

        # Add QMP monitor socket
        cmd.extend([
            '-qmp', f"unix:{self.config.qmp_socket_path},server=on,wait=off"
        ])

        # Add QEMU Guest Agent socket
        cmd.extend([
            '-chardev', f"socket,path={self.config.guest_agent_socket_path},server=on,wait=off,id=qga0",
            '-device', 'virtio-serial',
            '-device', 'virtserialport,chardev=qga0,name=org.qemu.guest_agent.0'
        ])

        # Add network with port forwarding
        netdev_args = f"user,id=net0"

        # Add port forwarding rules
        for name, rule in self.config.port_forwarding_rules.items():
            protocol = rule['protocol']
            host_port = rule['host_port']
            guest_port = rule['guest_port']
            host_ip = rule.get('host_ip', '')
            guest_ip = rule.get('guest_ip', '')

            hostfwd = f"{protocol}:{host_ip}:{host_port}-{guest_ip}:{guest_port}" if host_ip else f"{protocol}::{host_port}-:{guest_port}"
            netdev_args += f",hostfwd={hostfwd}"

        cmd.extend(['-netdev', netdev_args])
        cmd.extend(['-device', 'virtio-net-pci,netdev=net0'])

        log.debug(f"QEMU command: {' '.join(cmd)}")
        return cmd

    async def start(
        self,
        ctx_manager=None,
        raise_if_running: bool = False,
        stop_event=None,
        log_file: Optional[Path] = None,
        silent: bool = False,
        stage_ctx=None
    ) -> int:
        """
        Start the QEMU VM via libvirt.

        Creates libvirt domain definition and starts the VM, making it
        visible in virsh and virt-manager.

        Args:
            ctx_manager: Optional context manager for status updates
            raise_if_running: If True, raise exception if VM already running
            stop_event: Optional threading event to signal cancellation
            log_file: Optional path to log file
            silent: If True, suppress log output
            stage_ctx: Optional stage context for progress updates via sub_msg

        Returns:
            Return code (0 for success)

        Raises:
            VMStartException: If VM fails to start or state cannot be verified
            VMAlreadyRunningException: If VM is already running and raise_if_running=True
            HypervisorException: If libvirt domain definition fails
        """
        async def _start_async():
            import libvirt

            # Check if disk exists
            if not os.path.exists(self.config.disk_path):
                raise VMStartException(self.vm_name, f"VM disk not found at {self.config.disk_path}")

            # Clean up any stale socket files before starting
            for socket_path in [self.config.qmp_socket_path, self.config.guest_agent_socket_path]:
                if os.path.exists(socket_path):
                    try:
                        os.remove(socket_path)
                        log.debug(f"Removed stale socket: {socket_path}")
                    except OSError as e:
                        log.warning(f"Could not remove stale socket {socket_path}: {e}")

            # CRITICAL: Always redefine libvirt domain on each start
            # This ensures the domain XML contains the current overlay disk path,
            # preventing "Cannot access storage file" errors on subsequent runs
            # where the previous overlay was deleted during cleanup.

            # Update stage progress: domain definition (slow libvirt operation)
            if stage_ctx:
                stage_ctx.stage.sub_msg = "Defining libvirt domain XML configuration"
                stage_ctx.set_status(stage_ctx.stage.status)

            try:
                self._libvirt_domain = self._define_libvirt_domain()
            except HypervisorException:
                raise  # Re-raise specific hypervisor exceptions
            except libvirt.libvirtError as e:
                raise VMStartException(self.vm_name, f"Failed to define libvirt domain: {e}")
            except OSError as e:
                raise VMStartException(self.vm_name, f"OS error defining libvirt domain: {e}")

            # Check current state
            try:
                state, _ = self._libvirt_domain.state()
                if state == libvirt.VIR_DOMAIN_RUNNING:
                    message = f"VM '{self.vm_name}' is already running."
                    if raise_if_running:
                        raise VMAlreadyRunningException(message)
                    if not silent:
                        log.debug(f"{message}")
                    return 0
            except libvirt.libvirtError as e:
                log.warning(f"Could not check domain state: {e}")

            if not silent:
                log.debug(f"Starting QEMU VM '{self.vm_name}' via libvirt")

            # Get experiment log file for stderr capture
            log_file = get_experiment_log_file()

            # Update stage progress: starting QEMU process (slow operation)
            if stage_ctx:
                stage_ctx.stage.sub_msg = "Launching QEMU process via libvirt"
                stage_ctx.set_status(stage_ctx.stage.status)

            # Start the domain with stderr redirection to capture C library errors
            try:
                with LibvirtStderrRedirect(log_file=log_file, suppress_console=True):
                    self._libvirt_domain.create()

                # Give libvirt a moment to transition state
                await asyncio.sleep(1)

                # CRITICAL: Validate VM actually started
                # libvirt may fail silently and print to stderr instead of raising exception
                try:
                    is_active = self._libvirt_domain.isActive()
                    state, _ = self._libvirt_domain.state()

                    if not is_active or state != libvirt.VIR_DOMAIN_RUNNING:
                        raise VMStartException(
                            self.vm_name,
                            f"VM '{self.vm_name}' failed to start. "
                            f"Domain state: {state}, Active: {is_active}. "
                            f"Check experiment log for libvirt errors."
                        )
                except libvirt.libvirtError as e:
                    raise VMStartException(
                        self.vm_name,
                        f"Cannot verify VM state after start attempt: {e}"
                    )

                if not silent:
                    log.debug(f"VM '{self.vm_name}' started successfully")

                # Update stage progress: VM started successfully
                if stage_ctx:
                    stage_ctx.stage.sub_msg = ""  # Clear sub_msg on success
                    stage_ctx.set_status(stage_ctx.stage.status)

                return 0

            except VMStartException:
                raise  # Re-raise our own exception
            except VMAlreadyRunningException:
                raise  # Re-raise already running exception
            except libvirt.libvirtError as e:
                if "already running" in str(e).lower():
                    message = f"VM '{self.vm_name}' is already running."
                    if raise_if_running:
                        raise VMAlreadyRunningException(message)
                    if not silent:
                        log.debug(f"{message}")
                    return 0
                else:
                    raise VMStartException(self.vm_name, f"Failed to start VM via libvirt: {e}")
            except OSError as e:
                raise VMStartException(self.vm_name, f"OS error during VM start: {e}")

        return await self.manager.run_async(_start_async)

    async def stop(
        self,
        ctx_manager=None,
        log_file: Optional[Path] = None,
        silent: bool = False,
        force: bool = False,
        timeout: int = 60
    ) -> int:
        """
        Stop the QEMU VM gracefully via libvirt.

        Args:
            ctx_manager: Optional context manager for status updates
            log_file: Optional path to log file
            silent: If True, suppress log output
            force: If True, force immediate shutdown (equivalent to pulling power)
            timeout: Timeout in seconds for graceful shutdown

        Returns:
            Return code (0 for success, non-zero for failure)
        """
        async def _stop_async():
            import libvirt

            if not silent:
                log.debug(f"Stopping QEMU VM '{self.vm_name}' via libvirt")

            log_file_path = get_experiment_log_file()

            # Check if domain exists
            if not self._libvirt_domain:
                try:
                    self._ensure_libvirt_domain()
                except HypervisorException:
                    if not silent:
                        log.debug(f"VM '{self.vm_name}' is not defined in libvirt")
                    return 0

            # Check current state
            try:
                with LibvirtStderrRedirect(log_file=log_file_path, suppress_console=True):
                    state, _ = self._libvirt_domain.state()
                if state == libvirt.VIR_DOMAIN_SHUTOFF:
                    if not silent:
                        log.debug(f"VM '{self.vm_name}' is already stopped")
                    return 0
            except libvirt.libvirtError as e:
                log.warning(f"Could not check domain state: {e}")

            # Stop the domain
            try:
                with LibvirtStderrRedirect(log_file=log_file_path, suppress_console=True):
                    if force:
                        # Force stop (equivalent to virsh destroy)
                        if not silent:
                            log.debug(f"Force stopping VM '{self.vm_name}'")
                        self._libvirt_domain.destroy()
                    else:
                        # Graceful shutdown (equivalent to virsh shutdown)
                        if not silent:
                            log.debug(f"Gracefully shutting down VM '{self.vm_name}'")
                        self._libvirt_domain.shutdown()

                        # Wait for VM to stop with timeout
                        for _ in range(timeout):
                            await asyncio.sleep(1)
                            try:
                                state, _ = self._libvirt_domain.state()
                                if state == libvirt.VIR_DOMAIN_SHUTOFF:
                                    if not silent:
                                        log.debug(f"VM '{self.vm_name}' stopped gracefully")
                                    return 0
                            except libvirt.libvirtError:
                                # Domain might have been destroyed
                                break

                        # Timeout - force stop
                        log.warning("Graceful shutdown timed out, forcing stop")
                        self._libvirt_domain.destroy()

                if not silent:
                    log.debug(f"VM '{self.vm_name}' stopped")
                return 0

            except libvirt.libvirtError as e:
                if "not running" in str(e).lower() or "not active" in str(e).lower():
                    if not silent:
                        log.debug(f"VM '{self.vm_name}' is already stopped")
                    return 0
                else:
                    log.error(f"Failed to stop VM via libvirt: {e}")
                    return 1
            except (HypervisorException, OSError) as e:
                log.error(f"Error stopping VM: {e}")
                return 1

        return await self.manager.run_async(_stop_async)

    async def destroy(
        self,
        ctx_manager=None,
        stop_event=None,
        log_file: Optional[Path] = None,
        silent: bool = False
    ) -> int:
        """
        Destroy the QEMU VM (undefine libvirt domain, delete disk and config).

        Args:
            ctx_manager: Optional context manager for status updates
            stop_event: Optional threading event to signal cancellation
            log_file: Optional path to log file
            silent: If True, suppress log output

        Returns:
            Return code (0 for success, non-zero for failure)
        """
        async def _destroy_async():
            import libvirt

            if not silent:
                log.debug(f"Destroying QEMU VM '{self.vm_name}'")

            # Force stop regardless of reported state (ensure VM is truly stopped)
            try:
                await self.stop(silent=silent, force=True)
            except (HypervisorException, libvirt.libvirtError, OSError) as e:
                if not silent:
                    log.debug(f"Stop failed or VM already stopped: {e}")

            log_file_path = get_experiment_log_file()

            # Undefine libvirt domain (removes from virsh list)
            # Use undefineFlags for proper cleanup of snapshots and managed storage
            flags = (libvirt.VIR_DOMAIN_UNDEFINE_MANAGED_SAVE |
                     libvirt.VIR_DOMAIN_UNDEFINE_SNAPSHOTS_METADATA |
                     libvirt.VIR_DOMAIN_UNDEFINE_NVRAM)

            if self._libvirt_domain:
                try:
                    with LibvirtStderrRedirect(log_file=log_file_path, suppress_console=True):
                        try:
                            self._libvirt_domain.undefineFlags(flags)
                        except AttributeError:
                            # Fall back to basic undefine if undefineFlags not available
                            self._libvirt_domain.undefine()
                    if not silent:
                        log.debug(f"Undefined libvirt domain '{self.vm_name}'")
                except libvirt.libvirtError as e:
                    log.error(f"Could not undefine libvirt domain: {e}")
                    raise  # Propagate error instead of just warning
                self._libvirt_domain = None
            else:
                # Try to lookup and undefine if it exists
                try:
                    with LibvirtStderrRedirect(log_file=log_file_path, suppress_console=True):
                        conn = self._get_libvirt_connection()
                        domain = conn.lookupByName(self.vm_name)
                        try:
                            domain.undefineFlags(flags)
                        except AttributeError:
                            # Fall back to basic undefine if undefineFlags not available
                            domain.undefine()
                    if not silent:
                        log.debug(f"Undefined libvirt domain '{self.vm_name}'")
                except libvirt.libvirtError:
                    pass  # Domain doesn't exist, which is fine

            # Delete disk with retry logic (disk might be momentarily in use)
            disk_deleted = False
            if os.path.exists(self.config.disk_path):
                disk_name = Path(self.config.disk_path).name

                # CRITICAL SAFETY CHECK: Ensure we're deleting an overlay, not a base disk
                # Base disks are immutable and should never be deleted
                # Overlay disks have "-overlay-" or "-dev-" in their name
                if "-overlay-" not in disk_name and "-dev-" not in disk_name:
                    error_msg = (
                        f"CRITICAL: Attempted to delete what appears to be a BASE disk: {self.config.disk_path}\n"
                        f"Base disks should be preserved for reuse. Only overlay disks "
                        f"(containing '-overlay-' or '-dev-') should be deleted.\n"
                        f"This indicates a bug in session restoration or disk path tracking."
                    )
                    log.error(f"{error_msg}")
                    raise RuntimeError(
                        f"Refusing to delete potential base disk: {disk_name}. "
                        f"Only overlay disks (containing '-overlay-' or '-dev-') should be deleted."
                    )

                # Try multiple times with small delay (disk might be in use momentarily)
                for attempt in range(3):
                    try:
                        os.remove(self.config.disk_path)
                        if not silent:
                            log.debug(f"Deleted VM disk: {self.config.disk_path}")
                        disk_deleted = True
                        break
                    except OSError as e:
                        if attempt < 2:
                            if not silent:
                                log.debug(f"Disk deletion attempt {attempt+1} failed, retrying: {e}")
                            await asyncio.sleep(0.5)
                        else:
                            log.error(f"Failed to delete disk after 3 attempts: {e}")
                            raise  # Propagate error instead of swallowing it

                # Verify deletion
                if disk_deleted and os.path.exists(self.config.disk_path):
                    raise RuntimeError(f"Disk file still exists after deletion: {self.config.disk_path}")

                # Clean up empty parent directory for overlay disk artifacts
                if disk_deleted:
                    disk_path = Path(self.config.disk_path)
                    disk_name = disk_path.name

                    # Safety check: only clean up artifact dirs for overlay/dev disks
                    if "-overlay-" in disk_name or "-dev-" in disk_name:
                        artifact_dir = disk_path.parent / disk_path.stem
                        try:
                            if artifact_dir.exists() and artifact_dir.is_dir():
                                # Check if directory is empty
                                if not any(artifact_dir.iterdir()):
                                    artifact_dir.rmdir()
                                    if not silent:
                                        log.info(f"Removed empty artifact directory: {artifact_dir}")
                                else:
                                    if not silent:
                                        log.debug(f"Artifact directory not empty, preserving: {artifact_dir}")
                        except OSError as e:
                            # Non-critical error, log and continue
                            log.debug(f"Failed to remove artifact directory: {e}")
            elif not silent:
                log.debug(f"Disk does not exist: {self.config.disk_path}")

            # Delete config
            config_path = self._get_vm_config_path()
            if config_path.exists():
                try:
                    os.remove(config_path)
                    if not silent:
                        log.debug(f"Deleted VM config: {config_path}")
                except OSError as e:
                    log.error(f"Error deleting config: {e}")

            # Clean up sockets
            for socket_path in [self.config.qmp_socket_path, self.config.guest_agent_socket_path]:
                if os.path.exists(socket_path):
                    try:
                        os.remove(socket_path)
                    except OSError:
                        pass

            # Post-removal verification
            # Verify domain is undefined
            try:
                with LibvirtStderrRedirect(log_file=log_file_path, suppress_console=True):
                    conn = self._get_libvirt_connection()
                    domain = conn.lookupByName(self.vm_name)
                    log.error(f"Domain '{self.vm_name}' still defined after undefine!")
                    return 1
            except libvirt.libvirtError:
                if not silent:
                    log.debug("Verified domain is undefined")

            # Verify disk file deleted
            if os.path.exists(self.config.disk_path):
                log.error(f"Disk still exists after deletion: {self.config.disk_path}")
                return 1

            if not silent:
                log.debug(f"VM '{self.vm_name}' destroyed and verified")

            return 0

        return await self.manager.run_async(_destroy_async)

    def get_state(self) -> str:
        """
        Get the current state of the VM via libvirt.

        Returns:
            "running", "poweroff", "paused", or "unknown"
        """
        import libvirt

        try:
            log_file = get_experiment_log_file()

            # Try to get domain state from libvirt
            if not self._libvirt_domain:
                try:
                    self._ensure_libvirt_domain()
                except HypervisorException:
                    # Domain not defined in libvirt or connection unavailable
                    return "poweroff"

            # Get domain state
            with LibvirtStderrRedirect(log_file=log_file, suppress_console=True):
                state, _ = self._libvirt_domain.state()

            # Map libvirt states to ADARE states
            state_map = {
                libvirt.VIR_DOMAIN_RUNNING: 'running',
                libvirt.VIR_DOMAIN_BLOCKED: 'running',
                libvirt.VIR_DOMAIN_PAUSED: 'paused',
                libvirt.VIR_DOMAIN_SHUTDOWN: 'poweroff',
                libvirt.VIR_DOMAIN_SHUTOFF: 'poweroff',
                libvirt.VIR_DOMAIN_CRASHED: 'poweroff',
                libvirt.VIR_DOMAIN_PMSUSPENDED: 'paused'
            }

            return state_map.get(state, 'unknown')

        except libvirt.libvirtError as e:
            log.debug(f"Could not get VM state from libvirt: {e}")
            return "unknown"
        except (HypervisorException, OSError) as e:
            log.warning(f"Error getting VM state: {e}")
            return "unknown"

    def vm_exists(self) -> bool:
        """
        Check if the VM exists (disk file exists).

        Returns:
            True if VM exists, False otherwise
        """
        return os.path.exists(self.config.disk_path)

    @property
    def vm_identifier(self) -> str:
        """
        Get VM identifier (name for QEMU).

        Returns:
            VM name
        """
        return self.vm_name

    async def run_command(
        self,
        command: str,
        background: bool = False,
        silent: bool = False,
        stop_event: Optional[threading.Event] = None,
        cwd: Optional[str] = None,
        admin: bool = False,
        binary_is_filepath: bool = False,
        run_as_user: bool = False,
        inject_user_path: bool = False,
        redirect_stdout: str = "",
        redirect_stderr: str = "",
        **kwargs
    ) -> CommandResult:
        """
        Run a command in the guest VM via QEMU Guest Agent.

        Args:
            command: Command to execute
            background: If True, don't wait for completion
            silent: If True, suppress log output
            stop_event: Optional event to signal cancellation
            cwd: Optional working directory
            admin: If True, run with elevated privileges (sudo on Linux, RunAs on Windows)
            binary_is_filepath: If True, treat command as filepath in Start-Process (Windows)
            run_as_user: If True, use scheduled task for user session execution (Windows)
            inject_user_path: If True, inject user's PATH (Windows)
            redirect_stdout: Path to file for stdout redirection (QEMU-specific)
            redirect_stderr: Path to file for stderr redirection (QEMU-specific)
            **kwargs: Additional arguments

        Returns:
            CommandResult with returncode, stdout, stderr
        """
        if not silent:
            log.debug(f"Executing command in VM '{self.vm_name}': {command}")

        returncode, stdout, stderr = await self._execute_guest_command_via_agent(
            command,
            background=background,
            stop_event=stop_event,
            admin=admin,
            cwd=cwd,
            binary_is_filepath=binary_is_filepath,
            run_as_user=run_as_user,
            inject_user_path=inject_user_path,
            redirect_stdout=redirect_stdout,
            redirect_stderr=redirect_stderr
        )

        return CommandResult(
            returncode=returncode,
            stdout=stdout,
            stderr=stderr
        )

    async def wait_until_fully_booted(
        self,
        timeout: int = 300,
        ctx_manager=None,
        stop_event=None,
        skip_x11_discovery: bool = False
    ) -> bool:
        """
        Wait until VM is fully booted and guest agent is responsive.

        Tests both guest-ping (connectivity) and guest-exec (command execution)
        to ensure VM is truly ready for setup commands.

        Args:
            timeout: Timeout in seconds
            ctx_manager: Optional context manager for status updates
            stop_event: Optional event to signal cancellation
            skip_x11_discovery: If True, skip X11 environment discovery (for host-based GUI mode)

        Returns:
            True if VM is booted and ready, False if timeout
        """
        log.debug(f"Waiting for VM '{self.vm_name}' to boot (timeout: {timeout}s)")

        start_time = time.time()
        retry_delay = 0.5  # Start with short delay for quick boots
        max_retry_delay = 2.0  # Reduced from 5s for faster response

        while time.time() - start_time < timeout:
            if stop_event and stop_event.is_set():
                log.debug("Stop event detected")
                return False

            try:
                # Test command execution with guest-exec
                # This validates: socket exists, agent is responsive, and commands can execute
                log.debug("Testing guest-exec capability (validates socket + agent + execution)")

                # Determine test command based on guest OS
                if 'windows' in self.guest_os.lower():
                    test_path = 'cmd.exe'
                    test_args = ['/c', 'echo', 'Ready']
                else:
                    test_path = '/bin/echo'
                    test_args = ['Ready']

                exec_cmd = {
                    "execute": "guest-exec",
                    "arguments": {
                        "path": test_path,
                        "arg": test_args,
                        "capture-output": True
                    }
                }

                exec_response = await self._send_qga_command_via_libvirt(exec_cmd)

                if 'error' in exec_response:
                    error_desc = exec_response.get('error', {}).get('desc', '')
                    log.debug(f"guest-exec test failed: {error_desc}")
                    # Treat as retriable - socket might not be fully ready
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 1.5, max_retry_delay)
                    continue

                # Get PID from exec response
                pid = exec_response.get('return', {}).get('pid')
                if not pid:
                    log.debug("guest-exec returned no PID")
                    await asyncio.sleep(retry_delay)
                    retry_delay = min(retry_delay * 1.5, max_retry_delay)
                    continue

                # Wait for test command to complete (max 10s)
                test_timeout = 10
                test_start = time.time()

                while time.time() - test_start < test_timeout:
                    status_cmd = {
                        "execute": "guest-exec-status",
                        "arguments": {"pid": pid}
                    }

                    status_response = await self._send_qga_command_via_libvirt(status_cmd)

                    if 'error' in status_response:
                        log.debug(f"guest-exec-status failed: {status_response['error']}")
                        break

                    status_data = status_response.get('return', {})
                    if status_data.get('exited', False):
                        returncode = status_data.get('exitcode', -1)

                        if returncode == 0:
                            log.debug(f"VM '{self.vm_name}' is fully booted and guest-exec is functional")

                            # Phase 3+4: Discover PATH and X11 in parallel for faster boot
                            discovery_tasks = []

                            # Always discover PATH
                            log.debug("Discovering guest PATH environment")
                            discovery_tasks.append(self._discover_and_cache_guest_path())

                            # Conditionally discover X11 (Linux only, unless skipped)
                            should_discover_x11 = False
                            if skip_x11_discovery:
                                log.debug("Skipping X11 discovery - using host-based GUI automation")
                            elif 'windows' in self.guest_os.lower():
                                log.debug("Skipping X11 detection for Windows guest")
                            else:
                                log.debug("Discovering X11 authorization for GUI automation")
                                discovery_tasks.append(self._discover_and_cache_xauthority())
                                should_discover_x11 = True

                            # Run discoveries concurrently
                            results = await asyncio.gather(*discovery_tasks, return_exceptions=True)

                            # Check PATH discovery result (first result, always present)
                            if results:
                                path_result = results[0]
                                if isinstance(path_result, Exception):
                                    log.warning(f"PATH discovery failed with exception: {path_result}")

                            # Check X11 discovery result if it was requested
                            if should_discover_x11:
                                x11_result = results[1] if len(results) > 1 else None
                                if isinstance(x11_result, Exception):
                                    log.warning(f"X11 discovery failed: {x11_result}")
                                elif x11_result:
                                    log.debug(f"X11 authorization configured with XAUTHORITY={x11_result}")
                                else:
                                    raise RuntimeError(
                                        "XAUTHORITY not found - X11 environment required for GUI automation. "
                                        "Ensure the VM has an active X11 session (not headless). "
                                    )

                            return True
                        else:
                            log.warning(f"guest-exec test returned non-zero: {returncode}")
                            break

                    await asyncio.sleep(0.5)

                # Test command didn't complete in time, try again
                log.debug("guest-exec test timed out, retrying")

            except asyncio.TimeoutError:
                log.debug("Timeout during boot check")
            except OSError as e:
                log.debug(f"OS error during boot check: {e}")
            except ConnectionError as e:
                log.debug(f"Connection error during boot check: {e}")

            await asyncio.sleep(2)

        log.warning(f"Timeout waiting for VM '{self.vm_name}' to boot")
        return False

    async def _discover_and_cache_guest_path(self):
        """
        Discover guest PATH environment and cache it for future command execution.

        Called once after VM is fully booted and guest agent is responsive.
        Failures are non-fatal - the system will fall back to hardcoded PATH.

        This method:
        1. Checks if discovery was already attempted (prevents retry on failure)
        2. Calls _discover_guest_path() to query PATH from guest OS
        3. Caches successful result in _cached_guest_path instance variable
        4. Logs warning on failure but doesn't raise exceptions
        """
        if self._path_discovery_attempted:
            return  # Already tried, don't retry

        self._path_discovery_attempted = True

        discovered_path = await self._discover_guest_path()

        if discovered_path:
            self._cached_guest_path = discovered_path
            log.debug(f"Cached guest PATH: {discovered_path[:100]}...")
        else:
            log.warning("PATH discovery failed, will use hardcoded fallback")

    async def create_from_ovf_or_ova(
        self,
        file_path: Path,
        silent: bool = False,
        try_extract: bool = True
    ) -> Tuple[int, str]:
        """
        Create VM from OVF/OVA file by converting disk to qcow2.

        For --no-copy mode with qcow2 source: skips conversion entirely.
        For --no-copy mode with non-qcow2 source: converts in-place next to original file.

        Args:
            file_path: Path to OVF/OVA file or disk image
            silent: If True, suppress log output
            try_extract: If True, try to extract OVA

        Returns:
            Tuple of (return_code, output_message)
        """
        log.debug(f"Importing QEMU VM from {file_path}")

        qemu_img_exe = self.executables.qemu_img

        # For OVA, extract first
        if str(file_path).endswith('.ova') and try_extract:
            # Extract OVA (it's a tar file)
            import tarfile
            extract_dir = file_path.parent / f"{file_path.stem}_extracted"
            extract_dir.mkdir(exist_ok=True)

            with tarfile.open(file_path) as tar:
                tar.extractall(extract_dir)

            # Find VMDK or VDI file
            disk_files = list(extract_dir.glob('*.vmdk')) + list(extract_dir.glob('*.vdi'))
            if not disk_files:
                return 1, "No disk file found in OVA"

            source_disk = disk_files[0]
        else:
            # Assume it's already a disk file
            source_disk = file_path

        # Use base disk path (immutable) instead of regular disk path
        # This ensures the converted disk becomes the base for overlays
        dest_disk = self.get_base_disk_path()
        log.debug(f"Conversion target is base disk: {dest_disk}")

        # Detect source disk format for --no-copy optimization
        try:
            source_format = self._detect_disk_format(source_disk)
            log.debug(f"Detected source disk format: {source_format}")
        except HypervisorException as e:
            log.warning(f"Could not detect source format, will attempt conversion: {e}")
            source_format = 'unknown'

        # Check if conversion can be skipped (--no-copy mode with qcow2 source)
        if source_format == 'qcow2' and self._external_disk_path:
            # Check if source and dest are the same file (--no-copy with existing qcow2)
            if Path(source_disk).resolve() == Path(dest_disk).resolve():
                log.debug(f"Source is already qcow2 at target location, skipping conversion")
                self._save_vm_config()
                return 0, "VM imported successfully (no conversion needed)"

        # Validate write permissions for external disk path before conversion
        if self._external_disk_path:
            dest_path = Path(dest_disk)
            if dest_path.exists():
                # Check if file is writable
                if not os.access(dest_disk, os.W_OK):
                    return 1, (
                        f"External disk is not writable: {dest_disk}\n"
                        f"QEMU requires write access for snapshot operations.\n"
                        f"Please ensure the file has write permissions."
                    )
            else:
                # Check if parent directory is writable
                parent_dir = dest_path.parent
                if not parent_dir.exists():
                    return 1, f"Parent directory does not exist: {parent_dir}"
                if not os.access(parent_dir, os.W_OK):
                    return 1, (
                        f"Parent directory is not writable: {parent_dir}\n"
                        f"Cannot create converted qcow2 file for external VM.\n"
                        f"Please ensure directory has write permissions."
                    )

        # Convert to qcow2
        log.debug(f"Converting {source_format} disk to qcow2 at {dest_disk}")
        args = [qemu_img_exe, 'convert', '-O', 'qcow2', str(source_disk), dest_disk]

        try:
            result = subprocess.run(args, capture_output=True, text=True, check=False)

            if result.returncode == 0:
                log.debug(f"Successfully converted disk to {dest_disk}")
                self._save_vm_config()
                return 0, f"VM imported successfully"
            else:
                error_msg = f"Failed to convert {source_format} to qcow2: {result.stderr}"
                if self._external_disk_path:
                    error_msg += "\nConsider loading without --no-copy to use managed storage."
                return result.returncode, error_msg

        except (subprocess.CalledProcessError, OSError) as e:
            error_msg = f"Conversion error: {str(e)}"
            if self._external_disk_path:
                error_msg += "\nConsider loading without --no-copy to use managed storage."
            return 1, error_msg

    def queue_command(self, command: str, description: str = None):
        """Queue a command for later execution."""
        self._command_queue.append({'command': command, 'description': description})

    async def execute_queued_commands(
        self,
        ctx_manager=None,
        stop_event=None,
        log_file=None,
        silent=False
    ):
        """Execute all queued commands."""
        for cmd_info in self._command_queue:
            command = cmd_info['command']
            result = await self.run_command(command, silent=silent, stop_event=stop_event)
            if result.returncode != 0:
                log.error(f"Queued command failed: {command}")

        self._command_queue.clear()

    def cleanup_background_processes(self):
        """Clean up background processes (no-op for QEMU, processes managed by guest agent)."""
        self._background_pids.clear()

    # QMP Methods for Host-Based GUI Automation

    async def _send_qmp_command(self, command: dict) -> dict:
        """
        Send command to QEMU Monitor Protocol (QMP) via libvirt API.

        Args:
            command: QMP command dictionary

        Returns:
            Response dictionary
        """
        async def _qmp_async():
            import libvirt_qemu
            try:
                # Ensure libvirt domain is available
                try:
                    self._ensure_libvirt_domain()
                except HypervisorException as e:
                    log.warning(f"Failed to look up domain for QMP: {e}")
                    return {"error": {"desc": f"Domain not defined: {e}"}}

                cmd_json = json.dumps(command)
                log.debug(f"Sending QMP command: {command.get('execute', 'unknown')}")

                log_file = get_experiment_log_file()
                with LibvirtStderrRedirect(log_file=log_file, suppress_console=True):
                    result = libvirt_qemu.qemuMonitorCommand(
                        self._libvirt_domain,
                        cmd_json,
                        0  # flags (0 = default QMP mode)
                    )

                response = json.loads(result)

                # Log detailed response for debugging
                if 'error' in response:
                    log.error(f"QMP command failed - Command: {command.get('execute')}, Error: {response['error']}")
                elif 'return' not in response:
                    log.warning(f"QMP response missing 'return' key: {response}")
                else:
                    log.debug(f"QMP response: {response}")

                return response

            except libvirt.libvirtError as e:
                log.error(f"Libvirt error sending QMP command: {e}")
                return {"error": {"desc": f"Libvirt error: {e}"}}
            except json.JSONDecodeError as e:
                log.error(f"Failed to parse QMP response: {e}, Raw: {result if 'result' in locals() else 'N/A'}")
                return {"error": {"desc": f"Invalid JSON: {e}"}}
            except (OSError, AttributeError, TypeError) as e:
                log.error(f"Unexpected QMP error: {e}", exc_info=True)
                return {"error": {"desc": f"Error: {e}"}}

        return await self.manager.run_async(_qmp_async)

    async def send_qmp_screenshot(self, output_path: str) -> Tuple[bool, Optional[str]]:
        """
        Capture screenshot via QMP screendump command.

        Args:
            output_path: Path where screenshot will be saved (PPM format)

        Returns:
            Tuple of (success, error_message)
        """
        command = {
            "execute": "screendump",
            "arguments": {"filename": output_path}
        }
        response = await self._send_qmp_command(command)
        
        if 'return' in response:
            return True, None
        else:
            error_desc = response.get('error', {}).get('desc', 'Unknown QMP error')
            return False, error_desc

    async def _ensure_tablet_active(self) -> None:
        """Ensure USB tablet is the active mouse device for correct BTN event routing.

        On macOS/HVF, the virtio mouse may register before the USB tablet,
        causing BTN events to route to the wrong device. This activates the
        tablet via HMP 'mouse_set' which moves it to the head of the handler list.
        """
        if self._tablet_activated:
            return

        response = await self._send_qmp_command({
            "execute": "human-monitor-command",
            "arguments": {"command-line": "info mice"}
        })
        output = response.get('return', '')

        for line in output.strip().split('\n'):
            if 'tablet' in line.lower():
                if line.strip().startswith('*'):
                    self._tablet_activated = True
                    return
                idx = line.split('#')[1].split(':')[0].strip()
                await self._send_qmp_command({
                    "execute": "human-monitor-command",
                    "arguments": {"command-line": f"mouse_set {idx}"}
                })
                self._tablet_activated = True
                log.debug(f"Activated USB tablet as primary mouse (index {idx})")
                return

        log.warning("USB tablet not found in mouse list - clicks may not work correctly")
        self._tablet_activated = True  # Don't retry every click

    async def send_qmp_mouse_click(self, x: int, y: int, button: str = 'left') -> bool:
        """
        Execute mouse click via QMP input-send-event command.

        Sends position, press, and release as separate commands for reliable execution.
        Automatically normalizes pixel coordinates to QEMU USB tablet range (0-32767).

        Args:
            x: X coordinate in pixels
            y: Y coordinate in pixels
            button: Button type ('left', 'right', 'middle')

        Returns:
            True if successful, False otherwise

        Raises:
            RuntimeError: If screen resolution is not yet known
        """
        await self._ensure_tablet_active()

        # Normalize coordinates for USB tablet device
        norm_x, norm_y = self._normalize_coordinates(x, y)

        # Map button names to QMP button strings
        button_map = {'left': 'left', 'right': 'right', 'middle': 'middle', 'double': 'left'}
        qmp_button = button_map.get(button, 'left')

        # Step 1: Move mouse to position
        move_command = {
            "execute": "input-send-event",
            "arguments": {
                "events": [
                    {"type": "abs", "data": {"axis": "x", "value": norm_x}},
                    {"type": "abs", "data": {"axis": "y", "value": norm_y}}
                ]
            }
        }
        move_response = await self._send_qmp_command(move_command)

        if 'error' in move_response:
            log.error(f"QMP mouse move failed: {move_response.get('error')}")
            return False

        await asyncio.sleep(0.01)

        # Step 2: Press button
        press_command = {
            "execute": "input-send-event",
            "arguments": {
                "events": [
                    {"type": "btn", "data": {"button": qmp_button, "down": True}}
                ]
            }
        }
        press_response = await self._send_qmp_command(press_command)

        if 'error' in press_response:
            log.error(f"QMP button press failed: {press_response.get('error')}")
            return False

        await asyncio.sleep(0.05)  # Hold button down briefly

        # Step 3: Release button
        release_command = {
            "execute": "input-send-event",
            "arguments": {
                "events": [
                    {"type": "btn", "data": {"button": qmp_button, "down": False}}
                ]
            }
        }
        release_response = await self._send_qmp_command(release_command)

        if 'error' in release_response:
            log.error(f"QMP button release failed: {release_response.get('error')}")
            return False

        return all('return' in r for r in [move_response, press_response, release_response])

    async def send_qmp_mouse_drag(self, x1: int, y1: int, x2: int, y2: int) -> bool:
        """
        Execute drag operation via QMP input-send-event command.

        Sends position and button events separately for reliable execution.
        Automatically normalizes pixel coordinates to QEMU USB tablet range (0-32767).

        Args:
            x1: Start X coordinate in pixels
            y1: Start Y coordinate in pixels
            x2: End X coordinate in pixels
            y2: End Y coordinate in pixels

        Returns:
            True if successful, False otherwise

        Raises:
            RuntimeError: If screen resolution is not yet known
        """
        await self._ensure_tablet_active()

        # Normalize both start and end coordinates
        norm_x1, norm_y1 = self._normalize_coordinates(x1, y1)
        norm_x2, norm_y2 = self._normalize_coordinates(x2, y2)

        # Step 1: Move to start position
        move_start_command = {
            "execute": "input-send-event",
            "arguments": {
                "events": [
                    {"type": "abs", "data": {"axis": "x", "value": norm_x1}},
                    {"type": "abs", "data": {"axis": "y", "value": norm_y1}}
                ]
            }
        }
        response1 = await self._send_qmp_command(move_start_command)
        if 'error' in response1:
            log.error(f"QMP drag move to start failed: {response1.get('error')}")
            return False

        await asyncio.sleep(0.01)

        # Step 2: Press left button
        press_command = {
            "execute": "input-send-event",
            "arguments": {
                "events": [
                    {"type": "btn", "data": {"button": "left", "down": True}}
                ]
            }
        }
        response2 = await self._send_qmp_command(press_command)
        if 'error' in response2:
            log.error(f"QMP drag button press failed: {response2.get('error')}")
            return False

        await asyncio.sleep(0.01)

        # Step 3: Move to end position (while holding button)
        move_end_command = {
            "execute": "input-send-event",
            "arguments": {
                "events": [
                    {"type": "abs", "data": {"axis": "x", "value": norm_x2}},
                    {"type": "abs", "data": {"axis": "y", "value": norm_y2}}
                ]
            }
        }
        response3 = await self._send_qmp_command(move_end_command)
        if 'error' in response3:
            log.error(f"QMP drag move to end failed: {response3.get('error')}")
            return False

        await asyncio.sleep(0.01)

        # Step 4: Release button
        release_command = {
            "execute": "input-send-event",
            "arguments": {
                "events": [
                    {"type": "btn", "data": {"button": "left", "down": False}}
                ]
            }
        }
        response4 = await self._send_qmp_command(release_command)
        if 'error' in response4:
            log.error(f"QMP drag button release failed: {response4.get('error')}")
            return False

        return all('return' in r for r in [response1, response2, response3, response4])

    async def send_qmp_keyboard(self, events: List[dict]) -> bool:
        """
        Send keyboard events via QMP input-send-event command.

        Batches events to prevent QMP buffer overflow or truncation with long strings.

        Args:
            events: List of QMP keyboard event dictionaries

        Returns:
            True if successful (all batches sent), False otherwise
        """
        # Batch size for QMP commands (prevent truncation/buffer issues)
        BATCH_SIZE = 10
        success = True

        for i in range(0, len(events), BATCH_SIZE):
            batch = events[i:i + BATCH_SIZE]
            
            command = {
                "execute": "input-send-event",
                "arguments": {"events": batch}
            }
            
            response = await self._send_qmp_command(command)
            
            if 'return' not in response:
                log.error(f"QMP keyboard batch {i//BATCH_SIZE} failed: {response}")
                success = False
                # Continue trying to send remaining batches? 
                # Probably better to try to finish typing even if one chunk fails, 
                # though state might be inconsistent. 
                # For now, we'll mark as failure but continue.

            # Small delay to ensure QEMU processes the batch
            if len(events) > BATCH_SIZE:
                await asyncio.sleep(0.01)

        return success

    async def send_qmp_scroll(self, amount: int) -> bool:
        """
        Send scroll event via QMP input-send-event command.

        Args:
            amount: Scroll amount (positive = up, negative = down)

        Returns:
            True if successful, False otherwise
        """
        command = {
            "execute": "input-send-event",
            "arguments": {
                "events": [
                    {"type": "rel", "data": {"axis": "wheel", "value": amount}}
                ]
            }
        }
        response = await self._send_qmp_command(command)
        return 'return' in response

    async def send_qmp_trace_event_set_state(self, name: str, enable: bool) -> bool:
        """
        Set QEMU trace event state via QMP.

        Args:
            name: Trace event name or pattern (glob)
            enable: True to enable, False to disable

        Returns:
            True if successful
        """
        command = {
            "execute": "trace-event-set-state",
            "arguments": {
                "name": name,
                "enable": enable
            }
        }
        response = await self._send_qmp_command(command)
        return 'return' in response

    async def enable_input_tracing(self) -> bool:
        """
        Enable QEMU tracing for input events.
        
        Enables:
        - input_event_key_number
        - input_event_key_qcode
        - input_event_btn
        - input_event_abs
        - input_event_rel
        """
        patterns = [
            "input_event_key*",
            "input_event_btn",
            "input_event_abs",
            "input_event_rel", 
            "ps2_put_keycode" # Fallback/additional info
        ]
        
        success = True
        for pattern in patterns:
            if not await self.send_qmp_trace_event_set_state(pattern, True):
                log.warning(f"Failed to enable trace pattern: {pattern}")
                success = False
                
        return success

    async def disable_input_tracing(self) -> bool:
        """Disable QEMU tracing for input events."""
        patterns = [
            "input_event_key*",
            "input_event_btn",
            "input_event_abs",
            "input_event_rel",
            "ps2_put_keycode"
        ]
        
        success = True
        for pattern in patterns:
            await self.send_qmp_trace_event_set_state(pattern, False)
            
        return success

    def update_screen_resolution(self, width: int, height: int) -> None:
        """
        Update cached screen resolution for coordinate normalization.

        Called automatically when screenshots are captured to track current display size.
        Required because QEMU's USB tablet device expects normalized coordinates (0-32767),
        not raw pixel coordinates.

        Args:
            width: Screen width in pixels
            height: Screen height in pixels
        """
        if self._screen_width != width or self._screen_height != height:
            log.debug(f"Screen resolution updated: {width}x{height}")
            self._screen_width = width
            self._screen_height = height
            self._resolution_last_updated = time.time()

    def _normalize_coordinates(self, x: int, y: int) -> tuple[int, int]:
        """
        Normalize pixel coordinates to QEMU USB tablet range (0-32767).

        QEMU's USB tablet device uses absolute positioning with a normalized coordinate
        system where 0-32767 maps to the full screen width/height, regardless of actual
        pixel resolution.

        Args:
            x: X coordinate in pixels
            y: Y coordinate in pixels

        Returns:
            Tuple of (normalized_x, normalized_y) in range 0-32767

        Raises:
            RuntimeError: If screen resolution is not yet known
        """
        if self._screen_width is None or self._screen_height is None:
            raise RuntimeError(
                "Screen resolution unknown - cannot normalize coordinates. "
                "Ensure a screenshot is captured before mouse operations. "
                "This updates the cached resolution automatically."
            )

        # Normalize to 0-32767 range (0x7fff = 32767)
        # Formula: normalized = int((pixel / screen_dimension) * 32767)
        normalized_x = int((x / self._screen_width) * 32767)
        normalized_y = int((y / self._screen_height) * 32767)

        # Clamp to valid range (handle edge cases where coordinates might be at/beyond screen edge)
        normalized_x = max(0, min(32767, normalized_x))
        normalized_y = max(0, min(32767, normalized_y))

        log.debug(f"Normalized coordinates: ({x}, {y}) -> ({normalized_x}, {normalized_y}) "
                  f"for resolution {self._screen_width}x{self._screen_height}")

        return normalized_x, normalized_y
