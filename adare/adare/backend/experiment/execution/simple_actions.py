"""
Executors for simple playbook actions (GUI interactions and system operations).

Includes: click, drag, keyboard, idle, scroll, goto, screenshot, command,
save_timestamp, and pull actions.

The actual action methods are organized into mixins:
- GUIActionsMixin: click, drag, keyboard, idle, scroll, goto, screenshot
- DataActionsMixin: command, save_timestamp, save_variable, pull
- FilesystemActionsMixin: snapshot_filesystem, pull_changed_files
"""

import logging
import re

from .base import ActionResult  # noqa: F401 - re-exported for backward compatibility
from .data_actions import DataActionsMixin
from .executor_core import ActionsExecutorCore
from .filesystem_actions import FilesystemActionsMixin
from .gui_actions import GUIActionsMixin

log = logging.getLogger(__name__)


def sanitize_filename(name: str) -> str:
    """
    Sanitize filename to remove invalid characters and ensure safety.

    Args:
        name: Desired filename (without extension)

    Returns:
        Sanitized filename safe for filesystem use
    """
    # Remove or replace invalid characters
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name)
    # Remove leading/trailing whitespace and dots
    sanitized = sanitized.strip(' .')
    # Limit length to 200 characters (leaves room for extension and path)
    sanitized = sanitized[:200]
    # If empty after sanitization, use fallback
    if not sanitized:
        sanitized = 'screenshot'
    return sanitized


class SimpleActionsExecutor(GUIActionsMixin, DataActionsMixin, FilesystemActionsMixin, ActionsExecutorCore):
    """Handles execution of simple playbook actions (GUI and system operations)."""
