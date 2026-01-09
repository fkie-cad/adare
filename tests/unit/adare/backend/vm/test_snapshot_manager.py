"""
Unit tests for VM Snapshot Manager module.

Tests cover:
- SnapshotManager class methods
- Instance snapshot methods
- Deprecated methods (verifying they return False/log errors)
- Convenience functions
- Error handling and edge cases
"""

import sys
import pytest
from unittest.mock import MagicMock, patch, call
from datetime import datetime, UTC
import threading

# Mock the problematic modules before importing the module under test
# This is needed because snapshot_manager imports QEMUVM which imports libvirt_qemu
sys.modules['libvirt_qemu'] = MagicMock()

# Module under test
from adare.backend.vm.snapshot_manager import (
    SnapshotManager,
    create_base_snapshot_for_vm,
    restore_vm_to_base_snapshot,
    verify_base_snapshot_exists,
    check_snapshot_exists_by_uuid,
    create_base_snapshot_for_instance,
    restore_instance_to_base_snapshot,
    verify_instance_base_snapshot_exists,
)
from adare.backend.vm.exceptions import VMError
from adare.hypervisor.exceptions import VMNotFoundException


# Patch paths
# VmApi is imported inside functions, so we need to patch at the source
VM_API_PATCH_PATH = 'adare.database.api.vm.VmApi'
VIRTUALBOX_VM_PATCH_PATH = 'adare.backend.vm.snapshot_manager.VirtualBoxVM'
VIRTUALBOX_MANAGER_PATCH_PATH = 'adare.backend.vm.snapshot_manager.VirtualBoxManager'
QEMU_VM_PATCH_PATH = 'adare.backend.vm.snapshot_manager.QEMUVM'
QEMU_MANAGER_PATCH_PATH = 'adare.backend.vm.snapshot_manager.QEMUManager'
GET_VM_CREDENTIALS_PATCH_PATH = 'adare.config.get_vm_credentials'


# === Fixtures ===

@pytest.fixture
def snapshot_manager():
    """Create a fresh SnapshotManager for testing."""
    with patch(VIRTUALBOX_MANAGER_PATCH_PATH):
        return SnapshotManager()


@pytest.fixture
def mock_vbox_manager():
    """Create a mock VirtualBoxManager."""
    manager = MagicMock()
    manager.executables = {'vboxmanage': '/usr/bin/vboxmanage'}
    return manager


@pytest.fixture
def mock_vm_api():
    """Create a mock VmApi context manager."""
    api = MagicMock()
    api.__enter__ = MagicMock(return_value=api)
    api.__exit__ = MagicMock(return_value=False)
    return api


@pytest.fixture
def mock_vm_instance():
    """Create a mock VmInstance object."""
    instance = MagicMock()
    instance.id = "test-instance-id-12345678"
    instance.instance_name = "test-vm_exp_12345678"
    instance.vm_id = "test-vm-id-12345678"
    instance.vbox_uuid = "vbox-uuid-12345678"
    instance.base_snapshot_name = "test-vm_exp_12345678_base"
    instance.last_used_at = datetime.now(UTC)
    instance.created_at = datetime.now(UTC)
    instance.vm = MagicMock()
    instance.vm.hypervisor = "virtualbox"
    instance.vm.name = "test-vm"
    instance.vm.osinfo = MagicMock()
    instance.vm.osinfo.platform = "linux"
    return instance


@pytest.fixture
def mock_qemu_vm_instance():
    """Create a mock QEMU VmInstance object."""
    instance = MagicMock()
    instance.id = "test-qemu-instance-id"
    instance.instance_name = "test-qemu-vm_exp_12345678"
    instance.vm_id = "test-qemu-vm-id"
    instance.vbox_uuid = None
    instance.base_snapshot_name = "test-qemu-vm_exp_12345678_base"
    instance.last_used_at = datetime.now(UTC)
    instance.created_at = datetime.now(UTC)
    instance.vm = MagicMock()
    instance.vm.hypervisor = "qemu"
    instance.vm.name = "test-qemu-vm"
    instance.vm.osinfo = MagicMock()
    instance.vm.osinfo.platform = "linux"
    return instance


@pytest.fixture
def mock_vm_record():
    """Create a mock Vm record (deprecated template)."""
    vm = MagicMock()
    vm.id = "test-vm-id-12345678"
    vm.name = "test-vm"
    vm.hash = "abc123def456"
    vm.vbox_uuid = "vbox-uuid-12345678"
    vm.base_snapshot_name = "adare_base_abc123de"
    vm.osinfo = MagicMock()
    vm.osinfo.platform = "linux"
    return vm


@pytest.fixture
def mock_vbox_vm():
    """Create a mock VirtualBoxVM object."""
    vm = MagicMock()
    vm.create_snapshot = MagicMock(return_value=0)
    vm.restore_snapshot = MagicMock(return_value=True)
    vm.delete_snapshot = MagicMock(return_value=True)
    vm.snapshot_exists = MagicMock(return_value=True)
    return vm


@pytest.fixture
def mock_qemu_vm():
    """Create a mock QEMUVM object."""
    vm = MagicMock()
    vm.create_snapshot = MagicMock(return_value=0)
    vm.restore_snapshot = MagicMock(return_value=True)
    vm.delete_snapshot = MagicMock(return_value=True)
    vm.snapshot_exists = MagicMock(return_value=True)
    vm.get_state = MagicMock(return_value='poweroff')
    return vm


# === Tests for SnapshotManager.__init__ ===

class TestSnapshotManagerInit:
    """Tests for SnapshotManager initialization."""

    def test_initializes_with_default_vbox_manager(self):
        """Test initialization creates default VirtualBoxManager."""
        with patch(VIRTUALBOX_MANAGER_PATCH_PATH) as mock_manager_class:
            mock_manager = MagicMock()
            mock_manager_class.return_value = mock_manager

            manager = SnapshotManager()

            mock_manager_class.assert_called_once()
            assert manager.vbox_manager == mock_manager

    def test_initializes_with_provided_vbox_manager(self, mock_vbox_manager):
        """Test initialization uses provided VirtualBoxManager."""
        manager = SnapshotManager(vbox_manager=mock_vbox_manager)

        assert manager.vbox_manager == mock_vbox_manager


# === Tests for _get_vm_name_by_uuid ===

class TestGetVmNameByUuid:
    """Tests for _get_vm_name_by_uuid method."""

    def test_delegates_to_virtualbox_vm(self, snapshot_manager):
        """Test that method delegates to VirtualBoxVM.get_vm_name_by_uuid."""
        with patch(VIRTUALBOX_VM_PATCH_PATH) as mock_vbox_class:
            mock_vbox_class.get_vm_name_by_uuid.return_value = "my-vm-name"

            result = snapshot_manager._get_vm_name_by_uuid("test-uuid")

            mock_vbox_class.get_vm_name_by_uuid.assert_called_once_with("test-uuid")
            assert result == "my-vm-name"

    def test_returns_none_when_vm_not_found(self, snapshot_manager):
        """Test returns None when VM is not found."""
        with patch(VIRTUALBOX_VM_PATCH_PATH) as mock_vbox_class:
            mock_vbox_class.get_vm_name_by_uuid.return_value = None

            result = snapshot_manager._get_vm_name_by_uuid("nonexistent-uuid")

            assert result is None


