from adare.backend.events.pubsub import subscribe_cli, subscribe_db
from adare.backend.experiment.print import flowconsolemanager
from adarelib.constants import StatusEnum
from adare.types.stages import Stage, _stage_registry
from adare.types.event_types import event_type_resolver, EventType, ActionType

import logging
import asyncio
import threading
import queue
import time
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger(__name__)

# Cache for stage hierarchy levels to avoid repeated calculations
_stage_level_cache = {}

# Thread pool for async database operations
_db_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="EventDB")

# Database operation queue for batching
_db_operation_queue = queue.Queue()
_db_batch_processor_running = False
_db_batch_lock = threading.Lock()

# UI spinner debouncing to prevent flash effects
_spinner_timers = {}  # stage_id -> timer
_spinner_lock = threading.Lock()
_MIN_SPINNER_DISPLAY_TIME = 0.1  # Minimum 100ms spinner display

# Import shared action display logic
from adare.frontend.terminal.action_display import get_action_display_info, determine_action_status, format_action_message


def _schedule_delayed_completion(stage_id: str, console, completion_callback, delay_ms: float = 100):
    """
    Schedule a delayed completion to ensure spinner stays visible for minimum time.

    Args:
        stage_id: Stage identifier
        console: Flow console instance
        completion_callback: Function to call for completion
        delay_ms: Delay in milliseconds
    """
    def delayed_complete():
        time.sleep(delay_ms / 1000.0)
        try:
            completion_callback()
        except Exception as e:
            log.error(f"Error in delayed completion for {stage_id}: {e}")
        finally:
            with _spinner_lock:
                _spinner_timers.pop(stage_id, None)

    # Cancel any existing timer for this stage
    with _spinner_lock:
        existing_timer = _spinner_timers.get(stage_id)
        if existing_timer and existing_timer.is_alive():
            # Don't cancel if already running, let it complete
            return

        timer = threading.Thread(target=delayed_complete, daemon=True)
        _spinner_timers[stage_id] = timer
        timer.start()


def _queue_db_operation(operation_type: str, **kwargs):
    """
    Queue a database operation for asynchronous processing.

    Args:
        operation_type: Type of operation ('stage_update', 'action_event', 'test_event')
        **kwargs: Operation-specific parameters
    """
    operation = {
        'type': operation_type,
        'data': kwargs,
        'timestamp': threading.current_thread().ident  # For debugging
    }

    try:
        _db_operation_queue.put_nowait(operation)
        _ensure_db_batch_processor()
    except queue.Full:
        log.warning(f"Database operation queue full, dropping {operation_type} operation")


def _ensure_db_batch_processor():
    """Ensure the database batch processor is running."""
    global _db_batch_processor_running

    with _db_batch_lock:
        if not _db_batch_processor_running:
            _db_batch_processor_running = True
            _db_executor.submit(_process_db_operations)


def _process_db_operations():
    """Process database operations in batches to improve performance."""
    global _db_batch_processor_running

    try:
        batch = []
        batch_timeout = 0.005  # 5ms batch timeout for good responsiveness

        while True:
            try:
                # Get operation with short timeout to allow batching
                operation = _db_operation_queue.get(timeout=batch_timeout)
                batch.append(operation)

                # Process batch when we hit a reasonable size or timeout
                if len(batch) >= 10:  # Process batches of 10 operations
                    _execute_db_batch(batch)
                    batch = []

            except queue.Empty:
                # Process any remaining operations in batch
                if batch:
                    _execute_db_batch(batch)
                    batch = []

                # Check if queue is truly empty before stopping
                if _db_operation_queue.empty():
                    break

    except Exception as e:
        log.error(f"Error in database batch processor: {e}", exc_info=True)
    finally:
        # Process any final operations
        if batch:
            _execute_db_batch(batch)

        with _db_batch_lock:
            _db_batch_processor_running = False


