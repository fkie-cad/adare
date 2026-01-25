
import pytest
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path
import json
from adare.hypervisor.qemu.mixins.configuration import ConfigurationMixin
from adare.hypervisor.qemu.models import QEMUVMConfig

@pytest.fixture
def config_mixin():
    mixin = ConfigurationMixin()
    mixin.vm_name = "test-vm"
    mixin.executables = MagicMock()
    mixin.executables.qemu_img = "qemu-img"
    mixin.guest_os = "linux"
    mixin._external_disk_path = None
    mixin.cpus = 2
    mixin.ram = 2048
    mixin.machine = "pc"
    mixin.accel = "kvm"
    mixin.drive_format = "qcow2"
    return mixin

class TestConfigurationMixin:

    @patch('subprocess.run')
    def test_detect_disk_format_static_success(self, mock_run):
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = '{"format": "qcow2"}'
        
        fmt = ConfigurationMixin._detect_disk_format_static(Path("/tmp/disk.img"))
        
        assert fmt == "qcow2"
        mock_run.assert_called_once()

    @patch('subprocess.run')
    def test_detect_disk_format_static_fail(self, mock_run):
        mock_run.return_value.returncode = 1
        
        with pytest.raises(Exception): # HypervisorException
             ConfigurationMixin._detect_disk_format_static(Path("/tmp/disk.img"))

    def test_detect_disk_format_ova(self):
        fmt = ConfigurationMixin._detect_disk_format_static(Path("/tmp/image.ova"))
        assert fmt == "ova"

    @patch('adare.hypervisor.qemu.mixins.configuration.get_boot_mode_for_os')
    @patch('adare.hypervisor.qemu.mixins.configuration.QEMUVMConfig')
    def test_load_or_create_vm_config_new(self, mock_config_cls, mock_boot_mode, config_mixin):
        with patch.object(ConfigurationMixin, '_get_vm_config_path') as mock_path:
            mock_path.return_value.exists.return_value = False
            mock_boot_mode.return_value = "bios"
            
            # Setup save mocking
            config_mixin._save_vm_config_obj = MagicMock()
            
            # Act
            config = config_mixin._load_or_create_vm_config()
            
            # Assert
            mock_config_cls.assert_called_once()
            config_mixin._save_vm_config_obj.assert_called_once()

    def test_save_vm_config_obj_stripped_overlay(self, config_mixin):
        config = MagicMock()
        config.to_dict.return_value = {
            "disk_path": "/tmp/test-vm-base-overlay-123.qcow2",
            "vm_name": "test-vm"
        }
        
        # Mock strip logic
        config_mixin._strip_overlay_suffixes = lambda x: x.replace("-overlay-123", "")
        
        with patch('builtins.open', mock_open()) as mock_file:
            with patch('json.dump') as mock_json:
                with patch.object(ConfigurationMixin, '_get_vm_config_path', return_value=Path("/tmp/config.json")):
                    config_mixin._save_vm_config_obj(config)
                    
                    # Verify disk path was replaced
                    args, _ = mock_json.call_args
                    saved_dict = args[0]
                    # Expected: /tmp/test-vm-base.qcow2 -> strips -overlay...
                    # Logic in source: remove -base too
                    assert saved_dict['disk_path'] == "/tmp/test-vm.qcow2"
