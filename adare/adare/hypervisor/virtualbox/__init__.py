"""
VirtualBox hypervisor implementation.

Implements AbstractHypervisorManager and AbstractVM for VirtualBox.
"""
from .manager import VirtualBoxManager
from .models import CommandResult, PortForwardingRule, SharedFolderConfig
from .vm import VirtualBoxVM


def register():
    """Register VirtualBox hypervisor with the factory."""
    from adare.hypervisor import register_hypervisor
    register_hypervisor('virtualbox', VirtualBoxManager, VirtualBoxVM)


__all__ = [
    'VirtualBoxManager',
    'VirtualBoxVM',
    'PortForwardingRule',
    'SharedFolderConfig',
    'CommandResult',
    'register',
]
