"""
Unit tests for adare.hypervisor.qemu.mixins.networking module.
"""
import pytest
from unittest.mock import MagicMock
from pathlib import Path

from adare.hypervisor.qemu.mixins.networking import NetworkingMixin
from adare.hypervisor.qemu.models import QEMUVMConfig, PortForwardingRule, SharedFolderConfig
from adare.hypervisor.exceptions import HypervisorException

class MockVM(NetworkingMixin):
    """Mock VM class for testing networking mixin."""
    def __init__(self):
        self.vm_name = "test-vm"
        self.config = MagicMock(spec=QEMUVMConfig)
        self.config.port_forwarding_rules = {}
        self.config.virtiofs_shares = []
        self.config.virtiofs_enabled = False
        self._save_vm_config = MagicMock()
        self.log = MagicMock()
        # Mock get_state to return stopped by default
        self.get_state = MagicMock(return_value="stopped")

@pytest.fixture
def vm():
    return MockVM()

class TestNetworkingMixin:
    """Tests for NetworkingMixin methods."""

    @pytest.mark.asyncio
    async def test_add_port_forwarding(self, vm):
        """Test adding a port forwarding rule."""
        await vm.add_port_forwarding(
            name="ssh",
            protocol="tcp",
            host_port=2222,
            guest_port=22
        )
        
        assert "ssh" in vm.config.port_forwarding_rules
        rule = vm.config.port_forwarding_rules["ssh"]
        assert rule["protocol"] == "tcp"
        assert rule["host_port"] == 2222

    @pytest.mark.asyncio
    async def test_add_port_forwarding_conflict(self, vm):
        """Test errors when adding duplicate rules."""
        # Pre-populate rules in config dict directly since mocks don't hold state automatically unless we do it
        vm.config.port_forwarding_rules = {
            "ssh": {"name": "ssh", "protocol": "tcp", "host_port": 2222, "guest_port": 22}
        }
        
        # The mixin checks vm.config.port_forwarding_rules
        # But wait, add_port_forwarding returns int (0 success, 1 fail). It logs warning on dupe.
        # It does NOT raise HypervisorException in this implementation!
        
        result = await vm.add_port_forwarding("ssh", "tcp", 2223, 23, silent=True)
        assert result == 1 # Exists

    @pytest.mark.asyncio
    async def test_remove_port_forwarding(self, vm):
        """Test removing a port forwarding rule."""
        vm.config.port_forwarding_rules = {
            "ssh": {"name": "ssh", "protocol": "tcp", "host_port": 2222, "guest_port": 22}
        }
        
        await vm.remove_port_forwarding("ssh")
        
        assert "ssh" not in vm.config.port_forwarding_rules

    @pytest.mark.asyncio
    async def test_list_port_forwarding_rules(self, vm):
        """Test listing rules."""
        vm.config.port_forwarding_rules = {
            "ssh": {"name": "ssh", "protocol": "tcp", "host_port": 2222, "guest_port": 22}
        }
        
        rules = await vm.list_port_forwarding_rules()
        assert "ssh" in rules
        assert isinstance(rules["ssh"], PortForwardingRule)

    @pytest.mark.asyncio
    async def test_add_shared_folder(self, vm):
        """Test adding a shared folder."""
        vm.config.virtiofs_shares = []
        host_path = Path("/tmp/share")
        
        await vm.add_shared_folder(
            name="myshare",
            host_path=host_path,
            readonly=True
        )
        
        assert len(vm.config.virtiofs_shares) == 1
        share = vm.config.virtiofs_shares[0]
        # It stores dicts
        assert share['tag'] == "myshare"
        assert share['host_path'] == str(host_path)
        assert share['readonly'] is True

    @pytest.mark.asyncio
    async def test_remove_shared_folder(self, vm):
        """Test removing shared folder."""
        share = {'tag': "myshare", 'host_path': "/tmp", 'readonly': False}
        vm.config.virtiofs_shares = [share]
        
        await vm.remove_shared_folder("myshare")
        
        assert len(vm.config.virtiofs_shares) == 0
        
    @pytest.mark.asyncio
    async def test_remove_all_shared_folders(self, vm):
        """Test clearing all shared folders."""
        vm.config.virtiofs_shares = [
            {'tag': "s1", 'host_path': "/tmp/1"},
            {'tag': "s2", 'host_path': "/tmp/2"}
        ]
        vm.config.virtiofs_enabled = True
        
        await vm.remove_all_shared_folders()
        
        assert len(vm.config.virtiofs_shares) == 0
        assert vm.config.virtiofs_enabled is False
