"""
Unit tests for adare.hypervisor.qemu.manager module.
"""
import sys
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from pathlib import Path

# Mock libvirt
mock_libvirt = MagicMock()
class MockLibvirtError(Exception):
    pass
mock_libvirt.libvirtError = MockLibvirtError
sys.modules['libvirt'] = mock_libvirt

# Mock adare.backend.vm.commands to avoid import errors
mock_backend_vm_commands = MagicMock()
mock_backend_vm_commands._is_vm_managed = MagicMock(return_value=False)
sys.modules['adare.backend.vm.commands'] = mock_backend_vm_commands
sys.modules['adare.backend.vm'] = MagicMock()
sys.modules['adare.backend.vm'].commands = mock_backend_vm_commands

from adare.hypervisor.qemu.manager import QEMUManager
from adare.hypervisor.exceptions import VMImportException, HypervisorException


@pytest.fixture
def mock_shutil_which():
    with patch("shutil.which", return_value="/usr/bin/guestfish") as mock:
        yield mock


class TestQEMUManagerInitialization:
    """Tests for QEMUManager initialization."""

    def test_init_success(self, mock_shutil_which):
        """Test successful initialization with mocked dependencies."""
        with patch("adare.config.HYPERVISOR_CONFIGS", {'qemu': {'use_libvirt': True, 'libvirt_uri': 'test:///default'}}), \
             patch("libvirt.open") as mock_open:
            
            manager = QEMUManager()
            
            assert manager.default_machine == 'pc'
            assert manager.default_accel == 'kvm'
            mock_open.assert_called_once_with('test:///default')
            assert manager.libvirt_conn is not None

    def test_init_without_libvirt(self, mock_shutil_which):
        """Test initialization with use_libvirt=False."""
        with patch("adare.config.HYPERVISOR_CONFIGS", {'qemu': {'use_libvirt': False}}):
            manager = QEMUManager()
            assert manager.libvirt_conn is None

    def test_init_libvirt_failure(self, mock_shutil_which):
        """Test initialization failure when libvirt cannot connect."""
        with patch("adare.config.HYPERVISOR_CONFIGS", {'qemu': {'use_libvirt': True}}), \
             patch("libvirt.open", side_effect=Exception("Connection failed")):
            
            with pytest.raises(HypervisorException) as excinfo:
                QEMUManager()
            assert "Failed to connect to libvirt daemon" in str(excinfo.value)

    def test_init_cleanup(self, mock_shutil_which):
        """Test __del__ cleans up connection."""
        with patch("adare.config.HYPERVISOR_CONFIGS", {'qemu': {'use_libvirt': True}}), \
             patch("libvirt.open") as mock_open:
            
            mock_conn = MagicMock()
            mock_open.return_value = mock_conn
            
            manager = QEMUManager()
            manager.__del__()
            
            mock_conn.close.assert_called_once()


class TestQEMUManagerExecution:
    """Tests for run and run_async methods."""
    
    @pytest.fixture
    def manager(self, mock_shutil_which):
        with patch("adare.config.HYPERVISOR_CONFIGS", {'qemu': {'use_libvirt': False}}):
            return QEMUManager()

    @patch("queue.Queue")
    def test_run_sync(self, mock_queue_cls, manager):
        """Test synchronous run method queues command."""
        # Setup mock queue
        mock_result_queue = MagicMock()
        mock_queue_cls.return_value = mock_result_queue
        
        # Mock getting result
        mock_result_queue.get.return_value = ("Success", None)
        
        def test_func():
            return "Success"
            
        result = manager.run(test_func)
        
        assert result == "Success"
        # Verify it was put in main command queue
        assert manager._cmd_queue.qsize() == 1 or manager._cmd_queue.put.called

    @pytest.mark.asyncio
    async def test_run_async(self, manager):
        """Test asynchronous run_async method."""
        async def async_func(x):
            return x * 2
            
        result = await manager.run_async(async_func, 21)
        assert result == 42
        
    @pytest.mark.asyncio
    async def test_run_async_exception(self, manager):
        """Test run_async propagates exceptions."""
        async def async_fail():
            raise ValueError("Async Error")
            
        with pytest.raises(ValueError, match="Async Error"):
            await manager.run_async(async_fail)


@pytest.mark.asyncio
class TestVMImport:
    """Tests for import_vm_async."""
    
    @pytest.fixture
    def manager(self, mock_shutil_which):
        with patch("adare.config.HYPERVISOR_CONFIGS", {'qemu': {'use_libvirt': False}}), \
             patch("adare.hypervisor.executable_manager.ExecutableManager"):
            mgr = QEMUManager()
            mgr.executables = MagicMock()
            mgr.executables.qemu_img = "/bin/qemu-img"
            return mgr

    @patch("adare.hypervisor.qemu.vm.QEMUVM")
    @patch("adare.backend.vm.commands._is_vm_managed", return_value=False) # External VM
    async def test_import_external_qcow2(self, mock_is_managed, mock_vm_cls, manager):
        """Test importing an external qcow2 VM (no conversion)."""
        # Mock QEMUVM
        mock_vm = MagicMock()
        mock_vm_cls.return_value = mock_vm
        mock_vm_cls._detect_disk_format_static.return_value = 'qcow2'
        
        vm_path = Path("/tmp/external.qcow2")
        
        with patch("adare.config.get_vm_credentials", return_value=("user", "pass")):
            result_vm = await manager.import_vm_async(vm_path, "import-test")
            
        assert result_vm == mock_vm
        # Check that disk_path was passed as string of original path
        call_kwargs = mock_vm_cls.call_args[1]
        assert call_kwargs['disk_path'] == str(vm_path)
        # Should NOT call create_from_ovf_or_ova
        mock_vm.create_from_ovf_or_ova.assert_not_called()
        # Should save config
        mock_vm._save_vm_config.assert_called_once()
    
    @patch("adare.hypervisor.qemu.vm.QEMUVM")
    @patch("adare.backend.vm.commands._is_vm_managed", return_value=True) # Managed VM (e.g. OVA)
    async def test_import_ova_conversion(self, mock_is_managed, mock_vm_cls, manager):
        """Test importing an OVA which requires conversion."""
        mock_vm = MagicMock()
        mock_vm_cls.return_value = mock_vm
        mock_vm.create_from_ovf_or_ova = AsyncMock(return_value=(0, "Success"))
        
        vm_path = Path("/tmp/app.ova")
        
        with patch("adare.config.get_vm_credentials", return_value=("user", "pass")):
            result_vm = await manager.import_vm_async(vm_path, "import-app")
            
        assert result_vm == mock_vm
        mock_vm.create_from_ovf_or_ova.assert_called_once()

    @patch("adare.hypervisor.qemu.vm.QEMUVM")
    @patch("adare.backend.vm.commands._is_vm_managed", return_value=True) 
    async def test_import_failure(self, mock_is_managed, mock_vm_cls, manager):
        """Test import handling conversion failure."""
        mock_vm = MagicMock()
        mock_vm_cls.return_value = mock_vm
        mock_vm.create_from_ovf_or_ova = AsyncMock(return_value=(1, "Conversion failed"))
        
        vm_path = Path("/tmp/broken.ova")
        
        with patch("adare.config.get_vm_credentials", return_value=("user", "pass")):
            with pytest.raises(VMImportException) as excinfo:
                await manager.import_vm_async(vm_path, "import-broken")
            
            assert "return code 1" in str(excinfo.value)
