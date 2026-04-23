"""Shared action display logic extracted from the event listener.

This module provides consistent action display formatting for both live console
and historical run display.
"""

from adare.types.event_types import ActionType
from adarelib.constants import StatusEnum

# ── Per-action-type display handlers ────────────────────────────────


def _display_click(action_data: dict, _is_complete: bool) -> str:
    target_info = action_data.get('target_info')
    if target_info:
        if target_info.get('image'):
            return f"click {target_info['image']}"
        if target_info.get('text'):
            return f"click text '{target_info['text']}'"
    coords = action_data.get('coordinates')
    if coords:
        return f"click at ({coords[0]}, {coords[1]})"
    return "click action"


def _display_keyboard(action_data: dict, _is_complete: bool) -> str:
    key = action_data.get('key')
    text = action_data.get('text')
    keys = action_data.get('keys_sent') or action_data.get('keys')
    combination = action_data.get('combination')

    if key:
        return f"press '{key}'"
    if text:
        display_text = text[:15] + "..." if len(text) > 15 else text
        return f"type '{display_text}'"
    if keys:
        return f"type '{keys}'"
    if combination:
        return f"press {'+'.join(combination)}"
    return "keyboard input"


def _display_command(action_data: dict, _is_complete: bool) -> str:
    command = action_data.get('command_executed') or action_data.get('command') or action_data.get('cmd')
    if command:
        heredoc_pos = command.find('<<')
        if heredoc_pos != -1:
            command = command[:heredoc_pos + 2] + " ..."
        elif len(command) > 50:
            command = command[:47] + "..."
        return f"execute '{command}'"
    return "execute command"


def _display_idle(action_data: dict, _is_complete: bool) -> str:
    duration = action_data.get('actual_duration') or action_data.get('duration')
    if duration:
        return f"wait {duration:.1f}s"
    return "wait"


def _display_test(action_data: dict, _is_complete: bool) -> str:
    test_name = action_data.get('test_name')
    if test_name:
        return f"run test '{test_name}'"
    return "run test"


def _display_screenshot(action_data: dict, _is_complete: bool) -> str:
    path = action_data.get('screenshot_path')
    if path:
        return f"save screenshot to {path}"
    return "take screenshot"


def _display_scroll(action_data: dict, _is_complete: bool) -> str:
    direction = action_data.get('direction')
    amount = action_data.get('amount')
    if direction and amount:
        return f"scroll {direction} {amount} steps"
    if direction:
        return f"scroll {direction}"
    return "scroll"


def _display_drag(action_data: dict, _is_complete: bool) -> str:
    src_coords = action_data.get('source_coordinates')
    dest_coords = action_data.get('dest_coordinates')
    if src_coords and dest_coords:
        return f"drag from ({src_coords[0]}, {src_coords[1]}) to ({dest_coords[0]}, {dest_coords[1]})"
    return "drag action"


def _display_goto(action_data: dict, _is_complete: bool) -> str:
    url = action_data.get('final_url') or action_data.get('url')
    if url:
        return f"navigate to {url}"
    return "navigate"


def _display_savetimestamp(action_data: dict, _is_complete: bool) -> str:
    variable = action_data.get('variable')
    timestamp = action_data.get('timestamp_value')
    if variable and timestamp:
        return f"save timestamp {timestamp} to {variable}"
    if variable:
        return f"save timestamp to {variable}"
    return "save timestamp"


def _display_block(action_data: dict, _is_complete: bool) -> str:
    action_count = action_data.get('action_count') or action_data.get('actions_executed', 0)
    if action_count:
        return f"block ({action_count} actions)"
    return "block action"


def _display_find(action_data: dict, _is_complete: bool) -> str:
    target_info = action_data.get('target_info')
    matched_text = action_data.get('matched_text')

    if target_info:
        if target_info.get('image'):
            return f"finding image '{target_info['image']}' on screen"
        if target_info.get('text'):
            base_msg = f"finding text '{target_info['text']}' on screen"
            if matched_text and matched_text != target_info['text']:
                return f"{base_msg} (matched: '{matched_text}')"
            return base_msg
        if target_info.get('position'):
            return f"finding position {target_info['position']} on screen"
    return "finding target on screen"


