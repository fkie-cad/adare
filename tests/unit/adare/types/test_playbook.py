"""Unit tests for adare.types.playbook module.

Tests focus on validation logic in __attrs_post_init__ methods and default values.
"""

import pytest
from typing import List

from adare.types.playbook import (
    # Strategy classes
    SweepStrategy,
    BestConfidenceStrategy,
    ClosestToStrategy,
    TopLeftStrategy,
    TopRightStrategy,
    BottomLeftStrategy,
    BottomRightStrategy,
    LargestStrategy,
    SmallestStrategy,
    # Core types
    Settings,
    Target,
    # Condition types
    ExistsCondition,
    NotExistsCondition,
    VariableCondition,
    WaitCondition,
    # Action types
    KeyboardAction,
    ClickAction,
    DragAction,
    IdleAction,
    ScrollAction,
    GotoAction,
    ActionTestAction,
    CommandAction,
    CaptureSpec,
    ScreenshotAction,
    SaveTimestampAction,
    SaveVariableAction,
    PullAction,
    PullChangedFilesAction,
    SnapshotFilesystemAction,
    PauseAction,
    StopAction,
    ContinueAction,
    BlockAction,
    WaitUntilAction,
    LoopAction,
    Playbook,
)


class TestSettings:
    """Tests for Settings dataclass default values."""

    def test_default_values(self):
        """Settings should have sensible default values."""
        settings = Settings()

        assert settings.idle == 0.1
        assert settings.timeout is None
        assert settings.screenshot is None
        assert settings.continue_on_test_failure is False
        assert settings.auto_pull_on_test_failure is True
        assert settings.collect_system_info is True
        assert settings.forensic_logging is True
        assert settings.enable_filesystem_diff is True

    def test_custom_values(self):
        """Settings should accept custom values."""
        settings = Settings(
            idle=0.5,
            timeout=30.0,
            screenshot={'format': 'png'},
            continue_on_test_failure=True,
            auto_pull_on_test_failure=False,
            collect_system_info=False,
            forensic_logging=False,
            enable_filesystem_diff=False,
        )

        assert settings.idle == 0.5
        assert settings.timeout == 30.0
        assert settings.screenshot == {'format': 'png'}
        assert settings.continue_on_test_failure is True
        assert settings.auto_pull_on_test_failure is False
        assert settings.collect_system_info is False
        assert settings.forensic_logging is False
        assert settings.enable_filesystem_diff is False


class TestTarget:
    """Tests for Target dataclass variants."""

    def test_image_target(self):
        """Target with image only."""
        target = Target(image='button.png')

        assert target.image == 'button.png'
        assert target.text is None
        assert target.position is None
        assert target.strategy is None

    def test_text_target(self):
        """Target with text only."""
        target = Target(text='Click Me')

        assert target.image is None
        assert target.text == 'Click Me'
        assert target.position is None
        assert target.strategy is None

    def test_position_target(self):
        """Target with position coordinates."""
        target = Target(position=[100, 200])

        assert target.image is None
        assert target.text is None
        assert target.position == [100, 200]
        assert target.strategy is None

    def test_target_with_strategy(self):
        """Target with strategy specified."""
        strategy = SweepStrategy(index=2)
        target = Target(text='Label', strategy=strategy)

        assert target.text == 'Label'
        assert target.strategy == strategy
        assert target.strategy.index == 2

    def test_empty_target(self):
        """Target with all defaults (all None)."""
        target = Target()

        assert target.image is None
        assert target.text is None
        assert target.position is None
        assert target.strategy is None


class TestSweepStrategy:
    """Tests for SweepStrategy."""

    def test_default_index(self):
        """SweepStrategy should default to index 1."""
        strategy = SweepStrategy()
        assert strategy.index == 1

    def test_custom_index(self):
        """SweepStrategy should accept custom index."""
        strategy = SweepStrategy(index=5)
        assert strategy.index == 5


class TestBestConfidenceStrategy:
    """Tests for BestConfidenceStrategy."""

    def test_creation(self):
        """BestConfidenceStrategy is a simple marker class."""
        strategy = BestConfidenceStrategy()
        assert strategy is not None


