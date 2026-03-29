"""
Configuration Mixin - VM configuration lifecycle (load, save, defaults).
"""
import json
import logging
import subprocess
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from adare.hypervisor.exceptions import HypervisorException
from adare.hypervisor.qemu.models import QEMUVMConfig
from adare.hypervisor.qemu.utilities.disk_utils import get_boot_mode_for_os

if TYPE_CHECKING:
    from adare.hypervisor.qemu.vm import QEMUVM

log = logging.getLogger(__name__)


class ConfigurationMixin:
    """
    Mixin for VM configuration operations.

    Provides methods for loading, saving, and managing VM configuration files.
    Configuration includes disk paths, boot mode, resources, and runtime settings.
    """

    @staticmethod
    def _detect_disk_format_static(file_path: Path, qemu_img_exe: str = 'qemu-img') -> str:
        """
        Detect disk image format using qemu-img info (static version).

        Args:
            file_path: Path to disk image file
            qemu_img_exe: Path to qemu-img executable

        Returns:
            Format string (e.g., 'qcow2', 'vmdk', 'vdi', 'raw', 'vpc')
            Returns 'ova' for OVA files (special marker indicating extraction needed)

        Raises:
            HypervisorException: If format detection fails
        """
        # For OVA files, need to extract first to detect disk format
        if str(file_path).endswith('.ova'):
            log.debug(f"OVA file detected, will need extraction: {file_path}")
            return 'ova'

        # Use qemu-img info with JSON output
        args = [qemu_img_exe, 'info', '--output=json', str(file_path)]

        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                check=False
            )

            if result.returncode != 0:
                raise HypervisorException(
                    f"Failed to detect disk format for {file_path}: {result.stderr}"
                )

            info = json.loads(result.stdout)
            disk_format = info.get('format', 'unknown')

            log.debug(f"Detected disk format: {disk_format} for {file_path}")
            return disk_format

        except json.JSONDecodeError as e:
            raise HypervisorException(
                f"Failed to parse qemu-img info output: {e}"
            )
        except FileNotFoundError:
            raise HypervisorException(
                f"qemu-img executable not found. Please install QEMU tools."
            )
        except (OSError, IOError) as e:
            raise HypervisorException(
                f"Error detecting disk format: {e}"
            )

    def _detect_disk_format(self: 'QEMUVM', file_path: Path) -> str:
        """
        Detect disk image format using qemu-img info (instance method wrapper).

        Args:
            file_path: Path to disk image file

        Returns:
            Format string (e.g., 'qcow2', 'vmdk', 'vdi', 'raw', 'vpc')
            Returns 'ova' for OVA files (special marker indicating extraction needed)

        Raises:
            HypervisorException: If format detection fails
        """
        return self._detect_disk_format_static(file_path, self.executables.qemu_img)

    def _get_vm_config_path(self: 'QEMUVM') -> Path:
        """Get path to VM configuration JSON file."""
        # Store VM configs in ~/.adare/qemu/vms/
        config_dir = Path.home() / '.adare' / 'qemu' / 'vms'
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / f"{self.vm_name}.json"

    def _load_or_create_vm_config(self: 'QEMUVM') -> QEMUVMConfig:
        """Load VM config from JSON or create new one."""
        config_path = self._get_vm_config_path()

        if config_path.exists():
            log.debug(f"Loading VM config from {config_path}")
            with open(config_path, 'r') as f:
                data = json.load(f)
            config = QEMUVMConfig.from_dict(data)

            # CRITICAL FIX: Override disk_path if external path provided
            # This prevents using stale disk_path from saved config
            if self._external_disk_path:
                config.disk_path = self._external_disk_path
                log.debug(f"Overriding config disk_path with external: {self._external_disk_path}")

            # Validate and sync guest_os, architecture, and boot_mode from current environment
            # This fixes stale configs that may have incorrect values
            current_arch = getattr(self, 'architecture', 'x86_64')
            expected_boot_mode = get_boot_mode_for_os(self.guest_os, current_arch)
            config_updated = False

            if config.guest_os != self.guest_os:
                log.info(f"Updating guest_os in VM config: {config.guest_os} → {self.guest_os}")
                config.guest_os = self.guest_os
                config_updated = True

            if config.architecture != current_arch:
                log.info(f"Updating architecture in VM config: {config.architecture} → {current_arch}")
                config.architecture = current_arch
                config_updated = True

            if config.boot_mode != expected_boot_mode:
                log.info(f"Updating boot_mode in VM config: {config.boot_mode} → {expected_boot_mode}")
                config.boot_mode = expected_boot_mode
                config_updated = True

            # Sync Windows resource defaults
            # Windows VMs need more resources (4 vCPU, 8GB RAM) for proper operation
            if 'windows' in self.guest_os.lower():
                # Upgrade to Windows defaults if currently at standard defaults
                if config.cpus == 2:
                    log.info(f"Upgrading Windows VM to 4 vCPUs (was: 2)")
                    config.cpus = 4
                    config_updated = True

                if config.ram == 2048:
                    log.info(f"Upgrading Windows VM to 8192 MB RAM (was: 2048)")
                    config.ram = 8192
                    config_updated = True

            if config_updated:
                log.info(f"Saving updated VM config to {config_path}")
                self._save_vm_config_obj(config)

            return config
        else:
            log.debug(f"Creating new VM config for '{self.vm_name}'")
            # Create new config
            vm_uuid = str(uuid.uuid4())

            # Determine disk path: use external path if provided, otherwise use managed storage
            if self._external_disk_path:
                disk_path = self._external_disk_path
                log.debug(f"Using external disk path for --no-copy mode: {disk_path}")
            else:
                disk_dir = Path.home() / '.adare' / 'qemu' / 'disks'
                disk_dir.mkdir(parents=True, exist_ok=True)
                disk_path = str(disk_dir / f"{self.vm_name}.qcow2")
                log.debug(f"Using managed disk path: {disk_path}")

            # Socket paths
            runtime_dir = Path.home() / '.adare' / 'qemu' / 'run'
            runtime_dir.mkdir(parents=True, exist_ok=True)
            qmp_socket = str(runtime_dir / f"{self.vm_name}.qmp")
            qga_socket = str(runtime_dir / f"{self.vm_name}.qga")
            pid_file = str(runtime_dir / f"{self.vm_name}.pid")

            # Validate socket path lengths (Unix sockets have ~108 character limit)
            for name, path in [("QMP", qmp_socket), ("Guest Agent", qga_socket)]:
                if len(path) > 107:
                    raise ValueError(f"{name} socket path too long ({len(path)} > 107 chars): {path}")

            # Determine boot mode based on guest OS and architecture
            current_arch = getattr(self, 'architecture', 'x86_64')
            boot_mode = get_boot_mode_for_os(self.guest_os, current_arch)

            # Windows VMs need more resources for proper operation
            # Use higher defaults if the current values are the standard defaults
            if 'windows' in self.guest_os.lower():
                # If using default values (2 vCPU, 2048 MB), upgrade to Windows defaults
                config_cpus = self.cpus if self.cpus != 2 else 4
                config_ram = self.ram if self.ram != 2048 else 8192  # 8GB for Windows 11
                if config_cpus != self.cpus or config_ram != self.ram:
                    log.info(f"Using Windows VM defaults: {config_cpus} vCPU, {config_ram} MB RAM")
            else:
                config_cpus = self.cpus
                config_ram = self.ram

            config = QEMUVMConfig(
                vm_name=self.vm_name,
                uuid=vm_uuid,
                guest_os=self.guest_os,
                architecture=current_arch,
                disk_path=disk_path,
                cpus=config_cpus,
                ram=config_ram,
                machine=self.machine,
                accel=self.accel,
                drive_format=self.drive_format,
                boot_mode=boot_mode,
                network='user',
                qmp_socket_path=qmp_socket,
                guest_agent_socket_path=qga_socket,
                pid_file_path=pid_file
            )

            self._save_vm_config_obj(config)
            return config

    def _save_vm_config(self: 'QEMUVM'):
        """Save current VM config to JSON file."""
        self._save_vm_config_obj(self.config)

    def _save_vm_config_obj(self: 'QEMUVM', config: QEMUVMConfig):
        """
        Save VM config object to JSON file.

        IMPORTANT: This method ensures that overlay paths are NEVER persisted to the
        config file. If the current disk_path is an overlay, we substitute it with
        the original disk path to prevent overlay chaining on subsequent runs.
        """
        config_path = self._get_vm_config_path()

        # Create a copy of config dict to avoid modifying the in-memory config
        config_dict = config.to_dict()

        # CRITICAL: Don't persist overlay paths - they cause chaining bugs
        # If disk_path contains '-overlay-', substitute with the original path
        disk_path = config_dict.get('disk_path', '')
        if '-overlay-' in disk_path:
            # Determine the original disk path to persist instead
            if self._external_disk_path:
                # External qcow2: use the original path
                original_path = self._external_disk_path
                log.debug(f"Config save: replacing overlay path with external: {original_path}")
            else:
                # Managed VM: use the base disk path (without -base suffix for config)
                # The original config disk_path format is: /path/to/VM-name.qcow2
                # Strip overlay suffix and -base to get back to original format
                stripped = self._strip_overlay_suffixes(Path(disk_path).stem)
                stripped = stripped.replace('-base', '')
                original_path = str(Path(disk_path).parent / f"{stripped}{Path(disk_path).suffix}")
                log.debug(f"Config save: replacing overlay path with original: {original_path}")

            config_dict['disk_path'] = original_path

        log.debug(f"Saving VM config to {config_path}")
        with open(config_path, 'w') as f:
            json.dump(config_dict, f, indent=2)
