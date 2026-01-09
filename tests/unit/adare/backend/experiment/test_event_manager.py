"""
Comprehensive unit tests for EventManager.

Tests cover:
- EventManager initialization
- create_action_start_event() - event creation for all action types
- create_action_complete_event() - event completion for all action types
- event type handling
- parent/child event relationships
- _get_target_info() helper method
- _get_condition_info() helper method
- _generate_command_description() helper method
- update_playbook_items_map() method
"""

import pytest
import sys
from unittest.mock import MagicMock, patch
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any

# Mock libvirt_qemu and libvirt before any imports that might need it
sys.modules['libvirt_qemu'] = MagicMock()
sys.modules['libvirt'] = MagicMock()

from adare.backend.experiment.event_manager import EventManager
from adare.types.playbook import (
    ClickAction,
    DragAction,
    KeyboardAction,
    IdleAction,
    ScrollAction,
    GotoAction,
    ScreenshotAction,
    CommandAction,
    SaveTimestampAction,
    PullAction,
    ActionTestAction,
    BlockAction,
    LoopAction,
    WaitUntilAction,
    WaitCondition,
    PauseAction,
    StopAction,
    ContinueAction,
    SnapshotFilesystemAction,
    PullChangedFilesAction,
    Target,
    VariableCondition,
    ExistsCondition,
)
from adare.types.step_actions import FindAction, ExecuteAction
from adare.types.actions import (
    ActionStartEvent, ActionCompleteEvent,
    ClickActionStartEvent, ClickActionCompleteEvent,
    KeyboardActionStartEvent, KeyboardActionCompleteEvent,
    CommandActionStartEvent, CommandActionCompleteEvent,
    TestActionStartEvent, TestActionCompleteEvent,
    ScreenshotActionStartEvent, ScreenshotActionCompleteEvent,
    ScrollActionStartEvent, ScrollActionCompleteEvent,
    IdleActionStartEvent, IdleActionCompleteEvent,
    DragActionStartEvent, DragActionCompleteEvent,
    GotoActionStartEvent, GotoActionCompleteEvent,
    BlockActionStartEvent, BlockActionCompleteEvent,
    SaveTimestampActionStartEvent, SaveTimestampActionCompleteEvent,
    PullActionStartEvent, PullActionCompleteEvent,
    WaitUntilActionStartEvent, WaitUntilActionCompleteEvent,
    LoopActionStartEvent, LoopActionCompleteEvent,
    PauseActionStartEvent, PauseActionCompleteEvent,
    StopActionStartEvent, StopActionCompleteEvent,
    ContinueActionStartEvent, ContinueActionCompleteEvent,
    FindActionStartEvent, FindActionCompleteEvent,
    ExecuteActionStartEvent, ExecuteActionCompleteEvent,
    SnapshotFilesystemActionStartEvent, SnapshotFilesystemActionCompleteEvent,
    PullChangedFilesActionStartEvent, PullChangedFilesActionCompleteEvent,
)


# ============================================================================
# Mock ActionResult dataclass for testing
# ============================================================================

@dataclass
class MockActionResult:
    """Mock ActionResult for testing create_action_complete_event."""
    success: bool
    message: str = ""
    coordinates: Optional[Tuple[int, int]] = None
    data: Optional[Dict[str, Any]] = None
    execution_time: Optional[float] = None


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def event_manager():
    """Create an EventManager with default settings."""
    return EventManager()


@pytest.fixture
def event_manager_with_context():
    """Create an EventManager with experiment context."""
    return EventManager(
        experiment_run_id="run-123",
        playbook_items_map={0: "item-0", 1: "item-1", 2: "item-2"}
    )


@pytest.fixture
def simple_target():
    """Create a simple target with position."""
    return Target(position=[100, 200])


@pytest.fixture
def image_target():
    """Create a target with image."""
    return Target(image="button.png")


@pytest.fixture
def text_target():
    """Create a target with text."""
    return Target(text="Click Me")


@pytest.fixture
def success_result():
    """Create a successful action result."""
    return MockActionResult(
        success=True,
        message="Action completed",
        coordinates=(150, 250),
        data={"output": "test output"},
        execution_time=1.5
    )


@pytest.fixture
def failure_result():
    """Create a failed action result."""
    return MockActionResult(
        success=False,
        message="Action failed",
        coordinates=None,
        data=None,
        execution_time=0.5
    )


# ============================================================================
# TestEventManagerInit
# ============================================================================


class TestEventManagerInit:
    """Tests for EventManager initialization."""

    def test_default_initialization(self):
        """EventManager should initialize with default values."""
        manager = EventManager()

        assert manager.experiment_run_id is None
        assert manager.playbook_items_map == {}

    def test_initialization_with_experiment_run_id(self):
        """EventManager should accept experiment_run_id."""
        manager = EventManager(experiment_run_id="run-456")

        assert manager.experiment_run_id == "run-456"
        assert manager.playbook_items_map == {}

    def test_initialization_with_playbook_items_map(self):
        """EventManager should accept playbook_items_map."""
        items_map = {0: "item-a", 1: "item-b"}
        manager = EventManager(playbook_items_map=items_map)

        assert manager.experiment_run_id is None
        assert manager.playbook_items_map == items_map

    def test_initialization_with_all_parameters(self):
        """EventManager should accept all parameters."""
        items_map = {0: "item-x", 1: "item-y", 2: "item-z"}
        manager = EventManager(
            experiment_run_id="run-789",
            playbook_items_map=items_map
        )

        assert manager.experiment_run_id == "run-789"
        assert manager.playbook_items_map == items_map

    def test_initialization_with_none_playbook_items_map(self):
        """EventManager should handle None playbook_items_map gracefully."""
        manager = EventManager(playbook_items_map=None)

        assert manager.playbook_items_map == {}


# ============================================================================
# TestUpdatePlaybookItemsMap
# ============================================================================


