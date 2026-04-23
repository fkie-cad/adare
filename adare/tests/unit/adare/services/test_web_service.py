"""Tests for WebService — web authentication and data transfer operations."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def service():
    from adare.services.web_service import WebService
    return WebService()


@pytest.fixture
def download_env_request():
    from adare.core.dto.web import DownloadEnvironmentRequest
    return DownloadEnvironmentRequest(project_path=Path("/tmp/proj"), environment_name="test-env")


@pytest.fixture
def sync_request():
    from adare.core.dto.web import SyncRequest
    return SyncRequest(project_path=Path("/tmp/proj"))


@pytest.fixture
def check_experiment_request():
    from adare.core.dto.web import CheckExperimentRequest
    return CheckExperimentRequest(ulid="01ABC123")


@pytest.fixture
def check_run_request():
    from adare.core.dto.web import CheckRunRequest
    return CheckRunRequest(ulid="01RUN456")


@pytest.fixture
def upload_run_request():
    from adare.core.dto.web import UploadRunRequest
    return UploadRunRequest(ulid="01RUN456")


class TestWebServiceLogin:
    """Tests for WebService.login()."""

    @patch("adare.services.web_service.WebService.login")
    def test_login_success(self, mock_login):
        from adare.core.result import Result
        from adare.core.dto.web import WebLoginResult
        mock_login.return_value = Result.ok(WebLoginResult(logged_in=True, message="Login successful"))

        result = mock_login()

        assert result.success is True
        assert result.data.logged_in is True

    def test_login_failure(self, service):
        with patch("adare.web.login.login", side_effect=ConnectionError("no network")):
            result = service.login()

        assert result.success is False
        assert result.error.code == "LoginError"


class TestWebServiceLogout:
    """Tests for WebService.logout()."""

    def test_logout_success(self, service):
        with patch("adare.web.login.logout"):
            result = service.logout()

        assert result.success is True
        assert result.data.logged_out is True

    def test_logout_failure(self, service):
        with patch("adare.web.login.logout", side_effect=OSError("failed")):
            result = service.logout()

        assert result.success is False
        assert result.error.code == "LogoutError"


class TestWebServiceGetStatus:
    """Tests for WebService.get_status()."""

    @patch("adare.services.web_service.WebService.get_status")
    def test_get_status_logged_in(self, mock_status):
        from adare.core.result import Result
        from adare.core.dto.web import WebStatusResult
        mock_status.return_value = Result.ok(WebStatusResult(logged_in=True, username="alice"))

        result = mock_status()

        assert result.success is True
        assert result.data.logged_in is True
        assert result.data.username == "alice"

    @patch("adare.services.web_service.WebService.get_status")
    def test_get_status_not_logged_in(self, mock_status):
        from adare.core.result import Result
        from adare.core.dto.web import WebStatusResult
        mock_status.return_value = Result.ok(WebStatusResult(logged_in=False))

        result = mock_status()

        assert result.success is True
        assert result.data.logged_in is False


class TestWebServiceDownloadEnvironment:
    """Tests for WebService.download_environment()."""

    def test_download_environment_success(self, service, download_env_request):
        with patch("adare.backend.environment.commands.environment_download"):
            result = service.download_environment(download_env_request)

        assert result.success is True
        assert result.data.downloaded is True

    def test_download_environment_failure(self, service, download_env_request):
        with patch("adare.backend.environment.commands.environment_download",
                    side_effect=ConnectionError("network error")):
            result = service.download_environment(download_env_request)

        assert result.success is False
        assert result.error.code == "DownloadError"


class TestWebServiceSync:
    """Tests for WebService.sync()."""

    def test_sync_success(self, service, sync_request):
        with patch("adare.backend.sync.sync"):
            result = service.sync(sync_request)

        assert result.success is True
        assert result.data.synced is True

    def test_sync_failure(self, service, sync_request):
        with patch("adare.backend.sync.sync", side_effect=ConnectionError("offline")):
            result = service.sync(sync_request)

        assert result.success is False
        assert result.error.code == "SyncError"

    def test_sync_no_request(self, service):
        with patch("adare.backend.sync.sync"):
            result = service.sync(None)

        assert result.success is True


class TestWebServiceCheckExperiment:
    """Tests for WebService.check_experiment()."""

    def test_check_experiment_exists(self, service, check_experiment_request):
        with patch("adare.webappaccess.api_client.check_experiment_exists", return_value=True):
            result = service.check_experiment(check_experiment_request)

        assert result.success is True
        assert result.data.exists is True
        assert result.data.status == "published"

    def test_check_experiment_not_found(self, service, check_experiment_request):
        with patch("adare.webappaccess.api_client.check_experiment_exists", return_value=False):
            result = service.check_experiment(check_experiment_request)

        assert result.success is True
        assert result.data.exists is False
        assert result.data.status == "not_found"


class TestWebServiceCheckRun:
    """Tests for WebService.check_run()."""

    def test_check_run_exists(self, service, check_run_request):
        with patch("adare.webappaccess.api_client.check_run_exists", return_value=True):
            result = service.check_run(check_run_request)

        assert result.success is True
        assert result.data.exists is True

    def test_check_run_failure(self, service, check_run_request):
        with patch("adare.webappaccess.api_client.check_run_exists",
                    side_effect=ConnectionError("server down")):
            result = service.check_run(check_run_request)

        assert result.success is False
        assert result.error.code == "CheckError"


class TestWebServiceUploadRun:
    """Tests for WebService.upload_run()."""

    def test_upload_run_success(self, service, upload_run_request):
        with patch("adare.webappaccess.upload.publish_experiment_run"):
            result = service.upload_run(upload_run_request)

        assert result.success is True
        assert result.data.published is True

    def test_upload_run_failure(self, service, upload_run_request):
        with patch("adare.webappaccess.upload.publish_experiment_run",
                    side_effect=ConnectionError("upload failed")):
            result = service.upload_run(upload_run_request)

        assert result.success is False
        assert result.error.code == "UploadError"
