"""
CLI command handlers for development mode operations.

This module provides exec_* functions that implement dev mode commands:
- Session management (start, stop, list, state)
- Action and playbook execution
- Reset operations
- Checkpoint management
- Cleanup utilities
"""

import logging
from pathlib import Path

from adare.backend.basics import determine_projectdirectory
from adare.exceptions import NoProjectFoundError
from adare.helperfunctions.path_resolution import resolve_experiment_path
from adare.api import AdareAPI
from adare.core.dto.devmode import (
    DevSessionStartRequest,
    DevSessionStopRequest,
    DevActionExecuteRequest,
    DevPlaybookExecuteRequest,
    DevResetRequest,
    DevCheckpointCreateRequest,
    DevCheckpointRestoreRequest,
    DevCheckpointListRequest,
    DevSessionListRequest,
    DevSessionStateRequest,
    DevSessionCleanupRequest,
)
from adare.console import print_success_message, print_error_message

log = logging.getLogger(__name__)


def _handle_api_error(result) -> None:
    """
    Handle an API error result by printing formatted error message and exiting.

    Args:
        result: Result object with error information
    """
    error = result.error
    print_error_message(
        title=f'{error.code}: {error.message}',
        next_steps=error.solutions
    )
    exit(1)


def _get_project_path(arguments):
    """Get project path from arguments or current directory."""
    project = getattr(arguments, 'project', None)
    project_directory = determine_projectdirectory(project)
    if not project_directory:
        raise NoProjectFoundError(log, message='no project directory found')
    return project_directory


# =============================================================================
# Session Management Commands
# =============================================================================

def exec_dev_start(arguments):
    """Start a new dev mode session."""
    project_directory = _get_project_path(arguments)
    experiment_name = resolve_experiment_path(arguments.experiment, project_directory)

    api = AdareAPI()
    result = api.devmode.start_session(DevSessionStartRequest(
        project_path=project_directory,
        experiment_name=experiment_name,
        environment_name=arguments.environment
    ))

    if result.success:
        print_success_message(
            title=f'Dev session started: {result.data.session_id}',
            next_steps=result.data.next_steps,
            tip=result.data.tip
        )
        print(f"\nCLAUDE: Session ID: {result.data.session_id}")
        print(f"CLAUDE: Experiment: {result.data.experiment_name}")
        print(f"CLAUDE: Environment: {result.data.environment_name}")
        print(f"CLAUDE: VM Running: {result.data.vm_running}")
    else:
        _handle_api_error(result)


def exec_dev_stop(arguments):
    """Stop a dev mode session."""
    api = AdareAPI()
    result = api.devmode.stop_session(DevSessionStopRequest(
        session_id=arguments.session_id
    ))

    if result.success:
        print_success_message(
            title=f'Dev session stopped: {arguments.session_id}'
        )
    else:
        _handle_api_error(result)


def exec_dev_list(arguments):
    """List active dev mode sessions."""
    project_directory = None
    if hasattr(arguments, 'project') and arguments.project:
        project_directory = determine_projectdirectory(arguments.project)

    api = AdareAPI()
    result = api.devmode.list_sessions(DevSessionListRequest(
        project_path=project_directory
    ))

    if result.success:
        if not result.data:
            print("CLAUDE: No active dev sessions found")
            print("\nStart a new session with: adare dev start <experiment> -e <environment>")
        else:
            print(f"CLAUDE: Found {len(result.data)} active dev session(s):\n")
            for session in result.data:
                print(f"  Session ID: {session.session_id}")
                print(f"  Experiment: {session.experiment_name}")
                print(f"  Environment: {session.environment_name}")
                print(f"  VM Running: {session.vm_running}")
                print(f"  Actions Executed: {session.actions_executed}")
                print(f"  Created: {session.created_at}")
                print(f"  Project: {session.project_path}")
                print()
    else:
        _handle_api_error(result)