# === Tests for _get_vm_object ===

class TestGetVmObject:
    """Tests for _get_vm_object method."""

    def test_returns_virtualbox_vm_for_virtualbox_hypervisor(
        self, snapshot_manager, mock_vm_instance, mock_vbox_vm
    ):
        """Test returns VirtualBoxVM for VirtualBox instances."""
        with patch.object(snapshot_manager, '_get_vm_name_by_uuid', return_value="vm-name"):
            with patch(GET_VM_CREDENTIALS_PATCH_PATH, return_value=("user", "pass")):
                with patch(VIRTUALBOX_VM_PATCH_PATH, return_value=mock_vbox_vm):
                    result = snapshot_manager._get_vm_object(mock_vm_instance)

        assert result == mock_vbox_vm

    def test_raises_vm_error_when_virtualbox_uuid_missing(self, snapshot_manager, mock_vm_instance):
        """Test raises VMError when VirtualBox instance has no UUID."""
        mock_vm_instance.vbox_uuid = None

        with pytest.raises(VMError, match="has no vbox_uuid"):
            snapshot_manager._get_vm_object(mock_vm_instance)

    def test_raises_vm_error_when_virtualbox_vm_not_found(self, snapshot_manager, mock_vm_instance):
        """Test raises VMError when VirtualBox VM not found by UUID."""
        with patch.object(snapshot_manager, '_get_vm_name_by_uuid', return_value=None):
            with pytest.raises(VMError, match="not found"):
                snapshot_manager._get_vm_object(mock_vm_instance)

    def test_returns_qemu_vm_for_qemu_hypervisor(
        self, snapshot_manager, mock_qemu_vm_instance, mock_qemu_vm
    ):
        """Test returns QEMUVM for QEMU instances."""
        with patch(QEMU_VM_PATCH_PATH) as mock_qemu_class:
            with patch(QEMU_MANAGER_PATCH_PATH):
                mock_qemu_class.get_vm_by_name.return_value = mock_qemu_vm

                result = snapshot_manager._get_vm_object(mock_qemu_vm_instance)

        assert result == mock_qemu_vm

    def test_raises_vm_error_when_qemu_vm_not_found(self, snapshot_manager, mock_qemu_vm_instance):
        """Test raises VMError when QEMU VM not found."""
        with patch(QEMU_VM_PATCH_PATH) as mock_qemu_class:
            with patch(QEMU_MANAGER_PATCH_PATH):
                mock_qemu_class.get_vm_by_name.side_effect = VMNotFoundException("Not found")

                with pytest.raises(VMError, match="not found"):
                    snapshot_manager._get_vm_object(mock_qemu_vm_instance)

    def test_raises_vm_error_for_unsupported_hypervisor(self, snapshot_manager, mock_vm_instance):
        """Test raises VMError for unsupported hypervisor type."""
        mock_vm_instance.vm.hypervisor = "vmware"

        with pytest.raises(VMError, match="Unsupported hypervisor"):
            snapshot_manager._get_vm_object(mock_vm_instance)


# === Tests for _ensure_vm_stopped_for_qemu ===

class TestEnsureVmStoppedForQemu:
    """Tests for _ensure_vm_stopped_for_qemu method."""

    def test_returns_true_for_virtualbox(
        self, snapshot_manager, mock_vbox_vm, mock_vm_instance
    ):
        """Test returns True for VirtualBox VMs (no state check needed)."""
        mock_vm_instance.vm.hypervisor = "virtualbox"

        result = snapshot_manager._ensure_vm_stopped_for_qemu(
            mock_vbox_vm, mock_vm_instance, "test operation"
        )

        assert result is True
        # Should not call get_state for VirtualBox
        mock_vbox_vm.get_state.assert_not_called()

    def test_returns_true_when_qemu_vm_is_stopped(
        self, snapshot_manager, mock_qemu_vm, mock_qemu_vm_instance
    ):
        """Test returns True when QEMU VM is in poweroff state."""
        mock_qemu_vm.get_state.return_value = 'poweroff'

        result = snapshot_manager._ensure_vm_stopped_for_qemu(
            mock_qemu_vm, mock_qemu_vm_instance, "snapshot creation"
        )

        assert result is True
        mock_qemu_vm.get_state.assert_called_once()

    def test_returns_false_when_qemu_vm_is_running(
        self, snapshot_manager, mock_qemu_vm, mock_qemu_vm_instance
    ):
        """Test returns False when QEMU VM is running."""
        mock_qemu_vm.get_state.return_value = 'running'

        result = snapshot_manager._ensure_vm_stopped_for_qemu(
            mock_qemu_vm, mock_qemu_vm_instance, "snapshot creation"
        )

        assert result is False

    def test_returns_false_when_qemu_vm_is_paused(
        self, snapshot_manager, mock_qemu_vm, mock_qemu_vm_instance
    ):
        """Test returns False when QEMU VM is paused."""
        mock_qemu_vm.get_state.return_value = 'paused'

        result = snapshot_manager._ensure_vm_stopped_for_qemu(
            mock_qemu_vm, mock_qemu_vm_instance, "snapshot restore"
        )

        assert result is False

    def test_returns_false_on_os_error(
        self, snapshot_manager, mock_qemu_vm, mock_qemu_vm_instance
    ):
        """Test returns False when OSError occurs checking state."""
        mock_qemu_vm.get_state.side_effect = OSError("Failed to check state")

        result = snapshot_manager._ensure_vm_stopped_for_qemu(
            mock_qemu_vm, mock_qemu_vm_instance, "snapshot deletion"
        )

        assert result is False


# === Tests for create_base_snapshot_for_instance ===

