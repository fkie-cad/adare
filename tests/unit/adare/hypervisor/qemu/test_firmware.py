"""
Unit tests for adare.hypervisor.qemu.firmware module.
"""
import pytest
from unittest.mock import MagicMock, patch
import os
from pathlib import Path

from adare.hypervisor.qemu.firmware import (
    find_ovmf_firmware, 
    get_nvram_path_for_vm, 
    create_nvram_for_vm,
    OVMFFirmwareNotFoundError,
    OVMF_SEARCH_PATHS
)

class TestFirmware:
    
    @patch('os.path.exists')
    def test_find_ovmf_firmware_success(self, mock_exists):
        # Simulate finding the first pair in the list
        # We need to configure side_effect carefully based on calls
        # The function checks (code_path) then (vars_path)
        
        first_code = OVMF_SEARCH_PATHS[0][0]
        first_vars = OVMF_SEARCH_PATHS[0][1]
        
        def exists_side_effect(path):
            return path in [first_code, first_vars]
            
        mock_exists.side_effect = exists_side_effect
        
        code, vars_path = find_ovmf_firmware()
        assert code == first_code
        assert vars_path == first_vars
        
    @patch('os.path.exists', return_value=False)
    def test_find_ovmf_firmware_not_found(self, mock_exists):
        with pytest.raises(OVMFFirmwareNotFoundError):
            find_ovmf_firmware()

    def test_get_nvram_path_for_vm(self):
        vm_name = "test-vm"
        config_dir = Path("/tmp/qemu/vms")
        path = get_nvram_path_for_vm(vm_name, config_dir)
        assert path == "/tmp/qemu/vms/test-vm-nvram.fd"

    @patch('adare.hypervisor.qemu.firmware.find_ovmf_firmware')
    @patch('shutil.copy2')
    @patch('os.makedirs')
    @patch('os.path.exists')
    def test_create_nvram_for_vm_creates_new(self, mock_exists, mock_makedirs, mock_copy, mock_find):
        mock_find.return_value = ('code.fd', 'template.fd')
        mock_exists.return_value = False # NVRAM doesn't exist yet
        
        path = create_nvram_for_vm("test-vm", Path("/tmp/vms"))
        
        mock_makedirs.assert_called_with(Path("/tmp/vms"), exist_ok=True)
        mock_copy.assert_called_with('template.fd', str(Path("/tmp/vms/test-vm-nvram.fd")))
        assert path == str(Path("/tmp/vms/test-vm-nvram.fd"))

    @patch('adare.hypervisor.qemu.firmware.find_ovmf_firmware')
    @patch('shutil.copy2')
    @patch('os.path.exists')
    def test_create_nvram_for_vm_exists(self, mock_exists, mock_copy, mock_find):
        mock_find.return_value = ('code.fd', 'template.fd')
        mock_exists.return_value = True # Already exists
        
        create_nvram_for_vm("test-vm", Path("/tmp/vms"))
        
        mock_copy.assert_not_called()
