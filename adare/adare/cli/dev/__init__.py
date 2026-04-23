"""
CLI command handlers for development mode operations.

This package provides exec_* functions that implement dev mode commands:
- Session management (start, stop, list, state, resume, cleanup)
- Action and playbook execution
- Reset and checkpoint operations
- Recording

All exec_* functions are re-exported here so that
``from adare.cli.dev import exec_dev_start`` continues to work.
"""

from adare.cli.dev.actions import (
    exec_dev_action,
    exec_dev_cv_start,
    exec_dev_cv_stop,
    exec_dev_playbook,
    exec_dev_playbook_batch,
    exec_dev_update_testfunctions,
    parse_indices_with_bounds,
)
from adare.cli.dev.checkpoints import (
    exec_dev_checkpoint_create,
    exec_dev_checkpoint_delete,
    exec_dev_checkpoint_list,
    exec_dev_checkpoint_restore,
    exec_dev_reset_hard,
    exec_dev_reset_soft,
)
from adare.cli.dev.recording import exec_dev_record
from adare.cli.dev.session import (
    exec_dev_cleanup,
    exec_dev_list,
    exec_dev_resume,
    exec_dev_start,
    exec_dev_state,
    exec_dev_stop,
)

__all__ = [
    # Session management
    "exec_dev_start",
    "exec_dev_stop",
    "exec_dev_resume",
    "exec_dev_list",
    "exec_dev_state",
    "exec_dev_cleanup",
    # Actions and playbooks
    "exec_dev_action",
    "exec_dev_playbook",
    "exec_dev_playbook_batch",
    "exec_dev_cv_start",
    "exec_dev_cv_stop",
    "exec_dev_update_testfunctions",
    "parse_indices_with_bounds",
    # Checkpoints and resets
    "exec_dev_checkpoint_create",
    "exec_dev_checkpoint_restore",
    "exec_dev_checkpoint_list",
    "exec_dev_checkpoint_delete",
    "exec_dev_reset_soft",
    "exec_dev_reset_hard",
    # Recording
    "exec_dev_record",
]