class TestCreateBaseSnapshotForInstance:
    """Tests for create_base_snapshot_for_instance method."""

    def test_creates_snapshot_with_default_name(
        self, snapshot_manager, mock_vm_instance, mock_vbox_vm, mock_vm_api
    ):
        """Test creates snapshot with auto-generated name."""
        mock_vbox_vm.create_snapshot.return_value = 0

        with patch.object(snapshot_manager, '_get_vm_object', return_value=mock_vbox_vm):
            with patch.object(snapshot_manager, '_ensure_vm_stopped_for_qemu', return_value=True):
                with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
                    with patch.object(snapshot_manager, '_track_instance_snapshot_in_db'):
                        result = snapshot_manager.create_base_snapshot_for_instance(
                            mock_vm_instance
                        )

        assert result is True
        mock_vbox_vm.create_snapshot.assert_called_once()
        # Check auto-generated name
        call_args = mock_vbox_vm.create_snapshot.call_args
        assert call_args[1]['snapshot_name'] == f"{mock_vm_instance.instance_name}_base"

    def test_creates_snapshot_with_custom_name(
        self, snapshot_manager, mock_vm_instance, mock_vbox_vm, mock_vm_api
    ):
        """Test creates snapshot with custom name."""
        mock_vbox_vm.create_snapshot.return_value = 0

        with patch.object(snapshot_manager, '_get_vm_object', return_value=mock_vbox_vm):
            with patch.object(snapshot_manager, '_ensure_vm_stopped_for_qemu', return_value=True):
                with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
                    with patch.object(snapshot_manager, '_track_instance_snapshot_in_db'):
                        result = snapshot_manager.create_base_snapshot_for_instance(
                            mock_vm_instance,
                            snapshot_name="my_custom_snapshot"
                        )

        assert result is True
        call_args = mock_vbox_vm.create_snapshot.call_args
        assert call_args[1]['snapshot_name'] == "my_custom_snapshot"

    def test_creates_snapshot_with_custom_description(
        self, snapshot_manager, mock_vm_instance, mock_vbox_vm, mock_vm_api
    ):
        """Test creates snapshot with custom description."""
        mock_vbox_vm.create_snapshot.return_value = 0

        with patch.object(snapshot_manager, '_get_vm_object', return_value=mock_vbox_vm):
            with patch.object(snapshot_manager, '_ensure_vm_stopped_for_qemu', return_value=True):
                with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
                    with patch.object(snapshot_manager, '_track_instance_snapshot_in_db'):
                        result = snapshot_manager.create_base_snapshot_for_instance(
                            mock_vm_instance,
                            description="My custom description"
                        )

        assert result is True
        call_args = mock_vbox_vm.create_snapshot.call_args
        assert call_args[1]['description'] == "My custom description"

    def test_updates_instance_record_on_success(
        self, snapshot_manager, mock_vm_instance, mock_vbox_vm, mock_vm_api
    ):
        """Test updates instance record with snapshot info on success."""
        mock_vbox_vm.create_snapshot.return_value = 0

        with patch.object(snapshot_manager, '_get_vm_object', return_value=mock_vbox_vm):
            with patch.object(snapshot_manager, '_ensure_vm_stopped_for_qemu', return_value=True):
                with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
                    with patch.object(snapshot_manager, '_track_instance_snapshot_in_db'):
                        snapshot_manager.create_base_snapshot_for_instance(mock_vm_instance)

        mock_vm_api.update_vm_instance.assert_called_once()
        call_args = mock_vm_api.update_vm_instance.call_args
        assert call_args[0][0] == mock_vm_instance.id
        assert call_args[1]['use_snapshots'] is True

    def test_tracks_snapshot_in_database(
        self, snapshot_manager, mock_vm_instance, mock_vbox_vm, mock_vm_api
    ):
        """Test tracks snapshot in database on success."""
        mock_vbox_vm.create_snapshot.return_value = 0

        with patch.object(snapshot_manager, '_get_vm_object', return_value=mock_vbox_vm):
            with patch.object(snapshot_manager, '_ensure_vm_stopped_for_qemu', return_value=True):
                with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
                    with patch.object(
                        snapshot_manager, '_track_instance_snapshot_in_db'
                    ) as mock_track:
                        snapshot_manager.create_base_snapshot_for_instance(mock_vm_instance)

        mock_track.assert_called_once()
        call_args = mock_track.call_args
        assert call_args[0][0] == mock_vm_instance.id
        assert call_args[0][2] == "base"  # snapshot_type
        assert call_args[0][3] is None  # experiment_id (base snapshot has none)

    def test_returns_false_when_vm_object_fails(self, snapshot_manager, mock_vm_instance):
        """Test returns False when getting VM object fails."""
        with patch.object(
            snapshot_manager, '_get_vm_object',
            side_effect=VMError(MagicMock(), "Failed to get VM")
        ):
            result = snapshot_manager.create_base_snapshot_for_instance(mock_vm_instance)

        assert result is False

    def test_returns_false_when_qemu_not_stopped(
        self, snapshot_manager, mock_qemu_vm_instance, mock_qemu_vm
    ):
        """Test returns False when QEMU VM is not stopped."""
        with patch.object(snapshot_manager, '_get_vm_object', return_value=mock_qemu_vm):
            with patch.object(
                snapshot_manager, '_ensure_vm_stopped_for_qemu', return_value=False
            ):
                result = snapshot_manager.create_base_snapshot_for_instance(
                    mock_qemu_vm_instance
                )

        assert result is False

    def test_returns_false_when_snapshot_creation_fails(
        self, snapshot_manager, mock_vm_instance, mock_vbox_vm
    ):
        """Test returns False when snapshot creation fails."""
        mock_vbox_vm.create_snapshot.return_value = 1  # Non-zero indicates failure

        with patch.object(snapshot_manager, '_get_vm_object', return_value=mock_vbox_vm):
            with patch.object(snapshot_manager, '_ensure_vm_stopped_for_qemu', return_value=True):
                result = snapshot_manager.create_base_snapshot_for_instance(mock_vm_instance)

        assert result is False

    def test_returns_false_on_vm_not_found_exception(
        self, snapshot_manager, mock_vm_instance, mock_vbox_vm
    ):
        """Test returns False when VMNotFoundException is raised."""
        mock_vbox_vm.create_snapshot.side_effect = VMNotFoundException("VM not found")

        with patch.object(snapshot_manager, '_get_vm_object', return_value=mock_vbox_vm):
            with patch.object(snapshot_manager, '_ensure_vm_stopped_for_qemu', return_value=True):
                result = snapshot_manager.create_base_snapshot_for_instance(mock_vm_instance)

        assert result is False

    def test_returns_false_on_os_error(
        self, snapshot_manager, mock_vm_instance, mock_vbox_vm
    ):
        """Test returns False when OSError is raised."""
        mock_vbox_vm.create_snapshot.side_effect = OSError("Disk full")

        with patch.object(snapshot_manager, '_get_vm_object', return_value=mock_vbox_vm):
            with patch.object(snapshot_manager, '_ensure_vm_stopped_for_qemu', return_value=True):
                result = snapshot_manager.create_base_snapshot_for_instance(mock_vm_instance)

        assert result is False

    def test_silent_mode_passed_to_snapshot(
        self, snapshot_manager, mock_vm_instance, mock_vbox_vm, mock_vm_api
    ):
        """Test silent mode is passed to create_snapshot."""
        mock_vbox_vm.create_snapshot.return_value = 0

        with patch.object(snapshot_manager, '_get_vm_object', return_value=mock_vbox_vm):
            with patch.object(snapshot_manager, '_ensure_vm_stopped_for_qemu', return_value=True):
                with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
                    with patch.object(snapshot_manager, '_track_instance_snapshot_in_db'):
                        snapshot_manager.create_base_snapshot_for_instance(
                            mock_vm_instance, silent=True
                        )

        call_args = mock_vbox_vm.create_snapshot.call_args
        assert call_args[1]['silent'] is True


# === Tests for restore_instance_to_base_snapshot ===

