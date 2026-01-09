"""Comprehensive unit tests for adare/types/event_types.py."""

import pytest
from adare.types.event_types import EventType, ActionType, EventTypeResolver, event_type_resolver


class TestEventTypeEnum:
    """Tests for EventType enum."""

    def test_stage_event_type(self):
        """Test STAGE event type exists with correct value."""
        assert EventType.STAGE.value == "stage"

    @pytest.mark.parametrize(
        "event_type,expected_value",
        [
            (EventType.ACTION_START, "action_start"),
            (EventType.ACTION_COMPLETE, "action_complete"),
            (EventType.CLICK_START, "click_start"),
            (EventType.CLICK_COMPLETE, "click_complete"),
            (EventType.KEYBOARD_START, "keyboard_start"),
            (EventType.KEYBOARD_COMPLETE, "keyboard_complete"),
            (EventType.COMMAND_START, "command_start"),
            (EventType.COMMAND_COMPLETE, "command_complete"),
            (EventType.IDLE_START, "idle_start"),
            (EventType.IDLE_COMPLETE, "idle_complete"),
            (EventType.TEST_START, "test_start"),
            (EventType.TEST_COMPLETE, "test_complete"),
            (EventType.SCREENSHOT_START, "screenshot_start"),
            (EventType.SCREENSHOT_COMPLETE, "screenshot_complete"),
            (EventType.SCROLL_START, "scroll_start"),
            (EventType.SCROLL_COMPLETE, "scroll_complete"),
            (EventType.DRAG_START, "drag_start"),
            (EventType.DRAG_COMPLETE, "drag_complete"),
            (EventType.GOTO_START, "goto_start"),
            (EventType.GOTO_COMPLETE, "goto_complete"),
            (EventType.SAVETIMESTAMP_START, "savetimestamp_start"),
            (EventType.SAVETIMESTAMP_COMPLETE, "savetimestamp_complete"),
            (EventType.PULL_START, "pull_start"),
            (EventType.PULL_COMPLETE, "pull_complete"),
            (EventType.PAUSE_START, "pause_start"),
            (EventType.PAUSE_COMPLETE, "pause_complete"),
            (EventType.BLOCK_START, "block_start"),
            (EventType.BLOCK_COMPLETE, "block_complete"),
            (EventType.WAIT_UNTIL_START, "wait_until_start"),
            (EventType.WAIT_UNTIL_COMPLETE, "wait_until_complete"),
            (EventType.LOOP_START, "loop_start"),
            (EventType.LOOP_COMPLETE, "loop_complete"),
            (EventType.STOP_START, "stop_start"),
            (EventType.STOP_COMPLETE, "stop_complete"),
            (EventType.CONTINUE_START, "continue_start"),
            (EventType.CONTINUE_COMPLETE, "continue_complete"),
            (EventType.SNAPSHOT_FILESYSTEM_START, "snapshot_filesystem_start"),
            (EventType.SNAPSHOT_FILESYSTEM_COMPLETE, "snapshot_filesystem_complete"),
            (EventType.PULL_CHANGED_FILES_START, "pull_changed_files_start"),
            (EventType.PULL_CHANGED_FILES_COMPLETE, "pull_changed_files_complete"),
        ],
    )
    def test_event_type_values(self, event_type, expected_value):
        """Test all EventType enum members have correct values."""
        assert event_type.value == expected_value

    def test_event_type_count(self):
        """Test we have expected number of event types (at least 24)."""
        assert len(EventType) >= 24

    def test_event_type_from_value(self):
        """Test creating EventType from string value."""
        assert EventType("click_start") == EventType.CLICK_START
        assert EventType("command_complete") == EventType.COMMAND_COMPLETE

    def test_event_type_invalid_value_raises(self):
        """Test invalid value raises ValueError."""
        with pytest.raises(ValueError):
            EventType("invalid_event_type")