class TestClosestToStrategy:
    """Tests for ClosestToStrategy validation."""

    def test_coordinates_mode(self):
        """Valid coordinates mode with x and y."""
        strategy = ClosestToStrategy(x=100, y=200)

        assert strategy.x == 100
        assert strategy.y == 200
        assert strategy.text is None
        assert strategy.image is None

    def test_text_mode(self):
        """Valid text reference mode."""
        strategy = ClosestToStrategy(text='Reference Label')

        assert strategy.x is None
        assert strategy.y is None
        assert strategy.text == 'Reference Label'
        assert strategy.image is None

    def test_image_mode(self):
        """Valid image reference mode."""
        strategy = ClosestToStrategy(image='reference.png')

        assert strategy.x is None
        assert strategy.y is None
        assert strategy.text is None
        assert strategy.image == 'reference.png'

    def test_with_max_distance(self):
        """ClosestToStrategy with max_distance constraint."""
        strategy = ClosestToStrategy(x=100, y=200, max_distance=50)

        assert strategy.x == 100
        assert strategy.y == 200
        assert strategy.max_distance == 50

    def test_no_mode_specified_raises(self):
        """Should raise ValueError when no mode is specified."""
        with pytest.raises(ValueError) as exc_info:
            ClosestToStrategy()

        assert "exactly one of" in str(exc_info.value)

    def test_multiple_modes_raises(self):
        """Should raise ValueError when multiple modes specified."""
        with pytest.raises(ValueError) as exc_info:
            ClosestToStrategy(x=100, y=200, text='Label')

        assert "exactly one of" in str(exc_info.value)

    def test_only_x_raises(self):
        """Should raise ValueError when only x is specified.

        Note: The validation first checks that exactly one mode is set.
        Since only x (not both x,y) is provided, the coordinates mode isn't
        considered complete, so the 'exactly one of' error triggers first.
        """
        with pytest.raises(ValueError) as exc_info:
            ClosestToStrategy(x=100)

        # The first validation check triggers before the x/y pair check
        assert "exactly one of" in str(exc_info.value) or "x and y must both be specified" in str(exc_info.value)

    def test_only_y_raises(self):
        """Should raise ValueError when only y is specified.

        Note: The validation first checks that exactly one mode is set.
        Since only y (not both x,y) is provided, the coordinates mode isn't
        considered complete, so the 'exactly one of' error triggers first.
        """
        with pytest.raises(ValueError) as exc_info:
            ClosestToStrategy(y=200)

        # The first validation check triggers before the x/y pair check
        assert "exactly one of" in str(exc_info.value) or "x and y must both be specified" in str(exc_info.value)

    @pytest.mark.parametrize("max_dist", [0, -1, -100])
    def test_invalid_max_distance_raises(self, max_dist):
        """Should raise ValueError for non-positive max_distance."""
        with pytest.raises(ValueError) as exc_info:
            ClosestToStrategy(x=100, y=200, max_distance=max_dist)

        assert "max_distance must be positive" in str(exc_info.value)


class TestDirectionalStrategies:
    """Tests for directional strategy classes."""

    def test_top_left_strategy(self):
        """TopLeftStrategy is a simple marker class."""
        strategy = TopLeftStrategy()
        assert strategy is not None

    def test_top_right_strategy(self):
        """TopRightStrategy is a simple marker class."""
        strategy = TopRightStrategy()
        assert strategy is not None

    def test_bottom_left_strategy(self):
        """BottomLeftStrategy is a simple marker class."""
        strategy = BottomLeftStrategy()
        assert strategy is not None

    def test_bottom_right_strategy(self):
        """BottomRightStrategy is a simple marker class."""
        strategy = BottomRightStrategy()
        assert strategy is not None


class TestSizeStrategies:
    """Tests for size-based strategy classes."""

    def test_largest_strategy(self):
        """LargestStrategy is a simple marker class."""
        strategy = LargestStrategy()
        assert strategy is not None

    def test_smallest_strategy(self):
        """SmallestStrategy is a simple marker class."""
        strategy = SmallestStrategy()
        assert strategy is not None


