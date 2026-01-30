
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from adare.types.playbook import CommandAction
from adare.backend.experiment.execution.simple_actions import SimpleActionsExecutor

@pytest.mark.asyncio
class TestSimpleActionsExecutorCommand:

    async def test_powershell_auto_wrap_execution(self):
        """Test that execute_command wraps PowerShell commands."""
        # Mock dependencies
        mock_client = AsyncMock()
        mock_client.execute_shell.return_value = {"status": "success", "returncode": 0}
        
        executor = SimpleActionsExecutor(
            websocket_client=mock_client,
            target_resolution_executor=MagicMock()
        )
        
        # Action with PowerShell syntax
        command_str = "$x = 1"
        action = CommandAction(command=command_str)
        
        # Execute
        await executor.execute_command(action)
        
        # Verify execute_shell was called with WRAPPED command
        mock_client.execute_shell.assert_called_once()
        call_kwargs = mock_client.execute_shell.call_args.kwargs
        executed_cmd = call_kwargs['shell_command']
        
        assert executed_cmd.startswith("powershell -EncodedCommand ")
        assert executed_cmd != command_str
        
        # Verify action object itself was NOT modified
        assert action.command == command_str

    async def test_normal_command_no_wrap_execution(self):
        """Test that normal commands are NOT wrapped."""
        mock_client = AsyncMock()
        mock_client.execute_shell.return_value = {"status": "success", "returncode": 0}
        
        executor = SimpleActionsExecutor(
            websocket_client=mock_client,
            target_resolution_executor=MagicMock()
        )
        
        command_str = "echo hello"
        action = CommandAction(command=command_str)
        
        await executor.execute_command(action)
        
        mock_client.execute_shell.assert_called_once()
        call_kwargs = mock_client.execute_shell.call_args.kwargs
        executed_cmd = call_kwargs['shell_command']
        
        assert executed_cmd == command_str

    async def test_r_string_stripped_then_wrapped(self):
        """Test that r-strings are stripped by Action, then wrapped by Executor."""
        mock_client = AsyncMock()
        mock_client.execute_shell.return_value = {"status": "success", "returncode": 0}
        
        executor = SimpleActionsExecutor(
            websocket_client=mock_client,
            target_resolution_executor=MagicMock()
        )
        
        # Initial input with r""
        action = CommandAction(command='r"$x = 1"')
        # Action should have stripped it immediately
        assert action.command == "$x = 1"
        
        await executor.execute_command(action)
        
        # Executor should have wrapped the stripped command
        mock_client.execute_shell.assert_called_once()
        executed_cmd = mock_client.execute_shell.call_args.kwargs['shell_command']
        assert executed_cmd.startswith("powershell -EncodedCommand ")