def _execute_db_batch(batch):
    """Execute a batch of database operations."""
    if not batch:
        return

    try:
        for operation in batch:
            operation_type = operation['type']
            data = operation['data']

            if operation_type == 'stage_update':
                from adare.backend.experiment.database import update_stage_in_run
                update_stage_in_run(
                    stage=data['stage'],
                    experimentrun_ulid=data['ulid'],
                    stage_id=data['stage_id']
                )

            elif operation_type == 'action_event':
                from adare.database.api.event import EventDbApi
                with EventDbApi() as api:
                    api.add_action_event(
                        data['action_data'],
                        data['action_id'],
                        data['ulid'],
                        data.get('parent_event_id')
                    )

            elif operation_type == 'test_event':
                from adare.database.api.event import EventDbApi
                with EventDbApi() as api:
                    api.add_test_event(
                        data['action_data'],
                        data['action_id'],
                        data['ulid'],
                        data.get('parent_event_id')
                    )

    except Exception as e:
        log.error(f"Error executing database batch: {e}", exc_info=True)


def _get_stage_level(stage_name: str) -> int:
    """
    Get the display level for a stage, using caching for performance.

    Args:
        stage_name: Name of the stage to get level for

    Returns:
        Integer level (0 for root stages, incrementing for child stages)
    """
    if stage_name in _stage_level_cache:
        return _stage_level_cache[stage_name]

    # Calculate level by traversing parent hierarchy
    level = 0
    current_stage_name = stage_name

    while current_stage_name:
        stage_class = _stage_registry.get(current_stage_name)
        if not stage_class:
            log.warning(f"[EventListener CLI] Stage {current_stage_name} not found in registry")
            break

        stage_instance = stage_class()
        parent = getattr(stage_instance, 'parent', None)

        if not parent:
            break

        level += 1
        current_stage_name = parent

        if level > 10:
            log.warning(f"[EventListener CLI] Level too high for stage {stage_name}, breaking loop: {level}")
            break

    # Cache the result for future use
    _stage_level_cache[stage_name] = level
    return level


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

    log.info("CLAUDE: Event listener optimized with stage hierarchy caching and async DB operations")
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

    # Performance tracking: log event processing time for optimization
    import time
    event_start_time = time.time()

    # Check stage status first
    finished = stage.start_time and stage.end_time
    in_progress = stage.start_time and not stage.end_time
    
    # Calculate display level using cached hierarchy lookup
    level = _get_stage_level(stage.name)
    
    if stage.sub_msg:
        message = f"{stage.msg}: {stage.sub_msg}"
    else:
        message = stage.msg

    if finished:
        # Calculate stage duration if both start and end times are available
        stage_duration = None
        if stage.start_time and stage.end_time:
            stage_duration = (stage.end_time - stage.start_time).total_seconds()

        # Calculate how long the spinner has been visible
        spinner_visible_time = 0
        if console.exists(stage_id):
            try:
                # Try to get when the spinner was created (this is approximate)
                spinner_visible_time = (event_end_time - event_start_time)
            except:
                spinner_visible_time = 0

        # Determine if we need to delay completion for better UX
        min_display_time_needed = max(0, _MIN_SPINNER_DISPLAY_TIME - spinner_visible_time)

        def complete_stage():
            if console.exists(stage_id):
                # Add interrupt indication for spinner updates
                if stage.status == StatusEnum.INTERRUPTED:
                    final_message = f"{message} (interrupted by user)"
                else:
                    final_message = message

                if stage.result_status and stage.result_status != StatusEnum.NONE:
                    console.log_spinner_done(identifier=stage_id, status=StatusEnum.FINISHED, message=final_message, result_status=stage.result_status, duration=stage_duration)
                else:
                    console.log_spinner_done(identifier=stage_id, status=stage.status, message=final_message, duration=stage_duration)
                log.debug(f"[EventListener CLI] Completed stage spinner for {ulid}: {stage.name}")
            else:
                # Handle stages that completed without ever showing a spinner
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

        # Apply debouncing for very short stages to prevent flashing
        if min_display_time_needed > 0.01 and console.exists(stage_id):  # Only for existing spinners
            log.debug(f"[EventListener CLI] Delaying completion of {stage.name} by {min_display_time_needed*1000:.1f}ms for better UX")
            _schedule_delayed_completion(stage_id, console, complete_stage, min_display_time_needed * 1000)
        else:
            # Complete immediately if spinner has been visible long enough
            complete_stage()
    elif in_progress:
        # Only add the stage if it doesn't already exist
        if not console.exists(stage_id):
            log.info(f"[EventListener CLI] Creating new console spinner for stage: {stage.name}, ID: {stage_id}, Level: {level}")
            console.log_spinner(identifier=stage_id, message=message, level=level, start_time=stage.start_time)
        else:
            log.info(f"[EventListener CLI] Stage already exists in console: {stage.name}, ID: {stage_id}")

    # Performance tracking: log total event processing time
    event_end_time = time.time()
    processing_time_ms = (event_end_time - event_start_time) * 1000
    log.debug(f"[EventListener CLI] Processed stage event for {ulid}: {stage.name if stage else 'None'} (processing: {processing_time_ms:.2f}ms)")


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
                              spinner='dots', spinner_style='bold blue', start_time=start_time)
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
        # Handle different event types with async database operations
        event_type = event.get("type", "stage")

        if event_type == "stage":
            stage = event.get("data", {})
            stage_id = event.get("stage_id")
            stage = Stage.from_dict(stage) if stage else None
            if not stage:
                log.error(f"[EventListener DB] No stage data found in event: {event}")
                return

            # Queue database operation for async processing
            _queue_db_operation(
                'stage_update',
                stage=stage,
                ulid=ulid,
                stage_id=stage_id
            )
            log.debug(f"[EventListener DB] Queued stage event for {ulid}: {stage.name if stage else 'None'}")

            # ALSO store action substages (find/execute) as action events for better integration
            if stage.name in ['action_find', 'action_execute']:
                # Convert stage to action event data
                action_data = {
                    'action_description': stage.description if hasattr(stage, 'description') else stage.msg,
                    'success': stage.status == 2,  # StatusEnum.SUCCESS = 2
                    'execution_time': None,  # Could calculate from start/end times if needed
                    'timestamp': stage.start_time.isoformat() if stage.start_time else None
                }

                _queue_db_operation(
                    'action_event',
                    action_data=action_data,
                    action_id=stage_id,
                    ulid=ulid
                )
                log.debug(f"[EventListener DB] Queued substage as action event: {stage.name}")

        elif event_type == "action":
            # Store action events in the database for flow console history
            action_data = event.get("data", {})
            action_id = event.get("action_id")

            if not action_data:
                log.error(f"[EventListener DB] No action data found in event: {event}")
                return

            try:
                from adare.types.event_types import event_type_resolver

                # Determine if this is a test event
                resolved_event_type = event_type_resolver.resolve_event_type(action_data)
                action_type = event_type_resolver.get_action_type(resolved_event_type)

                # Extract parent event ID from action data if present
                parent_event_id = action_data.get('parent_event_id')

                if action_type.value == 'test':
                    # Queue test event for async processing
                    _queue_db_operation(
                        'test_event',
                        action_data=action_data,
                        action_id=action_id,
                        ulid=ulid,
                        parent_event_id=parent_event_id
                    )
                    log.debug(f"[EventListener DB] Queued test event in database: {action_id}")
                else:
                    # Queue action event for async processing
                    _queue_db_operation(
                        'action_event',
                        action_data=action_data,
                        action_id=action_id,
                        ulid=ulid,
                        parent_event_id=parent_event_id
                    )
                    log.debug(f"[EventListener DB] Queued action event in database: {action_id}")
            except Exception as e:
                log.error(f"[EventListener DB] Failed to queue action event {action_id}: {e}", exc_info=True)
        else:
            log.warning(f"[EventListener DB] Unknown event type: {event_type}")