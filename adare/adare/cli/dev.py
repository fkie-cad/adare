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
import threading
import time
from pathlib import Path

from adare.api import AdareAPI
from adare.backend.basics import determine_projectdirectory
from adare.console import print_error_message, print_success_message
from adare.core.dto.devmode import (
    DevActionExecuteRequest,
    DevCheckpointCreateRequest,
    DevCheckpointListRequest,
    DevCheckpointRestoreRequest,
    DevCVRestartRequest,
    DevCVStopRequest,
    DevPlaybookExecuteRequest,
    DevResetRequest,
    DevSessionCleanupRequest,
    DevSessionListRequest,
    DevSessionRecordRequest,
    DevSessionStartRequest,
    DevSessionStateRequest,
    DevSessionStopRequest,
)
from adare.exceptions import NoProjectFoundError

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


def _resolve_session_id(session_id: str | None, project_directory: Path | None = None) -> str:
    """
    Resolve session ID: use provided ID or auto-detect if only one session running.

    Args:
        session_id: Explicitly provided session ID (None if not provided)
        project_directory: Optional project filter for session lookup

    Returns:
        Valid session ID (either provided or auto-detected)

    Exits:
        With error message if session_id is None and:
        - No sessions running
        - Multiple sessions running (shows list)
    """
    # Fast path: session_id explicitly provided
    if session_id:
        return session_id

    # Slow path: auto-detect session
    from adare.database.api.devmode import DevModeApi

    api = DevModeApi()
    running_sessions = api.list_running_sessions(project_directory)

    if len(running_sessions) == 0:
        print_error_message(
            title='No active dev sessions found',
            next_steps=[
                'Start a new session with: adare dev start <experiment> -e <environment>',
                'Check all sessions with: adare dev list'
            ]
        )
        exit(1)
    elif len(running_sessions) == 1:
        # Auto-detect: exactly one session
        detected_id = running_sessions[0].session_id
        log.info(f"Auto-detected session: {detected_id}")
        return detected_id
    else:
        # Multiple sessions: user must specify
        print_error_message(
            title=f'Multiple dev sessions running ({len(running_sessions)})',
            next_steps=[
                'Specify session with: adare dev <command> -s <session_id>',
                'List all sessions with: adare dev list'
            ]
        )
        print("\nActive sessions:")
        for session in running_sessions:
            print(f"  - {session.session_id} ({session.experiment_name} / {session.environment_name})")
        exit(1)


def _start_event_listeners(console_ulid: str) -> None:
    """Start event coordinator and CLI listener for flow console integration."""
    from adare.backend.events.coordinator import start_stage_coordinator
    from adare.backend.events.listener import event_listener_cli

    # Start coordinator
    start_stage_coordinator()
    log.debug("Stage event coordinator started")

    # Start CLI listener in background thread
    cli_ready_event = threading.Event()

    def cli_wrapper():
        cli_ready_event.set()
        event_listener_cli(console_ulid)

    cli_thread = threading.Thread(target=cli_wrapper, daemon=True)
    cli_thread.start()

    # Wait for listener ready
    if not cli_ready_event.wait(timeout=5.0):
        raise RuntimeError("CLI event listener failed to start")

    log.debug("Event listeners started")


def _stop_event_listeners() -> None:
    """Stop event coordinator."""
    from adare.backend.events.coordinator import stop_stage_coordinator
    stop_stage_coordinator()
    log.debug("Event listeners stopped")




# =============================================================================
# Session Management Commands
# =============================================================================