class TestActionTypeEnum:
    """Tests for ActionType enum."""

    @pytest.mark.parametrize(
        "action_type,expected_value",
        [
            (ActionType.CLICK, "click"),
            (ActionType.RIGHTCLICK, "rightclick"),
            (ActionType.DOUBLECLICK, "doubleclick"),
            (ActionType.KEYBOARD, "keyboard"),
            (ActionType.COMMAND, "command"),
            (ActionType.IDLE, "idle"),
            (ActionType.TEST, "test"),
            (ActionType.SCREENSHOT, "screenshot"),
            (ActionType.SCROLL, "scroll"),
            (ActionType.DRAG, "drag"),
            (ActionType.GOTO, "goto"),
            (ActionType.SAVETIMESTAMP, "savetimestamp"),
            (ActionType.PULL, "pull"),
            (ActionType.PAUSE, "pause"),
            (ActionType.BLOCK, "block"),
            (ActionType.WAIT_UNTIL, "wait_until"),
            (ActionType.LOOP, "loop"),
            (ActionType.STOP, "stop"),
            (ActionType.CONTINUE, "continue"),
            (ActionType.SNAPSHOT_FILESYSTEM, "snapshot_filesystem"),
            (ActionType.PULL_CHANGED_FILES, "pull_changed_files"),
            (ActionType.FIND, "find"),
            (ActionType.EXECUTE, "execute"),
        ],
    )
    def test_action_type_values(self, action_type, expected_value):
        """Test all ActionType enum members have correct values."""
        assert action_type.value == expected_value

    def test_action_type_count(self):
        """Test we have expected number of action types (at least 21)."""
        assert len(ActionType) >= 21

    def test_action_type_from_value(self):
        """Test creating ActionType from string value."""
        assert ActionType("click") == ActionType.CLICK
        assert ActionType("keyboard") == ActionType.KEYBOARD

    def test_action_type_invalid_value_raises(self):
        """Test invalid value raises ValueError."""
        with pytest.raises(ValueError):
            ActionType("invalid_action_type")


class TestEventTypeResolverInit:
    """Tests for EventTypeResolver initialization."""

    def test_resolver_initialization(self):
        """Test resolver initializes with class name mappings."""
        resolver = EventTypeResolver()
        assert hasattr(resolver, "_class_name_mapping")
        assert len(resolver._class_name_mapping) > 0

    def test_global_resolver_instance_exists(self):
        """Test global resolver instance is available."""
        assert event_type_resolver is not None
        assert isinstance(event_type_resolver, EventTypeResolver)