class TestUpdatePlaybookItemsMap:
    """Tests for update_playbook_items_map method."""

    def test_update_empty_map(self, event_manager):
        """update_playbook_items_map should update an empty map."""
        new_map = {0: "new-item-0", 1: "new-item-1"}
        event_manager.update_playbook_items_map(new_map)

        assert event_manager.playbook_items_map == new_map

    def test_update_replaces_existing_map(self, event_manager_with_context):
        """update_playbook_items_map should replace existing map."""
        new_map = {5: "item-5", 6: "item-6"}
        event_manager_with_context.update_playbook_items_map(new_map)

        assert event_manager_with_context.playbook_items_map == new_map
        assert 0 not in event_manager_with_context.playbook_items_map


# ============================================================================
# TestCreateActionStartEventClickAction
# ============================================================================


class TestCreateActionStartEventClickAction:
    """Tests for create_action_start_event with ClickAction."""

    def test_click_action_creates_click_start_event(self, event_manager, simple_target):
        """ClickAction should create ClickActionStartEvent."""
        action = ClickAction(target=simple_target, description="Test click")

        event = event_manager.create_action_start_event(
            action=action,
            action_index=0,
            action_id="action-001"
        )

        assert isinstance(event, ClickActionStartEvent)
        assert event.action_id == "action-001"
        assert event.action_description == "Test click"
        assert event.sequence_order == 0

    def test_click_action_includes_target_info(self, event_manager, image_target):
        """ClickAction start event should include target info."""
        action = ClickAction(target=image_target, description="Click image")

        event = event_manager.create_action_start_event(
            action=action,
            action_index=0,
            action_id="action-001"
        )

        assert event.target_info is not None
        assert event.target_info.get('image') == "button.png"

    def test_click_action_with_parent_event_id(self, event_manager, simple_target):
        """ClickAction start event should include parent_event_id."""
        action = ClickAction(target=simple_target, description="Nested click")

        event = event_manager.create_action_start_event(
            action=action,
            action_index=1,
            action_id="action-002",
            parent_event_id="parent-001"
        )

        assert event.parent_event_id == "parent-001"

    def test_click_action_with_context(self, event_manager_with_context, simple_target):
        """ClickAction start event should include experiment context."""
        action = ClickAction(target=simple_target, description="Context click")

        event = event_manager_with_context.create_action_start_event(
            action=action,
            action_index=1,
            action_id="action-003"
        )

        assert event.experiment_run_id == "run-123"
        assert event.playbook_item_id == "item-1"


# ============================================================================
# TestCreateActionStartEventKeyboardAction
# ============================================================================


class TestCreateActionStartEventKeyboardAction:
    """Tests for create_action_start_event with KeyboardAction."""

    def test_keyboard_action_creates_keyboard_start_event(self, event_manager):
        """KeyboardAction should create KeyboardActionStartEvent."""
        action = KeyboardAction(text="hello world", description="Type text")

        event = event_manager.create_action_start_event(
            action=action,
            action_index=0,
            action_id="action-001"
        )

        assert isinstance(event, KeyboardActionStartEvent)
        assert event.action_id == "action-001"
        assert event.action_description == "Type text"

    def test_keyboard_action_with_key(self, event_manager):
        """KeyboardAction with key should include keys info."""
        action = KeyboardAction(key="enter", description="Press enter")

        event = event_manager.create_action_start_event(
            action=action,
            action_index=0,
            action_id="action-001"
        )

        assert isinstance(event, KeyboardActionStartEvent)


# ============================================================================
# TestCreateActionStartEventCommandAction
# ============================================================================


class TestCreateActionStartEventCommandAction:
    """Tests for create_action_start_event with CommandAction."""

    def test_command_action_creates_command_start_event(self, event_manager):
        """CommandAction should create CommandActionStartEvent."""
        action = CommandAction(command="echo hello", description="Echo command")

        event = event_manager.create_action_start_event(
            action=action,
            action_index=0,
            action_id="action-001"
        )

        assert isinstance(event, CommandActionStartEvent)
        assert event.command == "echo hello"

    def test_command_action_generates_description(self, event_manager):
        """CommandAction should generate description from command."""
        action = CommandAction(command="ls -la /tmp")

        event = event_manager.create_action_start_event(
            action=action,
            action_index=0,
            action_id="action-001"
        )

        assert "command:" in event.action_description.lower()

    def test_command_action_truncates_long_command(self, event_manager):
        """CommandAction should truncate long command in description."""
        long_command = "a" * 100
        action = CommandAction(command=long_command)

        event = event_manager.create_action_start_event(
            action=action,
            action_index=0,
            action_id="action-001"
        )

        assert "..." in event.action_description
        assert len(event.action_description) < 100


# ============================================================================
# TestCreateActionStartEventIdleAction
# ============================================================================


class TestCreateActionStartEventIdleAction:
    """Tests for create_action_start_event with IdleAction."""

    def test_idle_action_creates_idle_start_event(self, event_manager):
        """IdleAction should create IdleActionStartEvent."""
        action = IdleAction(duration=2.5, description="Wait 2.5 seconds")

        event = event_manager.create_action_start_event(
            action=action,
            action_index=0,
            action_id="action-001"
        )

        assert isinstance(event, IdleActionStartEvent)
        assert event.duration == 2.5
        assert event.action_description == "Wait 2.5 seconds"


# ============================================================================
# TestCreateActionStartEventScrollAction
# ============================================================================


class TestCreateActionStartEventScrollAction:
    """Tests for create_action_start_event with ScrollAction."""

    def test_scroll_action_creates_scroll_start_event(self, event_manager):
        """ScrollAction should create ScrollActionStartEvent."""
        action = ScrollAction(direction="down", amount=3, description="Scroll down")

        event = event_manager.create_action_start_event(
            action=action,
            action_index=0,
            action_id="action-001"
        )

        assert isinstance(event, ScrollActionStartEvent)
        assert event.direction == "down"
        assert event.amount == 3


# ============================================================================
# TestCreateActionStartEventDragAction
# ============================================================================


class TestCreateActionStartEventDragAction:
    """Tests for create_action_start_event with DragAction."""

    def test_drag_action_creates_drag_start_event(self, event_manager, simple_target):
        """DragAction should create DragActionStartEvent."""
        src_target = Target(position=[100, 100])
        dst_target = Target(position=[200, 200])
        action = DragAction(src=src_target, dst=dst_target, description="Drag item")

        event = event_manager.create_action_start_event(
            action=action,
            action_index=0,
            action_id="action-001"
        )

        assert isinstance(event, DragActionStartEvent)
        assert event.source_target is not None
        assert event.dest_target is not None


