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
from typing import Optional

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


def _resolve_session_id(session_id: Optional[str], project_directory: Optional[Path] = None) -> str:
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
    from adare.backend.events.listener import event_listener_cli
    from adare.backend.events.coordinator import start_stage_coordinator

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


def _setup_log_file_handler(log_file: Path) -> Optional[logging.Handler]:
    """Setup file handler for logging to a file."""
    try:
        # Create parent directory if needed
        log_file.parent.mkdir(parents=True, exist_ok=True)

        # Create file handler
        file_handler = logging.FileHandler(log_file, mode='w')
        file_handler.setLevel(logging.DEBUG)

        # Use detailed formatter for file logs
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(formatter)

        # Add to root logger
        logging.getLogger().addHandler(file_handler)
        log.info(f"Logging to file: {log_file}")

        return file_handler
    except OSError as e:
        log.error(f"Failed to setup log file handler: {e}")
        return None


def _cleanup_log_file_handler(handler: logging.Handler) -> None:
    """Remove and close log file handler."""
    if handler:
        logging.getLogger().removeHandler(handler)
        handler.close()


# =============================================================================
# Session Management Commands
# =============================================================================

def exec_dev_start(arguments):
    """Start dev session with flow console UI."""
    import ulid
    from adare.backend.experiment.print import flowconsolemanager, ExperimentFlowConsole

    # Setup
    project_directory = _get_project_path(arguments)
    experiment_name = resolve_experiment_path(arguments.experiment, project_directory)
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
    log_handler = _setup_log_file_handler(log_file) if log_file else None

    try:
        # Start session
        api = AdareAPI()
        result = api.devmode.start_session(DevSessionStartRequest(
            project_path=project_directory,
            experiment_name=experiment_name,
            environment_name=arguments.environment,
            gui_mode=getattr(arguments, 'gui_mode', None),
            vm_memory=getattr(arguments, 'vm_memory', None),
            vm_cpus=getattr(arguments, 'vm_cpus', None),
            debug_screenshots=getattr(arguments, 'debug_screenshots', False),
            log_file=log_file,
            console_ulid=console_ulid
        ))

        if result.success:
            flow_console.log_success('DEV_START_SUCCESS', f'Dev session started: {result.data.session_id}')
            flow_console.stop()
            print_success_message(
                title=f'Dev session started: {result.data.session_id}',
                next_steps=result.data.next_steps,
                tip=result.data.tip
            )
            if log_file:
                print(f"\nLogs saved to: {log_file}")
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
        flow_console.log_error('DEV_START_ERROR', f'Error: {str(e)}')
        flow_console.stop()
        print_error_message(title='Failed to start dev session', next_steps=['Check logs'])
        exit(1)
    finally:
        flowconsolemanager.remove_handler(console_ulid)
        _stop_event_listeners()
        if log_handler:
            _cleanup_log_file_handler(log_handler)


def exec_dev_resume(arguments):
    """Resume a stopped dev mode session."""
    import ulid
    from adare.backend.experiment.print import flowconsolemanager, ExperimentFlowConsole

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
    log_handler = _setup_log_file_handler(log_file) if log_file else None

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
            if log_file:
                print(f"\nLogs saved to: {log_file}")
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
        flow_console.log_error('DEV_RESUME_ERROR', f'Error: {str(e)}')
        flow_console.stop()
        print_error_message(title='Failed to resume dev session', next_steps=['Check logs'])
        exit(1)
    finally:
        flowconsolemanager.remove_handler(console_ulid)
        _stop_event_listeners()
        if log_handler:
            _cleanup_log_file_handler(log_handler)


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
            print("CLAUDE: No dev sessions found")
            print("\nStart a new session with: adare dev start <experiment> -e <environment>")
        else:
            print(f"CLAUDE: Found {len(result.data)} dev session(s):\n")
            for session in result.data:
                # Status indicator
                if session.status == 'running':
                    status_icon = "✓"
                    status_text = "running"
                elif session.status == 'stopped':
                    status_icon = "⏸"
                    status_text = "stopped"
                elif session.status == 'crashed':
                    status_icon = "✗"
                    status_text = "crashed"
                else:
                    status_icon = "?"
                    status_text = session.status

                print(f"  {status_icon} Session ID: {session.session_id} ({status_text})")
                print(f"    Experiment: {session.experiment_name}")
                print(f"    Environment: {session.environment_name}")
                print(f"    VM Running: {session.vm_running}")
                print(f"    Actions Executed: {session.actions_executed}")
                print(f"    Created: {session.created_at}")
                print(f"    Project: {session.project_path}")

                # Show action hint for stopped sessions
                if session.status == 'stopped':
                    print(f"    → Resume with: adare dev resume {session.session_id}")

                print()
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
    """Execute a playbook with flow console UI."""
    import ulid
    from adare.backend.experiment.print import flowconsolemanager, ExperimentFlowConsole

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

    # Create flow console
    user_interrupt_event = threading.Event()
    console_ulid = str(ulid.ULID())
    flow_console = ExperimentFlowConsole(disable=False, external_stop_event=user_interrupt_event)
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
            restore_initial=arguments.restore
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
        print(f"\nCLAUDE: {reset_result.message}")
        print(f"CLAUDE: Execution Time: {reset_result.execution_time:.2f}s")
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
        if arguments.description:
            print(f"\nCLAUDE: Description: {arguments.description}")
        print("\nCLAUDE: Checkpoint is a live snapshot - VM continued running during creation")
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
            print(f"CLAUDE: No checkpoints found for session {session_id}")
            print(f"\nCreate a checkpoint with: adare dev checkpoint-create -s {session_id} <name>")
        else:
            print(f"CLAUDE: Found {len(result.data)} checkpoint(s):\n")
            for checkpoint in result.data:
                print(f"  Name: {checkpoint.name}")
                if checkpoint.description:
                    print(f"  Description: {checkpoint.description}")
                print(f"  Created: {checkpoint.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
                print(f"  Variables: {checkpoint.variable_count}")
                if checkpoint.file_size_mb > 0:
                    print(f"  File Size: {checkpoint.file_size_mb:.1f} MB")
                if checkpoint.checkpoint_id:
                    print(f"  ID: {checkpoint.checkpoint_id}")
                print()
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
        print("\nCLAUDE: Checkpoint and associated snapshot files have been removed")
    else:
        _handle_api_error(result)
