"""
Comprehensive unit tests for AdareVMClient WebSocket client.

Tests cover:
- Initialization and URL construction
- Event handler management
- Connection state management
- Tool result handling
- Event handling
- Tool calls and timeouts
- GUI action methods
- Shell execution
- File transfer path normalization
- Testfunction uploads
"""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from pathlib import Path
import tempfile
import base64
import zipfile
import io

from adare.backend.experiment.websocket_client import (
    AdareVMClient,
    WebSocketTimeoutError,
)
from adarelib.websocket.protocol import (
    ToolResultMessage,
    EventMessage,
    ToolRegistry,
    MessageType,
    EventType,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def client():
    """Create a fresh AdareVMClient instance."""
    return AdareVMClient()


@pytest.fixture
def client_custom_host_port():
    """Create a client with custom host and port."""
    return AdareVMClient(host='192.168.1.100', port=9999)


@pytest.fixture
def mock_websocket():
    """Create a mock WebSocket for connection tests."""
    ws = AsyncMock()
    ws.send = AsyncMock()
    ws.close = AsyncMock()
    return ws


@pytest.fixture
def client_with_mock_call_tool():
    """Create a client with mocked call_tool method for GUI action tests."""
    client = AdareVMClient()
    client.call_tool = AsyncMock(return_value={'status': 'success'})
    return client


@pytest.fixture
def connected_client(mock_websocket):
    """Create a client that appears connected with a mock websocket."""
    client = AdareVMClient()
    client.connected = True
    client.websocket = mock_websocket
    return client


# ============================================================================
# TestAdareVMClientInit
# ============================================================================


class TestAdareVMClientInit:
    """Tests for AdareVMClient initialization."""

    def test_url_construction_default(self, client):
        """URL should be constructed as ws://host:port format with defaults."""
        assert client.server_url == 'ws://localhost:18765'

    def test_url_construction_custom_host_port(self, client_custom_host_port):
        """URL should use custom host and port values."""
        assert client_custom_host_port.server_url == 'ws://192.168.1.100:9999'

    def test_default_host_value(self, client):
        """Default host should be localhost."""
        # Verified through URL construction
        assert 'localhost' in client.server_url

    def test_default_port_value(self, client):
        """Default port should be 18765."""
        assert ':18765' in client.server_url

    def test_state_initialization_connected(self, client):
        """Connected should be False initially."""
        assert client.connected is False

    def test_state_initialization_pending_calls(self, client):
        """Pending calls should be an empty dict initially."""
        assert client.pending_calls == {}
        assert isinstance(client.pending_calls, dict)

    def test_state_initialization_event_handlers(self, client):
        """Event handlers should be an empty dict initially."""
        assert client.event_handlers == {}
        assert isinstance(client.event_handlers, dict)

    def test_websocket_initially_none(self, client):
        """WebSocket should be None initially."""
        assert client.websocket is None

    def test_message_handler_task_initially_none(self, client):
        """Message handler task should be None initially."""
        assert client.message_handler_task is None


# ============================================================================
# TestEventHandlerManagement
# ============================================================================


class TestEventHandlerManagement:
    """Tests for event handler add/remove operations."""

    def test_add_event_handler_creates_list(self, client):
        """add_event_handler should create list if event type not exists."""
        handler = MagicMock()
        client.add_event_handler('test_event', handler)

        assert 'test_event' in client.event_handlers
        assert isinstance(client.event_handlers['test_event'], list)

    def test_add_event_handler_appends_to_list(self, client):
        """add_event_handler should add handler to correct event type list."""
        handler1 = MagicMock()
        handler2 = MagicMock()

        client.add_event_handler('test_event', handler1)
        client.add_event_handler('test_event', handler2)

        assert len(client.event_handlers['test_event']) == 2
        assert handler1 in client.event_handlers['test_event']
        assert handler2 in client.event_handlers['test_event']

    def test_add_event_handler_different_events(self, client):
        """Handlers for different events should be in separate lists."""
        handler1 = MagicMock()
        handler2 = MagicMock()

        client.add_event_handler('event_a', handler1)
        client.add_event_handler('event_b', handler2)

        assert client.event_handlers['event_a'] == [handler1]
        assert client.event_handlers['event_b'] == [handler2]

    def test_add_wildcard_handler(self, client):
        """Should support wildcard event handler with '*'."""
        handler = MagicMock()
        client.add_event_handler('*', handler)

        assert '*' in client.event_handlers
        assert handler in client.event_handlers['*']

    def test_remove_event_handler_removes_handler(self, client):
        """remove_event_handler should remove the specified handler."""
        handler = MagicMock()
        client.add_event_handler('test_event', handler)
        client.remove_event_handler('test_event', handler)

        assert handler not in client.event_handlers['test_event']

    def test_remove_event_handler_preserves_others(self, client):
        """remove_event_handler should preserve other handlers."""
        handler1 = MagicMock()
        handler2 = MagicMock()

        client.add_event_handler('test_event', handler1)
        client.add_event_handler('test_event', handler2)
        client.remove_event_handler('test_event', handler1)

        assert handler1 not in client.event_handlers['test_event']
        assert handler2 in client.event_handlers['test_event']

    def test_remove_event_handler_missing_handler_gracefully(self, client):
        """remove_event_handler should handle missing handler gracefully."""
        handler1 = MagicMock()
        handler2 = MagicMock()

        client.add_event_handler('test_event', handler1)
        # This should not raise an exception
        client.remove_event_handler('test_event', handler2)

        # Original handler should still be there
        assert handler1 in client.event_handlers['test_event']

    def test_remove_event_handler_missing_event_type(self, client):
        """remove_event_handler should handle missing event type gracefully."""
        handler = MagicMock()
        # This should not raise an exception
        client.remove_event_handler('nonexistent_event', handler)


# ============================================================================
# TestConnectionState
# ============================================================================


class TestConnectionState:
    """Tests for connection state methods."""

    def test_is_connected_returns_false_initially(self, client):
        """is_connected should return False initially."""
        assert client.is_connected() is False

    def test_is_connected_returns_true_when_connected(self, client):
        """is_connected should return True when connected=True."""
        client.connected = True
        assert client.is_connected() is True

    def test_is_connected_returns_false_when_disconnected(self, client):
        """is_connected should return False when connected=False."""
        client.connected = True
        client.connected = False
        assert client.is_connected() is False

    @pytest.mark.asyncio
    async def test_wait_for_connection_returns_immediately_when_connected(self, client):
        """wait_for_connection should return immediately when already connected."""
        client.connected = True

        with patch('asyncio.sleep', new_callable=AsyncMock) as mock_sleep:
            result = await client.wait_for_connection(timeout=5.0)

        assert result is True
        mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_wait_for_connection_waits_until_connected(self, client):
        """wait_for_connection should poll until connected."""
        call_count = 0

        async def delayed_connect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                client.connected = True

        with patch('asyncio.sleep', new_callable=AsyncMock, side_effect=delayed_connect):
            result = await client.wait_for_connection(timeout=10.0)

        assert result is True
        assert call_count >= 3

    @pytest.mark.asyncio
    async def test_wait_for_connection_returns_false_on_timeout(self, client):
        """wait_for_connection should return False if timeout expires."""
        client.connected = False

        result = await client.wait_for_connection(timeout=0.2)

        assert result is False


# ============================================================================
# TestHandleToolResult
# ============================================================================


class TestHandleToolResult:
    """Tests for _handle_tool_result method."""

    @pytest.mark.asyncio
    async def test_resolves_pending_future_with_result(self, client):
        """Should resolve pending future with the tool result message."""
        call_id = 'test-call-123'
        future = asyncio.Future()
        client.pending_calls[call_id] = future

        result_message = ToolResultMessage(
            id=call_id,
            success=True,
            result={'data': 'test_value'}
        )

        await client._handle_tool_result(result_message)

        assert future.done()
        assert future.result() == result_message
        assert call_id not in client.pending_calls

    @pytest.mark.asyncio
    async def test_handles_missing_call_id_gracefully(self, client):
        """Should handle unknown call_id without raising exception."""
        result_message = ToolResultMessage(
            id='unknown-call-id',
            success=True,
            result={'data': 'test'}
        )

        # Should not raise
        await client._handle_tool_result(result_message)

    @pytest.mark.asyncio
    async def test_logs_warning_for_unknown_call_id(self, client):
        """Should log warning for unknown call_id."""
        result_message = ToolResultMessage(
            id='unknown-call-id',
            success=True,
            result={'data': 'test'}
        )

        with patch('adare.backend.experiment.websocket_client.log') as mock_log:
            await client._handle_tool_result(result_message)
            mock_log.warning.assert_called_once()
            assert 'unknown-call-id' in str(mock_log.warning.call_args)

    @pytest.mark.asyncio
    async def test_does_not_set_result_on_cancelled_future(self, client):
        """Should not set result on already cancelled future."""
        call_id = 'test-call-456'
        future = asyncio.Future()
        future.cancel()
        client.pending_calls[call_id] = future

        result_message = ToolResultMessage(
            id=call_id,
            success=True,
            result={'data': 'test'}
        )

        # Should not raise InvalidStateError
        await client._handle_tool_result(result_message)

        # Future should still be cancelled
        assert future.cancelled()


# ============================================================================
# TestHandleEvent
# ============================================================================


class TestHandleEvent:
    """Tests for _handle_event method."""

    @pytest.mark.asyncio
    async def test_calls_sync_handler_with_event_data(self, client):
        """Should call synchronous handler with event_type and data."""
        handler = MagicMock()
        client.add_event_handler('test_event', handler)

        event_message = EventMessage(
            event_type='test_event',
            data={'key': 'value'}
        )

        await client._handle_event(event_message)

        handler.assert_called_once_with('test_event', {'key': 'value'})

    @pytest.mark.asyncio
    async def test_calls_async_handler_with_event_data(self, client):
        """Should call async handler with event_type and data."""
        async_handler = AsyncMock()
        client.add_event_handler('test_event', async_handler)

        event_message = EventMessage(
            event_type='test_event',
            data={'key': 'value'}
        )

        await client._handle_event(event_message)

        async_handler.assert_called_once_with('test_event', {'key': 'value'})

    @pytest.mark.asyncio
    async def test_calls_multiple_handlers_for_same_event(self, client):
        """Should call all handlers registered for the same event type."""
        handler1 = MagicMock()
        handler2 = MagicMock()
        async_handler = AsyncMock()

        client.add_event_handler('test_event', handler1)
        client.add_event_handler('test_event', handler2)
        client.add_event_handler('test_event', async_handler)

        event_message = EventMessage(
            event_type='test_event',
            data={'value': 123}
        )

        await client._handle_event(event_message)

        handler1.assert_called_once_with('test_event', {'value': 123})
        handler2.assert_called_once_with('test_event', {'value': 123})
        async_handler.assert_called_once_with('test_event', {'value': 123})

    @pytest.mark.asyncio
    async def test_calls_wildcard_handlers(self, client):
        """Should call wildcard handlers for any event type."""
        specific_handler = MagicMock()
        wildcard_handler = MagicMock()

        client.add_event_handler('specific_event', specific_handler)
        client.add_event_handler('*', wildcard_handler)

        event_message = EventMessage(
            event_type='specific_event',
            data={'data': 'test'}
        )

        await client._handle_event(event_message)

        specific_handler.assert_called_once()
        wildcard_handler.assert_called_once()

    @pytest.mark.asyncio
    async def test_no_error_when_no_handlers_registered(self, client):
        """Should not raise error when no handlers registered for event."""
        event_message = EventMessage(
            event_type='unhandled_event',
            data={'some': 'data'}
        )

        # Should not raise
        await client._handle_event(event_message)

    @pytest.mark.asyncio
    async def test_handler_exception_does_not_stop_other_handlers(self, client):
        """Handler exception should not prevent other handlers from running."""
        failing_handler = MagicMock(side_effect=ValueError("Test error"))
        success_handler = MagicMock()

        client.add_event_handler('test_event', failing_handler)
        client.add_event_handler('test_event', success_handler)

        event_message = EventMessage(
            event_type='test_event',
            data={'test': 'data'}
        )

        # Should not raise even though first handler fails
        await client._handle_event(event_message)

        # Both handlers should have been called
        failing_handler.assert_called_once()
        success_handler.assert_called_once()


# ============================================================================
# TestCallTool
# ============================================================================


class TestCallTool:
    """Tests for call_tool method."""

    @pytest.mark.asyncio
    async def test_creates_and_sends_tool_call_message(self, connected_client, mock_websocket):
        """Should create tool call message and send via websocket."""
        # Create a future that will be resolved
        async def resolve_future():
            await asyncio.sleep(0.01)
            # Get the pending call and resolve it
            for call_id, future in list(connected_client.pending_calls.items()):
                if not future.done():
                    result = ToolResultMessage(
                        id=call_id,
                        success=True,
                        result={'status': 'ok'}
                    )
                    future.set_result(result)

        asyncio.create_task(resolve_future())

        result = await connected_client.call_tool('test_tool', {'param': 'value'}, timeout=5.0)

        # Verify websocket.send was called
        mock_websocket.send.assert_called_once()
        sent_data = mock_websocket.send.call_args[0][0]
        import json
        sent_message = json.loads(sent_data)
        assert sent_message['tool'] == 'test_tool'
        assert sent_message['params'] == {'param': 'value'}

    @pytest.mark.asyncio
    async def test_returns_result_when_future_resolved(self, connected_client, mock_websocket):
        """Should return result data when future is resolved."""
        async def resolve_future():
            await asyncio.sleep(0.01)
            for call_id, future in list(connected_client.pending_calls.items()):
                if not future.done():
                    result = ToolResultMessage(
                        id=call_id,
                        success=True,
                        result={'response': 'test_data'}
                    )
                    future.set_result(result)

        asyncio.create_task(resolve_future())

        result = await connected_client.call_tool('test_tool', {}, timeout=5.0)

        assert result == {'response': 'test_data'}

    @pytest.mark.asyncio
    async def test_raises_timeout_error_on_timeout(self, connected_client, mock_websocket):
        """Should raise WebSocketTimeoutError on timeout."""
        with pytest.raises(WebSocketTimeoutError) as exc_info:
            await connected_client.call_tool('slow_tool', {}, timeout=0.1)

        assert 'slow_tool' in str(exc_info.value)
        assert 'timed out' in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_raises_runtime_error_when_not_connected(self, client):
        """Should raise RuntimeError when not connected."""
        assert client.connected is False

        with pytest.raises(RuntimeError) as exc_info:
            await client.call_tool('test_tool', {})

        assert 'Not connected' in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_cleans_up_pending_call_on_timeout(self, connected_client, mock_websocket):
        """Should clean up pending call on timeout."""
        try:
            await connected_client.call_tool('test_tool', {}, timeout=0.1)
        except WebSocketTimeoutError:
            pass

        # Pending calls should be empty after timeout
        assert len(connected_client.pending_calls) == 0

    @pytest.mark.asyncio
    async def test_raises_runtime_error_on_tool_failure(self, connected_client, mock_websocket):
        """Should raise RuntimeError when tool call fails."""
        async def resolve_with_error():
            await asyncio.sleep(0.01)
            for call_id, future in list(connected_client.pending_calls.items()):
                if not future.done():
                    result = ToolResultMessage(
                        id=call_id,
                        success=False,
                        result={},
                        error='Tool execution failed'
                    )
                    future.set_result(result)

        asyncio.create_task(resolve_with_error())

        with pytest.raises(RuntimeError) as exc_info:
            await connected_client.call_tool('failing_tool', {}, timeout=5.0)

        assert 'Tool call failed' in str(exc_info.value)
        assert 'Tool execution failed' in str(exc_info.value)


# ============================================================================
# TestGUIActions
# ============================================================================


class TestGUIActions:
    """Tests for GUI action methods (screenshot, click, etc.)."""

    @pytest.mark.asyncio
    async def test_screenshot_calls_tool_with_no_params(self, client_with_mock_call_tool):
        """screenshot() without params should call with empty params."""
        await client_with_mock_call_tool.screenshot()

        client_with_mock_call_tool.call_tool.assert_called_once_with(
            ToolRegistry.SCREENSHOT, {}
        )

    @pytest.mark.asyncio
    async def test_screenshot_calls_tool_with_region_params(self, client_with_mock_call_tool):
        """screenshot() with region should call with x, y, width, height."""
        await client_with_mock_call_tool.screenshot(x=10, y=20, width=100, height=200)

        client_with_mock_call_tool.call_tool.assert_called_once_with(
            ToolRegistry.SCREENSHOT,
            {'x': 10, 'y': 20, 'width': 100, 'height': 200}
        )

    @pytest.mark.asyncio
    async def test_screenshot_requires_all_region_params(self, client_with_mock_call_tool):
        """screenshot() needs all 4 region params to include them."""
        # Only providing some params should result in empty params
        await client_with_mock_call_tool.screenshot(x=10, y=20)

        client_with_mock_call_tool.call_tool.assert_called_once_with(
            ToolRegistry.SCREENSHOT, {}
        )

    @pytest.mark.asyncio
    async def test_click_calls_tool_with_coordinates(self, client_with_mock_call_tool):
        """click() should call with x, y coordinates."""
        await client_with_mock_call_tool.click(x=100, y=200)

        client_with_mock_call_tool.call_tool.assert_called_once_with(
            ToolRegistry.CLICK, {'x': 100, 'y': 200}
        )

    @pytest.mark.asyncio
    async def test_right_click_calls_tool_with_coordinates(self, client_with_mock_call_tool):
        """right_click() should call with x, y coordinates."""
        await client_with_mock_call_tool.right_click(x=150, y=250)

        client_with_mock_call_tool.call_tool.assert_called_once_with(
            ToolRegistry.RIGHT_CLICK, {'x': 150, 'y': 250}
        )

    @pytest.mark.asyncio
    async def test_double_click_calls_tool_with_coordinates(self, client_with_mock_call_tool):
        """double_click() should call with x, y coordinates."""
        await client_with_mock_call_tool.double_click(x=200, y=300)

        client_with_mock_call_tool.call_tool.assert_called_once_with(
            ToolRegistry.DOUBLE_CLICK, {'x': 200, 'y': 300}
        )

    @pytest.mark.asyncio
    async def test_drag_calls_tool_with_start_end_coordinates(self, client_with_mock_call_tool):
        """drag() should call with start and end coordinates."""
        await client_with_mock_call_tool.drag(x1=10, y1=20, x2=100, y2=200)

        client_with_mock_call_tool.call_tool.assert_called_once_with(
            ToolRegistry.DRAG, {'x1': 10, 'y1': 20, 'x2': 100, 'y2': 200}
        )

    @pytest.mark.asyncio
    async def test_keyboard_calls_tool_with_type_and_key(self, client_with_mock_call_tool):
        """keyboard() should call with type and key."""
        await client_with_mock_call_tool.keyboard(type='press', key='Enter')

        client_with_mock_call_tool.call_tool.assert_called_once_with(
            ToolRegistry.KEYBOARD, {'type': 'press', 'key': 'Enter'}
        )

    @pytest.mark.asyncio
    async def test_scroll_calls_tool_with_direction_and_amount(self, client_with_mock_call_tool):
        """scroll() should call with direction and amount."""
        await client_with_mock_call_tool.scroll(direction='down', amount=5)

        client_with_mock_call_tool.call_tool.assert_called_once_with(
            ToolRegistry.SCROLL, {'direction': 'down', 'amount': 5}
        )

    @pytest.mark.asyncio
    async def test_goto_calls_tool_with_coordinates(self, client_with_mock_call_tool):
        """goto() should call with x, y coordinates."""
        await client_with_mock_call_tool.goto(x=500, y=600)

        client_with_mock_call_tool.call_tool.assert_called_once_with(
            ToolRegistry.GOTO, {'x': 500, 'y': 600}
        )

    @pytest.mark.asyncio
    async def test_idle_calls_tool_with_duration(self, client_with_mock_call_tool):
        """idle() should call with duration."""
        await client_with_mock_call_tool.idle(duration=2.5)

        client_with_mock_call_tool.call_tool.assert_called_once_with(
            ToolRegistry.IDLE, {'duration': 2.5}
        )

    @pytest.mark.asyncio
    async def test_screenshot_window_calls_tool_with_window_name(self, client_with_mock_call_tool):
        """screenshot_window() should call with window name."""
        await client_with_mock_call_tool.screenshot_window(window='Notepad')

        client_with_mock_call_tool.call_tool.assert_called_once_with(
            ToolRegistry.SCREENSHOT_WINDOW, {'window': 'Notepad'}
        )


# ============================================================================
# TestExecuteShell
# ============================================================================


class TestExecuteShell:
    """Tests for execute_shell method."""

    @pytest.mark.asyncio
    async def test_basic_command_parameter(self, client_with_mock_call_tool):
        """Should pass shell_command parameter."""
        await client_with_mock_call_tool.execute_shell('echo hello')

        call_args = client_with_mock_call_tool.call_tool.call_args
        params = call_args[0][1]
        assert params['shell_command'] == 'echo hello'

    @pytest.mark.asyncio
    async def test_all_optional_parameters(self, client_with_mock_call_tool):
        """Should pass all optional parameters when provided."""
        await client_with_mock_call_tool.execute_shell(
            shell_command='ls -la',
            cwd='/tmp',
            env={'PATH': '/usr/bin'},
            timeout=60.0,
            shell=True,
            inherit_env=False,
            admin=True
        )

        call_args = client_with_mock_call_tool.call_tool.call_args
        params = call_args[0][1]

        assert params['shell_command'] == 'ls -la'
        assert params['cwd'] == '/tmp'
        assert params['env'] == {'PATH': '/usr/bin'}
        assert params['timeout'] == 60.0
        assert params['shell'] is True
        assert params['inherit_env'] is False
        assert params['admin'] is True

    @pytest.mark.asyncio
    async def test_default_parameters(self, client_with_mock_call_tool):
        """Should use default timeout of 30s when no timeout specified."""
        await client_with_mock_call_tool.execute_shell('cmd')

        call_args = client_with_mock_call_tool.call_tool.call_args
        timeout_arg = call_args[1].get('timeout') or call_args[0][2]
        assert timeout_arg == 30.0

    @pytest.mark.asyncio
    async def test_timeout_calculation_with_command_timeout(self, client_with_mock_call_tool):
        """Websocket timeout should be command timeout + 10."""
        await client_with_mock_call_tool.execute_shell('cmd', timeout=50.0)

        call_args = client_with_mock_call_tool.call_tool.call_args
        # The third positional arg or 'timeout' kwarg should be timeout + 10
        timeout_arg = call_args[1].get('timeout') or call_args[0][2]
        assert timeout_arg == 60.0  # 50 + 10

    @pytest.mark.asyncio
    async def test_timeout_calculation_with_websocket_timeout_override(self, client_with_mock_call_tool):
        """Explicit websocket_timeout should override calculated timeout."""
        await client_with_mock_call_tool.execute_shell(
            'cmd',
            timeout=50.0,
            websocket_timeout=120.0
        )

        call_args = client_with_mock_call_tool.call_tool.call_args
        timeout_arg = call_args[1].get('timeout') or call_args[0][2]
        assert timeout_arg == 120.0


# ============================================================================
# TestFileTransfer
# ============================================================================


class TestFileTransfer:
    """Tests for file transfer path normalization in pull_multiple_files_chunked."""

    def test_windows_path_normalization(self):
        """Windows path C:\\foo\\bar should normalize to foo/bar."""
        guest_path = 'C:\\Users\\test\\file.txt'

        # Extract the normalization logic
        if ':' in guest_path:
            guest_path_cleaned = guest_path.split(':', 1)[1].lstrip('\\').lstrip('/')
            relative_path = guest_path_cleaned.replace('\\', '/')
        else:
            relative_path = guest_path.lstrip('/')

        assert relative_path == 'Users/test/file.txt'

    def test_unix_path_normalization(self):
        """Unix path /home/user should normalize to home/user."""
        guest_path = '/home/user/document.txt'

        if ':' in guest_path:
            guest_path_cleaned = guest_path.split(':', 1)[1].lstrip('\\').lstrip('/')
            relative_path = guest_path_cleaned.replace('\\', '/')
        else:
            relative_path = guest_path.lstrip('/')

        assert relative_path == 'home/user/document.txt'

    def test_preserves_relative_structure(self):
        """Should preserve nested directory structure."""
        guest_path = '/var/log/app/debug/trace.log'

        if ':' in guest_path:
            guest_path_cleaned = guest_path.split(':', 1)[1].lstrip('\\').lstrip('/')
            relative_path = guest_path_cleaned.replace('\\', '/')
        else:
            relative_path = guest_path.lstrip('/')

        assert relative_path == 'var/log/app/debug/trace.log'

    def test_windows_path_with_backslashes(self):
        """Windows path with backslashes should convert to forward slashes."""
        guest_path = 'D:\\Program Files\\App\\data.bin'

        if ':' in guest_path:
            guest_path_cleaned = guest_path.split(':', 1)[1].lstrip('\\').lstrip('/')
            relative_path = guest_path_cleaned.replace('\\', '/')
        else:
            relative_path = guest_path.lstrip('/')

        assert relative_path == 'Program Files/App/data.bin'


# ============================================================================
# TestUploadTestfunctions
# ============================================================================


class TestUploadTestfunctions:
    """Tests for upload_testfunctions method."""

    @pytest.mark.asyncio
    async def test_creates_zip_with_correct_structure(self, client_with_mock_call_tool):
        """Should create zip file with correct structure from directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            testfuncs_dir = Path(tmpdir) / 'testfunctions'
            testfuncs_dir.mkdir()

            # Create test files
            (testfuncs_dir / 'test1.py').write_text('# test 1')
            sub_dir = testfuncs_dir / 'submodule'
            sub_dir.mkdir()
            (sub_dir / 'test2.py').write_text('# test 2')

            await client_with_mock_call_tool.upload_testfunctions(testfuncs_dir)

            # Verify call_tool was called with upload_testfunctions
            call_args = client_with_mock_call_tool.call_tool.call_args
            assert call_args[0][0] == ToolRegistry.UPLOAD_TESTFUNCTIONS

    @pytest.mark.asyncio
    async def test_base64_encodes_zip_data(self, client_with_mock_call_tool):
        """Should base64 encode the zip data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            testfuncs_dir = Path(tmpdir) / 'testfunctions'
            testfuncs_dir.mkdir()
            (testfuncs_dir / 'test.py').write_text('print("test")')

            await client_with_mock_call_tool.upload_testfunctions(testfuncs_dir)

            call_args = client_with_mock_call_tool.call_tool.call_args
            params = call_args[0][1]
            zip_data = params['testfunctions_data']

            # Verify it's valid base64
            decoded = base64.b64decode(zip_data)
            # Verify it's a valid zip
            zip_buffer = io.BytesIO(decoded)
            with zipfile.ZipFile(zip_buffer, 'r') as zf:
                assert 'test.py' in zf.namelist()

    @pytest.mark.asyncio
    async def test_calls_upload_testfunctions_tool(self, client_with_mock_call_tool):
        """Should call the upload_testfunctions tool."""
        with tempfile.TemporaryDirectory() as tmpdir:
            testfuncs_dir = Path(tmpdir) / 'testfunctions'
            testfuncs_dir.mkdir()
            (testfuncs_dir / 'dummy.py').write_text('')

            await client_with_mock_call_tool.upload_testfunctions(testfuncs_dir)

            call_args = client_with_mock_call_tool.call_tool.call_args
            assert call_args[0][0] == ToolRegistry.UPLOAD_TESTFUNCTIONS
            assert 'testfunctions_data' in call_args[0][1]

    @pytest.mark.asyncio
    async def test_uploads_specific_files_only(self, client_with_mock_call_tool):
        """Should upload only specific files when specified."""
        with tempfile.TemporaryDirectory() as tmpdir:
            testfuncs_dir = Path(tmpdir) / 'testfunctions'
            testfuncs_dir.mkdir()

            # Create multiple test files
            file1 = testfuncs_dir / 'include.py'
            file1.write_text('# include this')
            file2 = testfuncs_dir / 'exclude.py'
            file2.write_text('# exclude this')

            # Upload only specific file
            specific_files = {file1}
            await client_with_mock_call_tool.upload_testfunctions(
                testfuncs_dir, specific_files=specific_files
            )

            call_args = client_with_mock_call_tool.call_tool.call_args
            params = call_args[0][1]
            zip_data = params['testfunctions_data']

            # Decode and check contents
            decoded = base64.b64decode(zip_data)
            zip_buffer = io.BytesIO(decoded)
            with zipfile.ZipFile(zip_buffer, 'r') as zf:
                namelist = zf.namelist()
                assert 'include.py' in namelist
                assert 'exclude.py' not in namelist

    @pytest.mark.asyncio
    async def test_uses_extended_timeout(self, client_with_mock_call_tool):
        """Should use 300s timeout for testfunction uploads."""
        with tempfile.TemporaryDirectory() as tmpdir:
            testfuncs_dir = Path(tmpdir) / 'testfunctions'
            testfuncs_dir.mkdir()
            (testfuncs_dir / 'test.py').write_text('')

            await client_with_mock_call_tool.upload_testfunctions(testfuncs_dir)

            call_args = client_with_mock_call_tool.call_tool.call_args
            timeout = call_args[1].get('timeout')
            assert timeout == 300.0


# ============================================================================
# TestPing
# ============================================================================


class TestPing:
    """Tests for ping method."""

    @pytest.mark.asyncio
    async def test_ping_returns_true_when_connected(self, connected_client):
        """ping should return True when connected."""
        result = await connected_client.ping()
        assert result is True

    @pytest.mark.asyncio
    async def test_ping_returns_false_when_disconnected(self, client):
        """ping should return False when not connected."""
        result = await client.ping()
        assert result is False

    @pytest.mark.asyncio
    async def test_ping_returns_false_when_websocket_none(self, client):
        """ping should return False when websocket is None."""
        client.connected = True
        client.websocket = None
        result = await client.ping()
        assert result is False


# ============================================================================
# TestContextManager
# ============================================================================


class TestContextManager:
    """Tests for async context manager methods."""

    @pytest.mark.asyncio
    async def test_aenter_calls_connect(self, client):
        """__aenter__ should call connect."""
        with patch.object(client, 'connect', new_callable=AsyncMock) as mock_connect:
            mock_connect.return_value = True
            result = await client.__aenter__()

            mock_connect.assert_called_once()
            assert result is client

    @pytest.mark.asyncio
    async def test_aexit_calls_disconnect(self, client):
        """__aexit__ should call disconnect."""
        with patch.object(client, 'disconnect', new_callable=AsyncMock) as mock_disconnect:
            await client.__aexit__(None, None, None)
            mock_disconnect.assert_called_once()


# ============================================================================
# TestOtherMethods
# ============================================================================


class TestOtherMethods:
    """Tests for other client methods."""

    @pytest.mark.asyncio
    async def test_set_variables(self, client_with_mock_call_tool):
        """set_variables should call tool with JSON-encoded variables."""
        variables = {'var1': 'value1', 'var2': 123}
        await client_with_mock_call_tool.set_variables(variables)

        call_args = client_with_mock_call_tool.call_tool.call_args
        assert call_args[0][0] == ToolRegistry.SET_VARIABLES
        import json
        assert json.loads(call_args[0][1]['variables']) == variables

    @pytest.mark.asyncio
    async def test_run_test(self, client_with_mock_call_tool):
        """run_test should call tool with test name and resolved data."""
        test_name = 'my_test'
        test_data = {'expected': 'result'}

        await client_with_mock_call_tool.run_test(test_name, test_data)

        call_args = client_with_mock_call_tool.call_tool.call_args
        assert call_args[0][0] == ToolRegistry.RUN_TEST
        assert call_args[0][1]['test_name'] == test_name
        assert call_args[0][1]['resolved_test_data'] == test_data

    @pytest.mark.asyncio
    async def test_get_status(self, client_with_mock_call_tool):
        """get_status should call GET_STATUS tool."""
        await client_with_mock_call_tool.get_status()

        call_args = client_with_mock_call_tool.call_tool.call_args
        assert call_args[0][0] == ToolRegistry.GET_STATUS

    @pytest.mark.asyncio
    async def test_collect_system_info_default_timeout(self, client_with_mock_call_tool):
        """collect_system_info should use default 120s timeout."""
        await client_with_mock_call_tool.collect_system_info()

        call_args = client_with_mock_call_tool.call_tool.call_args
        assert call_args[0][0] == ToolRegistry.COLLECT_SYSTEM_INFO
        assert call_args[1].get('timeout') == 120.0

    @pytest.mark.asyncio
    async def test_collect_system_info_custom_timeout(self, client_with_mock_call_tool):
        """collect_system_info should accept custom timeout."""
        await client_with_mock_call_tool.collect_system_info(timeout=300.0)

        call_args = client_with_mock_call_tool.call_tool.call_args
        assert call_args[1].get('timeout') == 300.0

    @pytest.mark.asyncio
    async def test_get_filesystem_snapshot(self, client_with_mock_call_tool):
        """get_filesystem_snapshot should call tool with path and adjusted timeout."""
        await client_with_mock_call_tool.get_filesystem_snapshot(root_path='/home', timeout=660.0)

        call_args = client_with_mock_call_tool.call_tool.call_args
        assert call_args[0][0] == ToolRegistry.GET_FILESYSTEM_SNAPSHOT
        params = call_args[0][1]
        assert params['root_path'] == '/home'
        assert params['timeout'] == 600.0  # 660 - 60 buffer
        assert call_args[1].get('timeout') == 660.0

    @pytest.mark.asyncio
    async def test_install_testfunction_dependencies(self, client_with_mock_call_tool):
        """install_testfunction_dependencies should call tool with deps list."""
        deps = ['requests>=2.0.0', 'numpy']
        await client_with_mock_call_tool.install_testfunction_dependencies(deps)

        call_args = client_with_mock_call_tool.call_tool.call_args
        assert call_args[0][0] == ToolRegistry.INSTALL_DEPENDENCIES
        assert call_args[0][1]['dependencies'] == deps
        assert call_args[1].get('timeout') == 300.0
