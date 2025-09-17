"""Event type definitions and registry for proper event handling."""

from enum import Enum
from typing import Dict, Type, Any, Optional
import logging

log = logging.getLogger(__name__)


class EventType(Enum):
    """Explicit event type enumeration."""
    
    # Stage events
    STAGE = "stage"
    
    # Action events - start/complete pairs
    ACTION_START = "action_start"
    ACTION_COMPLETE = "action_complete"
    
    # Specific action types
    CLICK_START = "click_start"
    CLICK_COMPLETE = "click_complete"
    KEYBOARD_START = "keyboard_start"
    KEYBOARD_COMPLETE = "keyboard_complete"
    COMMAND_START = "command_start"
    COMMAND_COMPLETE = "command_complete"
    IDLE_START = "idle_start"
    IDLE_COMPLETE = "idle_complete"
    TEST_START = "test_start"
    TEST_COMPLETE = "test_complete"
    SCREENSHOT_START = "screenshot_start"
    SCREENSHOT_COMPLETE = "screenshot_complete"
    SCROLL_START = "scroll_start"
    SCROLL_COMPLETE = "scroll_complete"
    DRAG_START = "drag_start"
    DRAG_COMPLETE = "drag_complete"
    GOTO_START = "goto_start"
    GOTO_COMPLETE = "goto_complete"
    SAVETIMESTAMP_START = "savetimestamp_start"
    SAVETIMESTAMP_COMPLETE = "savetimestamp_complete"
    PULL_START = "pull_start"
    PULL_COMPLETE = "pull_complete"
    PAUSE_START = "pause_start"
    PAUSE_COMPLETE = "pause_complete"
    BLOCK_START = "block_start"
    BLOCK_COMPLETE = "block_complete"


class ActionType(Enum):
    """Action type enumeration for cleaner categorization."""
    
    CLICK = "click"
    RIGHTCLICK = "rightclick"
    DOUBLECLICK = "doubleclick"
    KEYBOARD = "keyboard"
    COMMAND = "command"
    IDLE = "idle"
    TEST = "test"
    SCREENSHOT = "screenshot"
    SCROLL = "scroll"
    DRAG = "drag"
    GOTO = "goto"
    SAVETIMESTAMP = "savetimestamp"
    PULL = "pull"
    PAUSE = "pause"
    BLOCK = "block"
    
    # Internal step action types (not used in playbook YAML)
    FIND = "find"
    EXECUTE = "execute"


