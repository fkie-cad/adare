"""Action event types for playbook execution tracking."""

from datetime import UTC, datetime
from typing import Any

import attrs
import cattrs

from adare.types.event_types import EventType
from adare.types.playbook import Target
from adarelib.constants import StatusEnum

# -------------------------------
# cattrs Converter Setup
# -------------------------------

converter = cattrs.Converter()

# Handle datetime → str and back
converter.register_unstructure_hook(datetime, lambda dt: dt.isoformat() if dt else None)
converter.register_structure_hook(datetime, lambda s, _: datetime.fromisoformat(s) if s else None)

# Handle StatusEnum → int and back
converter.register_unstructure_hook(StatusEnum, lambda e: int(e))
converter.register_structure_hook(StatusEnum, lambda i, _: StatusEnum(i))

# Handle Target → dict and back
converter.register_unstructure_hook(Target, lambda t: {
    'image': t.image,
    'text': t.text,
    'position': t.position,
    'strategy': converter.unstructure(t.strategy) if t.strategy else None
})
converter.register_structure_hook(Target, lambda d, _: Target(
    image=d.get('image'),
    text=d.get('text'),
    position=d.get('position'),
    strategy=converter.structure(d.get('strategy'), type(None)) if d.get('strategy') else None
))

# -------------------------------
# Base Action Event Classes
# -------------------------------