def exec_dev_start(arguments):
    """Start dev session with flow console UI."""
    from pathlib import Path

    import ulid

    from adare.backend.experiment.print import ExperimentFlowConsole, flowconsolemanager

    # Setup
    project_directory = _get_project_path(arguments)
    log_file = Path(arguments.log) if hasattr(arguments, 'log') and arguments.log else None

    # Process shared directories
    # Format: host_path:vm_path
    shared_directories = {}
    raw_shared_dirs = getattr(arguments, 'shared_dir', None)

    if raw_shared_dirs:
        for idx, dir_spec in enumerate(raw_shared_dirs):
            try:
                host_path_str, vm_path_str = dir_spec.split(':', 1)

                # Setup structure expected by ExperimentConfig:
                # Dict[str, Dict[str, Path]] = {name: {'host': Path, 'vm': Path}}
                # Auto-generate name since user only provides paths
                share_name = f"dev_shared_{idx+1}"


                host_path = Path(host_path_str).resolve()
                if not host_path.exists():
                     # Auto-create if it doesn't exist, as this is a dev convenience feature
                     host_path.mkdir(parents=True, exist_ok=True)
                     log.info(f"Created shared directory on host: {host_path}")

                shared_directories[share_name] = {
                    'host': host_path,
                    'vm': Path(vm_path_str)
                }
                log.debug(f"Parsed shared directory: {host_path_str} -> {vm_path_str} ({share_name})")
            except ValueError:
                print_error_message(
                    title=f"Invalid shared directory format: {dir_spec}",
                    next_steps=["Use format: HOST_PATH:VM_PATH (e.g., /tmp/data:/mnt/data)"]
                )
                exit(1)

    # Create flow console
    user_interrupt_event = threading.Event()
    console_ulid = str(ulid.ULID())
    flow_console = ExperimentFlowConsole(disable=False, external_stop_event=user_interrupt_event)
    flowconsolemanager.add_handler(console_ulid, flow_console)
    flow_console.start()

    # Start event system
    _start_event_listeners(console_ulid)

    # Setup logging

    try:
        # Start session
        api = AdareAPI()
        result = api.devmode.start_session(DevSessionStartRequest(
            project_path=project_directory,
            environment_name=arguments.environment,
            gui_mode=getattr(arguments, 'gui_mode', None),
            vm_memory=getattr(arguments, 'vm_memory', None),
            vm_cpus=getattr(arguments, 'vm_cpus', None),
            debug_screenshots=getattr(arguments, 'debug_screenshots', False),
            console_ulid=console_ulid,
            shared_directories=shared_directories if shared_directories else None
        ))

        if result.success:
            flow_console.log_success('DEV_START_SUCCESS', f'Dev session started: {result.data.session_id}')
            flow_console.stop()
            print_success_message(
                title=f'Dev session started: {result.data.session_id}',
                next_steps=result.data.next_steps,
                tip=result.data.tip
            )

            if shared_directories:
                print("\nShared Directories:")
                for name, paths in shared_directories.items():
                    print(f"  - {paths['host']} -> {paths['vm']} ({name})")
        else:
            flow_console.stop()
            _handle_api_error(result)

    except KeyboardInterrupt:
        user_interrupt_event.set()
        flow_console.log_interrupted('DEV_START_INTERRUPTED', 'Interrupted by user')
        flow_console.stop()
        print("\n\nDev session start interrupted")
        exit(1)
    except Exception as e:
        log.error(f"Dev session start failed: {e}", exc_info=True)
        flow_console.log_error('DEV_START_ERROR', f'Error: {str(e)}')
        flow_console.stop()
        print_error_message(title='Failed to start dev session', next_steps=['Check logs'])
        exit(1)
    finally:
        flowconsolemanager.remove_handler(console_ulid)
        _stop_event_listeners()


def exec_dev_resume(arguments):
    """Resume a stopped dev mode session."""
    import ulid

    from adare.backend.experiment.print import ExperimentFlowConsole, flowconsolemanager

    # Setup
    project_directory = _get_project_path(arguments)
    log_file = Path(arguments.log) if hasattr(arguments, 'log') and arguments.log else None

    # Create flow console
    user_interrupt_event = threading.Event()
    console_ulid = str(ulid.ULID())
    flow_console = ExperimentFlowConsole(disable=False, external_stop_event=user_interrupt_event)
    flowconsolemanager.add_handler(console_ulid, flow_console)
    flow_console.start()

    # Start event system
    _start_event_listeners(console_ulid)

    # Setup logging

    try:
        # Resume session
        api = AdareAPI()

        # If session_id provided, resume that specific session
        if hasattr(arguments, 'session_id') and arguments.session_id:
            result = api.devmode.resume_session(arguments.session_id, console_ulid=console_ulid)
        else:
            # No session_id - resume most recent stopped session
            result = api.devmode.resume_most_recent(project_directory, console_ulid=console_ulid)

        if result.success:
            flow_console.log_success('DEV_RESUME_SUCCESS', f'Dev session resumed: {result.data.session_id}')
            flow_console.stop()
            print_success_message(
                title=f'Dev session resumed: {result.data.session_id}',
                next_steps=result.data.next_steps,
                tip=result.data.tip
            )
            print(f"\n  Variables preserved: {len(result.data.current_variables)}")
            print(f"  Checkpoints available: {len(result.data.available_snapshots)}")
            print(f"  Experiment: {result.data.experiment_name}")
            print(f"  Environment: {result.data.environment_name}")
            print(f"  VM Running: {result.data.vm_running}")
            print(f"  VM Running: {result.data.vm_running}")
        else:
            flow_console.stop()
            _handle_api_error(result)

    except KeyboardInterrupt:
        user_interrupt_event.set()
        flow_console.log_interrupted('DEV_RESUME_INTERRUPTED', 'Interrupted by user')
        flow_console.stop()
        print("\n\nDev session resume interrupted")
        exit(1)
    except Exception as e:
        log.error(f"Dev session resume failed: {e}", exc_info=True)
        flow_console.log_error('DEV_RESUME_ERROR', f'Error: {str(e)}')
        flow_console.stop()
        print_error_message(title='Failed to resume dev session', next_steps=['Check logs'])
        exit(1)
    finally:
        flowconsolemanager.remove_handler(console_ulid)
        _stop_event_listeners()


