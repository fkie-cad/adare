"""
Unit tests for adare.hypervisor.qemu.mixins.disk module.
"""
import pytest
import sys
import os
from unittest.mock import MagicMock, patch, call, AsyncMock
from pathlib import Path

# Mock adare.backend.vm.commands to avoid import errors
mock_backend_vm_commands = MagicMock()
mock_backend_vm_commands._is_vm_managed = MagicMock(return_value=False)
sys.modules['adare.backend.vm.commands'] = mock_backend_vm_commands
sys.modules['adare.backend.vm'] = MagicMock()
sys.modules['adare.backend.vm'].commands = mock_backend_vm_commands

from adare.hypervisor.qemu.mixins.disk import DiskManagementMixin
from adare.hypervisor.exceptions import HypervisorException
from adare.hypervisor.qemu.models import QEMUVMConfig

class MockVM(DiskManagementMixin):
    """Mock VM class for testing disk mixin."""
    def __init__(self):
        self.vm_name = "test-vm"
        self.config = MagicMock(spec=QEMUVMConfig)
        self.config.disk_path = "/var/lib/adare/images/test-vm.qcow2"
        self.executables = MagicMock()
        self.executables.qemu_img = "/usr/bin/qemu-img"
        self.manager = MagicMock()
        self._external_disk_path = None # Required by mixin

@pytest.fixture
def vm():
    return MockVM()

class TestDiskManagementMixin:
    """Tests for DiskManagementMixin methods."""

    def test_strip_overlay_suffixes(self):
        """Test ULID suffix stripping."""
        base = "Ubuntu-22.04"
        ulid = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
        overlay = f"{base}-overlay-{ulid}"
        assert DiskManagementMixin._strip_overlay_suffixes(overlay) == base
        assert DiskManagementMixin._strip_overlay_suffixes(base) == base

    def test_get_base_disk_path_external(self, vm):
        """Test getting base disk path for external VM."""
        vm._external_disk_path = "/home/user/my-vm.qcow2"
        assert vm.get_base_disk_path() == "/home/user/my-vm.qcow2"

    @patch("os.path.exists")
    def test_get_base_disk_path_managed(self, mock_exists, vm):
        """Test getting base disk path for managed VM."""
        vm._external_disk_path = None
        vm.config.disk_path = "/images/test-vm.qcow2"
        # Since it just does string manipulation for managed VMs in the code:
        # return str(current_disk.parent / f"{current_disk.stem}-base{current_disk.suffix}")
        assert vm.get_base_disk_path() == "/images/test-vm-base.qcow2"

    def test_get_true_base_disk_external(self, vm):
        """Test _get_true_base_disk for external VM."""
        vm._external_disk_path = "/ext/vm.qcow2"
        with patch("pathlib.Path.exists", return_value=True, autospec=True):
            assert vm._get_true_base_disk() == "/ext/vm.qcow2"

    def test_get_true_base_disk_simple(self, vm):
        """Test _get_true_base_disk with standard base path."""
        vm.config.disk_path = "/images/test-vm-base.qcow2"
        
        # We need autospec=True so side_effect receives 'self' (the path instance)
        with patch("pathlib.Path.exists", autospec=True) as mock_exists:
            def side_effect(path_obj):
                path_str = str(path_obj)
                # We want Priority 2 (test-vm-base-base) to FAIL
                if path_str.endswith("test-vm-base-base.qcow2"):
                    return False
                # We want Fallback (test-vm-base) to SUCCEED
                if path_str.endswith("test-vm-base.qcow2"):
                    return True
                return False
            
            mock_exists.side_effect = side_effect
            
            assert vm._get_true_base_disk() == "/images/test-vm-base.qcow2"

    def test_get_overlay_disk_path(self, vm):
        """Test overlay path generation."""
        vm.config.disk_path = "/images/VM-base.qcow2"
        exp_id = "01ABC"
        
        with patch("pathlib.Path.exists", return_value=True, autospec=True): # Base exists
             path = vm.get_overlay_disk_path(exp_id)
        
        # Base stem: VM-base -> stripped -> VM
        # Overlay: VM-overlay-01ABC.qcow2
        assert path == "/images/VM-overlay-01ABC.qcow2"

    @pytest.mark.asyncio
    async def test_create_overlay_disk(self, vm):
        """Test creating an overlay disk."""
        exp_id = "01ABC"
        base_path = "/images/VM-base.qcow2"
        overlay_path = "/images/VM-overlay-01ABC.qcow2"
        
        # Mock dependencies
        vm._get_true_base_disk = MagicMock(return_value=base_path)
        vm._cleanup_orphaned_overlays = AsyncMock() # Important: Mock async method
        vm.get_overlay_disk_path = MagicMock(return_value=overlay_path)
        
        # Mock shutil.disk_usage
        mock_usage = MagicMock()
        mock_usage.free = 20 * 1024**3 # 20GB
        
        # Mock subproccess
        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"", b"")
        mock_proc.returncode = 0
        
        with patch("shutil.disk_usage", return_value=mock_usage), \
             patch("asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec, \
             patch("pathlib.Path.exists", return_value=True, autospec=True):
            
            result = await vm.create_overlay_disk(exp_id)
            assert result == overlay_path
            
            # Verify qemu-img command
            mock_exec.assert_called_once()
            args = mock_exec.call_args[0]
            assert args[0] == "/usr/bin/qemu-img"
            assert args[1] == "create"
            assert "-b" in args
            assert "VM-base.qcow2" in args # Relative path check logic

    @pytest.mark.asyncio
    async def test_cleanup_overlay_disk(self, vm):
        """Test cleanup of overlay disk."""
        vm.get_overlay_disk_path = MagicMock(return_value="/tmp/overlay.qcow2")
        
        with patch("os.remove") as mock_remove, \
             patch("pathlib.Path.exists", return_value=True, autospec=True):
            
            await vm.cleanup_overlay_disk("exp1")
            mock_remove.assert_called_with("/tmp/overlay.qcow2")

    @pytest.mark.asyncio
    async def test_cleanup_orphaned_overlays(self, vm):
        """Test cleaning up old overlays."""
        vm._get_true_base_disk = MagicMock(return_value="/images/VM-base.qcow2")
        vm.get_overlay_disk_path = MagicMock(return_value="/images/VM-overlay-CURRENT.qcow2")
        vm._external_disk_path = None
        
        # files to be found
        f1 = MagicMock(spec=Path)
        f1.name = "VM-overlay-OLD.qcow2"
        f1.__eq__ = lambda s, o: str(s) == str(o) # Basic eq
        
        # We need Path.glob to return these
        with patch("pathlib.Path.glob", return_value=[f1], autospec=True):
             # We need f1.unlink() to be callable
             await vm._cleanup_orphaned_overlays("CURRENT")
             
             f1.unlink.assert_called_once()