# ============================================================================
# TestCreateActionStartEventGotoAction
# ============================================================================


class TestCreateActionStartEventGotoAction:
    """Tests for create_action_start_event with GotoAction."""

    def test_goto_action_creates_goto_start_event(self, event_manager, simple_target):
        """GotoAction should create GotoActionStartEvent."""
        action = GotoAction(target=simple_target, description="Go to position")

        event = event_manager.create_action_start_event(
            action=action,
            action_index=0,
            action_id="action-001"
        )

        assert isinstance(event, GotoActionStartEvent)


# ============================================================================
# TestCreateActionStartEventScreenshotAction
# ============================================================================


class TestCreateActionStartEventScreenshotAction:
    """Tests for create_action_start_event with ScreenshotAction."""

    def test_screenshot_action_creates_screenshot_start_event(self, event_manager):
        """ScreenshotAction should create ScreenshotActionStartEvent."""
        action = ScreenshotAction(description="Take screenshot", name="test_screenshot")

        event = event_manager.create_action_start_event(
            action=action,
            action_index=0,
            action_id="action-001"
        )

        assert isinstance(event, ScreenshotActionStartEvent)
        assert event.action_description == "Take screenshot"


# ============================================================================
# TestCreateActionStartEventBlockAction
# ============================================================================


class TestCreateActionStartEventBlockAction:
    """Tests for create_action_start_event with BlockAction."""

    def test_block_action_creates_block_start_event(self, event_manager):
        """BlockAction should create BlockActionStartEvent."""
        action = BlockAction(
            actions=[IdleAction(duration=1.0)],
            description="Test block"
        )

        event = event_manager.create_action_start_event(
            action=action,
            action_index=0,
            action_id="action-001"
        )

        assert isinstance(event, BlockActionStartEvent)
        assert event.action_count == 1

    def test_block_action_with_conditions(self, event_manager, text_target):
        """BlockAction with when conditions should include conditions info."""
        action = BlockAction(
            actions=[IdleAction(duration=1.0)],
            when=[ExistsCondition(text="Ready")],
            description="Conditional block"
        )

        event = event_manager.create_action_start_event(
            action=action,
            action_index=0,
            action_id="action-001"
        )

        assert isinstance(event, BlockActionStartEvent)
        assert event.conditions is not None


# ============================================================================
# TestCreateActionStartEventLoopAction
# ============================================================================


class TestCreateActionStartEventLoopAction:
    """Tests for create_action_start_event with LoopAction."""

    def test_loop_action_with_times_creates_loop_start_event(self, event_manager):
        """LoopAction with times should create LoopActionStartEvent."""
        action = LoopAction(
            actions=[IdleAction(duration=0.5)],
            times=5,
            description="Loop 5 times"
        )

        event = event_manager.create_action_start_event(
            action=action,
            action_index=0,
            action_id="action-001"
        )

        assert isinstance(event, LoopActionStartEvent)
        assert event.iteration_count == 5

    def test_loop_action_with_items_creates_loop_start_event(self, event_manager):
        """LoopAction with items should create LoopActionStartEvent."""
        action = LoopAction(
            actions=[IdleAction(duration=0.5)],
            items=["a", "b", "c"],
            description="Loop over items"
        )

        event = event_manager.create_action_start_event(
            action=action,
            action_index=0,
            action_id="action-001"
        )

        assert isinstance(event, LoopActionStartEvent)
        assert event.iteration_count == 3
        assert event.items == ["a", "b", "c"]


# ============================================================================
# TestCreateActionStartEventWaitUntilAction
# ============================================================================


class TestCreateActionStartEventWaitUntilAction:
    """Tests for create_action_start_event with WaitUntilAction."""

    def test_wait_until_action_with_exists_condition(self, event_manager, text_target):
        """WaitUntilAction with exists condition should create WaitUntilActionStartEvent."""
        action = WaitUntilAction(
            condition=WaitCondition(exists=text_target),
            timeout=30.0,
            description="Wait for text"
        )

        event = event_manager.create_action_start_event(
            action=action,
            action_index=0,
            action_id="action-001"
        )

        assert isinstance(event, WaitUntilActionStartEvent)
        assert event.timeout == 30.0
        assert event.target_info is not None

    def test_wait_until_action_with_not_exists_condition(self, event_manager, text_target):
        """WaitUntilAction with not_exists condition should create WaitUntilActionStartEvent."""
        action = WaitUntilAction(
            condition=WaitCondition(not_exists=text_target),
            timeout=15.0,
            description="Wait for text to disappear"
        )

        event = event_manager.create_action_start_event(
            action=action,
            action_index=0,
            action_id="action-001"
        )

        assert isinstance(event, WaitUntilActionStartEvent)
        assert event.timeout == 15.0


# ============================================================================
# TestCreateActionStartEventPauseAction
# ============================================================================


class TestCreateActionStartEventPauseAction:
    """Tests for create_action_start_event with PauseAction."""

    def test_pause_action_creates_pause_start_event(self, event_manager):
        """PauseAction should create PauseActionStartEvent."""
        action = PauseAction(message="Debug pause", description="Pause execution")

        event = event_manager.create_action_start_event(
            action=action,
            action_index=0,
            action_id="action-001"
        )

        assert isinstance(event, PauseActionStartEvent)
        assert event.message == "Debug pause"


# ============================================================================
# TestCreateActionStartEventStopAction
# ============================================================================


class TestCreateActionStartEventStopAction:
    """Tests for create_action_start_event with StopAction."""

    def test_stop_action_creates_stop_start_event(self, event_manager):
        """StopAction should create StopActionStartEvent."""
        action = StopAction(description="Stop execution")

        event = event_manager.create_action_start_event(
            action=action,
            action_index=0,
            action_id="action-001"
        )

        assert isinstance(event, StopActionStartEvent)

    def test_stop_action_with_condition(self, event_manager):
        """StopAction with condition should include condition info."""
        action = StopAction(
            condition=VariableCondition(variable="counter", equals=10),
            description="Stop when counter is 10"
        )

        event = event_manager.create_action_start_event(
            action=action,
            action_index=0,
            action_id="action-001"
        )

        assert isinstance(event, StopActionStartEvent)
        assert event.condition_info is not None
        assert event.condition_info['variable'] == "counter"
        assert event.condition_info['has_condition'] is True


