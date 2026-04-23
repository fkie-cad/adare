"""Tests for ShowService — data display and query operations."""

from unittest.mock import MagicMock, patch

import pytest

from adare.services.show_service import ShowService

pytestmark = pytest.mark.unit

# Patch path for StructuredDataApi (imported locally inside methods)
_SDA_PATH = "adare.database.api.structured_data.StructuredDataApi"


@pytest.fixture
def service():
    return ShowService()


def _make_run_structured(**overrides):
    """Helper to build a mock structured run object."""
    defaults = dict(
        ulid="01RUN", experiment_name="exp1", experiment_ulid="01EXP",
        environment_name="win10", environment_ulid="01ENV", project_name="proj1",
        start_time=None, end_time=None, duration_seconds=0.0,
        status="SUCCESS", overall_result="PASS", published=False, fake=False,
    )
    defaults.update(overrides)
    m = MagicMock()
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


def _make_project_structured(**overrides):
    """Helper to build a mock structured project object."""
    defaults = dict(name="proj1", description="A project", path="/tmp/proj1",
                    created_at=None, experiment_count=2, environment_count=1)
    defaults.update(overrides)
    m = MagicMock()
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


def _make_env_structured(**overrides):
    """Helper to build a mock structured environment object."""
    defaults = dict(
        ulid="01ENV", name="win10", display_name="Windows 10",
        dotnotation="proj.win10", project="proj1", description="",
        vm_box="win10box", vm_id="vm-1", os_info="Windows 10",
        osinfo_os="Windows", osinfo_distribution="", osinfo_version="10",
        osinfo_language="en", published=False, in_request=False,
        created_at=None, file="env.yaml",
    )
    defaults.update(overrides)
    m = MagicMock()
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


def _make_experiment_structured(**overrides):
    """Helper to build a mock structured experiment object."""
    defaults = dict(
        ulid="01EXP", name="exp1", display_name="Experiment 1",
        dotnotation="proj.exp1", project="proj1", environment="win10",
        environments=["win10"], description="", tags=[],
        published=False, in_request=False, created_at=None,
        run_count=0, last_run=None,
    )
    defaults.update(overrides)
    m = MagicMock()
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


def _make_testfunction_structured(**overrides):
    """Helper to build a mock structured testfunction object."""
    defaults = dict(
        id="01TF", name="click_button", dotnotation="file.click_button",
        display_name="Click Button", description="Clicks a button",
        parameter_count=1, parameters=[{"name": "x"}],
        file_id="01FILE", file_name="actions.py", file_path="tests/",
        full_file_path="/tmp/tests/actions.py", file_sha256="abc",
        file_description="Action file",
    )
    defaults.update(overrides)
    m = MagicMock()
    for k, v in defaults.items():
        setattr(m, k, v)
    return m


class TestShowServiceListRuns:
    """Tests for ShowService.list_runs()."""

    @patch.object(ShowService, "_query_across_projects")
    def test_list_runs_success(self, mock_query, service):
        mock_query.return_value = [_make_run_structured(), _make_run_structured(ulid="02RUN")]

        result = service.list_runs()

        assert result.success is True
        assert len(result.data) == 2

    @patch.object(ShowService, "_query_across_projects")
    def test_list_runs_empty(self, mock_query, service):
        mock_query.return_value = []

        result = service.list_runs()

        assert result.success is True
        assert result.data == []

    @patch.object(ShowService, "_query_across_projects")
    def test_list_runs_with_project_filter(self, mock_query, service):
        from adare.core.dto.show import RunListRequest
        mock_query.return_value = [
            _make_run_structured(project_name="proj1"),
            _make_run_structured(ulid="02RUN", project_name="proj2"),
        ]

        request = RunListRequest(project="proj1")
        result = service.list_runs(request)

        assert result.success is True
        assert len(result.data) == 1
        assert result.data[0].project_name == "proj1"


class TestShowServiceGetRun:
    """Tests for ShowService.get_run()."""

    @patch.object(ShowService, "_query_across_projects")
    def test_get_run_found(self, mock_query, service):
        mock_query.return_value = [_make_run_structured(ulid="01RUN")]

        result = service.get_run(ulid="01RUN")

        assert result.success is True
        assert result.data.ulid == "01RUN"

    @patch.object(ShowService, "_query_across_projects")
    def test_get_run_not_found(self, mock_query, service):
        mock_query.return_value = []

        result = service.get_run(ulid="MISSING")

        assert result.success is False
        assert result.error.code == "RunNotFoundError"


