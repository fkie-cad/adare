import pytest
from datetime import datetime
from pathlib import Path

pytestmark = pytest.mark.unit

from adare.core.dto.vm import (
    VmLoadRequest, VmInfo, VmInstanceInfo, VmInstanceUsage,
    VmClearResult, VmTestRequest, VmTestResult,
)


class TestVmLoadRequest:
    def test_defaults(self):
        req = VmLoadRequest(file_path=Path("/vm.ova"))
        assert req.name is None
        assert req.os_architecture == "x86_64"
        assert req.force is False

    def test_full_construction(self):
        req = VmLoadRequest(
            file_path=Path("/vm.ova"), name="win10",
            os_platform="windows", os_type="desktop",
            force=True,
        )
        assert req.name == "win10"
        assert req.force is True


class TestVmInfo:
    def test_construction(self):
        info = VmInfo(
            id="1", name="vm1", file_path="/f", file_hash="abc",
            description="d", hypervisor="virtualbox", use_snapshots=True,
        )
        assert info.instance_count == 0
        assert info.is_external is False
        assert info.os_platform is None


class TestVmInstanceInfo:
    def test_construction(self):
        now = datetime.now()
        info = VmInstanceInfo(
            id="1", vm_id="v1", vm_name="vm",
            instance_name="vm_inst_1", status="active",
            websocket_port=5900, vbox_uuid="uuid",
            base_snapshot_name="base", current_experiment_run_id=None,
            created_at=now, last_used_at=now,
        )
        assert info.status == "active"
        assert info.hypervisor == "virtualbox"


class TestVmInstanceUsage:
    def test_construction(self):
        usage = VmInstanceUsage(
            total_instances=5, active_instances=2,
            available_instances=2, stopped_instances=1,
            instances_by_vm={"vm1": 3, "vm2": 2},
        )
        assert usage.total_instances == 5
        assert usage.instances_by_vm["vm1"] == 3


class TestVmClearResult:
    def test_construction(self):
        r = VmClearResult(
            deleted_count=1, deleted_vms=["vm1"],
            failed_count=0, failed_vms=[],
        )
        assert r.deleted_count == 1


class TestVmTestRequest:
    def test_construction(self):
        req = VmTestRequest(ova_file_path=Path("/test.ova"), guest_platform="windows")
        assert req.verbose is False
        assert req.vm_cleanup_mode == "prompt"


class TestVmTestResult:
    def test_construction(self):
        r = VmTestResult(success=True, ova_file="test.ova", guest_platform="windows", message="OK")
        assert r.success is True
