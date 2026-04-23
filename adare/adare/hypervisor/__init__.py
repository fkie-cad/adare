"""
Hypervisor abstraction layer with factory pattern for runtime selection.

This module provides a factory pattern for creating hypervisor instances,
allowing different hypervisors (VirtualBox, QEMU, etc.) to be used interchangeably.
"""
import logging
from typing import Optional

log = logging.getLogger(__name__)

# Registry of available hypervisors
_HYPERVISOR_REGISTRY = {}


def register_hypervisor(name: str, manager_class, vm_class):
    """
    Register a hypervisor implementation.

    Args:
        name: Hypervisor name (e.g., 'virtualbox', 'qemu')
        manager_class: Hypervisor manager class (implements AbstractHypervisorManager)
        vm_class: VM class (implements AbstractVM)
    """
    _HYPERVISOR_REGISTRY[name] = {
        'manager': manager_class,
        'vm': vm_class
    }
    log.debug(f"Registered hypervisor: {name}")


def get_hypervisor_manager(hypervisor: str | None = None):
    """
    Get a hypervisor manager instance.

    Args:
        hypervisor: Hypervisor name ('virtualbox', 'qemu', etc.)
                   If None, uses DEFAULT_HYPERVISOR from config

    Returns:
        Hypervisor manager instance

    Raises:
        ValueError: If hypervisor is not supported
    """
    from adare.config import DEFAULT_HYPERVISOR, SUPPORTED_HYPERVISORS

    if hypervisor is None:
        hypervisor = DEFAULT_HYPERVISOR

    hypervisor = hypervisor.lower()

    if hypervisor not in SUPPORTED_HYPERVISORS:
        raise ValueError(f"Unsupported hypervisor: {hypervisor}. Supported: {SUPPORTED_HYPERVISORS}")

    if hypervisor not in _HYPERVISOR_REGISTRY:
        # Lazy loading - import hypervisor module
        _load_hypervisor_module(hypervisor)

    if hypervisor not in _HYPERVISOR_REGISTRY:
        raise ValueError(f"Hypervisor {hypervisor} could not be loaded")

    manager_class = _HYPERVISOR_REGISTRY[hypervisor]['manager']
    return manager_class()


def get_hypervisor_vm_class(hypervisor: str | None = None):
    """
    Get the VM class for a specific hypervisor.

    Args:
        hypervisor: Hypervisor name ('virtualbox', 'qemu', etc.)
                   If None, uses DEFAULT_HYPERVISOR from config

    Returns:
        VM class for the specified hypervisor

    Raises:
        ValueError: If hypervisor is not supported
    """
    from adare.config import DEFAULT_HYPERVISOR

    if hypervisor is None:
        hypervisor = DEFAULT_HYPERVISOR

    hypervisor = hypervisor.lower()

    if hypervisor not in _HYPERVISOR_REGISTRY:
        _load_hypervisor_module(hypervisor)

    return _HYPERVISOR_REGISTRY[hypervisor]['vm']


def _load_hypervisor_module(hypervisor: str):
    """
    Lazy load hypervisor implementation module.

    Args:
        hypervisor: Hypervisor name to load

    Raises:
        ValueError: If hypervisor module is unknown
    """
    try:
        if hypervisor == 'virtualbox':
            from adare.hypervisor.virtualbox import register as register_virtualbox
            register_virtualbox()
        elif hypervisor == 'qemu':
            from adare.hypervisor.qemu import register as register_qemu
            register_qemu()
        else:
            raise ValueError(f"Unknown hypervisor: {hypervisor}")
    except ImportError as e:
        log.error(f"Failed to load hypervisor module '{hypervisor}': {e}")
        raise






__all__ = [
    'register_hypervisor',
    'get_hypervisor_manager',
    'get_hypervisor_vm_class',
]
