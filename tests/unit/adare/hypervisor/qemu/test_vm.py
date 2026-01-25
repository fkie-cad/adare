"""
Unit tests for adare.hypervisor.qemu.vm module.
"""
import sys
import unittest
from unittest.mock import MagicMock, patch, AsyncMock
import pytest
from pathlib import Path

# Mock libvirt before importing modules that might use it
mock_libvirt = MagicMock()
class MockLibvirtError(Exception):
    pass
mock_libvirt.libvirtError = MockLibvirtError
mock_libvirt.VIR_DOMAIN_RUNNING = 1
mock_libvirt.VIR_DOMAIN_SHUTOFF = 5
mock_libvirt.VIR_DOMAIN_UNDEFINE_MANAGED_SAVE = 1
mock_libvirt.VIR_DOMAIN_UNDEFINE_SNAPSHOTS_METADATA = 2
mock_libvirt.VIR_DOMAIN_UNDEFINE_NVRAM = 4

sys.modules['libvirt'] = mock_libvirt

from adare.hypervisor.qemu.vm import QEMUVM
from adare.hypervisor.qemu.models import QEMUVMConfig


@pytest.fixture
def mock_manager():
    async def run_async_side_effect(func):
        return await func()

    manager = MagicMock()
    manager.run_async = AsyncMock(side_effect=run_async_side_effect)
    return manager


@pytest.fixture
def mock_executables():
    execs = MagicMock()
    execs.qemu_system = "/usr/bin/qemu-system-x86_64"
    execs.qemu_img = "/usr/bin/qemu-img"
    return execs


@pytest.fixture
def mock_config():
    config = MagicMock(spec=QEMUVMConfig)
    config.vm_name = "test-vm"
    config.uuid = "1234-uuid"
    config.guest_os = "linux"
    config.disk_path = "/tmp/test.qcow2"
    config.cpus = 2
    config.ram = 2048
    config.machine = "pc"
    config.accel = "kvm"
    config.drive_format = "qcow2"
    config.boot_mode = "bios"
    config.network = "user"
    config.port_forwarding_rules = {}
    config.qmp_socket_path = "/tmp/qmp.sock"
    config.guest_agent_socket_path = "/tmp/ga.sock"
    config.pid_file_path = "/tmp/vm.pid"
    config.serial_console_log_path = None
    config.qemu_debug_log_path = None
    config.display_enabled = False
    config.vnc_port = None
    
    # Defaults for new fields
    config.virtiofs_enabled = True
    config.virtiofs_shares = []
    
    return config


class TestQEMUVMInitialization:
    """Tests for QEMUVM initialization."""

    @patch('adare.hypervisor.qemu.vm.QEMUVM._load_or_create_vm_config')
    def test_init_sets_attributes(self, mock_load_config, mock_manager, mock_executables, mock_config):
        """Test that __init__ sets attributes correctly."""
        mock_load_config.return_value = mock_config

        vm = QEMUVM(
            vm_name="test-vm",
            guest_os="linux",
            manager=mock_manager,
            username="user",
            password="password",
            executables=mock_executables,
            cpus=4,
            ram=4096
        )

        assert vm.vm_name == "test-vm"
        assert vm.guest_os == "linux"
        assert vm.manager == mock_manager
        assert vm.executables == mock_executables
        assert vm.cpus == 4
        assert vm.ram == 4096
        assert vm.config == mock_config


class TestQEMUCommandBuilding:
    """Tests for _build_qemu_command."""

    @patch('adare.hypervisor.qemu.vm.QEMUVM._load_or_create_vm_config')
    def test_build_command_basic(self, mock_load_config, mock_manager, mock_executables, mock_config):
        """Test basic QEMU command generation."""
        mock_load_config.return_value = mock_config
        
        vm = QEMUVM(
            vm_name="test-vm",
            guest_os="linux",
            manager=mock_manager,
            username="user",
            password="pass",
            executables=mock_executables
        )
        
        # Ensure HYPERVISOR_CONFIGS is mocked if needed, but the code imports it inside method
        # We might need to patch it if it's not available in environment
        # But let's see if defaults work.
        
        with patch('adare.config.HYPERVISOR_CONFIGS', {}):
             cmd = vm._build_qemu_command()

        assert cmd[0] == "/usr/bin/qemu-system-x86_64"
        assert "-name" in cmd
        assert cmd[cmd.index("-name") + 1] == "test-vm"
        assert "-m" in cmd
        assert cmd[cmd.index("-m") + 1] == "2048"
        
        # Check disk
        assert any(f"file={mock_config.disk_path}" in arg for arg in cmd)

    @patch('adare.hypervisor.qemu.vm.QEMUVM._load_or_create_vm_config')
    def test_build_command_uefi(self, mock_load_config, mock_manager, mock_executables, mock_config):
        """Test QEMU command with UEFI enabled."""
        mock_config.boot_mode = 'uefi'
        mock_load_config.return_value = mock_config
        
        vm = QEMUVM(
            vm_name="test-vm",
            guest_os="linux",
            manager=mock_manager,
            username="user",
            password="pass",
            executables=mock_executables
        )

        with patch('adare.hypervisor.qemu.firmware.find_ovmf_firmware', return_value=('/usr/share/ovmf/OVMF_CODE.fd', '/usr/share/ovmf/OVMF_VARS.fd')), \
             patch('adare.hypervisor.qemu.firmware.create_nvram_for_vm', return_value='/tmp/nvram.fd'), \
             patch('adare.config.HYPERVISOR_CONFIGS', {}):
            
            cmd = vm._build_qemu_command()
        
        # Should use q35 for UEFI
        machine_arg = next(arg for arg in cmd if arg.startswith("q35"))
        assert "q35" in machine_arg
        
        # Should have pflash drives
        assert any("if=pflash" in arg and "OVMF_CODE.fd" in arg for arg in cmd)
        assert any("if=pflash" in arg and "/tmp/nvram.fd" in arg for arg in cmd)

    @patch('adare.hypervisor.qemu.vm.QEMUVM._load_or_create_vm_config')
    def test_build_command_port_forwarding(self, mock_load_config, mock_manager, mock_executables, mock_config):
        """Test QEMU command with port forwarding."""
        mock_config.port_forwarding_rules = {
            "ssh": {"protocol": "tcp", "host_port": 2222, "guest_port": 22},
            "web": {"protocol": "tcp", "host_port": 8080, "guest_port": 80}
        }
        mock_load_config.return_value = mock_config
        
        vm = QEMUVM(
            vm_name="test-vm",
            guest_os="linux",
            manager=mock_manager,
            username="user",
            password="pass",
            executables=mock_executables
        )
        
        with patch('adare.config.HYPERVISOR_CONFIGS', {}):
            cmd = vm._build_qemu_command()
            
        # Check netdev argument
        netdev_index = cmd.index("-netdev")
        netdev_arg = cmd[netdev_index + 1]
        
        assert "user,id=net0" in netdev_arg
        assert "hostfwd=tcp::2222-:22" in netdev_arg
        assert "hostfwd=tcp::8080-:80" in netdev_arg