class TestCaptureSpec:
    """Tests for CaptureSpec validation."""

    def test_valid_default_source(self):
        """Default source should be 'stdout'."""
        spec = CaptureSpec(variable='output')

        assert spec.variable == 'output'
        assert spec.source == 'stdout'
        assert spec.parser is None

    @pytest.mark.parametrize("source", ['stdout', 'stderr', 'returncode', 'all'])
    def test_valid_sources(self, source):
        """All valid source values should work."""
        spec = CaptureSpec(variable='output', source=source)
        assert spec.source == source

    def test_with_parser(self):
        """CaptureSpec with parser expression."""
        spec = CaptureSpec(
            variable='version',
            source='stdout',
            parser='output.split()[0]'
        )

        assert spec.variable == 'version'
        assert spec.parser == 'output.split()[0]'

    @pytest.mark.parametrize("invalid_source", ['stdin', 'output', 'result', 'STDOUT', ''])
    def test_invalid_source_raises(self, invalid_source):
        """Should raise ValueError for invalid source values."""
        with pytest.raises(ValueError) as exc_info:
            CaptureSpec(variable='output', source=invalid_source)

        assert "must be one of" in str(exc_info.value)


class TestVariableCondition:
    """Tests for VariableCondition validation."""

    def test_equals_operator(self):
        """Valid condition with equals operator."""
        cond = VariableCondition(variable='status', equals='success')

        assert cond.variable == 'status'
        assert cond.equals == 'success'

    def test_contains_operator(self):
        """Valid condition with contains operator."""
        cond = VariableCondition(variable='output', contains='error')

        assert cond.variable == 'output'
        assert cond.contains == 'error'

    def test_matches_operator(self):
        """Valid condition with matches (regex) operator."""
        cond = VariableCondition(variable='version', matches=r'\d+\.\d+')

        assert cond.variable == 'version'
        assert cond.matches == r'\d+\.\d+'

    def test_greater_than_operator(self):
        """Valid condition with greater_than operator."""
        cond = VariableCondition(variable='count', greater_than=10)

        assert cond.variable == 'count'
        assert cond.greater_than == 10

    def test_less_than_operator(self):
        """Valid condition with less_than operator."""
        cond = VariableCondition(variable='count', less_than=100)

        assert cond.variable == 'count'
        assert cond.less_than == 100

    def test_is_empty_true(self):
        """Valid condition with is_empty=True."""
        cond = VariableCondition(variable='result', is_empty=True)

        assert cond.variable == 'result'
        assert cond.is_empty is True

    def test_is_empty_false(self):
        """Valid condition with is_empty=False (check not empty)."""
        cond = VariableCondition(variable='result', is_empty=False)

        assert cond.variable == 'result'
        assert cond.is_empty is False

    def test_no_operator_raises(self):
        """Should raise ValueError when no operator is specified."""
        with pytest.raises(ValueError) as exc_info:
            VariableCondition(variable='status')

        assert "exactly one operator" in str(exc_info.value)

    def test_multiple_operators_raises(self):
        """Should raise ValueError when multiple operators specified."""
        with pytest.raises(ValueError) as exc_info:
            VariableCondition(variable='value', equals=5, greater_than=3)

        assert "exactly one operator" in str(exc_info.value)

    @pytest.mark.parametrize(
        "kwargs",
        [
            {'equals': 'a', 'contains': 'b'},
            {'matches': r'\d+', 'is_empty': True},
            {'greater_than': 5, 'less_than': 10},
            {'equals': 'x', 'greater_than': 1, 'less_than': 5},
        ],
    )
    def test_various_multiple_operators_raises(self, kwargs):
        """Various combinations of multiple operators should raise."""
        with pytest.raises(ValueError) as exc_info:
            VariableCondition(variable='test', **kwargs)

        assert "exactly one operator" in str(exc_info.value)


