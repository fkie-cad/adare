"""
Unit tests for the Adare Web API.
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

# Import the app (this will also import specific DTOs properly if we need them)
from adare.webapi.main import app
from adarelib.results import Result


@pytest.fixture
def mock_api():
    """Mock the global AdareAPI instance used in main.py."""
    with patch("adare.webapi.main.api") as mock:
        yield mock


@pytest.fixture
def client(mock_api):
    """Test client for the FastAPI app."""
    return TestClient(app)


class TestSessionEndpoints:
    """Tests for session management endpoints."""

    def test_start_session(self, client, mock_api):
        """Test POST /api/sessions/start."""
        # Setup mock
        mock_result = MagicMock()
        mock_result.is_success.return_value = True
        mock_result.value.session_id = "test-session-id"
        mock_result.value.vm_running = True
        mock_api.devmode.start_session.return_value = mock_result

        # Execute request
        payload = {
            "project_path": "/tmp/test",
            "experiment_name": "test-exp",
            "environment_name": "test-env",
            "gui_mode": "headless",
            "vm_memory": 4096,
            "vm_cpus": 2,
            "debug_screenshots": True
        }
        response = client.post("/api/sessions/start", json=payload)

        # Verify
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["data"]["session_id"] == "test-session-id"

        # Check call arguments
        mock_api.devmode.start_session.assert_called_once()
        args = mock_api.devmode.start_session.call_args[0][0]
        assert str(args.project_path) == "/tmp/test"
        assert args.experiment_name == "test-exp"

    def test_stop_session(self, client, mock_api):
        """Test POST /api/sessions/{id}/stop."""
        # Setup mock
        mock_result = MagicMock()
        mock_result.is_success.return_value = True
        mock_api.devmode.stop_session.return_value = mock_result

        # Execute request
        response = client.post(
            "/api/sessions/test-session-id/stop",
            json={"remove_resources": True}
        )

        # Verify
        assert response.status_code == 200
        assert response.json()["success"] is True

        # Check call arguments
        mock_api.devmode.stop_session.assert_called_once()
        args = mock_api.devmode.stop_session.call_args[0][0]
        assert args.session_id == "test-session-id"
        assert args.remove_resources is True

    def test_list_sessions(self, client, mock_api):
        """Test GET /api/sessions."""
        # Setup mock
        mock_result = MagicMock()
        mock_result.is_success.return_value = True
        mock_result.value = [{"id": "s1"}, {"id": "s2"}]
        mock_api.devmode.list_sessions.return_value = mock_result

        # Execute request
        response = client.get("/api/sessions?project_path=/tmp/test")

        # Verify
        assert response.status_code == 200
        assert response.json()["data"] == [{"id": "s1"}, {"id": "s2"}]

        # Check call arguments
        mock_api.devmode.list_sessions.assert_called_once()
        args = mock_api.devmode.list_sessions.call_args[0][0]
        assert str(args.project_path) == "/tmp/test"

    def test_get_session_state(self, client, mock_api):
        """Test GET /api/sessions/{id}/state."""
        # Setup mock
        mock_result = MagicMock()
        mock_result.is_success.return_value = True
        mock_result.value = {"status": "running"}
        mock_api.devmode.get_state.return_value = mock_result

        # Execute request
        response = client.get("/api/sessions/test-id/state")

        # Verify
        assert response.status_code == 200
        assert response.json()["data"] == {"status": "running"}

    def test_cleanup_sessions(self, client, mock_api):
        """Test POST /api/sessions/cleanup."""
        # Setup mock
        mock_result = MagicMock()
        mock_result.is_success.return_value = True
        mock_result.value = {"cleaned": 2}
        mock_api.devmode.cleanup_stale_sessions.return_value = mock_result

        # Execute request
        response = client.post("/api/sessions/cleanup?project_path=/tmp/test")

        # Verify
        assert response.status_code == 200
        assert response.json()["data"]["cleaned"] == 2


class TestActionEndpoints:
    """Tests for action execution endpoints."""

    def test_execute_action(self, client, mock_api):
        """Test POST /api/sessions/{id}/actions/execute."""
        # Setup mock
        mock_result = MagicMock()
        mock_result.is_success.return_value = True
        mock_result.value.success = True
        mock_result.value.message = "OK"
        mock_result.value.execution_time = 1.0
        mock_result.value.coordinates = None
        mock_api.devmode.execute_action.return_value = mock_result

        # Execute request
        payload = {
            "action_yaml": "type: click\ntarget: button.png"
        }
        response = client.post(
            "/api/sessions/test-id/actions/execute",
            json=payload
        )

        # Verify
        assert response.status_code == 200
        assert response.json()["success"] is True

        # Check call arguments
        mock_api.devmode.execute_action.assert_called_once()
        args = mock_api.devmode.execute_action.call_args[0][0]
        assert args.session_id == "test-id"
        assert args.action_content == payload["action_yaml"]

    def test_execute_playbook(self, client, mock_api):
        """Test POST /api/sessions/{id}/playbooks/execute."""
        # Setup mock
        mock_result = MagicMock()
        mock_result.is_success.return_value = True
        mock_api.devmode.execute_playbook.return_value = mock_result

        # Execute request
        payload = {
            "actions": [{"type": "click", "target": "ok"}],
            "settings": {"max_retries": 3}
        }
        response = client.post(
            "/api/sessions/test-id/playbooks/execute",
            json=payload
        )

        # Verify
        assert response.status_code == 200
        assert response.json()["success"] is True

        # Check call arguments
        mock_api.devmode.execute_playbook.assert_called_once()
        args = mock_api.devmode.execute_playbook.call_args[0][0]
        assert args.session_id == "test-id"
        # The playbook is passed as a file path, we can verify it exists
        assert "tmp" in str(args.playbook_content)


class TestResetEndpoints:
    """Tests for session reset endpoints."""

    def test_reset_session_soft(self, client, mock_api):
        """Test POST /api/sessions/{id}/reset?type=soft."""
        mock_result = MagicMock()
        mock_result.is_success.return_value = True
        mock_api.devmode.reset_soft.return_value = mock_result

        response = client.post("/api/sessions/test-id/reset?reset_type=soft")

        assert response.status_code == 200
        mock_api.devmode.reset_soft.assert_called_once()

    def test_reset_session_hard(self, client, mock_api):
        """Test POST /api/sessions/{id}/reset?type=hard."""
        mock_result = MagicMock()
        mock_result.is_success.return_value = True
        mock_api.devmode.reset_hard.return_value = mock_result

        response = client.post("/api/sessions/test-id/reset?reset_type=hard")

        assert response.status_code == 200
        mock_api.devmode.reset_hard.assert_called_once()


class TestCheckpointEndpoints:
    """Tests for checkpoint management endpoints."""

    def test_create_checkpoint(self, client, mock_api):
        """Test POST /api/sessions/{id}/checkpoints."""
        mock_result = MagicMock()
        mock_result.is_success.return_value = True
        mock_api.devmode.create_checkpoint.return_value = mock_result

        payload = {"name": "ckpt1", "description": "Initial state"}
        response = client.post("/api/sessions/test-id/checkpoints", json=payload)

        assert response.status_code == 200
        mock_api.devmode.create_checkpoint.assert_called_once()

    def test_list_checkpoints(self, client, mock_api):
        """Test GET /api/sessions/{id}/checkpoints."""
        mock_result = MagicMock()
        mock_result.is_success.return_value = True
        mock_result.value = ["ckpt1", "ckpt2"]
        mock_api.devmode.list_checkpoints.return_value = mock_result

        response = client.get("/api/sessions/test-id/checkpoints")

        assert response.status_code == 200
        assert response.json()["data"] == ["ckpt1", "ckpt2"]

    def test_restore_checkpoint(self, client, mock_api):
        """Test POST /api/sessions/{id}/checkpoints/{name}/restore."""
        mock_result = MagicMock()
        mock_result.is_success.return_value = True
        mock_api.devmode.restore_checkpoint.return_value = mock_result

        response = client.post("/api/sessions/test-id/checkpoints/ckpt1/restore")

        assert response.status_code == 200
        mock_api.devmode.restore_checkpoint.assert_called_once()

    def test_delete_checkpoint(self, client, mock_api):
        """Test DELETE /api/sessions/{id}/checkpoints/{name}."""
        mock_result = MagicMock()
        mock_result.is_success.return_value = True
        mock_api.devmode.delete_checkpoint.return_value = mock_result

        response = client.delete("/api/sessions/test-id/checkpoints/ckpt1")

        assert response.status_code == 200
        mock_api.devmode.delete_checkpoint.assert_called_once()


class TestPlaybookEndpoints:
    """Tests for playbook file management."""

    def test_save_playbook(self, client, tmp_path):
        """Test POST /api/playbooks/save."""
        # We need to patch the path where playbooks are saved because
        # the app uses relative "playbooks" dir in current working directory
        with patch("pathlib.Path.mkdir"), \
             patch("builtins.open", new_callable=MagicMock) as mock_open:

            payload = {
                "filename": "test_playbook.yml",
                "actions": [{"type": "click"}],
                "settings": {}
            }
            response = client.post("/api/playbooks/save", json=payload)

            assert response.status_code == 200
            assert response.json()["success"] is True

    def test_load_playbook(self, client):
        """Test GET /api/playbooks/{filename}."""
        # Mock file existence and content
        with patch("pathlib.Path.exists", return_value=True), \
             patch("builtins.open", new_callable=MagicMock) as mock_open, \
             patch("yaml.safe_load") as mock_yaml_load:

            mock_yaml_load.return_value = {
                "actions": [{"type": "click"}],
                "settings": {"foo": "bar"}
            }

            response = client.get("/api/playbooks/test_playbook.yml")

            assert response.status_code == 200
            data = response.json()["data"]
            assert len(data["actions"]) == 1
            assert data["settings"]["foo"] == "bar"

    def test_load_playbook_not_found(self, client):
        """Test GET /api/playbooks/{filename} when file missing."""
        with patch("pathlib.Path.exists", return_value=False):
            response = client.get("/api/playbooks/missing.yml")
            assert response.status_code == 404


class TestGeneralEndpoints:
    """Tests for general metadata endpoints."""

    def test_get_action_types(self, client):
        """Test GET /api/actions/types."""
        response = client.get("/api/actions/types")
        assert response.status_code == 200
        data = response.json()["data"]
        assert "Click" in data
        assert "Wait" in data

    def test_health_check(self, client):
        """Test GET /api/health."""
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
