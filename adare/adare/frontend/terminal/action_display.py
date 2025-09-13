"""Shared action display logic extracted from the event listener.

This module provides consistent action display formatting for both live console
and historical run display.
"""

from adarelib.constants import StatusEnum
from adare.types.event_types import ActionType


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
            elif target_info.get('text'):
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
        elif action_type == ActionType.DOUBLECLICK:
            coords = action_data.get('coordinates')
            if coords:
                return f"double-click at ({coords[0]}, {coords[1]})"
            return "double-click action"
    
    elif action_type == ActionType.KEYBOARD:
        keys = action_data.get('keys_sent') or action_data.get('keys')
        combination = action_data.get('combination')
        if keys:
            return f"type '{keys}'"
        elif combination:
            return f"press {'+'.join(combination)}"
        return "keyboard input"
    
    elif action_type == ActionType.COMMAND:
        command = action_data.get('command_executed') or action_data.get('command') or action_data.get('cmd')
        if command:
            # Truncate long commands
            if len(command) > 50:
                command = command[:47] + "..."
            return f"execute '{command}'"
        return "execute command"
    
    elif action_type == ActionType.IDLE:
        duration = action_data.get('actual_duration') or action_data.get('duration')
        if duration:
            return f"wait {duration:.1f}s"
        return "wait"
    
    elif action_type == ActionType.TEST:
        test_name = action_data.get('test_name')
        if test_name:
            return f"run test '{test_name}'"
        return "run test"
    
    elif action_type == ActionType.SCREENSHOT:
        path = action_data.get('screenshot_path')
        if path:
            return f"save screenshot to {path}"
        return "take screenshot"
    
    elif action_type == ActionType.SCROLL:
        direction = action_data.get('direction')
        amount = action_data.get('amount')
        if direction and amount:
            return f"scroll {direction} {amount} steps"
        elif direction:
            return f"scroll {direction}"
        return "scroll"
    
    elif action_type == ActionType.DRAG:
        src_coords = action_data.get('source_coordinates')
        dest_coords = action_data.get('dest_coordinates')
        if src_coords and dest_coords:
            return f"drag from ({src_coords[0]}, {src_coords[1]}) to ({dest_coords[0]}, {dest_coords[1]})"
        return "drag action"
    
    elif action_type == ActionType.GOTO:
        url = action_data.get('final_url') or action_data.get('url')
        if url:
            return f"navigate to {url}"
        return "navigate"
    
    elif action_type == ActionType.SAVETIMESTAMP:
        variable = action_data.get('variable')
        timestamp = action_data.get('timestamp_value')
        if variable and timestamp:
            return f"save timestamp {timestamp} to {variable}"
        elif variable:
            return f"save timestamp to {variable}"
        return "save timestamp"
    
    elif action_type == ActionType.BLOCK:
        action_count = action_data.get('action_count') or action_data.get('actions_executed', 0)
        if action_count:
            return f"block ({action_count} actions)"
        return "block action"
    
    elif action_type == ActionType.FIND:
        target_info = action_data.get('target_info')
        if target_info:
            if target_info.get('image'):
                return f"finding image '{target_info['image']}' on screen"
            elif target_info.get('text'):
                return f"finding text '{target_info['text']}' on screen"
            elif target_info.get('position'):
                return f"finding position {target_info['position']} on screen"
        return "finding target on screen"
    
    elif action_type == ActionType.EXECUTE:
        coordinates = action_data.get('coordinates')
        if coordinates:
            return f"executing at ({coordinates[0]}, {coordinates[1]})"
        return "executing action"
    
    elif action_type == ActionType.PULL:
        src = action_data.get('src') or action_data.get('source')
        
        if src:
            return f"pull {src}"
        return "pull files"
    
    else:
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
            # Extract test result category for enhanced status determination
            result_category = action_data.get('result_category', 'unknown')
            if result_category == 'success':
                status = StatusEnum.FINISHED
                result_status = StatusEnum.SUCCESS
            elif result_category == 'test_failure':
                status = StatusEnum.FINISHED  # Test ran successfully but failed condition
                result_status = StatusEnum.TEST_FAILED
            elif result_category == 'execution_error':
                status = StatusEnum.FAILED  # Test had execution issues - show as failed stage
                result_status = None  # No result status for execution errors
            else:
                status = StatusEnum.FINISHED
                result_status = StatusEnum.SUCCESS
        else:
            status = StatusEnum.FINISHED
            result_status = None
    else:
        # Failed action
        if action_type == ActionType.TEST:
            # For test actions, check the specific error type
            result_category = action_data.get('result_category', 'execution_error')
            if result_category == 'execution_error':
                status = StatusEnum.FAILED  # Test execution failed - show as failed stage
                result_status = None  # No result status for execution errors
            else:
                status = StatusEnum.FINISHED  # Test assertion failed - show as completed with failed result
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