class TestWaitCondition:
    """Tests for WaitCondition validation and depth checking."""

    def test_exists_condition(self):
        """Valid WaitCondition with exists."""
        target = Target(text='Button')
        cond = WaitCondition(exists=target)

        assert cond.exists == target
        assert cond.not_exists is None
        assert cond.all is None
        assert cond.any is None
        assert cond.negate is None

    def test_not_exists_condition(self):
        """Valid WaitCondition with not_exists."""
        target = Target(image='loading.png')
        cond = WaitCondition(not_exists=target)

        assert cond.not_exists == target

    def test_all_condition(self):
        """Valid WaitCondition with all (AND logic)."""
        cond1 = WaitCondition(exists=Target(text='A'))
        cond2 = WaitCondition(exists=Target(text='B'))
        cond = WaitCondition(all=[cond1, cond2])

        assert cond.all == [cond1, cond2]

    def test_any_condition(self):
        """Valid WaitCondition with any (OR logic)."""
        cond1 = WaitCondition(exists=Target(text='A'))
        cond2 = WaitCondition(exists=Target(text='B'))
        cond = WaitCondition(any=[cond1, cond2])

        assert cond.any == [cond1, cond2]

    def test_negate_condition(self):
        """Valid WaitCondition with negate (NOT logic)."""
        inner = WaitCondition(exists=Target(text='Error'))
        cond = WaitCondition(negate=inner)

        assert cond.negate == inner

    def test_no_field_raises(self):
        """Should raise ValueError when no field is set."""
        with pytest.raises(ValueError) as exc_info:
            WaitCondition()

        assert "exactly one field" in str(exc_info.value)

    def test_multiple_fields_raises(self):
        """Should raise ValueError when multiple fields set."""
        target = Target(text='Button')
        with pytest.raises(ValueError) as exc_info:
            WaitCondition(exists=target, not_exists=target)

        assert "exactly one field" in str(exc_info.value)

    def test_validate_depth_passes(self):
        """Moderate nesting depth should pass validation."""
        # Create nested condition: 3 levels deep
        inner = WaitCondition(exists=Target(text='Deep'))
        mid = WaitCondition(negate=inner)
        outer = WaitCondition(negate=mid)

        # Should not raise
        outer.validate_depth()

    def test_validate_depth_with_all(self):
        """Nested all conditions should validate depth."""
        leaf1 = WaitCondition(exists=Target(text='A'))
        leaf2 = WaitCondition(exists=Target(text='B'))
        combined = WaitCondition(all=[leaf1, leaf2])

        # Should not raise
        combined.validate_depth()

    def test_validate_depth_with_any(self):
        """Nested any conditions should validate depth."""
        leaf1 = WaitCondition(exists=Target(text='A'))
        leaf2 = WaitCondition(exists=Target(text='B'))
        combined = WaitCondition(any=[leaf1, leaf2])

        # Should not raise
        combined.validate_depth()

    def test_validate_depth_exceeds_max(self):
        """Should raise ValueError when nesting exceeds max depth."""
        # Build a chain that exceeds depth 10
        cond = WaitCondition(exists=Target(text='Leaf'))
        for _ in range(12):
            cond = WaitCondition(negate=cond)

        with pytest.raises(ValueError) as exc_info:
            cond.validate_depth()

        assert "exceeds maximum depth" in str(exc_info.value)

    def test_validate_depth_custom_max(self):
        """Should respect custom max_depth parameter."""
        cond = WaitCondition(exists=Target(text='Leaf'))
        for _ in range(5):
            cond = WaitCondition(negate=cond)

        # Should pass with default max_depth=10
        cond.validate_depth()

        # Build deeper chain
        for _ in range(3):
            cond = WaitCondition(negate=cond)

        # Should fail with custom max_depth=5
        with pytest.raises(ValueError) as exc_info:
            cond.validate_depth(max_depth=5)

        assert "exceeds maximum depth" in str(exc_info.value)