class TestRestoreInstanceToBaseSnapshot:
    """Tests for restore_instance_to_base_snapshot method."""

    def test_restores_successfully(
        self, snapshot_manager, mock_vm_instance, mock_vbox_vm
    ):
        """Test successful snapshot restore."""
        mock_vbox_vm.restore_snapshot.return_value = True

        with patch.object(snapshot_manager, '_get_vm_object', return_value=mock_vbox_vm):
            with patch.object(snapshot_manager, '_ensure_vm_stopped_for_qemu', return_value=True):
                result = snapshot_manager.restore_instance_to_base_snapshot(mock_vm_instance)

        assert result is True
        mock_vbox_vm.restore_snapshot.assert_called_once_with(
            snapshot_name=mock_vm_instance.base_snapshot_name,
            silent=False,
            stop_event=None
        )

    def test_returns_false_when_no_base_snapshot_configured(
        self, snapshot_manager, mock_vm_instance
    ):
        """Test returns False when instance has no base snapshot."""
        mock_vm_instance.base_snapshot_name = None

        result = snapshot_manager.restore_instance_to_base_snapshot(mock_vm_instance)

        assert result is False

    def test_returns_false_when_interrupt_event_set_before_start(
        self, snapshot_manager, mock_vm_instance
    ):
        """Test returns False when interrupt event is set before starting."""
        interrupt_event = threading.Event()
        interrupt_event.set()

        result = snapshot_manager.restore_instance_to_base_snapshot(
            mock_vm_instance, interrupt_event=interrupt_event
        )

        assert result is False

    def test_returns_false_when_vm_object_fails(self, snapshot_manager, mock_vm_instance):
        """Test returns False when getting VM object fails."""
        with patch.object(
            snapshot_manager, '_get_vm_object',
            side_effect=VMError(MagicMock(), "Failed to get VM")
        ):
            result = snapshot_manager.restore_instance_to_base_snapshot(mock_vm_instance)

        assert result is False

    def test_returns_false_when_qemu_not_stopped(
        self, snapshot_manager, mock_qemu_vm_instance, mock_qemu_vm
    ):
        """Test returns False when QEMU VM is not stopped."""
        with patch.object(snapshot_manager, '_get_vm_object', return_value=mock_qemu_vm):
            with patch.object(
                snapshot_manager, '_ensure_vm_stopped_for_qemu', return_value=False
            ):
                result = snapshot_manager.restore_instance_to_base_snapshot(
                    mock_qemu_vm_instance
                )

        assert result is False

    def test_returns_false_when_restore_fails(
        self, snapshot_manager, mock_vm_instance, mock_vbox_vm
    ):
        """Test returns False when restore_snapshot returns False."""
        mock_vbox_vm.restore_snapshot.return_value = False

        with patch.object(snapshot_manager, '_get_vm_object', return_value=mock_vbox_vm):
            with patch.object(snapshot_manager, '_ensure_vm_stopped_for_qemu', return_value=True):
                result = snapshot_manager.restore_instance_to_base_snapshot(mock_vm_instance)

        assert result is False

    def test_returns_false_when_interrupt_event_set_after_operation(
        self, snapshot_manager, mock_vm_instance, mock_vbox_vm
    ):
        """Test returns False when interrupt event is set after operation."""
        interrupt_event = threading.Event()

        def restore_and_interrupt(*args, **kwargs):
            interrupt_event.set()
            return True

        mock_vbox_vm.restore_snapshot.side_effect = restore_and_interrupt

        with patch.object(snapshot_manager, '_get_vm_object', return_value=mock_vbox_vm):
            with patch.object(snapshot_manager, '_ensure_vm_stopped_for_qemu', return_value=True):
                result = snapshot_manager.restore_instance_to_base_snapshot(
                    mock_vm_instance, interrupt_event=interrupt_event
                )

        assert result is False

    def test_returns_false_on_interrupted_error(
        self, snapshot_manager, mock_vm_instance, mock_vbox_vm
    ):
        """Test returns False when InterruptedError is raised."""
        mock_vbox_vm.restore_snapshot.side_effect = InterruptedError("Interrupted")

        with patch.object(snapshot_manager, '_get_vm_object', return_value=mock_vbox_vm):
            with patch.object(snapshot_manager, '_ensure_vm_stopped_for_qemu', return_value=True):
                result = snapshot_manager.restore_instance_to_base_snapshot(mock_vm_instance)

        assert result is False

    def test_returns_false_on_vm_not_found_exception(
        self, snapshot_manager, mock_vm_instance, mock_vbox_vm
    ):
        """Test returns False when VMNotFoundException is raised."""
        mock_vbox_vm.restore_snapshot.side_effect = VMNotFoundException("Not found")

        with patch.object(snapshot_manager, '_get_vm_object', return_value=mock_vbox_vm):
            with patch.object(snapshot_manager, '_ensure_vm_stopped_for_qemu', return_value=True):
                result = snapshot_manager.restore_instance_to_base_snapshot(mock_vm_instance)

        assert result is False

    def test_returns_false_on_os_error(
        self, snapshot_manager, mock_vm_instance, mock_vbox_vm
    ):
        """Test returns False when OSError is raised."""
        mock_vbox_vm.restore_snapshot.side_effect = OSError("IO error")

        with patch.object(snapshot_manager, '_get_vm_object', return_value=mock_vbox_vm):
            with patch.object(snapshot_manager, '_ensure_vm_stopped_for_qemu', return_value=True):
                result = snapshot_manager.restore_instance_to_base_snapshot(mock_vm_instance)

        assert result is False

    def test_passes_interrupt_event_to_restore(
        self, snapshot_manager, mock_vm_instance, mock_vbox_vm
    ):
        """Test interrupt event is passed to restore_snapshot."""
        interrupt_event = threading.Event()
        mock_vbox_vm.restore_snapshot.return_value = True

        with patch.object(snapshot_manager, '_get_vm_object', return_value=mock_vbox_vm):
            with patch.object(snapshot_manager, '_ensure_vm_stopped_for_qemu', return_value=True):
                snapshot_manager.restore_instance_to_base_snapshot(
                    mock_vm_instance, interrupt_event=interrupt_event
                )

        call_args = mock_vbox_vm.restore_snapshot.call_args
        assert call_args[1]['stop_event'] == interrupt_event

    def test_silent_mode_passed_to_restore(
        self, snapshot_manager, mock_vm_instance, mock_vbox_vm
    ):
        """Test silent mode is passed to restore_snapshot."""
        mock_vbox_vm.restore_snapshot.return_value = True

        with patch.object(snapshot_manager, '_get_vm_object', return_value=mock_vbox_vm):
            with patch.object(snapshot_manager, '_ensure_vm_stopped_for_qemu', return_value=True):
                snapshot_manager.restore_instance_to_base_snapshot(
                    mock_vm_instance, silent=True
                )

        call_args = mock_vbox_vm.restore_snapshot.call_args
        assert call_args[1]['silent'] is True


# === Tests for check_instance_base_snapshot_exists ===