@pytest.mark.asyncio
class TestVMStartStop:
    """Tests for start and stop validation."""

    @patch('adare.hypervisor.qemu.vm.QEMUVM._load_or_create_vm_config')
    @patch('adare.hypervisor.qemu.vm.QEMUVM._define_libvirt_domain')
    @patch('os.path.exists', return_value=True)  # Disk exists
    async def test_start_success(self, mock_exists, mock_define_domain, mock_load_config, mock_manager, mock_executables, mock_config):
        """Test successful VM start."""
        mock_load_config.return_value = mock_config
        
        # Mock domain
        mock_domain = MagicMock()
        mock_domain.state.return_value = (1, 1) # VIR_DOMAIN_RUNNING = 1
        mock_domain.isActive.return_value = True
        mock_define_domain.return_value = mock_domain
        
        vm = QEMUVM(
            vm_name="test-vm",
            guest_os="linux",
            manager=mock_manager,
            username="user",
            password="pass",
            executables=mock_executables
        )
        
        # Mock initial state to be SHUTOFF (5) or something not RUNNING
        # The code checks state before starting.
        # Let's side_effect state() to return SHUTOFF first, then RUNNING
        mock_domain.state.side_effect = [(5, 0), (1, 1)] # 5=SHUTOFF, 1=RUNNING
        
        with patch('adare.hypervisor.qemu.libvirt_stderr_redirect.LibvirtStderrRedirect'):
             ret = await vm.start()
             
        assert ret == 0
        mock_define_domain.assert_called_once()
        mock_domain.create.assert_called_once()
        
    @patch('adare.hypervisor.qemu.vm.QEMUVM._load_or_create_vm_config')
    async def test_stop_graceful(self, mock_load_config, mock_manager, mock_executables, mock_config):
        """Test graceful shutdown."""
        mock_load_config.return_value = mock_config
        
        vm = QEMUVM(
            vm_name="test-vm",
            guest_os="linux",
            manager=mock_manager,
            username="user",
            password="pass",
            executables=mock_executables
        )
        
        # Mock libvirt connection and domain lookups
        mock_conn = MagicMock()
        mock_domain = MagicMock()
        mock_conn.lookupByName.return_value = mock_domain
        
        # Setup state transitions: RUNNING -> (shutdown called) -> SHUTOFF
        mock_domain.state.side_effect = [(1, 1), (5, 0)] 
        
        with patch.object(vm, '_get_libvirt_connection', return_value=mock_conn), \
             patch('adare.hypervisor.qemu.libvirt_stderr_redirect.LibvirtStderrRedirect'):
            
            ret = await vm.stop()
            
        assert ret == 0
        mock_domain.shutdown.assert_called_once()
        mock_domain.destroy.assert_not_called()

    @patch('adare.hypervisor.qemu.vm.QEMUVM._load_or_create_vm_config')
    async def test_stop_force(self, mock_load_config, mock_manager, mock_executables, mock_config):
        """Test forced shutdown."""
        mock_load_config.return_value = mock_config
        
        vm = QEMUVM(
            vm_name="test-vm",
            guest_os="linux",
            manager=mock_manager,
            username="user",
            password="pass",
            executables=mock_executables
        )
        
        mock_conn = MagicMock()
        mock_domain = MagicMock()
        mock_conn.lookupByName.return_value = mock_domain
        mock_domain.state.return_value = (1, 1) # Running
        
        with patch.object(vm, '_get_libvirt_connection', return_value=mock_conn), \
             patch('adare.hypervisor.qemu.libvirt_stderr_redirect.LibvirtStderrRedirect'):
            
            ret = await vm.stop(force=True)
            
        assert ret == 0
        mock_domain.destroy.assert_called_once()