class TestLoopAction:
    """Tests for LoopAction validation."""

    def test_loop_with_times(self):
        """Valid loop with times specified."""
        loop = LoopAction(actions=[], times=5)

        assert loop.times == 5
        assert loop.items is None

    def test_loop_with_items_list(self):
        """Valid loop with items list."""
        loop = LoopAction(actions=[], items=['a', 'b', 'c'])

        assert loop.times is None
        assert loop.items == ['a', 'b', 'c']

    def test_loop_with_items_variable(self):
        """Valid loop with items as variable reference."""
        loop = LoopAction(actions=[], items='{{my_list}}')

        assert loop.times is None
        assert loop.items == '{{my_list}}'

    def test_loop_with_item_var(self):
        """Loop with custom item variable name."""
        loop = LoopAction(actions=[], items=[1, 2, 3], item_var='num')

        assert loop.items == [1, 2, 3]
        assert loop.item_var == 'num'

    def test_loop_neither_times_nor_items_raises(self):
        """Should raise ValueError when neither times nor items specified."""
        with pytest.raises(ValueError) as exc_info:
            LoopAction(actions=[])

        assert "exactly one of: times or items" in str(exc_info.value)

    def test_loop_both_times_and_items_raises(self):
        """Should raise ValueError when both times and items specified."""
        with pytest.raises(ValueError) as exc_info:
            LoopAction(actions=[], times=3, items=['a', 'b'])

        assert "exactly one of: times or items" in str(exc_info.value)

    @pytest.mark.parametrize("invalid_times", [0, -1, -10])
    def test_loop_invalid_times_raises(self, invalid_times):
        """Should raise ValueError for times < 1."""
        with pytest.raises(ValueError) as exc_info:
            LoopAction(actions=[], times=invalid_times)

        assert "must be >= 1" in str(exc_info.value)

    def test_loop_times_one_valid(self):
        """Loop with times=1 should be valid."""
        loop = LoopAction(actions=[], times=1)
        assert loop.times == 1


class TestCommandAction:
    """Tests for CommandAction validation."""

    def test_valid_string_command(self):
        """CommandAction with valid string command."""
        action = CommandAction(command='ls -la')

        assert action.command == 'ls -la'
        assert action.shell is False
        assert action.admin is False
        assert action.background is False
        assert action.allow_failure is False

    def test_with_options(self):
        """CommandAction with various options."""
        capture = CaptureSpec(variable='output')
        action = CommandAction(
            command='npm install',
            name='Install deps',
            description='Install project dependencies',
            cwd='/app',
            env={'NODE_ENV': 'production'},
            timeout=120.0,
            shell=True,
            admin=True,
            background=False,
            capture=capture,
            allow_failure=True,
        )

        assert action.command == 'npm install'
        assert action.name == 'Install deps'
        assert action.cwd == '/app'
        assert action.env == {'NODE_ENV': 'production'}
        assert action.timeout == 120.0
        assert action.shell is True
        assert action.admin is True
        assert action.capture == capture
        assert action.allow_failure is True

    def test_list_command_raises(self):
        """Should raise ValueError when command is a list."""
        with pytest.raises(ValueError) as exc_info:
            CommandAction(command=['ls', '-la'])

        assert "must be a string, not a list" in str(exc_info.value)


class TestPullAction:
    """Tests for PullAction validation."""

    def test_valid_single_path(self):
        """PullAction with single path."""
        action = PullAction(src='/path/to/file.txt')

        assert action.src == '/path/to/file.txt'
        assert action.dst is None
        assert action.mode == 'hypervisor'

    def test_valid_list_of_paths(self):
        """PullAction with list of paths."""
        action = PullAction(src=['/path/a.txt', '/path/b.txt'])

        assert action.src == ['/path/a.txt', '/path/b.txt']

    def test_websocket_mode(self):
        """PullAction with websocket mode."""
        action = PullAction(src='/file.txt', mode='websocket')

        assert action.mode == 'websocket'

    @pytest.mark.parametrize("invalid_mode", ['http', 'ftp', 'ssh', 'HYPERVISOR', ''])
    def test_invalid_mode_raises(self, invalid_mode):
        """Should raise ValueError for invalid mode."""
        with pytest.raises(ValueError) as exc_info:
            PullAction(src='/file.txt', mode=invalid_mode)

        assert "must be one of" in str(exc_info.value)