# ============================================================================
# TestCreateActionStartEventContinueAction
# ============================================================================


class TestCreateActionStartEventContinueAction:
    """Tests for create_action_start_event with ContinueAction."""

    def test_continue_action_creates_continue_start_event(self, event_manager):
        """ContinueAction should create ContinueActionStartEvent."""
        action = ContinueAction(description="Continue to next iteration")

        event = event_manager.create_action_start_event(
            action=action,
            action_index=0,
            action_id="action-001"
        )

        assert isinstance(event, ContinueActionStartEvent)

    def test_continue_action_with_condition(self, event_manager):
        """ContinueAction with condition should include condition info."""
        action = ContinueAction(
            condition=VariableCondition(variable="skip_flag", equals=True),
            description="Continue if skip flag is true"
        )

        event = event_manager.create_action_start_event(
            action=action,
            action_index=0,
            action_id="action-001"
        )

        assert isinstance(event, ContinueActionStartEvent)
        assert event.condition_info is not None


# ============================================================================
# TestCreateActionStartEventTestAction
# ============================================================================


class TestCreateActionStartEventTestAction:
    """Tests for create_action_start_event with ActionTestAction."""

    def test_test_action_creates_test_start_event(self, event_manager):
        """ActionTestAction should create TestActionStartEvent."""
        action = ActionTestAction(name="test_file_exists", description="Test file exists")

        event = event_manager.create_action_start_event(
            action=action,
            action_index=0,
            action_id="action-001"
        )

        assert isinstance(event, TestActionStartEvent)
        assert event.test_name == "test_file_exists"


# ============================================================================
# TestCreateActionStartEventSaveTimestampAction
# ============================================================================


class TestCreateActionStartEventSaveTimestampAction:
    """Tests for create_action_start_event with SaveTimestampAction."""

    def test_save_timestamp_action_creates_save_timestamp_start_event(self, event_manager):
        """SaveTimestampAction should create SaveTimestampActionStartEvent."""
        action = SaveTimestampAction(variable="my_timestamp", description="Save timestamp")

        event = event_manager.create_action_start_event(
            action=action,
            action_index=0,
            action_id="action-001"
        )

        assert isinstance(event, SaveTimestampActionStartEvent)
        assert event.variable == "my_timestamp"


# ============================================================================
# TestCreateActionStartEventPullAction
# ============================================================================


class TestCreateActionStartEventPullAction:
    """Tests for create_action_start_event with PullAction."""

    def test_pull_action_creates_pull_start_event(self, event_manager):
        """PullAction should create PullActionStartEvent."""
        action = PullAction(src="/path/to/file", dst="local_file", description="Pull file")

        event = event_manager.create_action_start_event(
            action=action,
            action_index=0,
            action_id="action-001"
        )

        assert isinstance(event, PullActionStartEvent)
        assert event.source == "/path/to/file"
        assert event.destination == "local_file"


# ============================================================================
# TestCreateActionStartEventSnapshotFilesystemAction
# ============================================================================


class TestCreateActionStartEventSnapshotFilesystemAction:
    """Tests for create_action_start_event with SnapshotFilesystemAction."""

    def test_snapshot_filesystem_creates_snapshot_start_event(self, event_manager):
        """SnapshotFilesystemAction should create SnapshotFilesystemActionStartEvent."""
        action = SnapshotFilesystemAction(variable="fs_snap", description="Snapshot filesystem")

        event = event_manager.create_action_start_event(
            action=action,
            action_index=0,
            action_id="action-001"
        )

        assert isinstance(event, SnapshotFilesystemActionStartEvent)


# ============================================================================
# TestCreateActionStartEventPullChangedFilesAction
# ============================================================================


class TestCreateActionStartEventPullChangedFilesAction:
    """Tests for create_action_start_event with PullChangedFilesAction."""

    def test_pull_changed_files_creates_pull_changed_start_event(self, event_manager):
        """PullChangedFilesAction should create PullChangedFilesActionStartEvent."""
        action = PullChangedFilesAction(
            snapshot_before="snap_before",
            snapshot_after="snap_after",
            description="Pull changed files"
        )

        event = event_manager.create_action_start_event(
            action=action,
            action_index=0,
            action_id="action-001"
        )

        assert isinstance(event, PullChangedFilesActionStartEvent)


# ============================================================================
# TestCreateActionStartEventFindAction
# ============================================================================


class TestCreateActionStartEventFindAction:
    """Tests for create_action_start_event with FindAction."""

    def test_find_action_creates_find_start_event(self, event_manager):
        """FindAction should create FindActionStartEvent."""
        action = FindAction(description="Find target", target_info={"image": "button.png"})

        event = event_manager.create_action_start_event(
            action=action,
            action_index=0,
            action_id="action-001"
        )

        assert isinstance(event, FindActionStartEvent)
        assert event.target_info == {"image": "button.png"}


# ============================================================================
# TestCreateActionStartEventExecuteAction
# ============================================================================


class TestCreateActionStartEventExecuteAction:
    """Tests for create_action_start_event with ExecuteAction."""

    def test_execute_action_creates_execute_start_event(self, event_manager):
        """ExecuteAction should create ExecuteActionStartEvent."""
        action = ExecuteAction(description="Execute at coords", coordinates=(100, 200))

        event = event_manager.create_action_start_event(
            action=action,
            action_index=0,
            action_id="action-001"
        )

        assert isinstance(event, ExecuteActionStartEvent)
        assert event.coordinates == (100, 200)


# ============================================================================
# TestCreateActionStartEventUnknownAction
# ============================================================================


class TestCreateActionStartEventUnknownAction:
    """Tests for create_action_start_event with unknown action types."""

    def test_unknown_action_creates_generic_start_event(self, event_manager):
        """Unknown action type should create generic ActionStartEvent."""
        class UnknownAction:
            description = "Unknown action type"

        action = UnknownAction()

        event = event_manager.create_action_start_event(
            action=action,
            action_index=0,
            action_id="action-001"
        )

        assert isinstance(event, ActionStartEvent)
        assert event.action_id == "action-001"


