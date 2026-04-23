import pytest
from pathlib import Path
from unittest.mock import MagicMock

pytestmark = pytest.mark.unit

from adare.core.dto.environment import (
    EnvironmentCreateRequest, EnvironmentDeleteRequest, EnvironmentInfo,
    EnvironmentListItem, EnvironmentLoadRequest,
)


class TestEnvironmentLoadRequest:
    def test_construction(self):
        req = EnvironmentLoadRequest(environment="myenv.yaml")
        assert req.environment == "myenv.yaml"
        assert req.force is False
        assert req.no_copy is False


class TestEnvironmentCreateRequest:
    def test_construction(self):
        req = EnvironmentCreateRequest(project_path=Path("/p"), name="env1")
        assert req.name == "env1"
        assert req.vm_path is None


class TestEnvironmentDeleteRequest:
    def test_construction(self):
        req = EnvironmentDeleteRequest(identifier="env1", force=True)
        assert req.identifier == "env1"
        assert req.force is True


class TestEnvironmentInfo:
    def test_construction(self):
        info = EnvironmentInfo(
            id="1", name="env", description="d",
            vm_name="vm1", hypervisor="virtualbox", os_platform="windows",
            file_path=Path("/f"),
        )
        assert info.next_steps == []
        assert info.tip is None

    def test_to_dict(self):
        info = EnvironmentInfo(
            id="1", name="env", description="d",
            vm_name=None, hypervisor="vbox", os_platform=None,
            file_path=None,
        )
        d = info.to_dict()
        assert d["vm_name"] is None
        assert d["file_path"] is None


class TestEnvironmentListItem:
    def test_construction(self):
        item = EnvironmentListItem(
            id="1", name="env", description="d",
            vm_name="vm", hypervisor="vbox", os_platform="linux",
        )
        assert item.os_platform == "linux"

    def test_from_model_with_vm(self):
        osinfo = MagicMock()
        osinfo.platform = "windows"
        vm = MagicMock()
        vm.name = "win10"
        vm.osinfo = osinfo
        model = MagicMock()
        model.id = "1"
        model.name = "env"
        model.description = "desc"
        model.hypervisor = "virtualbox"
        model.vm = vm
        item = EnvironmentListItem.from_model(model)
        assert item.vm_name == "win10"
        assert item.os_platform == "windows"

    def test_from_model_no_vm(self):
        model = MagicMock(spec=["id", "name", "description", "hypervisor"])
        model.id = "2"
        model.name = "env2"
        model.description = None
        model.hypervisor = None
        item = EnvironmentListItem.from_model(model)
        assert item.vm_name is None
        assert item.os_platform is None
        assert item.hypervisor == "virtualbox"
        assert item.description == ""