def _display_execute(action_data: dict, _is_complete: bool) -> str:
    coordinates = action_data.get('coordinates')
    if coordinates:
        return f"executing at ({coordinates[0]}, {coordinates[1]})"
    return "executing action"


def _display_pull(action_data: dict, _is_complete: bool) -> str:
    src = action_data.get('src') or action_data.get('source')
    if src:
        return f"pull {src}"
    return "pull files"


def _display_wait_until(action_data: dict, is_complete: bool) -> str:
    target_info = action_data.get('target_info')
    timeout = action_data.get('timeout')

    target_desc = "target"
    if target_info:
        if target_info.get('image'):
            target_desc = f"image '{target_info['image']}'"
        elif target_info.get('text'):
            target_desc = f"text '{target_info['text']}'"
        elif target_info.get('position'):
            target_desc = f"position {target_info['position']}"

    if is_complete:
        if action_data.get('found'):
            return f"wait until {target_desc} appears - found text"
        if timeout:
            return f"wait until {target_desc} appears (timeout after {timeout}s)"
        return f"wait until {target_desc} appears - failed"

    config_parts = []
    if timeout:
        config_parts.append(f"timeout: {timeout}s")
    initial_delay = action_data.get('initial_delay')
    if initial_delay and initial_delay > 0:
        config_parts.append(f"delay: {initial_delay}s")
    check_interval = action_data.get('check_interval')
    if check_interval and check_interval > 0:
        config_parts.append(f"interval: {check_interval}s")

    if config_parts:
        return f"wait until {target_desc} appears ({', '.join(config_parts)})"
    return f"wait until {target_desc} appears"


def _display_loop(action_data: dict, is_complete: bool) -> str:
    if is_complete:
        iterations = action_data.get('iterations') or action_data.get('iterations_completed', 0)
        actions_executed = action_data.get('actions_executed', 0)
        if iterations and actions_executed:
            return f"loop completed ({iterations} iterations, {actions_executed} actions)"
        if iterations:
            return f"loop completed ({iterations} iterations)"
        return "loop completed"

    iteration_count = action_data.get('iteration_count')
    items = action_data.get('items')
    if iteration_count:
        return f"loop ({iteration_count} iterations)"
    if items and isinstance(items, list):
        return f"loop ({len(items)} items)"
    return "loop action"


def _display_stop(action_data: dict, is_complete: bool) -> str:
    if is_complete:
        should_stop = action_data.get('should_stop', False)
        variable = action_data.get('variable')
        if should_stop:
            if variable:
                return f"stop condition met (variable: {variable}) - execution halted"
            return "unconditional stop - execution halted"
        if variable:
            return f"stop condition not met (variable: {variable}) - continuing"
        return "stop action - continuing"
    return "evaluating stop condition"


def _display_continue(action_data: dict, is_complete: bool) -> str:
    if is_complete:
        should_continue = action_data.get('should_continue', False)
        variable = action_data.get('variable')
        if should_continue:
            if variable:
                return f"continue condition met (variable: {variable}) - skipping remaining actions"
            return "unconditional continue - skipping remaining actions"
        if variable:
            return f"continue condition not met (variable: {variable}) - proceeding normally"
        return "continue action - proceeding normally"
    return "evaluating continue condition"


def _display_snapshot_filesystem(action_data: dict, is_complete: bool) -> str:
    snapshot_type = action_data.get('snapshot_type')
    label = snapshot_type or 'snapshot'
    if is_complete:
        files_count = action_data.get('files_count')
        if files_count:
            return f"filesystem snapshot ({label}) - {files_count} files"
        return f"filesystem snapshot ({label}) complete"
    return f"capturing filesystem snapshot ({label})"


def _display_pull_changed_files(action_data: dict, is_complete: bool) -> str:
    if is_complete:
        files_pulled = action_data.get('files_pulled')
        if files_pulled:
            return f"pulled {files_pulled} changed files"
        return "pull changed files complete"
    destination = action_data.get('destination')
    if destination:
        return f"pulling changed files to {destination}"
    return "pulling changed files"