# ============================================================================
# TestCreateActionCompleteEventClickAction
# ============================================================================


class TestCreateActionCompleteEventClickAction:
    """Tests for create_action_complete_event with ClickAction."""

    def test_click_action_creates_click_complete_event(self, event_manager, simple_target, success_result):
        """ClickAction should create ClickActionCompleteEvent."""
        action = ClickAction(target=simple_target, description="Test click")

        event = event_manager.create_action_complete_event(
            action=action,
            action_index=0,
            action_id="action-001",
            result=success_result
        )

        assert isinstance(event, ClickActionCompleteEvent)
        assert event.success is True
        assert event.coordinates == (150, 250)
        assert event.execution_time == 1.5

    def test_click_action_complete_with_failure(self, event_manager, simple_target, failure_result):
        """ClickAction complete event should handle failure."""
        action = ClickAction(target=simple_target, description="Failed click")

        event = event_manager.create_action_complete_event(
            action=action,
            action_index=0,
            action_id="action-001",
            result=failure_result
        )

        assert isinstance(event, ClickActionCompleteEvent)
        assert event.success is False

    def test_click_action_complete_with_parent_event_id(self, event_manager, simple_target, success_result):
        """ClickAction complete event should include parent_event_id."""
        action = ClickAction(target=simple_target, description="Nested click")

        event = event_manager.create_action_complete_event(
            action=action,
            action_index=0,
            action_id="action-001",
            result=success_result,
            parent_event_id="parent-001"
        )

        assert event.parent_event_id == "parent-001"


# ============================================================================
# TestCreateActionCompleteEventKeyboardAction
# ============================================================================


class TestCreateActionCompleteEventKeyboardAction:
    """Tests for create_action_complete_event with KeyboardAction."""

    def test_keyboard_action_creates_keyboard_complete_event(self, event_manager, success_result):
        """KeyboardAction should create KeyboardActionCompleteEvent."""
        action = KeyboardAction(text="hello", description="Type text")

        event = event_manager.create_action_complete_event(
            action=action,
            action_index=0,
            action_id="action-001",
            result=success_result
        )

        assert isinstance(event, KeyboardActionCompleteEvent)
        assert event.success is True


# ============================================================================
# TestCreateActionCompleteEventCommandAction
# ============================================================================


class TestCreateActionCompleteEventCommandAction:
    """Tests for create_action_complete_event with CommandAction."""

    def test_command_action_creates_command_complete_event(self, event_manager):
        """CommandAction should create CommandActionCompleteEvent."""
        action = CommandAction(command="echo hello", description="Echo command")
        result = MockActionResult(
            success=True,
            data={"output": "hello\n", "return_code": 0},
            execution_time=0.1
        )

        event = event_manager.create_action_complete_event(
            action=action,
            action_index=0,
            action_id="action-001",
            result=result
        )

        assert isinstance(event, CommandActionCompleteEvent)
        assert event.command_executed == "echo hello"
        assert event.output == "hello\n"
        assert event.return_code == 0


# ============================================================================
# TestCreateActionCompleteEventIdleAction
# ============================================================================


class TestCreateActionCompleteEventIdleAction:
    """Tests for create_action_complete_event with IdleAction."""

    def test_idle_action_creates_idle_complete_event(self, event_manager, success_result):
        """IdleAction should create IdleActionCompleteEvent."""
        action = IdleAction(duration=2.0, description="Wait")

        event = event_manager.create_action_complete_event(
            action=action,
            action_index=0,
            action_id="action-001",
            result=success_result
        )

        assert isinstance(event, IdleActionCompleteEvent)
        assert event.actual_duration == 1.5  # from execution_time


# ============================================================================
# TestCreateActionCompleteEventScrollAction
# ============================================================================


class TestCreateActionCompleteEventScrollAction:
    """Tests for create_action_complete_event with ScrollAction."""

    def test_scroll_action_creates_scroll_complete_event(self, event_manager, success_result):
        """ScrollAction should create ScrollActionCompleteEvent."""
        action = ScrollAction(direction="up", amount=5, description="Scroll up")

        event = event_manager.create_action_complete_event(
            action=action,
            action_index=0,
            action_id="action-001",
            result=success_result
        )

        assert isinstance(event, ScrollActionCompleteEvent)


# ============================================================================
# TestCreateActionCompleteEventDragAction
# ============================================================================


class TestCreateActionCompleteEventDragAction:
    """Tests for create_action_complete_event with DragAction."""

    def test_drag_action_creates_drag_complete_event(self, event_manager):
        """DragAction should create DragActionCompleteEvent."""
        src_target = Target(position=[100, 100])
        dst_target = Target(position=[200, 200])
        action = DragAction(src=src_target, dst=dst_target, description="Drag")
        result = MockActionResult(
            success=True,
            coordinates=(200, 200),
            data={"source_coordinates": (100, 100)},
            execution_time=0.5
        )

        event = event_manager.create_action_complete_event(
            action=action,
            action_index=0,
            action_id="action-001",
            result=result
        )

        assert isinstance(event, DragActionCompleteEvent)
        assert event.source_coordinates == (100, 100)
        assert event.dest_coordinates == (200, 200)


# ============================================================================
# TestCreateActionCompleteEventGotoAction
# ============================================================================


class TestCreateActionCompleteEventGotoAction:
    """Tests for create_action_complete_event with GotoAction."""

    def test_goto_action_creates_goto_complete_event(self, event_manager, simple_target):
        """GotoAction should create GotoActionCompleteEvent."""
        action = GotoAction(target=simple_target, description="Go to")
        result = MockActionResult(
            success=True,
            data={"final_url": "https://example.com"},
            execution_time=0.3
        )

        event = event_manager.create_action_complete_event(
            action=action,
            action_index=0,
            action_id="action-001",
            result=result
        )

        assert isinstance(event, GotoActionCompleteEvent)
        assert event.final_url == "https://example.com"


# ============================================================================
# TestCreateActionCompleteEventScreenshotAction
# ============================================================================