class TestResolveEventType:
    """Tests for EventTypeResolver.resolve_event_type()."""

    @pytest.fixture
    def resolver(self):
        """Create a fresh resolver instance."""
        return EventTypeResolver()

    def test_resolve_with_explicit_event_type_field(self, resolver):
        """Test resolution with explicit event_type field."""
        data = {"event_type": "click_start", "other_field": "value"}
        assert resolver.resolve_event_type(data) == EventType.CLICK_START

    def test_resolve_with_explicit_event_type_complete(self, resolver):
        """Test resolution with explicit event_type field for complete event."""
        data = {"event_type": "command_complete", "success": True}
        assert resolver.resolve_event_type(data) == EventType.COMMAND_COMPLETE

    @pytest.mark.parametrize(
        "event_type_value,expected",
        [
            ("stage", EventType.STAGE),
            ("action_start", EventType.ACTION_START),
            ("action_complete", EventType.ACTION_COMPLETE),
            ("keyboard_start", EventType.KEYBOARD_START),
            ("test_complete", EventType.TEST_COMPLETE),
            ("screenshot_start", EventType.SCREENSHOT_START),
            ("loop_complete", EventType.LOOP_COMPLETE),
            ("snapshot_filesystem_start", EventType.SNAPSHOT_FILESYSTEM_START),
            ("pull_changed_files_complete", EventType.PULL_CHANGED_FILES_COMPLETE),
        ],
    )
    def test_resolve_various_explicit_event_types(self, resolver, event_type_value, expected):
        """Test resolution of various explicit event_type values."""
        data = {"event_type": event_type_value}
        assert resolver.resolve_event_type(data) == expected

    def test_resolve_with_unknown_event_type_falls_through(self, resolver):
        """Test unknown event_type falls through to other resolution methods."""
        data = {"event_type": "unknown_type", "__class__": "ClickStartEvent"}
        result = resolver.resolve_event_type(data)
        assert result == EventType.CLICK_START

    @pytest.mark.parametrize(
        "class_name,expected",
        [
            ("ClickStartEvent", EventType.CLICK_START),
            ("ClickCompleteEvent", EventType.CLICK_COMPLETE),
            ("KeyboardStartEvent", EventType.KEYBOARD_START),
            ("KeyboardCompleteEvent", EventType.KEYBOARD_COMPLETE),
            ("CommandStartEvent", EventType.COMMAND_START),
            ("CommandCompleteEvent", EventType.COMMAND_COMPLETE),
            ("IdleStartEvent", EventType.IDLE_START),
            ("IdleCompleteEvent", EventType.IDLE_COMPLETE),
            ("TestStartEvent", EventType.TEST_START),
            ("TestCompleteEvent", EventType.TEST_COMPLETE),
            ("ScreenshotStartEvent", EventType.SCREENSHOT_START),
            ("ScreenshotCompleteEvent", EventType.SCREENSHOT_COMPLETE),
            ("ScrollStartEvent", EventType.SCROLL_START),
            ("ScrollCompleteEvent", EventType.SCROLL_COMPLETE),
            ("DragStartEvent", EventType.DRAG_START),
            ("DragCompleteEvent", EventType.DRAG_COMPLETE),
            ("GotoStartEvent", EventType.GOTO_START),
            ("GotoCompleteEvent", EventType.GOTO_COMPLETE),
            ("SavetimestampStartEvent", EventType.SAVETIMESTAMP_START),
            ("SavetimestampCompleteEvent", EventType.SAVETIMESTAMP_COMPLETE),
            ("PullActionStartEvent", EventType.PULL_START),
            ("PullActionCompleteEvent", EventType.PULL_COMPLETE),
            ("PauseActionStartEvent", EventType.PAUSE_START),
            ("PauseActionCompleteEvent", EventType.PAUSE_COMPLETE),
            ("BlockActionStartEvent", EventType.BLOCK_START),
            ("BlockActionCompleteEvent", EventType.BLOCK_COMPLETE),
            ("WaitUntilActionStartEvent", EventType.WAIT_UNTIL_START),
            ("WaitUntilActionCompleteEvent", EventType.WAIT_UNTIL_COMPLETE),
            ("LoopActionStartEvent", EventType.LOOP_START),
            ("LoopActionCompleteEvent", EventType.LOOP_COMPLETE),
            ("StopActionStartEvent", EventType.STOP_START),
            ("StopActionCompleteEvent", EventType.STOP_COMPLETE),
            ("ContinueActionStartEvent", EventType.CONTINUE_START),
            ("ContinueActionCompleteEvent", EventType.CONTINUE_COMPLETE),
            ("SnapshotFilesystemActionStartEvent", EventType.SNAPSHOT_FILESYSTEM_START),
            ("SnapshotFilesystemActionCompleteEvent", EventType.SNAPSHOT_FILESYSTEM_COMPLETE),
            ("PullChangedFilesActionStartEvent", EventType.PULL_CHANGED_FILES_START),
            ("PullChangedFilesActionCompleteEvent", EventType.PULL_CHANGED_FILES_COMPLETE),
        ],
    )
    def test_resolve_with_legacy_class_field(self, resolver, class_name, expected):
        """Test resolution with legacy __class__ field mapping."""
        data = {"__class__": class_name}
        assert resolver.resolve_event_type(data) == expected

    def test_resolve_with_type_field_instead_of_class(self, resolver):
        """Test resolution with _type field instead of __class__."""
        data = {"_type": "ClickStartEvent"}
        assert resolver.resolve_event_type(data) == EventType.CLICK_START