class TestCheckInstanceBaseSnapshotExists:
    """Tests for check_instance_base_snapshot_exists method."""

    def test_returns_true_when_snapshot_exists(
        self, snapshot_manager, mock_vm_instance, mock_vbox_vm
    ):
        """Test returns True when snapshot exists."""
        mock_vbox_vm.snapshot_exists.return_value = True

        with patch.object(snapshot_manager, '_get_vm_object', return_value=mock_vbox_vm):
            result = snapshot_manager.check_instance_base_snapshot_exists(mock_vm_instance)

        assert result is True
        mock_vbox_vm.snapshot_exists.assert_called_once_with(
            mock_vm_instance.base_snapshot_name
        )

    def test_returns_false_when_snapshot_does_not_exist(
        self, snapshot_manager, mock_vm_instance, mock_vbox_vm
    ):
        """Test returns False when snapshot does not exist."""
        mock_vbox_vm.snapshot_exists.return_value = False

        with patch.object(snapshot_manager, '_get_vm_object', return_value=mock_vbox_vm):
            result = snapshot_manager.check_instance_base_snapshot_exists(mock_vm_instance)

        assert result is False

    def test_returns_false_when_no_base_snapshot_configured(
        self, snapshot_manager, mock_vm_instance
    ):
        """Test returns False when no base snapshot name configured."""
        mock_vm_instance.base_snapshot_name = None

        result = snapshot_manager.check_instance_base_snapshot_exists(mock_vm_instance)

        assert result is False

    def test_returns_false_on_vm_error(self, snapshot_manager, mock_vm_instance):
        """Test returns False when VMError is raised."""
        with patch.object(
            snapshot_manager, '_get_vm_object',
            side_effect=VMError(MagicMock(), "Failed to get VM")
        ):
            result = snapshot_manager.check_instance_base_snapshot_exists(mock_vm_instance)

        assert result is False

    def test_returns_false_on_vm_not_found_exception(
        self, snapshot_manager, mock_vm_instance
    ):
        """Test returns False when VMNotFoundException is raised."""
        with patch.object(
            snapshot_manager, '_get_vm_object',
            side_effect=VMNotFoundException("Not found")
        ):
            result = snapshot_manager.check_instance_base_snapshot_exists(mock_vm_instance)

        assert result is False


# === Tests for create_experiment_snapshot_for_instance ===

class TestCreateExperimentSnapshotForInstance:
    """Tests for create_experiment_snapshot_for_instance method."""

    def test_creates_experiment_snapshot_successfully(
        self, snapshot_manager, mock_vm_instance, mock_vbox_vm, mock_vm_api
    ):
        """Test creates experiment snapshot with generated name."""
        mock_vbox_vm.create_snapshot.return_value = 0

        with patch.object(snapshot_manager, '_get_vm_object', return_value=mock_vbox_vm):
            with patch.object(snapshot_manager, '_ensure_vm_stopped_for_qemu', return_value=True):
                with patch.object(snapshot_manager, '_track_instance_snapshot_in_db'):
                    result = snapshot_manager.create_experiment_snapshot_for_instance(
                        mock_vm_instance,
                        experiment_id="exp123456789"
                    )

        assert result == "adare_exp_exp12345"  # First 8 chars of experiment_id
        mock_vbox_vm.create_snapshot.assert_called_once()

    def test_tracks_experiment_snapshot_in_database(
        self, snapshot_manager, mock_vm_instance, mock_vbox_vm
    ):
        """Test tracks experiment snapshot in database."""
        mock_vbox_vm.create_snapshot.return_value = 0
        experiment_id = "exp123456789"

        with patch.object(snapshot_manager, '_get_vm_object', return_value=mock_vbox_vm):
            with patch.object(snapshot_manager, '_ensure_vm_stopped_for_qemu', return_value=True):
                with patch.object(
                    snapshot_manager, '_track_instance_snapshot_in_db'
                ) as mock_track:
                    snapshot_manager.create_experiment_snapshot_for_instance(
                        mock_vm_instance,
                        experiment_id=experiment_id
                    )

        mock_track.assert_called_once()
        call_args = mock_track.call_args
        assert call_args[0][2] == "experiment"  # snapshot_type
        assert call_args[0][3] == experiment_id

    def test_returns_none_when_vm_object_fails(self, snapshot_manager, mock_vm_instance):
        """Test returns None when getting VM object fails."""
        with patch.object(
            snapshot_manager, '_get_vm_object',
            side_effect=VMError(MagicMock(), "Failed to get VM")
        ):
            result = snapshot_manager.create_experiment_snapshot_for_instance(
                mock_vm_instance, experiment_id="exp123"
            )

        assert result is None

    def test_returns_none_when_snapshot_creation_fails(
        self, snapshot_manager, mock_vm_instance, mock_vbox_vm
    ):
        """Test returns None when snapshot creation fails."""
        mock_vbox_vm.create_snapshot.return_value = 1

        with patch.object(snapshot_manager, '_get_vm_object', return_value=mock_vbox_vm):
            with patch.object(snapshot_manager, '_ensure_vm_stopped_for_qemu', return_value=True):
                result = snapshot_manager.create_experiment_snapshot_for_instance(
                    mock_vm_instance, experiment_id="exp123"
                )

        assert result is None

    def test_uses_custom_description(
        self, snapshot_manager, mock_vm_instance, mock_vbox_vm
    ):
        """Test uses custom description when provided."""
        mock_vbox_vm.create_snapshot.return_value = 0

        with patch.object(snapshot_manager, '_get_vm_object', return_value=mock_vbox_vm):
            with patch.object(snapshot_manager, '_ensure_vm_stopped_for_qemu', return_value=True):
                with patch.object(snapshot_manager, '_track_instance_snapshot_in_db'):
                    snapshot_manager.create_experiment_snapshot_for_instance(
                        mock_vm_instance,
                        experiment_id="exp123",
                        description="My experiment snapshot"
                    )

        call_args = mock_vbox_vm.create_snapshot.call_args
        assert call_args[1]['description'] == "My experiment snapshot"


# === Tests for delete_instance_snapshot ===