def exec_dev_stop(arguments):
    """Stop a dev mode session."""
    # AUTO-DETECT SESSION ID
    session_id = _resolve_session_id(arguments.session_id)

    api = AdareAPI()

    # Extract remove_resources flag (default to False)
    remove_resources = getattr(arguments, 'remove_resources', False)

    result = api.devmode.stop_session(DevSessionStopRequest(
        session_id=session_id,
        remove_resources=remove_resources
    ))

    if result.success:
        if remove_resources:
            print_success_message(
                title=f'Dev session removed: {session_id}',
                next_steps=[
                    'All resources deleted (VM, snapshots, database)',
                    'Session cannot be restarted'
                ]
            )
        else:
            print_success_message(
                title=f'Dev session stopped: {session_id}',
                next_steps=[
                    'VM shut down, resources preserved',
                    f'Resume with: adare dev resume {session_id}',
                    'Or resume most recent: adare dev resume'
                ]
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
            print("No dev sessions found")
            print("\nStart a new session with: adare dev start <experiment> -e <environment>")
        else:
            # Use Rich table panel for display
            import pandas as pd
            from rich.layout import Layout

            from adare.frontend.terminal.console import DefaultConsole
            from adare.frontend.terminal.dev_session_list import DevSessionTablePanel

            # Convert to DataFrame
            data = []
            for session in result.data:
                data.append({
                    'session_id': session.session_id,
                    'experiment_name': session.experiment_name,
                    'environment_name': session.environment_name,
                    'vm_running': session.vm_running,
                    'actions_executed': session.actions_executed,
                    'created_at': session.created_at,
                    'status': session.status,
                })

            df = pd.DataFrame(data)

            # Print table
            console = DefaultConsole()
            layout = Layout(name="root")
            panel = DevSessionTablePanel(df)
            layout.update(panel)
            console.print(layout)

            # Show action hint as footer if there are stopped sessions
            has_stopped = any(s.status == 'stopped' for s in result.data)
            if has_stopped:
                print("\nResume a session with: adare dev resume <session_id>")
    else:
        _handle_api_error(result)


def exec_dev_state(arguments):
    """Show session state."""
    # AUTO-DETECT SESSION ID
    session_id = _resolve_session_id(arguments.session_id)

    api = AdareAPI()
    result = api.devmode.get_state(DevSessionStateRequest(
        session_id=session_id
    ))

    if result.success:
        state = result.data
        print(f"Dev Session State: {state.session_id}\n")
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
            print("No stale sessions found")
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
    # AUTO-DETECT SESSION ID
    session_id = _resolve_session_id(arguments.session_id)

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
        session_id=session_id,
        action_source=source,
        action_content=content
    ))

    if result.success:
        action_result = result.data
        print_success_message(
            title='Action executed successfully'
        )
        print(f"\nSuccess: {action_result.success}")
        print(f"Message: {action_result.message}")
        print(f"Execution Time: {action_result.execution_time:.2f}s")
        if action_result.coordinates:
            print(f"Coordinates: {action_result.coordinates}")
        if action_result.data:
            print(f"Data: {action_result.data}")
    else:
        _handle_api_error(result)


def parse_indices_with_bounds(indices_str: str, total_actions: int) -> list[int]:
    """
    Parse indices string into a list of integers with S/E support.

    Supports formats:
    - "1-3", "1,3,4", "1-3,4-9" (numeric indices)
    - "S-5", "7,23-E", "S-E" (S=start=1, E=end=total_actions)
    - Case-insensitive: "s-5", "e" work the same as "S-5", "E"

    Args:
        indices_str: Index specification string (cannot be None/empty)
        total_actions: Total number of actions in the playbook

    Returns:
        Sorted list of unique 1-based indices

    Raises:
        ValueError: If format is invalid or indices are out of bounds
    """
    # Normalize case
    indices_str = indices_str.upper()

    # Replace S with 1 and E with total_actions
    indices_str = indices_str.replace('S', '1')
    indices_str = indices_str.replace('E', str(total_actions))

    # Parse ranges and single values
    indices = set()
    parts = indices_str.split(',')
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            range_parts = part.split('-')
            if len(range_parts) != 2:
                raise ValueError(f"Invalid range format: '{part}'")
            start, end = map(int, range_parts)
            if start > end:
                raise ValueError(f"Invalid range '{part}': start ({start}) > end ({end})")
            indices.update(range(start, end + 1))
        else:
            indices.add(int(part))

    # Validate all indices are in bounds
    for idx in indices:
        if idx < 1 or idx > total_actions:
            raise ValueError(
                f"Index {idx} out of bounds (playbook has {total_actions} actions)"
            )

    return sorted(list(indices))


