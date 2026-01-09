"""
Abstract base classes for hypervisor implementations.
"""
from .manager import AbstractHypervisorManager
from .vm import AbstractVM
from .models import PortForwardingRule, SharedFolderConfig, CommandResult
from .identifier_strategy import (
    HypervisorIdentifierStrategy,
    VirtualBoxIdentifierStrategy,
    QEMUIdentifierStrategy,
    get_identifier_strategy,
    register_identifier_strategy,
    get_vm_identifier,
    verify_vm_exists,
    get_vm_state,
)

__all__ = [
    'AbstractHypervisorManager',
    'AbstractVM',
    'PortForwardingRule',
    'SharedFolderConfig',
    'CommandResult',
    # Identifier Strategy Pattern
    'HypervisorIdentifierStrategy',
    'VirtualBoxIdentifierStrategy',
    'QEMUIdentifierStrategy',
    'get_identifier_strategy',
    'register_identifier_strategy',
    'get_vm_identifier',
    'verify_vm_exists',
    'get_vm_state',
]
