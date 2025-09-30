"""
Host-side test services for ADARE.

This package provides service abstractions for host-based test execution,
enabling tests to access CV server, screenshots, and VM files through
a clean, modular interface.
"""

from .cv_service import CVService
from .screenshot_service import ScreenshotService
from .vm_file_service import VMFileService

__all__ = ['CVService', 'ScreenshotService', 'VMFileService']