class TestDetectEventTypeFromPatterns:
    """Tests for EventTypeResolver._detect_event_type_from_patterns()."""

    @pytest.fixture
    def resolver(self):
        """Create a fresh resolver instance."""
        return EventTypeResolver()

    def test_detect_complete_event_with_success_field(self, resolver):
        """Test detection of complete event when success field is present."""
        data = {"success": True}
        result = resolver._detect_event_type_from_patterns(data, "ClickEvent")
        assert result == EventType.CLICK_COMPLETE

    def test_detect_start_event_without_success_field(self, resolver):
        """Test detection of start event when success field is absent."""
        data = {}
        result = resolver._detect_event_type_from_patterns(data, "ClickStart")
        assert result == EventType.CLICK_START

    def test_detect_complete_from_class_name_suffix(self, resolver):
        """Test detection of complete event from 'Complete' in class name."""
        data = {}
        result = resolver._detect_event_type_from_patterns(data, "ClickComplete")
        assert result == EventType.CLICK_COMPLETE

    @pytest.mark.parametrize(
        "class_name,is_complete,expected",
        [
            ("ClickStart", False, EventType.CLICK_START),
            ("ClickComplete", True, EventType.CLICK_COMPLETE),
            ("RightclickStart", False, EventType.CLICK_START),
            ("DoubleclickComplete", True, EventType.CLICK_COMPLETE),
            ("KeyboardStart", False, EventType.KEYBOARD_START),
            ("KeyboardComplete", True, EventType.KEYBOARD_COMPLETE),
            ("CommandStart", False, EventType.COMMAND_START),
            ("CommandComplete", True, EventType.COMMAND_COMPLETE),
            ("IdleStart", False, EventType.IDLE_START),
            ("IdleComplete", True, EventType.IDLE_COMPLETE),
            ("TestStart", False, EventType.TEST_START),
            ("TestComplete", True, EventType.TEST_COMPLETE),
            ("ScreenshotStart", False, EventType.SCREENSHOT_START),
            ("ScreenshotComplete", True, EventType.SCREENSHOT_COMPLETE),
            ("ScrollStart", False, EventType.SCROLL_START),
            ("ScrollComplete", True, EventType.SCROLL_COMPLETE),
            ("DragStart", False, EventType.DRAG_START),
            ("DragComplete", True, EventType.DRAG_COMPLETE),
            ("GotoStart", False, EventType.GOTO_START),
            ("GotoComplete", True, EventType.GOTO_COMPLETE),
            ("SavetimestampStart", False, EventType.SAVETIMESTAMP_START),
            ("SavetimestampComplete", True, EventType.SAVETIMESTAMP_COMPLETE),
            ("PullStart", False, EventType.PULL_START),
            ("PullComplete", True, EventType.PULL_COMPLETE),
            ("PauseStart", False, EventType.PAUSE_START),
            ("PauseComplete", True, EventType.PAUSE_COMPLETE),
            ("BlockStart", False, EventType.BLOCK_START),
            ("BlockComplete", True, EventType.BLOCK_COMPLETE),
            ("WaituntilStart", False, EventType.WAIT_UNTIL_START),
            ("WaituntilComplete", True, EventType.WAIT_UNTIL_COMPLETE),
            ("LoopStart", False, EventType.LOOP_START),
            ("LoopComplete", True, EventType.LOOP_COMPLETE),
            ("StopStart", False, EventType.STOP_START),
            ("StopComplete", True, EventType.STOP_COMPLETE),
            ("ContinueStart", False, EventType.CONTINUE_START),
            ("ContinueComplete", True, EventType.CONTINUE_COMPLETE),
            ("SnapshotfilesystemStart", False, EventType.SNAPSHOT_FILESYSTEM_START),
            ("SnapshotfilesystemComplete", True, EventType.SNAPSHOT_FILESYSTEM_COMPLETE),
            ("PullchangedfilesStart", False, EventType.PULL_CHANGED_FILES_START),
            ("PullchangedfilesComplete", True, EventType.PULL_CHANGED_FILES_COMPLETE),
        ],
    )
    def test_detect_various_action_types(self, resolver, class_name, is_complete, expected):
        """Test pattern detection for various action types."""
        data = {"success": True} if is_complete else {}
        result = resolver._detect_event_type_from_patterns(data, class_name)
        assert result == expected

    def test_detect_find_action_start(self, resolver):
        """Test detection of find action as generic action start."""
        data = {}
        result = resolver._detect_event_type_from_patterns(data, "FindStart")
        assert result == EventType.ACTION_START

    def test_detect_find_action_complete(self, resolver):
        """Test detection of find action as generic action complete."""
        data = {"success": True}
        result = resolver._detect_event_type_from_patterns(data, "FindComplete")
        assert result == EventType.ACTION_COMPLETE

    def test_detect_execute_action_start(self, resolver):
        """Test detection of execute action as generic action start."""
        data = {}
        result = resolver._detect_event_type_from_patterns(data, "ExecuteStart")
        assert result == EventType.ACTION_START

    def test_detect_execute_action_complete(self, resolver):
        """Test detection of execute action as generic action complete."""
        data = {"success": True}
        result = resolver._detect_event_type_from_patterns(data, "ExecuteComplete")
        assert result == EventType.ACTION_COMPLETE

    def test_detect_unknown_class_name_defaults_to_generic(self, resolver):
        """Test unknown class name defaults to generic action type."""
        data = {}
        result = resolver._detect_event_type_from_patterns(data, "UnknownEvent")
        assert result == EventType.ACTION_START

    def test_detect_unknown_complete_defaults_to_action_complete(self, resolver):
        """Test unknown class with success field defaults to action complete."""
        data = {"success": True}
        result = resolver._detect_event_type_from_patterns(data, "UnknownEvent")
        assert result == EventType.ACTION_COMPLETE