class TestPullChangedFilesAction:
    """Tests for PullChangedFilesAction validation."""

    def test_valid_default(self):
        """PullChangedFilesAction with defaults."""
        action = PullChangedFilesAction(
            snapshot_before='snap_before',
            snapshot_after='snap_after',
        )

        assert action.snapshot_before == 'snap_before'
        assert action.snapshot_after == 'snap_after'
        assert action.dst == 'changed_files'
        assert action.mode == 'websocket'
        assert action.include_modified is True
        assert action.include_added is True

    def test_hypervisor_mode(self):
        """PullChangedFilesAction with hypervisor mode."""
        action = PullChangedFilesAction(
            snapshot_before='before',
            snapshot_after='after',
            mode='hypervisor',
        )

        assert action.mode == 'hypervisor'

    @pytest.mark.parametrize("invalid_mode", ['http', 'ftp', ''])
    def test_invalid_mode_raises(self, invalid_mode):
        """Should raise ValueError for invalid mode."""
        with pytest.raises(ValueError) as exc_info:
            PullChangedFilesAction(
                snapshot_before='before',
                snapshot_after='after',
                mode=invalid_mode,
            )

        assert "must be one of" in str(exc_info.value)

    def test_no_includes_raises(self):
        """Should raise when both include_modified and include_added are False."""
        with pytest.raises(ValueError) as exc_info:
            PullChangedFilesAction(
                snapshot_before='before',
                snapshot_after='after',
                include_modified=False,
                include_added=False,
            )

        assert "at least one of" in str(exc_info.value)

    def test_only_modified(self):
        """Valid with only include_modified=True."""
        action = PullChangedFilesAction(
            snapshot_before='before',
            snapshot_after='after',
            include_modified=True,
            include_added=False,
        )

        assert action.include_modified is True
        assert action.include_added is False

    def test_only_added(self):
        """Valid with only include_added=True."""
        action = PullChangedFilesAction(
            snapshot_before='before',
            snapshot_after='after',
            include_modified=False,
            include_added=True,
        )

        assert action.include_modified is False
        assert action.include_added is True


class TestWaitUntilAction:
    """Tests for WaitUntilAction validation."""

    def test_valid_with_defaults(self):
        """WaitUntilAction with default timeouts."""
        cond = WaitCondition(exists=Target(text='Ready'))
        action = WaitUntilAction(condition=cond)

        assert action.condition == cond
        assert action.timeout == 60.0
        assert action.check_interval == 0.0
        assert action.initial_delay == 5.0

    def test_custom_timeouts(self):
        """WaitUntilAction with custom timeouts."""
        cond = WaitCondition(exists=Target(text='Ready'))
        action = WaitUntilAction(
            condition=cond,
            timeout=120.0,
            check_interval=1.0,
            initial_delay=2.0,
        )

        assert action.timeout == 120.0
        assert action.check_interval == 1.0
        assert action.initial_delay == 2.0

    def test_validates_condition_depth(self):
        """WaitUntilAction should validate condition depth on creation."""
        # Build deeply nested condition
        cond = WaitCondition(exists=Target(text='Leaf'))
        for _ in range(12):
            cond = WaitCondition(negate=cond)

        with pytest.raises(ValueError) as exc_info:
            WaitUntilAction(condition=cond)

        assert "exceeds maximum depth" in str(exc_info.value)


