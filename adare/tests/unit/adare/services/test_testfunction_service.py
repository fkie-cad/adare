"""Tests for TestfunctionService."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def service():
    from adare.services.testfunction_service import TestfunctionService
    return TestfunctionService()


@pytest.fixture
def create_request():
    from adare.core.dto.testfunction import TestfunctionCreateRequest
    return TestfunctionCreateRequest(project_path=Path("/tmp/project"), name="check_file")


@pytest.fixture
def load_request():
    from adare.core.dto.testfunction import TestfunctionLoadRequest
    return TestfunctionLoadRequest(path=Path("/tmp/testfunctions/check_file.py"), force=False)


def _make_exception(exc_cls, message="test error"):
    """Helper to construct LoggedErrorException subclasses with a mock logger."""
    return exc_cls(MagicMock(), message=message)


# ---------------------------------------------------------------------------
# create()
# ---------------------------------------------------------------------------
class TestTestfunctionServiceCreate:

    @patch("adare.services.testfunction_service.backend_testfunction_create")
    def test_create_success(self, mock_create, service, create_request):
        result = service.create(create_request)

        assert result.success is True
        assert result.data.name == "check_file"
        assert result.data.file_path == Path("/tmp/project/testfunctions/check_file")
        mock_create.assert_called_once_with(Path("/tmp/project"), "check_file")

    @patch("adare.services.testfunction_service.backend_testfunction_create")
    def test_create_fails_missing_file(self, mock_create, service, create_request):
        from adare.backend.testfunction.exceptions import TestfunctionMissingFileError
        mock_create.side_effect = _make_exception(TestfunctionMissingFileError)

        result = service.create(create_request)

        assert result.success is False
        assert result.error.code == "TestfunctionMissingFileError"


# ---------------------------------------------------------------------------
# load()
# ---------------------------------------------------------------------------
class TestTestfunctionServiceLoad:

    @patch("adare.services.testfunction_service.backend_testfunction_load_global")
    def test_load_success(self, mock_load, service, load_request):
        mock_load.return_value = "01ULID"

        result = service.load(load_request)

        assert result.success is True
        # Path("/tmp/testfunctions/check_file.py").is_file() is False (doesn't exist), so .name is used
        assert result.data.name == "check_file.py"
        assert result.data.id == "01ULID"
        mock_load.assert_called_once_with(Path("/tmp/testfunctions/check_file.py"), force=False)

    @patch("adare.services.testfunction_service.backend_testfunction_load_global")
    def test_load_directory_path(self, mock_load, service):
        from adare.core.dto.testfunction import TestfunctionLoadRequest
        req = TestfunctionLoadRequest(path=Path("/tmp/testfunctions/my_tests"), force=True)
        # Simulate directory (is_file returns False for MagicMock by default; use a real Path trick)
        mock_load.return_value = "01XYZ"

        with patch.object(Path, "is_file", return_value=False):
            result = service.load(req)

        assert result.success is True
        assert result.data.name == "my_tests"

    @patch("adare.services.testfunction_service.backend_testfunction_load_global")
    def test_load_fails_missing_file(self, mock_load, service, load_request):
        from adare.backend.testfunction.exceptions import TestfunctionMissingFileError
        mock_load.side_effect = _make_exception(TestfunctionMissingFileError)

        result = service.load(load_request)

        assert result.success is False
        assert result.error.code == "TestfunctionMissingFileError"


# ---------------------------------------------------------------------------
# remove()
# ---------------------------------------------------------------------------
class TestTestfunctionServiceRemove:

    @patch("adare.services.testfunction_service.backend_testfunction_remove")
    @patch("adare.services.testfunction_service.testfunction_database")
    def test_remove_success(self, mock_db, mock_remove, service):
        mock_db.testfunction_file_exists.return_value = True
        mock_db.get_testfunction_usage.return_value = {
            "can_safely_delete": True, "experiments": [], "runs": [],
        }

        result = service.remove("check_file", force=True)

        assert result.success is True
        assert result.data.name == "check_file"
        assert result.data.was_removed is True
        mock_remove.assert_called_once_with("check_file")

    @patch("adare.services.testfunction_service.testfunction_database")
    def test_remove_not_found(self, mock_db, service):
        mock_db.testfunction_file_exists.return_value = False

        result = service.remove("nonexistent")

        assert result.success is False
        assert result.error.code == "TestfunctionNotFoundError"

    @patch("adare.services.testfunction_service.testfunction_database")
    def test_remove_in_use_without_force(self, mock_db, service):
        mock_db.testfunction_file_exists.return_value = True
        mock_db.get_testfunction_usage.return_value = {
            "can_safely_delete": False,
            "experiments": [{"name": "exp1"}, {"name": "exp2"}],
            "runs": [],
        }

        result = service.remove("check_file", force=False)

        assert result.success is False
        assert result.error.code == "TestfunctionInUseError"

    @patch("adare.services.testfunction_service.backend_testfunction_remove")
    @patch("adare.services.testfunction_service.testfunction_database")
    def test_remove_in_use_with_force(self, mock_db, mock_remove, service):
        mock_db.testfunction_file_exists.return_value = True
        mock_db.get_testfunction_usage.return_value = {
            "can_safely_delete": False,
            "experiments": [{"name": "exp1"}],
            "runs": [{"id": 1}, {"id": 2}],
        }

        result = service.remove("check_file", force=True)

        assert result.success is True
        assert result.data.experiments_affected == 1
        assert result.data.runs_deleted == 2

    @patch("adare.services.testfunction_service.testfunction_database")
    def test_remove_backend_exception(self, mock_db, service):
        from adare.backend.testfunction.exceptions import TestfunctionMissingFileError
        mock_db.testfunction_file_exists.side_effect = _make_exception(TestfunctionMissingFileError)

        result = service.remove("check_file")

        assert result.success is False
        assert result.error.code == "TestfunctionMissingFileError"


# ---------------------------------------------------------------------------
# list_all()
# ---------------------------------------------------------------------------
class TestTestfunctionServiceListAll:

    @patch("adare.services.testfunction_service.TestfunctionDbApi")
    def test_list_all_returns_items(self, mock_api_cls, service):
        tf_file = MagicMock()
        tf_file.id = 1
        tf_file.name = "checks"
        tf_file.is_published = False
        tf = MagicMock()
        tf.id = 10
        tf.name = "check_file"
        mock_ctx = MagicMock()
        mock_ctx.get_testfunction_files.return_value = [tf_file]
        mock_ctx.get_testfunctions_by_file.return_value = [tf]
        mock_api_cls.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_api_cls.return_value.__exit__ = MagicMock(return_value=False)

        result = service.list_all()

        assert result.success is True
        assert len(result.data) == 1
        assert result.data[0].dotnotation == "checks.check_file"

    @patch("adare.services.testfunction_service.TestfunctionDbApi")
    def test_list_all_empty(self, mock_api_cls, service):
        mock_ctx = MagicMock()
        mock_ctx.get_testfunction_files.return_value = []
        mock_api_cls.return_value.__enter__ = MagicMock(return_value=mock_ctx)
        mock_api_cls.return_value.__exit__ = MagicMock(return_value=False)

        result = service.list_all()

        assert result.success is True
        assert result.data == []

    @patch("adare.services.testfunction_service.TestfunctionDbApi")
    def test_list_all_db_error(self, mock_api_cls, service):
        mock_api_cls.side_effect = RuntimeError("db down")

        result = service.list_all()

        assert result.success is False
        assert result.error.code == "TestfunctionListError"


# ---------------------------------------------------------------------------
# get_usage()
# ---------------------------------------------------------------------------
class TestTestfunctionServiceGetUsage:

    @patch("adare.services.testfunction_service.testfunction_database")
    def test_get_usage_success(self, mock_db, service):
        mock_db.get_testfunction_usage.return_value = {
            "exists": True, "testfunction_file_id": 1, "can_safely_delete": False,
            "projects_affected": [{"name": "proj1"}],
            "experiments": [{"name": "exp1"}],
            "runs": [{"id": 1}],
        }

        result = service.get_usage("check_file")

        assert result.success is True
        assert result.data.exists is True
        assert result.data.runs_count == 1
        assert result.data.projects_affected == ["proj1"]

    @patch("adare.services.testfunction_service.testfunction_database")
    def test_get_usage_db_error(self, mock_db, service):
        mock_db.get_testfunction_usage.side_effect = RuntimeError("db down")

        result = service.get_usage("check_file")

        assert result.success is False
        assert result.error.code == "TestfunctionUsageError"


# ---------------------------------------------------------------------------
# exists()
# ---------------------------------------------------------------------------
class TestTestfunctionServiceExists:

    @patch("adare.services.testfunction_service.testfunction_database")
    def test_exists_true(self, mock_db, service):
        mock_db.testfunction_exists.return_value = True

        result = service.exists("check_file")

        assert result.success is True
        assert result.data.exists is True
        assert result.data.name == "check_file"

    @patch("adare.services.testfunction_service.testfunction_database")
    def test_exists_false(self, mock_db, service):
        mock_db.testfunction_exists.return_value = False

        result = service.exists("nonexistent")

        assert result.success is True
        assert result.data.exists is False

    @patch("adare.services.testfunction_service.testfunction_database")
    def test_exists_db_error(self, mock_db, service):
        mock_db.testfunction_exists.side_effect = RuntimeError("db down")

        result = service.exists("check_file")

        assert result.success is False
        assert result.error.code == "TestfunctionExistsError"
