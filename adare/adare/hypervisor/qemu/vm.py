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
import uuid
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple

from adarelib.constants import StatusEnum

from adare.hypervisor.base.vm import AbstractVM
from adare.hypervisor.exceptions import (
    VMImportException,
    VMAlreadyRunningException,
    VMNotFoundException,
    HypervisorException
)
from adare.hypervisor.qemu.manager import QEMUManager
from adare.hypervisor.qemu.mixins.commands import CommandExecutionMixin
from adare.hypervisor.qemu.mixins.snapshots import SnapshotMixin
from adare.hypervisor.qemu.mixins.networking import NetworkingMixin
from adare.hypervisor.qemu.models import QEMUVMConfig, CommandResult

log = logging.getLogger(__name__)


class QEMUVM(CommandExecutionMixin, SnapshotMixin, NetworkingMixin, AbstractVM):
    """
    QEMU VM management class with modular operations.
    Inherits from mixins for command execution, snapshots, and networking.
    """

    def __init__(
        self,
        vm_name: str,
        guest_os: str,
        manager: 'QEMUManager',
        username: str,
        password: str,
        cpus: int = 2,
        ram: int = 2048,
        machine: str = 'pc',
        accel: str = 'kvm',
        drive_format: str = 'qcow2'
    ):
        self.vm_name = vm_name
        self.guest_os = guest_os
        self.username = username
        self.password = password
        self.cpus = cpus
        self.ram = ram
        self.machine = machine
        self.accel = accel
        self.drive_format = drive_format
        self.host_os = platform.system().lower()
        self.manager = manager
        self._background_pids = []
        self._command_queue = []
        self._qemu_process = None  # Running QEMU process

        # Load or create VM config
        self.config = self._load_or_create_vm_config()

        log.info(f"CLAUDE: Initialized QEMUVM for '{self.vm_name}' ({self.guest_os})")

    def _get_vm_config_path(self) -> Path:
        """Get path to VM configuration JSON file."""
        # Store VM configs in ~/.adare/qemu/vms/
        config_dir = Path.home() / '.adare' / 'qemu' / 'vms'
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / f"{self.vm_name}.json"

    def _load_or_create_vm_config(self) -> QEMUVMConfig:
        """Load VM config from JSON or create new one."""
        config_path = self._get_vm_config_path()

        if config_path.exists():
            log.debug(f"CLAUDE: Loading VM config from {config_path}")
            with open(config_path, 'r') as f:
                data = json.load(f)
            return QEMUVMConfig.from_dict(data)
        else:
            log.debug(f"CLAUDE: Creating new VM config for '{self.vm_name}'")
            # Create new config
            vm_uuid = str(uuid.uuid4())
            disk_dir = Path.home() / '.adare' / 'qemu' / 'disks'
            disk_dir.mkdir(parents=True, exist_ok=True)
            disk_path = str(disk_dir / f"{self.vm_name}.qcow2")

            # Socket paths
            runtime_dir = Path.home() / '.adare' / 'qemu' / 'run'
            runtime_dir.mkdir(parents=True, exist_ok=True)
            qmp_socket = str(runtime_dir / f"{self.vm_name}.qmp")
            qga_socket = str(runtime_dir / f"{self.vm_name}.qga")
            pid_file = str(runtime_dir / f"{self.vm_name}.pid")

            config = QEMUVMConfig(
                vm_name=self.vm_name,
                uuid=vm_uuid,
                guest_os=self.guest_os,
                disk_path=disk_path,
                cpus=self.cpus,
                ram=self.ram,
                machine=self.machine,
                accel=self.accel,
                drive_format=self.drive_format,
                network='user',
                qmp_socket_path=qmp_socket,
                guest_agent_socket_path=qga_socket,
                pid_file_path=pid_file
            )

            self._save_vm_config_obj(config)
            return config

    def _save_vm_config(self):
        """Save current VM config to JSON file."""
        self._save_vm_config_obj(self.config)

    def _save_vm_config_obj(self, config: QEMUVMConfig):
        """Save VM config object to JSON file."""
        config_path = self._get_vm_config_path()
        log.debug(f"CLAUDE: Saving VM config to {config_path}")
        with open(config_path, 'w') as f:
            json.dump(config.to_dict(), f, indent=2)

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
                log.info(f"CLAUDE: Creating QEMU VM '{self.vm_name}' with "
                        f"{self.cpus} CPUs, {self.ram}MB RAM")

            from adare.config import HYPERVISOR_CONFIGS
            qemu_img_exe = HYPERVISOR_CONFIGS.get('qemu', {}).get('qemu_img_exe', 'qemu-img')

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
                    log.info(f"CLAUDE: VM '{self.vm_name}' disk created at {disk_path}")
                # Save config
                self._save_vm_config()
            else:
                log.error(f"CLAUDE: Failed to create VM disk: {stderr}")

            return returncode

        return await self.manager.run_async(_create_async)

    def _build_qemu_command(self) -> List[str]:
        """
        Build QEMU command line for starting VM.

        Returns:
            List of command arguments
        """
        from adare.config import HYPERVISOR_CONFIGS
        qemu_system_exe = HYPERVISOR_CONFIGS.get('qemu', {}).get('qemu_system_exe', 'qemu-system-x86_64')

        cmd = [
            qemu_system_exe,
            '-name', self.vm_name,
            '-machine', f"{self.machine},accel={self.accel}",
            '-cpu', 'host',
            '-smp', str(self.cpus),
            '-m', str(self.ram),
            '-drive', f"file={self.config.disk_path},format={self.drive_format},if=virtio",
            '-display', 'none',  # Headless
            '-daemonize',  # Run as daemon
            '-pidfile', self.config.pid_file_path
        ]

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

        log.debug(f"CLAUDE: QEMU command: {' '.join(cmd)}")
        return cmd

    async def start(
        self,
        ctx_manager=None,
        raise_if_running: bool = False,
        stop_event=None,
        log_file: Optional[Path] = None,
        silent: bool = False
    ) -> int:
        """
        Start the QEMU VM.

        Args:
            ctx_manager: Optional context manager for status updates
            raise_if_running: If True, raise exception if VM already running
            stop_event: Optional threading event to signal cancellation
            log_file: Optional path to log file
            silent: If True, suppress log output

        Returns:
            Return code (0 for success, non-zero for failure)
        """
        async def _start_async():
            current_state = self.get_state()

            if current_state == "running":
                message = f"VM '{self.vm_name}' is already running."
                if raise_if_running:
                    raise VMAlreadyRunningException(message)
                if not silent:
                    log.info(f"CLAUDE: {message}")
                return 0

            if not silent:
                log.info(f"CLAUDE: Starting QEMU VM '{self.vm_name}'")

            # Check if disk exists
            if not os.path.exists(self.config.disk_path):
                log.error(f"CLAUDE: VM disk not found at {self.config.disk_path}")
                return 1

            # Build QEMU command
            cmd = self._build_qemu_command()

            # Execute QEMU command
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=False
                )

                if result.returncode == 0:
                    # Give it a moment to start
                    await asyncio.sleep(1)

                    if not silent:
                        log.info(f"CLAUDE: VM '{self.vm_name}' started successfully")
                    return 0
                else:
                    log.error(f"CLAUDE: Failed to start VM: {result.stderr}")
                    return result.returncode

            except Exception as e:
                log.error(f"CLAUDE: Error starting VM: {e}")
                return 1

        return await self.manager.run_async(_start_async)

    async def stop(
        self,
        ctx_manager=None,
        log_file: Optional[Path] = None,
        silent: bool = False
    ) -> int:
        """
        Stop the QEMU VM gracefully.

        Args:
            ctx_manager: Optional context manager for status updates
            log_file: Optional path to log file
            silent: If True, suppress log output

        Returns:
            Return code (0 for success, non-zero for failure)
        """
        async def _stop_async():
            if not silent:
                log.info(f"CLAUDE: Stopping QEMU VM '{self.vm_name}'")

            state = self.get_state()
            if state == "poweroff":
                if not silent:
                    log.info(f"CLAUDE: VM '{self.vm_name}' is already stopped")
                return 0

            # Try graceful shutdown via guest agent
            try:
                if os.path.exists(self.config.guest_agent_socket_path):
                    shutdown_cmd = {"execute": "guest-shutdown"}
                    await self._send_qga_command(self.config.guest_agent_socket_path, shutdown_cmd)

                    # Wait for VM to stop (timeout 30 seconds)
                    for _ in range(30):
                        await asyncio.sleep(1)
                        if self.get_state() == "poweroff":
                            if not silent:
                                log.info(f"CLAUDE: VM '{self.vm_name}' stopped gracefully")
                            return 0

                    log.warning("CLAUDE: Graceful shutdown timed out, forcing stop")

            except Exception as e:
                log.warning(f"CLAUDE: Graceful shutdown failed: {e}, forcing stop")

            # Force stop by killing process
            if os.path.exists(self.config.pid_file_path):
                try:
                    with open(self.config.pid_file_path, 'r') as f:
                        pid = int(f.read().strip())

                    os.kill(pid, 15)  # SIGTERM
                    await asyncio.sleep(2)

                    # Check if still running
                    try:
                        os.kill(pid, 0)  # Check if process exists
                        # Still running, force kill
                        os.kill(pid, 9)  # SIGKILL
                    except ProcessLookupError:
                        pass  # Process already dead

                    if not silent:
                        log.info(f"CLAUDE: VM '{self.vm_name}' stopped")

                    # Clean up PID file
                    os.remove(self.config.pid_file_path)

                except Exception as e:
                    log.error(f"CLAUDE: Error stopping VM: {e}")
                    return 1

            return 0

        return await self.manager.run_async(_stop_async)

    async def destroy(
        self,
        ctx_manager=None,
        stop_event=None,
        log_file: Optional[Path] = None,
        silent: bool = False
    ) -> int:
        """
        Destroy the QEMU VM (delete disk and config).

        Args:
            ctx_manager: Optional context manager for status updates
            stop_event: Optional threading event to signal cancellation
            log_file: Optional path to log file
            silent: If True, suppress log output

        Returns:
            Return code (0 for success, non-zero for failure)
        """
        async def _destroy_async():
            if not silent:
                log.info(f"CLAUDE: Destroying QEMU VM '{self.vm_name}'")

            # Stop VM if running
            if self.get_state() == "running":
                await self.stop(silent=silent)

            # Delete disk
            if os.path.exists(self.config.disk_path):
                try:
                    os.remove(self.config.disk_path)
                    if not silent:
                        log.info(f"CLAUDE: Deleted VM disk: {self.config.disk_path}")
                except Exception as e:
                    log.error(f"CLAUDE: Error deleting disk: {e}")

            # Delete config
            config_path = self._get_vm_config_path()
            if config_path.exists():
                try:
                    os.remove(config_path)
                    if not silent:
                        log.info(f"CLAUDE: Deleted VM config: {config_path}")
                except Exception as e:
                    log.error(f"CLAUDE: Error deleting config: {e}")

            # Clean up sockets
            for socket_path in [self.config.qmp_socket_path, self.config.guest_agent_socket_path]:
                if os.path.exists(socket_path):
                    try:
                        os.remove(socket_path)
                    except:
                        pass

            if not silent:
                log.info(f"CLAUDE: VM '{self.vm_name}' destroyed")

            return 0

        return await self.manager.run_async(_destroy_async)

    def get_state(self) -> str:
        """
        Get the current state of the VM.

        Returns:
            "running", "poweroff", or "unknown"
        """
        # Check if PID file exists and process is running
        if os.path.exists(self.config.pid_file_path):
            try:
                with open(self.config.pid_file_path, 'r') as f:
                    pid = int(f.read().strip())

                # Check if process exists
                os.kill(pid, 0)
                return "running"

            except (ProcessLookupError, ValueError):
                # Process not found or invalid PID
                return "poweroff"
        else:
            return "poweroff"

    def vm_exists(self) -> bool:
        """
        Check if the VM exists (disk file exists).

        Returns:
            True if VM exists, False otherwise
        """
        return os.path.exists(self.config.disk_path)

    @classmethod
    def get_vm_by_name(cls, vm_name: str, manager=None) -> 'QEMUVM':
        """
        Get a VM instance by name.

        Args:
            vm_name: Name of the VM
            manager: Optional QEMUManager instance

        Returns:
            QEMUVM instance

        Raises:
            VMNotFoundException: If VM config not found
        """
        from adare.config import get_vm_credentials

        if manager is None:
            manager = QEMUManager()

        # Check if config exists
        config_dir = Path.home() / '.adare' / 'qemu' / 'vms'
        config_path = config_dir / f"{vm_name}.json"

        if not config_path.exists():
            raise VMNotFoundException(f"QEMU VM '{vm_name}' not found")

        # Load config
        with open(config_path, 'r') as f:
            data = json.load(f)

        guest_os = data.get('guest_os', 'linux')
        username, password = get_vm_credentials(guest_os)

        # Create VM instance
        vm = cls(
            vm_name=vm_name,
            guest_os=guest_os,
            manager=manager,
            username=username,
            password=password,
            cpus=data.get('cpus', 2),
            ram=data.get('ram', 2048),
            machine=data.get('machine', 'pc'),
            accel=data.get('accel', 'kvm'),
            drive_format=data.get('drive_format', 'qcow2')
        )

        return vm

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
            **kwargs: Additional arguments

        Returns:
            CommandResult with returncode, stdout, stderr
        """
        if not silent:
            log.info(f"CLAUDE: Executing command in VM '{self.vm_name}': {command}")

        returncode, stdout, stderr = await self._execute_guest_command_via_agent(
            command,
            background=background,
            stop_event=stop_event
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
        stop_event=None
    ) -> bool:
        """
        Wait until VM is fully booted and guest agent is responsive.

        Args:
            timeout: Timeout in seconds
            ctx_manager: Optional context manager for status updates
            stop_event: Optional event to signal cancellation

        Returns:
            True if VM is booted, False if timeout
        """
        log.info(f"CLAUDE: Waiting for VM '{self.vm_name}' to boot (timeout: {timeout}s)")

        start_time = time.time()
        while time.time() - start_time < timeout:
            if stop_event and stop_event.is_set():
                log.info("CLAUDE: Stop event detected")
                return False

            # Check if guest agent is responsive
            if os.path.exists(self.config.guest_agent_socket_path):
                try:
                    ping_cmd = {"execute": "guest-ping"}
                    response = await self._send_qga_command(self.config.guest_agent_socket_path, ping_cmd)

                    if 'return' in response:
                        log.info(f"CLAUDE: VM '{self.vm_name}' is fully booted")
                        return True

                except Exception:
                    pass  # Guest agent not ready yet

            await asyncio.sleep(2)

        log.warning(f"CLAUDE: Timeout waiting for VM '{self.vm_name}' to boot")
        return False

    async def create_from_ovf_or_ova(
        self,
        file_path: Path,
        silent: bool = False,
        try_extract: bool = True
    ) -> Tuple[int, str]:
        """
        Create VM from OVF/OVA file by converting disk to qcow2.

        Args:
            file_path: Path to OVF/OVA file
            silent: If True, suppress log output
            try_extract: If True, try to extract OVA

        Returns:
            Tuple of (return_code, output_message)
        """
        log.info(f"CLAUDE: Importing QEMU VM from {file_path}")

        from adare.config import HYPERVISOR_CONFIGS
        qemu_img_exe = HYPERVISOR_CONFIGS.get('qemu', {}).get('qemu_img_exe', 'qemu-img')

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

        # Convert to qcow2
        dest_disk = self.config.disk_path
        args = [qemu_img_exe, 'convert', '-O', 'qcow2', str(source_disk), dest_disk]

        try:
            result = subprocess.run(args, capture_output=True, text=True, check=False)

            if result.returncode == 0:
                log.info(f"CLAUDE: Successfully converted disk to {dest_disk}")
                self._save_vm_config()
                return 0, f"VM imported successfully"
            else:
                return result.returncode, result.stderr

        except Exception as e:
            return 1, str(e)

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
                log.error(f"CLAUDE: Queued command failed: {command}")

        self._command_queue.clear()

    def cleanup_background_processes(self):
        """Clean up background processes (no-op for QEMU, processes managed by guest agent)."""
        self._background_pids.clear()