class TestCreateActionCompleteEventScreenshotAction:
    """Tests for create_action_complete_event with ScreenshotAction."""

    def test_screenshot_action_creates_screenshot_complete_event(self, event_manager):
        """ScreenshotAction should create ScreenshotActionCompleteEvent."""
        action = ScreenshotAction(description="Take screenshot")
        result = MockActionResult(
            success=True,
            data={"screenshot_path": "/tmp/screenshot.png"},
            execution_time=0.2
        )

        event = event_manager.create_action_complete_event(
            action=action,
            action_index=0,
            action_id="action-001",
            result=result
        )

        assert isinstance(event, ScreenshotActionCompleteEvent)
        assert event.screenshot_path == "/tmp/screenshot.png"


# ============================================================================
# TestCreateActionCompleteEventBlockAction
# ============================================================================


class TestCreateActionCompleteEventBlockAction:
    """Tests for create_action_complete_event with BlockAction."""

    def test_block_action_creates_block_complete_event(self, event_manager):
        """BlockAction should create BlockActionCompleteEvent."""
        action = BlockAction(actions=[IdleAction(duration=1.0)], description="Block")
        result = MockActionResult(
            success=True,
            data={"actions_executed": 3},
            execution_time=1.5
        )

        event = event_manager.create_action_complete_event(
            action=action,
            action_index=0,
            action_id="action-001",
            result=result
        )

        assert isinstance(event, BlockActionCompleteEvent)
        assert event.actions_executed == 3


# ============================================================================
# TestCreateActionCompleteEventLoopAction
# ============================================================================


class TestCreateActionCompleteEventLoopAction:
    """Tests for create_action_complete_event with LoopAction."""

    def test_loop_action_creates_loop_complete_event(self, event_manager):
        """LoopAction should create LoopActionCompleteEvent."""
        action = LoopAction(actions=[IdleAction(duration=0.5)], times=3, description="Loop")
        result = MockActionResult(
            success=True,
            data={"iterations": 3, "actions_executed": 9},
            execution_time=4.5
        )

        event = event_manager.create_action_complete_event(
            action=action,
            action_index=0,
            action_id="action-001",
            result=result
        )

        assert isinstance(event, LoopActionCompleteEvent)
        assert event.iterations_completed == 3
        assert event.actions_executed == 9


# ============================================================================
# TestCreateActionCompleteEventWaitUntilAction
# ============================================================================


class TestCreateActionCompleteEventWaitUntilAction:
    """Tests for create_action_complete_event with WaitUntilAction."""

    def test_wait_until_action_creates_wait_until_complete_event(self, event_manager, text_target):
        """WaitUntilAction should create WaitUntilActionCompleteEvent."""
        action = WaitUntilAction(
            condition=WaitCondition(exists=text_target),
            timeout=30.0,
            description="Wait for text"
        )
        result = MockActionResult(
            success=True,
            coordinates=(100, 150),
            execution_time=5.2
        )

        event = event_manager.create_action_complete_event(
            action=action,
            action_index=0,
            action_id="action-001",
            result=result
        )

        assert isinstance(event, WaitUntilActionCompleteEvent)
        assert event.found is True
        assert event.coordinates == (100, 150)


# ============================================================================
# TestCreateActionCompleteEventPauseAction
# ============================================================================


class TestCreateActionCompleteEventPauseAction:
    """Tests for create_action_complete_event with PauseAction."""

    def test_pause_action_creates_pause_complete_event(self, event_manager):
        """PauseAction should create PauseActionCompleteEvent."""
        action = PauseAction(message="Debug pause", description="Pause")
        result = MockActionResult(
            success=True,
            data={"user_input": "continue"},
            execution_time=10.0
        )

        event = event_manager.create_action_complete_event(
            action=action,
            action_index=0,
            action_id="action-001",
            result=result
        )

        assert isinstance(event, PauseActionCompleteEvent)
        assert event.user_input == "continue"


# ============================================================================
# TestCreateActionCompleteEventStopAction
# ============================================================================


class TestCreateActionCompleteEventStopAction:
    """Tests for create_action_complete_event with StopAction."""

    def test_stop_action_creates_stop_complete_event(self, event_manager):
        """StopAction should create StopActionCompleteEvent."""
        action = StopAction(description="Stop execution")
        result = MockActionResult(
            success=True,
            data={"condition_met": True, "should_stop": True},
            execution_time=0.01
        )

        event = event_manager.create_action_complete_event(
            action=action,
            action_index=0,
            action_id="action-001",
            result=result
        )

        assert isinstance(event, StopActionCompleteEvent)
        assert event.condition_met is True
        assert event.stopped_execution is True


# ============================================================================
# TestCreateActionCompleteEventContinueAction
# ============================================================================


class TestCreateActionCompleteEventContinueAction:
    """Tests for create_action_complete_event with ContinueAction."""

    def test_continue_action_creates_continue_complete_event(self, event_manager):
        """ContinueAction should create ContinueActionCompleteEvent."""
        action = ContinueAction(description="Continue")
        result = MockActionResult(
            success=True,
            data={"condition_met": True, "should_continue": True},
            execution_time=0.01
        )

        event = event_manager.create_action_complete_event(
            action=action,
            action_index=0,
            action_id="action-001",
            result=result
        )

        assert isinstance(event, ContinueActionCompleteEvent)
        assert event.condition_met is True
        assert event.skipped_remaining is True


# ============================================================================
# TestCreateActionCompleteEventTestAction
# ============================================================================


class TestCreateActionCompleteEventTestAction:
    """Tests for create_action_complete_event with ActionTestAction."""

    def test_test_action_creates_test_complete_event(self, event_manager):
        """ActionTestAction should create TestActionCompleteEvent."""
        action = ActionTestAction(name="test_file_exists", description="Test")
        result = MockActionResult(
            success=True,
            data={
                "result": {"details": "File exists at /path/to/file"},
                "result_category": "pass",
                "expect_to_fail": False
            },
            execution_time=0.5
        )

        event = event_manager.create_action_complete_event(
            action=action,
            action_index=0,
            action_id="action-001",
            result=result
        )

        assert isinstance(event, TestActionCompleteEvent)
        assert event.test_name == "test_file_exists"
        assert event.test_output == "File exists at /path/to/file"
        assert event.result_category == "pass"
        assert event.expect_to_fail is False