class TestSimpleActions:
    """Tests for simple action types without complex validation."""

    def test_keyboard_action(self):
        """KeyboardAction fields."""
        action = KeyboardAction(key='enter', description='Press enter')

        assert action.key == 'enter'
        assert action.text is None
        assert action.combination is None
        assert action.description == 'Press enter'

    def test_keyboard_action_with_text(self):
        """KeyboardAction with text typing."""
        action = KeyboardAction(text='Hello World')

        assert action.key is None
        assert action.text == 'Hello World'

    def test_keyboard_action_with_combination(self):
        """KeyboardAction with key combination."""
        action = KeyboardAction(combination=['ctrl', 'c'])

        assert action.combination == ['ctrl', 'c']

    def test_click_action(self):
        """ClickAction fields."""
        target = Target(text='Button')
        action = ClickAction(target=target, type='double')

        assert action.target == target
        assert action.type == 'double'
        assert action.description == ''

    def test_click_action_defaults(self):
        """ClickAction default values."""
        action = ClickAction(target=Target())

        assert action.type == 'left'
        assert action.description == ''

    def test_drag_action(self):
        """DragAction fields."""
        src = Target(position=[100, 100])
        dst = Target(position=[200, 200])
        action = DragAction(src=src, dst=dst, description='Drag item')

        assert action.src == src
        assert action.dst == dst
        assert action.description == 'Drag item'

    def test_idle_action(self):
        """IdleAction fields."""
        action = IdleAction(duration=2.5, description='Wait a bit')

        assert action.duration == 2.5
        assert action.description == 'Wait a bit'

    def test_scroll_action(self):
        """ScrollAction fields."""
        action = ScrollAction(direction='down', amount=3)

        assert action.direction == 'down'
        assert action.amount == 3

    def test_goto_action(self):
        """GotoAction fields."""
        target = Target(text='Menu')
        action = GotoAction(target=target)

        assert action.target == target

    def test_action_test_action(self):
        """ActionTestAction fields."""
        action = ActionTestAction(name='validate_login')

        assert action.name == 'validate_login'
        assert action.description == ''

    def test_screenshot_action(self):
        """ScreenshotAction fields."""
        action = ScreenshotAction(
            name='login_screen',
            x=0,
            y=0,
            width=800,
            height=600,
        )

        assert action.name == 'login_screen'
        assert action.x == 0
        assert action.y == 0
        assert action.width == 800
        assert action.height == 600

    def test_save_timestamp_action(self):
        """SaveTimestampAction fields."""
        action = SaveTimestampAction(variable='start_time')

        assert action.variable == 'start_time'

    def test_save_variable_action(self):
        """SaveVariableAction fields."""
        action = SaveVariableAction(name='counter', value=42)

        assert action.name == 'counter'
        assert action.value == 42

    def test_pause_action(self):
        """PauseAction fields."""
        action = PauseAction(message='Check the screen', name='manual_check')

        assert action.message == 'Check the screen'
        assert action.name == 'manual_check'

    def test_stop_action(self):
        """StopAction fields."""
        cond = VariableCondition(variable='error', equals=True)
        action = StopAction(condition=cond)

        assert action.condition == cond

    def test_stop_action_unconditional(self):
        """StopAction without condition (unconditional stop)."""
        action = StopAction()

        assert action.condition is None

    def test_continue_action(self):
        """ContinueAction fields."""
        cond = VariableCondition(variable='skip', equals=True)
        action = ContinueAction(condition=cond)

        assert action.condition == cond

    def test_block_action(self):
        """BlockAction fields."""
        inner_action = IdleAction(duration=1.0)
        action = BlockAction(actions=[inner_action])

        assert len(action.actions) == 1
        assert action.when is None

    def test_snapshot_filesystem_action(self):
        """SnapshotFilesystemAction fields."""
        action = SnapshotFilesystemAction(
            variable='fs_snap',
            root_path='/home/user',
            timeout=600.0,
        )

        assert action.variable == 'fs_snap'
        assert action.root_path == '/home/user'
        assert action.timeout == 600.0


class TestConditionTypes:
    """Tests for condition types."""

    def test_exists_condition(self):
        """ExistsCondition fields."""
        cond = ExistsCondition(text='Welcome')

        assert cond.text == 'Welcome'
        assert cond.image is None

    def test_exists_condition_with_image(self):
        """ExistsCondition with image."""
        cond = ExistsCondition(image='icon.png')

        assert cond.text is None
        assert cond.image == 'icon.png'

    def test_not_exists_condition(self):
        """NotExistsCondition fields."""
        cond = NotExistsCondition(text='Error')

        assert cond.text == 'Error'
        assert cond.image is None


class TestPlaybook:
    """Tests for Playbook structure."""

    def test_minimal_playbook(self):
        """Playbook with minimal configuration."""
        playbook = Playbook(actions=[])

        assert playbook.actions == []
        assert isinstance(playbook.settings, Settings)
        assert playbook.variables is None
        assert playbook.tests == []

    def test_playbook_with_actions(self):
        """Playbook with actions list."""
        actions = [
            IdleAction(duration=1.0),
            KeyboardAction(key='enter'),
        ]
        playbook = Playbook(actions=actions)

        assert len(playbook.actions) == 2

    def test_playbook_with_custom_settings(self):
        """Playbook with custom settings."""
        settings = Settings(idle=0.5, timeout=30.0)
        playbook = Playbook(actions=[], settings=settings)

        assert playbook.settings.idle == 0.5
        assert playbook.settings.timeout == 30.0
