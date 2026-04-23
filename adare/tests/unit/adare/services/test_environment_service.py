"""Tests for EnvironmentService."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def service():
    from adare.services.environment_service import EnvironmentService
    return EnvironmentService()


@pytest.fixture
def load_request():
    from adare.core.dto.environment import EnvironmentLoadRequest
    return EnvironmentLoadRequest(environment="test-env.yml", force=False, no_copy=False)


@pytest.fixture
def create_request():
    from adare.core.dto.environment import EnvironmentCreateRequest
    return EnvironmentCreateRequest(project_path=Path("/tmp/project"), name="test-env")


def _make_exception(exc_cls, message="test error"):
    """Helper to construct LoggedErrorException subclasses with a mock logger."""
    return exc_cls(MagicMock(), message=message)


# ---------------------------------------------------------------------------
# load()
# ---------------------------------------------------------------------------
class TestEnvironmentServiceLoad:

    @patch("adare.services.environment_service.environment_database")
    @patch("adare.services.environment_service.backend_environment_load")
    def test_load_success_with_db_data(self, mock_load, mock_db, service, load_request):
        mock_db.resolve_environment_identifier.return_value = "01ULID"
        mock_db.get_environment_data.return_value = {
            "id": "01ULID", "name": "test-env", "description": "desc",
            "vm_name": "win10", "hypervisor": "virtualbox", "vm_os_type": "windows",
            "file": "/tmp/env.yml",
        }

        result = service.load(load_request)

        assert result.success is True
        assert result.data.name == "test-env"
        assert result.data.vm_name == "win10"
        mock_load.assert_called_once()

    @patch("adare.services.environment_service.environment_database")
    @patch("adare.services.environment_service.backend_environment_load")
    def test_load_fallback_when_not_in_db(self, mock_load, mock_db, service, load_request):
        from adare.backend.environment.exceptions import EnvironmentDoesNotExistInDatabase
        mock_db.resolve_environment_identifier.side_effect = _make_exception(
            EnvironmentDoesNotExistInDatabase
        )

        result = service.load(load_request)

        assert result.success is True
        assert result.data.name == "test-env"

    @patch("adare.services.environment_service.backend_environment_load")
    def test_load_fails_on_load_error(self, mock_load, service, load_request):
        from adare.backend.environment.exceptions import EnvironmentLoadFailed
        mock_load.side_effect = _make_exception(EnvironmentLoadFailed)

        result = service.load(load_request)

        assert result.success is False
        assert result.error.code == "EnvironmentLoadFailed"

    @patch("adare.services.environment_service.backend_environment_load")
    def test_load_fails_on_already_exists(self, mock_load, service, load_request):
        from adare.backend.environment.exceptions import EnvironmentAlreadyExists
        mock_load.side_effect = _make_exception(EnvironmentAlreadyExists)

        result = service.load(load_request)

        assert result.success is False
        assert result.error.code == "EnvironmentAlreadyExists"

    @patch("adare.services.environment_service.backend_environment_load")
    def test_load_fails_on_update_error(self, mock_load, service, load_request):
        from adare.backend.environment.exceptions import EnvironmentUpdateError
        mock_load.side_effect = _make_exception(EnvironmentUpdateError)

        result = service.load(load_request)

        assert result.success is False
        assert result.error.code == "EnvironmentUpdateError"


# ---------------------------------------------------------------------------
# create()
# ---------------------------------------------------------------------------
class TestEnvironmentServiceCreate:

    @patch("adare.services.environment_service.backend_environment_create")
    def test_create_success(self, mock_create, service, create_request):
        result = service.create(create_request)

        assert result.success is True
        assert result.data.name == "test-env"
        assert result.data.file_path == Path("/tmp/project/environments/test-env.yml")
        mock_create.assert_called_once_with(create_request.project_path, "test-env", vm_path=None)

    @patch("adare.services.environment_service.backend_environment_create")
    def test_create_fails_file_exists(self, mock_create, service, create_request):
        from adare.backend.environment.exceptions import EnvironmentFileAlreadyExists
        mock_create.side_effect = _make_exception(EnvironmentFileAlreadyExists)

        result = service.create(create_request)

        assert result.success is False
        assert result.error.code == "EnvironmentFileAlreadyExists"


# ---------------------------------------------------------------------------
# delete()
# ---------------------------------------------------------------------------
class TestEnvironmentServiceDelete:

    @patch("adare.services.environment_service.backend_environment_delete")
    @patch("adare.services.environment_service.environment_database")
    def test_delete_success(self, mock_db, mock_delete, service):
        mock_db.resolve_environment_identifier.return_value = "01ULID"

        result = service.delete("test-env")

        assert result.success is True
        mock_delete.assert_called_once_with("01ULID", force=False)

    @patch("adare.services.environment_service.environment_database")
    def test_delete_not_found(self, mock_db, service):
        from adare.backend.environment.exceptions import EnvironmentDoesNotExistInDatabase
        mock_db.resolve_environment_identifier.side_effect = _make_exception(
            EnvironmentDoesNotExistInDatabase
        )

        result = service.delete("nonexistent")

        assert result.success is False
        assert result.error.code == "EnvironmentDoesNotExistInDatabase"

    @patch("adare.services.environment_service.backend_environment_delete")
    @patch("adare.services.environment_service.environment_database")
    def test_delete_deletion_error(self, mock_db, mock_delete, service):
        from adare.backend.environment.exceptions import EnvironmentDeletionError
        mock_db.resolve_environment_identifier.return_value = "01ULID"
        mock_delete.side_effect = _make_exception(EnvironmentDeletionError)

        result = service.delete("test-env")

        assert result.success is False
        assert result.error.code == "EnvironmentDeletionError"


# ---------------------------------------------------------------------------
# list_all()
# ---------------------------------------------------------------------------
class TestEnvironmentServiceListAll:

    @patch("adare.services.environment_service.EnvironmentDbApi")
    def test_list_all_returns_items(self, mock_api_cls, service):
        env = MagicMock()
        env.id = "01A"
        env.name = "env1"
        env.description = "d"
        env.hypervisor = "vbox"
        env.vm = MagicMock()
        env.vm.name = "vm1"
        env.vm.osinfo = MagicMock()
        env.vm.osinfo.platform = "linux"
        mock_ctx = MagicMock()
        mock_ctx.get_environments.return_value = [env]
        mock_api_cls.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_api_cls.return_value.__exit__ = MagicMock(return_value=False)

        result = service.list_all()

        assert result.success is True
        assert len(result.data) == 1
        assert result.data[0].name == "env1"

    @patch("adare.services.environment_service.EnvironmentDbApi")
    def test_list_all_empty(self, mock_api_cls, service):
        mock_ctx = MagicMock()
        mock_ctx.get_environments.return_value = []
        mock_api_cls.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_api_cls.return_value.__exit__ = MagicMock(return_value=False)

        result = service.list_all()

        assert result.success is True
        assert result.data == []

    @patch("adare.services.environment_service.EnvironmentDbApi")
    def test_list_all_db_error(self, mock_api_cls, service):
        mock_api_cls.side_effect = RuntimeError("db down")

        result = service.list_all()

        assert result.success is False
        assert result.error.code == "EnvironmentListError"


# ---------------------------------------------------------------------------
# get_by_id()
# ---------------------------------------------------------------------------
class TestEnvironmentServiceGetById:

    @patch("adare.services.environment_service.environment_database")
    def test_get_by_id_found(self, mock_db, service):
        mock_db.get_environment_data.return_value = {
            "id": "01A", "name": "env1", "description": "d",
            "vm_name": "vm1", "vm_os_type": "linux", "file": "/tmp/env.yml",
        }
        mock_db.get_environment_hypervisor.return_value = "virtualbox"

        result = service.get_by_id("01A")

        assert result.success is True
        assert result.data.name == "env1"
        assert result.data.file_path == Path("/tmp/env.yml")

    @patch("adare.services.environment_service.environment_database")
    def test_get_by_id_not_found(self, mock_db, service):
        mock_db.get_environment_data.return_value = None

        result = service.get_by_id("01MISSING")

        assert result.success is False
        assert result.error.code == "EnvironmentNotFoundError"

    @patch("adare.services.environment_service.environment_database")
    def test_get_by_id_db_exception(self, mock_db, service):
        from adare.backend.environment.exceptions import EnvironmentDoesNotExistInDatabase
        mock_db.get_environment_data.side_effect = _make_exception(
            EnvironmentDoesNotExistInDatabase
        )

        result = service.get_by_id("01BAD")

        assert result.success is False
        assert result.error.code == "EnvironmentDoesNotExistInDatabase"


# ---------------------------------------------------------------------------
# get_by_name()
# ---------------------------------------------------------------------------
class TestEnvironmentServiceGetByName:

    @patch("adare.services.environment_service.environment_database")
    def test_get_by_name_found(self, mock_db, service):
        mock_db.resolve_environment_identifier.return_value = "01A"
        mock_db.get_environment_data.return_value = {
            "id": "01A", "name": "env1", "description": "d",
            "vm_name": "vm1", "vm_os_type": "linux",
        }
        mock_db.get_environment_hypervisor.return_value = "virtualbox"

        result = service.get_by_name("env1")

        assert result.success is True
        assert result.data.name == "env1"

    @patch("adare.services.environment_service.environment_database")
    def test_get_by_name_not_found(self, mock_db, service):
        from adare.backend.environment.exceptions import EnvironmentDoesNotExistInDatabase
        mock_db.resolve_environment_identifier.side_effect = _make_exception(
            EnvironmentDoesNotExistInDatabase
        )

        result = service.get_by_name("nonexistent")

        assert result.success is False
        assert result.error.code == "EnvironmentDoesNotExistInDatabase"
