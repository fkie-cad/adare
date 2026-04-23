"""
Shared helper functions for dev CLI sub-modules.

These helpers are used across session, actions, checkpoints, and recording modules.
They are internal to the dev package (prefixed with underscore).
"""

import logging
import threading
from pathlib import Path

from adare.console import print_error_message

log = logging.getLogger(__name__)


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
