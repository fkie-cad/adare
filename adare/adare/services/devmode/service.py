"""
DevMode Service - Business logic for development mode operations.

This service handles dev mode session operations and returns Result[T] objects
that can be consumed by any frontend (CLI, Web UI, REST API).

The service is composed from mixins that handle specific concerns:
- SessionManagementMixin: Session lifecycle (start, resume, stop, list, etc.)
- ActionExecutionMixin: Action and playbook execution
- CheckpointManagementMixin: Checkpoints, resets, and VM resource validation
"""

from adare.backend.devmode.manager import DevModeSessionManager
from adare.database.api.devmode import DevModeApi
from adare.services.devmode.action_execution import ActionExecutionMixin
from adare.services.devmode.checkpoint_management import CheckpointManagementMixin
from adare.services.devmode.session_management import SessionManagementMixin


class DevModeService(
    SessionManagementMixin,
    ActionExecutionMixin,
    CheckpointManagementMixin,
):
    """
    Service for development mode operations.

    Provides a synchronous API over the async DevModeSessionManager,
    with database persistence and multi-source input support.
    """

    def __init__(self):
        """Initialize the DevMode service."""
        self._manager = DevModeSessionManager()
        self._db_api = DevModeApi()
