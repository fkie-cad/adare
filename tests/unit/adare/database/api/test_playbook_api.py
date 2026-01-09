"""
Unit tests for PlaybookApi class.

Tests serialization/deserialization helpers and database methods for playbook
operations. Uses mock SQLAlchemy sessions and model objects.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
import json
import sys


# === Fixtures ===

@pytest.fixture(scope="module")
def mock_db_setup():
    """Set up mocks before importing PlaybookApi."""
    with patch.dict(sys.modules, {'adare.config.database': MagicMock()}):
        yield


def create_playbook_api():
    """Factory function to create PlaybookApi with mocked dependencies."""
    with patch('adare.config.database.get_project_database_location', return_value=MagicMock()):
        with patch('adare.database.api.base.ProjectDatabaseApi.__init__', return_value=None):
            from adare.database.api.playbook import PlaybookApi
            api = PlaybookApi.__new__(PlaybookApi)
            api._session = MagicMock()
            api.project_path = MagicMock()
            return api


@pytest.fixture
def playbook_api():
    """Create a PlaybookApi instance with mocked database connection."""
    return create_playbook_api()


# === Mock Model Factories ===

def create_mock_playbook_item(
    item_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
    playbook_id="playbook_123",
    action_type="click",
    target=None,
    parameters=None,
    conditions=None,
    description="Test action",
    sequence_order=0,
):
    """Create a mock PlaybookItem for testing."""
    item = MagicMock()
    item.id = item_id
    item.playbook_id = playbook_id
    item.action_type = action_type
    item.target = target
    item.parameters = parameters or {}
    item.conditions = conditions
    item.description = description
    item.sequence_order = sequence_order
    item.is_enabled = True
    item.parent_id = None
    return item


def create_mock_playbook(
    playbook_id="playbook_123",
    experiment_id="exp_123",
    name="Test Playbook",
    settings=None,
    original_yaml_content="actions: []",
    version=1,
):
    """Create a mock Playbook for testing."""
    playbook = MagicMock()
    playbook.id = playbook_id
    playbook.experiment_id = experiment_id
    playbook.name = name
    playbook.settings = settings or {}
    playbook.original_yaml_content = original_yaml_content
    playbook.version = version
    return playbook


def create_mock_action_execution(
    execution_id="exec_123",
    playbook_item_id="item_123",
    experiment_run_id="run_123",
    status="pending",
    started_at=None,
    completed_at=None,
    result_data=None,
    error_message=None,
    attempt_number=1,
):
    """Create a mock ActionExecution for testing."""
    execution = MagicMock()
    execution.id = execution_id
    execution.playbook_item_id = playbook_item_id
    execution.experiment_run_id = experiment_run_id
    execution.status = status
    execution.started_at = started_at
    execution.completed_at = completed_at
    execution.result_data = result_data
    execution.error_message = error_message
    execution.attempt_number = attempt_number
    return execution


# === SERIALIZATION TESTS ===

class TestConfigToSettingsJson:
    """Tests for _config_to_settings_json method."""

    @pytest.fixture
    def api(self):
        return create_playbook_api()

    def test_empty_settings(self, api):
        """Config with no settings returns empty dict."""
        from adare.types.playbook import Playbook as PlaybookType, Settings
        config = PlaybookType(actions=[], settings=None)
        # When settings is None, the method should handle it
        config.settings = None
        result = api._config_to_settings_json(config)
        assert result == {}

    def test_default_settings(self, api):
        """Config with default Settings serializes correctly."""
        from adare.types.playbook import Playbook as PlaybookType, Settings
        config = PlaybookType(actions=[], settings=Settings())

        result = api._config_to_settings_json(config)

        assert result['idle'] == 0.1
        assert result.get('continue_on_test_failure') is False

    def test_settings_with_timeout(self, api):
        """Settings with timeout serializes correctly."""
        from adare.types.playbook import Playbook as PlaybookType, Settings
        config = PlaybookType(actions=[], settings=Settings(timeout=30.0))

        result = api._config_to_settings_json(config)

        assert result['idle'] == 0.1
        assert result['timeout'] == 30.0

    def test_settings_with_screenshot(self, api):
        """Settings with screenshot config serializes correctly."""
        from adare.types.playbook import Playbook as PlaybookType, Settings
        config = PlaybookType(actions=[], settings=Settings(screenshot={'format': 'png'}))

        result = api._config_to_settings_json(config)

        assert result['screenshot'] == {'format': 'png'}

    def test_settings_all_fields(self, api):
        """Settings with all fields serializes correctly."""
        from adare.types.playbook import Playbook as PlaybookType, Settings
        config = PlaybookType(
            actions=[],
            settings=Settings(
                idle=0.5,
                timeout=60.0,
                screenshot={'format': 'jpg'},
                continue_on_test_failure=True
            )
        )

        result = api._config_to_settings_json(config)

        assert result['idle'] == 0.5
        assert result['timeout'] == 60.0
        assert result['screenshot'] == {'format': 'jpg'}
        assert result['continue_on_test_failure'] is True


class TestTargetToJson:
    """Tests for _target_to_json method."""

    @pytest.fixture
    def api(self):
        return create_playbook_api()

    def test_image_target(self, api):
        """Target with image serializes correctly."""
        from adare.types.playbook import Target
        target = Target(image='button.png')

        result = api._target_to_json(target)

        assert result == {'image': 'button.png'}

    def test_text_target(self, api):
        """Target with text serializes correctly."""
        from adare.types.playbook import Target
        target = Target(text='Click Me')

        result = api._target_to_json(target)

        assert result == {'text': 'Click Me'}

    def test_position_target(self, api):
        """Target with position serializes correctly."""
        from adare.types.playbook import Target
        target = Target(position=[100, 200])

        result = api._target_to_json(target)

        assert result == {'position': [100, 200]}

    def test_target_with_strategy(self, api):
        """Target with strategy serializes correctly."""
        from adare.types.playbook import Target, SweepStrategy
        target = Target(text='Label', strategy=SweepStrategy(index=3))

        result = api._target_to_json(target)

        assert result['text'] == 'Label'
        assert 'strategy' in result
        assert result['strategy'] == {'SweepStrategy': {'index': 3}}

    def test_combined_target(self, api):
        """Target with multiple fields serializes correctly."""
        from adare.types.playbook import Target
        target = Target(image='icon.png', text='Button')

        result = api._target_to_json(target)

        assert result['image'] == 'icon.png'
        assert result['text'] == 'Button'


class TestStrategyToJson:
    """Tests for _strategy_to_json method."""

    @pytest.fixture
    def api(self):
        return create_playbook_api()

    def test_sweep_strategy(self, api):
        """SweepStrategy serializes correctly."""
        from adare.types.playbook import SweepStrategy
        strategy = SweepStrategy(index=5)

        result = api._strategy_to_json(strategy)

        assert result == {'SweepStrategy': {'index': 5}}

    def test_best_confidence_strategy(self, api):
        """BestConfidenceStrategy serializes correctly."""
        from adare.types.playbook import BestConfidenceStrategy
        strategy = BestConfidenceStrategy()

        result = api._strategy_to_json(strategy)

        assert 'BestConfidenceStrategy' in result

    def test_closest_to_strategy_coordinates(self, api):
        """ClosestToStrategy with coordinates serializes correctly."""
        from adare.types.playbook import ClosestToStrategy
        strategy = ClosestToStrategy(x=100, y=200)

        result = api._strategy_to_json(strategy)

        assert 'ClosestToStrategy' in result
        assert result['ClosestToStrategy']['x'] == 100
        assert result['ClosestToStrategy']['y'] == 200

    def test_closest_to_strategy_text(self, api):
        """ClosestToStrategy with text reference serializes correctly."""
        from adare.types.playbook import ClosestToStrategy
        strategy = ClosestToStrategy(text='Reference')

        result = api._strategy_to_json(strategy)

        assert 'ClosestToStrategy' in result
        assert result['ClosestToStrategy']['text'] == 'Reference'

    @pytest.mark.parametrize("strategy_class,expected_key", [
        ('TopLeftStrategy', 'TopLeftStrategy'),
        ('TopRightStrategy', 'TopRightStrategy'),
        ('BottomLeftStrategy', 'BottomLeftStrategy'),
        ('BottomRightStrategy', 'BottomRightStrategy'),
        ('LargestStrategy', 'LargestStrategy'),
        ('SmallestStrategy', 'SmallestStrategy'),
    ])
    def test_directional_strategies(self, api, strategy_class, expected_key):
        """Directional strategies serialize correctly."""
        from adare.types import playbook
        strategy_cls = getattr(playbook, strategy_class)
        strategy = strategy_cls()

        result = api._strategy_to_json(strategy)

        assert expected_key in result


class TestConditionToJson:
    """Tests for _condition_to_json method."""

    @pytest.fixture
    def api(self):
        return create_playbook_api()

    def test_exists_condition(self, api):
        """ExistsCondition serializes correctly."""
        from adare.types.playbook import ExistsCondition
        condition = ExistsCondition(text='Button')

        result = api._condition_to_json(condition)

        assert result['type'] == 'exists'
        assert result['text'] == 'Button'

    def test_not_exists_condition(self, api):
        """NotExistsCondition serializes correctly."""
        from adare.types.playbook import NotExistsCondition
        condition = NotExistsCondition(image='loading.png')

        result = api._condition_to_json(condition)

        assert result['type'] == 'notexists'
        assert result['image'] == 'loading.png'


class TestActionToParametersJson:
    """Tests for _action_to_parameters_json method."""

    @pytest.fixture
    def api(self):
        return create_playbook_api()

    def test_click_action_parameters(self, api):
        """ClickAction parameters serialize correctly."""
        from adare.types.playbook import ClickAction, Target
        action = ClickAction(target=Target(text='Button'), type='double')

        result = api._action_to_parameters_json(action)

        assert result['type'] == 'double'
        # target should be excluded from parameters
        assert 'target' not in result

    def test_keyboard_action_parameters(self, api):
        """KeyboardAction parameters serialize correctly."""
        from adare.types.playbook import KeyboardAction
        action = KeyboardAction(key='enter', text=None, combination=None)

        result = api._action_to_parameters_json(action)

        assert result['key'] == 'enter'

    def test_idle_action_parameters(self, api):
        """IdleAction parameters serialize correctly."""
        from adare.types.playbook import IdleAction
        action = IdleAction(duration=2.5)

        result = api._action_to_parameters_json(action)

        assert result['duration'] == 2.5

    def test_command_action_parameters(self, api):
        """CommandAction parameters serialize correctly."""
        from adare.types.playbook import CommandAction
        action = CommandAction(
            command='ls -la',
            cwd='/home/user',
            timeout=30.0,
            shell=True
        )

        result = api._action_to_parameters_json(action)

        assert result['command'] == 'ls -la'
        assert result['cwd'] == '/home/user'
        assert result['timeout'] == 30.0
        assert result['shell'] is True


class TestSerializeValue:
    """Tests for _serialize_value method."""

    @pytest.fixture
    def api(self):
        return create_playbook_api()

    def test_primitives(self, api):
        """Primitive values serialize correctly."""
        assert api._serialize_value(None) is None
        assert api._serialize_value('hello') == 'hello'
        assert api._serialize_value(42) == 42
        assert api._serialize_value(3.14) == 3.14
        assert api._serialize_value(True) is True

    def test_list(self, api):
        """Lists serialize recursively."""
        result = api._serialize_value([1, 'two', 3.0])
        assert result == [1, 'two', 3.0]

    def test_dict(self, api):
        """Dicts serialize recursively."""
        result = api._serialize_value({'a': 1, 'b': 'two'})
        assert result == {'a': 1, 'b': 'two'}

    def test_nested_structure(self, api):
        """Nested structures serialize recursively."""
        value = {'items': [1, 2, 3], 'meta': {'key': 'value'}}
        result = api._serialize_value(value)
        assert result == {'items': [1, 2, 3], 'meta': {'key': 'value'}}


class TestSerializeWaitCondition:
    """Tests for _serialize_wait_condition method."""

    @pytest.fixture
    def api(self):
        return create_playbook_api()

    def test_exists_condition(self, api):
        """WaitCondition with exists serializes correctly."""
        from adare.types.playbook import WaitCondition, Target
        condition = WaitCondition(exists=Target(text='Ready'))

        result = api._serialize_wait_condition(condition)

        assert 'exists' in result
        assert result['exists']['text'] == 'Ready'

    def test_not_exists_condition(self, api):
        """WaitCondition with not_exists serializes correctly."""
        from adare.types.playbook import WaitCondition, Target
        condition = WaitCondition(not_exists=Target(image='loading.png'))

        result = api._serialize_wait_condition(condition)

        assert 'not_exists' in result
        assert result['not_exists']['image'] == 'loading.png'

    def test_all_condition(self, api):
        """WaitCondition with all (AND) serializes correctly."""
        from adare.types.playbook import WaitCondition, Target
        cond1 = WaitCondition(exists=Target(text='A'))
        cond2 = WaitCondition(exists=Target(text='B'))
        condition = WaitCondition(all=[cond1, cond2])

        result = api._serialize_wait_condition(condition)

        assert 'all' in result
        assert len(result['all']) == 2
        assert result['all'][0]['exists']['text'] == 'A'
        assert result['all'][1]['exists']['text'] == 'B'

    def test_any_condition(self, api):
        """WaitCondition with any (OR) serializes correctly."""
        from adare.types.playbook import WaitCondition, Target
        cond1 = WaitCondition(exists=Target(text='A'))
        cond2 = WaitCondition(exists=Target(text='B'))
        condition = WaitCondition(any=[cond1, cond2])

        result = api._serialize_wait_condition(condition)

        assert 'any' in result
        assert len(result['any']) == 2

    def test_negate_condition(self, api):
        """WaitCondition with negate (NOT) serializes correctly."""
        from adare.types.playbook import WaitCondition, Target
        inner = WaitCondition(exists=Target(text='Error'))
        condition = WaitCondition(negate=inner)

        result = api._serialize_wait_condition(condition)

        assert 'negate' in result
        assert result['negate']['exists']['text'] == 'Error'

    def test_nested_conditions(self, api):
        """Nested WaitConditions serialize correctly."""
        from adare.types.playbook import WaitCondition, Target
        leaf1 = WaitCondition(exists=Target(text='A'))
        leaf2 = WaitCondition(not_exists=Target(image='loading.png'))
        combined = WaitCondition(all=[leaf1, leaf2])
        outer = WaitCondition(negate=combined)

        result = api._serialize_wait_condition(outer)

        assert 'negate' in result
        assert 'all' in result['negate']


# === DESERIALIZATION TESTS ===

class TestJsonToSettings:
    """Tests for _json_to_settings method."""

    @pytest.fixture
    def api(self):
        return create_playbook_api()

    def test_empty_json(self, api):
        """Empty JSON returns default Settings."""
        result = api._json_to_settings({})

        assert result.idle == 0.1
        assert result.continue_on_test_failure is False

    def test_none_json(self, api):
        """None returns default Settings."""
        result = api._json_to_settings(None)

        assert result.idle == 0.1

    def test_custom_values(self, api):
        """Custom values deserialize correctly."""
        settings_json = {
            'idle': 0.5,
            'timeout': 30.0,
            'screenshot': {'format': 'png'},
            'continue_on_test_failure': True
        }

        result = api._json_to_settings(settings_json)

        assert result.idle == 0.5
        assert result.timeout == 30.0
        assert result.screenshot == {'format': 'png'}
        assert result.continue_on_test_failure is True


class TestJsonToTarget:
    """Tests for _json_to_target method."""

    @pytest.fixture
    def api(self):
        return create_playbook_api()

    def test_none_returns_none(self, api):
        """None returns None."""
        result = api._json_to_target(None)
        assert result is None

    def test_empty_dict_returns_none(self, api):
        """Empty dict returns None (same as None input)."""
        # Note: The implementation treats empty dict as falsy, returning None
        result = api._json_to_target({})
        assert result is None

    def test_image_target(self, api):
        """Image target deserializes correctly."""
        result = api._json_to_target({'image': 'button.png'})
        assert result.image == 'button.png'

    def test_text_target(self, api):
        """Text target deserializes correctly."""
        result = api._json_to_target({'text': 'Click Me'})
        assert result.text == 'Click Me'

    def test_position_target(self, api):
        """Position target deserializes correctly."""
        result = api._json_to_target({'position': [100, 200]})
        assert result.position == [100, 200]

    def test_target_with_strategy(self, api):
        """Target with strategy deserializes correctly."""
        target_json = {
            'text': 'Label',
            'strategy': {'SweepStrategy': {'index': 3}}
        }

        result = api._json_to_target(target_json)

        assert result.text == 'Label'
        assert result.strategy is not None
        assert result.strategy.index == 3


class TestJsonToStrategy:
    """Tests for _json_to_strategy method."""

    @pytest.fixture
    def api(self):
        return create_playbook_api()

    def test_sweep_strategy(self, api):
        """SweepStrategy deserializes correctly."""
        result = api._json_to_strategy({'SweepStrategy': {'index': 5}})

        from adare.types.playbook import SweepStrategy
        assert isinstance(result, SweepStrategy)
        assert result.index == 5

    def test_best_confidence_strategy(self, api):
        """BestConfidenceStrategy deserializes correctly."""
        result = api._json_to_strategy({'BestConfidenceStrategy': {}})

        from adare.types.playbook import BestConfidenceStrategy
        assert isinstance(result, BestConfidenceStrategy)

    def test_closest_to_strategy(self, api):
        """ClosestToStrategy deserializes correctly."""
        result = api._json_to_strategy({'ClosestToStrategy': {'x': 100, 'y': 200}})

        from adare.types.playbook import ClosestToStrategy
        assert isinstance(result, ClosestToStrategy)
        assert result.x == 100
        assert result.y == 200

    @pytest.mark.parametrize("strategy_json,strategy_class_name", [
        ({'TopLeftStrategy': {}}, 'TopLeftStrategy'),
        ({'TopRightStrategy': {}}, 'TopRightStrategy'),
        ({'BottomLeftStrategy': {}}, 'BottomLeftStrategy'),
        ({'BottomRightStrategy': {}}, 'BottomRightStrategy'),
        ({'LargestStrategy': {}}, 'LargestStrategy'),
        ({'SmallestStrategy': {}}, 'SmallestStrategy'),
    ])
    def test_directional_strategies(self, api, strategy_json, strategy_class_name):
        """Directional strategies deserialize correctly."""
        from adare.types import playbook

        result = api._json_to_strategy(strategy_json)

        expected_class = getattr(playbook, strategy_class_name)
        assert isinstance(result, expected_class)

    def test_unknown_strategy_raises(self, api):
        """Unknown strategy type raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            api._json_to_strategy({'UnknownStrategy': {}})

        assert 'Unknown strategy type' in str(exc_info.value)


