"""
Hypervisor Identifier Strategy Pattern.

Provides a polymorphic way to handle VM instance identification across
different hypervisors (VirtualBox uses UUIDs, QEMU uses instance names).

This eliminates scattered type-checking code like:
    if vm_instance.vm.hypervisor == 'virtualbox':
        uuid = vm_instance.vbox_uuid
    elif vm_instance.vm.hypervisor == 'qemu':
        identifier = vm_instance.instance_name

Instead, use:
    strategy = get_identifier_strategy(vm_instance.vm.hypervisor)
    identifier = strategy.get_identifier(vm_instance)
    if strategy.verify_exists(identifier):
        # Work with VM
"""

from abc import ABC, abstractmethod
from typing import Optional, TYPE_CHECKING
import logging

if TYPE_CHECKING:
    from adare.database.models.global_models import VmInstance

log = logging.getLogger(__name__)


class HypervisorIdentifierStrategy(ABC):
    """
    Abstract base class for hypervisor-specific VM instance identification.

    Each hypervisor has its own way of identifying VM instances:
    - VirtualBox: Uses UUIDs generated on import
    - QEMU: Uses domain names (instance_name)

    This strategy pattern centralizes this logic and makes it easy to add
    new hypervisors without modifying existing code.
    """

    @property
    @abstractmethod
    def hypervisor_name(self) -> str:
        """Return the hypervisor name this strategy handles."""
        pass

    @abstractmethod
    def get_identifier(self, vm_instance: 'VmInstance') -> Optional[str]:
        """
        Get the hypervisor-specific identifier for a VM instance.

        Args:
            vm_instance: VmInstance database model

        Returns:
            The hypervisor-specific identifier, or None if not available
        """
        pass

    @abstractmethod
    def verify_exists(self, identifier: str) -> bool:
        """
        Verify that a VM with the given identifier exists in the hypervisor.

        Args:
            identifier: Hypervisor-specific identifier

        Returns:
            True if the VM exists, False otherwise
        """
        pass

    @abstractmethod
    def get_vm_state(self, identifier: str) -> str:
        """
        Get the current state of the VM.

        Args:
            identifier: Hypervisor-specific identifier

        Returns:
            VM state string (e.g., 'running', 'poweroff', 'not_found')
        """
        pass

    def get_vm_name(self, identifier: str) -> Optional[str]:
        """
        Get the VM name from the identifier.

        For some hypervisors (like QEMU), the identifier IS the name.
        For others (like VirtualBox), we need to look it up.

        Args:
            identifier: Hypervisor-specific identifier

        Returns:
            VM name, or None if not found
        """
        # Default implementation assumes identifier is the name
        return identifier


class VirtualBoxIdentifierStrategy(HypervisorIdentifierStrategy):
    """VirtualBox-specific identifier strategy using UUIDs."""

    @property
    def hypervisor_name(self) -> str:
        return 'virtualbox'

    def get_identifier(self, vm_instance: 'VmInstance') -> Optional[str]:
        """Get the VirtualBox UUID for the instance."""
        return vm_instance.vbox_uuid

    def verify_exists(self, identifier: str) -> bool:
        """Verify VM exists in VirtualBox by UUID."""
        if not identifier:
            return False

        try:
            from adare.hypervisor.virtualbox.vm import VirtualBoxVM
            vm_name = VirtualBoxVM.get_vm_name_by_uuid(identifier)
            return vm_name is not None
        except ImportError:
            log.warning("VirtualBox hypervisor module not available")
            return False

    def get_vm_state(self, identifier: str) -> str:
        """Get VirtualBox VM state."""
        if not identifier:
            return "not_found"

        try:
            from adare.hypervisor.virtualbox.vm import VirtualBoxVM
            from adare.hypervisor.virtualbox.manager import VirtualBoxManager

            vm_name = VirtualBoxVM.get_vm_name_by_uuid(identifier)
            if not vm_name:
                return "not_found"

            manager = VirtualBoxManager()
            vbox_vm = VirtualBoxVM(vm_name, "", manager, "dummy", "dummy", manager.executables)
            return vbox_vm._get_state(raise_on_missing=False)

        except ImportError:
            log.warning("VirtualBox hypervisor module not available")
            return "error"

    def get_vm_name(self, identifier: str) -> Optional[str]:
        """Look up VM name from VirtualBox UUID."""
        if not identifier:
            return None

        try:
            from adare.hypervisor.virtualbox.vm import VirtualBoxVM
            return VirtualBoxVM.get_vm_name_by_uuid(identifier)
        except ImportError:
            log.warning("VirtualBox hypervisor module not available")
            return None


