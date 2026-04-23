"""Tests for ExperimentService — experiment lifecycle and query operations."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def service():
    from adare.services.experiment_service import ExperimentService
    return ExperimentService()


@pytest.fixture
def project_path():
    return Path("/tmp/test-project")


@pytest.fixture
def create_request(project_path):
    from adare.core.dto.experiment import ExperimentCreateRequest
    return ExperimentCreateRequest(project_path=project_path, name="test-exp")


@pytest.fixture
def load_request(project_path):
    from adare.core.dto.experiment import ExperimentLoadRequest
    return ExperimentLoadRequest(project_path=project_path, name="test-exp")


@pytest.fixture
def clone_request(project_path):
    from adare.core.dto.experiment import ExperimentCloneRequest
    return ExperimentCloneRequest(
        project_path=project_path,
        source_experiment="source-exp",
        target_experiment="cloned-exp",
    )


@pytest.fixture
def remove_request(project_path):
    from adare.core.dto.experiment import ExperimentRemoveRequest
    return ExperimentRemoveRequest(project_path=project_path, name="test-exp")


@pytest.fixture
def validate_request(project_path):
    from adare.core.dto.experiment import ExperimentValidateRequest
    return ExperimentValidateRequest(project_path=project_path, name="test-exp")


@pytest.fixture
def env_modify_request(project_path):
    from adare.core.dto.experiment import ExperimentEnvModifyRequest
    return ExperimentEnvModifyRequest(
        project_path=project_path,
        experiment_pattern="test-*",
        environments=["win10", "win11"],
    )


class TestExperimentServiceCreate:
    """Tests for ExperimentService.create()."""

    @patch("adare.services.experiment_service.ExperimentDirectory")
    @patch("adare.services.experiment_service.backend_experiment_create")
    def test_create_success(self, mock_create, mock_exp_dir_cls, service, create_request):
        mock_exp_dir = MagicMock()
        mock_exp_dir.path = Path("/tmp/test-project/experiments/test-exp")
        mock_exp_dir.playbookfile.name = "playbook.yaml"
        mock_exp_dir.metadatafile.name = "metadata.yaml"
        mock_exp_dir_cls.return_value = mock_exp_dir

        result = service.create(create_request)

        assert result.success is True
        assert result.data.name == "test-exp"
        assert len(result.data.next_steps) > 0
        mock_create.assert_called_once_with(create_request.project_path, "test-exp")

    @patch("adare.services.experiment_service.backend_experiment_create")
    def test_create_directory_already_exists(self, mock_create, service, create_request):
        from adare.backend.experiment.exceptions import ExperimentDirectoryAlreadyExistsError
        mock_create.side_effect = ExperimentDirectoryAlreadyExistsError(
            MagicMock(), "directory already exists"
        )

        result = service.create(create_request)

        assert result.success is False


class TestExperimentServiceLoad:
    """Tests for ExperimentService.load()."""

    @patch("adare.services.experiment_service.ExperimentDirectory")
    @patch("adare.services.experiment_service.experiment_database")
    @patch("adare.services.experiment_service.ExperimentApi")
    @patch("adare.services.experiment_service.backend_experiment_load")
    def test_load_success(self, mock_load, mock_api_cls, mock_exp_db, mock_exp_dir_cls,
                          service, load_request):
        mock_experiment = MagicMock()
        mock_experiment.id = "01ABC"
        mock_experiment.name = "test-exp"
        mock_experiment.description = "desc"
        mock_experiment.sha256 = "abc123"
        mock_experiment.environments = []

        mock_ctx = MagicMock()
        mock_ctx.get_experiment_by_project_and_name.return_value = mock_experiment
        mock_api_cls.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_api_cls.return_value.__exit__ = MagicMock(return_value=False)

        mock_exp_db.get_experiment_run_count.return_value = 0

        mock_exp_dir = MagicMock()
        mock_exp_dir.path = Path("/tmp/test-project/experiments/test-exp")
        mock_exp_dir.exists.return_value = True
        mock_exp_dir_cls.return_value = mock_exp_dir

        result = service.load(load_request)

        assert result.success is True
        assert result.data.name == "test-exp"
        mock_load.assert_called_once()

    @patch("adare.services.experiment_service.backend_experiment_load")
    def test_load_directory_not_exists(self, mock_load, service, load_request):
        from adare.backend.experiment.exceptions import ExperimentDirectoryDoesNotExistError
        mock_load.side_effect = ExperimentDirectoryDoesNotExistError(
            MagicMock(), "directory does not exist"
        )

        result = service.load(load_request)

        assert result.success is False


class TestExperimentServiceClone:
    """Tests for ExperimentService.clone()."""

    @patch("adare.services.experiment_service.ExperimentDirectory")
    @patch("adare.services.experiment_service.backend_experiment_clone")
    def test_clone_success(self, mock_clone, mock_exp_dir_cls, service, clone_request):
        mock_exp_dir = MagicMock()
        mock_exp_dir.path = Path("/tmp/test-project/experiments/cloned-exp")
        mock_exp_dir_cls.return_value = mock_exp_dir

        result = service.clone(clone_request)

        assert result.success is True
        assert result.data.name == "cloned-exp"
        assert "Cloned from source-exp" in result.data.description
        mock_clone.assert_called_once()

    @patch("adare.services.experiment_service.backend_experiment_clone")
    def test_clone_target_exists(self, mock_clone, service, clone_request):
        from adare.backend.experiment.exceptions import ExperimentDirectoryAlreadyExistsError
        mock_clone.side_effect = ExperimentDirectoryAlreadyExistsError(
            MagicMock(), "target directory already exists"
        )

        result = service.clone(clone_request)

        assert result.success is False


class TestExperimentServiceRemove:
    """Tests for ExperimentService.remove()."""

    @patch("adare.services.experiment_service.backend_experiment_remove")
    def test_remove_success(self, mock_remove, service, remove_request):
        result = service.remove(remove_request)

        assert result.success is True
        assert result.data.removed_from_db is True
        assert result.data.experiment_name == "test-exp"
        mock_remove.assert_called_once()

    @patch("adare.services.experiment_service.backend_experiment_remove")
    def test_remove_directory_not_exists(self, mock_remove, service, remove_request):
        from adare.backend.experiment.exceptions import ExperimentDirectoryDoesNotExistError
        mock_remove.side_effect = ExperimentDirectoryDoesNotExistError(
            MagicMock(), "directory does not exist"
        )

        result = service.remove(remove_request)

        assert result.success is False


class TestExperimentServiceClean:
    """Tests for ExperimentService.clean()."""

    @patch("adare.services.experiment_service.backend_experiment_clean")
    def test_clean_success(self, mock_clean, service, project_path):
        mock_clean.return_value = 5

        result = service.clean(project_path, "test-exp")

        assert result.success is True
        assert result.data.deleted_count == 5


class TestExperimentServiceValidate:
    """Tests for ExperimentService.validate()."""

    @patch("adare.services.experiment_service.backend_experiment_validate")
    def test_validate_success(self, mock_validate, service, validate_request):
        mock_validate.return_value = []

        result = service.validate(validate_request)

        assert result.success is True
        assert result.data.name == "test-exp"


class TestExperimentServiceListAll:
    """Tests for ExperimentService.list_all()."""

    @patch("adare.services.experiment_service.experiment_database")
    @patch("adare.services.experiment_service.ExperimentApi")
    def test_list_all_returns_experiments(self, mock_api_cls, mock_exp_db, service, project_path):
        mock_exp1 = MagicMock()
        mock_exp1.id = "01A"
        mock_exp1.name = "exp1"
        mock_exp1.description = "First"
        mock_exp1.environments = [MagicMock()]

        mock_exp2 = MagicMock()
        mock_exp2.id = "01B"
        mock_exp2.name = "exp2"
        mock_exp2.description = "Second"
        mock_exp2.environments = []

        mock_ctx = MagicMock()
        mock_ctx.get_experiments.return_value = [mock_exp1, mock_exp2]
        mock_api_cls.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_api_cls.return_value.__exit__ = MagicMock(return_value=False)

        mock_exp_db.get_experiment_run_count.return_value = 0

        result = service.list_all(project_path)

        assert result.success is True
        assert len(result.data) == 2
        assert result.data[0].name == "exp1"

    @patch("adare.services.experiment_service.ExperimentApi")
    def test_list_all_empty(self, mock_api_cls, service, project_path):
        mock_ctx = MagicMock()
        mock_ctx.get_experiments.return_value = []
        mock_api_cls.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_api_cls.return_value.__exit__ = MagicMock(return_value=False)

        result = service.list_all(project_path)

        assert result.success is True
        assert result.data == []


class TestExperimentServiceGetByName:
    """Tests for ExperimentService.get_by_name()."""

    @patch("adare.services.experiment_service.ExperimentDirectory")
    @patch("adare.services.experiment_service.experiment_database")
    @patch("adare.services.experiment_service.ExperimentApi")
    def test_get_by_name_found(self, mock_api_cls, mock_exp_db, mock_exp_dir_cls,
                               service, project_path):
        mock_experiment = MagicMock()
        mock_experiment.id = "01ABC"
        mock_experiment.name = "my-exp"
        mock_experiment.description = "Test"
        mock_experiment.sha256 = "abc"
        mock_experiment.environments = [MagicMock(name="win10")]

        mock_ctx = MagicMock()
        mock_ctx.get_experiment_by_project_and_name.return_value = mock_experiment
        mock_api_cls.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_api_cls.return_value.__exit__ = MagicMock(return_value=False)

        mock_exp_db.get_experiment_run_count.return_value = 3

        mock_exp_dir = MagicMock()
        mock_exp_dir.path = Path("/tmp/test-project/experiments/my-exp")
        mock_exp_dir.exists.return_value = True
        mock_exp_dir_cls.return_value = mock_exp_dir

        result = service.get_by_name(project_path, "my-exp")

        assert result.success is True
        assert result.data.name == "my-exp"
        assert result.data.is_loaded is True

    @patch("adare.services.experiment_service.ExperimentApi")
    def test_get_by_name_not_found(self, mock_api_cls, service, project_path):
        mock_ctx = MagicMock()
        mock_ctx.get_experiment_by_project_and_name.return_value = None
        mock_api_cls.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_api_cls.return_value.__exit__ = MagicMock(return_value=False)

        result = service.get_by_name(project_path, "nonexistent")

        assert result.success is False
        assert result.error.code == "ExperimentNotFoundError"


class TestExperimentServiceAddEnvironments:
    """Tests for ExperimentService.add_environments()."""

    @patch("adare.services.experiment_service.backend_experiment_add_environments")
    def test_add_environments_success(self, mock_add, service, env_modify_request):
        mock_add.return_value = {'affected_experiments': ['test-exp1', 'test-exp2']}

        result = service.add_environments(env_modify_request)

        assert result.success is True
        assert result.data.operation == 'add'
        assert len(result.data.affected_experiments) == 2


class TestExperimentServiceRemoveEnvironments:
    """Tests for ExperimentService.remove_environments()."""

    @patch("adare.services.experiment_service.backend_experiment_remove_environments")
    def test_remove_environments_success(self, mock_remove, service, env_modify_request):
        mock_remove.return_value = {'affected_experiments': ['test-exp1']}

        result = service.remove_environments(env_modify_request)

        assert result.success is True
        assert result.data.operation == 'remove'
        assert result.data.environments_changed == ["win10", "win11"]
