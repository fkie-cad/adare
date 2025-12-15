"""
DEPRECATED: Use adare.hypervisor module instead.

This module provides backward compatibility shims for existing code
that imports from adare.virtualbox.

New code should use:
    from adare.hypervisor import get_hypervisor_manager, get_hypervisor_vm_class
    from adare.hypervisor.virtualbox import VirtualBoxManager, VirtualBoxVM
"""
import warnings

warnings.warn(
    "adare.virtualbox is deprecated, use adare.hypervisor instead",
    DeprecationWarning,
    stacklevel=2
)

# Import from new location for backward compatibility
from adare.hypervisor.virtualbox.manager import VirtualBoxManager
from adare.hypervisor.virtualbox.vm import VirtualBoxVM
from adare.hypervisor.virtualbox.models import (
    PortForwardingRule,
    SharedFolderConfig,
    CommandResult
)
from adare.hypervisor.exceptions import (
    VMImportException,
    VMAlreadyRunningException,
    VMNotFoundException
)

__all__ = [
    'VirtualBoxManager',
    'VirtualBoxVM',
    'PortForwardingRule',
    'SharedFolderConfig',
    'CommandResult',
    'VMImportException',
    'VMAlreadyRunningException',
    'VMNotFoundException',
]