"""
Abstract base classes for hypervisor implementations.
"""
from .manager import AbstractHypervisorManager
from .vm import AbstractVM
from .models import PortForwardingRule, SharedFolderConfig, CommandResult

__all__ = [
    'AbstractHypervisorManager',
    'AbstractVM',
    'PortForwardingRule',
    'SharedFolderConfig',
    'CommandResult',
]
