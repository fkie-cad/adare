"""Shared action display logic extracted from the event listener.

This module provides consistent action display formatting for both live console
and historical run display.
"""

from adare.types.event_types import ActionType
from adarelib.constants import StatusEnum


def get_action_display_info(action_type: ActionType, action_data: dict, is_complete: bool = False) -> str:
    """Get display information based on action type and data.

    This is the same logic used in the live event listener console.
    """

    if action_type in (ActionType.CLICK, ActionType.RIGHTCLICK, ActionType.DOUBLECLICK):
        # Try to get target info first, then fall back to coordinates
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

        # Handle different click types
        if action_type == ActionType.RIGHTCLICK:
            coords = action_data.get('coordinates')
            if coords:
                return f"right-click at ({coords[0]}, {coords[1]})"
            return "right-click action"
        if action_type == ActionType.DOUBLECLICK:
            coords = action_data.get('coordinates')
            if coords:
                return f"double-click at ({coords[0]}, {coords[1]})"
            return "double-click action"

    if action_type == ActionType.KEYBOARD:
        # Check for standard fields first (key, text)
        key = action_data.get('key')
        text = action_data.get('text')

        # Check for legacy fields
        keys = action_data.get('keys_sent') or action_data.get('keys')
        combination = action_data.get('combination')

        if key:
            return f"press '{key}'"
        if text:
            # Truncate text if too long
            display_text = text[:15] + "..." if len(text) > 15 else text
            return f"type '{display_text}'"
        if keys:
            return f"type '{keys}'"
        if combination:
            return f"press {'+'.join(combination)}"
        return "keyboard input"

    if action_type == ActionType.COMMAND:
        command = action_data.get('command_executed') or action_data.get('command') or action_data.get('cmd')
        if command:
            # Smart truncation for heredoc commands
            heredoc_pos = command.find('<<')
            if heredoc_pos != -1:
                # Found heredoc syntax, truncate after the << operator
                command = command[:heredoc_pos + 2] + " ..."
            elif len(command) > 50:
                # Regular truncation for long commands
                command = command[:47] + "..."
            return f"execute '{command}'"
        return "execute command"

    if action_type == ActionType.IDLE:
        duration = action_data.get('actual_duration') or action_data.get('duration')
        if duration:
            return f"wait {duration:.1f}s"
        return "wait"

    if action_type == ActionType.TEST:
        test_name = action_data.get('test_name')
        if test_name:
            return f"run test '{test_name}'"
        return "run test"

    if action_type == ActionType.SCREENSHOT:
        path = action_data.get('screenshot_path')
        if path:
            return f"save screenshot to {path}"
        return "take screenshot"

    if action_type == ActionType.SCROLL:
        direction = action_data.get('direction')
        amount = action_data.get('amount')
        if direction and amount:
            return f"scroll {direction} {amount} steps"
        if direction:
            return f"scroll {direction}"
        return "scroll"

    if action_type == ActionType.DRAG:
        src_coords = action_data.get('source_coordinates')
        dest_coords = action_data.get('dest_coordinates')
        if src_coords and dest_coords:
            return f"drag from ({src_coords[0]}, {src_coords[1]}) to ({dest_coords[0]}, {dest_coords[1]})"
        return "drag action"

    if action_type == ActionType.GOTO:
        url = action_data.get('final_url') or action_data.get('url')
        if url:
            return f"navigate to {url}"
        return "navigate"

    if action_type == ActionType.SAVETIMESTAMP:
        variable = action_data.get('variable')
        timestamp = action_data.get('timestamp_value')
        if variable and timestamp:
            return f"save timestamp {timestamp} to {variable}"
        if variable:
            return f"save timestamp to {variable}"
        return "save timestamp"

    if action_type == ActionType.BLOCK:
        action_count = action_data.get('action_count') or action_data.get('actions_executed', 0)
        if action_count:
            return f"block ({action_count} actions)"
        return "block action"

    if action_type == ActionType.FIND:
        target_info = action_data.get('target_info')
        matched_text = action_data.get('matched_text')  # What OCR actually detected

        if target_info:
            if target_info.get('image'):
                return f"finding image '{target_info['image']}' on screen"
            if target_info.get('text'):
                base_msg = f"finding text '{target_info['text']}' on screen"
                # Show what was actually matched if different (fuzzy/regex matching)
                if matched_text and matched_text != target_info['text']:
                    return f"{base_msg} (matched: '{matched_text}')"
                return base_msg
            if target_info.get('position'):
                return f"finding position {target_info['position']} on screen"
        return "finding target on screen"

    if action_type == ActionType.EXECUTE:
        coordinates = action_data.get('coordinates')
        if coordinates:
            return f"executing at ({coordinates[0]}, {coordinates[1]})"
        return "executing action"

    if action_type == ActionType.PULL:
        src = action_data.get('src') or action_data.get('source')

        if src:
            return f"pull {src}"
        return "pull files"

    if action_type == ActionType.WAIT_UNTIL:
        target_info = action_data.get('target_info')
        timeout = action_data.get('timeout')
        found = action_data.get('found')
        initial_delay = action_data.get('initial_delay')
        check_interval = action_data.get('check_interval')

        # Build the target description
        target_desc = "target"
        if target_info:
            if target_info.get('image'):
                target_desc = f"image '{target_info['image']}'"
            elif target_info.get('text'):
                target_desc = f"text '{target_info['text']}'"
            elif target_info.get('position'):
                target_desc = f"position {target_info['position']}"

        # For complete events, include result
        if is_complete:
            if found:
                return f"wait until {target_desc} appears - found text"
            if timeout:
                return f"wait until {target_desc} appears (timeout after {timeout}s)"
            return f"wait until {target_desc} appears - failed"
        # For start events, show configuration
        config_parts = []
        if timeout:
            config_parts.append(f"timeout: {timeout}s")
        if initial_delay and initial_delay > 0:
            config_parts.append(f"delay: {initial_delay}s")
        if check_interval and check_interval > 0:
            config_parts.append(f"interval: {check_interval}s")

        if config_parts:
            config_str = f" ({', '.join(config_parts)})"
            return f"wait until {target_desc} appears{config_str}"
        return f"wait until {target_desc} appears"

    if action_type == ActionType.LOOP:
        # For complete events, show summary
        if is_complete:
            iterations = action_data.get('iterations') or action_data.get('iterations_completed', 0)
            actions_executed = action_data.get('actions_executed', 0)
            if iterations and actions_executed:
                return f"loop completed ({iterations} iterations, {actions_executed} actions)"
            if iterations:
                return f"loop completed ({iterations} iterations)"
            return "loop completed"
        # For start events, show configuration
        iteration_count = action_data.get('iteration_count')
        items = action_data.get('items')
        if iteration_count:
            return f"loop ({iteration_count} iterations)"
        if items and isinstance(items, list):
            return f"loop ({len(items)} items)"
        return "loop action"

    if action_type == ActionType.STOP:
        # Show stop condition result
        if is_complete:
            should_stop = action_data.get('should_stop', False)
            condition_met = action_data.get('condition_met')
            variable = action_data.get('variable')

            if should_stop:
                if variable:
                    return f"stop condition met (variable: {variable}) - execution halted"
                return "unconditional stop - execution halted"
            if variable:
                return f"stop condition not met (variable: {variable}) - continuing"
            return "stop action - continuing"
        # For start events
        return "evaluating stop condition"

    if action_type == ActionType.CONTINUE:
        # Show continue condition result
        if is_complete:
            should_continue = action_data.get('should_continue', False)
            condition_met = action_data.get('condition_met')
            variable = action_data.get('variable')

            if should_continue:
                if variable:
                    return f"continue condition met (variable: {variable}) - skipping remaining actions"
                return "unconditional continue - skipping remaining actions"
            if variable:
                return f"continue condition not met (variable: {variable}) - proceeding normally"
            return "continue action - proceeding normally"
        # For start events
        return "evaluating continue condition"

    if action_type == ActionType.SNAPSHOT_FILESYSTEM:
        snapshot_type = action_data.get('snapshot_type')
        files_count = action_data.get('files_count')
        if is_complete:
            if files_count:
                return f"filesystem snapshot ({snapshot_type or 'snapshot'}) - {files_count} files"
            return f"filesystem snapshot ({snapshot_type or 'snapshot'}) complete"
        return f"capturing filesystem snapshot ({snapshot_type or 'snapshot'})"

    if action_type == ActionType.PULL_CHANGED_FILES:
        destination = action_data.get('destination')
        files_pulled = action_data.get('files_pulled')
        if is_complete:
            if files_pulled:
                return f"pulled {files_pulled} changed files"
            return "pull changed files complete"
        if destination:
            return f"pulling changed files to {destination}"
        return "pulling changed files"

    # Throw exception for unhandled action types to catch missing cases
    raise ValueError(f"Unhandled action type in get_action_display_info: {action_type} (value: {action_type.value})")