def exec_dev_state(arguments):
    """Show session state."""
    api = AdareAPI()
    result = api.devmode.get_state(DevSessionStateRequest(
        session_id=arguments.session_id
    ))

    if result.success:
        state = result.data
        print(f"CLAUDE: Dev Session State: {state.session_id}\n")
        print(f"  Experiment: {state.experiment_name}")
        print(f"  Environment: {state.environment_name}")
        print(f"  VM Running: {state.vm_running}")
        print(f"  Actions Executed: {state.actions_executed}")
        print(f"  Created: {state.created_at}")
        print(f"\n  Current Variables ({len(state.current_variables)}):")
        for key, value in state.current_variables.items():
            print(f"    {key}: {value}")
        print(f"\n  Available Snapshots ({len(state.available_snapshots)}):")
        for snapshot in state.available_snapshots:
            # Extract checkpoint name from snapshot_name (devmode_{session_id}_{name})
            checkpoint_name = snapshot.snapshot_name.split('_')[-1]
            print(f"    {checkpoint_name}: {snapshot.description} ({snapshot.created_at})")
    else:
        _handle_api_error(result)


def exec_dev_cleanup(arguments):
    """Cleanup stale sessions."""
    project_directory = None
    if hasattr(arguments, 'project') and arguments.project:
        project_directory = determine_projectdirectory(arguments.project)

    api = AdareAPI()
    result = api.devmode.cleanup_stale_sessions(DevSessionCleanupRequest(
        project_path=project_directory
    ))

    if result.success:
        if result.data.sessions_removed == 0:
            print("CLAUDE: No stale sessions found")
        else:
            print_success_message(
                title=f'Cleaned up {result.data.sessions_removed} stale session(s)'
            )
            for session_id in result.data.removed_session_ids:
                print(f"  Removed: {session_id}")
    else:
        _handle_api_error(result)


# =============================================================================
# Action and Playbook Execution Commands
# =============================================================================

def exec_dev_action(arguments):
    """Execute a single action."""
    # Determine source and content
    if arguments.action_file:
        source = 'file'
        content = arguments.action_file
    elif arguments.action_yaml:
        source = 'yaml'
        content = arguments.action_yaml
    elif arguments.stdin:
        source = 'stdin'
        content = ''
    else:
        print_error_message(
            title='No action source specified',
            next_steps=[
                'Specify action with: -f <file>, -y <yaml>, or --stdin'
            ]
        )
        exit(1)

    api = AdareAPI()
    result = api.devmode.execute_action(DevActionExecuteRequest(
        session_id=arguments.session_id,
        action_source=source,
        action_content=content
    ))

    if result.success:
        action_result = result.data
        print_success_message(
            title=f'Action executed successfully'
        )
        print(f"\nCLAUDE: Success: {action_result.success}")
        print(f"CLAUDE: Message: {action_result.message}")
        print(f"CLAUDE: Execution Time: {action_result.execution_time:.2f}s")
        if action_result.coordinates:
            print(f"CLAUDE: Coordinates: {action_result.coordinates}")
        if action_result.data:
            print(f"CLAUDE: Data: {action_result.data}")
    else:
        _handle_api_error(result)


def exec_dev_playbook(arguments):
    """Execute a playbook."""
    # Determine source and content
    if arguments.playbook_file:
        source = 'file'
        content = arguments.playbook_file
    elif arguments.url:
        source = 'url'
        content = arguments.url
    elif arguments.stdin:
        source = 'stdin'
        content = ''
    else:
        print_error_message(
            title='No playbook source specified',
            next_steps=[
                'Specify playbook with: -f <file>, -u <url>, or --stdin'
            ]
        )
        exit(1)

    api = AdareAPI()
    result = api.devmode.execute_playbook(DevPlaybookExecuteRequest(
        session_id=arguments.session_id,
        playbook_source=source,
        playbook_content=content
    ))

    if result.success:
        playbook_result = result.data
        if playbook_result.success:
            print_success_message(
                title=f'Playbook executed successfully'
            )
        else:
            print_error_message(
                title='Playbook execution failed',
                next_steps=['Check error message below']
            )

        print(f"\nCLAUDE: Total Actions: {playbook_result.total_actions}")
        print(f"CLAUDE: Successful: {playbook_result.successful_actions}")
        print(f"CLAUDE: Failed: {playbook_result.failed_actions}")
        print(f"CLAUDE: Execution Time: {playbook_result.execution_time:.2f}s")

        if playbook_result.error_message:
            print(f"CLAUDE: Error: {playbook_result.error_message}")

        if playbook_result.test_stats:
            print(f"\nCLAUDE: Test Statistics:")
            for key, value in playbook_result.test_stats.items():
                print(f"  {key}: {value}")

        # Show individual action results if any failed
        if playbook_result.failed_actions > 0:
            print(f"\nCLAUDE: Failed Actions:")
            for i, action_result in enumerate(playbook_result.action_results):
                if not action_result.success:
                    print(f"  Action {i+1}: {action_result.message}")
    else:
        _handle_api_error(result)