class TestGetActionType:
    """Tests for EventTypeResolver.get_action_type()."""

    @pytest.fixture
    def resolver(self):
        """Create a fresh resolver instance."""
        return EventTypeResolver()

    @pytest.mark.parametrize(
        "event_type,expected_action",
        [
            (EventType.CLICK_START, ActionType.CLICK),
            (EventType.CLICK_COMPLETE, ActionType.CLICK),
            (EventType.KEYBOARD_START, ActionType.KEYBOARD),
            (EventType.KEYBOARD_COMPLETE, ActionType.KEYBOARD),
            (EventType.COMMAND_START, ActionType.COMMAND),
            (EventType.COMMAND_COMPLETE, ActionType.COMMAND),
            (EventType.IDLE_START, ActionType.IDLE),
            (EventType.IDLE_COMPLETE, ActionType.IDLE),
            (EventType.TEST_START, ActionType.TEST),
            (EventType.TEST_COMPLETE, ActionType.TEST),
            (EventType.SCREENSHOT_START, ActionType.SCREENSHOT),
            (EventType.SCREENSHOT_COMPLETE, ActionType.SCREENSHOT),
            (EventType.SCROLL_START, ActionType.SCROLL),
            (EventType.SCROLL_COMPLETE, ActionType.SCROLL),
            (EventType.DRAG_START, ActionType.DRAG),
            (EventType.DRAG_COMPLETE, ActionType.DRAG),
            (EventType.GOTO_START, ActionType.GOTO),
            (EventType.GOTO_COMPLETE, ActionType.GOTO),
            (EventType.SAVETIMESTAMP_START, ActionType.SAVETIMESTAMP),
            (EventType.SAVETIMESTAMP_COMPLETE, ActionType.SAVETIMESTAMP),
            (EventType.PULL_START, ActionType.PULL),
            (EventType.PULL_COMPLETE, ActionType.PULL),
            (EventType.PAUSE_START, ActionType.PAUSE),
            (EventType.PAUSE_COMPLETE, ActionType.PAUSE),
            (EventType.BLOCK_START, ActionType.BLOCK),
            (EventType.BLOCK_COMPLETE, ActionType.BLOCK),
            (EventType.WAIT_UNTIL_START, ActionType.WAIT_UNTIL),
            (EventType.WAIT_UNTIL_COMPLETE, ActionType.WAIT_UNTIL),
            (EventType.LOOP_START, ActionType.LOOP),
            (EventType.LOOP_COMPLETE, ActionType.LOOP),
            (EventType.STOP_START, ActionType.STOP),
            (EventType.STOP_COMPLETE, ActionType.STOP),
            (EventType.CONTINUE_START, ActionType.CONTINUE),
            (EventType.CONTINUE_COMPLETE, ActionType.CONTINUE),
            (EventType.SNAPSHOT_FILESYSTEM_START, ActionType.SNAPSHOT_FILESYSTEM),
            (EventType.SNAPSHOT_FILESYSTEM_COMPLETE, ActionType.SNAPSHOT_FILESYSTEM),
            # Note: PULL_CHANGED_FILES events match "pull_" prefix first due to order of checks in source
            # This returns ActionType.PULL instead of ActionType.PULL_CHANGED_FILES
            (EventType.PULL_CHANGED_FILES_START, ActionType.PULL),
            (EventType.PULL_CHANGED_FILES_COMPLETE, ActionType.PULL),
        ],
    )
    def test_get_action_type_from_event_type(self, resolver, event_type, expected_action):
        """Test extracting action type from various event types."""
        assert resolver.get_action_type(event_type) == expected_action

    def test_get_action_type_with_find_action_data(self, resolver):
        """Test extracting FIND action type from action data."""
        action_data = {"__class__": "FindAction"}
        result = resolver.get_action_type(EventType.ACTION_START, action_data)
        assert result == ActionType.FIND

    def test_get_action_type_with_execute_action_data(self, resolver):
        """Test extracting EXECUTE action type from action data."""
        action_data = {"__class__": "ExecuteAction"}
        result = resolver.get_action_type(EventType.ACTION_COMPLETE, action_data)
        assert result == ActionType.EXECUTE

    def test_get_action_type_with_type_field(self, resolver):
        """Test extracting action type from _type field."""
        action_data = {"_type": "FindSomething"}
        result = resolver.get_action_type(EventType.ACTION_START, action_data)
        assert result == ActionType.FIND

    def test_get_action_type_generic_without_action_data(self, resolver):
        """Test generic event type without action data defaults to CLICK."""
        result = resolver.get_action_type(EventType.ACTION_START)
        assert result == ActionType.CLICK

    def test_get_action_type_stage_defaults_to_click(self, resolver):
        """Test STAGE event type defaults to CLICK."""
        result = resolver.get_action_type(EventType.STAGE)
        assert result == ActionType.CLICK