# ============================================================================
# TestCreateActionCompleteEventSaveTimestampAction
# ============================================================================


class TestCreateActionCompleteEventSaveTimestampAction:
    """Tests for create_action_complete_event with SaveTimestampAction."""

    def test_save_timestamp_action_creates_save_timestamp_complete_event(self, event_manager):
        """SaveTimestampAction should create SaveTimestampActionCompleteEvent."""
        action = SaveTimestampAction(variable="my_timestamp", description="Save timestamp")
        result = MockActionResult(
            success=True,
            data={"my_timestamp": 1704067200.123},
            execution_time=0.001
        )

        event = event_manager.create_action_complete_event(
            action=action,
            action_index=0,
            action_id="action-001",
            result=result
        )

        assert isinstance(event, SaveTimestampActionCompleteEvent)
        assert event.variable == "my_timestamp"
        assert event.timestamp_value == 1704067200.123


# ============================================================================
# TestCreateActionCompleteEventPullAction
# ============================================================================


class TestCreateActionCompleteEventPullAction:
    """Tests for create_action_complete_event with PullAction."""

    def test_pull_action_creates_pull_complete_event(self, event_manager):
        """PullAction should create PullActionCompleteEvent."""
        action = PullAction(src="/remote/file.txt", dst="local.txt", description="Pull")
        result = MockActionResult(
            success=True,
            data={"files_copied": 1, "total_size": 1024},
            execution_time=2.5
        )

        event = event_manager.create_action_complete_event(
            action=action,
            action_index=0,
            action_id="action-001",
            result=result
        )

        assert isinstance(event, PullActionCompleteEvent)
        assert event.source == "/remote/file.txt"
        assert event.destination == "local.txt"
        assert event.files_copied == 1
        assert event.total_size == 1024


# ============================================================================
# TestCreateActionCompleteEventSnapshotFilesystemAction
# ============================================================================


class TestCreateActionCompleteEventSnapshotFilesystemAction:
    """Tests for create_action_complete_event with SnapshotFilesystemAction."""

    def test_snapshot_filesystem_creates_snapshot_complete_event(self, event_manager):
        """SnapshotFilesystemAction should create SnapshotFilesystemActionCompleteEvent."""
        action = SnapshotFilesystemAction(variable="fs_snap", description="Snapshot")
        result = MockActionResult(
            success=True,
            data={"files_count": 5000},
            execution_time=30.0
        )

        event = event_manager.create_action_complete_event(
            action=action,
            action_index=0,
            action_id="action-001",
            result=result
        )

        assert isinstance(event, SnapshotFilesystemActionCompleteEvent)
        assert event.files_count == 5000


# ============================================================================
# TestCreateActionCompleteEventPullChangedFilesAction
# ============================================================================


class TestCreateActionCompleteEventPullChangedFilesAction:
    """Tests for create_action_complete_event with PullChangedFilesAction."""

    def test_pull_changed_files_creates_pull_changed_complete_event(self, event_manager):
        """PullChangedFilesAction should create PullChangedFilesActionCompleteEvent."""
        action = PullChangedFilesAction(
            snapshot_before="before",
            snapshot_after="after",
            description="Pull changed"
        )
        result = MockActionResult(
            success=True,
            data={"files_pulled": 25, "total_size": 50000},
            execution_time=15.0
        )

        event = event_manager.create_action_complete_event(
            action=action,
            action_index=0,
            action_id="action-001",
            result=result
        )

        assert isinstance(event, PullChangedFilesActionCompleteEvent)
        assert event.files_pulled == 25
        assert event.total_size == 50000


# ============================================================================
# TestCreateActionCompleteEventFindAction
# ============================================================================


class TestCreateActionCompleteEventFindAction:
    """Tests for create_action_complete_event with FindAction."""

    def test_find_action_creates_find_complete_event(self, event_manager, success_result):
        """FindAction should create FindActionCompleteEvent."""
        action = FindAction(description="Find target", target_info={"image": "button.png"})

        event = event_manager.create_action_complete_event(
            action=action,
            action_index=0,
            action_id="action-001",
            result=success_result
        )

        assert isinstance(event, FindActionCompleteEvent)
        assert event.target_info == {"image": "button.png"}
        assert event.coordinates == (150, 250)


# ============================================================================
# TestCreateActionCompleteEventExecuteAction
# ============================================================================


class TestCreateActionCompleteEventExecuteAction:
    """Tests for create_action_complete_event with ExecuteAction."""

    def test_execute_action_creates_execute_complete_event(self, event_manager, success_result):
        """ExecuteAction should create ExecuteActionCompleteEvent."""
        action = ExecuteAction(description="Execute", coordinates=(100, 200))

        event = event_manager.create_action_complete_event(
            action=action,
            action_index=0,
            action_id="action-001",
            result=success_result
        )

        assert isinstance(event, ExecuteActionCompleteEvent)
        assert event.coordinates == (150, 250)  # from result


# ============================================================================
# TestCreateActionCompleteEventUnknownAction
# ============================================================================


class TestCreateActionCompleteEventUnknownAction:
    """Tests for create_action_complete_event with unknown action types."""

    def test_unknown_action_creates_generic_complete_event(self, event_manager, success_result):
        """Unknown action type should create generic ActionCompleteEvent."""
        class UnknownAction:
            description = "Unknown action type"

        action = UnknownAction()

        event = event_manager.create_action_complete_event(
            action=action,
            action_index=0,
            action_id="action-001",
            result=success_result
        )

        assert isinstance(event, ActionCompleteEvent)
        assert event.success is True


# ============================================================================
# TestGetTargetInfo
# ============================================================================


