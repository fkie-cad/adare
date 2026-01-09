"""
Comprehensive unit tests for ActionExecutor.

Tests cover:
- ActionExecutor initialization
- set_test_loader() method
- execute_action() method - async action dispatch for all action types
- execute_programmatic_pull() method
- Variable resolution in execute_action
- ActionResult dataclass
"""

import pytest
import sys
from unittest.mock import MagicMock, AsyncMock, patch
from pathlib import Path
from dataclasses import asdict

# Mock libvirt_qemu and libvirt before any imports that might need it
sys.modules['libvirt_qemu'] = MagicMock()
sys.modules['libvirt'] = MagicMock()

from adare.backend.experiment.action_executor import ActionExecutor, ActionResult
from adare.types.playbook import (
    Playbook,
    Settings,
    ClickAction,
    DragAction,
    KeyboardAction,
    IdleAction,
    ScrollAction,
    GotoAction,
    ScreenshotAction,
    CommandAction,
    SaveTimestampAction,
    SaveVariableAction,
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
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_websocket_client():
    """Create a mock WebSocket client."""
    client = MagicMock()
    client.connected = True
    client.idle = AsyncMock()
    return client


@pytest.fixture
def mock_target_resolver():
    """Create a mock MCPTargetResolver."""
    resolver = MagicMock()
    resolver.resolve_target = AsyncMock(return_value=(100, 200))
    return resolver


@pytest.fixture
def mock_condition_checker():
    """Create a mock MCPConditionChecker."""
    checker = MagicMock()
    checker.check_conditions = AsyncMock(return_value=True)
    return checker


@pytest.fixture
def temp_experiment_dir(tmp_path):
    """Create a temporary experiment directory."""
    exp_dir = tmp_path / "experiment"
    exp_dir.mkdir()
    return exp_dir


@pytest.fixture
def temp_screenshots_dir(tmp_path):
    """Create a temporary screenshots directory."""
    screenshots_dir = tmp_path / "screenshots"
    screenshots_dir.mkdir()
    return screenshots_dir


@pytest.fixture
def simple_playbook():
    """Create a simple playbook with basic actions."""
    return Playbook(
        actions=[
            ClickAction(target=Target(position=[100, 100]), description="Click action"),
            IdleAction(duration=1.0, description="Wait"),
        ],
        settings=Settings(),
    )


@pytest.fixture
def mock_action_executor(mock_websocket_client, mock_target_resolver,
                         mock_condition_checker, temp_experiment_dir, simple_playbook):
    """Create an ActionExecutor with mocked dependencies."""
    # Mock all the specialized executors
    with patch('adare.backend.experiment.action_executor.TargetResolutionExecutor') as mock_target_res:
        with patch('adare.backend.experiment.action_executor.SimpleActionsExecutor') as mock_simple:
            with patch('adare.backend.experiment.action_executor.FlowControlExecutor') as mock_flow:
                with patch('adare.backend.experiment.action_executor.TestActionsExecutor') as mock_test:
                    # Configure mock returns
                    mock_target_res_instance = MagicMock()
                    mock_target_res.return_value = mock_target_res_instance

                    mock_simple_instance = MagicMock()
                    mock_simple_instance.gui_executor = MagicMock()
                    mock_simple.return_value = mock_simple_instance

                    mock_flow_instance = MagicMock()
                    mock_flow.return_value = mock_flow_instance

                    mock_test_instance = MagicMock()
                    mock_test.return_value = mock_test_instance

                    executor = ActionExecutor(
                        websocket_client=mock_websocket_client,
                        target_resolver=mock_target_resolver,
                        condition_checker=mock_condition_checker,
                        experiment_run_id="run-123",
                        playbook=simple_playbook,
                        execution_context={},
                        debug_screenshots=False,
                        screenshots_dir=None,
                        vm=None,
                        experiment_run_directory=temp_experiment_dir,
                        flow_console=None
                    )

                    # Store mock references for test assertions
                    executor._mock_target_resolution = mock_target_res_instance
                    executor._mock_simple_actions = mock_simple_instance
                    executor._mock_flow_control = mock_flow_instance
                    executor._mock_test_actions = mock_test_instance

                    return executor


# ============================================================================
# TestActionResult
# ============================================================================


class TestActionResult:
    """Tests for ActionResult dataclass."""

    def test_creation_with_minimal_fields(self):
        """ActionResult should be created with minimal required fields."""
        result = ActionResult(success=True, message="Done")

        assert result.success is True
        assert result.message == "Done"
        assert result.coordinates is None
        assert result.data is None
        assert result.execution_time is None

    def test_creation_with_all_fields(self):
        """ActionResult should support all optional fields."""
        result = ActionResult(
            success=False,
            message="Target not found",
            coordinates=(150, 250),
            data={"target": "button.png", "confidence": 0.85},
            execution_time=2.5
        )

        assert result.success is False
        assert result.message == "Target not found"
        assert result.coordinates == (150, 250)
        assert result.data == {"target": "button.png", "confidence": 0.85}
        assert result.execution_time == 2.5

    def test_is_dataclass(self):
        """ActionResult should be a proper dataclass."""
        result = ActionResult(success=True, message="OK")

        result_dict = asdict(result)
        assert isinstance(result_dict, dict)
        assert "success" in result_dict
        assert "message" in result_dict
        assert "coordinates" in result_dict
        assert "data" in result_dict
        assert "execution_time" in result_dict

    def test_default_message_is_empty_string(self):
        """ActionResult message should default to empty string."""
        result = ActionResult(success=True)

        assert result.message == ""

    def test_coordinates_tuple(self):
        """ActionResult coordinates should store tuple correctly."""
        result = ActionResult(
            success=True,
            message="Click completed",
            coordinates=(512, 384)
        )

        assert result.coordinates == (512, 384)
        assert result.coordinates[0] == 512
        assert result.coordinates[1] == 384

    def test_data_dict(self):
        """ActionResult data should store dict correctly."""
        data = {
            "screenshot_path": "/tmp/screenshot.png",
            "target_info": {"type": "image", "name": "button.png"},
            "timing": 1.234
        }
        result = ActionResult(success=True, message="Screenshot saved", data=data)

        assert result.data == data
        assert result.data["screenshot_path"] == "/tmp/screenshot.png"


# ============================================================================
# TestActionExecutorInit
# ============================================================================


class TestActionExecutorInit:
    """Tests for ActionExecutor initialization."""

    def test_basic_initialization(self, mock_websocket_client, mock_target_resolver,
                                   mock_condition_checker, temp_experiment_dir, simple_playbook):
        """ActionExecutor should initialize with basic parameters."""
        with patch('adare.backend.experiment.action_executor.TargetResolutionExecutor'):
            with patch('adare.backend.experiment.action_executor.SimpleActionsExecutor') as mock_simple:
                mock_simple.return_value.gui_executor = MagicMock()
                with patch('adare.backend.experiment.action_executor.FlowControlExecutor'):
                    with patch('adare.backend.experiment.action_executor.TestActionsExecutor'):
                        executor = ActionExecutor(
                            websocket_client=mock_websocket_client,
                            target_resolver=mock_target_resolver,
                            condition_checker=mock_condition_checker,
                        )

        assert executor.client == mock_websocket_client
        assert executor.target_resolver == mock_target_resolver
        assert executor.condition_checker == mock_condition_checker

    def test_default_values(self, mock_websocket_client, mock_target_resolver,
                             mock_condition_checker):
        """ActionExecutor should have correct default values."""
        with patch('adare.backend.experiment.action_executor.TargetResolutionExecutor'):
            with patch('adare.backend.experiment.action_executor.SimpleActionsExecutor') as mock_simple:
                mock_simple.return_value.gui_executor = MagicMock()
                with patch('adare.backend.experiment.action_executor.FlowControlExecutor'):
                    with patch('adare.backend.experiment.action_executor.TestActionsExecutor'):
                        executor = ActionExecutor(
                            websocket_client=mock_websocket_client,
                            target_resolver=mock_target_resolver,
                            condition_checker=mock_condition_checker,
                        )

        assert executor.experiment_run_id is None
        assert executor.playbook is None
        assert executor.execution_context == {}
        assert executor.debug_screenshots is False
        assert executor.screenshots_dir is None
        assert executor.vm is None
        assert executor.experiment_run_directory is None
        assert executor.flow_console is None

    def test_with_all_parameters(self, mock_websocket_client, mock_target_resolver,
                                  mock_condition_checker, temp_experiment_dir,
                                  temp_screenshots_dir, simple_playbook):
        """ActionExecutor should accept all parameters."""
        mock_vm = MagicMock()
        mock_flow_console = MagicMock()
        execution_context = {"config": {"setting": "value"}}

        with patch('adare.backend.experiment.action_executor.TargetResolutionExecutor'):
            with patch('adare.backend.experiment.action_executor.SimpleActionsExecutor') as mock_simple:
                mock_simple.return_value.gui_executor = MagicMock()
                with patch('adare.backend.experiment.action_executor.FlowControlExecutor'):
                    with patch('adare.backend.experiment.action_executor.TestActionsExecutor'):
                        executor = ActionExecutor(
                            websocket_client=mock_websocket_client,
                            target_resolver=mock_target_resolver,
                            condition_checker=mock_condition_checker,
                            experiment_run_id="run-123",
                            playbook=simple_playbook,
                            execution_context=execution_context,
                            debug_screenshots=True,
                            screenshots_dir=temp_screenshots_dir,
                            vm=mock_vm,
                            experiment_run_directory=temp_experiment_dir,
                            flow_console=mock_flow_console
                        )

        assert executor.experiment_run_id == "run-123"
        assert executor.playbook == simple_playbook
        assert executor.execution_context == execution_context
        assert executor.debug_screenshots is True
        assert executor.screenshots_dir == temp_screenshots_dir
        assert executor.vm == mock_vm
        assert executor.experiment_run_directory == temp_experiment_dir
        assert executor.flow_console == mock_flow_console

    def test_specialized_executors_initialized(self, mock_websocket_client, mock_target_resolver,
                                                mock_condition_checker):
        """ActionExecutor should initialize all specialized executors."""
        with patch('adare.backend.experiment.action_executor.TargetResolutionExecutor') as mock_target_res:
            with patch('adare.backend.experiment.action_executor.SimpleActionsExecutor') as mock_simple:
                mock_simple.return_value.gui_executor = MagicMock()
                with patch('adare.backend.experiment.action_executor.FlowControlExecutor') as mock_flow:
                    with patch('adare.backend.experiment.action_executor.TestActionsExecutor') as mock_test:
                        executor = ActionExecutor(
                            websocket_client=mock_websocket_client,
                            target_resolver=mock_target_resolver,
                            condition_checker=mock_condition_checker,
                        )

        mock_target_res.assert_called_once()
        mock_simple.assert_called_once()
        mock_flow.assert_called_once()
        mock_test.assert_called_once()

    def test_execution_context_shared_between_executors(self, mock_websocket_client, mock_target_resolver,
                                                         mock_condition_checker):
        """Execution context should be the same reference for SimpleActions and FlowControl."""
        execution_context = {"shared": "value"}

        with patch('adare.backend.experiment.action_executor.TargetResolutionExecutor'):
            with patch('adare.backend.experiment.action_executor.SimpleActionsExecutor') as mock_simple:
                mock_simple.return_value.gui_executor = MagicMock()
                with patch('adare.backend.experiment.action_executor.FlowControlExecutor') as mock_flow:
                    with patch('adare.backend.experiment.action_executor.TestActionsExecutor'):
                        executor = ActionExecutor(
                            websocket_client=mock_websocket_client,
                            target_resolver=mock_target_resolver,
                            condition_checker=mock_condition_checker,
                            execution_context=execution_context,
                        )

        # Check that both executors received the same execution_context reference
        simple_call_kwargs = mock_simple.call_args.kwargs
        flow_call_kwargs = mock_flow.call_args.kwargs

        assert 'execution_context' in simple_call_kwargs
        assert 'execution_context' in flow_call_kwargs
        # They should be the same object reference
        assert simple_call_kwargs['execution_context'] is flow_call_kwargs['execution_context']


# ============================================================================
# TestSetTestLoader
# ============================================================================


class TestSetTestLoader:
    """Tests for set_test_loader method."""

    def test_set_test_loader(self, mock_action_executor):
        """set_test_loader should set the test loader on the test_actions executor."""
        mock_test_loader = MagicMock()

        mock_action_executor.set_test_loader(mock_test_loader)

        # Verify test_actions.set_test_loader was called
        mock_action_executor._mock_test_actions.set_test_loader.assert_called_once_with(mock_test_loader)

    def test_set_test_loader_stores_reference(self, mock_action_executor):
        """set_test_loader should store reference for backward compatibility."""
        mock_test_loader = MagicMock()

        mock_action_executor.set_test_loader(mock_test_loader)

        assert mock_action_executor.test_loader == mock_test_loader


# ============================================================================
# TestExecuteActionDispatch
# ============================================================================


class TestExecuteActionDispatch:
    """Tests for execute_action method - action type dispatch."""

    @pytest.mark.asyncio
    async def test_dispatch_click_action(self, mock_action_executor):
        """ClickAction should dispatch to simple_actions.execute_click."""
        action = ClickAction(target=Target(position=[100, 200]), description="Test click")
        mock_action_executor._mock_simple_actions.execute_click = AsyncMock(
            return_value=ActionResult(success=True, message="Click executed")
        )

        result = await mock_action_executor.execute_action(action)

        mock_action_executor._mock_simple_actions.execute_click.assert_called_once()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_dispatch_drag_action(self, mock_action_executor):
        """DragAction should dispatch to simple_actions.execute_drag."""
        action = DragAction(
            src=Target(position=[100, 100]),
            dst=Target(position=[200, 200]),
            description="Test drag"
        )
        mock_action_executor._mock_simple_actions.execute_drag = AsyncMock(
            return_value=ActionResult(success=True, message="Drag executed")
        )

        result = await mock_action_executor.execute_action(action)

        mock_action_executor._mock_simple_actions.execute_drag.assert_called_once()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_dispatch_keyboard_action(self, mock_action_executor):
        """KeyboardAction should dispatch to simple_actions.execute_keyboard."""
        action = KeyboardAction(text="hello", description="Test keyboard")
        mock_action_executor._mock_simple_actions.execute_keyboard = AsyncMock(
            return_value=ActionResult(success=True, message="Keyboard executed")
        )

        result = await mock_action_executor.execute_action(action)

        mock_action_executor._mock_simple_actions.execute_keyboard.assert_called_once()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_dispatch_idle_action(self, mock_action_executor):
        """IdleAction should dispatch to simple_actions.execute_idle."""
        action = IdleAction(duration=1.5, description="Test idle")
        mock_action_executor._mock_simple_actions.execute_idle = AsyncMock(
            return_value=ActionResult(success=True, message="Idle executed")
        )

        result = await mock_action_executor.execute_action(action)

        mock_action_executor._mock_simple_actions.execute_idle.assert_called_once()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_dispatch_scroll_action(self, mock_action_executor):
        """ScrollAction should dispatch to simple_actions.execute_scroll."""
        action = ScrollAction(direction="down", amount=3, description="Test scroll")
        mock_action_executor._mock_simple_actions.execute_scroll = AsyncMock(
            return_value=ActionResult(success=True, message="Scroll executed")
        )

        result = await mock_action_executor.execute_action(action)

        mock_action_executor._mock_simple_actions.execute_scroll.assert_called_once()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_dispatch_goto_action(self, mock_action_executor):
        """GotoAction should dispatch to simple_actions.execute_goto."""
        action = GotoAction(target=Target(position=[300, 400]), description="Test goto")
        mock_action_executor._mock_simple_actions.execute_goto = AsyncMock(
            return_value=ActionResult(success=True, message="Goto executed")
        )

        result = await mock_action_executor.execute_action(action)

        mock_action_executor._mock_simple_actions.execute_goto.assert_called_once()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_dispatch_screenshot_action(self, mock_action_executor):
        """ScreenshotAction should dispatch to simple_actions.execute_screenshot."""
        action = ScreenshotAction(description="Test screenshot", name="test_screenshot")
        mock_action_executor._mock_simple_actions.execute_screenshot = AsyncMock(
            return_value=ActionResult(success=True, message="Screenshot executed")
        )

        result = await mock_action_executor.execute_action(action)

        mock_action_executor._mock_simple_actions.execute_screenshot.assert_called_once()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_dispatch_command_action(self, mock_action_executor):
        """CommandAction should dispatch to simple_actions.execute_command."""
        action = CommandAction(command="echo hello", description="Test command")
        mock_action_executor._mock_simple_actions.execute_command = AsyncMock(
            return_value=ActionResult(success=True, message="Command executed")
        )

        result = await mock_action_executor.execute_action(action)

        mock_action_executor._mock_simple_actions.execute_command.assert_called_once()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_dispatch_save_timestamp_action(self, mock_action_executor):
        """SaveTimestampAction should dispatch to simple_actions.execute_save_timestamp."""
        action = SaveTimestampAction(variable="my_timestamp", description="Test save timestamp")
        mock_action_executor._mock_simple_actions.execute_save_timestamp = AsyncMock(
            return_value=ActionResult(success=True, message="Timestamp saved")
        )

        result = await mock_action_executor.execute_action(action)

        mock_action_executor._mock_simple_actions.execute_save_timestamp.assert_called_once()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_dispatch_save_variable_action(self, mock_action_executor):
        """SaveVariableAction should dispatch to simple_actions.execute_save_variable."""
        action = SaveVariableAction(name="my_var", value="test_value", description="Test save variable")
        mock_action_executor._mock_simple_actions.execute_save_variable = AsyncMock(
            return_value=ActionResult(success=True, message="Variable saved")
        )

        result = await mock_action_executor.execute_action(action)

        mock_action_executor._mock_simple_actions.execute_save_variable.assert_called_once()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_dispatch_pull_action(self, mock_action_executor):
        """PullAction should dispatch to simple_actions.execute_pull."""
        action = PullAction(src="/path/to/file", description="Test pull")
        mock_action_executor._mock_simple_actions.execute_pull = AsyncMock(
            return_value=ActionResult(success=True, message="Pull executed")
        )

        result = await mock_action_executor.execute_action(action)

        mock_action_executor._mock_simple_actions.execute_pull.assert_called_once()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_dispatch_action_test_action(self, mock_action_executor):
        """ActionTestAction should dispatch to test_actions.execute_test."""
        action = ActionTestAction(name="test_file_exists", description="Test action test")
        mock_action_executor._mock_test_actions.execute_test = AsyncMock(
            return_value=ActionResult(success=True, message="Test executed")
        )

        result = await mock_action_executor.execute_action(action)

        mock_action_executor._mock_test_actions.execute_test.assert_called_once()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_dispatch_block_action(self, mock_action_executor):
        """BlockAction should dispatch to flow_control.execute_block."""
        action = BlockAction(
            actions=[IdleAction(duration=0.5)],
            description="Test block"
        )
        mock_action_executor._mock_flow_control.execute_block = AsyncMock(
            return_value=ActionResult(success=True, message="Block executed")
        )

        result = await mock_action_executor.execute_action(action)

        mock_action_executor._mock_flow_control.execute_block.assert_called_once()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_dispatch_loop_action(self, mock_action_executor):
        """LoopAction should dispatch to flow_control.execute_loop."""
        action = LoopAction(
            actions=[IdleAction(duration=0.1)],
            times=3,
            description="Test loop"
        )
        mock_action_executor._mock_flow_control.execute_loop = AsyncMock(
            return_value=ActionResult(success=True, message="Loop executed")
        )

        result = await mock_action_executor.execute_action(action)

        mock_action_executor._mock_flow_control.execute_loop.assert_called_once()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_dispatch_wait_until_action(self, mock_action_executor):
        """WaitUntilAction should dispatch to flow_control.execute_wait_until."""
        action = WaitUntilAction(
            condition=WaitCondition(exists=Target(text="Ready")),
            timeout=30.0,
            description="Test wait until"
        )
        mock_action_executor._mock_flow_control.execute_wait_until = AsyncMock(
            return_value=ActionResult(success=True, message="Wait until executed")
        )

        result = await mock_action_executor.execute_action(action)

        mock_action_executor._mock_flow_control.execute_wait_until.assert_called_once()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_dispatch_pause_action(self, mock_action_executor):
        """PauseAction should dispatch to flow_control.execute_pause."""
        action = PauseAction(message="Debug pause", description="Test pause")
        mock_action_executor._mock_flow_control.execute_pause = AsyncMock(
            return_value=ActionResult(success=True, message="Pause executed")
        )

        result = await mock_action_executor.execute_action(action)

        mock_action_executor._mock_flow_control.execute_pause.assert_called_once()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_dispatch_stop_action(self, mock_action_executor):
        """StopAction should dispatch to flow_control.execute_stop."""
        action = StopAction(description="Test stop")
        mock_action_executor._mock_flow_control.execute_stop = AsyncMock(
            return_value=ActionResult(success=True, message="Stop executed")
        )

        result = await mock_action_executor.execute_action(action)

        mock_action_executor._mock_flow_control.execute_stop.assert_called_once()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_dispatch_continue_action(self, mock_action_executor):
        """ContinueAction should dispatch to flow_control.execute_continue."""
        action = ContinueAction(description="Test continue")
        mock_action_executor._mock_flow_control.execute_continue = AsyncMock(
            return_value=ActionResult(success=True, message="Continue executed")
        )

        result = await mock_action_executor.execute_action(action)

        mock_action_executor._mock_flow_control.execute_continue.assert_called_once()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_dispatch_snapshot_filesystem_action(self, mock_action_executor):
        """SnapshotFilesystemAction should dispatch to simple_actions.execute_snapshot_filesystem."""
        action = SnapshotFilesystemAction(variable="fs_snapshot", description="Test snapshot filesystem")
        mock_action_executor._mock_simple_actions.execute_snapshot_filesystem = AsyncMock(
            return_value=ActionResult(success=True, message="Snapshot filesystem executed")
        )

        result = await mock_action_executor.execute_action(action)

        mock_action_executor._mock_simple_actions.execute_snapshot_filesystem.assert_called_once()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_dispatch_pull_changed_files_action(self, mock_action_executor):
        """PullChangedFilesAction should dispatch to simple_actions.execute_pull_changed_files."""
        action = PullChangedFilesAction(
            snapshot_before="before_snap",
            snapshot_after="after_snap",
            description="Test pull changed files"
        )
        mock_action_executor._mock_simple_actions.execute_pull_changed_files = AsyncMock(
            return_value=ActionResult(success=True, message="Pull changed files executed")
        )

        result = await mock_action_executor.execute_action(action)

        mock_action_executor._mock_simple_actions.execute_pull_changed_files.assert_called_once()
        assert result.success is True

    @pytest.mark.asyncio
    async def test_dispatch_unknown_action_type(self, mock_action_executor):
        """Unknown action type should return error ActionResult."""
        # Create a mock unknown action
        class UnknownAction:
            description = "Unknown action"

        action = UnknownAction()

        result = await mock_action_executor.execute_action(action)

        assert result.success is False
        assert "Unknown action type" in result.message
        assert "UnknownAction" in result.message


# ============================================================================
# TestExecuteActionWithVariableResolution
# ============================================================================


class TestExecuteActionWithVariableResolution:
    """Tests for execute_action with variable resolution."""

    @pytest.mark.asyncio
    async def test_variable_resolver_called_when_provided(self, mock_action_executor):
        """Variable resolver should be called when provided."""
        action = ClickAction(target=Target(position=[100, 200]))
        mock_variable_resolver = MagicMock()
        mock_variable_resolver.resolve_action_variables.return_value = action

        mock_action_executor._mock_simple_actions.execute_click = AsyncMock(
            return_value=ActionResult(success=True, message="Click executed")
        )

        await mock_action_executor.execute_action(
            action,
            variable_resolver=mock_variable_resolver
        )

        mock_variable_resolver.resolve_action_variables.assert_called_once_with(
            action, mock_action_executor.execution_context
        )

    @pytest.mark.asyncio
    async def test_action_not_modified_without_variable_resolver(self, mock_action_executor):
        """Action should not be modified without variable resolver."""
        action = ClickAction(target=Target(position=[100, 200]), description="Original")
        mock_action_executor._mock_simple_actions.execute_click = AsyncMock(
            return_value=ActionResult(success=True, message="Click executed")
        )

        await mock_action_executor.execute_action(action)

        # Verify original action was passed (not modified)
        call_args = mock_action_executor._mock_simple_actions.execute_click.call_args
        passed_action = call_args[0][0]
        assert passed_action.description == "Original"

    @pytest.mark.asyncio
    async def test_resolved_action_used_in_dispatch(self, mock_action_executor):
        """Resolved action should be used in dispatch."""
        original_action = ClickAction(target=Target(position=[100, 200]), description="Original")
        resolved_action = ClickAction(target=Target(position=[300, 400]), description="Resolved")

        mock_variable_resolver = MagicMock()
        mock_variable_resolver.resolve_action_variables.return_value = resolved_action

        mock_action_executor._mock_simple_actions.execute_click = AsyncMock(
            return_value=ActionResult(success=True, message="Click executed")
        )

        await mock_action_executor.execute_action(
            original_action,
            variable_resolver=mock_variable_resolver
        )

        # Verify resolved action was passed
        call_args = mock_action_executor._mock_simple_actions.execute_click.call_args
        passed_action = call_args[0][0]
        assert passed_action.description == "Resolved"
        assert passed_action.target.position == [300, 400]


# ============================================================================
# TestExecuteActionEventParameters
# ============================================================================


class TestExecuteActionEventParameters:
    """Tests for execute_action event parameters."""

    @pytest.mark.asyncio
    async def test_parent_event_id_passed_to_executor(self, mock_action_executor):
        """parent_event_id should be passed to executor."""
        action = ClickAction(target=Target(position=[100, 200]))
        mock_action_executor._mock_simple_actions.execute_click = AsyncMock(
            return_value=ActionResult(success=True, message="Click executed")
        )

        await mock_action_executor.execute_action(action, parent_event_id="event-123")

        call_args = mock_action_executor._mock_simple_actions.execute_click.call_args
        assert call_args[0][1] == "event-123"

    @pytest.mark.asyncio
    async def test_event_emitter_passed_to_executor(self, mock_action_executor):
        """event_emitter should be passed to executor."""
        action = ClickAction(target=Target(position=[100, 200]))
        mock_event_emitter = MagicMock()
        mock_action_executor._mock_simple_actions.execute_click = AsyncMock(
            return_value=ActionResult(success=True, message="Click executed")
        )

        await mock_action_executor.execute_action(action, event_emitter=mock_event_emitter)

        call_args = mock_action_executor._mock_simple_actions.execute_click.call_args
        assert call_args[0][2] == mock_event_emitter


# ============================================================================
# TestExecuteActionExceptionHandling
# ============================================================================


class TestExecuteActionExceptionHandling:
    """Tests for execute_action exception handling."""

    @pytest.mark.asyncio
    async def test_exception_returns_failure_result(self, mock_action_executor):
        """Exception during execution should return failure ActionResult."""
        action = ClickAction(target=Target(position=[100, 200]))
        mock_action_executor._mock_simple_actions.execute_click = AsyncMock(
            side_effect=ValueError("Test error")
        )

        result = await mock_action_executor.execute_action(action)

        assert result.success is False
        assert "Exception" in result.message
        assert "Test error" in result.message

    @pytest.mark.asyncio
    async def test_exception_message_contains_error_details(self, mock_action_executor):
        """Exception message should contain error details."""
        action = IdleAction(duration=1.0)
        mock_action_executor._mock_simple_actions.execute_idle = AsyncMock(
            side_effect=RuntimeError("Connection timeout")
        )

        result = await mock_action_executor.execute_action(action)

        assert result.success is False
        assert "Connection timeout" in result.message


# ============================================================================
# TestExecuteActionDebugScreenshots
# ============================================================================


class TestExecuteActionDebugScreenshots:
    """Tests for execute_action debug screenshots feature."""

    @pytest.mark.asyncio
    async def test_debug_screenshot_captured_for_gui_action(self, mock_action_executor):
        """Debug screenshot should be captured for successful GUI actions."""
        mock_action_executor.debug_screenshots = True
        action = ClickAction(target=Target(position=[100, 200]))
        mock_action_executor._mock_simple_actions.execute_click = AsyncMock(
            return_value=ActionResult(success=True, message="Click executed")
        )
        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path = AsyncMock()

        await mock_action_executor.execute_action(action)

        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path.assert_called_once()

    @pytest.mark.asyncio
    async def test_debug_screenshot_not_captured_for_failed_action(self, mock_action_executor):
        """Debug screenshot should not be captured for failed actions."""
        mock_action_executor.debug_screenshots = True
        action = ClickAction(target=Target(position=[100, 200]))
        mock_action_executor._mock_simple_actions.execute_click = AsyncMock(
            return_value=ActionResult(success=False, message="Click failed")
        )
        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path = AsyncMock()

        await mock_action_executor.execute_action(action)

        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path.assert_not_called()

    @pytest.mark.asyncio
    async def test_debug_screenshot_not_captured_for_non_gui_action(self, mock_action_executor):
        """Debug screenshot should not be captured for non-GUI actions."""
        mock_action_executor.debug_screenshots = True
        action = IdleAction(duration=1.0)
        mock_action_executor._mock_simple_actions.execute_idle = AsyncMock(
            return_value=ActionResult(success=True, message="Idle executed")
        )
        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path = AsyncMock()

        await mock_action_executor.execute_action(action)

        # IdleAction is in non_gui_actions list, so no screenshot
        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path.assert_not_called()

    @pytest.mark.asyncio
    async def test_debug_screenshot_not_captured_when_disabled(self, mock_action_executor):
        """Debug screenshot should not be captured when debug_screenshots is False."""
        mock_action_executor.debug_screenshots = False
        action = ClickAction(target=Target(position=[100, 200]))
        mock_action_executor._mock_simple_actions.execute_click = AsyncMock(
            return_value=ActionResult(success=True, message="Click executed")
        )
        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path = AsyncMock()

        await mock_action_executor.execute_action(action)

        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path.assert_not_called()

    @pytest.mark.asyncio
    async def test_screenshot_failure_does_not_fail_action(self, mock_action_executor):
        """Screenshot capture failure should not fail the action."""
        mock_action_executor.debug_screenshots = True
        action = ClickAction(target=Target(position=[100, 200]))
        mock_action_executor._mock_simple_actions.execute_click = AsyncMock(
            return_value=ActionResult(success=True, message="Click executed")
        )
        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path = AsyncMock(
            side_effect=IOError("Failed to capture screenshot")
        )

        result = await mock_action_executor.execute_action(action)

        # Action should still succeed despite screenshot failure
        assert result.success is True
        assert result.message == "Click executed"


# ============================================================================
# TestExecuteActionNonGuiActions
# ============================================================================


class TestExecuteActionNonGuiActions:
    """Tests for non-GUI actions that should not trigger debug screenshots."""

    @pytest.mark.asyncio
    async def test_save_timestamp_is_non_gui(self, mock_action_executor):
        """SaveTimestampAction should be treated as non-GUI action."""
        mock_action_executor.debug_screenshots = True
        action = SaveTimestampAction(variable="ts")
        mock_action_executor._mock_simple_actions.execute_save_timestamp = AsyncMock(
            return_value=ActionResult(success=True, message="Timestamp saved")
        )
        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path = AsyncMock()

        await mock_action_executor.execute_action(action)

        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path.assert_not_called()

    @pytest.mark.asyncio
    async def test_save_variable_is_non_gui(self, mock_action_executor):
        """SaveVariableAction should be treated as non-GUI action."""
        mock_action_executor.debug_screenshots = True
        action = SaveVariableAction(name="var", value="value")
        mock_action_executor._mock_simple_actions.execute_save_variable = AsyncMock(
            return_value=ActionResult(success=True, message="Variable saved")
        )
        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path = AsyncMock()

        await mock_action_executor.execute_action(action)

        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path.assert_not_called()

    @pytest.mark.asyncio
    async def test_pull_action_is_non_gui(self, mock_action_executor):
        """PullAction should be treated as non-GUI action."""
        mock_action_executor.debug_screenshots = True
        action = PullAction(src="/path/to/file")
        mock_action_executor._mock_simple_actions.execute_pull = AsyncMock(
            return_value=ActionResult(success=True, message="Pull executed")
        )
        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path = AsyncMock()

        await mock_action_executor.execute_action(action)

        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path.assert_not_called()

    @pytest.mark.asyncio
    async def test_block_action_is_non_gui(self, mock_action_executor):
        """BlockAction should be treated as non-GUI action."""
        mock_action_executor.debug_screenshots = True
        action = BlockAction(actions=[IdleAction(duration=0.1)])
        mock_action_executor._mock_flow_control.execute_block = AsyncMock(
            return_value=ActionResult(success=True, message="Block executed")
        )
        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path = AsyncMock()

        await mock_action_executor.execute_action(action)

        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path.assert_not_called()

    @pytest.mark.asyncio
    async def test_loop_action_is_non_gui(self, mock_action_executor):
        """LoopAction should be treated as non-GUI action."""
        mock_action_executor.debug_screenshots = True
        action = LoopAction(actions=[IdleAction(duration=0.1)], times=2)
        mock_action_executor._mock_flow_control.execute_loop = AsyncMock(
            return_value=ActionResult(success=True, message="Loop executed")
        )
        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path = AsyncMock()

        await mock_action_executor.execute_action(action)

        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path.assert_not_called()

    @pytest.mark.asyncio
    async def test_pause_action_is_non_gui(self, mock_action_executor):
        """PauseAction should be treated as non-GUI action."""
        mock_action_executor.debug_screenshots = True
        action = PauseAction(message="Pause")
        mock_action_executor._mock_flow_control.execute_pause = AsyncMock(
            return_value=ActionResult(success=True, message="Pause executed")
        )
        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path = AsyncMock()

        await mock_action_executor.execute_action(action)

        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_action_is_non_gui(self, mock_action_executor):
        """StopAction should be treated as non-GUI action."""
        mock_action_executor.debug_screenshots = True
        action = StopAction()
        mock_action_executor._mock_flow_control.execute_stop = AsyncMock(
            return_value=ActionResult(success=True, message="Stop executed")
        )
        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path = AsyncMock()

        await mock_action_executor.execute_action(action)

        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path.assert_not_called()

    @pytest.mark.asyncio
    async def test_continue_action_is_non_gui(self, mock_action_executor):
        """ContinueAction should be treated as non-GUI action."""
        mock_action_executor.debug_screenshots = True
        action = ContinueAction()
        mock_action_executor._mock_flow_control.execute_continue = AsyncMock(
            return_value=ActionResult(success=True, message="Continue executed")
        )
        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path = AsyncMock()

        await mock_action_executor.execute_action(action)

        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path.assert_not_called()


# ============================================================================
# TestExecuteActionGuiActions
# ============================================================================


class TestExecuteActionGuiActions:
    """Tests for GUI actions that should trigger debug screenshots."""

    @pytest.mark.asyncio
    async def test_click_action_is_gui(self, mock_action_executor):
        """ClickAction should be treated as GUI action."""
        mock_action_executor.debug_screenshots = True
        action = ClickAction(target=Target(position=[100, 200]))
        mock_action_executor._mock_simple_actions.execute_click = AsyncMock(
            return_value=ActionResult(success=True, message="Click executed")
        )
        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path = AsyncMock()

        await mock_action_executor.execute_action(action)

        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path.assert_called_once()

    @pytest.mark.asyncio
    async def test_keyboard_action_is_gui(self, mock_action_executor):
        """KeyboardAction should be treated as GUI action."""
        mock_action_executor.debug_screenshots = True
        action = KeyboardAction(text="hello")
        mock_action_executor._mock_simple_actions.execute_keyboard = AsyncMock(
            return_value=ActionResult(success=True, message="Keyboard executed")
        )
        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path = AsyncMock()

        await mock_action_executor.execute_action(action)

        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path.assert_called_once()

    @pytest.mark.asyncio
    async def test_scroll_action_is_gui(self, mock_action_executor):
        """ScrollAction should be treated as GUI action."""
        mock_action_executor.debug_screenshots = True
        action = ScrollAction(direction="down", amount=3)
        mock_action_executor._mock_simple_actions.execute_scroll = AsyncMock(
            return_value=ActionResult(success=True, message="Scroll executed")
        )
        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path = AsyncMock()

        await mock_action_executor.execute_action(action)

        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path.assert_called_once()

    @pytest.mark.asyncio
    async def test_goto_action_is_gui(self, mock_action_executor):
        """GotoAction should be treated as GUI action."""
        mock_action_executor.debug_screenshots = True
        action = GotoAction(target=Target(position=[300, 400]))
        mock_action_executor._mock_simple_actions.execute_goto = AsyncMock(
            return_value=ActionResult(success=True, message="Goto executed")
        )
        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path = AsyncMock()

        await mock_action_executor.execute_action(action)

        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path.assert_called_once()

    @pytest.mark.asyncio
    async def test_drag_action_is_gui(self, mock_action_executor):
        """DragAction should be treated as GUI action."""
        mock_action_executor.debug_screenshots = True
        action = DragAction(src=Target(position=[100, 100]), dst=Target(position=[200, 200]))
        mock_action_executor._mock_simple_actions.execute_drag = AsyncMock(
            return_value=ActionResult(success=True, message="Drag executed")
        )
        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path = AsyncMock()

        await mock_action_executor.execute_action(action)

        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path.assert_called_once()

    @pytest.mark.asyncio
    async def test_screenshot_action_is_gui(self, mock_action_executor):
        """ScreenshotAction should be treated as GUI action."""
        mock_action_executor.debug_screenshots = True
        action = ScreenshotAction(name="test")
        mock_action_executor._mock_simple_actions.execute_screenshot = AsyncMock(
            return_value=ActionResult(success=True, message="Screenshot executed")
        )
        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path = AsyncMock()

        await mock_action_executor.execute_action(action)

        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path.assert_called_once()

    @pytest.mark.asyncio
    async def test_command_action_is_gui(self, mock_action_executor):
        """CommandAction should be treated as GUI action."""
        mock_action_executor.debug_screenshots = True
        action = CommandAction(command="echo hello")
        mock_action_executor._mock_simple_actions.execute_command = AsyncMock(
            return_value=ActionResult(success=True, message="Command executed")
        )
        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path = AsyncMock()

        await mock_action_executor.execute_action(action)

        mock_action_executor._mock_target_resolution.get_current_screenshot_with_path.assert_called_once()


# ============================================================================
# TestExecuteProgrammaticPull
# ============================================================================


class TestExecuteProgrammaticPull:
    """Tests for execute_programmatic_pull method."""

    @pytest.mark.asyncio
    async def test_delegates_to_simple_actions(self, mock_action_executor):
        """execute_programmatic_pull should delegate to simple_actions."""
        mock_action_executor._mock_simple_actions.execute_programmatic_pull = AsyncMock(
            return_value=ActionResult(success=True, message="Pull executed")
        )

        result = await mock_action_executor.execute_programmatic_pull("/path/to/file")

        mock_action_executor._mock_simple_actions.execute_programmatic_pull.assert_called_once_with(
            "/path/to/file", "Programmatic pull"
        )
        assert result.success is True

    @pytest.mark.asyncio
    async def test_custom_description(self, mock_action_executor):
        """execute_programmatic_pull should pass custom description."""
        mock_action_executor._mock_simple_actions.execute_programmatic_pull = AsyncMock(
            return_value=ActionResult(success=True, message="Pull executed")
        )

        await mock_action_executor.execute_programmatic_pull(
            "/path/to/file",
            description="Auto-pull on test failure"
        )

        mock_action_executor._mock_simple_actions.execute_programmatic_pull.assert_called_once_with(
            "/path/to/file", "Auto-pull on test failure"
        )

    @pytest.mark.asyncio
    async def test_returns_action_result(self, mock_action_executor):
        """execute_programmatic_pull should return ActionResult."""
        expected_result = ActionResult(
            success=True,
            message="File pulled successfully",
            data={"path": "/artifacts/file.txt"}
        )
        mock_action_executor._mock_simple_actions.execute_programmatic_pull = AsyncMock(
            return_value=expected_result
        )

        result = await mock_action_executor.execute_programmatic_pull("/path/to/file")

        assert result == expected_result
        assert result.success is True
        assert result.data == {"path": "/artifacts/file.txt"}


# ============================================================================
# TestExecuteActionTestActionIntegration
# ============================================================================


class TestExecuteActionTestActionIntegration:
    """Tests for ActionTestAction execution specifics."""

    @pytest.mark.asyncio
    async def test_action_executor_passed_to_test_executor(self, mock_action_executor):
        """ActionTestAction should receive action_executor for nested execution."""
        action = ActionTestAction(name="test_example")
        mock_action_executor._mock_test_actions.execute_test = AsyncMock(
            return_value=ActionResult(success=True, message="Test executed")
        )

        await mock_action_executor.execute_action(action)

        call_kwargs = mock_action_executor._mock_test_actions.execute_test.call_args.kwargs
        assert call_kwargs['action_executor'] == mock_action_executor

    @pytest.mark.asyncio
    async def test_execution_context_passed_to_test_executor(self, mock_action_executor):
        """ActionTestAction should receive execution_context."""
        mock_action_executor.execution_context = {"var": "value"}
        action = ActionTestAction(name="test_example")
        mock_action_executor._mock_test_actions.execute_test = AsyncMock(
            return_value=ActionResult(success=True, message="Test executed")
        )

        await mock_action_executor.execute_action(action)

        call_kwargs = mock_action_executor._mock_test_actions.execute_test.call_args.kwargs
        assert call_kwargs['execution_context'] == {"var": "value"}

    @pytest.mark.asyncio
    async def test_websocket_client_passed_to_test_executor(self, mock_action_executor):
        """ActionTestAction should receive websocket_client."""
        action = ActionTestAction(name="test_example")
        mock_action_executor._mock_test_actions.execute_test = AsyncMock(
            return_value=ActionResult(success=True, message="Test executed")
        )

        await mock_action_executor.execute_action(action)

        call_kwargs = mock_action_executor._mock_test_actions.execute_test.call_args.kwargs
        assert call_kwargs['websocket_client'] == mock_action_executor.client


# ============================================================================
# TestExecuteActionBlockAndLoopIntegration
# ============================================================================


class TestExecuteActionBlockAndLoopIntegration:
    """Tests for BlockAction and LoopAction execution specifics."""

    @pytest.mark.asyncio
    async def test_block_action_receives_action_executor(self, mock_action_executor):
        """BlockAction should receive action_executor for nested execution."""
        action = BlockAction(actions=[IdleAction(duration=0.1)])
        mock_action_executor._mock_flow_control.execute_block = AsyncMock(
            return_value=ActionResult(success=True, message="Block executed")
        )

        await mock_action_executor.execute_action(action)

        call_kwargs = mock_action_executor._mock_flow_control.execute_block.call_args.kwargs
        assert call_kwargs['action_executor'] == mock_action_executor

    @pytest.mark.asyncio
    async def test_loop_action_receives_action_executor(self, mock_action_executor):
        """LoopAction should receive action_executor for nested execution."""
        action = LoopAction(actions=[IdleAction(duration=0.1)], times=2)
        mock_action_executor._mock_flow_control.execute_loop = AsyncMock(
            return_value=ActionResult(success=True, message="Loop executed")
        )

        await mock_action_executor.execute_action(action)

        call_kwargs = mock_action_executor._mock_flow_control.execute_loop.call_args.kwargs
        assert call_kwargs['action_executor'] == mock_action_executor

    @pytest.mark.asyncio
    async def test_block_action_receives_variable_resolver(self, mock_action_executor):
        """BlockAction should receive variable_resolver."""
        action = BlockAction(actions=[IdleAction(duration=0.1)])
        mock_variable_resolver = MagicMock()
        mock_variable_resolver.resolve_action_variables.return_value = action
        mock_action_executor._mock_flow_control.execute_block = AsyncMock(
            return_value=ActionResult(success=True, message="Block executed")
        )

        await mock_action_executor.execute_action(action, variable_resolver=mock_variable_resolver)

        call_kwargs = mock_action_executor._mock_flow_control.execute_block.call_args.kwargs
        assert call_kwargs['variable_resolver'] == mock_variable_resolver

    @pytest.mark.asyncio
    async def test_loop_action_receives_variable_resolver(self, mock_action_executor):
        """LoopAction should receive variable_resolver."""
        action = LoopAction(actions=[IdleAction(duration=0.1)], times=2)
        mock_variable_resolver = MagicMock()
        mock_variable_resolver.resolve_action_variables.return_value = action
        mock_action_executor._mock_flow_control.execute_loop = AsyncMock(
            return_value=ActionResult(success=True, message="Loop executed")
        )

        await mock_action_executor.execute_action(action, variable_resolver=mock_variable_resolver)

        call_kwargs = mock_action_executor._mock_flow_control.execute_loop.call_args.kwargs
        assert call_kwargs['variable_resolver'] == mock_variable_resolver
