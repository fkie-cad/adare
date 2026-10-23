"""Tests for VMService — VM management operations."""

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def service():
    from adare.services.vm_service import VMService

    return VMService()


@pytest.fixture
def load_request():
    from pathlib import Path

    from adare.core.dto.vm import VmLoadRequest

    return VmLoadRequest(file_path=Path("/tmp/test.ova"), name="test-vm")


def _make_vm_mock(vm_id="vm-01", name="test-vm", hash_val="abc123def456", hypervisor="qemu"):
    """Helper to build a mock VM ORM object."""
    vm = MagicMock()
    vm.id = vm_id
    vm.name = name
    vm.hash = hash_val
    vm.file = "/tmp/test.ova"
    vm.description = "A test VM"
    vm.hypervisor = hypervisor
    vm.use_snapshots = True
    osinfo = MagicMock()
    osinfo.platform = "linux"
    osinfo.os = "Linux"
    osinfo.distribution = "Ubuntu"
    osinfo.version = "22.04"
    osinfo.language = "en"
    osinfo.architecture = "x86_64"
    vm.osinfo = osinfo
    return vm


class TestVMServiceListAll:
    """Tests for VMService.list_all()."""

    @patch("adare.services.vm_service.VmApi")
    def test_list_all_returns_vms(self, mock_api_cls, service):
        mock_api = MagicMock()
        mock_api_cls.return_value.__enter__ = MagicMock(return_value=mock_api)
        mock_api_cls.return_value.__exit__ = MagicMock(return_value=False)

        vm = _make_vm_mock()
        mock_api.get_all_vms.return_value = [vm]
        mock_api.get_vm_instances_for_vm.return_value = []

        result = service.list_all()

        assert result.success is True
        assert len(result.data) == 1
        assert result.data[0].name == "test-vm"

    @patch("adare.services.vm_service.VmApi")
    def test_list_all_empty(self, mock_api_cls, service):
        mock_api = MagicMock()
        mock_api_cls.return_value.__enter__ = MagicMock(return_value=mock_api)
        mock_api_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_api.get_all_vms.return_value = []

        result = service.list_all()

        assert result.success is True
        assert result.data == []


class TestVMServiceGetByName:
    """Tests for VMService.get_by_name()."""

    @patch("adare.services.vm_service.VmApi")
    def test_get_by_name_not_found(self, mock_api_cls, service):
        mock_api = MagicMock()
        mock_api_cls.return_value.__enter__ = MagicMock(return_value=mock_api)
        mock_api_cls.return_value.__exit__ = MagicMock(return_value=False)
        mock_api.get_vm_by_name.return_value = None

        result = service.get_by_name("nonexistent")

        assert result.success is False
        assert result.error.code == "VMNotFoundError"


class TestVMServiceDelete:
    """Tests for VMService.delete(): the shared removal path, never cascading into environments."""

    @patch("adare.backend.vm.removal.remove_vm")
    def test_delete_success(self, mock_remove, service):
        result = service.delete("vm-01", force=True)

        assert result.success is True
        mock_remove.assert_called_once_with("vm-01", force=True, cascade=False)

    @patch("adare.backend.vm.removal.remove_vm")
    def test_delete_not_found(self, mock_remove, service):
        from adare.database.api.vm import VMNotFoundError

        mock_remove.side_effect = VMNotFoundError(MagicMock(), message="VM with ID vm-99 not found")

        result = service.delete("vm-99")

        assert result.success is False
        assert result.error.code == "VMNotFoundError"

    @patch("adare.backend.vm.removal.remove_vm")
    def test_delete_refuses_a_vm_environments_use(self, mock_remove, service):
        from adare.backend.vm.exceptions import VMInUseByEnvironmentError

        mock_remove.side_effect = VMInUseByEnvironmentError(MagicMock(), message="used by environment(s) ubuntu")

        result = service.delete("vm-01")

        assert result.success is False
        assert result.error.code == "VMInUseByEnvironmentError"


class TestVMServiceClearAll:
    """Tests for VMService.clear_all()."""

    @patch("adare.services.vm_service.backend_clear_all_vms")
    def test_clear_all_success(self, mock_clear, service):
        mock_clear.return_value = {
            "deleted_count": 2,
            "deleted_vms": ["a", "b"],
            "failed_count": 0,
            "failed_vms": [],
        }

        result = service.clear_all(force=True)

        assert result.success is True
        assert result.data.deleted_count == 2

    @patch("adare.services.vm_service.backend_clear_all_vms")
    def test_clear_all_vm_error(self, mock_clear, service):
        from adare.backend.vm.exceptions import VMError

        mock_clear.side_effect = VMError(MagicMock(), message="clear failed")

        result = service.clear_all()

        assert result.success is False


class TestVMServiceRemoveInstance:
    """Tests for VMService.remove_instance() (async)."""

    @pytest.mark.asyncio
    @patch("adare.services.vm_service.VMService.remove_instance")
    async def test_remove_instance_success(self, mock_remove):
        from adare.core.result import Result

        mock_remove.return_value = Result.ok(None)

        result = await mock_remove("inst-01")

        assert result.success is True

    @pytest.mark.asyncio
    async def test_remove_instance_forwards_force(self, service):
        from unittest.mock import AsyncMock

        with patch("adare.backend.vm.instance_manager.cleanup_vm_instance", new_callable=AsyncMock) as cleanup:
            result = await service.remove_instance("inst-01", force=True)

        assert result.success is True
        cleanup.assert_awaited_once_with("inst-01", force=True)

    @pytest.mark.asyncio
    async def test_remove_running_instance_is_a_failure_result(self, service):
        from adare.hypervisor.exceptions import InstanceStateException

        with patch(
            "adare.backend.vm.instance_manager.cleanup_vm_instance",
            side_effect=InstanceStateException("inst-01", current_state="running", expected_states=["shutoff"]),
        ):
            result = await service.remove_instance("inst-01")

        assert result.success is False
        assert result.error.code == "InstanceStateException"

    @pytest.mark.asyncio
    async def test_remove_instance_not_found(self, service):
        from adare.database.api.vm import VMNotFoundError

        with patch(
            "adare.backend.vm.instance_manager.cleanup_vm_instance",
            side_effect=VMNotFoundError(MagicMock(), message="not found"),
        ):
            result = await service.remove_instance("inst-99")

        assert result.success is False


class TestVMServiceGetInstanceUsage:
    """Tests for VMService.get_instance_usage()."""

    @patch("adare.services.vm_service.VmApi")
    def test_get_instance_usage(self, mock_api_cls, service):
        mock_api = MagicMock()
        mock_api_cls.return_value.__enter__ = MagicMock(return_value=mock_api)
        mock_api_cls.return_value.__exit__ = MagicMock(return_value=False)

        inst1 = MagicMock(status="active")
        inst1.vm.name = "vm-a"
        inst2 = MagicMock(status="stopped")
        inst2.vm.name = "vm-a"
        mock_api.get_all_vm_instances.return_value = [inst1, inst2]

        result = service.get_instance_usage()

        assert result.success is True
        assert result.data.total_instances == 2
        assert result.data.active_instances == 1
        assert result.data.stopped_instances == 1
