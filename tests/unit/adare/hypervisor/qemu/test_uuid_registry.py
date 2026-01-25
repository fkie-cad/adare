"""
Unit tests for adare.hypervisor.qemu.utilities.uuid_registry module.
"""
import pytest
from unittest.mock import MagicMock, patch, mock_open
import json

from adare.hypervisor.qemu.utilities.uuid_registry import QEMUVMRegistry
from adare.hypervisor.exceptions import VMNotFoundException

class TestQEMUVMRegistry:
    
    @patch('pathlib.Path.exists', return_value=True)
    @patch('builtins.open', new_callable=mock_open, read_data='{"vm_name": "test-vm", "uuid": "1234", "guest_os": "linux"}')
    @patch('adare.config.get_vm_credentials', return_value=("user", "pass"))
    @patch('adare.hypervisor.qemu.manager.QEMUManager')
    @patch('adare.hypervisor.qemu.vm.QEMUVM')
    def test_get_vm_by_name_success(self, mock_qemuvm, mock_manager, mock_creds, mock_file, mock_exists):
        # Setup mock VM instance
        mock_vm_instance = MagicMock()
        mock_vm_instance.vm_name = "test-vm"
        mock_vm_instance.guest_os = "linux"
        mock_qemuvm.return_value = mock_vm_instance
        
        vm = QEMUVMRegistry.get_vm_by_name("test-vm")
        assert vm.vm_name == "test-vm"
        assert vm.guest_os == "linux"

    @patch('pathlib.Path.exists', return_value=False)
    def test_get_vm_by_name_not_found(self, mock_exists):
        with pytest.raises(VMNotFoundException):
            QEMUVMRegistry.get_vm_by_name("nonexistent")

    @patch('glob.glob')
    @patch('pathlib.Path.exists', return_value=True)
    def test_get_vm_name_by_uuid_found(self, mock_exists, mock_glob):
        mock_glob.return_value = ["/path/to/test-vm.json"]
        
        with patch('builtins.open', new_callable=mock_open, read_data='{"vm_name": "test-vm", "uuid": "1234"}'):
             name = QEMUVMRegistry.get_vm_name_by_uuid("1234")
             assert name == "test-vm"

    @patch('glob.glob')
    @patch('pathlib.Path.exists', return_value=True)
    def test_get_vm_name_by_uuid_not_found(self, mock_exists, mock_glob):
        mock_glob.return_value = ["/path/to/other.json"]
        
        with patch('builtins.open', new_callable=mock_open, read_data='{"vm_name": "other", "uuid": "5678"}'):
             name = QEMUVMRegistry.get_vm_name_by_uuid("1234")
             assert name is None
