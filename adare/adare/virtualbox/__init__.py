"""
VirtualBox API module for managing VirtualBox VMs.
"""

from .manager import VirtualBoxManager
from .models import (
    PortForwardingRule,
    SharedFolderConfig,
    CommandResult,
    VMImportException,
    VMAlreadyRunningException,
    VMNotFoundException,
)
from .api import VirtualBoxVM

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