"""
Comprehensive unit tests for PlaybookController.

Tests cover:
- PlaybookExecutionResult dataclass
- PlaybookController initialization
- Helper methods (_is_test_action, _is_utility_action, _is_countable_action, etc.)
- Jinja environment creation
- Playbook items mapping initialization
- Async execution methods (mocked)
"""

import pytest
import sys
from unittest.mock import MagicMock, AsyncMock, patch
from pathlib import Path
from dataclasses import asdict

# Mock libvirt_qemu before any imports that might need it
sys.modules['libvirt_qemu'] = MagicMock()
sys.modules['libvirt'] = MagicMock()

from adare.backend.experiment.playbook_controller import (
    PlaybookController,
    PlaybookExecutionResult,
)
from adare.backend.experiment.action_executor import ActionResult
from adare.types.playbook import (
    Playbook,
    ActionTestAction,
    PullAction,
    PauseAction,
    SaveTimestampAction,
    ClickAction,
    Target,
    IdleAction,
    KeyboardAction,
    CommandAction,
    Settings,
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
def temp_experiment_dir(tmp_path):
    """Create a temporary experiment directory."""
    exp_dir = tmp_path / "experiment"
    exp_dir.mkdir()
    return exp_dir


@pytest.fixture
def temp_project_dir(tmp_path):
    """Create a temporary project directory."""
    proj_dir = tmp_path / "project"
    proj_dir.mkdir()
    return proj_dir


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
def playbook_with_test_actions():
    """Create a playbook that includes test actions."""
    return Playbook(
        actions=[
            ClickAction(target=Target(position=[100, 100])),
            ActionTestAction(name="test_file_exists"),
            IdleAction(duration=0.5),
            ActionTestAction(name="test_registry_key"),
        ],
        settings=Settings(),
    )


@pytest.fixture
def playbook_with_utility_actions():
    """Create a playbook with utility actions (pull, pause, save_timestamp)."""
    return Playbook(
        actions=[
            ClickAction(target=Target(position=[100, 100])),
            PullAction(src="/path/to/file"),
            PauseAction(message="Debug pause"),
            SaveTimestampAction(variable="my_ts"),
            IdleAction(duration=0.5),
        ],
        settings=Settings(),
    )


@pytest.fixture
def mock_controller(mock_websocket_client, temp_experiment_dir, temp_project_dir, simple_playbook):
    """Create a PlaybookController with mocked dependencies."""
    with patch('adare.backend.experiment.playbook_controller.MCPTargetResolver'):
        with patch('adare.backend.experiment.playbook_controller.MCPConditionChecker'):
            with patch.object(PlaybookController, '_initialize_modules'):
                controller = PlaybookController(
                    websocket_client=mock_websocket_client,
                    experiment_dir=temp_experiment_dir,
                    project_dir=temp_project_dir,
                    playbook=simple_playbook,
                    test_mode=True
                )
                return controller


# ============================================================================
# TestPlaybookExecutionResult
# ============================================================================


class TestPlaybookExecutionResult:
    """Tests for PlaybookExecutionResult dataclass."""

    def test_creation_with_required_fields(self):
        """PlaybookExecutionResult should be created with required fields."""
        result = PlaybookExecutionResult(
            success=True,
            total_actions=10,
            successful_actions=8,
            failed_actions=2,
            execution_time=5.5,
            action_results=[],
        )

        assert result.success is True
        assert result.total_actions == 10
        assert result.successful_actions == 8
        assert result.failed_actions == 2
        assert result.execution_time == 5.5
        assert result.action_results == []

    def test_default_error_message_is_none(self):
        """error_message should default to None."""
        result = PlaybookExecutionResult(
            success=True,
            total_actions=5,
            successful_actions=5,
            failed_actions=0,
            execution_time=2.0,
            action_results=[],
        )

        assert result.error_message is None

    def test_default_test_statistics(self):
        """Test statistics should default to 0."""
        result = PlaybookExecutionResult(
            success=True,
            total_actions=5,
            successful_actions=5,
            failed_actions=0,
            execution_time=2.0,
            action_results=[],
        )

        assert result.total_tests == 0
        assert result.successful_tests == 0
        assert result.failed_tests == 0

    def test_with_error_message(self):
        """PlaybookExecutionResult should support error_message."""
        result = PlaybookExecutionResult(
            success=False,
            total_actions=5,
            successful_actions=3,
            failed_actions=2,
            execution_time=3.0,
            action_results=[],
            error_message="Action 4 failed: target not found",
        )

        assert result.success is False
        assert result.error_message == "Action 4 failed: target not found"

    def test_with_test_statistics(self):
        """PlaybookExecutionResult should track test statistics."""
        result = PlaybookExecutionResult(
            success=True,
            total_actions=10,
            successful_actions=10,
            failed_actions=0,
            execution_time=5.0,
            action_results=[],
            total_tests=4,
            successful_tests=3,
            failed_tests=1,
        )

        assert result.total_tests == 4
        assert result.successful_tests == 3
        assert result.failed_tests == 1

    def test_with_action_results(self):
        """PlaybookExecutionResult should store action results."""
        action_result_1 = ActionResult(success=True, message="Click succeeded")
        action_result_2 = ActionResult(success=False, message="Target not found")

        result = PlaybookExecutionResult(
            success=False,
            total_actions=2,
            successful_actions=1,
            failed_actions=1,
            execution_time=1.5,
            action_results=[action_result_1, action_result_2],
        )

        assert len(result.action_results) == 2
        assert result.action_results[0].success is True
        assert result.action_results[1].success is False

    def test_is_dataclass(self):
        """PlaybookExecutionResult should be a proper dataclass."""
        result = PlaybookExecutionResult(
            success=True,
            total_actions=1,
            successful_actions=1,
            failed_actions=0,
            execution_time=0.5,
            action_results=[],
        )

        # Should be convertible to dict
        result_dict = asdict(result)
        assert isinstance(result_dict, dict)
        assert "success" in result_dict
        assert "total_actions" in result_dict


# ============================================================================
# TestPlaybookControllerInit
# ============================================================================


class TestPlaybookControllerInit:
    """Tests for PlaybookController initialization."""

    def test_basic_initialization(self, mock_websocket_client, temp_experiment_dir,
                                   temp_project_dir, simple_playbook):
        """Controller should initialize with basic parameters."""
        with patch('adare.backend.experiment.playbook_controller.MCPTargetResolver'):
            with patch('adare.backend.experiment.playbook_controller.MCPConditionChecker'):
                with patch.object(PlaybookController, '_initialize_modules'):
                    controller = PlaybookController(
                        websocket_client=mock_websocket_client,
                        experiment_dir=temp_experiment_dir,
                        project_dir=temp_project_dir,
                        playbook=simple_playbook,
                    )

        assert controller.client == mock_websocket_client
        assert controller.experiment_dir == temp_experiment_dir
        assert controller.project_dir == temp_project_dir
        assert controller.playbook == simple_playbook

    def test_default_values(self, mock_websocket_client, temp_experiment_dir,
                            temp_project_dir, simple_playbook):
        """Controller should have correct default values."""
        with patch('adare.backend.experiment.playbook_controller.MCPTargetResolver'):
            with patch('adare.backend.experiment.playbook_controller.MCPConditionChecker'):
                with patch.object(PlaybookController, '_initialize_modules'):
                    controller = PlaybookController(
                        websocket_client=mock_websocket_client,
                        experiment_dir=temp_experiment_dir,
                        project_dir=temp_project_dir,
                        playbook=simple_playbook,
                    )

        assert controller.debug_screenshots is False
        assert controller.screenshots_dir is None
        assert controller.test_mode is False
        assert controller.vm is None
        assert controller.experiment_run_directory is None
        assert controller.flow_console is None

    def test_with_test_mode(self, mock_websocket_client, temp_experiment_dir,
                            temp_project_dir, simple_playbook):
        """Controller should accept test_mode parameter."""
        with patch('adare.backend.experiment.playbook_controller.MCPTargetResolver'):
            with patch('adare.backend.experiment.playbook_controller.MCPConditionChecker'):
                with patch.object(PlaybookController, '_initialize_modules'):
                    controller = PlaybookController(
                        websocket_client=mock_websocket_client,
                        experiment_dir=temp_experiment_dir,
                        project_dir=temp_project_dir,
                        playbook=simple_playbook,
                        test_mode=True,
                    )

        assert controller.test_mode is True

    def test_with_experiment_ids(self, mock_websocket_client, temp_experiment_dir,
                                  temp_project_dir, simple_playbook):
        """Controller should accept experiment tracking IDs."""
        with patch('adare.backend.experiment.playbook_controller.MCPTargetResolver'):
            with patch('adare.backend.experiment.playbook_controller.MCPConditionChecker'):
                with patch.object(PlaybookController, '_initialize_modules'):
                    with patch.object(PlaybookController, '_initialize_playbook_items_mapping'):
                        controller = PlaybookController(
                            websocket_client=mock_websocket_client,
                            experiment_dir=temp_experiment_dir,
                            project_dir=temp_project_dir,
                            playbook=simple_playbook,
                            experiment_id="exp-123",
                            experiment_run_id="run-456",
                        )

        assert controller.experiment_id == "exp-123"
        assert controller.experiment_run_id == "run-456"

    def test_with_debug_screenshots(self, mock_websocket_client, temp_experiment_dir,
                                     temp_project_dir, simple_playbook, tmp_path):
        """Controller should accept debug screenshot configuration."""
        screenshots_dir = tmp_path / "screenshots"
        screenshots_dir.mkdir()

        with patch('adare.backend.experiment.playbook_controller.MCPTargetResolver'):
            with patch('adare.backend.experiment.playbook_controller.MCPConditionChecker'):
                with patch.object(PlaybookController, '_initialize_modules'):
                    controller = PlaybookController(
                        websocket_client=mock_websocket_client,
                        experiment_dir=temp_experiment_dir,
                        project_dir=temp_project_dir,
                        playbook=simple_playbook,
                        debug_screenshots=True,
                        screenshots_dir=screenshots_dir,
                    )

        assert controller.debug_screenshots is True
        assert controller.screenshots_dir == screenshots_dir

    def test_execution_context_with_config(self, mock_websocket_client, temp_experiment_dir,
                                            temp_project_dir, simple_playbook):
        """Controller should include config in execution context."""
        mock_config = MagicMock()
        mock_config.some_setting = "value"

        with patch('adare.backend.experiment.playbook_controller.MCPTargetResolver'):
            with patch('adare.backend.experiment.playbook_controller.MCPConditionChecker'):
                with patch.object(PlaybookController, '_initialize_modules'):
                    controller = PlaybookController(
                        websocket_client=mock_websocket_client,
                        experiment_dir=temp_experiment_dir,
                        project_dir=temp_project_dir,
                        playbook=simple_playbook,
                        config=mock_config,
                    )

        assert "config" in controller.execution_context
        assert controller.execution_context["config"] == mock_config

    def test_execution_context_empty_without_config(self, mock_websocket_client, temp_experiment_dir,
                                                     temp_project_dir, simple_playbook):
        """Controller should have empty execution context without config."""
        with patch('adare.backend.experiment.playbook_controller.MCPTargetResolver'):
            with patch('adare.backend.experiment.playbook_controller.MCPConditionChecker'):
                with patch.object(PlaybookController, '_initialize_modules'):
                    controller = PlaybookController(
                        websocket_client=mock_websocket_client,
                        experiment_dir=temp_experiment_dir,
                        project_dir=temp_project_dir,
                        playbook=simple_playbook,
                    )

        assert controller.execution_context == {}

    def test_playbook_items_map_initialized_empty(self, mock_websocket_client, temp_experiment_dir,
                                                   temp_project_dir, simple_playbook):
        """Controller should initialize playbook_items_map as empty dict."""
        with patch('adare.backend.experiment.playbook_controller.MCPTargetResolver'):
            with patch('adare.backend.experiment.playbook_controller.MCPConditionChecker'):
                with patch.object(PlaybookController, '_initialize_modules'):
                    controller = PlaybookController(
                        websocket_client=mock_websocket_client,
                        experiment_dir=temp_experiment_dir,
                        project_dir=temp_project_dir,
                        playbook=simple_playbook,
                    )

        assert controller.playbook_items_map == {}

    def test_action_results_initialized_empty(self, mock_websocket_client, temp_experiment_dir,
                                               temp_project_dir, simple_playbook):
        """Controller should initialize action_results as empty list."""
        with patch('adare.backend.experiment.playbook_controller.MCPTargetResolver'):
            with patch('adare.backend.experiment.playbook_controller.MCPConditionChecker'):
                with patch.object(PlaybookController, '_initialize_modules'):
                    controller = PlaybookController(
                        websocket_client=mock_websocket_client,
                        experiment_dir=temp_experiment_dir,
                        project_dir=temp_project_dir,
                        playbook=simple_playbook,
                    )

        assert controller.action_results == []

    def test_performance_tracking_initialized(self, mock_websocket_client, temp_experiment_dir,
                                               temp_project_dir, simple_playbook):
        """Controller should initialize performance tracking fields."""
        with patch('adare.backend.experiment.playbook_controller.MCPTargetResolver'):
            with patch('adare.backend.experiment.playbook_controller.MCPConditionChecker'):
                with patch.object(PlaybookController, '_initialize_modules'):
                    controller = PlaybookController(
                        websocket_client=mock_websocket_client,
                        experiment_dir=temp_experiment_dir,
                        project_dir=temp_project_dir,
                        playbook=simple_playbook,
                    )

        assert controller.start_time is None
        assert controller.action_timings == {}

    def test_auto_pull_tracking_initialized(self, mock_websocket_client, temp_experiment_dir,
                                             temp_project_dir, simple_playbook):
        """Controller should initialize auto-pull tracking fields."""
        with patch('adare.backend.experiment.playbook_controller.MCPTargetResolver'):
            with patch('adare.backend.experiment.playbook_controller.MCPConditionChecker'):
                with patch.object(PlaybookController, '_initialize_modules'):
                    controller = PlaybookController(
                        websocket_client=mock_websocket_client,
                        experiment_dir=temp_experiment_dir,
                        project_dir=temp_project_dir,
                        playbook=simple_playbook,
                    )

        assert controller._auto_pull_files == []
        assert controller._auto_pull_executed is False


# ============================================================================
# TestIsTestAction
# ============================================================================


class TestIsTestAction:
    """Tests for _is_test_action helper method."""

    def test_action_test_action_returns_true(self, mock_controller):
        """ActionTestAction should be identified as a test action."""
        action = ActionTestAction(name="test_example")
        assert mock_controller._is_test_action(action) is True

    def test_click_action_returns_false(self, mock_controller):
        """ClickAction should not be a test action."""
        action = ClickAction(target=Target(position=[100, 100]))
        assert mock_controller._is_test_action(action) is False

    def test_idle_action_returns_false(self, mock_controller):
        """IdleAction should not be a test action."""
        action = IdleAction(duration=1.0)
        assert mock_controller._is_test_action(action) is False

    def test_keyboard_action_returns_false(self, mock_controller):
        """KeyboardAction should not be a test action."""
        action = KeyboardAction(text="hello")
        assert mock_controller._is_test_action(action) is False

    def test_command_action_returns_false(self, mock_controller):
        """CommandAction should not be a test action."""
        action = CommandAction(command="echo hello")
        assert mock_controller._is_test_action(action) is False

    def test_pull_action_returns_false(self, mock_controller):
        """PullAction should not be a test action."""
        action = PullAction(src="/path/to/file")
        assert mock_controller._is_test_action(action) is False

    def test_pause_action_returns_false(self, mock_controller):
        """PauseAction should not be a test action."""
        action = PauseAction(message="Pause")
        assert mock_controller._is_test_action(action) is False

    def test_save_timestamp_action_returns_false(self, mock_controller):
        """SaveTimestampAction should not be a test action."""
        action = SaveTimestampAction(variable="ts")
        assert mock_controller._is_test_action(action) is False


# ============================================================================
# TestIsUtilityAction
# ============================================================================


class TestIsUtilityAction:
    """Tests for _is_utility_action helper method."""

    def test_pull_action_returns_true(self, mock_controller):
        """PullAction should be a utility action."""
        action = PullAction(src="/path/to/file")
        assert mock_controller._is_utility_action(action) is True

    def test_pause_action_returns_true(self, mock_controller):
        """PauseAction should be a utility action."""
        action = PauseAction(message="Debug pause")
        assert mock_controller._is_utility_action(action) is True

    def test_save_timestamp_action_returns_true(self, mock_controller):
        """SaveTimestampAction should be a utility action."""
        action = SaveTimestampAction(variable="my_timestamp")
        assert mock_controller._is_utility_action(action) is True

    def test_click_action_returns_false(self, mock_controller):
        """ClickAction should not be a utility action."""
        action = ClickAction(target=Target(position=[100, 100]))
        assert mock_controller._is_utility_action(action) is False

    def test_idle_action_returns_false(self, mock_controller):
        """IdleAction should not be a utility action."""
        action = IdleAction(duration=1.0)
        assert mock_controller._is_utility_action(action) is False

    def test_action_test_action_returns_false(self, mock_controller):
        """ActionTestAction should not be a utility action."""
        action = ActionTestAction(name="test_example")
        assert mock_controller._is_utility_action(action) is False

    def test_command_action_returns_false(self, mock_controller):
        """CommandAction should not be a utility action."""
        action = CommandAction(command="ls -la")
        assert mock_controller._is_utility_action(action) is False


# ============================================================================
# TestIsCountableAction
# ============================================================================


class TestIsCountableAction:
    """Tests for _is_countable_action helper method."""

    def test_click_action_is_countable(self, mock_controller):
        """ClickAction should be countable."""
        action = ClickAction(target=Target(position=[100, 100]))
        assert mock_controller._is_countable_action(action) is True

    def test_idle_action_is_countable(self, mock_controller):
        """IdleAction should be countable."""
        action = IdleAction(duration=1.0)
        assert mock_controller._is_countable_action(action) is True

    def test_keyboard_action_is_countable(self, mock_controller):
        """KeyboardAction should be countable."""
        action = KeyboardAction(key="enter")
        assert mock_controller._is_countable_action(action) is True

    def test_command_action_is_countable(self, mock_controller):
        """CommandAction should be countable."""
        action = CommandAction(command="pwd")
        assert mock_controller._is_countable_action(action) is True

    def test_action_test_action_is_countable(self, mock_controller):
        """ActionTestAction should be countable."""
        action = ActionTestAction(name="test_check")
        assert mock_controller._is_countable_action(action) is True

    def test_pull_action_not_countable(self, mock_controller):
        """PullAction should not be countable (utility action)."""
        action = PullAction(src="/path/to/file")
        assert mock_controller._is_countable_action(action) is False

    def test_pause_action_not_countable(self, mock_controller):
        """PauseAction should not be countable (utility action)."""
        action = PauseAction(message="Wait")
        assert mock_controller._is_countable_action(action) is False

    def test_save_timestamp_action_not_countable(self, mock_controller):
        """SaveTimestampAction should not be countable (utility action)."""
        action = SaveTimestampAction(variable="ts")
        assert mock_controller._is_countable_action(action) is False

    def test_countable_is_opposite_of_utility(self, mock_controller):
        """_is_countable_action should return opposite of _is_utility_action."""
        actions = [
            ClickAction(target=Target(position=[100, 100])),
            PullAction(src="/file"),
            PauseAction(),
            SaveTimestampAction(variable="ts"),
            IdleAction(duration=1.0),
            ActionTestAction(name="test"),
        ]

        for action in actions:
            assert mock_controller._is_countable_action(action) == (
                not mock_controller._is_utility_action(action)
            )


# ============================================================================
# TestIsTestActionResult
# ============================================================================


class TestIsTestActionResult:
    """Tests for _is_test_action_result helper method."""

    def test_result_with_test_data_structure(self, mock_controller):
        """Result with test-specific data structure should be identified."""
        result = ActionResult(
            success=True,
            message="Test passed",
            data={
                "result": {
                    "status": "passed",
                    "details": {"check_count": 5}
                }
            }
        )
        assert mock_controller._is_test_action_result(result) is True

    def test_result_with_failed_test_structure(self, mock_controller):
        """Failed test result should be identified as test action result."""
        result = ActionResult(
            success=False,
            message="Test failed",
            data={
                "result": {
                    "status": "failed",
                    "details": {"error": "File not found"}
                }
            }
        )
        assert mock_controller._is_test_action_result(result) is True

    def test_result_without_result_key(self, mock_controller):
        """Result without 'result' key should not be a test result."""
        result = ActionResult(
            success=True,
            message="Click succeeded",
            data={"coordinates": (100, 200)}
        )
        assert mock_controller._is_test_action_result(result) is False

    def test_result_without_status_key(self, mock_controller):
        """Result without 'status' in result should not be a test result."""
        result = ActionResult(
            success=True,
            message="Action done",
            data={
                "result": {
                    "details": {"some": "data"}
                }
            }
        )
        assert mock_controller._is_test_action_result(result) is False

    def test_result_without_details_key(self, mock_controller):
        """Result without 'details' in result should not be a test result."""
        result = ActionResult(
            success=True,
            message="Action done",
            data={
                "result": {
                    "status": "completed"
                }
            }
        )
        assert mock_controller._is_test_action_result(result) is False

    def test_result_with_none_data(self, mock_controller):
        """Result with None data should not be a test result."""
        result = ActionResult(
            success=True,
            message="Completed",
            data=None
        )
        assert mock_controller._is_test_action_result(result) is False

    def test_result_with_non_dict_data(self, mock_controller):
        """Result with non-dict data should not be a test result."""
        result = ActionResult(
            success=True,
            message="Done",
            data="string data"
        )
        assert mock_controller._is_test_action_result(result) is False


# ============================================================================
# TestCreateJinjaEnvironment
# ============================================================================


class TestCreateJinjaEnvironment:
    """Tests for _create_jinja_environment method."""

    def test_creates_jinja_environment(self, mock_controller):
        """Should create a valid Jinja2 environment."""
        import jinja2

        env = mock_controller._create_jinja_environment()

        assert isinstance(env, jinja2.Environment)

    def test_environment_can_render_templates(self, mock_controller):
        """Created environment should be able to render templates."""
        env = mock_controller._create_jinja_environment()

        template = env.from_string("Hello, {{ name }}!")
        result = template.render(name="World")

        assert result == "Hello, World!"

    def test_environment_with_playbook_without_variables(
        self, mock_websocket_client, temp_experiment_dir, temp_project_dir
    ):
        """Environment should be created even without playbook variables."""
        playbook = Playbook(
            actions=[IdleAction(duration=1.0)],
            settings=Settings(),
            variables=None,
        )

        with patch('adare.backend.experiment.playbook_controller.MCPTargetResolver'):
            with patch('adare.backend.experiment.playbook_controller.MCPConditionChecker'):
                with patch.object(PlaybookController, '_initialize_modules'):
                    controller = PlaybookController(
                        websocket_client=mock_websocket_client,
                        experiment_dir=temp_experiment_dir,
                        project_dir=temp_project_dir,
                        playbook=playbook,
                    )

        env = controller._create_jinja_environment()
        assert env is not None


# ============================================================================
# TestInitializePlaybookItemsMapping
# ============================================================================


class TestInitializePlaybookItemsMapping:
    """Tests for _initialize_playbook_items_mapping method."""

    def test_no_mapping_without_experiment_id(self, mock_controller):
        """Should not initialize mapping without experiment_id."""
        mock_controller.experiment_id = None
        mock_controller.playbook_items_map = {}

        mock_controller._initialize_playbook_items_mapping()

        assert mock_controller.playbook_items_map == {}

    def test_mapping_with_experiment_id(
        self, mock_websocket_client, temp_experiment_dir, temp_project_dir, simple_playbook
    ):
        """Should initialize mapping when experiment_id is provided."""
        mock_playbook = MagicMock()
        mock_playbook.id = "pb-123"

        mock_item_1 = MagicMock()
        mock_item_1.sequence_order = 0
        mock_item_1.id = "item-1"

        mock_item_2 = MagicMock()
        mock_item_2.sequence_order = 1
        mock_item_2.id = "item-2"

        mock_playbook_api_instance = MagicMock()
        mock_playbook_api_instance.get_playbook_by_experiment_id.return_value = mock_playbook
        mock_playbook_api_instance.get_playbook_items.return_value = [mock_item_1, mock_item_2]
        mock_playbook_api_instance.__enter__ = MagicMock(return_value=mock_playbook_api_instance)
        mock_playbook_api_instance.__exit__ = MagicMock(return_value=None)

        with patch('adare.backend.experiment.playbook_controller.MCPTargetResolver'):
            with patch('adare.backend.experiment.playbook_controller.MCPConditionChecker'):
                with patch.object(PlaybookController, '_initialize_modules'):
                    with patch(
                        'adare.database.api.playbook.PlaybookApi',
                        return_value=mock_playbook_api_instance
                    ):
                        controller = PlaybookController(
                            websocket_client=mock_websocket_client,
                            experiment_dir=temp_experiment_dir,
                            project_dir=temp_project_dir,
                            playbook=simple_playbook,
                            experiment_id="exp-123",
                        )

        assert controller.playbook_items_map == {0: "item-1", 1: "item-2"}

    def test_mapping_empty_when_no_playbook_found(
        self, mock_websocket_client, temp_experiment_dir, temp_project_dir, simple_playbook
    ):
        """Should have empty mapping when no playbook found in database."""
        mock_playbook_api_instance = MagicMock()
        mock_playbook_api_instance.get_playbook_by_experiment_id.return_value = None
        mock_playbook_api_instance.__enter__ = MagicMock(return_value=mock_playbook_api_instance)
        mock_playbook_api_instance.__exit__ = MagicMock(return_value=None)

        with patch('adare.backend.experiment.playbook_controller.MCPTargetResolver'):
            with patch('adare.backend.experiment.playbook_controller.MCPConditionChecker'):
                with patch.object(PlaybookController, '_initialize_modules'):
                    with patch(
                        'adare.database.api.playbook.PlaybookApi',
                        return_value=mock_playbook_api_instance
                    ):
                        controller = PlaybookController(
                            websocket_client=mock_websocket_client,
                            experiment_dir=temp_experiment_dir,
                            project_dir=temp_project_dir,
                            playbook=simple_playbook,
                            experiment_id="exp-nonexistent",
                        )

        assert controller.playbook_items_map == {}


# ============================================================================
# TestInitializeModules (integration-style with full mocking)
# ============================================================================


class TestInitializeModulesIntegration:
    """Tests for _initialize_modules method requiring more extensive mocking."""

    def test_modules_fields_exist_after_init(
        self, mock_websocket_client, temp_experiment_dir, temp_project_dir, simple_playbook
    ):
        """After full initialization, module fields should exist."""
        # Create mocks for all the module classes
        mock_variable_resolver = MagicMock()
        mock_event_manager = MagicMock()
        mock_action_executor = MagicMock()
        mock_test_loader = MagicMock()

        with patch('adare.backend.experiment.playbook_controller.MCPTargetResolver'):
            with patch('adare.backend.experiment.playbook_controller.MCPConditionChecker'):
                with patch('adare.backend.experiment.playbook_controller.VariableResolver', return_value=mock_variable_resolver):
                    with patch('adare.backend.experiment.playbook_controller.EventManager', return_value=mock_event_manager):
                        with patch('adare.backend.experiment.playbook_controller.ActionExecutor', return_value=mock_action_executor):
                            with patch('adare.backend.experiment.playbook_controller.TestLoader', return_value=mock_test_loader):
                                controller = PlaybookController(
                                    websocket_client=mock_websocket_client,
                                    experiment_dir=temp_experiment_dir,
                                    project_dir=temp_project_dir,
                                    playbook=simple_playbook,
                                )

        assert hasattr(controller, 'variable_resolver')
        assert hasattr(controller, 'event_manager')
        assert hasattr(controller, 'action_executor')
        assert hasattr(controller, 'test_loader')


# ============================================================================
# TestCreateDatabaseExecutionRecord
# ============================================================================


class TestCreateDatabaseExecutionRecord:
    """Tests for _create_database_execution_record async method."""

    @pytest.mark.asyncio
    async def test_creates_execution_record(self, mock_controller):
        """Should create database execution record."""
        mock_controller.experiment_run_id = "run-123"
        mock_controller.playbook_items_map = {0: "item-1"}

        mock_execution = MagicMock()
        mock_execution.id = "exec-123"

        mock_playbook_api_instance = MagicMock()
        mock_playbook_api_instance.create_action_execution.return_value = mock_execution
        mock_playbook_api_instance.update_action_execution_start = MagicMock()
        mock_playbook_api_instance.__enter__ = MagicMock(return_value=mock_playbook_api_instance)
        mock_playbook_api_instance.__exit__ = MagicMock(return_value=None)

        with patch(
            'adare.database.api.playbook.PlaybookApi',
            return_value=mock_playbook_api_instance
        ):
            result = await mock_controller._create_database_execution_record(0)

        assert result == "exec-123"
        mock_playbook_api_instance.create_action_execution.assert_called_once_with(
            playbook_item_id="item-1",
            experiment_run_id="run-123",
            status='pending'
        )

    @pytest.mark.asyncio
    async def test_returns_none_on_exception(self, mock_controller):
        """Should return None and log warning on exception."""
        mock_controller.experiment_run_id = "run-123"
        mock_controller.playbook_items_map = {0: "item-1"}

        with patch(
            'adare.database.api.playbook.PlaybookApi',
            side_effect=Exception("Database error")
        ):
            result = await mock_controller._create_database_execution_record(0)

        assert result is None


# ============================================================================
# TestUpdateDatabaseExecutionRecord
# ============================================================================


class TestUpdateDatabaseExecutionRecord:
    """Tests for _update_database_execution_record async method."""

    @pytest.mark.asyncio
    async def test_updates_execution_record_success(self, mock_controller):
        """Should update execution record for successful action."""
        result = ActionResult(
            success=True,
            message="Action completed",
            coordinates=(100, 200),
            data={"key": "value"}
        )

        mock_playbook_api_instance = MagicMock()
        mock_playbook_api_instance.update_action_execution_complete = MagicMock()
        mock_playbook_api_instance.__enter__ = MagicMock(return_value=mock_playbook_api_instance)
        mock_playbook_api_instance.__exit__ = MagicMock(return_value=None)

        with patch(
            'adare.database.api.playbook.PlaybookApi',
            return_value=mock_playbook_api_instance
        ):
            await mock_controller._update_database_execution_record("exec-123", result, 1.5)

        mock_playbook_api_instance.update_action_execution_complete.assert_called_once_with(
            execution_id="exec-123",
            success=True,
            result_data={
                'coordinates': (100, 200),
                'data': {"key": "value"},
                'execution_time': 1.5
            },
            error_message=None
        )

    @pytest.mark.asyncio
    async def test_updates_execution_record_failure(self, mock_controller):
        """Should update execution record with error message for failed action."""
        result = ActionResult(
            success=False,
            message="Target not found",
        )

        mock_playbook_api_instance = MagicMock()
        mock_playbook_api_instance.update_action_execution_complete = MagicMock()
        mock_playbook_api_instance.__enter__ = MagicMock(return_value=mock_playbook_api_instance)
        mock_playbook_api_instance.__exit__ = MagicMock(return_value=None)

        with patch(
            'adare.database.api.playbook.PlaybookApi',
            return_value=mock_playbook_api_instance
        ):
            await mock_controller._update_database_execution_record("exec-456", result, 2.0)

        call_args = mock_playbook_api_instance.update_action_execution_complete.call_args
        assert call_args.kwargs['success'] is False
        assert call_args.kwargs['error_message'] == "Target not found"

    @pytest.mark.asyncio
    async def test_handles_exception_gracefully(self, mock_controller):
        """Should handle database exceptions gracefully."""
        result = ActionResult(success=True, message="Done")

        with patch(
            'adare.database.api.playbook.PlaybookApi',
            side_effect=Exception("DB connection failed")
        ):
            # Should not raise exception
            await mock_controller._update_database_execution_record("exec-789", result, 0.5)


# ============================================================================
# TestPlaybookControllerWithVariables
# ============================================================================


class TestPlaybookControllerWithVariables:
    """Tests for PlaybookController with variable handling."""

    def test_controller_with_vm_info_adds_automatic_variables(
        self, mock_websocket_client, temp_experiment_dir, temp_project_dir
    ):
        """Controller should add automatic variables when VM info is provided."""
        playbook = Playbook(
            actions=[IdleAction(duration=1.0)],
            settings=Settings(),
        )

        with patch('adare.backend.experiment.playbook_controller.MCPTargetResolver'):
            with patch('adare.backend.experiment.playbook_controller.MCPConditionChecker'):
                with patch.object(PlaybookController, '_initialize_modules'):
                    controller = PlaybookController(
                        websocket_client=mock_websocket_client,
                        experiment_dir=temp_experiment_dir,
                        project_dir=temp_project_dir,
                        playbook=playbook,
                        vm_os="windows",
                        vm_user="testuser",
                    )

        # Check that vm_os and vm_user are stored
        assert controller.vm_os == "windows"
        assert controller.vm_user == "testuser"


# ============================================================================
# TestPlaybookControllerMCPIntegration
# ============================================================================


class TestPlaybookControllerMCPIntegration:
    """Tests for MCP GUI integration in PlaybookController."""

    def test_target_resolver_initialized_with_mcp_url(
        self, mock_websocket_client, temp_experiment_dir, temp_project_dir, simple_playbook
    ):
        """Target resolver should be initialized with MCP GUI URL."""
        custom_url = "http://192.168.1.100:13109/mcp"

        with patch('adare.backend.experiment.playbook_controller.MCPTargetResolver') as mock_resolver:
            with patch('adare.backend.experiment.playbook_controller.MCPConditionChecker'):
                with patch.object(PlaybookController, '_initialize_modules'):
                    controller = PlaybookController(
                        websocket_client=mock_websocket_client,
                        experiment_dir=temp_experiment_dir,
                        project_dir=temp_project_dir,
                        playbook=simple_playbook,
                        mcp_gui_url=custom_url,
                    )

        mock_resolver.assert_called_once()
        call_args = mock_resolver.call_args
        assert call_args[0][1] == custom_url

    def test_condition_checker_initialized_with_target_resolver(
        self, mock_websocket_client, temp_experiment_dir, temp_project_dir, simple_playbook
    ):
        """Condition checker should be initialized with target resolver."""
        mock_resolver_instance = MagicMock()

        with patch('adare.backend.experiment.playbook_controller.MCPTargetResolver',
                   return_value=mock_resolver_instance):
            with patch('adare.backend.experiment.playbook_controller.MCPConditionChecker') as mock_checker:
                with patch.object(PlaybookController, '_initialize_modules'):
                    controller = PlaybookController(
                        websocket_client=mock_websocket_client,
                        experiment_dir=temp_experiment_dir,
                        project_dir=temp_project_dir,
                        playbook=simple_playbook,
                    )

        mock_checker.assert_called_once_with(mock_resolver_instance)


# ============================================================================
# TestActionResultDataclass
# ============================================================================


class TestActionResultDataclass:
    """Tests for ActionResult dataclass used in playbook execution."""

    def test_action_result_creation_minimal(self):
        """ActionResult should be created with minimal required fields."""
        result = ActionResult(success=True, message="Done")

        assert result.success is True
        assert result.message == "Done"
        assert result.coordinates is None
        assert result.data is None
        assert result.execution_time is None

    def test_action_result_creation_full(self):
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

    def test_action_result_is_dataclass(self):
        """ActionResult should be a proper dataclass."""
        result = ActionResult(success=True, message="OK")

        result_dict = asdict(result)
        assert isinstance(result_dict, dict)
        assert "success" in result_dict
        assert "message" in result_dict
