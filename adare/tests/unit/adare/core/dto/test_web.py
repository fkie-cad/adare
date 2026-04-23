import pytest
from pathlib import Path

pytestmark = pytest.mark.unit

from adare.core.dto.web import (
    WebLoginResult, WebLogoutResult, WebStatusResult,
    DownloadEnvironmentRequest, DownloadResult,
    SyncResult, PublishResult, CheckExperimentResult,
    SubmitResult,
)


class TestWebLoginResult:
    def test_defaults(self):
        r = WebLoginResult(logged_in=True)
        assert r.username is None
        assert r.message == ""

    def test_full(self):
        r = WebLoginResult(logged_in=True, username="user", message="Welcome")
        assert r.username == "user"


class TestWebLogoutResult:
    def test_construction(self):
        r = WebLogoutResult(logged_out=True, message="Bye")
        assert r.logged_out is True


class TestWebStatusResult:
    def test_construction(self):
        r = WebStatusResult(logged_in=False)
        assert r.username is None


class TestDownloadEnvironmentRequest:
    def test_construction(self):
        req = DownloadEnvironmentRequest(project_path=Path("/p"), environment_name="env1")
        assert req.environment_name == "env1"


class TestDownloadResult:
    def test_defaults(self):
        r = DownloadResult(downloaded=True)
        assert r.message == ""
        assert r.location is None

    def test_with_location(self):
        r = DownloadResult(downloaded=True, location=Path("/dl/file"))
        assert r.location == Path("/dl/file")


class TestSyncResult:
    def test_construction(self):
        r = SyncResult(synced=True, message="All synced")
        assert r.synced is True


class TestPublishResult:
    def test_construction(self):
        r = PublishResult(published=True, message="Published successfully")
        assert r.published is True


class TestCheckExperimentResult:
    def test_construction(self):
        r = CheckExperimentResult(experiment_ulid="abc", exists=True, status="published")
        assert r.status == "published"


class TestSubmitResult:
    def test_construction(self):
        r = SubmitResult(pr_url="https://github.com/pr/1", pr_number=1, message="Created")
        assert r.pr_number == 1
