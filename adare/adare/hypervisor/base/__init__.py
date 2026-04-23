"""
Abstract base classes for hypervisor implementations.
"""
from .identifier_strategy import (
    HypervisorIdentifierStrategy,
    QEMUIdentifierStrategy,
    VirtualBoxIdentifierStrategy,
    get_identifier_strategy,
    get_vm_identifier,
    get_vm_state,
    register_identifier_strategy,
    verify_vm_exists,
)
from .manager import AbstractHypervisorManager
from .models import CommandResult, PortForwardingRule, SharedFolderConfig
from .vm import AbstractVM

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