class TestShowServiceListProjects:
    """Tests for ShowService.list_projects()."""

    @patch(_SDA_PATH)
    def test_list_projects_success(self, mock_api_cls, service):
        mock_ctx = MagicMock()
        mock_ctx.get_projects_structured.return_value = [
            _make_project_structured(),
            _make_project_structured(name="proj2"),
        ]
        mock_api_cls.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_api_cls.return_value.__exit__ = MagicMock(return_value=False)

        result = service.list_projects()

        assert result.success is True
        assert len(result.data) == 2
        assert result.data[0].name == "proj1"

    @patch(_SDA_PATH)
    def test_list_projects_exception(self, mock_api_cls, service):
        mock_api_cls.return_value.__enter__ = MagicMock(side_effect=RuntimeError("db error"))
        mock_api_cls.return_value.__exit__ = MagicMock(return_value=False)

        result = service.list_projects()

        assert result.success is False
        assert result.error.code == "ProjectListError"


class TestShowServiceListEnvironments:
    """Tests for ShowService.list_environments()."""

    @patch(_SDA_PATH)
    def test_list_environments_success(self, mock_api_cls, service):
        mock_ctx = MagicMock()
        mock_ctx.get_environments_structured.return_value = [_make_env_structured()]
        mock_api_cls.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_api_cls.return_value.__exit__ = MagicMock(return_value=False)

        result = service.list_environments()

        assert result.success is True
        assert len(result.data) == 1
        assert result.data[0].name == "win10"


class TestShowServiceGetEnvironment:
    """Tests for ShowService.get_environment()."""

    @patch(_SDA_PATH)
    def test_get_environment_found(self, mock_api_cls, service):
        mock_ctx = MagicMock()
        mock_ctx.get_environments_structured.return_value = [_make_env_structured(name="win10")]
        mock_api_cls.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_api_cls.return_value.__exit__ = MagicMock(return_value=False)

        result = service.get_environment("win10")

        assert result.success is True
        assert result.data.name == "win10"

    @patch(_SDA_PATH)
    def test_get_environment_not_found(self, mock_api_cls, service):
        mock_ctx = MagicMock()
        mock_ctx.get_environments_structured.return_value = []
        mock_api_cls.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_api_cls.return_value.__exit__ = MagicMock(return_value=False)

        result = service.get_environment("nonexistent")

        assert result.success is False
        assert result.error.code == "EnvironmentNotFoundError"


class TestShowServiceListExperiments:
    """Tests for ShowService.list_experiments()."""

    @patch.object(ShowService, "_query_across_projects")
    def test_list_experiments_success(self, mock_query, service):
        mock_query.return_value = [_make_experiment_structured()]

        result = service.list_experiments()

        assert result.success is True
        assert len(result.data) == 1
        assert result.data[0].name == "exp1"


class TestShowServiceGetExperiment:
    """Tests for ShowService.get_experiment()."""

    @patch.object(ShowService, "_query_across_projects")
    def test_get_experiment_by_name(self, mock_query, service):
        mock_query.return_value = [_make_experiment_structured(name="my-exp")]

        result = service.get_experiment(name="my-exp")

        assert result.success is True
        assert result.data.name == "my-exp"

    @patch.object(ShowService, "_query_across_projects")
    def test_get_experiment_not_found(self, mock_query, service):
        mock_query.return_value = []

        result = service.get_experiment(name="missing")

        assert result.success is False
        assert result.error.code == "ExperimentNotFoundError"

    @patch.object(ShowService, "_query_across_projects")
    def test_get_experiment_by_ulid(self, mock_query, service):
        mock_query.return_value = [_make_experiment_structured(ulid="01XYZ")]

        result = service.get_experiment(ulid="01XYZ")

        assert result.success is True
        assert result.data.ulid == "01XYZ"


class TestShowServiceListTestfunctions:
    """Tests for ShowService.list_testfunctions()."""

    @patch(_SDA_PATH)
    def test_list_testfunctions_success(self, mock_api_cls, service):
        mock_ctx = MagicMock()
        mock_ctx.get_testfunctions_structured.return_value = [_make_testfunction_structured()]
        mock_api_cls.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_api_cls.return_value.__exit__ = MagicMock(return_value=False)

        result = service.list_testfunctions()

        assert result.success is True
        assert len(result.data) == 1
        assert result.data[0].name == "click_button"


class TestShowServiceGetTestfunction:
    """Tests for ShowService.get_testfunction()."""

    @patch(_SDA_PATH)
    def test_get_testfunction_found(self, mock_api_cls, service):
        mock_ctx = MagicMock()
        mock_ctx.get_testfunctions_structured.return_value = [
            _make_testfunction_structured(dotnotation="file.click_button")
        ]
        mock_api_cls.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_api_cls.return_value.__exit__ = MagicMock(return_value=False)

        result = service.get_testfunction("file.click_button")

        assert result.success is True
        assert result.data.dotnotation == "file.click_button"

    @patch(_SDA_PATH)
    def test_get_testfunction_not_found(self, mock_api_cls, service):
        mock_ctx = MagicMock()
        mock_ctx.get_testfunctions_structured.return_value = []
        mock_api_cls.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_api_cls.return_value.__exit__ = MagicMock(return_value=False)

        result = service.get_testfunction("missing.func")

        assert result.success is False
        assert result.error.code == "TestfunctionNotFoundError"
