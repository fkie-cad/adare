
import pytest
from unittest.mock import MagicMock, patch
from adare.backend.experiment.execution.simple_actions import SimpleActionsExecutor
from adare.types.playbook import KeyboardAction

@pytest.fixture
def mock_deps():
    ws_client = MagicMock()
    target_res = MagicMock()
    ws_client.execute_shell = MagicMock()
    return ws_client, target_res

@patch('adare.backend.experiment.execution.gui_executor_factory.create_gui_executor')
@patch('adare.backend.experiment.execution.gui_executor_factory.resolve_gui_execution_mode')
async def test_execute_keyboard_returns_data(mock_resolve, mock_create, mock_deps):
    ws_client, target_res = mock_deps
    
    # Mock GUI executor
    mock_gui = MagicMock()
    # keyboard must be awaitable
    async def async_keyboard(*args, **kwargs):
        return {'status': 'success', 'message': 'ok'}
    mock_gui.keyboard = async_keyboard
    mock_create.return_value = mock_gui
    
    executor = SimpleActionsExecutor(ws_client, target_res)
    
    # Test Single Key
    action = KeyboardAction(key='enter')
    result = await executor.execute_keyboard(action)
    assert result.success is True
    assert result.data == {'key': 'enter'}

    # Test Text
    action = KeyboardAction(text='hello')
    result = await executor.execute_keyboard(action)
    assert result.success is True
    assert result.data == {'text': 'hello'}

    # Test Combination
    action = KeyboardAction(combination=['ctrl', 'c'])
    result = await executor.execute_keyboard(action)
    assert result.success is True
    assert result.data == {'combination': ['ctrl', 'c']}
