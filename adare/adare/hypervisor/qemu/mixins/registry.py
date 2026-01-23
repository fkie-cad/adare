"""
Registry Mixin - VM discovery and lookup operations.

Implements abstract methods from AbstractVM for VM discovery by UUID and name.
Delegates to QEMUVMRegistry for the actual implementation.
"""
from typing import Optional, Dict, Any


class RegistryMixin:
    """
    Mixin providing VM discovery and lookup operations.
    Implements abstract methods required by AbstractVM.
    """

    @classmethod
    def get_vm_by_name(cls, vm_name: str, manager=None):
        """
        Get VM information by name and create a VM instance.
        Delegates to QEMUVMRegistry.
        """
        from adare.hypervisor.qemu.utilities.uuid_registry import QEMUVMRegistry
        return QEMUVMRegistry.get_vm_by_name(vm_name, manager)

    @staticmethod
    def get_vm_uuid_by_name(vm_name: str) -> Optional[str]:
        """
        Get VM UUID/identifier by name.
        Delegates to QEMUVMRegistry.
        """
        from adare.hypervisor.qemu.utilities.uuid_registry import QEMUVMRegistry
        return QEMUVMRegistry.get_vm_uuid_by_name(vm_name)

    @staticmethod
    def verify_vm_exists_by_uuid(uuid: str) -> bool:
        """
        Verify if a VM exists by its UUID/identifier.
        Delegates to QEMUVMRegistry.
        """
        from adare.hypervisor.qemu.utilities.uuid_registry import QEMUVMRegistry
        return QEMUVMRegistry.verify_vm_exists_by_uuid(uuid)

    @staticmethod
    def get_vm_info_by_uuid(uuid: str) -> Optional[Dict[str, Any]]:
        """
        Get VM information by UUID/identifier.
        Delegates to QEMUVMRegistry.
        """
        from adare.hypervisor.qemu.utilities.uuid_registry import QEMUVMRegistry
        return QEMUVMRegistry.get_vm_info_by_uuid(uuid)

    @staticmethod
    def get_vm_name_by_uuid(uuid: str) -> Optional[str]:
        """
        Get VM name by UUID/identifier.
        Delegates to QEMUVMRegistry.
        """
        from adare.hypervisor.qemu.utilities.uuid_registry import QEMUVMRegistry
        return QEMUVMRegistry.get_vm_name_by_uuid(uuid)