class QEMUIdentifierStrategy(HypervisorIdentifierStrategy):
    """QEMU/libvirt-specific identifier strategy using domain names."""

    @property
    def hypervisor_name(self) -> str:
        return 'qemu'

    def get_identifier(self, vm_instance: 'VmInstance') -> Optional[str]:
        """Get the instance name (domain name) for QEMU instances."""
        return vm_instance.instance_name

    def verify_exists(self, identifier: str) -> bool:
        """Verify domain exists in libvirt."""
        if not identifier:
            return False

        try:
            from adare.hypervisor.qemu.utilities.uuid_registry import QEMUVMRegistry
            vm = QEMUVMRegistry.get_vm_by_name(identifier)
            return vm is not None
        except ImportError:
            log.warning("QEMU hypervisor module not available")
            return False

    def get_vm_state(self, identifier: str) -> str:
        """Get QEMU/libvirt domain state."""
        if not identifier:
            return "not_found"

        try:
            from adare.hypervisor.qemu.utilities.uuid_registry import QEMUVMRegistry
            vm = QEMUVMRegistry.get_vm_by_name(identifier)
            if not vm:
                return "not_found"

            # Get libvirt domain state
            state = vm.get_state()
            return state

        except ImportError:
            log.warning("QEMU hypervisor module not available")
            return "error"


# Registry of identifier strategies by hypervisor name
_IDENTIFIER_STRATEGIES: dict[str, HypervisorIdentifierStrategy] = {
    'virtualbox': VirtualBoxIdentifierStrategy(),
    'qemu': QEMUIdentifierStrategy(),
}


def get_identifier_strategy(hypervisor: str) -> HypervisorIdentifierStrategy:
    """
    Get the appropriate identifier strategy for a hypervisor.

    Args:
        hypervisor: Hypervisor name ('virtualbox', 'qemu')

    Returns:
        HypervisorIdentifierStrategy instance

    Raises:
        KeyError: If hypervisor is not supported
    """
    if hypervisor not in _IDENTIFIER_STRATEGIES:
        raise KeyError(
            f"No identifier strategy for hypervisor '{hypervisor}'. "
            f"Supported hypervisors: {list(_IDENTIFIER_STRATEGIES.keys())}"
        )
    return _IDENTIFIER_STRATEGIES[hypervisor]


def register_identifier_strategy(hypervisor: str, strategy: HypervisorIdentifierStrategy) -> None:
    """
    Register a new identifier strategy for a hypervisor.

    This allows adding support for new hypervisors at runtime.

    Args:
        hypervisor: Hypervisor name
        strategy: Strategy instance to register
    """
    _IDENTIFIER_STRATEGIES[hypervisor] = strategy
    log.info(f"Registered identifier strategy for hypervisor: {hypervisor}")


def get_vm_identifier(vm_instance: 'VmInstance') -> Optional[str]:
    """
    Convenience function to get the identifier for a VM instance.

    This uses the VmInstance's hypervisor_identifier hybrid property,
    or falls back to the appropriate strategy.

    Args:
        vm_instance: VmInstance database model

    Returns:
        Hypervisor-specific identifier, or None if not available
    """
    # Use the model's hybrid property if available
    return vm_instance.hypervisor_identifier


def verify_vm_exists(vm_instance: 'VmInstance') -> bool:
    """
    Convenience function to verify a VM instance exists in its hypervisor.

    Args:
        vm_instance: VmInstance database model

    Returns:
        True if the VM exists in the hypervisor
    """
    if not vm_instance.vm:
        return False

    strategy = get_identifier_strategy(vm_instance.vm.hypervisor)
    identifier = strategy.get_identifier(vm_instance)

    if not identifier:
        return False

    return strategy.verify_exists(identifier)


def get_vm_state(vm_instance: 'VmInstance') -> str:
    """
    Convenience function to get VM state from its hypervisor.

    Args:
        vm_instance: VmInstance database model

    Returns:
        VM state string
    """
    if not vm_instance.vm:
        return "error"

    strategy = get_identifier_strategy(vm_instance.vm.hypervisor)
    identifier = strategy.get_identifier(vm_instance)

    if not identifier:
        return "not_found"

    return strategy.get_vm_state(identifier)
