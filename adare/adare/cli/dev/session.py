"""
CLI command handlers for dev mode session management.

Provides exec_* functions for session lifecycle:
- start, stop, resume, list, state, cleanup
"""

import logging
import threading
from pathlib import Path

from adare.api import AdareAPI
from adare.backend.basics import determine_projectdirectory
from adare.cli.dev._helpers import (
    _resolve_session_id,
    _start_event_listeners,
    _stop_event_listeners,
)
from adare.cli.utils import get_project_path, handle_api_error
from adare.console import print_error_message, print_success_message
from adare.core.dto.devmode import (
    DevSessionCleanupRequest,
    DevSessionListRequest,
    DevSessionStartRequest,
    DevSessionStateRequest,
    DevSessionStopRequest,
)

log = logging.getLogger(__name__)


def exec_dev_start(arguments):
    """Start dev session with flow console UI."""
    from pathlib import Path

    import ulid

    from adare.backend.experiment.print import ExperimentFlowConsole, flowconsolemanager

    # Setup
    project_directory = get_project_path(arguments)
    Path(arguments.log) if hasattr(arguments, 'log') and arguments.log else None

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
            handle_api_error(result)

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
    project_directory = get_project_path(arguments)
    Path(arguments.log) if hasattr(arguments, 'log') and arguments.log else None

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
            handle_api_error(result)

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
        handle_api_error(result)


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
        handle_api_error(result)


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
        handle_api_error(result)


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
        handle_api_error(result)
