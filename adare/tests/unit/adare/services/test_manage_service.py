"""Tests for ManageService — database and system management operations."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def service():
    from adare.services.manage_service import ManageService

    return ManageService()


class TestManageServiceGetDbStatus:
    """Tests for ManageService.get_db_status()."""

    @patch("adare.services.manage_service.validate_database_integrity")
    def test_get_db_status_success(self, mock_validate, service):
        mock_validate.return_value = {
            'global_db_exists': True,
            'global_db_accessible': True,
            'global_db_location': '/tmp/adare.db',
            'valid': True,
            'errors': [],
        }

        result = service.get_db_status()

        assert result.success is True
        assert result.data.global_db_exists is True
        assert result.data.valid is True
        assert result.data.global_db_location == Path('/tmp/adare.db')

    @patch("adare.services.manage_service.validate_database_integrity")
    def test_get_db_status_exception(self, mock_validate, service):
        mock_validate.side_effect = OSError("db locked")

        result = service.get_db_status()

        assert result.success is False
        assert result.error.code == "DbStatusError"


class TestManageServiceInitDb:
    """Tests for ManageService.init_db()."""

    @patch("adare.services.manage_service.initialize_database_system")
    def test_init_db_success(self, mock_init, service):
        mock_init.return_value = {
            'global_db_initialized': True,
            'global_db_location': '/tmp/adare.db',
            'errors': [],
        }

        result = service.init_db()

        assert result.success is True
        assert result.data.global_db_initialized is True
        assert result.data.global_db_location == Path('/tmp/adare.db')

    @patch("adare.services.manage_service.initialize_database_system")
    def test_init_db_exception(self, mock_init, service):
        mock_init.side_effect = PermissionError("permission denied")

        result = service.init_db()

        assert result.success is False
        assert result.error.code == "DbInitError"


class TestManageServiceRepairDb:
    """Tests for ManageService.repair_db()."""

    @patch("adare.services.manage_service.repair_database_system")
    def test_repair_db_success(self, mock_repair, service):
        mock_repair.return_value = {
            'repaired': True,
            'actions_taken': ['recreated index'],
            'errors': [],
        }

        result = service.repair_db()

        assert result.success is True
        assert result.data.repaired is True
        assert result.data.actions_taken == ['recreated index']

    @patch("adare.services.manage_service.repair_database_system")
    def test_repair_db_exception(self, mock_repair, service):
        mock_repair.side_effect = OSError("disk full")

        result = service.repair_db()

        assert result.success is False
        assert result.error.code == "DbRepairError"


class TestManageServiceCleanInstallDb:
    """Tests for ManageService.clean_install_db()."""

    def test_clean_install_db_without_force(self, service):
        result = service.clean_install_db(force=False)

        assert result.success is False
        assert result.error.code == "ConfirmationRequired"

    @patch("adare.services.manage_service.clean_install_database_system")
    def test_clean_install_db_with_force(self, mock_clean, service):
        mock_clean.return_value = {
            'installed': True,
            'actions_taken': ['dropped tables', 'recreated schema'],
            'errors': [],
        }

        result = service.clean_install_db(force=True)

        assert result.success is True
        assert result.data.installed is True
        assert len(result.data.actions_taken) == 2

    @patch("adare.services.manage_service.clean_install_database_system")
    def test_clean_install_db_exception(self, mock_clean, service):
        mock_clean.side_effect = OSError("in use")

        result = service.clean_install_db(force=True)

        assert result.success is False
        assert result.error.code == "DbCleanInstallError"


class TestManageServiceResetDb:
    """Tests for ManageService.reset_db()."""

    @patch("adare.services.manage_service.get_global_database_location")
    def test_reset_db_exists(self, mock_get_loc, service, tmp_path):
        db_path = tmp_path / 'global.db.sqlite3'
        db_path.write_bytes(b'')
        mock_get_loc.return_value = db_path

        result = service.reset_db()

        assert result.success is True
        assert result.data.was_reset is True
        assert not db_path.exists()

    @patch("adare.services.manage_service.get_global_database_location")
    def test_reset_db_not_exists(self, mock_get_loc, service, tmp_path):
        mock_get_loc.return_value = tmp_path / 'global.db.sqlite3'

        result = service.reset_db()

        assert result.success is True
        assert result.data.was_reset is False

    @patch("adare.services.manage_service.get_global_database_location")
    def test_reset_db_exception(self, mock_get_loc, service):
        mock_get_loc.side_effect = PermissionError("access denied")

        result = service.reset_db()

        assert result.success is False
        assert result.error.code == "DbResetError"


class TestManageServiceResetAllVms:
    """Tests for ManageService.reset_all_vms()."""

    def test_reset_all_vms_without_force(self, service):
        result = service.reset_all_vms(force=False)

        assert result.success is False
        assert result.error.code == "ConfirmationRequired"

    @patch("adare.backend.vm.commands.clear_all_vms")
    def test_reset_all_vms_with_force(self, mock_clear, service):
        mock_clear.return_value = {
            'deleted_count': 3,
            'failed_count': 0,
            'deleted_vms': ['vm1', 'vm2', 'vm3'],
            'failed_vms': [],
        }

        result = service.reset_all_vms(force=True)

        assert result.success is True
        assert result.data.deleted_count == 3
        assert result.data.failed_count == 0


class TestManageServiceRefreshVmRuntime:
    """Tests for ManageService.refresh_vm_runtime()."""

    @patch("adare.backend.project.directory.ProjectDirectory")
    @patch("shutil.rmtree")
    def test_refresh_vm_runtime_success(self, mock_rmtree, mock_proj_dir_cls, service):
        project_path = Path("/tmp/test-project")

        mock_proj_dir = MagicMock()
        mock_proj_dir_cls.return_value = mock_proj_dir

        with patch.object(Path, 'exists', return_value=True):
            result = service.refresh_vm_runtime(project_path=project_path)

        assert result.success is True
        assert result.data.refreshed is True
        mock_proj_dir.copy_vm_runtime_files.assert_called_once()

    @patch("adare.backend.basics.determine_projectdirectory", return_value=None)
    def test_refresh_vm_runtime_no_project(self, mock_determine, service):
        result = service.refresh_vm_runtime(project_path=None)

        assert result.success is False
        assert result.error.code == "NoProjectFoundError"


class TestManageServiceMaintenance:
    """compact_db / check_db resolve their databases, then defer to adare.database.maintenance."""

    @patch("adare.backend.basics.registered_project_name", return_value="T2F")
    @patch("adare.backend.basics.determine_projectdirectory")
    def test_current_project_by_default(self, mock_determine, _mock_name, service, tmp_path):
        mock_determine.return_value = tmp_path
        entry = MagicMock(failed=False)

        with patch("adare.database.maintenance.compact_database", return_value=entry) as compact:
            result = service.compact_db(dry_run=True)

        assert result.success is True
        assert result.data.dry_run is True
        assert result.data.databases == [entry]
        target = compact.call_args.args[0]
        assert target.label == "T2F"
        assert target.project_path == tmp_path
        assert compact.call_args.kwargs == {"dry_run": True, "progress": None}

    def test_all_includes_every_target_and_passes_labelled_progress(self, service, tmp_path):
        from adare.database.maintenance import DatabaseTarget

        targets = [DatabaseTarget("global", tmp_path / "g.db"), DatabaseTarget("p", tmp_path / "p.db", tmp_path)]
        seen = []

        def fake_compact(target, dry_run, progress):
            progress(5, 10)
            return MagicMock(failed=False)

        with (
            patch("adare.database.maintenance.all_targets", return_value=targets),
            patch("adare.database.maintenance.compact_database", side_effect=fake_compact),
        ):
            result = service.compact_db(all_databases=True, progress=lambda *args: seen.append(args))

        assert result.success is True
        assert seen == [("global", 5, 10), ("p", 5, 10)]

    @patch("adare.backend.basics.determine_projectdirectory", return_value=None)
    def test_no_project_fails_with_all_hint(self, _mock_determine, service):
        result = service.check_db()

        assert result.success is False
        assert result.error.code == "NoProjectFoundError"
        assert any("--all" in solution for solution in result.error.solutions)

    def test_global_database_unreadable_is_a_failure(self, service):
        with patch("adare.database.maintenance.all_targets", side_effect=OSError("gone")):
            result = service.check_db(all_databases=True)

        assert result.success is False
        assert result.error.code == "DbMaintenanceError"
