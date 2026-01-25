
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path
from adare.backend.devmode.manager import DevModeSessionManager
from adare.backend.devmode.session import DevModeSession

@pytest.fixture
def manager():
    # managers are singletons, so we need to reset the instance for each test
    DevModeSessionManager._instance = None
    mgr = DevModeSessionManager()
    yield mgr
    DevModeSessionManager._instance = None

@pytest.fixture
def mock_session():
    session = MagicMock(spec=DevModeSession)
    session.start = AsyncMock(return_value=True)
    session.shutdown = AsyncMock()
    session.stop_and_remove = AsyncMock()
    # Setup state for list_sessions
    state = MagicMock()
    session.get_state.return_value = state
    return session

class TestDevModeSessionManager:
    
    def test_singleton(self):
        m1 = DevModeSessionManager()
        m2 = DevModeSessionManager()
        assert m1 is m2
        assert m1._initialized is True

    @patch('adare.backend.devmode.manager.DevModeSession')
    @patch('adare.backend.devmode.manager.ulid.ULID')
    @pytest.mark.asyncio
    async def test_create_session_success(self, mock_ulid, mock_dev_session_cls, manager, mock_session):
        # Arrange
        mock_ulid.return_value = '01ARZ3NDEKTSV4RRFFQ69G5FAV'
        mock_dev_session_cls.return_value = mock_session
        
        project_path = Path("/tmp/test")
        env_name = "test-env"
        
        # Act
        session_id = await manager.create_session(project_path, env_name)
        
        # Assert
        assert session_id == '01ARZ3NDEKTSV4RRFFQ69G5FAV'
        mock_dev_session_cls.assert_called_once_with(
            session_id='01ARZ3NDEKTSV4RRFFQ69G5FAV',
            project_path=project_path,
            environment_name=env_name,
            gui_mode=None,
            vm_memory=None,
            vm_cpus=None,
            debug_screenshots=False,
            console_ulid=None
        )
        mock_session.start.assert_called_once()
        assert manager.get_session(session_id) == mock_session
        assert manager.get_session_count() == 1

    @patch('adare.backend.devmode.manager.DevModeSession')
    @pytest.mark.asyncio
    async def test_create_session_failure(self, mock_dev_session_cls, manager, mock_session):
        # Arrange
        mock_session.start.return_value = False
        mock_dev_session_cls.return_value = mock_session
        
        # Act/Assert
        with pytest.raises(RuntimeError, match="Failed to start dev mode session"):
            await manager.create_session(Path("/tmp"), "env")
            
        assert manager.get_session_count() == 0

    @pytest.mark.asyncio
    async def test_shutdown_session(self, manager, mock_session):
        # Arrange
        manager._sessions['test-id'] = mock_session
        
        # Act
        result = await manager.shutdown_session('test-id')
        
        # Assert
        assert result is True
        mock_session.shutdown.assert_called_once()
        assert manager.get_session('test-id') is None
        assert manager.get_session_count() == 0

    @pytest.mark.asyncio
    async def test_shutdown_session_not_found(self, manager):
        result = await manager.shutdown_session('non-existent')
        assert result is False

    @pytest.mark.asyncio
    async def test_stop_and_remove_session(self, manager, mock_session):
        # Arrange
        manager._sessions['test-id'] = mock_session
        
        # Act
        result = await manager.stop_and_remove_session('test-id')
        
        # Assert
        assert result is True
        mock_session.stop_and_remove.assert_called_once()
        assert manager.get_session('test-id') is None

    def test_list_sessions(self, manager, mock_session):
        manager._sessions['id1'] = mock_session
        manager._sessions['id2'] = mock_session
        
        sessions = manager.list_sessions()
        
        assert len(sessions) == 2
        assert mock_session.get_state.call_count == 2

    @pytest.mark.asyncio
    async def test_stop_all(self, manager, mock_session):
        manager._sessions['id1'] = mock_session
        manager._sessions['id2'] = mock_session
        
        await manager.stop_all()
        
        assert mock_session.shutdown.call_count == 2
        assert manager.get_session_count() == 0

    @patch('adare.database.api.devmode.DevModeApi')
    @patch('adare.backend.devmode.manager.is_vm_running')
    @patch('adare.backend.devmode.manager.restore_context')
    @patch('adare.backend.environment.database.resolve_environment_identifier')
    @patch('adare.backend.environment.database.get_environment_hypervisor')
    @pytest.mark.asyncio
    async def test_restore_session_success(
        self, mock_get_hypervisor, mock_resolve_env, mock_restore_ctx, 
        mock_is_vm_running, mock_db_api_cls, manager
    ):
        # Arrange
        session_id = 'restored-session'
        db_api = MagicMock()
        mock_db_api_cls.return_value = db_api
        
        db_session = MagicMock()
        db_session.status = 'running'
        db_session.project_path = '/tmp/proj'
        db_session.environment_name = 'env'
        db_session.vm_name = 'vm-1'
        db_api.get_session.return_value = db_session
        
        mock_is_vm_running.return_value = True
        mock_restore_ctx.return_value = True
        
        # Act
        # We need to mock import of AdareVMClient inside the method if we wanted to test full flow
        # But mocking sys.modules or patch.dict is tricky here. 
        # For now, let's assume restoring without connection works cleanly or mocks out properly.
        # The method tries to import inside.
        
        with patch.dict('sys.modules', {'adare.backend.experiment.websocket_client': MagicMock()}):
             session = await manager.restore_session(session_id)
        
        # Assert
        assert session is not None
        assert session.session_id == session_id
        assert manager.get_session(session_id) == session
        mock_restore_ctx.assert_called_once()

    @patch('adare.database.api.devmode.DevModeApi')
    @pytest.mark.asyncio
    async def test_restore_session_not_found(self, mock_db_api_cls, manager):
        mock_db_api_cls.return_value.get_session.return_value = None
        
        session = await manager.restore_session('missing')
        assert session is None

    @patch('adare.database.api.devmode.DevModeApi')
    @pytest.mark.asyncio
    async def test_restore_session_wrong_status(self, mock_db_api_cls, manager):
        session_obj = MagicMock()
        session_obj.status = 'failed'
        mock_db_api_cls.return_value.get_session.return_value = session_obj
        
        session = await manager.restore_session('failed-id')
        assert session is None

