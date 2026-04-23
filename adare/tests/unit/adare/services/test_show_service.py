"""Tests for ShowService — data display and query operations."""

from unittest.mock import MagicMock, patch

import pytest

from adare.services.show_service import ShowService

pytestmark = pytest.mark.unit

_SDA = "adare.database.api.structured_data.StructuredDataApi"


@pytest.fixture
def service():
    return ShowService()


def _mock(defaults, **overrides):
    """Build a MagicMock with attributes from defaults + overrides."""
    vals = {**defaults, **overrides}
    m = MagicMock()
    for k, v in vals.items():
        setattr(m, k, v)
    return m


_RUN = dict(ulid="01RUN", experiment_name="exp1", experiment_ulid="01EXP",
            environment_name="win10", environment_ulid="01ENV", project_name="proj1",
            start_time=None, end_time=None, duration_seconds=0.0,
            status="SUCCESS", overall_result="PASS", published=False, fake=False)

_PROJECT = dict(name="proj1", description="A project", path="/tmp/proj1",
                created_at=None, experiment_count=2, environment_count=1)

_ENV = dict(ulid="01ENV", name="win10", display_name="Windows 10",
            dotnotation="proj.win10", project="proj1", description="",
            vm_box="win10box", vm_id="vm-1", os_info="Windows 10",
            osinfo_os="Windows", osinfo_distribution="", osinfo_version="10",
            osinfo_language="en", published=False, in_request=False,
            created_at=None, file="env.yaml")

_EXP = dict(ulid="01EXP", name="exp1", display_name="Experiment 1",
            dotnotation="proj.exp1", project="proj1", environment="win10",
            environments=["win10"], description="", tags=[],
            published=False, in_request=False, created_at=None,
            run_count=0, last_run=None)

_TF = dict(id="01TF", name="click_button", dotnotation="file.click_button",
           display_name="Click Button", description="Clicks a button",
           parameter_count=1, parameters=[{"name": "x"}],
           file_id="01FILE", file_name="actions.py", file_path="tests/",
           full_file_path="/tmp/tests/actions.py", file_sha256="abc",
           file_description="Action file")


def _sda_ctx(mock_cls):
    """Wire up StructuredDataApi context manager, return inner context."""
    ctx = MagicMock()
    mock_cls.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_cls.return_value.__exit__ = MagicMock(return_value=False)
    return ctx


class TestShowServiceListRuns:
    @patch.object(ShowService, "_query_across_projects")
    def test_success(self, mock_q, service):
        mock_q.return_value = [_mock(_RUN), _mock(_RUN, ulid="02RUN")]
        result = service.list_runs()
        assert result.success is True and len(result.data) == 2

    @patch.object(ShowService, "_query_across_projects")
    def test_empty(self, mock_q, service):
        mock_q.return_value = []
        assert service.list_runs().data == []

    @patch.object(ShowService, "_query_across_projects")
    def test_project_filter(self, mock_q, service):
        from adare.core.dto.show import RunListRequest
        mock_q.return_value = [_mock(_RUN, project_name="proj1"),
                               _mock(_RUN, ulid="02", project_name="proj2")]
        result = service.list_runs(RunListRequest(project="proj1"))
        assert len(result.data) == 1 and result.data[0].project_name == "proj1"


class TestShowServiceGetRun:
    @patch.object(ShowService, "_query_across_projects")
    def test_found(self, mock_q, service):
        mock_q.return_value = [_mock(_RUN, ulid="01RUN")]
        result = service.get_run(ulid="01RUN")
        assert result.success is True and result.data.ulid == "01RUN"

    @patch.object(ShowService, "_query_across_projects")
    def test_not_found(self, mock_q, service):
        mock_q.return_value = []
        result = service.get_run(ulid="MISSING")
        assert result.success is False and result.error.code == "RunNotFoundError"


class TestShowServiceListProjects:
    @patch(_SDA)
    def test_success(self, mock_cls, service):
        ctx = _sda_ctx(mock_cls)
        ctx.get_projects_structured.return_value = [_mock(_PROJECT), _mock(_PROJECT, name="p2")]
        result = service.list_projects()
        assert result.success is True and len(result.data) == 2

    @patch(_SDA)
    def test_exception(self, mock_cls, service):
        from sqlalchemy.exc import SQLAlchemyError
        mock_cls.return_value.__enter__ = MagicMock(side_effect=SQLAlchemyError("err"))
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)
        result = service.list_projects()
        assert result.success is False and result.error.code == "ProjectListError"


class TestShowServiceEnvironments:
    @patch(_SDA)
    def test_list_success(self, mock_cls, service):
        _sda_ctx(mock_cls).get_environments_structured.return_value = [_mock(_ENV)]
        result = service.list_environments()
        assert result.success is True and result.data[0].name == "win10"

    @patch(_SDA)
    def test_get_found(self, mock_cls, service):
        _sda_ctx(mock_cls).get_environments_structured.return_value = [_mock(_ENV, name="win10")]
        assert service.get_environment("win10").data.name == "win10"

    @patch(_SDA)
    def test_get_not_found(self, mock_cls, service):
        _sda_ctx(mock_cls).get_environments_structured.return_value = []
        result = service.get_environment("nonexistent")
        assert result.error.code == "EnvironmentNotFoundError"


class TestShowServiceExperiments:
    @patch.object(ShowService, "_query_across_projects")
    def test_list_success(self, mock_q, service):
        mock_q.return_value = [_mock(_EXP)]
        assert len(service.list_experiments().data) == 1

    @patch.object(ShowService, "_query_across_projects")
    def test_get_by_name(self, mock_q, service):
        mock_q.return_value = [_mock(_EXP, name="my-exp")]
        assert service.get_experiment(name="my-exp").data.name == "my-exp"

    @patch.object(ShowService, "_query_across_projects")
    def test_get_not_found(self, mock_q, service):
        mock_q.return_value = []
        assert service.get_experiment(name="x").error.code == "ExperimentNotFoundError"

    @patch.object(ShowService, "_query_across_projects")
    def test_get_by_ulid(self, mock_q, service):
        mock_q.return_value = [_mock(_EXP, ulid="01XYZ")]
        assert service.get_experiment(ulid="01XYZ").data.ulid == "01XYZ"


class TestShowServiceTestfunctions:
    @patch(_SDA)
    def test_list_success(self, mock_cls, service):
        _sda_ctx(mock_cls).get_testfunctions_structured.return_value = [_mock(_TF)]
        assert service.list_testfunctions().data[0].name == "click_button"

    @patch(_SDA)
    def test_get_found(self, mock_cls, service):
        _sda_ctx(mock_cls).get_testfunctions_structured.return_value = [_mock(_TF)]
        assert service.get_testfunction("file.click_button").data.dotnotation == "file.click_button"

    @patch(_SDA)
    def test_get_not_found(self, mock_cls, service):
        _sda_ctx(mock_cls).get_testfunctions_structured.return_value = []
        assert service.get_testfunction("x.y").error.code == "TestfunctionNotFoundError"