def determine_action_status(action_type: ActionType, action_data: dict):
    """Determine the appropriate status for an action based on its result.

    This uses the same logic as the live event listener.
    Returns: (status, result_status) tuple
    """
    success = action_data.get('success', False)
    error_message = action_data.get('error_message') or action_data.get('error')

    if success:
        # Check if it's a test action for special handling
        if action_type == ActionType.TEST:
            # Extract test result category and expect_to_fail flag for enhanced status determination
            result_category = action_data.get('result_category', 'unknown')
            expect_to_fail = action_data.get('expect_to_fail', False)

            if result_category == 'success':
                status = StatusEnum.FINISHED
                # For expect_to_fail tests, success means the test unexpectedly passed (bad)
                result_status = StatusEnum.TEST_FAILED if expect_to_fail else StatusEnum.SUCCESS
            elif result_category == 'test_failure':
                status = StatusEnum.FINISHED  # Test ran successfully but failed condition
                # For expect_to_fail tests, failure means the test failed as expected (good)
                result_status = StatusEnum.SUCCESS if expect_to_fail else StatusEnum.TEST_FAILED
            elif result_category == 'execution_error':
                status = StatusEnum.FAILED  # Test had execution issues - show as failed stage
                result_status = None  # No result status for execution errors (never invert execution errors)
            else:
                status = StatusEnum.FINISHED
                result_status = StatusEnum.SUCCESS
        else:
            status = StatusEnum.FINISHED
            result_status = None
    else:
        # Failed action (success=False)
        if action_type == ActionType.TEST:
            # For test actions, check the specific error type and expect_to_fail flag
            result_category = action_data.get('result_category', 'execution_error')
            expect_to_fail = action_data.get('expect_to_fail', False)

            if result_category == 'execution_error':
                status = StatusEnum.FAILED  # Test execution failed - show as failed stage
                result_status = None  # No result status for execution errors (never invert execution errors)
            elif result_category == 'success' and expect_to_fail:
                # Special case: test succeeded but expect_to_fail=True caused success to be inverted to False
                # This means test passed when it should have failed - show as FAILED
                status = StatusEnum.FINISHED
                result_status = StatusEnum.TEST_FAILED
            elif result_category == 'test_failure' and expect_to_fail:
                # Test failed as expected - show as SUCCESS
                status = StatusEnum.FINISHED
                result_status = StatusEnum.SUCCESS
            else:
                # Normal test failure (no expect_to_fail or other cases)
                status = StatusEnum.FINISHED
                result_status = StatusEnum.TEST_FAILED
        else:
            status = StatusEnum.FAILED
            result_status = None

    return status, result_status


def format_action_message(action_type: ActionType, display_info: str, error_message: str = None) -> str:
    """Format the complete action message as shown in the live console."""
    message = f"{action_type.value}: {display_info}"

    # Add error message if available
    if error_message:
        message = f"{message} - {error_message}"

    return message