@attrs.define
class ActionEvent:
    """Base class for all action execution events."""

    # Action identification
    action_id: str
    action_description: str = ""
    sequence_order: int = 0

    # Execution timing
    timestamp: datetime = attrs.field(factory=lambda: datetime.now(UTC))

    # Execution context
    playbook_item_id: str | None = None
    experiment_run_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for event publishing."""
        data = converter.unstructure(self)
        # Add explicit event_type for proper deserialization
        data['event_type'] = self.get_event_type().value
        # Keep __class__ for backward compatibility during transition
        data['__class__'] = self.__class__.__name__
        return data

    def get_event_type(self) -> EventType:
        """Get the explicit event type for this action event."""
        # This should be overridden by subclasses
        return EventType.ACTION_START

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActionEvent":
        """Create from dictionary."""
        return converter.structure(data, cls)

    @property
    def action_type(self) -> str:
        """Get action type from class name."""
        return self.__class__.__name__.replace('Event', '').replace('Action', '').lower()


# -------------------------------
# Click Action Events
# -------------------------------

@attrs.define
class ActionStartEvent(ActionEvent):
    """Base class for action start events."""
    parent_event_id: str | None = None

    def get_event_type(self) -> EventType:
        return EventType.ACTION_START


@attrs.define
class ActionCompleteEvent(ActionEvent):
    """Base class for action completion events."""
    success: bool = False
    execution_time: float | None = None
    parent_event_id: str | None = None

    def get_event_type(self) -> EventType:
        return EventType.ACTION_COMPLETE


@attrs.define
class ClickActionStartEvent(ActionStartEvent):
    """Event for click action start."""
    target_info: dict[str, Any] | None = None

    def get_event_type(self) -> EventType:
        return EventType.CLICK_START


@attrs.define
class ClickActionCompleteEvent(ActionCompleteEvent):
    """Event for click action completion."""
    coordinates: tuple[int, int] | None = None
    target_info: dict[str, Any] | None = None

    def get_event_type(self) -> EventType:
        return EventType.CLICK_COMPLETE




# -------------------------------
# Keyboard Action Events
# -------------------------------

@attrs.define
class KeyboardActionStartEvent(ActionStartEvent):
    """Event for keyboard action start."""
    key: str | None = None           # Single key press (e.g., "enter")
    text: str | None = None          # Text input (e.g., "hello world")
    combination: list | None = None  # Key combo (e.g., ["ctrl", "c"])
    keys: str | None = None          # Legacy field for backward compatibility

    def get_event_type(self) -> EventType:
        return EventType.KEYBOARD_START


@attrs.define
class KeyboardActionCompleteEvent(ActionCompleteEvent):
    """Event for keyboard action completion."""
    key: str | None = None           # Single key press
    text: str | None = None          # Text input
    combination: list | None = None  # Key combo
    keys_sent: str | None = None     # Legacy field for backward compatibility

    def get_event_type(self) -> EventType:
        return EventType.KEYBOARD_COMPLETE


# -------------------------------
# Command Action Events
# -------------------------------

@attrs.define
class CommandActionStartEvent(ActionStartEvent):
    """Event for command action start."""
    command: str | None = None

    def get_event_type(self) -> EventType:
        return EventType.COMMAND_START


@attrs.define
class CommandActionCompleteEvent(ActionCompleteEvent):
    """Event for command action completion."""
    command_executed: str | None = None
    output: str | None = None
    return_code: int | None = None

    def get_event_type(self) -> EventType:
        return EventType.COMMAND_COMPLETE


# -------------------------------
# Test Action Events (Special handling)
# -------------------------------

@attrs.define
class TestActionStartEvent(ActionStartEvent):
    """Event for test action start."""
    test_name: str = ""

    def get_event_type(self) -> EventType:
        return EventType.TEST_START


@attrs.define
class TestActionCompleteEvent(ActionCompleteEvent):
    """Event for test action completion."""
    test_name: str = ""
    test_output: str | None = None
    result_category: str | None = None
    expect_to_fail: bool = False

    def get_event_type(self) -> EventType:
        return EventType.TEST_COMPLETE

    @property
    def status(self) -> StatusEnum:
        """Get appropriate status for test results."""
        if self.success:
            return StatusEnum.SUCCESS
        return StatusEnum.TEST_FAILED


# -------------------------------
# Block Action Events
# -------------------------------

@attrs.define
class BlockActionStartEvent(ActionStartEvent):
    """Event for block action start."""
    conditions: dict[str, Any] | None = None
    action_count: int = 0

    def get_event_type(self) -> EventType:
        return EventType.BLOCK_START


@attrs.define
class BlockActionCompleteEvent(ActionCompleteEvent):
    """Event for block action completion."""
    actions_executed: int = 0

    def get_event_type(self) -> EventType:
        return EventType.BLOCK_COMPLETE


# -------------------------------
# Other Action Events
# -------------------------------

@attrs.define
class ScreenshotActionStartEvent(ActionStartEvent):
    """Event for screenshot action start."""
    pass

    def get_event_type(self) -> EventType:
        return EventType.SCREENSHOT_START


@attrs.define
class ScreenshotActionCompleteEvent(ActionCompleteEvent):
    """Event for screenshot action completion."""
    screenshot_path: str | None = None

    def get_event_type(self) -> EventType:
        return EventType.SCREENSHOT_COMPLETE


@attrs.define
class ScrollActionStartEvent(ActionStartEvent):
    """Event for scroll action start."""
    direction: str | None = None
    amount: int | None = None

    def get_event_type(self) -> EventType:
        return EventType.SCROLL_START


@attrs.define
class ScrollActionCompleteEvent(ActionCompleteEvent):
    """Event for scroll action completion."""
    pass

    def get_event_type(self) -> EventType:
        return EventType.SCROLL_COMPLETE


@attrs.define
class IdleActionStartEvent(ActionStartEvent):
    """Event for idle action start."""
    duration: float | None = None

    def get_event_type(self) -> EventType:
        return EventType.IDLE_START


@attrs.define
class IdleActionCompleteEvent(ActionCompleteEvent):
    """Event for idle action completion."""
    actual_duration: float | None = None

    def get_event_type(self) -> EventType:
        return EventType.IDLE_COMPLETE


@attrs.define
class DragActionStartEvent(ActionStartEvent):
    """Event for drag action start."""
    source_target: dict[str, Any] | None = None
    dest_target: dict[str, Any] | None = None

    def get_event_type(self) -> EventType:
        return EventType.DRAG_START


@attrs.define
class DragActionCompleteEvent(ActionCompleteEvent):
    """Event for drag action completion."""
    source_coordinates: tuple[int, int] | None = None
    dest_coordinates: tuple[int, int] | None = None

    def get_event_type(self) -> EventType:
        return EventType.DRAG_COMPLETE


@attrs.define
class GotoActionStartEvent(ActionStartEvent):
    """Event for goto action start."""
    url: str | None = None

    def get_event_type(self) -> EventType:
        return EventType.GOTO_START


@attrs.define
class GotoActionCompleteEvent(ActionCompleteEvent):
    """Event for goto action completion."""
    final_url: str | None = None

    def get_event_type(self) -> EventType:
        return EventType.GOTO_COMPLETE


@attrs.define
class SaveTimestampActionStartEvent(ActionStartEvent):
    """Event for save timestamp action start."""
    variable: str | None = None

    def get_event_type(self) -> EventType:
        return EventType.SAVETIMESTAMP_START


@attrs.define
class SaveTimestampActionCompleteEvent(ActionCompleteEvent):
    """Event for save timestamp action completion."""
    variable: str | None = None
    timestamp_value: float | None = None

    def get_event_type(self) -> EventType:
        return EventType.SAVETIMESTAMP_COMPLETE


# -------------------------------
# Pull Action Events
# -------------------------------

@attrs.define
class PullActionStartEvent(ActionStartEvent):
    """Event for pull action start."""
    source: str | None = None
    destination: str | None = None

    def get_event_type(self) -> EventType:
        return EventType.PULL_START


@attrs.define
class PullActionCompleteEvent(ActionCompleteEvent):
    """Event for pull action completion."""
    source: str | None = None
    destination: str | None = None
    files_copied: int | None = None
    total_size: int | None = None

    def get_event_type(self) -> EventType:
        return EventType.PULL_COMPLETE


# -------------------------------
# Pause Action Events
# -------------------------------

@attrs.define
class PauseActionStartEvent(ActionStartEvent):
    """Event for pause action start."""
    message: str | None = None

    def get_event_type(self) -> EventType:
        return EventType.PAUSE_START


@attrs.define
class PauseActionCompleteEvent(ActionCompleteEvent):
    """Event for pause action completion."""
    user_input: str | None = None

    def get_event_type(self) -> EventType:
        return EventType.PAUSE_COMPLETE


# -------------------------------
# Wait Until Action Events
# -------------------------------

@attrs.define
class WaitUntilActionStartEvent(ActionStartEvent):
    """Event for wait until action start."""
    target_info: dict[str, Any] | None = None
    timeout: float | None = None
    check_interval: float | None = None
    initial_delay: float | None = None

    def get_event_type(self) -> EventType:
        return EventType.WAIT_UNTIL_START


@attrs.define
class WaitUntilActionCompleteEvent(ActionCompleteEvent):
    """Event for wait until action completion."""
    target_info: dict[str, Any] | None = None
    coordinates: tuple[int, int] | None = None
    found: bool = False

    def get_event_type(self) -> EventType:
        return EventType.WAIT_UNTIL_COMPLETE


# -------------------------------
# Loop Action Events
# -------------------------------

@attrs.define
class LoopActionStartEvent(ActionStartEvent):
    """Event for loop action start."""
    iteration_count: int | None = None
    items: list | None = None

    def get_event_type(self) -> EventType:
        return EventType.LOOP_START


@attrs.define
class LoopActionCompleteEvent(ActionCompleteEvent):
    """Event for loop action completion."""
    iterations_completed: int | None = None
    actions_executed: int | None = None

    def get_event_type(self) -> EventType:
        return EventType.LOOP_COMPLETE


# -------------------------------
# Stop Action Events
# -------------------------------

@attrs.define
class StopActionStartEvent(ActionStartEvent):
    """Event for stop action start."""
    condition_info: dict[str, Any] | None = None

    def get_event_type(self) -> EventType:
        return EventType.STOP_START


@attrs.define
class StopActionCompleteEvent(ActionCompleteEvent):
    """Event for stop action completion."""
    condition_met: bool | None = None
    stopped_execution: bool = False

    def get_event_type(self) -> EventType:
        return EventType.STOP_COMPLETE


# -------------------------------
# Continue Action Events
# -------------------------------

@attrs.define
class ContinueActionStartEvent(ActionStartEvent):
    """Event for continue action start."""
    condition_info: dict[str, Any] | None = None

    def get_event_type(self) -> EventType:
        return EventType.CONTINUE_START


@attrs.define
class ContinueActionCompleteEvent(ActionCompleteEvent):
    """Event for continue action completion."""
    condition_met: bool | None = None
    skipped_remaining: bool = False

    def get_event_type(self) -> EventType:
        return EventType.CONTINUE_COMPLETE


# -------------------------------
# Substage Action Events
# -------------------------------

@attrs.define
class FindActionStartEvent(ActionStartEvent):
    """Event for find substage start."""
    target_info: dict[str, Any] | None = None

    def get_event_type(self) -> EventType:
        return EventType.ACTION_START


@attrs.define
class FindActionCompleteEvent(ActionCompleteEvent):
    """Event for find substage completion."""
    target_info: dict[str, Any] | None = None
    coordinates: tuple[int, int] | None = None
    matched_text: str | None = None  # What OCR actually detected (for fuzzy/regex matching)

    def get_event_type(self) -> EventType:
        return EventType.ACTION_COMPLETE


@attrs.define
class ExecuteActionStartEvent(ActionStartEvent):
    """Event for execute substage start."""
    coordinates: tuple[int, int] | None = None

    def get_event_type(self) -> EventType:
        return EventType.ACTION_START


@attrs.define
class ExecuteActionCompleteEvent(ActionCompleteEvent):
    """Event for execute substage completion."""
    coordinates: tuple[int, int] | None = None

    def get_event_type(self) -> EventType:
        return EventType.ACTION_COMPLETE


# -------------------------------
# Snapshot Filesystem Action Events
# -------------------------------

@attrs.define
class SnapshotFilesystemActionStartEvent(ActionStartEvent):
    """Event for snapshot filesystem action start."""
    snapshot_type: str | None = None  # 'initial' or 'final'

    def get_event_type(self) -> EventType:
        return EventType.SNAPSHOT_FILESYSTEM_START


@attrs.define
class SnapshotFilesystemActionCompleteEvent(ActionCompleteEvent):
    """Event for snapshot filesystem action completion."""
    snapshot_type: str | None = None
    files_count: int | None = None

    def get_event_type(self) -> EventType:
        return EventType.SNAPSHOT_FILESYSTEM_COMPLETE


# -------------------------------
# Pull Changed Files Action Events
# -------------------------------

@attrs.define
class PullChangedFilesActionStartEvent(ActionStartEvent):
    """Event for pull changed files action start."""
    destination: str | None = None

    def get_event_type(self) -> EventType:
        return EventType.PULL_CHANGED_FILES_START


@attrs.define
class PullChangedFilesActionCompleteEvent(ActionCompleteEvent):
    """Event for pull changed files action completion."""
    destination: str | None = None
    files_pulled: int | None = None
    total_size: int | None = None

    def get_event_type(self) -> EventType:
        return EventType.PULL_CHANGED_FILES_COMPLETE
