"""Tests for ProjectService — establishes service test pattern."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def service():
    from adare.services.project_service import ProjectService
    return ProjectService()


@pytest.fixture
def create_request():
    from adare.core.dto.project import ProjectCreateRequest
    return ProjectCreateRequest(name="test-project", path=Path("/tmp/test-project"), description="A test project")


@pytest.fixture
def remove_request():
    from adare.core.dto.project import ProjectRemoveRequest
    return ProjectRemoveRequest(path=Path("/tmp/test-project"))


class TestProjectServiceCreate:
    """Tests for ProjectService.create()."""

    @patch("adare.services.project_service.project_database")
    @patch("adare.services.project_service.ProjectDirectory")
    @patch("adare.services.project_service.ensure_project_database_exists")
    @patch("adare.services.project_service.fixture_stages")
    @patch("adare.services.project_service.fixture_status")
    def test_create_success(self, mock_fix_status, mock_fix_stages, mock_ensure_db,
                            mock_proj_dir_cls, mock_proj_db, service, create_request):
        mock_proj_dir = MagicMock()
        mock_proj_dir_cls.return_value = mock_proj_dir
        mock_proj_db.get_project_by_path.return_value = {"id": "01ABCDEF"}

        with patch("adare.database.api.base.ProjectDatabaseApi") as mock_db_api:
            mock_ctx = MagicMock()
            mock_db_api.return_value.__enter__ = MagicMock(return_value=mock_ctx)
            mock_db_api.return_value.__exit__ = MagicMock(return_value=False)

            result = service.create(create_request)

        assert result.success is True
        assert result.data.name == "test-project"
        assert result.data.path == Path("/tmp/test-project")
        assert len(result.data.next_steps) > 0
        mock_proj_dir.create.assert_called_once()

    @patch("adare.services.project_service.ProjectDirectory")
    def test_create_fails_on_directory_creation_error(self, mock_proj_dir_cls, service, create_request):
        from adare.backend.project.exceptions import ProjectDirectoryCreationError

        mock_proj_dir = MagicMock()
        mock_proj_dir.create.side_effect = ProjectDirectoryCreationError(
            MagicMock(), message="directory already exists"
        )
        mock_proj_dir_cls.return_value = mock_proj_dir

        result = service.create(create_request)

        assert result.success is False
        assert result.error is not None

    @patch("adare.services.project_service.project_database")
    @patch("adare.services.project_service.ProjectDirectory")
    def test_create_fails_on_database_error_cleans_up(self, mock_proj_dir_cls, mock_proj_db,
                                                       service, create_request):
        from adare.database.exceptions import DatabaseProjectCreationError

        mock_proj_dir = MagicMock()
        mock_proj_dir_cls.return_value = mock_proj_dir
        mock_proj_db.add_project.side_effect = DatabaseProjectCreationError(
            MagicMock(), message="project already exists in database"
        )

        result = service.create(create_request)

        assert result.success is False
        mock_proj_dir.remove.assert_called_once()


class TestProjectServiceRemove:
    """Tests for ProjectService.remove()."""

    @patch("adare.services.project_service.project_database")
    @patch("adare.services.project_service.ProjectDirectory")
    def test_remove_success(self, mock_proj_dir_cls, mock_proj_db, service, remove_request):
        mock_proj_db.get_project_by_path.return_value = {"id": "01ABCDEF", "name": "test"}
        mock_proj_dir = MagicMock()
        mock_proj_dir.exists.return_value = True
        mock_proj_dir_cls.return_value = mock_proj_dir

        result = service.remove(remove_request)

        assert result.success is True
        mock_proj_dir.remove.assert_called_once()
        mock_proj_db.remove_project.assert_called_once_with(remove_request.path)

    @patch("adare.services.project_service.project_database")
    def test_remove_project_not_in_database(self, mock_proj_db, service, remove_request):
        mock_proj_db.get_project_by_path.return_value = None

        result = service.remove(remove_request)

        assert result.success is False
        assert result.error.code == "ProjectMissingInDatabaseError"

    @patch("adare.services.project_service.project_database")
    @patch("adare.services.project_service.ProjectDirectory")
    def test_remove_directory_already_deleted(self, mock_proj_dir_cls, mock_proj_db, service, remove_request):
        mock_proj_db.get_project_by_path.return_value = {"id": "01ABCDEF"}
        mock_proj_dir = MagicMock()
        mock_proj_dir.exists.return_value = False
        mock_proj_dir_cls.return_value = mock_proj_dir

        result = service.remove(remove_request)

        assert result.success is True
        mock_proj_dir.remove.assert_not_called()
        mock_proj_db.remove_project.assert_called_once()


class TestProjectServiceListAll:
    """Tests for ProjectService.list_all()."""

    @patch("adare.services.project_service.project_database")
    def test_list_all_returns_projects(self, mock_proj_db, service):
        mock_proj_db.get_all_projects.return_value = [
            {"id": "01A", "name": "proj1", "path": "/tmp/proj1", "description": "First"},
            {"id": "01B", "name": "proj2", "path": "/tmp/proj2", "description": "Second"},
        ]

        result = service.list_all()

        assert result.success is True
        assert len(result.data) == 2
        assert result.data[0].name == "proj1"
        assert result.data[1].name == "proj2"

    @patch("adare.services.project_service.project_database")
    def test_list_all_empty(self, mock_proj_db, service):
        mock_proj_db.get_all_projects.return_value = []

        result = service.list_all()

        assert result.success is True
        assert result.data == []


class TestProjectServiceGetByPath:
    """Tests for ProjectService.get_by_path()."""

    @patch("adare.services.project_service.project_database")
    def test_get_by_path_found(self, mock_proj_db, service):
        mock_proj_db.get_project_by_path.return_value = {
            "id": "01A", "name": "myproj", "path": "/tmp/myproj", "description": "Test"
        }

        result = service.get_by_path(Path("/tmp/myproj"))

        assert result.success is True
        assert result.data.name == "myproj"
        assert result.data.path == Path("/tmp/myproj")

    @patch("adare.services.project_service.project_database")
    def test_get_by_path_not_found(self, mock_proj_db, service):
        mock_proj_db.get_project_by_path.return_value = None

        result = service.get_by_path(Path("/tmp/nonexistent"))

        assert result.success is False
        assert result.error.code == "ProjectNotFoundError"
