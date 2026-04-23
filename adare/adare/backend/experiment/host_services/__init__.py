"""
Host-side test services for ADARE.

This package provides service abstractions for host-based test execution,
enabling tests to access CV server, screenshots, and VM files through
a clean, modular interface.
"""

from .cv_service import CVService
from .guest_command_proxy import GuestCommandProxy
from .guest_file_proxy import FileMetadata, GuestFileProxy
from .screenshot_service import ScreenshotService
from .vm_file_service import VMFileService
from .vm_operation_proxy import VMOperationProxy

__all__ = [
    'CVService', 'ScreenshotService', 'VMFileService',
    'VMOperationProxy', 'GuestFileProxy', 'GuestCommandProxy', 'FileMetadata',
]
