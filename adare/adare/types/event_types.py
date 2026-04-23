"""Event type definitions and registry for proper event handling."""

import logging
from enum import Enum
from typing import Any

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
    WAIT_UNTIL_START = "wait_until_start"
    WAIT_UNTIL_COMPLETE = "wait_until_complete"
    LOOP_START = "loop_start"
    LOOP_COMPLETE = "loop_complete"
    STOP_START = "stop_start"
    STOP_COMPLETE = "stop_complete"
    CONTINUE_START = "continue_start"
    CONTINUE_COMPLETE = "continue_complete"
    SNAPSHOT_FILESYSTEM_START = "snapshot_filesystem_start"
    SNAPSHOT_FILESYSTEM_COMPLETE = "snapshot_filesystem_complete"
    PULL_CHANGED_FILES_START = "pull_changed_files_start"
    PULL_CHANGED_FILES_COMPLETE = "pull_changed_files_complete"


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
    WAIT_UNTIL = "wait_until"
    LOOP = "loop"
    STOP = "stop"
    CONTINUE = "continue"
    SNAPSHOT_FILESYSTEM = "snapshot_filesystem"
    PULL_CHANGED_FILES = "pull_changed_files"

    # Internal step action types (not used in playbook YAML)
    FIND = "find"
    EXECUTE = "execute"


_ACTION_RAW_TO_EVENT: dict[str, tuple[EventType, EventType]] = {
    "click": (EventType.CLICK_START, EventType.CLICK_COMPLETE),
    "rightclick": (EventType.CLICK_START, EventType.CLICK_COMPLETE),
    "doubleclick": (EventType.CLICK_START, EventType.CLICK_COMPLETE),
    "keyboard": (EventType.KEYBOARD_START, EventType.KEYBOARD_COMPLETE),
    "command": (EventType.COMMAND_START, EventType.COMMAND_COMPLETE),
    "idle": (EventType.IDLE_START, EventType.IDLE_COMPLETE),
    "test": (EventType.TEST_START, EventType.TEST_COMPLETE),
    "screenshot": (EventType.SCREENSHOT_START, EventType.SCREENSHOT_COMPLETE),
    "scroll": (EventType.SCROLL_START, EventType.SCROLL_COMPLETE),
    "drag": (EventType.DRAG_START, EventType.DRAG_COMPLETE),
    "goto": (EventType.GOTO_START, EventType.GOTO_COMPLETE),
    "savetimestamp": (EventType.SAVETIMESTAMP_START, EventType.SAVETIMESTAMP_COMPLETE),
    "pull": (EventType.PULL_START, EventType.PULL_COMPLETE),
    "pause": (EventType.PAUSE_START, EventType.PAUSE_COMPLETE),
    "block": (EventType.BLOCK_START, EventType.BLOCK_COMPLETE),
    "waituntil": (EventType.WAIT_UNTIL_START, EventType.WAIT_UNTIL_COMPLETE),
    "loop": (EventType.LOOP_START, EventType.LOOP_COMPLETE),
    "stop": (EventType.STOP_START, EventType.STOP_COMPLETE),
    "continue": (EventType.CONTINUE_START, EventType.CONTINUE_COMPLETE),
    "snapshotfilesystem": (EventType.SNAPSHOT_FILESYSTEM_START, EventType.SNAPSHOT_FILESYSTEM_COMPLETE),
    "pullchangedfiles": (EventType.PULL_CHANGED_FILES_START, EventType.PULL_CHANGED_FILES_COMPLETE),
    "find": (EventType.ACTION_START, EventType.ACTION_COMPLETE),
    "execute": (EventType.ACTION_START, EventType.ACTION_COMPLETE),
}