# =============================================================================
# Reset Commands
# =============================================================================

def exec_dev_reset_soft(arguments):
    """Soft reset (variables only)."""
    api = AdareAPI()
    result = api.devmode.reset_soft(DevResetRequest(
        session_id=arguments.session_id,
        reset_type='soft'
    ))

    if result.success:
        reset_result = result.data
        print_success_message(
            title='Soft reset completed'
        )
        print(f"\nCLAUDE: {reset_result.message}")
        print(f"CLAUDE: Execution Time: {reset_result.execution_time:.2f}s")
    else:
        _handle_api_error(result)


def exec_dev_reset_hard(arguments):
    """Hard reset (full VM restore)."""
    api = AdareAPI()
    result = api.devmode.reset_hard(DevResetRequest(
        session_id=arguments.session_id,
        reset_type='hard'
    ))

    if result.success:
        reset_result = result.data
        print_success_message(
            title='Hard reset completed'
        )
        print(f"\nCLAUDE: {reset_result.message}")
        print(f"CLAUDE: Execution Time: {reset_result.execution_time:.2f}s")
        print("\nCLAUDE: VM has been restored to initial snapshot")
        print("CLAUDE: All variables have been reset")
    else:
        _handle_api_error(result)


# =============================================================================
# Checkpoint Commands
# =============================================================================

def exec_dev_checkpoint_create(arguments):
    """Create a checkpoint."""
    api = AdareAPI()
    result = api.devmode.create_checkpoint(DevCheckpointCreateRequest(
        session_id=arguments.session_id,
        name=arguments.name,
        description=arguments.description
    ))

    if result.success:
        print_success_message(
            title=f'Checkpoint "{arguments.name}" created'
        )
        if arguments.description:
            print(f"\nCLAUDE: Description: {arguments.description}")
        print("\nCLAUDE: Checkpoint is a live snapshot - VM continued running during creation")
    else:
        _handle_api_error(result)


def exec_dev_checkpoint_restore(arguments):
    """Restore a checkpoint."""
    api = AdareAPI()
    result = api.devmode.restore_checkpoint(DevCheckpointRestoreRequest(
        session_id=arguments.session_id,
        name=arguments.name
    ))

    if result.success:
        print_success_message(
            title=f'Checkpoint "{arguments.name}" restored'
        )
        print("\nCLAUDE: VM has been restored to checkpoint state")
        print("CLAUDE: Variables have been restored")
        print("CLAUDE: This operation required VM restart")
    else:
        _handle_api_error(result)


def exec_dev_checkpoint_list(arguments):
    """List checkpoints."""
    api = AdareAPI()
    result = api.devmode.list_checkpoints(DevCheckpointListRequest(
        session_id=arguments.session_id
    ))

    if result.success:
        if not result.data:
            print(f"CLAUDE: No checkpoints found for session {arguments.session_id}")
            print(f"\nCreate a checkpoint with: adare dev checkpoint-create {arguments.session_id} <name>")
        else:
            print(f"CLAUDE: Found {len(result.data)} checkpoint(s):\n")
            for checkpoint in result.data:
                print(f"  Name: {checkpoint.name}")
                print(f"  Description: {checkpoint.description}")
                print(f"  Created: {checkpoint.created_at}")
                print(f"  Variables: {checkpoint.variable_count}")
                print()
    else:
        _handle_api_error(result)
