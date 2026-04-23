"""Unit tests for adare.cli.project handler functions."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from adare.core.dto.project import ProjectCreateRequest, ProjectInfo, ProjectListItem
from adare.core.result import Result

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# exec_create_project
# ---------------------------------------------------------------------------

@patch("adare.cli.project.print_success_message")
@patch("adare.cli.project.AdareAPI")
def test_exec_create_project_success(mock_api_cls, mock_print_success):
    """Successful project creation calls API and prints success message."""
    from adare.cli.project import exec_create_project

    mock_api = MagicMock()
    mock_api_cls.return_value = mock_api

    project_info = ProjectInfo(
        id="abc123",
        name="myproject",
        path=Path("/tmp/myproject"),
        description="A test project",
        next_steps=["cd myproject", "adare env create"],
        tip="Use --help for more options",
    )
    mock_api.project.create.return_value = Result.ok(project_info)

    args = MagicMock()
    args.name = "myproject"
    args.description = "A test project"

    with patch("adare.cli.project.Path") as mock_path_cls:
        mock_cwd = MagicMock()
        mock_path_cls.cwd.return_value = mock_cwd
        project_path = MagicMock()
        project_path.name = "myproject"
        mock_cwd.__truediv__ = MagicMock(return_value=project_path)

        exec_create_project(args)

    mock_api.project.create.assert_called_once()
    mock_print_success.assert_called_once_with(
        title='Project "myproject" created successfully!',
        location=str(project_info.path),
        next_steps=project_info.next_steps,
        tip=project_info.tip,
    )


@patch("adare.cli.project.handle_api_error")
@patch("adare.cli.project.AdareAPI")
def test_exec_create_project_failure(mock_api_cls, mock_handle_error):
    """Failed project creation delegates to handle_api_error."""
    from adare.cli.project import exec_create_project

    mock_api = MagicMock()
    mock_api_cls.return_value = mock_api

    fail_result = Result.fail("DUPLICATE", "Project already exists")
    mock_api.project.create.return_value = fail_result

    args = MagicMock()
    args.name = "myproject"
    args.description = ""

    exec_create_project(args)

    mock_handle_error.assert_called_once_with(fail_result)


# ---------------------------------------------------------------------------
# exec_remove_project
# ---------------------------------------------------------------------------

@patch("adare.cli.project.print_success_message")
@patch("adare.cli.project.AdareAPI")
@patch("adare.cli.project.determine_projectdirectory_for_removal")
def test_exec_remove_project_success(mock_determine, mock_api_cls, mock_print_success):
    """Successful project removal calls API and prints success."""
    from adare.cli.project import exec_remove_project

    project_path = Path("/tmp/myproject")
    mock_determine.return_value = project_path

    mock_api = MagicMock()
    mock_api_cls.return_value = mock_api
    mock_api.project.remove.return_value = Result.ok(None)

    args = MagicMock()
    args.name = "myproject"

    exec_remove_project(args)

    mock_api.project.remove.assert_called_once()
    mock_print_success.assert_called_once_with(
        title=f'Project at "{project_path}" removed successfully!',
    )


@patch("adare.cli.project.AdareAPI")
@patch("adare.cli.project.determine_projectdirectory_for_removal")
def test_exec_remove_project_no_path_exits(mock_determine, mock_api_cls):
    """When no valid project path found, exit(1) is called."""
    from adare.cli.project import exec_remove_project

    mock_determine.return_value = None

    args = MagicMock()
    args.name = "nonexistent"

    with pytest.raises(SystemExit):
        exec_remove_project(args)

    mock_api_cls.return_value.project.remove.assert_not_called()


# ---------------------------------------------------------------------------
# exec_list_projects
# ---------------------------------------------------------------------------

@patch("adare.cli.project.handle_api_error")
@patch("adare.cli.project.AdareAPI")
def test_exec_list_projects_api_failure(mock_api_cls, mock_handle_error):
    """When API call fails, handle_api_error is called."""
    from adare.cli.project import exec_list_projects

    mock_api = MagicMock()
    mock_api_cls.return_value = mock_api

    fail_result = Result.fail("DB_ERROR", "Database unavailable")
    mock_api.project.list_all.return_value = fail_result

    args = MagicMock()

    exec_list_projects(args)

    mock_handle_error.assert_called_once_with(fail_result)


@patch("adare.cli.project.AdareAPI")
def test_exec_list_projects_empty_raises(mock_api_cls):
    """When no projects found, NoProjectsFoundMessage is raised."""
    from adare.cli.project import exec_list_projects

    mock_api = MagicMock()
    mock_api_cls.return_value = mock_api
    mock_api.project.list_all.return_value = Result.ok([])

    args = MagicMock()

    with pytest.raises(Exception, match="no projects found"):
        exec_list_projects(args)