# Ordered list of (prefix, ActionType) for get_action_type dispatch.
# Longer prefixes MUST come before shorter ones to avoid false matches
# (e.g. "pull_changed_files_" before "pull_", "snapshot_filesystem_" before "stop_").
_EVENT_PREFIX_TO_ACTION: list[tuple[str, ActionType]] = [
    ("snapshot_filesystem_", ActionType.SNAPSHOT_FILESYSTEM),
    ("pull_changed_files_", ActionType.PULL_CHANGED_FILES),
    ("wait_until_", ActionType.WAIT_UNTIL),
    ("screenshot_", ActionType.SCREENSHOT),
    ("savetimestamp_", ActionType.SAVETIMESTAMP),
    ("continue_", ActionType.CONTINUE),
    ("keyboard_", ActionType.KEYBOARD),
    ("command_", ActionType.COMMAND),
    ("scroll_", ActionType.SCROLL),
    ("click_", ActionType.CLICK),
    ("pause_", ActionType.PAUSE),
    ("block_", ActionType.BLOCK),
    ("idle_", ActionType.IDLE),
    ("test_", ActionType.TEST),
    ("drag_", ActionType.DRAG),
    ("goto_", ActionType.GOTO),
    ("loop_", ActionType.LOOP),
    ("stop_", ActionType.STOP),
    ("pull_", ActionType.PULL),
]


class EventTypeResolver:
    """Resolves event types from serialized data and provides type-safe event handling."""

    def __init__(self):
        # Map legacy class names to proper event types
        self._class_name_mapping: dict[str, EventType] = {
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
            "WaitUntilActionStartEvent": EventType.WAIT_UNTIL_START,
            "WaitUntilActionCompleteEvent": EventType.WAIT_UNTIL_COMPLETE,
            "LoopActionStartEvent": EventType.LOOP_START,
            "LoopActionCompleteEvent": EventType.LOOP_COMPLETE,
            "StopActionStartEvent": EventType.STOP_START,
            "StopActionCompleteEvent": EventType.STOP_COMPLETE,
            "ContinueActionStartEvent": EventType.CONTINUE_START,
            "ContinueActionCompleteEvent": EventType.CONTINUE_COMPLETE,
            "SnapshotFilesystemActionStartEvent": EventType.SNAPSHOT_FILESYSTEM_START,
            "SnapshotFilesystemActionCompleteEvent": EventType.SNAPSHOT_FILESYSTEM_COMPLETE,
            "PullChangedFilesActionStartEvent": EventType.PULL_CHANGED_FILES_START,
            "PullChangedFilesActionCompleteEvent": EventType.PULL_CHANGED_FILES_COMPLETE,
        }

    def resolve_event_type(self, event_data: dict[str, Any]) -> EventType:
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

    def _detect_event_type_from_patterns(self, event_data: dict[str, Any], class_name: str) -> EventType:
        """Fallback detection based on data patterns and class name hints."""

        # Check for success field to determine start vs complete
        has_success = "success" in event_data
        is_complete = has_success or "Complete" in class_name or class_name.endswith("Complete")

        # Extract action type from class name
        action_type_raw = class_name.replace("Event", "").replace("Action", "").replace("Start", "").replace("Complete", "").lower()

        # Dispatch via lookup table
        event_pair = _ACTION_RAW_TO_EVENT.get(action_type_raw)
        if event_pair is not None:
            return event_pair[1] if is_complete else event_pair[0]

        # Default fallback to generic action types
        log.warning(f"Could not determine specific event type for: {class_name}, defaulting to generic action")
        return EventType.ACTION_COMPLETE if is_complete else EventType.ACTION_START

    def get_action_type(self, event_type: EventType, action_data: dict[str, Any] = None) -> ActionType:
        """Extract action type from event type and optionally action data."""
        event_name = event_type.value

        # Dispatch via ordered prefix table
        for prefix, action_type in _EVENT_PREFIX_TO_ACTION:
            if event_name.startswith(prefix):
                return action_type

        # For generic action events, check the original action data
        if action_data:
            class_name = action_data.get("__class__", action_data.get("_type", ""))
            if "Find" in class_name:
                return ActionType.FIND
            if "Execute" in class_name:
                return ActionType.EXECUTE

        # Check for find/execute in event names directly
        event_name_lower = event_name.lower() if event_name else ""
        if "find" in event_name_lower:
            return ActionType.FIND
        if "execute" in event_name_lower:
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
