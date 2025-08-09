from adare.backend.events.pubsub import subscribe_cli, subscribe_db
from adare.backend.experiment.print import flowconsolemanager
from adarelib.constants import StatusEnum
from adare.types.stages import Stage, _stage_registry
from adare.types.event_types import event_type_resolver, EventType, ActionType

import logging
log = logging.getLogger(__name__)


# Import shared action display logic
from adare.frontend.terminal.action_display import get_action_display_info, determine_action_status, format_action_message


def _compute_display_level(action_data):
    """
    Compute display level based on parent relationships.
    Root level events have display_level = 2 (main playbook actions), each nested level adds 1.
    
    This handles the common cases:
    - Level 2: Main playbook actions (no parent_event_id)
    - Level 3: Sub-actions like block actions, find/execute substages (has parent_event_id)
    
    For deeper nesting (parent->parent->parent chains), a per-experiment session cache
    or database traversal would be needed, but the current pattern handles the main use cases.
    """
    base_level = 2  # Flow console expects main playbook actions at level 2
    
    if not action_data.get('parent_event_id'):
        return base_level  # Main playbook actions (level 2)
    else:
        # For sub-actions (with parent), add 1 to base level  
        # This covers block sub-actions, find/execute substages, etc.
        return base_level + 1  # Sub-actions (level 3)

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
                console.log_spinner_done(identifier=stage_id, status=StatusEnum.FINISHED, message=message, result_status=stage.result_status, duration=stage_duration)
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
            console.log_spinner(identifier=stage_id, message=message, level=level, start_time=stage.start_time)
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
        action_type = event_type_resolver.get_action_type(event_type, action_data)
        
        # Debug logging with proper type information
        log.debug(f"[EventListener CLI] Processing action event: type={event_type.value}, action={action_type.value}, id={action_id}")
        
        # Determine if this is a start or complete event
        is_start_event = event_type_resolver.is_start_event(event_type)
        is_complete_event = event_type_resolver.is_complete_event(event_type)
        
        # Compute display level from parent relationships
        level = _compute_display_level(action_data)
        
        if is_start_event:
            # Show spinner for action in progress with type-specific data
            display_info = get_action_display_info(action_type, action_data, is_complete=False)
            message = format_action_message(action_type, display_info)
            
            # Extract start time from action data for live duration tracking
            from datetime import datetime
            start_time = None
            if action_data.get('timestamp'):
                try:
                    start_time = datetime.fromisoformat(action_data['timestamp'].replace('Z', '+00:00'))
                except:
                    start_time = datetime.now(timezone.utc)
            else:
                start_time = datetime.now(timezone.utc)
            
            console.log_spinner(identifier=action_id, message=message, level=level, 
                              spinner='dots', spinner_style='cyan', start_time=start_time)
            log.info(f"[EventListener CLI] Action started: {action_type.value} with ID {action_id}")
            
        elif is_complete_event:
            # Update spinner with completion status and type-specific data
            display_info = get_action_display_info(action_type, action_data, is_complete=True)
            error_message = action_data.get('error_message') or action_data.get('error')
            message = format_action_message(action_type, display_info, error_message)
            
            # Determine status using shared logic
            status, result_status = determine_action_status(action_type, action_data)
            execution_time = action_data.get('execution_time')
            
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
            
            success = action_data.get('success', False)
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
            
            # ALSO store action substages (find/execute) as action events for better integration
            if stage.name in ['action_find', 'action_execute']:
                try:
                    from adare.database.api.event import EventDbApi
                    
                    # Convert stage to action event data
                    action_data = {
                        'action_description': stage.description if hasattr(stage, 'description') else stage.msg,
                        'success': stage.status == 2,  # StatusEnum.SUCCESS = 2
                        'execution_time': None,  # Could calculate from start/end times if needed
                        'timestamp': stage.start_time.isoformat() if stage.start_time else None
                    }
                    
                    with EventDbApi() as api:
                        api.add_action_event(action_data, stage_id, ulid)
                        log.debug(f"[EventListener DB] Also stored substage as action event: {stage.name}")
                except Exception as e:
                    log.warning(f"[EventListener DB] Failed to store substage as action event: {e}")
        elif event_type == "action":
            # Store action events in the database for flow console history
            action_data = event.get("data", {})
            action_id = event.get("action_id")
            
            if not action_data:
                log.error(f"[EventListener DB] No action data found in event: {event}")
                return
            
            try:
                from adare.database.api.event import EventDbApi
                from adare.types.event_types import event_type_resolver
                
                # Determine if this is a test event
                resolved_event_type = event_type_resolver.resolve_event_type(action_data)
                action_type = event_type_resolver.get_action_type(resolved_event_type)
                
                # Extract parent event ID from action data if present
                parent_event_id = action_data.get('parent_event_id')
                
                with EventDbApi() as api:
                    if action_type.value == 'test':
                        # Store test events as TestEvent for proper test section display
                        api.add_test_event(action_data, action_id, ulid, parent_event_id)
                        log.debug(f"[EventListener DB] Stored test event in database: {action_id}")
                    else:
                        # Store other actions as ActionEvent
                        api.add_action_event(action_data, action_id, ulid, parent_event_id)
                        log.debug(f"[EventListener DB] Stored action event in database: {action_id}")
            except Exception as e:
                log.error(f"[EventListener DB] Failed to store action event {action_id}: {e}", exc_info=True)
        else:
            log.warning(f"[EventListener DB] Unknown event type: {event_type}")