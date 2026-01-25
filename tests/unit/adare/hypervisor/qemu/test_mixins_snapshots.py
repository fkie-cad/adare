"""
Unit tests for adare.hypervisor.qemu.mixins.snapshots module.
"""
import pytest
from unittest.mock import MagicMock, patch, call
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
        # All calls success
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "<domain>test</domain>"
        
        with patch('pathlib.Path.mkdir'):
            with patch('tempfile.NamedTemporaryFile') as mock_temp:
                mock_temp.return_value.__enter__.return_value.name = "/tmp/fake.xml"
                success = mixin.create_external_snapshot(
                    "snap1", 
                    "/tmp/snap1.save", 
                    "/tmp/snap1.qcow2",
                    use_quiesce=False
                )
        
        assert success is True
        
        calls = mock_run.call_args_list
        # Expected sequence: save, snapshot, dumpxml, restore
        
        # 1. Save: ['virsh', 'save', ...]
        save_calls = [c for c in calls if c[0][0][1] == 'save']
        assert len(save_calls) == 1
        
        # 2. Snapshot
        snap_calls = [c for c in calls if 'snapshot-create-as' in str(c[0][0])]
        assert len(snap_calls) == 1
        
        # 3. DumpXML
        dump_calls = [c for c in calls if 'dumpxml' in str(c[0][0])]
        assert len(dump_calls) == 1
        
        # 4. Restore
        restore_calls = [c for c in calls if c[0][0][1] == 'restore']
        assert len(restore_calls) == 1
        restore_args = restore_calls[0][0][0]
        assert '--xml' in restore_args
        assert '--running' in restore_args

    @patch('subprocess.run')
    def test_create_external_snapshot_with_manual_quiesce(self, mock_run, mixin):
        # All calls return 0 (success)
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = "<domain>test</domain>"
        
        with patch('pathlib.Path.mkdir'):
             with patch('tempfile.NamedTemporaryFile') as mock_temp:
                mock_temp.return_value.__enter__.return_value.name = "/tmp/fake.xml"
                success = mixin.create_external_snapshot(
                    "snap1", 
                    "/tmp/snap1.save", 
                    "/tmp/snap1.qcow2",
                    use_quiesce=True
                )
            
        assert success is True
        
        calls = mock_run.call_args_list
        # 1. Ping
        assert any('guest-ping' in str(c[0][0]) for c in calls)
        # 2. Freeze
        assert any('domfsfreeze' in str(c[0][0]) for c in calls)
        # 3. Save
        assert any('save' in str(c[0][0]) for c in calls)
        # 4. Snapshot
        assert any('snapshot-create-as' in str(c[0][0]) for c in calls)
        # 5. Restore
        assert any('restore' in str(c[0][0]) for c in calls)
        # 6. Thaw
        assert any('domfsthaw' in str(c[0][0]) for c in calls)

    @patch('subprocess.run')
    def test_create_external_snapshot_quiesce_freeze_fail(self, mock_run, mixin):
        # Ping succeeds, Freeze fails, Save succeeds, Snapshot succeeds, Restore succeeds.
        from subprocess import CalledProcessError
        
        def side_effect(args, **kwargs):
            cmd_str = str(args)
            if 'guest-ping' in cmd_str:
                return MagicMock(returncode=0)
            elif 'domfsfreeze' in cmd_str:
                # Raise error as check=True is used for freeze
                raise CalledProcessError(1, args)
            elif 'stdout' in str(dict(kwargs)): # Basic Mock doesn't support kwargs checking nicely in side_effect usually
                 pass
            
            # Default success mock
            m = MagicMock(returncode=0)
            m.stdout = "<domain>test</domain>"
            return m
            
        mock_run.side_effect = side_effect
        
        with patch('pathlib.Path.mkdir'):
             with patch('tempfile.NamedTemporaryFile') as mock_temp:
                mock_temp.return_value.__enter__.return_value.name = "/tmp/fake.xml"
                success = mixin.create_external_snapshot(
                    "snap1", "/tmp/m", "/tmp/d", use_quiesce=True
                )
            
        assert success is True 
        
        calls = mock_run.call_args_list
        # Ensure freeze was called
        freeze_called = any('domfsfreeze' in str(c[0][0]) for c in calls)
        assert freeze_called
        
        # Ensure thaw was NOT called
        thaw_called = any('domfsthaw' in str(c[0][0]) for c in calls)
        assert not thaw_called

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
