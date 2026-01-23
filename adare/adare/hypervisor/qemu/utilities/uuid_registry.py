"""
UUID Registry - VM discovery and lookup operations.

Provides a registry pattern for VM discovery by UUID and name.
"""
import glob
import json
from pathlib import Path
from typing import Optional, Dict, Any


class QEMUVMRegistry:
    """
    Registry for VM lookup operations by UUID and name.
    All methods are static and operate on the VM config directory.
    """

    @staticmethod
    def get_vm_by_name(vm_name: str, manager=None) -> 'QEMUVM':
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
        from adare.hypervisor.qemu.manager import QEMUManager
        from adare.hypervisor.qemu.vm import QEMUVM
        from adare.hypervisor.exceptions import VMNotFoundException

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
        vm = QEMUVM(
            vm_name=vm_name,
            guest_os=guest_os,
            manager=manager,
            username=username,
            password=password,
            executables=manager.executables,
            cpus=data.get('cpus', 2),
            ram=data.get('ram', 2048),
            machine=data.get('machine', 'pc'),
            accel=data.get('accel', 'kvm'),
            drive_format=data.get('drive_format', 'qcow2')
        )

        return vm

    @staticmethod
    def get_vm_info_by_uuid(uuid: str) -> Optional[Dict[str, Any]]:
        """
        Get VM information by UUID/identifier.

        For QEMU, we search through all VM config files to find one with matching UUID.

        Args:
            uuid: VM UUID/identifier

        Returns:
            Dictionary of VM information if found, None otherwise
        """
        from adare.config import get_vm_credentials

        # Search for all VM config files
        config_dir = Path.home() / '.adare' / 'qemu' / 'vms'
        if not config_dir.exists():
            return None

        config_files = glob.glob(str(config_dir / "*.json"))
        for config_file in config_files:
            try:
                with open(config_file, 'r') as f:
                    data = json.load(f)

                # Check if UUID matches
                if data.get('uuid') == uuid:
                    vm_name = data.get('vm_name')
                    guest_os = data.get('guest_os', 'linux')
                    username, password = get_vm_credentials(guest_os)

                    return {
                        'name': vm_name,
                        'uuid': uuid,
                        'guest_os': guest_os,
                        'username': username,
                        'password': password,
                        'cpus': data.get('cpus', 2),
                        'ram': data.get('ram', 2048),
                        'disk_path': data.get('disk_path'),
                        'config_path': config_file
                    }
            except (json.JSONDecodeError, KeyError, IOError):
                # Skip invalid config files
                continue

        return None

    @staticmethod
    def get_vm_name_by_uuid(uuid: str) -> Optional[str]:
        """
        Get VM name by UUID/identifier.

        For QEMU, we search through all VM config files to find one with matching UUID.

        Args:
            uuid: VM UUID/identifier

        Returns:
            VM name if found, None otherwise
        """
        # Search for all VM config files
        config_dir = Path.home() / '.adare' / 'qemu' / 'vms'
        if not config_dir.exists():
            return None

        config_files = glob.glob(str(config_dir / "*.json"))
        for config_file in config_files:
            try:
                with open(config_file, 'r') as f:
                    data = json.load(f)

                # Check if UUID matches
                if data.get('uuid') == uuid:
                    return data.get('vm_name')
            except (json.JSONDecodeError, KeyError, IOError):
                # Skip invalid config files
                continue

        return None

    @staticmethod
    def get_vm_uuid_by_name(vm_name: str) -> Optional[str]:
        """
        Get VM UUID/identifier by name.

        For QEMU, the UUID is stored in the VM config file.

        Args:
            vm_name: Name of the VM

        Returns:
            VM UUID/identifier if found, None otherwise
        """
        # Check if config exists
        config_dir = Path.home() / '.adare' / 'qemu' / 'vms'
        config_path = config_dir / f"{vm_name}.json"

        if not config_path.exists():
            return None

        try:
            with open(config_path, 'r') as f:
                data = json.load(f)
            return data.get('uuid')
        except (json.JSONDecodeError, KeyError, IOError):
            return None

    @staticmethod
    def verify_vm_exists_by_uuid(uuid: str) -> bool:
        """
        Verify if a VM exists by its UUID/identifier.

        For QEMU, we search through all VM config files to find one with matching UUID.

        Args:
            uuid: VM UUID/identifier

        Returns:
            True if VM exists, False otherwise
        """
        # Search for all VM config files
        config_dir = Path.home() / '.adare' / 'qemu' / 'vms'
        if not config_dir.exists():
            return False

        config_files = glob.glob(str(config_dir / "*.json"))
        for config_file in config_files:
            try:
                with open(config_file, 'r') as f:
                    data = json.load(f)

                # Check if UUID matches
                if data.get('uuid') == uuid:
                    return True
            except (json.JSONDecodeError, KeyError, IOError):
                # Skip invalid config files
                continue

        return False
