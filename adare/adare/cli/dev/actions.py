"""
CLI command handlers for dev mode action and playbook execution.

Provides exec_* functions for:
- Single action execution
- Playbook execution (single and batch)
- CV server management
- Test function updates
"""

import logging
import threading
import time
from pathlib import Path

from adare.api import AdareAPI
from adare.cli.dev._helpers import (
    _resolve_session_id,
    _start_event_listeners,
    _stop_event_listeners,
)
from adare.cli.utils import get_project_path, handle_api_error
from adare.console import print_error_message, print_success_message
from adare.core.dto.devmode import (
    DevActionExecuteRequest,
    DevCVRestartRequest,
    DevCVStopRequest,
    DevPlaybookExecuteRequest,
)

log = logging.getLogger(__name__)


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
        handle_api_error(result)


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
            handle_api_error(result)

    except KeyboardInterrupt:
        user_interrupt_event.set()
        flow_console.log_interrupted('PLAYBOOK_INTERRUPTED', 'Interrupted by user')
        flow_console.stop()
        print("\n\nPlaybook execution interrupted")
        exit(1)
    finally:
        flowconsolemanager.remove_handler(console_ulid)
        _stop_event_listeners()


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
        handle_api_error(result)


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
        handle_api_error(result)


def exec_dev_playbook_batch(arguments):
    """Execute multiple playbooks with checkpoint restoration."""
    import ulid

    from adare.console.flow import ExperimentFlowConsole
    from adare.core.dto.devmode import DevPlaybookBatchExecuteRequest

    # AUTO-DETECT SESSION ID
    session_id = _resolve_session_id(arguments.session_id)

    # Create flow console for progress tracking
    console_ulid = str(ulid.ULID())
    ExperimentFlowConsole(
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
        handle_api_error(result)


def exec_dev_update_testfunctions(arguments):
    """
    Update test functions in the VM.

    Args:
        arguments: Parsed arguments
    """
    project_directory = get_project_path(arguments)
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
        handle_api_error(result)
