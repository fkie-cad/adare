"""Tests for DevModeService — development mode session operations."""

import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


# Pre-mock heavy database/backend modules so the devmode_service module can import cleanly.
_mocked_modules = {}
for _mod_name in [
    "adare.database.api.devmode",
    "adare.database.models.devcheckpoint",
    "adare.database.models.devsession",
    "adare.database.models.global_models",
    "adare.backend.devmode.manager",
    "adare.backend.devmode.session",
]:
    if _mod_name not in sys.modules:
        _mocked_modules[_mod_name] = MagicMock()
        sys.modules[_mod_name] = _mocked_modules[_mod_name]

from adare.services.devmode import DevModeService  # noqa: E402


@pytest.fixture
def service():
    svc = DevModeService.__new__(DevModeService)
    svc._manager = MagicMock()
    svc._db_api = MagicMock()
    return svc


@pytest.fixture
def start_request():
    from adare.core.dto.devmode import DevSessionStartRequest
    return DevSessionStartRequest(
        project_path=Path("/tmp/proj"),
        environment_name="test-env",
    )


@pytest.fixture
def stop_request():
    from adare.core.dto.devmode import DevSessionStopRequest
    return DevSessionStopRequest(session_id="sess-01")


@pytest.fixture
def list_request():
    from adare.core.dto.devmode import DevSessionListRequest
    return DevSessionListRequest(project_path=Path("/tmp/proj"))


@pytest.fixture
def action_request():
    from adare.core.dto.devmode import DevActionExecuteRequest
    return DevActionExecuteRequest(
        session_id="sess-01",
        action_source="yaml",
        action_content="click: {target: 'button'}",
    )


class TestDevModeServiceStartSession:
    """Tests for DevModeService.start_session()."""

    @patch("adare.services.devmode.session_management.environment_database")
    def test_start_session_env_not_found(self, mock_env_db, service, start_request):
        from adare.backend.environment.exceptions import EnvironmentDoesNotExistInDatabase
        mock_env_db.resolve_environment_identifier.side_effect = EnvironmentDoesNotExistInDatabase(
            MagicMock(), message="not found"
        )

        result = service.start_session(start_request)

        assert result.success is False
        assert result.error.code == "ENVIRONMENT_NOT_FOUND"

    @patch("adare.services.devmode.session_management.environment_database")
    def test_start_session_runtime_error(self, mock_env_db, service, start_request):
        mock_env_db.resolve_environment_identifier.return_value = "env-ulid"
        mock_env_db.get_environment_hypervisor.return_value = "qemu"

        with patch("asyncio.run", side_effect=RuntimeError("VM failed")):
            result = service.start_session(start_request)

        assert result.success is False
        assert result.error.code == "SESSION_START_FAILED"

    @patch("adare.services.devmode.session_management.environment_database")
    def test_start_session_virtualbox_not_implemented(self, mock_env_db, service, start_request):
        mock_env_db.resolve_environment_identifier.return_value = "env-ulid"
        mock_env_db.get_environment_hypervisor.return_value = "virtualbox"

        result = service.start_session(start_request)

        # NotImplementedError is caught by the generic Exception handler
        assert result.success is False


class TestDevModeServiceStopSession:
    """Tests for DevModeService.stop_session()."""

    def test_stop_session_not_found(self, service, stop_request):
        service._db_api.session_exists.return_value = False

        result = service.stop_session(stop_request)

        assert result.success is False
        assert result.error.code == "SESSION_NOT_FOUND"

    def test_stop_session_success_stopped(self, service, stop_request):
        service._db_api.session_exists.return_value = True

        with patch("asyncio.run", return_value="stopped"):
            result = service.stop_session(stop_request)

        assert result.success is True
        assert result.data is True
        service._db_api.update_session_status.assert_called_once_with("sess-01", "stopped")

    def test_stop_session_success_removed(self, service, stop_request):
        stop_request.remove_resources = True
        service._db_api.session_exists.return_value = True

        with patch("asyncio.run", return_value="removed"):
            result = service.stop_session(stop_request)

        assert result.success is True
        service._db_api.delete_session.assert_called_once_with("sess-01")

    def test_stop_session_unexpected_error(self, service, stop_request):
        service._db_api.session_exists.return_value = True

        with patch("asyncio.run", side_effect=OSError("disk error")):
            result = service.stop_session(stop_request)

        assert result.success is False
        assert result.error.code == "INTERNAL_ERROR"


