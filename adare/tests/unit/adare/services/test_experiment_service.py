"""Tests for ExperimentService — experiment lifecycle and query operations."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

PP = Path("/tmp/test-project")


@pytest.fixture
def service():
    from adare.services.experiment_service import ExperimentService
    return ExperimentService()


@pytest.fixture
def create_request():
    from adare.core.dto.experiment import ExperimentCreateRequest
    return ExperimentCreateRequest(project_path=PP, name="test-exp")


@pytest.fixture
def load_request():
    from adare.core.dto.experiment import ExperimentLoadRequest
    return ExperimentLoadRequest(project_path=PP, name="test-exp")


@pytest.fixture
def clone_request():
    from adare.core.dto.experiment import ExperimentCloneRequest
    return ExperimentCloneRequest(project_path=PP, source_experiment="source-exp",
                                  target_experiment="cloned-exp")


@pytest.fixture
def remove_request():
    from adare.core.dto.experiment import ExperimentRemoveRequest
    return ExperimentRemoveRequest(project_path=PP, name="test-exp")


@pytest.fixture
def env_modify_request():
    from adare.core.dto.experiment import ExperimentEnvModifyRequest
    return ExperimentEnvModifyRequest(project_path=PP, experiment_pattern="test-*",
                                      environments=["win10", "win11"])


def _mock_api_ctx(mock_api_cls):
    """Wire up a mock ExperimentApi context manager, return the inner context."""
    ctx = MagicMock()
    mock_api_cls.return_value.__enter__ = MagicMock(return_value=ctx)
    mock_api_cls.return_value.__exit__ = MagicMock(return_value=False)
    return ctx


class TestExperimentServiceCreate:
    @patch("adare.services.experiment_service.ExperimentDirectory")
    @patch("adare.services.experiment_service.backend_experiment_create")
    def test_create_success(self, mock_create, mock_dir_cls, service, create_request):
        d = MagicMock(); d.path = PP / "experiments/test-exp"
        d.playbookfile.name = "playbook.yaml"; d.metadatafile.name = "metadata.yaml"
        mock_dir_cls.return_value = d
        result = service.create(create_request)
        assert result.success is True
        assert result.data.name == "test-exp"
        assert len(result.data.next_steps) > 0

    @patch("adare.services.experiment_service.backend_experiment_create")
    def test_create_already_exists(self, mock_create, service, create_request):
        from adare.backend.experiment.exceptions import ExperimentDirectoryAlreadyExistsError
        mock_create.side_effect = ExperimentDirectoryAlreadyExistsError(MagicMock(), "exists")
        assert service.create(create_request).success is False


class TestExperimentServiceLoad:
    @patch("adare.services.experiment_service.ExperimentDirectory")
    @patch("adare.services.experiment_service.experiment_database")
    @patch("adare.services.experiment_service.ExperimentApi")
    @patch("adare.services.experiment_service.backend_experiment_load")
    def test_load_success(self, mock_load, mock_api_cls, mock_db, mock_dir_cls, service, load_request):
        exp = MagicMock(id="01ABC", description="d", sha256="x", environments=[])
        exp.name = "test-exp"
        _mock_api_ctx(mock_api_cls).get_experiment_by_project_and_name.return_value = exp
        mock_db.get_experiment_run_count.return_value = 0
        d = MagicMock(); d.path = PP / "experiments/test-exp"; d.exists.return_value = True
        mock_dir_cls.return_value = d
        result = service.load(load_request)
        assert result.success is True and result.data.name == "test-exp"

    @patch("adare.services.experiment_service.backend_experiment_load")
    def test_load_dir_missing(self, mock_load, service, load_request):
        from adare.backend.experiment.exceptions import ExperimentDirectoryDoesNotExistError
        mock_load.side_effect = ExperimentDirectoryDoesNotExistError(MagicMock(), "missing")
        assert service.load(load_request).success is False


class TestExperimentServiceClone:
    @patch("adare.services.experiment_service.ExperimentDirectory")
    @patch("adare.services.experiment_service.backend_experiment_clone")
    def test_clone_success(self, mock_clone, mock_dir_cls, service, clone_request):
        mock_dir_cls.return_value.path = PP / "experiments/cloned-exp"
        result = service.clone(clone_request)
        assert result.success is True and result.data.name == "cloned-exp"
        assert "Cloned from source-exp" in result.data.description

    @patch("adare.services.experiment_service.backend_experiment_clone")
    def test_clone_target_exists(self, mock_clone, service, clone_request):
        from adare.backend.experiment.exceptions import ExperimentDirectoryAlreadyExistsError
        mock_clone.side_effect = ExperimentDirectoryAlreadyExistsError(MagicMock(), "exists")
        assert service.clone(clone_request).success is False


class TestExperimentServiceRemove:
    @patch("adare.services.experiment_service.backend_experiment_remove")
    def test_remove_success(self, mock_remove, service, remove_request):
        result = service.remove(remove_request)
        assert result.success is True
        assert result.data.removed_from_db is True and result.data.experiment_name == "test-exp"

    @patch("adare.services.experiment_service.backend_experiment_remove")
    def test_remove_dir_missing(self, mock_remove, service, remove_request):
        from adare.backend.experiment.exceptions import ExperimentDirectoryDoesNotExistError
        mock_remove.side_effect = ExperimentDirectoryDoesNotExistError(MagicMock(), "missing")
        assert service.remove(remove_request).success is False


class TestExperimentServiceClean:
    @patch("adare.services.experiment_service.backend_experiment_clean")
    def test_clean_success(self, mock_clean, service):
        mock_clean.return_value = 5
        result = service.clean(PP, "test-exp")
        assert result.success is True and result.data.deleted_count == 5


class TestExperimentServiceValidate:
    @patch("adare.services.experiment_service.backend_experiment_validate")
    def test_validate_success(self, mock_validate, service):
        from adare.core.dto.experiment import ExperimentValidateRequest
        mock_validate.return_value = []
        result = service.validate(ExperimentValidateRequest(project_path=PP, name="test-exp"))
        assert result.success is True and result.data.name == "test-exp"


class TestExperimentServiceListAll:
    @patch("adare.services.experiment_service.experiment_database")
    @patch("adare.services.experiment_service.ExperimentApi")
    def test_list_all_returns_experiments(self, mock_api_cls, mock_db, service):
        e1 = MagicMock(id="01A", name="exp1", description="", environments=[MagicMock()])
        e2 = MagicMock(id="01B", name="exp2", description="", environments=[])
        _mock_api_ctx(mock_api_cls).get_experiments.return_value = [e1, e2]
        mock_db.get_experiment_run_count.return_value = 0
        result = service.list_all(PP)
        assert result.success is True and len(result.data) == 2

    @patch("adare.services.experiment_service.ExperimentApi")
    def test_list_all_empty(self, mock_api_cls, service):
        _mock_api_ctx(mock_api_cls).get_experiments.return_value = []
        result = service.list_all(PP)
        assert result.success is True and result.data == []


class TestExperimentServiceGetByName:
    @patch("adare.services.experiment_service.ExperimentDirectory")
    @patch("adare.services.experiment_service.experiment_database")
    @patch("adare.services.experiment_service.ExperimentApi")
    def test_found(self, mock_api_cls, mock_db, mock_dir_cls, service):
        exp = MagicMock(id="01X", name="my-exp", description="T", sha256="a",
                        environments=[MagicMock(name="win10")])
        _mock_api_ctx(mock_api_cls).get_experiment_by_project_and_name.return_value = exp
        mock_db.get_experiment_run_count.return_value = 3
        d = MagicMock(); d.path = PP / "experiments/my-exp"; d.exists.return_value = True
        mock_dir_cls.return_value = d
        result = service.get_by_name(PP, "my-exp")
        assert result.success is True and result.data.is_loaded is True

    @patch("adare.services.experiment_service.ExperimentApi")
    def test_not_found(self, mock_api_cls, service):
        _mock_api_ctx(mock_api_cls).get_experiment_by_project_and_name.return_value = None
        result = service.get_by_name(PP, "nonexistent")
        assert result.success is False and result.error.code == "ExperimentNotFoundError"


class TestExperimentServiceEnvironments:
    @patch("adare.services.experiment_service.backend_experiment_add_environments")
    def test_add_environments(self, mock_add, service, env_modify_request):
        mock_add.return_value = {'affected_experiments': ['e1', 'e2']}
        result = service.add_environments(env_modify_request)
        assert result.success is True and result.data.operation == 'add'

    @patch("adare.services.experiment_service.backend_experiment_remove_environments")
    def test_remove_environments(self, mock_remove, service, env_modify_request):
        mock_remove.return_value = {'affected_experiments': ['e1']}
        result = service.remove_environments(env_modify_request)
        assert result.success is True and result.data.operation == 'remove'