class TestJsonToConditions:
    """Tests for _json_to_conditions method."""

    @pytest.fixture
    def api(self):
        return create_playbook_api()

    def test_none_returns_none(self, api):
        """None returns None."""
        result = api._json_to_conditions(None)
        assert result is None

    def test_empty_dict_returns_none(self, api):
        """Empty dict returns None."""
        result = api._json_to_conditions({})
        assert result is None

    def test_missing_when_key(self, api):
        """Dict without 'when' key returns None."""
        result = api._json_to_conditions({'other': 'value'})
        assert result is None

    def test_exists_condition(self, api):
        """Exists condition deserializes correctly."""
        conditions_json = {
            'when': [{'type': 'exists', 'text': 'Button'}]
        }

        result = api._json_to_conditions(conditions_json)

        assert result is not None
        assert len(result) == 1
        assert result[0].text == 'Button'

    def test_not_exists_condition(self, api):
        """NotExists condition deserializes correctly."""
        conditions_json = {
            'when': [{'type': 'notexists', 'image': 'loading.png'}]
        }

        result = api._json_to_conditions(conditions_json)

        assert result is not None
        assert len(result) == 1
        assert result[0].image == 'loading.png'

    def test_multiple_conditions(self, api):
        """Multiple conditions deserialize correctly."""
        conditions_json = {
            'when': [
                {'type': 'exists', 'text': 'Button'},
                {'type': 'notexists', 'image': 'loading.png'}
            ]
        }

        result = api._json_to_conditions(conditions_json)

        assert result is not None
        assert len(result) == 2


