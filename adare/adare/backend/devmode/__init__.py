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

from .session import DevModeSession, DevModeState, DevModeSnapshot
from .manager import DevModeSessionManager

__all__ = [
    "DevModeSession",
    "DevModeState",
    "DevModeSnapshot",
    "DevModeSessionManager",
]