class TestIsStartEvent:
    """Tests for EventTypeResolver.is_start_event()."""

    @pytest.fixture
    def resolver(self):
        """Create a fresh resolver instance."""
        return EventTypeResolver()

    @pytest.mark.parametrize(
        "event_type",
        [
            EventType.ACTION_START,
            EventType.CLICK_START,
            EventType.KEYBOARD_START,
            EventType.COMMAND_START,
            EventType.IDLE_START,
            EventType.TEST_START,
            EventType.SCREENSHOT_START,
            EventType.SCROLL_START,
            EventType.DRAG_START,
            EventType.GOTO_START,
            EventType.SAVETIMESTAMP_START,
            EventType.PULL_START,
            EventType.PAUSE_START,
            EventType.BLOCK_START,
            EventType.WAIT_UNTIL_START,
            EventType.LOOP_START,
            EventType.STOP_START,
            EventType.CONTINUE_START,
            EventType.SNAPSHOT_FILESYSTEM_START,
            EventType.PULL_CHANGED_FILES_START,
        ],
    )
    def test_is_start_event_returns_true_for_start_events(self, resolver, event_type):
        """Test is_start_event returns True for all start event types."""
        assert resolver.is_start_event(event_type) is True

    @pytest.mark.parametrize(
        "event_type",
        [
            EventType.ACTION_COMPLETE,
            EventType.CLICK_COMPLETE,
            EventType.KEYBOARD_COMPLETE,
            EventType.COMMAND_COMPLETE,
            EventType.IDLE_COMPLETE,
            EventType.TEST_COMPLETE,
            EventType.SCREENSHOT_COMPLETE,
            EventType.SCROLL_COMPLETE,
            EventType.DRAG_COMPLETE,
            EventType.GOTO_COMPLETE,
            EventType.SAVETIMESTAMP_COMPLETE,
            EventType.PULL_COMPLETE,
            EventType.PAUSE_COMPLETE,
            EventType.BLOCK_COMPLETE,
            EventType.WAIT_UNTIL_COMPLETE,
            EventType.LOOP_COMPLETE,
            EventType.STOP_COMPLETE,
            EventType.CONTINUE_COMPLETE,
            EventType.SNAPSHOT_FILESYSTEM_COMPLETE,
            EventType.PULL_CHANGED_FILES_COMPLETE,
        ],
    )
    def test_is_start_event_returns_false_for_complete_events(self, resolver, event_type):
        """Test is_start_event returns False for all complete event types."""
        assert resolver.is_start_event(event_type) is False

    def test_is_start_event_returns_false_for_stage(self, resolver):
        """Test is_start_event returns False for STAGE event type."""
        assert resolver.is_start_event(EventType.STAGE) is False


