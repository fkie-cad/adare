"""Unit tests for adare.cli.manage handler functions."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from adare.core.dto.manage import DbInitResult, DbResetResult, VmRuntimeRefreshResult
from adare.core.result import Result

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# exec_manage_reset_db
# ---------------------------------------------------------------------------

@patch("adare.cli.manage.print_success_message")
@patch("adare.cli.manage.AdareAPI")
def test_exec_manage_reset_db_success(mock_api_cls, mock_print_success):
    """Successful DB reset prints success with location."""
    from adare.cli.manage import exec_manage_reset_db

    mock_api = MagicMock()
    mock_api_cls.return_value = mock_api

    reset_result = DbResetResult(was_reset=True, location=Path("/var/adare/global.db"))
    mock_api.manage.reset_db.return_value = Result.ok(reset_result)

    args = MagicMock()
    exec_manage_reset_db(args)

    mock_api.manage.reset_db.assert_called_once()
    mock_print_success.assert_called_once_with(
        title="Global database reset successfully!",
        location=str(reset_result.location),
    )


@patch("builtins.print")
@patch("adare.cli.manage.AdareAPI")
def test_exec_manage_reset_db_no_db(mock_api_cls, mock_print):
    """When DB was not reset (not found), prints informational message."""
    from adare.cli.manage import exec_manage_reset_db

    mock_api = MagicMock()
    mock_api_cls.return_value = mock_api

    reset_result = DbResetResult(was_reset=False)
    mock_api.manage.reset_db.return_value = Result.ok(reset_result)

    args = MagicMock()
    exec_manage_reset_db(args)

    mock_print.assert_called_once_with("No global database found to reset")


@patch("adare.cli.manage.handle_api_error")
@patch("adare.cli.manage.AdareAPI")
def test_exec_manage_reset_db_failure(mock_api_cls, mock_handle_error):
    """Failed DB reset delegates to handle_api_error."""
    from adare.cli.manage import exec_manage_reset_db

    mock_api = MagicMock()
    mock_api_cls.return_value = mock_api

    fail_result = Result.fail("PERMISSION_DENIED", "Cannot delete database")
    mock_api.manage.reset_db.return_value = fail_result

    args = MagicMock()
    exec_manage_reset_db(args)

    mock_handle_error.assert_called_once_with(fail_result)


# ---------------------------------------------------------------------------
# exec_manage_init_db
# ---------------------------------------------------------------------------

@patch("builtins.print")
@patch("adare.cli.manage.AdareAPI")
def test_exec_manage_init_db_success(mock_api_cls, mock_print):
    """Successful DB init prints initialization messages."""
    from adare.cli.manage import exec_manage_init_db

    mock_api = MagicMock()
    mock_api_cls.return_value = mock_api

    init_result = DbInitResult(
        global_db_initialized=True,
        global_db_location=Path("/var/adare/global.db"),
    )
    mock_api.manage.init_db.return_value = Result.ok(init_result)

    args = MagicMock()
    exec_manage_init_db(args)

    mock_api.manage.init_db.assert_called_once()
    # Should print the initialization message and success lines
    printed = [c.args[0] for c in mock_print.call_args_list]
    assert any("Initializing" in msg for msg in printed)
    assert any("Global database initialized" in msg for msg in printed)
    assert any("completed successfully" in msg for msg in printed)


@patch("builtins.print")
@patch("adare.cli.manage.AdareAPI")
def test_exec_manage_init_db_failure_flag(mock_api_cls, mock_print):
    """When global_db_initialized is False, prints failure and errors."""
    from adare.cli.manage import exec_manage_init_db

    mock_api = MagicMock()
    mock_api_cls.return_value = mock_api

    init_result = DbInitResult(
        global_db_initialized=False,
        global_db_location=None,
        errors=["disk full"],
    )
    mock_api.manage.init_db.return_value = Result.ok(init_result)

    args = MagicMock()
    exec_manage_init_db(args)

    printed = [c.args[0] for c in mock_print.call_args_list]
    assert any("Failed to initialize" in msg for msg in printed)
    assert any("disk full" in msg for msg in printed)


# ---------------------------------------------------------------------------
# exec_manage_vm_runtime_refresh
# ---------------------------------------------------------------------------

@patch("adare.cli.manage.print_success_message")
@patch("adare.cli.manage.AdareAPI")
def test_exec_manage_vm_runtime_refresh_success(mock_api_cls, mock_print_success):
    """Successful VM runtime refresh calls API and prints success."""
    from adare.cli.manage import exec_manage_vm_runtime_refresh

    mock_api = MagicMock()
    mock_api_cls.return_value = mock_api

    refresh_result = VmRuntimeRefreshResult(
        refreshed=True,
        project_path=Path("/tmp/myproject"),
    )
    mock_api.manage.refresh_vm_runtime.return_value = Result.ok(refresh_result)

    args = MagicMock()
    exec_manage_vm_runtime_refresh(args)

    mock_api.manage.refresh_vm_runtime.assert_called_once()
    mock_print_success.assert_called_once_with(
        title="VM runtime refreshed successfully!",
        location=str(refresh_result.project_path),
    )


@patch("adare.cli.manage.handle_api_error")
@patch("adare.cli.manage.AdareAPI")
def test_exec_manage_vm_runtime_refresh_failure(mock_api_cls, mock_handle_error):
    """Failed VM runtime refresh delegates to handle_api_error."""
    from adare.cli.manage import exec_manage_vm_runtime_refresh

    mock_api = MagicMock()
    mock_api_cls.return_value = mock_api

    fail_result = Result.fail("NO_PROJECT", "No project found in current directory")
    mock_api.manage.refresh_vm_runtime.return_value = fail_result

    args = MagicMock()
    exec_manage_vm_runtime_refresh(args)

    mock_handle_error.assert_called_once_with(fail_result)
