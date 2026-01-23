"""
QEMU Utilities - Standalone helper functions and utilities.
"""

from adare.hypervisor.qemu.utilities.disk_utils import get_boot_mode_for_os
from adare.hypervisor.qemu.utilities.uuid_registry import QEMUVMRegistry

__all__ = ['get_boot_mode_for_os', 'QEMUVMRegistry']
