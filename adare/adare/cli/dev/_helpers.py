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
    Resolve a session reference: an explicit id/name, or auto-detect one running.

    When a reference is given it may be a session id OR a human-friendly name
    (set with `adare dev start --name`). A unique name resolves to its id; an
    ambiguous name lists the candidates and exits.

    Args:
        session_id: Explicitly provided session id or name (None if not provided)
        project_directory: Optional project filter for lookup / name scoping

    Returns:
        Valid session ID (provided, resolved from a name, or auto-detected)

    Exits:
        With error message if:
        - A given name is ambiguous (lists candidates)
        - session_id is None and no / multiple sessions are running
    """
    from adare.database.api.devmode import AmbiguousSessionNameError, DevModeApi

    api = DevModeApi()

    # Fast path: a reference was given — resolve it as an id or a name.
    if session_id:
        try:
            resolved = api.resolve_session_ref(session_id, project_directory)
        except AmbiguousSessionNameError as e:
            print_error_message(
                title=f"Session name '{e.name}' is ambiguous ({len(e.matches)} matches)",
                next_steps=[
                    'Specify the exact session with: adare dev <command> -s <session_id>',
                    'List all sessions with: adare dev list',
                ]
            )
            print("\nMatching sessions:")
            for s in e.matches:
                print(
                    f"  - {s.session_id}  name={s.name}  status={s.status}  "
                    f"({s.experiment_name} / {s.environment_name})"
                )
            exit(1)
        # None -> ref is neither a known id nor a name; return it unchanged so
        # downstream emits the familiar SESSION_NOT_FOUND error.
        return resolved or session_id

    # Slow path: auto-detect session
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