def _parse_indices(indices_str: str | None, total_actions: int) -> list[int] | None:
    """
    CLI wrapper for parse_indices_with_bounds.
    Returns None if indices_str is None, exits on error.
    """
    if not indices_str:
        return None

    try:
        return parse_indices_with_bounds(indices_str, total_actions)
    except ValueError as e:
        print_error_message(
            title="Invalid indices format",
            next_steps=[
                str(e),
                "Use format like '1-3', 'S-5', '7,23-E', or 'S-E'"
            ]
        )
        exit(1)


def exec_dev_playbook(arguments):
    """Execute a playbook with flow console UI."""
    import ulid

    from adare.backend.experiment.print import ExperimentFlowConsole, flowconsolemanager

    # AUTO-DETECT SESSION ID
    session_id = _resolve_session_id(arguments.session_id)

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

    # Keep indices as string - will be parsed in service layer after playbook is loaded
    indices = getattr(arguments, 'indices', None)

    # Create flow console
    user_interrupt_event = threading.Event()
    console_ulid = str(ulid.ULID())
    # Use indent_offset=1 to fix indentation issue:
    # "Dangling" stages (Level 1) will be printed as Level 0
    # "Sub-stages" (Level 2) will be printed as Level 1
    flow_console = ExperimentFlowConsole(disable=False, external_stop_event=user_interrupt_event, indent_offset=1)
    flowconsolemanager.add_handler(console_ulid, flow_console)
    flow_console.start()

    # Start event system
    _start_event_listeners(console_ulid)

    try:
        # Execute playbook with console_ulid
        api = AdareAPI()
        result = api.devmode.execute_playbook(DevPlaybookExecuteRequest(
            session_id=session_id,
            playbook_source=source,
            playbook_content=content,
            console_ulid=console_ulid,
            restore_initial=arguments.restore,
            indices=indices
        ))

        # Log completion and summary to flow console BEFORE stopping
        if result.success:
            playbook_result = result.data

            # Use flow console's formatted summary display
            flow_console.log_experiment_summary(
                ulid=console_ulid,
                success=playbook_result.success,
                total_actions=playbook_result.total_actions,
                successful_actions=playbook_result.successful_actions,
                failed_actions=playbook_result.failed_actions,
                total_tests=playbook_result.test_stats.get('total_tests', 0) if playbook_result.test_stats else 0,
                successful_tests=playbook_result.test_stats.get('successful_tests', 0) if playbook_result.test_stats else 0,
                failed_tests=playbook_result.test_stats.get('failed_tests', 0) if playbook_result.test_stats else 0,
                duration=playbook_result.execution_time,
                was_interrupted=False
            )

            # Give flow console time to render summary
            time.sleep(0.5)
        else:
            flow_console.log_error('PLAYBOOK_FAILED', 'Playbook execution failed')
            time.sleep(0.2)

        # Stop flow console AFTER summary is logged
        flow_console.stop()

        # Show error message if failed
        if result.success and not result.data.success:
            print_error_message(
                title='Playbook execution completed with errors',
                next_steps=['Check the summary above for details']
            )
        elif not result.success:
            _handle_api_error(result)

    except KeyboardInterrupt:
        user_interrupt_event.set()
        flow_console.log_interrupted('PLAYBOOK_INTERRUPTED', 'Interrupted by user')
        flow_console.stop()
        print("\n\nPlaybook execution interrupted")
        exit(1)
    finally:
        flowconsolemanager.remove_handler(console_ulid)
        _stop_event_listeners()


# =============================================================================
# Reset Commands
# =============================================================================

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
        _handle_api_error(result)


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
        _handle_api_error(result)


# =============================================================================
# Checkpoint Commands
# =============================================================================

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
        _handle_api_error(result)


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
        _handle_api_error(result)


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
        _handle_api_error(result)


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
        _handle_api_error(result)


