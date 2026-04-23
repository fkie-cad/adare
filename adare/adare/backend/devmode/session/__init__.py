"""
Development mode session management.

This package provides the core DevModeSession class that wraps the existing
experiment run infrastructure to enable interactive playbook development.

The class is composed from mixins in sub-modules:
- core.py: Initialization, logging, utilities, state query
- lifecycle.py: Start, shutdown, stop, cleanup
- action_execution.py: Action/playbook execution, MCP server, recording
- snapshots.py: Snapshots, checkpoints, soft/hard resets
"""

from .action_execution import DevModeActionExecutionMixin
from .core import DevModeSessionCore, DevModeSnapshot, DevModeState
from .lifecycle import DevModeLifecycleMixin
from .snapshots import DevModeSnapshotsMixin


class DevModeSession(
    DevModeSnapshotsMixin,
    DevModeActionExecutionMixin,
    DevModeLifecycleMixin,
    DevModeSessionCore,
):
    """
    Development mode session - a long-lived, interactive experiment run.

    This class wraps the standard experiment run infrastructure to provide
    interactive development capabilities while maximizing code reuse.

    Architecture:
        - Facade pattern: Wraps ExperimentRunCtx, PlaybookController, VMLifecycleManager
        - Reuses 95%+ of experiment execution infrastructure
        - Zero modifications to core experiment components
        - Composed from mixins for maintainability:
          - DevModeSessionCore: __init__, logging, utilities
          - DevModeLifecycleMixin: start, shutdown, stop_and_remove
          - DevModeActionExecutionMixin: execute_action, execute_playbook, MCP, recording
          - DevModeSnapshotsMixin: snapshots, checkpoints, resets

    MRO (method resolution order):
        DevModeSnapshotsMixin -> DevModeActionExecutionMixin ->
        DevModeLifecycleMixin -> DevModeSessionCore

        This ensures lifecycle methods (stop_and_remove) can call snapshot methods
        (_cleanup_snapshots), and all mixins can access core attributes/methods.

    Usage:
        session = DevModeSession(session_id, project_path, experiment_name, env_name)
        await session.start()
        result = await session.execute_action(action)
        await session.reset_hard()
        await session.stop()
    """
    pass


__all__ = [
    "DevModeSession",
    "DevModeSnapshot",
    "DevModeState",
]