class TestPlaybookItemToAction:
    """Tests for _playbook_item_to_action method."""

    @pytest.fixture
    def api(self):
        return create_playbook_api()

    def test_click_action(self, api):
        """ClickAction deserializes correctly."""
        item = create_mock_playbook_item(
            action_type='click',
            target={'text': 'Button'},
            parameters={'type': 'double'},
            description='Double click button'
        )

        result = api._playbook_item_to_action(item)

        from adare.types.playbook import ClickAction
        assert isinstance(result, ClickAction)
        assert result.target.text == 'Button'
        assert result.type == 'double'
        assert result.description == 'Double click button'

    def test_keyboard_action(self, api):
        """KeyboardAction deserializes correctly."""
        item = create_mock_playbook_item(
            action_type='keyboard',
            parameters={'key': 'enter', 'text': None, 'combination': None}
        )

        result = api._playbook_item_to_action(item)

        from adare.types.playbook import KeyboardAction
        assert isinstance(result, KeyboardAction)
        assert result.key == 'enter'

    def test_idle_action(self, api):
        """IdleAction deserializes correctly."""
        item = create_mock_playbook_item(
            action_type='idle',
            parameters={'duration': 2.5}
        )

        result = api._playbook_item_to_action(item)

        from adare.types.playbook import IdleAction
        assert isinstance(result, IdleAction)
        assert result.duration == 2.5

    def test_scroll_action(self, api):
        """ScrollAction deserializes correctly."""
        item = create_mock_playbook_item(
            action_type='scroll',
            parameters={'direction': 'down', 'amount': 3}
        )

        result = api._playbook_item_to_action(item)

        from adare.types.playbook import ScrollAction
        assert isinstance(result, ScrollAction)
        assert result.direction == 'down'
        assert result.amount == 3

    def test_goto_action(self, api):
        """GotoAction deserializes correctly."""
        item = create_mock_playbook_item(
            action_type='goto',
            target={'text': 'Menu'}
        )

        result = api._playbook_item_to_action(item)

        from adare.types.playbook import GotoAction
        assert isinstance(result, GotoAction)
        assert result.target.text == 'Menu'

    def test_actiontest_action(self, api):
        """ActionTestAction deserializes correctly."""
        item = create_mock_playbook_item(
            action_type='actiontest',
            parameters={'name': 'validate_login'}
        )

        result = api._playbook_item_to_action(item)

        from adare.types.playbook import ActionTestAction
        assert isinstance(result, ActionTestAction)
        assert result.name == 'validate_login'

    def test_command_action(self, api):
        """CommandAction deserializes correctly."""
        item = create_mock_playbook_item(
            action_type='command',
            parameters={
                'command': 'ls -la',
                'cwd': '/home/user',
                'timeout': 30.0,
                'shell': True,
                'admin': False,
                'background': False
            }
        )

        result = api._playbook_item_to_action(item)

        from adare.types.playbook import CommandAction
        assert isinstance(result, CommandAction)
        assert result.command == 'ls -la'
        assert result.cwd == '/home/user'
        assert result.timeout == 30.0
        assert result.shell is True

    def test_screenshot_action(self, api):
        """ScreenshotAction deserializes correctly."""
        item = create_mock_playbook_item(
            action_type='screenshot',
            parameters={'name': 'login_screen', 'x': 0, 'y': 0, 'width': 800, 'height': 600}
        )

        result = api._playbook_item_to_action(item)

        from adare.types.playbook import ScreenshotAction
        assert isinstance(result, ScreenshotAction)
        assert result.name == 'login_screen'
        assert result.width == 800

    def test_savetimestamp_action(self, api):
        """SaveTimestampAction deserializes correctly."""
        item = create_mock_playbook_item(
            action_type='savetimestamp',
            parameters={'variable': 'start_time'}
        )

        result = api._playbook_item_to_action(item)

        from adare.types.playbook import SaveTimestampAction
        assert isinstance(result, SaveTimestampAction)
        assert result.variable == 'start_time'

    def test_pull_action(self, api):
        """PullAction deserializes correctly."""
        item = create_mock_playbook_item(
            action_type='pull',
            parameters={'src': '/path/to/file', 'dst': 'artifacts', 'mode': 'hypervisor'}
        )

        result = api._playbook_item_to_action(item)

        from adare.types.playbook import PullAction
        assert isinstance(result, PullAction)
        assert result.src == '/path/to/file'
        assert result.mode == 'hypervisor'

    def test_pull_action_list_src(self, api):
        """PullAction with list src deserializes correctly."""
        item = create_mock_playbook_item(
            action_type='pull',
            parameters={'src': ['/path/a', '/path/b'], 'mode': 'hypervisor'}
        )

        result = api._playbook_item_to_action(item)

        from adare.types.playbook import PullAction
        assert isinstance(result, PullAction)
        assert result.src == ['/path/a', '/path/b']

    def test_pause_action(self, api):
        """PauseAction deserializes correctly."""
        item = create_mock_playbook_item(
            action_type='pause',
            parameters={'message': 'Check the screen', 'name': 'manual_check'}
        )

        result = api._playbook_item_to_action(item)

        from adare.types.playbook import PauseAction
        assert isinstance(result, PauseAction)
        assert result.message == 'Check the screen'

    def test_waituntil_action(self, api):
        """WaitUntilAction deserializes correctly."""
        item = create_mock_playbook_item(
            action_type='waituntil',
            parameters={
                'condition': {'exists': {'text': 'Ready'}},
                'timeout': 120.0,
                'check_interval': 1.0,
                'initial_delay': 2.0
            }
        )

        result = api._playbook_item_to_action(item)

        from adare.types.playbook import WaitUntilAction
        assert isinstance(result, WaitUntilAction)
        assert result.timeout == 120.0
        assert result.condition.exists.text == 'Ready'

    def test_drag_action(self, api):
        """DragAction deserializes correctly."""
        item = create_mock_playbook_item(
            action_type='drag',
            parameters={
                'src': {'position': [100, 100]},
                'dst': {'position': [200, 200]}
            }
        )

        result = api._playbook_item_to_action(item)

        from adare.types.playbook import DragAction
        assert isinstance(result, DragAction)
        assert result.src.position == [100, 100]
        assert result.dst.position == [200, 200]

    def test_snapshotfilesystem_action(self, api):
        """SnapshotFilesystemAction deserializes correctly."""
        item = create_mock_playbook_item(
            action_type='snapshotfilesystem',
            parameters={'variable': 'fs_snap', 'root_path': '/home', 'timeout': 600.0}
        )

        result = api._playbook_item_to_action(item)

        from adare.types.playbook import SnapshotFilesystemAction
        assert isinstance(result, SnapshotFilesystemAction)
        assert result.variable == 'fs_snap'

    def test_pullchangedfiles_action(self, api):
        """PullChangedFilesAction deserializes correctly."""
        item = create_mock_playbook_item(
            action_type='pullchangedfiles',
            parameters={
                'snapshot_before': 'snap1',
                'snapshot_after': 'snap2',
                'dst': 'changed',
                'mode': 'websocket',
                'include_modified': True,
                'include_added': True
            }
        )

        result = api._playbook_item_to_action(item)

        from adare.types.playbook import PullChangedFilesAction
        assert isinstance(result, PullChangedFilesAction)
        assert result.snapshot_before == 'snap1'

    def test_unknown_action_type_raises(self, api):
        """Unknown action type raises ValueError."""
        item = create_mock_playbook_item(action_type='unknown_action')

        with pytest.raises(ValueError) as exc_info:
            api._playbook_item_to_action(item)

        assert 'Unknown action type' in str(exc_info.value)

    def test_json_string_parameters(self, api):
        """Parameters stored as JSON string are parsed."""
        item = create_mock_playbook_item(
            action_type='idle',
            parameters='{"duration": 2.5}'
        )

        result = api._playbook_item_to_action(item)

        from adare.types.playbook import IdleAction
        assert isinstance(result, IdleAction)
        assert result.duration == 2.5