def exec_dev_record(arguments):
    """
    Record user interactions in a dev session.

    Args:
        arguments: Parsed arguments
    """
    project_directory = _get_project_path(arguments)
    session_id = _resolve_session_id(getattr(arguments, 'session_id', None), project_directory)
    output_file = Path(getattr(arguments, 'output', 'playbook.yml')).resolve()

    log.info(f"Recording session {session_id} to {output_file}")
    print(f"Starting recording for session {session_id}...")
    print(f"Output will be saved to: {output_file}")
    print("Press Ctrl+C to stop recording.")

    api = AdareAPI()

    try:
        # Start recording
        result = api.devmode.record_session(DevSessionRecordRequest(
            session_id=session_id,
            output_file=output_file
        ))

        if not result.success:
            _handle_api_error(result)

        # Loop until interrupted
        try:
            while True:
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\nStopping recording...")

            # Stop recording
            stop_result = api.devmode.stop_recording_session(session_id)
            if stop_result.success:
                print_success_message(
                    title="Recording stopped",
                    next_steps=[f"View playbook: {output_file}"],
                    tip=f"Run with: adare dev playbook {session_id} -f {output_file}"
                )
            else:
                _handle_api_error(stop_result)

    except Exception as e:
        print_error_message(title="Recording failed", next_steps=[str(e)])
        exit(1)


def exec_dev_update_testfunctions(arguments):
    """
    Update test functions in the VM.

    Args:
        arguments: Parsed arguments
    """
    project_directory = _get_project_path(arguments)
    session_id = _resolve_session_id(getattr(arguments, 'session_id', None), project_directory)

    api = AdareAPI()

    from adare.core.dto.devmode import DevUpdateTestfunctionsRequest

    result = api.devmode.update_testfunctions(DevUpdateTestfunctionsRequest(
        session_id=session_id
    ))

    if result.success:
        print_success_message(
            title="Test functions updated successfully",
            next_steps=[
                f"Execution time: {result.data.execution_time:.2f}s",
                "You can now run tests with the updated code"
            ]
        )
    else:
        _handle_api_error(result)

def exec_dev_cv_start(arguments):
    """Start/Response CV server with new options."""
    # AUTO-DETECT SESSION ID
    session_id = _resolve_session_id(arguments.session_id)

    # Parse debug flag
    debug = None
    if arguments.debug:
        debug = True
    elif arguments.no_debug:
        debug = False

    # debug_output_dir
    debug_output_dir = None
    if arguments.debug_output:
        debug_output_dir = Path(arguments.debug_output)

    api = AdareAPI()
    result = api.devmode.restart_cv_server(DevCVRestartRequest(
        session_id=session_id,
        debug=debug,
        debug_output_dir=debug_output_dir
    ))

    if result.success:
        print_success_message(
            title=f'CV Server started/restarted for session {session_id}',
            next_steps=[
                f'Debug logging: {"Enabled" if debug else "Disabled" if debug is False else "Unchanged"}',
                f'Debug output directory: {debug_output_dir if debug_output_dir else "Unchanged/Default"}'
            ]
        )
    else:
        _handle_api_error(result)


def exec_dev_cv_stop(arguments):
    """Stop CV server."""
    # AUTO-DETECT SESSION ID
    session_id = _resolve_session_id(arguments.session_id)

    api = AdareAPI()
    result = api.devmode.stop_cv_server(DevCVStopRequest(
        session_id=session_id
    ))

    if result.success:
        print_success_message(
            title=f'CV Server stopped for session {session_id}'
        )
    else:
        _handle_api_error(result)


def exec_dev_playbook_batch(arguments):
    """Execute multiple playbooks with checkpoint restoration."""
    import ulid

    from adare.console.flow import ExperimentFlowConsole
    from adare.core.dto.devmode import DevPlaybookBatchExecuteRequest

    # AUTO-DETECT SESSION ID
    session_id = _resolve_session_id(arguments.session_id)

    # Create flow console for progress tracking
    console_ulid = str(ulid.ULID())
    flow_console = ExperimentFlowConsole(
        run_ulid=console_ulid,
        total_action_count=0,  # Will be updated during execution
        show_substages=True
    )

    # Execute batch
    api = AdareAPI()
    result = api.devmode.execute_playbook_batch(DevPlaybookBatchExecuteRequest(
        session_id=session_id,
        playbook_patterns=list(arguments.playbook_patterns),
        checkpoint_name=arguments.checkpoint_name,
        timeout=arguments.timeout,
        console_ulid=console_ulid
    ))

    # Print summary
    if result.success:
        result.data.print_summary()
    else:
        _handle_api_error(result)