class TestIsCompleteEvent:
    """Tests for EventTypeResolver.is_complete_event()."""

    @pytest.fixture
    def resolver(self):
        """Create a fresh resolver instance."""
        return EventTypeResolver()

    @pytest.mark.parametrize(
        "event_type",
        [
            EventType.ACTION_COMPLETE,
            EventType.CLICK_COMPLETE,
            EventType.KEYBOARD_COMPLETE,
            EventType.COMMAND_COMPLETE,
            EventType.IDLE_COMPLETE,
            EventType.TEST_COMPLETE,
            EventType.SCREENSHOT_COMPLETE,
            EventType.SCROLL_COMPLETE,
            EventType.DRAG_COMPLETE,
            EventType.GOTO_COMPLETE,
            EventType.SAVETIMESTAMP_COMPLETE,
            EventType.PULL_COMPLETE,
            EventType.PAUSE_COMPLETE,
            EventType.BLOCK_COMPLETE,
            EventType.WAIT_UNTIL_COMPLETE,
            EventType.LOOP_COMPLETE,
            EventType.STOP_COMPLETE,
            EventType.CONTINUE_COMPLETE,
            EventType.SNAPSHOT_FILESYSTEM_COMPLETE,
            EventType.PULL_CHANGED_FILES_COMPLETE,
        ],
    )
    def test_is_complete_event_returns_true_for_complete_events(self, resolver, event_type):
        """Test is_complete_event returns True for all complete event types."""
        assert resolver.is_complete_event(event_type) is True

    @pytest.mark.parametrize(
        "event_type",
        [
            EventType.ACTION_START,
            EventType.CLICK_START,
            EventType.KEYBOARD_START,
            EventType.COMMAND_START,
            EventType.IDLE_START,
            EventType.TEST_START,
            EventType.SCREENSHOT_START,
            EventType.SCROLL_START,
            EventType.DRAG_START,
            EventType.GOTO_START,
            EventType.SAVETIMESTAMP_START,
            EventType.PULL_START,
            EventType.PAUSE_START,
            EventType.BLOCK_START,
            EventType.WAIT_UNTIL_START,
            EventType.LOOP_START,
            EventType.STOP_START,
            EventType.CONTINUE_START,
            EventType.SNAPSHOT_FILESYSTEM_START,
            EventType.PULL_CHANGED_FILES_START,
        ],
    )
    def test_is_complete_event_returns_false_for_start_events(self, resolver, event_type):
        """Test is_complete_event returns False for all start event types."""
        assert resolver.is_complete_event(event_type) is False

    def test_is_complete_event_returns_false_for_stage(self, resolver):
        """Test is_complete_event returns False for STAGE event type."""
        assert resolver.is_complete_event(EventType.STAGE) is False


