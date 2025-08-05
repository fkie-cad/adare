from adare.backend.events.pubsub import subscribe_cli, subscribe_db
from adare.backend.experiment.print import flowconsolemanager
from adarelib.constants import StatusEnum
from adare.types.stages import Stage, _stage_registry
from adare.types.event_types import event_type_resolver, EventType, ActionType

import logging
log = logging.getLogger(__name__)


def _get_action_display_info(action_type: ActionType, action_data: dict, is_complete: bool = False) -> str:
    """Get display information based on action type and data."""
    
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
    
    else:
        # Fallback to description if provided, otherwise generic
        return action_data.get('action_description', f"{action_type.value} action")

def event_listener_cli(ulid):
    console = flowconsolemanager.get_handler(ulid)
    if not console:
        log.error(f"[EventListener CLI] No console found for ULID: {ulid}")
        return
    for event in subscribe_cli(ulid):
        try:
            log.info(f"[EventListener CLI] Processing event for {ulid}: {event}")
            
            # Determine event type (stage or action)
            event_type = event.get("type", "stage")  # Default to stage for backward compatibility
            
            if event_type == "stage":
                _handle_stage_event(event, console, ulid)
            elif event_type == "action":
                _handle_action_event(event, console, ulid)
            else:
                log.warning(f"[EventListener CLI] Unknown event type: {event_type}")

        except Exception as e:
            # Log or handle malformed events
            log.error(f"[EventListener CLI] Error processing event: {e}")


def _handle_stage_event(event, console, ulid):
    """Handle stage events (existing logic)."""
    stage = event.get("data", {})
    stage_id = event.get("stage_id")
    if not stage:
        log.warning(f"[EventListener CLI] No stage data found in event: {event}")
        return
    stage = Stage.from_dict(stage)
    
    # Debug logging for duplicate stage investigation
    log.info(f"[EventListener CLI] Stage: {stage.name}, ID: {stage_id}, Start: {stage.start_time}, End: {stage.end_time}, Status: {stage.status}")

    # Check stage status first
    finished = stage.start_time and stage.end_time
    in_progress = stage.start_time and not stage.end_time
    
    # Calculate display level based on parent hierarchy
    level = 0
    parent = stage.parent
    while parent:
        parent_stage_class = _stage_registry.get(parent)
        if not parent_stage_class:
            log.warning(f"[EventListener CLI] Parent stage {parent} not found in registry")
            break
        level += 1
        parent = parent_stage_class().parent
        if level > 10:
            log.warning(f"[EventListener CLI] Level too high, breaking loop due to expected endless loop: {level}")
            break
    
    if stage.sub_msg:
        message = f"{stage.name}: {stage.sub_msg}"
    else:
        message = stage.msg

    if finished:
        # Calculate stage duration if both start and end times are available
        stage_duration = None
        if stage.start_time and stage.end_time:
            stage_duration = (stage.end_time - stage.start_time).total_seconds()
        
        if console.exists(stage_id):
            # Add interrupt indication for spinner updates
            if stage.status == StatusEnum.INTERRUPTED:
                message = f"{message} (interrupted by user)"
            if stage.result_status:
                console.log_spinner_done(identifier=stage_id, status=stage.status, message=message, result_status=stage.result_status, duration=stage_duration)
            else:
                console.log_spinner_done(identifier=stage_id,  status=stage.status, message=message, duration=stage_duration)
            log.info(f"[EventListener CLI] Processed stage event for {ulid}: {stage.name if stage else 'None'}")
        else:
            if stage.status == StatusEnum.SUCCESS:
                console.log_success(identifier=stage_id, message=message, level=level, duration=stage_duration)
            elif stage.status == StatusEnum.WARNING:
                console.log_warning(identifier=stage_id, message=message, level=level, duration=stage_duration)
            elif stage.status == StatusEnum.ERROR:
                console.log_error(identifier=stage_id, message=message, level=level, duration=stage_duration)
            elif stage.status == StatusEnum.INTERRUPTED:
                interrupted_message = f"{message} (interrupted by user)"
                console.log_interrupted(identifier=stage_id, message=interrupted_message, level=level, duration=stage_duration)
            elif stage.status == StatusEnum.FAILED:
                console.log_failed(identifier=stage_id, message=message, level=level, duration=stage_duration)
            elif stage.status == StatusEnum.FINISHED:
                console.log_finished(identifier=stage_id, message=message, level=level, duration=stage_duration)
    elif in_progress:
        # Only add the stage if it doesn't already exist
        if not console.exists(stage_id):
            log.info(f"[EventListener CLI] Creating new console spinner for stage: {stage.name}, ID: {stage_id}, Level: {level}")
            console.log_spinner(identifier=stage_id, message=message, level=level)
        else:
            log.info(f"[EventListener CLI] Stage already exists in console: {stage.name}, ID: {stage_id}")

    log.info(f"[EventListener CLI] Processed stage event for {ulid}: {stage.name if stage else 'None'}")


