"""
CLI command handlers for dev mode checkpoint and reset operations.

Provides exec_* functions for:
- Checkpoint create, restore, list, delete
- Soft and hard reset
"""

import logging

from adare.api import AdareAPI
from adare.cli.dev._helpers import _resolve_session_id
from adare.cli.utils import handle_api_error
from adare.console import print_success_message
from adare.core.dto.devmode import (
    DevCheckpointCreateRequest,
    DevCheckpointListRequest,
    DevCheckpointRestoreRequest,
    DevResetRequest,
)

log = logging.getLogger(__name__)


def exec_dev_reset_soft(arguments):
    """Soft reset (variables only)."""
    # AUTO-DETECT SESSION ID
    session_id = _resolve_session_id(arguments.session_id)

    api = AdareAPI()
    result = api.devmode.reset_soft(DevResetRequest(
        session_id=session_id,
        reset_type='soft'
    ))

    if result.success:
        reset_result = result.data
        print_success_message(
            title='Soft reset completed'
        )
        print(f"\n{reset_result.message}")
        print(f"Execution Time: {reset_result.execution_time:.2f}s")
    else:
        handle_api_error(result)


def exec_dev_reset_hard(arguments):
    """Hard reset (full VM restore)."""
    # AUTO-DETECT SESSION ID
    session_id = _resolve_session_id(arguments.session_id)

    api = AdareAPI()
    result = api.devmode.reset_hard(DevResetRequest(
        session_id=session_id,
        reset_type='hard'
    ))

    if result.success:
        reset_result = result.data
        print_success_message(
            title='Hard reset completed'
        )
        print(f"\n{reset_result.message}")
        print(f"Execution Time: {reset_result.execution_time:.2f}s")
        print("\nVM has been restored to initial snapshot")
        print("All variables have been reset")
    else:
        handle_api_error(result)


def exec_dev_checkpoint_create(arguments):
    """Create a checkpoint."""
    # AUTO-DETECT SESSION ID
    session_id = _resolve_session_id(arguments.session_id)

    api = AdareAPI()
    result = api.devmode.create_checkpoint(DevCheckpointCreateRequest(
        session_id=session_id,
        name=arguments.name,
        description=arguments.description
    ))

    if result.success:
        print_success_message(
            title=f'Checkpoint "{arguments.name}" created'
        )
    else:
        handle_api_error(result)


def exec_dev_checkpoint_restore(arguments):
    """Restore a checkpoint."""
    # AUTO-DETECT SESSION ID
    session_id = _resolve_session_id(arguments.session_id)

    api = AdareAPI()
    result = api.devmode.restore_checkpoint(DevCheckpointRestoreRequest(
        session_id=session_id,
        name=arguments.name
    ))

    if result.success:
        print_success_message(
            title=f'Checkpoint "{arguments.name}" restored'
        )
    else:
        handle_api_error(result)


def exec_dev_checkpoint_list(arguments):
    """List checkpoints."""
    # AUTO-DETECT SESSION ID
    session_id = _resolve_session_id(arguments.session_id)

    api = AdareAPI()
    result = api.devmode.list_checkpoints(DevCheckpointListRequest(
        session_id=session_id
    ))

    if result.success:
        if not result.data:
            print(f"No checkpoints found for session {session_id}")
            print(f"\nCreate a checkpoint with: adare dev checkpoint-create -s {session_id} <name>")
        else:
            # Use Rich table panel for display
            import pandas as pd
            from rich.layout import Layout

            from adare.frontend.terminal.console import DefaultConsole
            from adare.frontend.terminal.dev_session_list import DevCheckpointTablePanel

            # Convert to DataFrame
            data = []
            for checkpoint in result.data:
                data.append({
                    'name': checkpoint.name,
                    'description': checkpoint.description,
                    'created_at': checkpoint.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'variable_count': checkpoint.variable_count,
                    'file_size_mb': checkpoint.file_size_mb,
                    'checkpoint_id': checkpoint.checkpoint_id,
                })

            df = pd.DataFrame(data)

            # Print table
            console = DefaultConsole()
            layout = Layout(name="root")
            panel = DevCheckpointTablePanel(df)
            layout.update(panel)
            console.print(layout)
    else:
        handle_api_error(result)


def exec_dev_checkpoint_delete(arguments):
    """Delete a checkpoint."""
    # AUTO-DETECT SESSION ID
    session_id = _resolve_session_id(arguments.session_id)

    from adare.core.dto.devmode import DevCheckpointDeleteRequest

    api = AdareAPI()
    result = api.devmode.delete_checkpoint(DevCheckpointDeleteRequest(
        session_id=session_id,
        name=arguments.name
    ))

    if result.success:
        print_success_message(
            title=f'Checkpoint "{arguments.name}" deleted'
        )
        print("\nCheckpoint and associated snapshot files have been removed")
    else:
        handle_api_error(result)
