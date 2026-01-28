import unittest
from unittest.mock import MagicMock, patch, call
from adare.hypervisor.qemu.mixins.snapshots import SnapshotMixin
from adare.hypervisor.qemu.models import QEMUVMConfig
from pathlib import Path

class TestSnapshotMixin(unittest.TestCase):
    def setUp(self):
        self.mixin = SnapshotMixin()
        self.mixin.vm_name = "test-vm"
        self.mixin.config = MagicMock(spec=QEMUVMConfig)
        self.mixin.config.disk_path = "/path/to/test-vm.qcow2"
        self.mixin.config.virtiofs_enabled = True
        self.mixin.config.virtiofs_shares = [{'tag': 'test', 'guest_mount': '/mnt', 'host_path': '/host'}]
        # Initialize _libvirt_domain as None effectively mocking a detached state or initial state
        self.mixin._libvirt_domain = None 
        self.mixin.machine = 'pc' # Add missing machine attribute
        # Mock _get_libvirt_connection to return a mock connection
        self.mock_conn = MagicMock()
        self.mixin._get_libvirt_connection = MagicMock(return_value=self.mock_conn)
        
        # Mock helper methods to avoid side effects
        self.mixin._attach_virtiofs_shares = MagicMock(return_value=True)
        self.mixin._refresh_guest_mounts = MagicMock()
        self.mixin._path_discovery_attempted = True
        self.mixin._cached_guest_path = "/bin"

    @patch('subprocess.run')
    @patch('os.path.exists')
    @patch('adare.hypervisor.qemu.libvirt_xml.generate_virtiofs_xml_element')
    @patch('xml.etree.ElementTree.tostring')
    def test_restore_external_snapshot_refreshes_domain(self, mock_tostring, mock_gen_xml, mock_exists, mock_run):
        # Setup mocks
        mock_exists.return_value = True
        
        # Mock subprocess calls
        mock_destroy = MagicMock()
        mock_destroy.returncode = 0
        
        mock_virt_xml = MagicMock()
        mock_virt_xml.returncode = 0
        
        mock_restore = MagicMock()
        mock_restore.returncode = 0
        
        mock_run.side_effect = [mock_destroy, mock_virt_xml, mock_restore]

        # Call the method
        memory_path = "/path/to/mem.save"
        disk_path = "/path/to/disk.qcow2"
        
        result = self.mixin.restore_external_snapshot(memory_path, disk_path)

        # Verification
        self.assertTrue(result)
        
        # KEY CHECK: Verify lookupByName was called to refresh the domain object
        self.mock_conn.lookupByName.assert_called_with("test-vm")
        
        # Verify checking existence of files
        mock_exists.assert_any_call(memory_path)
        mock_exists.assert_any_call(disk_path)
        
        # Verify correct commands executed
        # 1. destroy
        # 2. virt-xml edit
        # 3. restore
        self.assertEqual(mock_run.call_count, 3)
        mock_run.assert_has_calls([
            call(['virsh', 'destroy', 'test-vm'], capture_output=True, text=True, check=False),
            call(['virt-xml', 'test-vm', '--edit', '--disk', f'path={disk_path}'], capture_output=True, text=True, check=False),
            call(['virsh', 'restore', memory_path], capture_output=True, text=True, check=False)
        ])
        
        # Verify cache invalidation
        self.assertFalse(self.mixin._path_discovery_attempted)
        self.assertIsNone(self.mixin._cached_guest_path)
        
        # Verify re-attachment logic
        self.mixin._attach_virtiofs_shares.assert_called()
        self.mixin._refresh_guest_mounts.assert_called()

if __name__ == '__main__':
    unittest.main()
