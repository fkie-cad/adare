
import pytest
from unittest.mock import MagicMock, patch, ANY, AsyncMock
from pathlib import Path
import logging

from adare.backend.devmode.session import DevModeSession
from adare.backend.experiment.runctx import ExperimentRunCtx
from adare.types.playbook import ClickAction

@pytest.fixture
def mock_session():
    """Create a mock DevModeSession with minimal dependencies."""
    session = DevModeSession("test-session", Path("/tmp"), "test-env")
    
    # Mock experiment context
    session.experiment_ctx = MagicMock(spec=ExperimentRunCtx)
    session.experiment_ctx.experiment_run_directory = MagicMock()
    session.experiment_ctx.experiment_run_directory.log_directory = Path("/tmp/logs")
    
    # Mock playbook controller
    session.playbook_controller = MagicMock()
    session.playbook_controller.action_executor = MagicMock()
    session.playbook_controller.variable_resolver = MagicMock()
    
    session.is_running = True
    
    return session

@pytest.mark.asyncio
async def test_command_logger_context_manager(mock_session):
    """Test that command logger creates a file handler and removes it."""
    
    with patch('logging.FileHandler') as mock_file_handler_cls:
        mock_handler = MagicMock()
        mock_file_handler_cls.return_value = mock_handler
        
        with patch('logging.getLogger') as mock_get_logger:
            mock_root_logger = MagicMock()
            mock_get_logger.return_value = mock_root_logger
            
            # Test usage
            with mock_session._command_logger("TestAction"):
                # Inside context: should have added handler
                mock_file_handler_cls.assert_called_once()
                mock_root_logger.addHandler.assert_called_once_with(mock_handler)
                
            # After context: should have removed handler
            mock_root_logger.removeHandler.assert_called_once_with(mock_handler)
            mock_handler.close.assert_called_once()
            
            # Verify filename format (timestamp_TestAction.log)
            # Args are (filename, mode, encoding)
            args, _ = mock_file_handler_cls.call_args
            assert str(args[0]).endswith("_TestAction.log")
            assert "logs" in str(args[0])

@pytest.mark.asyncio
async def test_execute_action_logs_command(mock_session):
    """Test that execute_action wraps execution in command logger."""
    
    action = ClickAction(target="test")
    mock_session.playbook_controller.action_executor.execute_action.return_value = MagicMock(success=True)
    
    with patch.object(mock_session, '_command_logger') as mock_logger:
        mock_ctx = MagicMock()
        mock_logger.return_value.__enter__.return_value = mock_ctx
        
        await mock_session.execute_action(action)
        
        # Verify logger was called with action class name
        mock_logger.assert_called_once_with("ClickAction")

@pytest.mark.asyncio
async def test_execute_playbook_logs_command(mock_session):
    """Test that execute_playbook wraps execution in command logger."""
    
    playbook = MagicMock()
    playbook.variables = {}
    
    # Use AsyncMock for async method
    mock_session.playbook_controller.execute_playbook = AsyncMock()
    mock_session.playbook_controller.execute_playbook.return_value = MagicMock(total_actions=1, successful_actions=1)
    
    with patch.object(mock_session, '_command_logger') as mock_logger:
        mock_ctx = MagicMock()
        mock_logger.return_value.__enter__.return_value = mock_ctx
        
        await mock_session.execute_playbook(playbook)
        
        # Verify logger was called with playbook_execution
        mock_logger.assert_called_once_with("playbook_execution")

if __name__ == "__main__":
    import asyncio
    async def run_tests():
        session = mock_session()
        print("Running test_command_logger_context_manager...")
        await test_command_logger_context_manager(session)
        print("PASS")
        
        print("Running test_execute_action_logs_command...")
        await test_execute_action_logs_command(session)
        print("PASS")
        
        print("Running test_execute_playbook_logs_command...")
        await test_execute_playbook_logs_command(session)
        print("PASS")
        
    asyncio.run(run_tests())