class TestJsonToWaitCondition:
    """Tests for _json_to_wait_condition method."""

    @pytest.fixture
    def api(self):
        return create_playbook_api()

    def test_exists_condition(self, api):
        """Exists condition deserializes correctly."""
        result = api._json_to_wait_condition({'exists': {'text': 'Ready'}})

        assert result.exists is not None
        assert result.exists.text == 'Ready'

    def test_not_exists_condition(self, api):
        """Not exists condition deserializes correctly."""
        result = api._json_to_wait_condition({'not_exists': {'image': 'loading.png'}})

        assert result.not_exists is not None
        assert result.not_exists.image == 'loading.png'

    def test_all_condition(self, api):
        """All (AND) condition deserializes correctly."""
        condition_data = {
            'all': [
                {'exists': {'text': 'A'}},
                {'exists': {'text': 'B'}}
            ]
        }

        result = api._json_to_wait_condition(condition_data)

        assert result.all is not None
        assert len(result.all) == 2

    def test_any_condition(self, api):
        """Any (OR) condition deserializes correctly."""
        condition_data = {
            'any': [
                {'exists': {'text': 'A'}},
                {'exists': {'text': 'B'}}
            ]
        }

        result = api._json_to_wait_condition(condition_data)

        assert result.any is not None
        assert len(result.any) == 2

    def test_negate_condition(self, api):
        """Negate (NOT) condition deserializes correctly."""
        condition_data = {
            'negate': {'exists': {'text': 'Error'}}
        }

        result = api._json_to_wait_condition(condition_data)

        assert result.negate is not None
        assert result.negate.exists.text == 'Error'

    def test_deeply_nested(self, api):
        """Deeply nested conditions deserialize correctly."""
        condition_data = {
            'all': [
                {'negate': {'exists': {'text': 'Error'}}},
                {'any': [
                    {'exists': {'text': 'A'}},
                    {'not_exists': {'image': 'loading.png'}}
                ]}
            ]
        }

        result = api._json_to_wait_condition(condition_data)

        assert result.all is not None
        assert len(result.all) == 2
        assert result.all[0].negate.exists.text == 'Error'
        assert result.all[1].any is not None

    def test_invalid_condition_raises(self, api):
        """Invalid condition data raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            api._json_to_wait_condition({})

        assert 'Invalid WaitCondition' in str(exc_info.value)


# === ROUND-TRIP SERIALIZATION TESTS ===

class TestSerializationRoundTrip:
    """Tests for round-trip serialization/deserialization."""

    @pytest.fixture
    def api(self):
        return create_playbook_api()

    def test_settings_round_trip(self, api):
        """Settings survives round-trip serialization."""
        from adare.types.playbook import Settings, Playbook as PlaybookType

        original_settings = Settings(
            idle=0.5,
            timeout=30.0,
            continue_on_test_failure=True
        )
        config = PlaybookType(actions=[], settings=original_settings)

        # Serialize
        json_data = api._config_to_settings_json(config)

        # Deserialize
        result = api._json_to_settings(json_data)

        assert result.idle == original_settings.idle
        assert result.timeout == original_settings.timeout
        assert result.continue_on_test_failure == original_settings.continue_on_test_failure

    def test_target_round_trip(self, api):
        """Target survives round-trip serialization."""
        from adare.types.playbook import Target, SweepStrategy

        original = Target(
            text='Button',
            image='icon.png',
            strategy=SweepStrategy(index=3)
        )

        # Serialize
        json_data = api._target_to_json(original)

        # Deserialize
        result = api._json_to_target(json_data)

        assert result.text == original.text
        assert result.image == original.image
        assert result.strategy.index == original.strategy.index

    @pytest.mark.parametrize("strategy_class,kwargs", [
        ('SweepStrategy', {'index': 5}),
        ('BestConfidenceStrategy', {}),
        ('ClosestToStrategy', {'x': 100, 'y': 200}),
        ('TopLeftStrategy', {}),
        ('TopRightStrategy', {}),
        ('BottomLeftStrategy', {}),
        ('BottomRightStrategy', {}),
        ('LargestStrategy', {}),
        ('SmallestStrategy', {}),
    ])
    def test_strategy_round_trip(self, api, strategy_class, kwargs):
        """All strategies survive round-trip serialization."""
        from adare.types import playbook

        cls = getattr(playbook, strategy_class)
        original = cls(**kwargs)

        # Serialize
        json_data = api._strategy_to_json(original)

        # Deserialize
        result = api._json_to_strategy(json_data)

        assert type(result).__name__ == strategy_class
        for key, value in kwargs.items():
            assert getattr(result, key) == value

    def test_wait_condition_round_trip(self, api):
        """WaitCondition survives round-trip serialization."""
        from adare.types.playbook import WaitCondition, Target

        original = WaitCondition(
            all=[
                WaitCondition(exists=Target(text='A')),
                WaitCondition(negate=WaitCondition(not_exists=Target(image='loading.png')))
            ]
        )

        # Serialize
        json_data = api._serialize_wait_condition(original)

        # Deserialize
        result = api._json_to_wait_condition(json_data)

        assert result.all is not None
        assert len(result.all) == 2
        assert result.all[0].exists.text == 'A'
        assert result.all[1].negate.not_exists.image == 'loading.png'


# === DATABASE METHOD TESTS ===

class TestCreateActionExecution:
    """Tests for create_action_execution method."""

    @pytest.fixture
    def api(self):
        return create_playbook_api()

    def test_creates_execution_record(self, api):
        """Creates ActionExecution with correct fields."""
        api._session.add = MagicMock()
        api._session.flush = MagicMock()

        result = api.create_action_execution(
            playbook_item_id='item_123',
            experiment_run_id='run_123',
            status='pending'
        )

        api._session.add.assert_called_once()
        api._session.flush.assert_called_once()

    def test_default_status_pending(self, api):
        """Default status is 'pending'."""
        api._session.add = MagicMock()
        api._session.flush = MagicMock()

        result = api.create_action_execution(
            playbook_item_id='item_123',
            experiment_run_id='run_123'
        )

        # Verify the created object has pending status
        call_args = api._session.add.call_args
        created_execution = call_args[0][0]
        assert created_execution.status == 'pending'


class TestUpdateActionExecutionStart:
    """Tests for update_action_execution_start method."""

    @pytest.fixture
    def api(self):
        return create_playbook_api()

    def test_marks_execution_running(self, api):
        """Marks execution as running with started_at timestamp."""
        mock_execution = create_mock_action_execution()
        api._session.query.return_value.filter.return_value.first.return_value = mock_execution

        api.update_action_execution_start('exec_123')

        assert mock_execution.status == 'running'
        assert mock_execution.started_at is not None

    def test_handles_missing_execution(self, api):
        """Handles case where execution not found."""
        api._session.query.return_value.filter.return_value.first.return_value = None

        # Should not raise
        api.update_action_execution_start('nonexistent_id')


class TestUpdateActionExecutionComplete:
    """Tests for update_action_execution_complete method."""

    @pytest.fixture
    def api(self):
        return create_playbook_api()

    def test_marks_execution_success(self, api):
        """Marks execution as success."""
        mock_execution = create_mock_action_execution()
        api._session.query.return_value.filter.return_value.first.return_value = mock_execution

        api.update_action_execution_complete(
            execution_id='exec_123',
            success=True,
            result_data={'position': [100, 200]}
        )

        assert mock_execution.status == 'success'
        assert mock_execution.result_data == {'position': [100, 200]}
        assert mock_execution.completed_at is not None

    def test_marks_execution_failed(self, api):
        """Marks execution as failed with error message."""
        mock_execution = create_mock_action_execution()
        api._session.query.return_value.filter.return_value.first.return_value = mock_execution

        api.update_action_execution_complete(
            execution_id='exec_123',
            success=False,
            error_message='Target not found'
        )

        assert mock_execution.status == 'failed'
        assert mock_execution.error_message == 'Target not found'

    def test_sets_attempt_number(self, api):
        """Sets attempt number correctly."""
        mock_execution = create_mock_action_execution()
        api._session.query.return_value.filter.return_value.first.return_value = mock_execution

        api.update_action_execution_complete(
            execution_id='exec_123',
            success=True,
            attempt_number=3
        )

        assert mock_execution.attempt_number == 3


class TestGetPlaybookItems:
    """Tests for get_playbook_items method."""

    @pytest.fixture
    def api(self):
        return create_playbook_api()

    def test_returns_items_by_playbook(self, api):
        """Returns items filtered by playbook_id."""
        mock_items = [
            create_mock_playbook_item(sequence_order=0),
            create_mock_playbook_item(sequence_order=1),
        ]
        api._session.query.return_value.filter.return_value.filter.return_value.order_by.return_value.all.return_value = mock_items

        result = api.get_playbook_items('playbook_123')

        assert len(result) == 2

    def test_filters_by_parent_id(self, api):
        """Filters by parent_id when provided."""
        api._session.query.return_value.filter.return_value.filter.return_value.order_by.return_value.all.return_value = []

        api.get_playbook_items('playbook_123', parent_id='parent_456')

        # Verify filter was called
        api._session.query.assert_called()


class TestGetActionExecutionsByRun:
    """Tests for get_action_executions_by_run method."""

    @pytest.fixture
    def api(self):
        return create_playbook_api()

    def test_returns_executions_for_run(self, api):
        """Returns all executions for an experiment run."""
        mock_executions = [
            create_mock_action_execution(),
            create_mock_action_execution(execution_id='exec_456'),
        ]
        api._session.query.return_value.filter.return_value.order_by.return_value.all.return_value = mock_executions

        result = api.get_action_executions_by_run('run_123')

        assert len(result) == 2


class TestRecoverPlaybookYaml:
    """Tests for recover_playbook_yaml method."""

    @pytest.fixture
    def api(self):
        return create_playbook_api()

    def test_returns_original_yaml(self, api):
        """Returns original YAML content."""
        mock_playbook = create_mock_playbook(original_yaml_content="actions:\n  - idle:\n      duration: 1.0")
        api._session.query.return_value.filter.return_value.first.return_value = mock_playbook

        result = api.recover_playbook_yaml('exp_123')

        assert 'actions:' in result
        assert 'idle:' in result

    def test_raises_when_no_playbook(self, api):
        """Raises ValueError when no playbook found."""
        api._session.query.return_value.filter.return_value.first.return_value = None

        with pytest.raises(ValueError) as exc_info:
            api.recover_playbook_yaml('exp_123')

        assert 'No playbook found' in str(exc_info.value)

    def test_raises_when_no_yaml_content(self, api):
        """Raises ValueError when no YAML content stored."""
        mock_playbook = create_mock_playbook(original_yaml_content=None)
        api._session.query.return_value.filter.return_value.first.return_value = mock_playbook

        with pytest.raises(ValueError) as exc_info:
            api.recover_playbook_yaml('exp_123')

        assert 'No original YAML content' in str(exc_info.value)


class TestGetPlaybookByExperimentId:
    """Tests for get_playbook_by_experiment_id method."""

    @pytest.fixture
    def api(self):
        return create_playbook_api()

    def test_returns_playbook(self, api):
        """Returns playbook for experiment."""
        mock_playbook = create_mock_playbook()
        api._session.query.return_value.filter.return_value.first.return_value = mock_playbook

        result = api.get_playbook_by_experiment_id('exp_123')

        assert result == mock_playbook

    def test_returns_none_when_not_found(self, api):
        """Returns None when no playbook found."""
        api._session.query.return_value.filter.return_value.first.return_value = None

        result = api.get_playbook_by_experiment_id('nonexistent')

        assert result is None


# === EDGE CASE TESTS ===

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.fixture
    def api(self):
        return create_playbook_api()

    def test_empty_target_serialization(self, api):
        """Empty Target serializes to empty dict."""
        from adare.types.playbook import Target
        target = Target()

        result = api._target_to_json(target)

        assert result == {}

    def test_action_with_no_description(self, api):
        """Action with empty description handled correctly."""
        item = create_mock_playbook_item(
            action_type='click',
            target={'text': 'Button'},
            parameters={'type': 'left'},
            description=None
        )

        result = api._playbook_item_to_action(item)

        assert result.description == ''

    def test_keyboard_action_with_combination(self, api):
        """KeyboardAction with combination deserializes correctly."""
        item = create_mock_playbook_item(
            action_type='keyboard',
            parameters={'combination': ['ctrl', 'c']}
        )

        result = api._playbook_item_to_action(item)

        from adare.types.playbook import KeyboardAction
        assert isinstance(result, KeyboardAction)
        assert result.combination == ['ctrl', 'c']

    def test_keyboard_action_with_text(self, api):
        """KeyboardAction with text deserializes correctly."""
        item = create_mock_playbook_item(
            action_type='keyboard',
            parameters={'text': 'Hello World'}
        )

        result = api._playbook_item_to_action(item)

        from adare.types.playbook import KeyboardAction
        assert isinstance(result, KeyboardAction)
        assert result.text == 'Hello World'

    def test_click_action_default_type(self, api):
        """ClickAction defaults to 'left' type."""
        item = create_mock_playbook_item(
            action_type='click',
            target={'text': 'Button'},
            parameters={}
        )

        result = api._playbook_item_to_action(item)

        assert result.type == 'left'

    def test_scroll_action_defaults(self, api):
        """ScrollAction uses defaults for missing parameters."""
        item = create_mock_playbook_item(
            action_type='scroll',
            parameters={}
        )

        result = api._playbook_item_to_action(item)

        assert result.direction == 'down'
        assert result.amount == 1

    def test_waituntil_action_defaults(self, api):
        """WaitUntilAction uses defaults for missing parameters."""
        item = create_mock_playbook_item(
            action_type='waituntil',
            parameters={'condition': {'exists': {'text': 'Ready'}}}
        )

        result = api._playbook_item_to_action(item)

        assert result.timeout == 60.0
        assert result.check_interval == 0.0
        assert result.initial_delay == 5.0
