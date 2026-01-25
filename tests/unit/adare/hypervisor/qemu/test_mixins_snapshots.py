"""
Unit tests for adare.hypervisor.qemu.mixins.snapshots module.
"""
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

from adare.hypervisor.qemu.mixins.snapshots import SnapshotMixin
from adare.hypervisor.qemu.models import QEMUVMConfig

class TestSnapshotMixin:
    
    @pytest.fixture
    def mixin(self):
        mixin = SnapshotMixin()
        mixin.vm_name = "test-vm"
        
        # Mock config
        mixin.config = MagicMock(spec=QEMUVMConfig)
        mixin.config.disk_path = "/var/lib/libvirt/images/test-vm.qcow2"
        
        # Mock state getter
        mixin.get_state = MagicMock(return_value="running")
        
        return mixin

    def test_get_snapshot_storage_dir(self, mixin):
        d = mixin._get_snapshot_storage_dir()
        assert d == Path("/var/lib/libvirt/images/test-vm/snapshots")

    @patch('subprocess.run')
    def test_create_external_snapshot_success(self, mock_run, mixin):
        mock_run.return_value.returncode = 0
        
        with patch('pathlib.Path.mkdir'):
            success = mixin.create_external_snapshot(
                "snap1", 
                "/tmp/snap1.save", 
                "/tmp/snap1.qcow2",
                use_quiesce=False
            )
        
        assert success is True
        mock_run.assert_called()
        args = mock_run.call_args[0][0]
        assert 'snapshot-create-as' in args
        assert '--memspec' in args
        assert '--diskspec' in args

    @patch('subprocess.run')
    @patch('os.path.exists', return_value=True)
    def test_restore_external_snapshot_success(self, mock_exists, mock_run, mixin):
        # Mock sequence: destroy, virt-xml, restore
        mock_run.side_effect = [
            MagicMock(returncode=0), # destroy
            MagicMock(returncode=0), # virt-xml
            MagicMock(returncode=0)  # restore
        ]
        
        success = mixin.restore_external_snapshot("/tmp/mem", "/tmp/disk")
        
        assert success is True
        assert mock_run.call_count == 3
        # Check calls?
        calls = mock_run.call_args_list
        assert calls[1][0][0][1] == "test-vm" # virt-xml ...
        assert calls[2][0][0][1] == "restore" # virsh restore

    @patch('subprocess.run')
    @patch('os.remove')
    @patch('os.path.exists')
    def test_delete_external_snapshot_success(self, mock_exists, mock_remove, mock_run, mixin):
        # Mock metadata delete fails (expected for external), but file delete succeeds
        mock_run.return_value.returncode = 1
        mock_run.return_value.stderr = "external disk snapshots not supported"
        
        # Files exist initially, then they are removed.
        # Logic checks exists calling (disk_path) and (memory_path).
        # We need to ensure that subsequent checks return False.
        # But os.remove is called in between.
        # Let's make exists return True first few times, then False?
        # The code checks: if os.path.exists(mem): remove(mem); if memory_deleted and os.path.exists(mem): fail
        
        # We can implement a side effect based on a mutable set of existing files
        existing_files = {"/tmp/mem", "/tmp/disk"}
        
        def exists_side_effect(path):
            return path in existing_files
            
        def remove_side_effect(path):
            if path in existing_files:
                existing_files.remove(path)
        
        mock_exists.side_effect = exists_side_effect
        mock_remove.side_effect = remove_side_effect
        
        success = mixin.delete_external_snapshot("snap1", "/tmp/mem", "/tmp/disk")
        
        assert success is True
        assert mock_remove.call_count == 2 # mem and disk