# ── Dispatch table ──────────────────────────────────────────────────

_ACTION_DISPLAY_HANDLERS: dict[ActionType, callable] = {
    ActionType.CLICK: _display_click,
    ActionType.RIGHTCLICK: _display_click,
    ActionType.DOUBLECLICK: _display_click,
    ActionType.KEYBOARD: _display_keyboard,
    ActionType.COMMAND: _display_command,
    ActionType.IDLE: _display_idle,
    ActionType.TEST: _display_test,
    ActionType.SCREENSHOT: _display_screenshot,
    ActionType.SCROLL: _display_scroll,
    ActionType.DRAG: _display_drag,
    ActionType.GOTO: _display_goto,
    ActionType.SAVETIMESTAMP: _display_savetimestamp,
    ActionType.BLOCK: _display_block,
    ActionType.FIND: _display_find,
    ActionType.EXECUTE: _display_execute,
    ActionType.PULL: _display_pull,
    ActionType.WAIT_UNTIL: _display_wait_until,
    ActionType.LOOP: _display_loop,
    ActionType.STOP: _display_stop,
    ActionType.CONTINUE: _display_continue,
    ActionType.SNAPSHOT_FILESYSTEM: _display_snapshot_filesystem,
    ActionType.PULL_CHANGED_FILES: _display_pull_changed_files,
}


# ── Public API ──────────────────────────────────────────────────────


def get_action_display_info(action_type: ActionType, action_data: dict, is_complete: bool = False) -> str:
    """Get display information based on action type and data.

    This is the same logic used in the live event listener console.
    """
    handler = _ACTION_DISPLAY_HANDLERS.get(action_type)
    if handler is None:
        raise ValueError(
            f"Unhandled action type in get_action_display_info: {action_type} (value: {action_type.value})"
        )
    return handler(action_data, is_complete)


def determine_action_status(action_type: ActionType, action_data: dict):
    """Determine the appropriate status for an action based on its result.

    This uses the same logic as the live event listener.
    Returns: (status, result_status) tuple
    """
    success = action_data.get('success', False)

    if success:
        if action_type == ActionType.TEST:
            return _determine_test_status_success(action_data)
        return StatusEnum.FINISHED, None

    if action_type == ActionType.TEST:
        return _determine_test_status_failure(action_data)
    return StatusEnum.FAILED, None


def _determine_test_status_success(action_data: dict):
    """Determine status for a successful test action."""
    result_category = action_data.get('result_category', 'unknown')
    expect_to_fail = action_data.get('expect_to_fail', False)

    if result_category == 'success':
        result_status = StatusEnum.TEST_FAILED if expect_to_fail else StatusEnum.SUCCESS
        return StatusEnum.FINISHED, result_status
    if result_category == 'test_failure':
        result_status = StatusEnum.SUCCESS if expect_to_fail else StatusEnum.TEST_FAILED
        return StatusEnum.FINISHED, result_status
    if result_category == 'execution_error':
        return StatusEnum.FAILED, None
    return StatusEnum.FINISHED, StatusEnum.SUCCESS


def _determine_test_status_failure(action_data: dict):
    """Determine status for a failed test action."""
    result_category = action_data.get('result_category', 'execution_error')
    expect_to_fail = action_data.get('expect_to_fail', False)

    if result_category == 'execution_error':
        return StatusEnum.FAILED, None
    if result_category == 'success' and expect_to_fail:
        return StatusEnum.FINISHED, StatusEnum.TEST_FAILED
    if result_category == 'test_failure' and expect_to_fail:
        return StatusEnum.FINISHED, StatusEnum.SUCCESS
    return StatusEnum.FINISHED, StatusEnum.TEST_FAILED


def format_action_message(action_type: ActionType, display_info: str, error_message: str = None) -> str:
    """Format the complete action message as shown in the live console."""
    message = f"{action_type.value}: {display_info}"
    if error_message:
        message = f"{message} - {error_message}"
    return message