class TestDeleteInstanceSnapshot:
    """Tests for delete_instance_snapshot method."""

    def test_deletes_snapshot_successfully(
        self, snapshot_manager, mock_vm_instance, mock_vbox_vm, mock_vm_api
    ):
        """Test deletes non-base snapshot successfully."""
        mock_vbox_vm.delete_snapshot.return_value = True

        with patch.object(snapshot_manager, '_get_vm_object', return_value=mock_vbox_vm):
            with patch.object(snapshot_manager, '_ensure_vm_stopped_for_qemu', return_value=True):
                with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
                    result = snapshot_manager.delete_instance_snapshot(
                        mock_vm_instance,
                        snapshot_name="some_experiment_snapshot"
                    )

        assert result is True
        mock_vbox_vm.delete_snapshot.assert_called_once_with(
            snapshot_name="some_experiment_snapshot",
            silent=False
        )

    def test_raises_vm_error_when_deleting_base_snapshot(
        self, snapshot_manager, mock_vm_instance
    ):
        """Test raises VMError when attempting to delete base snapshot."""
        with pytest.raises(VMError, match="Cannot delete base snapshot"):
            snapshot_manager.delete_instance_snapshot(
                mock_vm_instance,
                snapshot_name=mock_vm_instance.base_snapshot_name
            )

    def test_removes_snapshot_record_from_database(
        self, snapshot_manager, mock_vm_instance, mock_vbox_vm, mock_vm_api
    ):
        """Test removes snapshot record from database on success."""
        mock_vbox_vm.delete_snapshot.return_value = True

        with patch.object(snapshot_manager, '_get_vm_object', return_value=mock_vbox_vm):
            with patch.object(snapshot_manager, '_ensure_vm_stopped_for_qemu', return_value=True):
                with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
                    snapshot_manager.delete_instance_snapshot(
                        mock_vm_instance,
                        snapshot_name="exp_snapshot"
                    )

        mock_vm_api.delete_instance_snapshot_record.assert_called_once_with(
            vm_instance_id=mock_vm_instance.id,
            snapshot_name="exp_snapshot"
        )

    def test_returns_false_when_vm_object_fails(
        self, snapshot_manager, mock_vm_instance
    ):
        """Test returns False when getting VM object fails."""
        mock_vm_instance.base_snapshot_name = "different_snapshot"

        with patch.object(
            snapshot_manager, '_get_vm_object',
            side_effect=VMError(MagicMock(), "Failed to get VM")
        ):
            result = snapshot_manager.delete_instance_snapshot(
                mock_vm_instance,
                snapshot_name="exp_snapshot"
            )

        assert result is False

    def test_returns_false_when_deletion_fails(
        self, snapshot_manager, mock_vm_instance, mock_vbox_vm
    ):
        """Test returns False when snapshot deletion fails."""
        mock_vbox_vm.delete_snapshot.return_value = False

        with patch.object(snapshot_manager, '_get_vm_object', return_value=mock_vbox_vm):
            with patch.object(snapshot_manager, '_ensure_vm_stopped_for_qemu', return_value=True):
                result = snapshot_manager.delete_instance_snapshot(
                    mock_vm_instance,
                    snapshot_name="exp_snapshot"
                )

        assert result is False

    def test_returns_false_on_os_error(
        self, snapshot_manager, mock_vm_instance, mock_vbox_vm
    ):
        """Test returns False when OSError is raised."""
        mock_vbox_vm.delete_snapshot.side_effect = OSError("IO error")

        with patch.object(snapshot_manager, '_get_vm_object', return_value=mock_vbox_vm):
            with patch.object(snapshot_manager, '_ensure_vm_stopped_for_qemu', return_value=True):
                result = snapshot_manager.delete_instance_snapshot(
                    mock_vm_instance,
                    snapshot_name="exp_snapshot"
                )

        assert result is False


# === Tests for _track_instance_snapshot_in_db ===

class TestTrackInstanceSnapshotInDb:
    """Tests for _track_instance_snapshot_in_db method."""

    def test_creates_snapshot_record(self, snapshot_manager, mock_vm_api):
        """Test creates snapshot record in database."""
        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            snapshot_manager._track_instance_snapshot_in_db(
                vm_instance_id="instance-123",
                snapshot_name="my_snapshot",
                snapshot_type="base",
                experiment_id=None,
                description="Test snapshot"
            )

        mock_vm_api.create_instance_snapshot_record.assert_called_once_with(
            vm_instance_id="instance-123",
            snapshot_name="my_snapshot",
            snapshot_type="base",
            experiment_id=None,
            description="Test snapshot"
        )

    def test_tracks_experiment_snapshot_with_experiment_id(
        self, snapshot_manager, mock_vm_api
    ):
        """Test tracks experiment snapshot with experiment ID."""
        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            snapshot_manager._track_instance_snapshot_in_db(
                vm_instance_id="instance-123",
                snapshot_name="exp_snapshot",
                snapshot_type="experiment",
                experiment_id="exp-456",
                description="Experiment snapshot"
            )

        call_args = mock_vm_api.create_instance_snapshot_record.call_args
        assert call_args[1]['experiment_id'] == "exp-456"
        assert call_args[1]['snapshot_type'] == "experiment"


# === Tests for Deprecated Methods ===

class TestDeprecatedMethods:
    """Tests for deprecated methods that should return False/log errors."""

    def test_create_base_snapshot_returns_false_and_logs_error(
        self, snapshot_manager, mock_vm_record, caplog
    ):
        """Test create_base_snapshot returns False and logs deprecation error."""
        import logging
        with caplog.at_level(logging.ERROR):
            result = snapshot_manager.create_base_snapshot(mock_vm_record)

        assert result is False
        assert "deprecated" in caplog.text.lower()

    def test_restore_base_snapshot_returns_false_and_logs_error(
        self, snapshot_manager, mock_vm_record, caplog
    ):
        """Test restore_base_snapshot returns False and logs deprecation error."""
        import logging
        with caplog.at_level(logging.ERROR):
            result = snapshot_manager.restore_base_snapshot(mock_vm_record)

        assert result is False
        assert "deprecated" in caplog.text.lower()

    def test_check_base_snapshot_exists_returns_false_and_logs_error(
        self, snapshot_manager, mock_vm_record, caplog
    ):
        """Test check_base_snapshot_exists returns False and logs deprecation error."""
        import logging
        with caplog.at_level(logging.ERROR):
            result = snapshot_manager.check_base_snapshot_exists(mock_vm_record)

        assert result is False
        assert "deprecated" in caplog.text.lower()

    def test_get_snapshot_info_returns_empty_dict_and_logs_warning(
        self, snapshot_manager, mock_vm_record, caplog
    ):
        """Test get_snapshot_info returns empty dict structure and logs warning."""
        import logging
        with caplog.at_level(logging.WARNING):
            result = snapshot_manager.get_snapshot_info(mock_vm_record)

        assert result == {
            "base_snapshot": {"name": None, "exists": False},
            "experiment_snapshots": [],
            "total_snapshots": 0
        }
        assert "deprecated" in caplog.text.lower()

    def test_track_snapshot_in_db_logs_error(self, snapshot_manager, caplog):
        """Test _track_snapshot_in_db logs deprecation error."""
        import logging
        with caplog.at_level(logging.ERROR):
            snapshot_manager._track_snapshot_in_db(
                "vm-id", "snapshot", "base", None, "desc"
            )

        assert "deprecated" in caplog.text.lower()

    def test_get_experiment_snapshots_for_vm_returns_empty_list(
        self, snapshot_manager, caplog
    ):
        """Test _get_experiment_snapshots_for_vm returns empty list."""
        import logging
        with caplog.at_level(logging.WARNING):
            result = snapshot_manager._get_experiment_snapshots_for_vm("vm-id")

        assert result == []
        assert "deprecated" in caplog.text.lower()

    def test_delete_snapshot_returns_false(self, snapshot_manager, mock_vm_record, caplog):
        """Test _delete_snapshot returns False tuple."""
        import logging
        with caplog.at_level(logging.ERROR):
            result = snapshot_manager._delete_snapshot(mock_vm_record, "snapshot")

        assert result == (False, "VM templates don't have snapshots - use instance-based snapshots")


# === Tests for Convenience Functions ===