class TestGetTargetInfo:
    """Tests for _get_target_info helper method."""

    def test_returns_none_for_none_target(self, event_manager):
        """_get_target_info should return None for None target."""
        result = event_manager._get_target_info(None)
        assert result is None

    def test_extracts_image_info(self, event_manager, image_target):
        """_get_target_info should extract image info."""
        result = event_manager._get_target_info(image_target)

        assert result is not None
        assert result.get('image') == "button.png"

    def test_extracts_text_info(self, event_manager, text_target):
        """_get_target_info should extract text info."""
        result = event_manager._get_target_info(text_target)

        assert result is not None
        assert result.get('text') == "Click Me"

    def test_extracts_position_info(self, event_manager, simple_target):
        """_get_target_info should extract position info."""
        result = event_manager._get_target_info(simple_target)

        assert result is not None
        assert result.get('position') == [100, 200]

    def test_returns_none_for_empty_target(self, event_manager):
        """_get_target_info should return None for target with no info."""
        empty_target = Target()
        result = event_manager._get_target_info(empty_target)

        assert result is None

    def test_extracts_strategy_info(self, event_manager):
        """_get_target_info should extract strategy info."""
        from adare.types.playbook import SweepStrategy
        target = Target(image="button.png", strategy=SweepStrategy(index=2))

        result = event_manager._get_target_info(target)

        assert result is not None
        assert result.get('strategy') == "SweepStrategy"


# ============================================================================
# TestGetConditionInfo
# ============================================================================


class TestGetConditionInfo:
    """Tests for _get_condition_info helper method."""

    def test_returns_none_for_none_conditions(self, event_manager):
        """_get_condition_info should return None for None conditions."""
        result = event_manager._get_condition_info(None)
        assert result is None

    def test_handles_list_of_conditions(self, event_manager):
        """_get_condition_info should handle list of conditions."""
        conditions = [
            ExistsCondition(text="Ready"),
            ExistsCondition(image="icon.png")
        ]

        result = event_manager._get_condition_info(conditions)

        assert result is not None
        assert result.get('count') == 2
        assert len(result.get('types')) == 2

    def test_handles_single_condition(self, event_manager):
        """_get_condition_info should handle single condition."""
        condition = ExistsCondition(text="Ready")

        result = event_manager._get_condition_info(condition)

        assert result is not None
        assert result.get('type') == "ExistsCondition"


# ============================================================================
# TestGenerateCommandDescription
# ============================================================================


class TestGenerateCommandDescription:
    """Tests for _generate_command_description helper method."""

    def test_short_command(self, event_manager):
        """Short commands should be displayed fully."""
        action = CommandAction(command="ls -la")
        result = event_manager._generate_command_description(action)

        assert "ls -la" in result
        assert "command:" in result.lower()

    def test_long_command_truncated(self, event_manager):
        """Long commands should be truncated."""
        long_command = "a" * 100
        action = CommandAction(command=long_command)

        result = event_manager._generate_command_description(action)

        assert "..." in result
        assert len(result) < 100

    def test_heredoc_command(self, event_manager):
        """Heredoc commands should be handled specially."""
        action = CommandAction(command="cat > /tmp/file.txt << EOF\ncontent\nEOF")

        result = event_manager._generate_command_description(action)

        assert "command:" in result.lower()

    def test_multiline_command_collapsed(self, event_manager):
        """Multiline commands should be collapsed to single line."""
        action = CommandAction(command="echo hello\necho world")

        result = event_manager._generate_command_description(action)

        assert "\n" not in result


# ============================================================================
# TestEventDataSerialization
# ============================================================================


class TestEventDataSerialization:
    """Tests for event data serialization."""

    def test_start_event_contains_all_required_fields(self, event_manager_with_context, simple_target):
        """Start events should contain all required fields."""
        action = ClickAction(target=simple_target, description="Test click")

        event = event_manager_with_context.create_action_start_event(
            action=action,
            action_index=0,
            action_id="action-001",
            parent_event_id="parent-001"
        )

        assert event.action_id == "action-001"
        assert event.action_description == "Test click"
        assert event.sequence_order == 0
        assert event.playbook_item_id == "item-0"
        assert event.experiment_run_id == "run-123"
        assert event.parent_event_id == "parent-001"

    def test_complete_event_contains_all_required_fields(self, event_manager_with_context, simple_target, success_result):
        """Complete events should contain all required fields."""
        action = ClickAction(target=simple_target, description="Test click")

        event = event_manager_with_context.create_action_complete_event(
            action=action,
            action_index=1,
            action_id="action-002",
            result=success_result,
            parent_event_id="parent-001"
        )

        assert event.action_id == "action-002"
        assert event.action_description == "Test click"
        assert event.sequence_order == 1
        assert event.playbook_item_id == "item-1"
        assert event.experiment_run_id == "run-123"
        assert event.parent_event_id == "parent-001"
        assert event.success is True
        assert event.execution_time == 1.5


# ============================================================================
# TestDescriptionNewlineHandling
# ============================================================================


class TestDescriptionNewlineHandling:
    """Tests for description newline handling."""

    def test_description_newlines_stripped(self, event_manager, simple_target):
        """Descriptions with newlines should be collapsed to single line."""
        action = ClickAction(
            target=simple_target,
            description="Line 1\nLine 2\nLine 3"
        )

        event = event_manager.create_action_start_event(
            action=action,
            action_index=0,
            action_id="action-001"
        )

        assert "\n" not in event.action_description
        assert "Line 1" in event.action_description
        assert "Line 2" in event.action_description
        assert "Line 3" in event.action_description

    def test_empty_description_handled(self, event_manager, simple_target):
        """Empty descriptions should be handled."""
        action = ClickAction(target=simple_target, description="")

        event = event_manager.create_action_start_event(
            action=action,
            action_index=0,
            action_id="action-001"
        )

        assert event.action_description == ""


# ============================================================================
# TestPlaybookItemIdMapping
# ============================================================================


class TestPlaybookItemIdMapping:
    """Tests for playbook item ID mapping."""

    def test_playbook_item_id_from_map(self, event_manager_with_context, simple_target):
        """Events should include playbook_item_id from map."""
        action = ClickAction(target=simple_target, description="Test")

        event = event_manager_with_context.create_action_start_event(
            action=action,
            action_index=1,
            action_id="action-001"
        )

        assert event.playbook_item_id == "item-1"

    def test_playbook_item_id_none_when_not_in_map(self, event_manager_with_context, simple_target):
        """playbook_item_id should be None when action_index not in map."""
        action = ClickAction(target=simple_target, description="Test")

        event = event_manager_with_context.create_action_start_event(
            action=action,
            action_index=99,  # Not in map
            action_id="action-001"
        )

        assert event.playbook_item_id is None
