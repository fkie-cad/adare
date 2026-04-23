"""
Development mode for ADARE.

This package provides an interactive development mode for testing and developing playbooks.
Dev mode wraps the existing experiment run infrastructure to provide:
- Long-lived VM sessions
- Interactive action execution
- Soft/hard reset capabilities
- Checkpoint management

Architecture:
- DevModeSession: Facade wrapping ExperimentRunCtx + PlaybookController
- DevModeSessionManager: Singleton managing multiple sessions
"""

from .manager import DevModeSessionManager
from .session import DevModeSession, DevModeSnapshot, DevModeState  # noqa: F401

__all__ = [
    "DevModeSession",
    "DevModeState",
    "DevModeSnapshot",
    "DevModeSessionManager",
]