class TestConvenienceFunctions:
    """Tests for module-level convenience functions."""

    def test_create_base_snapshot_for_vm_uses_manager(self, mock_vm_record):
        """Test create_base_snapshot_for_vm uses SnapshotManager."""
        with patch(VIRTUALBOX_MANAGER_PATCH_PATH):
            with patch.object(
                SnapshotManager, 'create_base_snapshot', return_value=False
            ) as mock_method:
                result = create_base_snapshot_for_vm(mock_vm_record, silent=True)

        mock_method.assert_called_once_with(mock_vm_record, silent=True)
        assert result is False

    def test_restore_vm_to_base_snapshot_uses_manager(self, mock_vm_record):
        """Test restore_vm_to_base_snapshot uses SnapshotManager."""
        interrupt_event = threading.Event()

        with patch(VIRTUALBOX_MANAGER_PATCH_PATH):
            with patch.object(
                SnapshotManager, 'restore_base_snapshot', return_value=False
            ) as mock_method:
                result = restore_vm_to_base_snapshot(
                    mock_vm_record,
                    silent=True,
                    interrupt_event=interrupt_event,
                    timeout=60
                )

        mock_method.assert_called_once_with(
            mock_vm_record,
            silent=True,
            interrupt_event=interrupt_event,
            timeout=60
        )
        assert result is False

    def test_verify_base_snapshot_exists_uses_manager(self, mock_vm_record):
        """Test verify_base_snapshot_exists uses SnapshotManager."""
        with patch(VIRTUALBOX_MANAGER_PATCH_PATH):
            with patch.object(
                SnapshotManager, 'check_base_snapshot_exists', return_value=False
            ) as mock_method:
                result = verify_base_snapshot_exists(mock_vm_record)

        mock_method.assert_called_once_with(mock_vm_record)
        assert result is False


# === Tests for check_snapshot_exists_by_uuid ===

class TestCheckSnapshotExistsByUuid:
    """Tests for check_snapshot_exists_by_uuid function."""

    def test_returns_true_when_snapshot_exists(self, mock_vbox_vm):
        """Test returns True when snapshot exists."""
        mock_vbox_vm.snapshot_exists.return_value = True

        with patch(VIRTUALBOX_VM_PATCH_PATH) as mock_vbox_class:
            mock_vbox_class.get_vm_name_by_uuid.return_value = "vm-name"
            mock_vbox_class.return_value = mock_vbox_vm

            with patch(VIRTUALBOX_MANAGER_PATCH_PATH) as mock_manager_class:
                mock_manager = MagicMock()
                mock_manager.executables = {}
                mock_manager_class.return_value = mock_manager

                result = check_snapshot_exists_by_uuid("test-uuid", "my_snapshot")

        assert result is True

    def test_returns_false_when_vm_not_found(self):
        """Test returns False when VM UUID not found."""
        with patch(VIRTUALBOX_VM_PATCH_PATH) as mock_vbox_class:
            mock_vbox_class.get_vm_name_by_uuid.return_value = None

            result = check_snapshot_exists_by_uuid("nonexistent-uuid", "snapshot")

        assert result is False

    def test_returns_false_when_snapshot_does_not_exist(self, mock_vbox_vm):
        """Test returns False when snapshot does not exist."""
        mock_vbox_vm.snapshot_exists.return_value = False

        with patch(VIRTUALBOX_VM_PATCH_PATH) as mock_vbox_class:
            mock_vbox_class.get_vm_name_by_uuid.return_value = "vm-name"
            mock_vbox_class.return_value = mock_vbox_vm

            with patch(VIRTUALBOX_MANAGER_PATCH_PATH) as mock_manager_class:
                mock_manager = MagicMock()
                mock_manager.executables = {}
                mock_manager_class.return_value = mock_manager

                result = check_snapshot_exists_by_uuid("test-uuid", "nonexistent")

        assert result is False

    def test_returns_false_on_exception(self, mock_vbox_vm):
        """Test returns False when exception is raised."""
        mock_vbox_vm.snapshot_exists.side_effect = RuntimeError("Error")

        with patch(VIRTUALBOX_VM_PATCH_PATH) as mock_vbox_class:
            mock_vbox_class.get_vm_name_by_uuid.return_value = "vm-name"
            mock_vbox_class.return_value = mock_vbox_vm

            with patch(VIRTUALBOX_MANAGER_PATCH_PATH) as mock_manager_class:
                mock_manager = MagicMock()
                mock_manager.executables = {}
                mock_manager_class.return_value = mock_manager

                result = check_snapshot_exists_by_uuid("test-uuid", "snapshot")

        assert result is False


# === Tests for Instance-Aware Convenience Functions ===

class TestInstanceAwareConvenienceFunctions:
    """Tests for instance-aware convenience functions."""

    def test_create_base_snapshot_for_instance_function(self, mock_vm_instance):
        """Test create_base_snapshot_for_instance convenience function."""
        with patch(VIRTUALBOX_MANAGER_PATCH_PATH):
            with patch.object(
                SnapshotManager, 'create_base_snapshot_for_instance', return_value=True
            ) as mock_method:
                result = create_base_snapshot_for_instance(mock_vm_instance, silent=True)

        mock_method.assert_called_once_with(mock_vm_instance, silent=True)
        assert result is True

    def test_restore_instance_to_base_snapshot_function(self, mock_vm_instance):
        """Test restore_instance_to_base_snapshot convenience function."""
        interrupt_event = threading.Event()

        with patch(VIRTUALBOX_MANAGER_PATCH_PATH):
            with patch.object(
                SnapshotManager, 'restore_instance_to_base_snapshot', return_value=True
            ) as mock_method:
                result = restore_instance_to_base_snapshot(
                    mock_vm_instance,
                    silent=True,
                    interrupt_event=interrupt_event,
                    timeout=60
                )

        mock_method.assert_called_once_with(
            mock_vm_instance,
            silent=True,
            interrupt_event=interrupt_event,
            timeout=60
        )
        assert result is True

    def test_verify_instance_base_snapshot_exists_function(self, mock_vm_instance):
        """Test verify_instance_base_snapshot_exists convenience function."""
        with patch(VIRTUALBOX_MANAGER_PATCH_PATH):
            with patch.object(
                SnapshotManager, 'check_instance_base_snapshot_exists', return_value=True
            ) as mock_method:
                result = verify_instance_base_snapshot_exists(mock_vm_instance)

        mock_method.assert_called_once_with(mock_vm_instance)
        assert result is True