def _handle_action_event(event, console, ulid):
    """Handle action events using the new event type system."""
    action_data = event.get("data", {})
    action_id = event.get("action_id")
    
    if not action_data:
        log.warning(f"[EventListener CLI] No action data found in event: {event}")
        return
    
    try:
        # Use the event type resolver to determine event type
        event_type = event_type_resolver.resolve_event_type(action_data)
        action_type = event_type_resolver.get_action_type(event_type)
        
        # Debug logging with proper type information
        log.debug(f"[EventListener CLI] Processing action event: type={event_type.value}, action={action_type.value}, id={action_id}")
        
        # Determine if this is a start or complete event
        is_start_event = event_type_resolver.is_start_event(event_type)
        is_complete_event = event_type_resolver.is_complete_event(event_type)
        
        # Set display level - regular actions at level 2, sub-actions at level 3
        level = action_data.get('display_level', 2)
        
        if is_start_event:
            # Show spinner for action in progress with type-specific data
            display_info = _get_action_display_info(action_type, action_data, is_complete=False)
            message = f"{action_type.value}: {display_info}"
            console.log_spinner(identifier=action_id, message=message, level=level, 
                              spinner='dots', spinner_style='cyan')
            log.info(f"[EventListener CLI] Action started: {action_type.value} with ID {action_id}")
            
        elif is_complete_event:
            # Update spinner with completion status and type-specific data
            display_info = _get_action_display_info(action_type, action_data, is_complete=True)
            message = f"{action_type.value}: {display_info}"
            
            # Determine status based on action result
            success = action_data.get('success', False)
            execution_time = action_data.get('execution_time')
            error_message = action_data.get('error_message')
            
            if success:
                # Check if it's a test action for special handling
                if action_type == ActionType.TEST:
                    status = StatusEnum.SUCCESS
                    result_status = StatusEnum.SUCCESS
                else:
                    status = StatusEnum.SUCCESS
                    result_status = None
            else:
                # Failed action
                if action_type == ActionType.TEST:
                    status = StatusEnum.TEST_FAILED
                    result_status = StatusEnum.TEST_FAILED
                else:
                    status = StatusEnum.FAILED
                    result_status = None
                
                # Add error message if available
                if error_message:
                    message = f"{message} - {error_message}"
            
            # Update the console
            if console.exists(action_id):
                console.log_spinner_done(identifier=action_id, status=status, 
                                       message=message, result_status=result_status, duration=execution_time)
            else:
                # Direct log if spinner doesn't exist
                if status == StatusEnum.SUCCESS:
                    console.log_success(identifier=action_id, message=message, level=level, duration=execution_time)
                elif status == StatusEnum.TEST_FAILED:
                    console.log_failed(identifier=action_id, message=message, level=level, duration=execution_time)
                elif status == StatusEnum.FAILED:
                    console.log_failed(identifier=action_id, message=message, level=level, duration=execution_time)
            
            log.info(f"[EventListener CLI] Action completed: {action_type.value} with ID {action_id}, Success: {success}")
            
        else:
            log.warning(f"[EventListener CLI] Unknown action event type: {event_type.value}")
            
    except Exception as e:
        log.error(f"[EventListener CLI] Error processing action event: {e}", exc_info=True)


def event_listener_db(ulid):
    for event in subscribe_db(ulid):
        from adare.backend.experiment.database import update_stage_in_run
        
        # Handle different event types
        event_type = event.get("type", "stage")
        
        if event_type == "stage":
            stage = event.get("data", {})
            stage_id = event.get("stage_id")
            stage = Stage.from_dict(stage) if stage else None
            if not stage:
                log.error(f"[EventListener DB] No stage data found in event: {event}")
                return
            update_stage_in_run(stage=stage, experimentrun_ulid=ulid, stage_id=stage_id)
            log.debug(f"[EventListener DB] Processed stage event for {ulid}: {stage.name if stage else 'None'}")
        elif event_type == "action":
            # For now, we don't store action events in the database
            # The PlaybookController already handles database storage via ActionExecution records
            log.debug(f"[EventListener DB] Skipping action event (handled by PlaybookController)")
        else:
            log.warning(f"[EventListener DB] Unknown event type: {event_type}")