class TestDevModeServiceListSessions:
    """Tests for DevModeService.list_sessions()."""

    def test_list_sessions_with_results(self, service, list_request):
        db_sess = MagicMock()
        db_sess.session_id = "sess-01"
        db_sess.experiment_name = "exp1"
        db_sess.environment_name = "env1"
        db_sess.created_at = datetime(2025, 1, 1)
        db_sess.project_path = "/tmp/proj"
        db_sess.status = "running"

        service._db_api.list_sessions.return_value = [db_sess]

        live_state = MagicMock()
        live_state.vm_running = True
        live_state.actions_executed = 5
        live_session = MagicMock()
        live_session.get_state.return_value = live_state
        service._manager.get_session.return_value = live_session

        result = service.list_sessions(list_request)

        assert result.success is True
        assert len(result.data) == 1
        assert result.data[0].session_id == "sess-01"
        assert result.data[0].vm_running is True
        assert result.data[0].actions_executed == 5

    def test_list_sessions_empty(self, service, list_request):
        service._db_api.list_sessions.return_value = []

        result = service.list_sessions(list_request)

        assert result.success is True
        assert result.data == []

    def test_list_sessions_no_live_session(self, service, list_request):
        db_sess = MagicMock()
        db_sess.session_id = "sess-02"
        db_sess.experiment_name = "exp1"
        db_sess.environment_name = "env1"
        db_sess.created_at = datetime(2025, 1, 1)
        db_sess.project_path = "/tmp/proj"
        db_sess.status = "stopped"

        service._db_api.list_sessions.return_value = [db_sess]
        service._manager.get_session.return_value = None

        result = service.list_sessions(list_request)

        assert result.success is True
        assert result.data[0].vm_running is False
        assert result.data[0].actions_executed == 0


class TestDevModeServiceExecuteAction:
    """Tests for DevModeService.execute_action()."""

    def test_execute_action_success(self, service, action_request):
        action_result_mock = MagicMock()
        action_result_mock.success = True
        action_result_mock.message = "clicked"
        action_result_mock.coordinates = (100, 200)
        action_result_mock.data = None

        with patch("asyncio.run", return_value=(action_result_mock, 0.5)):
            result = service.execute_action(action_request)

        assert result.success is True
        assert result.data.success is True
        assert result.data.execution_time == 0.5

    def test_execute_action_session_not_found(self, service, action_request):
        with patch("asyncio.run", side_effect=RuntimeError("session not found")):
            result = service.execute_action(action_request)

        assert result.success is False
        assert result.error.code == "SESSION_NOT_FOUND"

    def test_execute_action_invalid_source(self, service, action_request):
        with patch("asyncio.run", side_effect=ValueError("Invalid action source 'bad'")):
            result = service.execute_action(action_request)

        assert result.success is False
        assert result.error.code == "INVALID_ACTION_SOURCE"

    def test_execute_action_yaml_parse_error(self, service, action_request):
        import yaml
        with patch("asyncio.run", side_effect=yaml.YAMLError("bad yaml")):
            result = service.execute_action(action_request)

        assert result.success is False
        assert result.error.code == "YAML_PARSE_ERROR"

    def test_execute_action_file_not_found(self, service, action_request):
        action_request.action_source = "file"
        action_request.action_content = "/nonexistent.yml"

        with patch("asyncio.run", side_effect=FileNotFoundError("/nonexistent.yml")):
            result = service.execute_action(action_request)

        assert result.success is False
        assert result.error.code == "FILE_NOT_FOUND"