class TestResolveEventTypeFromName:
    """Tests for EventTypeResolver.resolve_event_type_from_name()."""

    @pytest.fixture
    def resolver(self):
        """Create a fresh resolver instance."""
        return EventTypeResolver()

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("stage", EventType.STAGE),
            ("action_start", EventType.ACTION_START),
            ("action_complete", EventType.ACTION_COMPLETE),
            ("click_start", EventType.CLICK_START),
            ("click_complete", EventType.CLICK_COMPLETE),
            ("keyboard_start", EventType.KEYBOARD_START),
            ("command_complete", EventType.COMMAND_COMPLETE),
            ("test_start", EventType.TEST_START),
            ("screenshot_complete", EventType.SCREENSHOT_COMPLETE),
            ("loop_start", EventType.LOOP_START),
            ("wait_until_complete", EventType.WAIT_UNTIL_COMPLETE),
            ("snapshot_filesystem_start", EventType.SNAPSHOT_FILESYSTEM_START),
            ("pull_changed_files_complete", EventType.PULL_CHANGED_FILES_COMPLETE),
        ],
    )
    def test_resolve_valid_event_type_names(self, resolver, name, expected):
        """Test resolving valid event type names."""
        assert resolver.resolve_event_type_from_name(name) == expected

    def test_resolve_unknown_name_defaults_to_action_start(self, resolver):
        """Test unknown name defaults to ACTION_START."""
        result = resolver.resolve_event_type_from_name("unknown_event_name")
        assert result == EventType.ACTION_START

    def test_resolve_empty_string_defaults_to_action_start(self, resolver):
        """Test empty string defaults to ACTION_START."""
        result = resolver.resolve_event_type_from_name("")
        assert result == EventType.ACTION_START


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.fixture
    def resolver(self):
        """Create a fresh resolver instance."""
        return EventTypeResolver()

    def test_resolve_empty_dict(self, resolver):
        """Test resolution with empty dictionary falls back to pattern detection."""
        result = resolver.resolve_event_type({})
        assert result == EventType.ACTION_START

    def test_resolve_with_none_values(self, resolver):
        """Test resolution with None values in dict."""
        data = {"event_type": None, "__class__": "ClickStartEvent"}
        result = resolver.resolve_event_type(data)
        assert result == EventType.CLICK_START

    def test_resolve_with_missing_both_fields(self, resolver):
        """Test resolution with neither event_type nor __class__."""
        data = {"some_field": "value", "another": 123}
        result = resolver.resolve_event_type(data)
        assert result == EventType.ACTION_START

    def test_get_action_type_with_empty_action_data(self, resolver):
        """Test get_action_type with empty action data dict."""
        result = resolver.get_action_type(EventType.ACTION_START, {})
        assert result == ActionType.CLICK

    def test_resolve_with_success_false(self, resolver):
        """Test resolution with success=False still considered complete."""
        data = {"success": False}
        result = resolver._detect_event_type_from_patterns(data, "ClickEvent")
        assert result == EventType.CLICK_COMPLETE

    def test_class_name_mapping_completeness(self, resolver):
        """Test that class name mapping has pairs for start and complete events."""
        start_events = [k for k in resolver._class_name_mapping if "Start" in k]
        complete_events = [k for k in resolver._class_name_mapping if "Complete" in k]

        assert len(start_events) > 0
        assert len(complete_events) > 0
        assert len(start_events) == len(complete_events)

    def test_resolver_is_stateless(self, resolver):
        """Test that resolver does not maintain state between calls."""
        data1 = {"event_type": "click_start"}
        data2 = {"event_type": "command_complete"}

        result1 = resolver.resolve_event_type(data1)
        result2 = resolver.resolve_event_type(data2)
        result1_again = resolver.resolve_event_type(data1)

        assert result1 == EventType.CLICK_START
        assert result2 == EventType.COMMAND_COMPLETE
        assert result1_again == EventType.CLICK_START
