"""
Host-side test services for ADARE.

This package provides service abstractions for host-based test execution,
enabling tests to access CV server, screenshots, and VM files through
a clean, modular interface.
"""

from .cv_service import CVService
from .screenshot_service import ScreenshotService
from .vm_file_service import VMFileService
from .vm_operation_proxy import VMOperationProxy
from .guest_file_proxy import GuestFileProxy, FileMetadata
from .guest_command_proxy import GuestCommandProxy

__all__ = [
    'CVService', 'ScreenshotService', 'VMFileService',
    'VMOperationProxy', 'GuestFileProxy', 'GuestCommandProxy', 'FileMetadata',
]