class EventTypeResolver:
    """Resolves event types from serialized data and provides type-safe event handling."""
    
    def __init__(self):
        # Map legacy class names to proper event types
        self._class_name_mapping: Dict[str, EventType] = {
            # Legacy class name patterns
            "ClickStartEvent": EventType.CLICK_START,
            "ClickCompleteEvent": EventType.CLICK_COMPLETE,
            "KeyboardStartEvent": EventType.KEYBOARD_START,
            "KeyboardCompleteEvent": EventType.KEYBOARD_COMPLETE,
            "CommandStartEvent": EventType.COMMAND_START,
            "CommandCompleteEvent": EventType.COMMAND_COMPLETE,
            "IdleStartEvent": EventType.IDLE_START,
            "IdleCompleteEvent": EventType.IDLE_COMPLETE,
            "TestStartEvent": EventType.TEST_START,
            "TestCompleteEvent": EventType.TEST_COMPLETE,
            "ScreenshotStartEvent": EventType.SCREENSHOT_START,
            "ScreenshotCompleteEvent": EventType.SCREENSHOT_COMPLETE,
            "ScrollStartEvent": EventType.SCROLL_START,
            "ScrollCompleteEvent": EventType.SCROLL_COMPLETE,
            "DragStartEvent": EventType.DRAG_START,
            "DragCompleteEvent": EventType.DRAG_COMPLETE,
            "GotoStartEvent": EventType.GOTO_START,
            "GotoCompleteEvent": EventType.GOTO_COMPLETE,
            "SavetimestampStartEvent": EventType.SAVETIMESTAMP_START,
            "SavetimestampCompleteEvent": EventType.SAVETIMESTAMP_COMPLETE,
            "PullActionStartEvent": EventType.PULL_START,
            "PullActionCompleteEvent": EventType.PULL_COMPLETE,
            "PauseActionStartEvent": EventType.PAUSE_START,
            "PauseActionCompleteEvent": EventType.PAUSE_COMPLETE,
            "BlockActionStartEvent": EventType.BLOCK_START,
            "BlockActionCompleteEvent": EventType.BLOCK_COMPLETE,
        }
    
    def resolve_event_type(self, event_data: Dict[str, Any]) -> EventType:
        """
        Resolve event type from event data.
        
        Priority:
        1. Explicit 'event_type' field (preferred)
        2. Legacy '__class__' field mapping
        3. Fallback detection based on data patterns
        """
        # First priority: explicit event_type field
        if "event_type" in event_data:
            try:
                return EventType(event_data["event_type"])
            except ValueError:
                log.warning(f"Unknown event_type: {event_data['event_type']}")
        
        # Second priority: legacy __class__ mapping
        class_name = event_data.get("__class__", event_data.get("_type", ""))
        if class_name in self._class_name_mapping:
            return self._class_name_mapping[class_name]
        
        # Third priority: pattern-based detection (fallback for legacy data)
        return self._detect_event_type_from_patterns(event_data, class_name)
    
    def _detect_event_type_from_patterns(self, event_data: Dict[str, Any], class_name: str) -> EventType:
        """Fallback detection based on data patterns and class name hints."""
        
        # Check for success field to determine start vs complete
        has_success = "success" in event_data
        is_complete = has_success or "Complete" in class_name or class_name.endswith("Complete")
        is_start = "Start" in class_name or class_name.endswith("Start") or not is_complete
        
        # Extract action type from class name
        action_type_raw = class_name.replace("Event", "").replace("Action", "").replace("Start", "").replace("Complete", "").lower()
        
        # Map to action types and determine event type
        if action_type_raw in ["click", "rightclick", "doubleclick"]:
            return EventType.CLICK_COMPLETE if is_complete else EventType.CLICK_START
        elif action_type_raw == "keyboard":
            return EventType.KEYBOARD_COMPLETE if is_complete else EventType.KEYBOARD_START
        elif action_type_raw == "command":
            return EventType.COMMAND_COMPLETE if is_complete else EventType.COMMAND_START
        elif action_type_raw == "idle":
            return EventType.IDLE_COMPLETE if is_complete else EventType.IDLE_START
        elif action_type_raw == "test":
            return EventType.TEST_COMPLETE if is_complete else EventType.TEST_START
        elif action_type_raw == "screenshot":
            return EventType.SCREENSHOT_COMPLETE if is_complete else EventType.SCREENSHOT_START
        elif action_type_raw == "scroll":
            return EventType.SCROLL_COMPLETE if is_complete else EventType.SCROLL_START
        elif action_type_raw == "drag":
            return EventType.DRAG_COMPLETE if is_complete else EventType.DRAG_START
        elif action_type_raw == "goto":
            return EventType.GOTO_COMPLETE if is_complete else EventType.GOTO_START
        elif action_type_raw == "savetimestamp":
            return EventType.SAVETIMESTAMP_COMPLETE if is_complete else EventType.SAVETIMESTAMP_START
        elif action_type_raw == "pull":
            return EventType.PULL_COMPLETE if is_complete else EventType.PULL_START
        elif action_type_raw == "pause":
            return EventType.PAUSE_COMPLETE if is_complete else EventType.PAUSE_START
        elif action_type_raw == "block":
            return EventType.BLOCK_COMPLETE if is_complete else EventType.BLOCK_START
        elif action_type_raw == "find":
            return EventType.ACTION_COMPLETE if is_complete else EventType.ACTION_START
        elif action_type_raw == "execute":
            return EventType.ACTION_COMPLETE if is_complete else EventType.ACTION_START
        
        # Default fallback to generic action types
        log.warning(f"Could not determine specific event type for: {class_name}, defaulting to generic action")
        return EventType.ACTION_COMPLETE if is_complete else EventType.ACTION_START
    
    def get_action_type(self, event_type: EventType, action_data: Dict[str, Any] = None) -> ActionType:
        """Extract action type from event type and optionally action data."""
        event_name = event_type.value
        
        if event_name.startswith("click_"):
            return ActionType.CLICK
        elif event_name.startswith("keyboard_"):
            return ActionType.KEYBOARD
        elif event_name.startswith("command_"):
            return ActionType.COMMAND
        elif event_name.startswith("idle_"):
            return ActionType.IDLE
        elif event_name.startswith("test_"):
            return ActionType.TEST
        elif event_name.startswith("screenshot_"):
            return ActionType.SCREENSHOT
        elif event_name.startswith("scroll_"):
            return ActionType.SCROLL
        elif event_name.startswith("drag_"):
            return ActionType.DRAG
        elif event_name.startswith("goto_"):
            return ActionType.GOTO
        elif event_name.startswith("savetimestamp_"):
            return ActionType.SAVETIMESTAMP
        elif event_name.startswith("pull_"):
            return ActionType.PULL
        elif event_name.startswith("pause_"):
            return ActionType.PAUSE
        elif event_name.startswith("block_"):
            return ActionType.BLOCK
        else:
            # For generic action events, check the original action data
            if action_data:
                class_name = action_data.get("__class__", action_data.get("_type", ""))
                if "Find" in class_name:
                    return ActionType.FIND
                elif "Execute" in class_name:
                    return ActionType.EXECUTE
            
            # Check for find/execute in event names directly
            event_name_lower = event_name.lower() if event_name else ""
            if "find" in event_name_lower:
                return ActionType.FIND
            elif "execute" in event_name_lower:
                return ActionType.EXECUTE
            
            # Fallback for generic action events
            return ActionType.CLICK  # Default fallback
    
    def is_start_event(self, event_type: EventType) -> bool:
        """Check if event type is a start event."""
        return event_type.value.endswith("_start") or event_type == EventType.ACTION_START
    
    def is_complete_event(self, event_type: EventType) -> bool:
        """Check if event type is a complete event."""
        return event_type.value.endswith("_complete") or event_type == EventType.ACTION_COMPLETE
    
    def resolve_event_type_from_name(self, event_type_name: str) -> EventType:
        """Resolve event type directly from event type name string."""
        try:
            return EventType(event_type_name)
        except ValueError:
            log.warning(f"Unknown event type name: {event_type_name}, defaulting to generic action")
            return EventType.ACTION_START


# Global resolver instance
event_type_resolver = EventTypeResolver()