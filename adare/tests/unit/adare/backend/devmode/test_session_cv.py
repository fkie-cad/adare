
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adare.backend.devmode.session import DevModeSession
from adare.backend.experiment.mcp_server_manager import MCPServerManager
from adare.backend.experiment.runctx import ExperimentRunCtx


@pytest.fixture
def mock_session():
    session = DevModeSession(
        session_id="test_session",
        project_path=Path("/tmp/project"),
        environment_name="test_env"
    )
    session.experiment_ctx = MagicMock(spec=ExperimentRunCtx)
    return session

@pytest.mark.asyncio
async def test_restart_mcp_server_success(mock_session):
    # Setup mocks
    mock_old_server = AsyncMock(spec=MCPServerManager)
    mock_old_server.debug = False
    mock_old_server.debug_output_dir = None
    mock_old_server.log_file = Path("/tmp/old_log.log")

    mock_session.experiment_ctx.mcp_server = mock_old_server

    # Mock MCPServerManager constructor and start method
    with patch('adare.backend.devmode.session.MCPServerManager') as MockManager:
        mock_new_manager = AsyncMock(spec=MCPServerManager)
        mock_new_manager.start.return_value = True
        MockManager.return_value = mock_new_manager

        # Execute
        result = await mock_session.restart_mcp_server(debug=True, debug_output_dir=Path("/tmp/debug"))

        # Verify - now returns Result[None]
        assert result.success is True

        # 1. Stop called on old server
        mock_old_server.stop.assert_called_once_with(force_external=True)

        # 2. New manager created with correct args
        MockManager.assert_called_once_with(
            log_file=Path("/tmp/old_log.log"), # Should reuse log file
            debug=True,
            debug_output_dir=Path("/tmp/debug")
        )

        # 3. Start called on new manager
        mock_new_manager.start.assert_called_once_with(allow_existing=False)

        # 4. Context updated
        assert mock_session.experiment_ctx.mcp_server == mock_new_manager

@pytest.mark.asyncio
async def test_restart_mcp_server_defaults(mock_session):
    # Setup mocks
    mock_old_server = AsyncMock(spec=MCPServerManager)
    mock_old_server.debug = True
    mock_old_server.debug_output_dir = Path("/tmp/existing_debug")
    mock_old_server.log_file = Path("/tmp/old_log.log")

    mock_session.experiment_ctx.mcp_server = mock_old_server

    with patch('adare.backend.devmode.session.MCPServerManager') as MockManager:
        mock_new_manager = AsyncMock(spec=MCPServerManager)
        mock_new_manager.start.return_value = True
        MockManager.return_value = mock_new_manager

        # Execute with defaults (None)
        result = await mock_session.restart_mcp_server()

        assert result.success is True

        # Verify reuse of existing config
        MockManager.assert_called_once_with(
            log_file=Path("/tmp/old_log.log"),
            debug=True, # Inherited
            debug_output_dir=Path("/tmp/existing_debug") # Inherited
        )

@pytest.mark.asyncio
async def test_restart_mcp_server_failure(mock_session):
    mock_session.experiment_ctx.mcp_server = AsyncMock()

    with patch('adare.backend.devmode.session.MCPServerManager') as MockManager:
        mock_new_manager = AsyncMock()
        mock_new_manager.start.return_value = False # fail
        MockManager.return_value = mock_new_manager

        result = await mock_session.restart_mcp_server(debug=True)

        assert result.success is False

@pytest.mark.asyncio
async def test_stop_mcp_server_success(mock_session):
    mock_server = AsyncMock(spec=MCPServerManager)
    mock_server.stop.return_value = True
    mock_session.experiment_ctx.mcp_server = mock_server

    result = await mock_session.stop_mcp_server()

    assert result.success is True
    mock_server.stop.assert_called_once_with(force_external=True)

@pytest.mark.asyncio
async def test_stop_mcp_server_not_running(mock_session):
    mock_session.experiment_ctx.mcp_server = None

    result = await mock_session.stop_mcp_server()

    assert result.success is True  # Considered success (idempotent)