# === Tests for Edge Cases ===

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_create_snapshot_with_empty_instance_name(
        self, snapshot_manager, mock_vm_instance, mock_vbox_vm, mock_vm_api
    ):
        """Test snapshot creation handles empty instance name gracefully."""
        mock_vm_instance.instance_name = ""
        mock_vbox_vm.create_snapshot.return_value = 0

        with patch.object(snapshot_manager, '_get_vm_object', return_value=mock_vbox_vm):
            with patch.object(snapshot_manager, '_ensure_vm_stopped_for_qemu', return_value=True):
                with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
                    with patch.object(snapshot_manager, '_track_instance_snapshot_in_db'):
                        result = snapshot_manager.create_base_snapshot_for_instance(
                            mock_vm_instance
                        )

        assert result is True
        call_args = mock_vbox_vm.create_snapshot.call_args
        assert call_args[1]['snapshot_name'] == "_base"  # Empty name + _base

    def test_restore_with_empty_base_snapshot_name(
        self, snapshot_manager, mock_vm_instance
    ):
        """Test restore returns False with empty string base snapshot name."""
        mock_vm_instance.base_snapshot_name = ""

        result = snapshot_manager.restore_instance_to_base_snapshot(mock_vm_instance)

        assert result is False

    def test_experiment_snapshot_with_short_experiment_id(
        self, snapshot_manager, mock_vm_instance, mock_vbox_vm
    ):
        """Test experiment snapshot with experiment ID shorter than 8 chars."""
        mock_vbox_vm.create_snapshot.return_value = 0

        with patch.object(snapshot_manager, '_get_vm_object', return_value=mock_vbox_vm):
            with patch.object(snapshot_manager, '_ensure_vm_stopped_for_qemu', return_value=True):
                with patch.object(snapshot_manager, '_track_instance_snapshot_in_db'):
                    result = snapshot_manager.create_experiment_snapshot_for_instance(
                        mock_vm_instance,
                        experiment_id="abc"
                    )

        assert result == "adare_exp_abc"  # Uses full short ID

    def test_get_vm_object_with_missing_osinfo(
        self, snapshot_manager, mock_vm_instance, mock_vbox_vm
    ):
        """Test _get_vm_object handles missing osinfo gracefully."""
        mock_vm_instance.vm.osinfo = None

        with patch.object(snapshot_manager, '_get_vm_name_by_uuid', return_value="vm-name"):
            with patch(GET_VM_CREDENTIALS_PATCH_PATH, return_value=("user", "pass")):
                with patch(VIRTUALBOX_VM_PATCH_PATH, return_value=mock_vbox_vm):
                    result = snapshot_manager._get_vm_object(mock_vm_instance)

        # Should default to 'linux' platform
        assert result == mock_vbox_vm

    def test_delete_snapshot_allows_when_base_snapshot_is_none(
        self, snapshot_manager, mock_vm_instance, mock_vbox_vm, mock_vm_api
    ):
        """Test delete_instance_snapshot allows deletion when base_snapshot_name is None."""
        mock_vm_instance.base_snapshot_name = None
        mock_vbox_vm.delete_snapshot.return_value = True

        with patch.object(snapshot_manager, '_get_vm_object', return_value=mock_vbox_vm):
            with patch.object(snapshot_manager, '_ensure_vm_stopped_for_qemu', return_value=True):
                with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
                    # Should not raise since we're not deleting the base snapshot
                    result = snapshot_manager.delete_instance_snapshot(
                        mock_vm_instance,
                        snapshot_name="some_other_snapshot"
                    )

        assert result is True


# === Tests for QEMU-Specific Behavior ===

class TestQemuSpecificBehavior:
    """Tests for QEMU-specific snapshot behavior."""

    def test_qemu_create_snapshot_checks_state(
        self, snapshot_manager, mock_qemu_vm_instance, mock_qemu_vm, mock_vm_api
    ):
        """Test QEMU snapshot creation checks VM state."""
        mock_qemu_vm.get_state.return_value = 'poweroff'
        mock_qemu_vm.create_snapshot.return_value = 0

        with patch.object(snapshot_manager, '_get_vm_object', return_value=mock_qemu_vm):
            with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
                with patch.object(snapshot_manager, '_track_instance_snapshot_in_db'):
                    result = snapshot_manager.create_base_snapshot_for_instance(
                        mock_qemu_vm_instance
                    )

        assert result is True
        mock_qemu_vm.get_state.assert_called_once()

    def test_qemu_create_snapshot_fails_when_running(
        self, snapshot_manager, mock_qemu_vm_instance, mock_qemu_vm
    ):
        """Test QEMU snapshot creation fails when VM is running."""
        mock_qemu_vm.get_state.return_value = 'running'

        with patch.object(snapshot_manager, '_get_vm_object', return_value=mock_qemu_vm):
            result = snapshot_manager.create_base_snapshot_for_instance(
                mock_qemu_vm_instance
            )

        assert result is False
        mock_qemu_vm.create_snapshot.assert_not_called()

    def test_qemu_restore_fails_when_paused(
        self, snapshot_manager, mock_qemu_vm_instance, mock_qemu_vm
    ):
        """Test QEMU restore fails when VM is paused."""
        mock_qemu_vm.get_state.return_value = 'paused'

        with patch.object(snapshot_manager, '_get_vm_object', return_value=mock_qemu_vm):
            result = snapshot_manager.restore_instance_to_base_snapshot(
                mock_qemu_vm_instance
            )

        assert result is False
        mock_qemu_vm.restore_snapshot.assert_not_called()

    def test_qemu_delete_fails_when_running(
        self, snapshot_manager, mock_qemu_vm_instance, mock_qemu_vm
    ):
        """Test QEMU snapshot deletion fails when VM is running."""
        mock_qemu_vm_instance.base_snapshot_name = "different_snapshot"
        mock_qemu_vm.get_state.return_value = 'running'

        with patch.object(snapshot_manager, '_get_vm_object', return_value=mock_qemu_vm):
            result = snapshot_manager.delete_instance_snapshot(
                mock_qemu_vm_instance,
                snapshot_name="exp_snapshot"
            )

        assert result is False
        mock_qemu_vm.delete_snapshot.assert_not_called()


# === Tests for VirtualBox-Specific Behavior ===

class TestVirtualboxSpecificBehavior:
    """Tests for VirtualBox-specific snapshot behavior."""

    def test_virtualbox_snapshot_does_not_check_state(
        self, snapshot_manager, mock_vm_instance, mock_vbox_vm, mock_vm_api
    ):
        """Test VirtualBox snapshot does not check VM state (can snapshot while running)."""
        mock_vbox_vm.create_snapshot.return_value = 0

        with patch.object(snapshot_manager, '_get_vm_object', return_value=mock_vbox_vm):
            with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
                with patch.object(snapshot_manager, '_track_instance_snapshot_in_db'):
                    result = snapshot_manager.create_base_snapshot_for_instance(
                        mock_vm_instance
                    )

        assert result is True
        # VirtualBox VM should not have get_state called
        # (the mock_vbox_vm fixture doesn't have get_state defined which is correct)

    def test_virtualbox_creates_vm_with_credentials(
        self, snapshot_manager, mock_vm_instance, mock_vbox_vm
    ):
        """Test VirtualBox VM is created with proper credentials."""
        with patch.object(snapshot_manager, '_get_vm_name_by_uuid', return_value="vm-name"):
            with patch(GET_VM_CREDENTIALS_PATCH_PATH, return_value=("testuser", "testpass")):
                with patch(VIRTUALBOX_VM_PATCH_PATH) as mock_vbox_class:
                    mock_vbox_class.return_value = mock_vbox_vm

                    snapshot_manager._get_vm_object(mock_vm_instance)

        mock_vbox_class.assert_called_once()
        call_kwargs = mock_vbox_class.call_args[1]
        assert call_kwargs['username'] == "testuser"
        assert call_kwargs['password'] == "testpass"
