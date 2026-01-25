"""
Unit tests for VM Instance Manager module.

Tests cover:
- VmInstanceManager class methods
- Global singleton functions
- Locking behavior
- Async operations
- Error handling and edge cases
"""

import sys
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from datetime import datetime, timedelta, UTC
import threading

# Mock the problematic modules before importing the module under test
# This is needed because snapshot_manager imports QEMUVM which imports libvirt_qemu
sys.modules['libvirt_qemu'] = MagicMock()

# Module under test
from adare.backend.vm.instance_manager import (
    VmInstanceManager,
    allocate_vm_instance_for_experiment,
    release_vm_instance,
    cleanup_vm_instance,
    cleanup_old_vm_instances,
    remove_all_instances,
    get_vm_instance_stats,
    _instance_manager,
)
from adare.backend.vm.exceptions import VMError
from adare.hypervisor.exceptions import (
    InstanceNotFoundException,
    InstanceStateException,
)


# The VmApi is imported inside methods, so we need to patch it at the source
VM_API_PATCH_PATH = 'adare.database.api.vm.VmApi'
# vm_database is imported as a module inside create_new_instance
VM_DATABASE_PATCH_PATH = 'adare.backend.vm.database'


# === Fixtures ===

@pytest.fixture
def instance_manager():
    """Create a fresh VmInstanceManager for testing."""
    return VmInstanceManager()


@pytest.fixture
def mock_vm_instance():
    """Create a mock VmInstance object."""
    instance = MagicMock()
    instance.id = "test-instance-id-12345678"
    instance.instance_name = "test-vm_exp_12345678"
    instance.vm_id = "test-vm-id-12345678"
    instance.vbox_uuid = "vbox-uuid-12345678"
    instance.websocket_port = 18765
    instance.status = "active"
    instance.current_experiment_run_id = "test-experiment-run"
    instance.base_snapshot_name = None  # Set to None to skip snapshot validation in tests
    instance.last_used_at = datetime.now(UTC)
    instance.created_at = datetime.now(UTC)
    instance.vm = MagicMock()
    instance.vm.hypervisor = "virtualbox"
    instance.vm.name = "test-vm"
    return instance


@pytest.fixture
def mock_vm_record():
    """Create a mock VM record."""
    vm = MagicMock()
    vm.id = "test-vm-id-12345678"
    vm.name = "test-vm"
    vm.hypervisor = "virtualbox"
    vm.file = "/path/to/vm.ova"
    return vm


@pytest.fixture
def mock_vm_api():
    """Create a mock VmApi context manager."""
    api = MagicMock()
    api.__enter__ = MagicMock(return_value=api)
    api.__exit__ = MagicMock(return_value=False)
    return api


# === Tests for Constants ===

class TestConstants:
    """Tests for module constants."""

    def test_max_instances_per_vm(self):
        """Verify MAX_INSTANCES_PER_VM constant value."""
        assert VmInstanceManager.MAX_INSTANCES_PER_VM == 20

    def test_cleanup_age_days(self):
        """Verify CLEANUP_AGE_DAYS constant value."""
        assert VmInstanceManager.CLEANUP_AGE_DAYS == 7


# === Tests for _generate_instance_name ===

class TestGenerateInstanceName:
    """Tests for _generate_instance_name method."""

    def test_generates_name_with_short_id(self, instance_manager):
        """Test that instance name uses first 8 chars of experiment ID."""
        result = instance_manager._generate_instance_name(
            "my-base-vm",
            "abcdefghijklmnopqrstuvwxyz"
        )
        assert result == "my-base-vm_exp_abcdefgh"

    def test_exact_8_char_experiment_id(self, instance_manager):
        """Test with exactly 8 character experiment ID."""
        result = instance_manager._generate_instance_name(
            "vm-name",
            "12345678"
        )
        assert result == "vm-name_exp_12345678"

    def test_preserves_base_vm_name_special_chars(self, instance_manager):
        """Test that special characters in base name are preserved."""
        result = instance_manager._generate_instance_name(
            "vm-with_special.chars",
            "experiment123"
        )
        assert result == "vm-with_special.chars_exp_experime"


# === Tests for find_available_instance ===

class TestFindAvailableInstance:
    """Tests for find_available_instance method."""

    def test_returns_most_recently_used_instance(self, instance_manager, mock_vm_api):
        """Test that the most recently used instance is returned."""
        older_instance = MagicMock()
        older_instance.last_used_at = datetime.now(UTC) - timedelta(hours=1)
        older_instance.instance_name = "old-instance"

        newer_instance = MagicMock()
        newer_instance.last_used_at = datetime.now(UTC)
        newer_instance.instance_name = "new-instance"

        mock_vm_api.get_vm_instances_for_vm.return_value = [older_instance, newer_instance]

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            result = instance_manager.find_available_instance("test-vm-id")

        assert result == newer_instance

    def test_returns_none_when_no_available_instances(self, instance_manager, mock_vm_api):
        """Test returns None when no instances available."""
        mock_vm_api.get_vm_instances_for_vm.return_value = []

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            result = instance_manager.find_available_instance("test-vm-id")

        assert result is None

    def test_passes_available_status_filter(self, instance_manager, mock_vm_api):
        """Test that status='available' is passed to API."""
        mock_vm_api.get_vm_instances_for_vm.return_value = []

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            instance_manager.find_available_instance("test-vm-id")

        mock_vm_api.get_vm_instances_for_vm.assert_called_once_with(
            "test-vm-id", status='available'
        )


# === Tests for get_instance_count_for_vm ===

class TestGetInstanceCountForVm:
    """Tests for get_instance_count_for_vm method."""

    def test_returns_correct_count(self, instance_manager, mock_vm_api):
        """Test returns correct number of instances."""
        mock_vm_api.get_vm_instances_for_vm.return_value = [
            MagicMock(), MagicMock(), MagicMock()
        ]

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            result = instance_manager.get_instance_count_for_vm("test-vm-id")

        assert result == 3

    def test_returns_zero_when_no_instances(self, instance_manager, mock_vm_api):
        """Test returns 0 when no instances exist."""
        mock_vm_api.get_vm_instances_for_vm.return_value = []

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            result = instance_manager.get_instance_count_for_vm("test-vm-id")

        assert result == 0


# === Tests for _get_hypervisor_vm_state ===

class TestGetHypervisorVmState:
    """Tests for _get_hypervisor_vm_state method."""

    def test_returns_not_found_when_no_identifier(self, instance_manager, mock_vm_instance, mock_vm_api):
        """Test returns 'not_found' when instance has no hypervisor identifier."""
        mock_vm_instance.vbox_uuid = None
        mock_vm_instance.instance_name = "test-instance"

        mock_strategy = MagicMock()
        mock_strategy.get_identifier.return_value = None

        with patch('adare.backend.vm.instance_manager.get_identifier_strategy', return_value=mock_strategy):
            with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
                result = instance_manager._get_hypervisor_vm_state(mock_vm_instance)

        assert result == "not_found"

    def test_returns_error_when_vm_not_found(self, instance_manager, mock_vm_instance, mock_vm_api):
        """Test returns 'error' when VM record cannot be found."""
        mock_vm_instance.vm = None
        mock_vm_api.get_vm_by_id.return_value = None

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            result = instance_manager._get_hypervisor_vm_state(mock_vm_instance)

        assert result == "error"

    def test_uses_strategy_for_virtualbox(self, instance_manager, mock_vm_instance):
        """Test uses identifier strategy for VirtualBox VMs."""
        mock_vm_instance.vm.hypervisor = "virtualbox"

        mock_strategy = MagicMock()
        mock_strategy.get_identifier.return_value = "vbox-uuid-123"
        mock_strategy.get_vm_state.return_value = "running"

        with patch('adare.backend.vm.instance_manager.get_identifier_strategy', return_value=mock_strategy):
            result = instance_manager._get_hypervisor_vm_state(mock_vm_instance)

        assert result == "running"
        mock_strategy.get_vm_state.assert_called_once_with("vbox-uuid-123")

    def test_uses_strategy_for_qemu(self, instance_manager, mock_vm_instance):
        """Test uses identifier strategy for QEMU VMs."""
        mock_vm_instance.vm.hypervisor = "qemu"

        mock_strategy = MagicMock()
        mock_strategy.get_identifier.return_value = "qemu-instance-name"
        mock_strategy.get_vm_state.return_value = "shutoff"

        with patch('adare.backend.vm.instance_manager.get_identifier_strategy', return_value=mock_strategy):
            result = instance_manager._get_hypervisor_vm_state(mock_vm_instance)

        assert result == "shutoff"


# === Tests for get_instance_stats ===

class TestGetInstanceStats:
    """Tests for get_instance_stats method."""

    def test_returns_correct_stats_structure(self, instance_manager, mock_vm_api, mock_vm_instance):
        """Test that stats contain expected keys."""
        mock_vm_api.get_all_vm_instances.return_value = [mock_vm_instance]

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            with patch.object(instance_manager, '_get_hypervisor_vm_state', return_value="running"):
                with patch.object(instance_manager, '_get_instance_disk_usage', return_value=10.5):
                    result = instance_manager.get_instance_stats()

        assert 'total_instances' in result
        assert 'running_instances' in result
        assert 'stopped_instances' in result
        assert 'total_disk_gb' in result
        assert 'top_disk_consumers' in result

    def test_counts_running_and_stopped_correctly(self, instance_manager, mock_vm_api):
        """Test that running and stopped instances are counted correctly."""
        instance1 = MagicMock()
        instance1.id = "id1"
        instance1.instance_name = "inst1"
        instance1.vm_id = "vm1"
        instance1.vm = MagicMock()
        instance1.vm.hypervisor = "virtualbox"
        instance1.vbox_uuid = "uuid1"

        instance2 = MagicMock()
        instance2.id = "id2"
        instance2.instance_name = "inst2"
        instance2.vm_id = "vm2"
        instance2.vm = MagicMock()
        instance2.vm.hypervisor = "virtualbox"
        instance2.vbox_uuid = "uuid2"

        mock_vm_api.get_all_vm_instances.return_value = [instance1, instance2]

        def get_state(instance):
            if instance.id == "id1":
                return "running"
            return "poweroff"

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            with patch.object(instance_manager, '_get_hypervisor_vm_state', side_effect=get_state):
                with patch.object(instance_manager, '_get_instance_disk_usage', return_value=0):
                    result = instance_manager.get_instance_stats()

        assert result['total_instances'] == 2
        assert result['running_instances'] == 1
        assert result['stopped_instances'] == 1

    def test_calculates_total_disk_usage(self, instance_manager, mock_vm_api, mock_vm_instance):
        """Test that total disk usage is calculated."""
        mock_vm_api.get_all_vm_instances.return_value = [mock_vm_instance]

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            with patch.object(instance_manager, '_get_hypervisor_vm_state', return_value="poweroff"):
                with patch.object(instance_manager, '_get_instance_disk_usage', return_value=25.5):
                    result = instance_manager.get_instance_stats()

        assert result['total_disk_gb'] == 25.5


# === Tests for release_instance (async) ===

class TestReleaseInstance:
    """Tests for release_instance async method."""

    @pytest.mark.asyncio
    async def test_marks_instance_as_available(self, instance_manager, mock_vm_api, mock_vm_instance):
        """Test that released instance is marked as available."""
        mock_vm_api.get_vm_instance_by_id.return_value = mock_vm_instance

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            await instance_manager.release_instance("test-instance-id")

        mock_vm_api.update_vm_instance.assert_called_once()
        call_args = mock_vm_api.update_vm_instance.call_args
        assert call_args[0][0] == "test-instance-id"
        assert call_args[1]['status'] == 'available'
        assert call_args[1]['current_experiment_run_id'] is None
        assert call_args[1]['websocket_port'] is None

    @pytest.mark.asyncio
    async def test_handles_missing_instance_gracefully(self, instance_manager, mock_vm_api):
        """Test that missing instance doesn't raise error."""
        mock_vm_api.get_vm_instance_by_id.return_value = None

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            # Should not raise
            await instance_manager.release_instance("nonexistent-id")

        mock_vm_api.update_vm_instance.assert_not_called()


# === Tests for cleanup_instance (async) ===

class TestCleanupInstance:
    """Tests for cleanup_instance async method."""

    @pytest.mark.asyncio
    async def test_raises_not_found_for_missing_instance(self, instance_manager, mock_vm_api):
        """Test raises InstanceNotFoundException for missing instance."""
        mock_vm_api.get_vm_instance_by_id.return_value = None

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            with pytest.raises(InstanceNotFoundException):
                await instance_manager.cleanup_instance("nonexistent-id")

    @pytest.mark.asyncio
    async def test_raises_state_exception_for_running_instance(self, instance_manager, mock_vm_api, mock_vm_instance):
        """Test raises InstanceStateException for running VM."""
        mock_vm_api.get_vm_instance_by_id.return_value = mock_vm_instance

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            with patch.object(instance_manager, '_get_hypervisor_vm_state', return_value="running"):
                with pytest.raises(InstanceStateException):
                    await instance_manager.cleanup_instance(mock_vm_instance.id)

    @pytest.mark.asyncio
    async def test_raises_state_exception_for_paused_instance(self, instance_manager, mock_vm_api, mock_vm_instance):
        """Test raises InstanceStateException for paused VM."""
        mock_vm_api.get_vm_instance_by_id.return_value = mock_vm_instance

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            with patch.object(instance_manager, '_get_hypervisor_vm_state', return_value="paused"):
                with pytest.raises(InstanceStateException):
                    await instance_manager.cleanup_instance(mock_vm_instance.id)

    @pytest.mark.asyncio
    async def test_deletes_stopped_instance(self, instance_manager, mock_vm_api, mock_vm_instance):
        """Test that stopped instance is deleted from database."""
        mock_vm_api.get_vm_instance_by_id.return_value = mock_vm_instance

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            with patch.object(instance_manager, '_get_hypervisor_vm_state', return_value="poweroff"):
                with patch.object(instance_manager, '_cleanup_hypervisor_instance', new_callable=AsyncMock):
                    await instance_manager.cleanup_instance(mock_vm_instance.id)

        mock_vm_api.delete_vm_instance.assert_called_once_with(mock_vm_instance.id)

    @pytest.mark.asyncio
    async def test_cleans_up_not_found_instance(self, instance_manager, mock_vm_api, mock_vm_instance):
        """Test that instance not found in hypervisor is cleaned up."""
        mock_vm_api.get_vm_instance_by_id.return_value = mock_vm_instance

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            with patch.object(instance_manager, '_get_hypervisor_vm_state', return_value="not_found"):
                with patch.object(instance_manager, '_cleanup_hypervisor_instance', new_callable=AsyncMock):
                    await instance_manager.cleanup_instance(mock_vm_instance.id)

        mock_vm_api.delete_vm_instance.assert_called_once()


# === Tests for cleanup_oldest_available_instance (async) ===

class TestCleanupOldestAvailableInstance:
    """Tests for cleanup_oldest_available_instance async method."""

    @pytest.mark.asyncio
    async def test_returns_false_when_no_available_instances(self, instance_manager, mock_vm_api):
        """Test returns False when no instances to clean up."""
        mock_vm_api.get_vm_instances_for_vm.return_value = []

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            result = await instance_manager.cleanup_oldest_available_instance("test-vm-id")

        assert result is False

    @pytest.mark.asyncio
    async def test_cleans_up_oldest_instance(self, instance_manager, mock_vm_api):
        """Test cleans up the oldest available instance."""
        older_instance = MagicMock()
        older_instance.id = "older-id"
        older_instance.instance_name = "older-instance"
        older_instance.last_used_at = datetime.now(UTC) - timedelta(days=2)

        newer_instance = MagicMock()
        newer_instance.id = "newer-id"
        newer_instance.instance_name = "newer-instance"
        newer_instance.last_used_at = datetime.now(UTC) - timedelta(hours=1)

        mock_vm_api.get_vm_instances_for_vm.return_value = [newer_instance, older_instance]

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            with patch.object(instance_manager, '_cleanup_hypervisor_instance', new_callable=AsyncMock):
                result = await instance_manager.cleanup_oldest_available_instance("test-vm-id")

        assert result is True
        mock_vm_api.delete_vm_instance.assert_called_once_with("older-id")


# === Tests for create_new_instance (async) ===

class TestCreateNewInstance:
    """Tests for create_new_instance async method."""

    @pytest.mark.asyncio
    async def test_raises_error_when_vm_not_found(self, instance_manager, mock_vm_api):
        """Test raises VMError when source VM not found."""
        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            with patch(VM_DATABASE_PATCH_PATH + '.get_vm_by_id', return_value=None):
                with patch.object(instance_manager, 'get_instance_count_for_vm', return_value=0):
                    with pytest.raises(VMError, match="not found"):
                        await instance_manager.create_new_instance("nonexistent-vm-id", "exp-id")

    @pytest.mark.asyncio
    async def test_raises_error_at_max_capacity_with_all_active(self, instance_manager, mock_vm_api, mock_vm_record):
        """Test raises VMError at max capacity with no available instances."""
        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            with patch(VM_DATABASE_PATCH_PATH + '.get_vm_by_id', return_value=mock_vm_record):
                with patch.object(instance_manager, 'get_instance_count_for_vm', return_value=20):
                    with patch.object(instance_manager, 'cleanup_oldest_available_instance',
                                     new_callable=AsyncMock, return_value=False):
                        with patch.object(instance_manager, 'cleanup_oldest_error_instance',
                                         new_callable=AsyncMock, return_value=False):
                            with pytest.raises(VMError, match="maximum instance capacity"):
                                await instance_manager.create_new_instance("test-vm-id", "exp-id")

    @pytest.mark.asyncio
    async def test_cleans_up_error_instance_when_at_max_capacity(self, instance_manager, mock_vm_api, mock_vm_record, mock_vm_instance):
        """Test cleans up error instance when at max capacity and no available instances."""
        mock_vm_api.get_vm_instance_by_name.return_value = mock_vm_instance
        mock_vm_api.get_vm_instance_by_id.return_value = mock_vm_instance

        cleanup_error_mock = AsyncMock(return_value=True)

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            with patch(VM_DATABASE_PATCH_PATH + '.get_vm_by_id', return_value=mock_vm_record):
                # At capacity (20)
                with patch.object(instance_manager, 'get_instance_count_for_vm', return_value=20):
                    # No available instances to clean up
                    with patch.object(instance_manager, 'cleanup_oldest_available_instance', 
                                     new_callable=AsyncMock, return_value=False):
                        # Should fall back to cleaning up error instances
                        with patch.object(instance_manager, 'cleanup_oldest_error_instance', cleanup_error_mock):
                            with patch('adare.backend.vm.instance_manager.reserve_port_atomically', return_value=18765):
                                result = await instance_manager.create_new_instance("test-vm-id", "exp-id123")

        assert result is not None
        cleanup_error_mock.assert_called_once_with("test-vm-id")

    @pytest.mark.asyncio
    async def test_cleans_up_when_at_max_capacity(self, instance_manager, mock_vm_api, mock_vm_record, mock_vm_instance):
        """Test cleans up instance when at max capacity."""
        mock_vm_api.get_vm_instance_by_name.return_value = mock_vm_instance
        mock_vm_api.get_vm_instance_by_id.return_value = mock_vm_instance

        cleanup_mock = AsyncMock(return_value=True)

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            with patch(VM_DATABASE_PATCH_PATH + '.get_vm_by_id', return_value=mock_vm_record):
                with patch.object(instance_manager, 'get_instance_count_for_vm', return_value=20):
                    with patch.object(instance_manager, 'cleanup_oldest_available_instance', cleanup_mock):
                        with patch('adare.backend.vm.instance_manager.reserve_port_atomically', return_value=18765):
                            result = await instance_manager.create_new_instance("test-vm-id", "exp-id123")

        assert result is not None
        cleanup_mock.assert_called_once_with("test-vm-id")


# === Tests for reuse_instance (async) ===

class TestReuseInstance:
    """Tests for reuse_instance async method."""

    @pytest.mark.asyncio
    async def test_updates_instance_status_to_active(self, instance_manager, mock_vm_api, mock_vm_instance):
        """Test that reused instance is marked as active."""
        mock_vm_instance.status = "available"
        mock_vm_instance.vbox_uuid = None  # Skip VirtualBox snapshot validation
        mock_vm_instance.base_snapshot_name = None  # Skip snapshot validation entirely
        mock_vm_api.get_vm_instance_by_id.return_value = mock_vm_instance
        mock_vm_api.get_all_vm_instances.return_value = []

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            result = await instance_manager.reuse_instance(mock_vm_instance, "new-experiment-id")

        mock_vm_api.update_vm_instance.assert_called_once()
        call_args = mock_vm_api.update_vm_instance.call_args
        assert call_args[1]['status'] == 'active'
        assert call_args[1]['current_experiment_run_id'] == 'new-experiment-id'

    @pytest.mark.asyncio
    async def test_allocates_fresh_websocket_port(self, instance_manager, mock_vm_api, mock_vm_instance):
        """Test that a fresh websocket port is allocated."""
        mock_vm_instance.status = "available"
        mock_vm_instance.vbox_uuid = None  # Skip VirtualBox snapshot validation
        mock_vm_instance.base_snapshot_name = None  # Skip snapshot validation entirely
        mock_vm_api.get_vm_instance_by_id.return_value = mock_vm_instance
        mock_vm_api.get_all_vm_instances.return_value = []

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            await instance_manager.reuse_instance(mock_vm_instance, "new-experiment-id")

        call_args = mock_vm_api.update_vm_instance.call_args
        assert call_args[1]['websocket_port'] is not None

    @pytest.mark.asyncio
    async def test_raises_error_when_no_ports_available(self, instance_manager, mock_vm_api, mock_vm_instance):
        """Test raises VMError when no websocket ports available."""
        mock_vm_instance.status = "available"
        mock_vm_instance.vbox_uuid = None
        mock_vm_instance.base_snapshot_name = None  # Skip snapshot validation entirely

        # Create instances using all ports
        used_instances = []
        from adare.backend.vm.port_manager import PORT_RANGE_START, PORT_RANGE_END
        for port in range(PORT_RANGE_START, PORT_RANGE_END + 1):
            inst = MagicMock()
            inst.status = 'active'
            inst.websocket_port = port
            used_instances.append(inst)

        mock_vm_api.get_all_vm_instances.return_value = used_instances
        mock_vm_api.get_vm_instance_by_id.return_value = mock_vm_instance

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            with pytest.raises(VMError, match="No available websocket ports"):
                await instance_manager.reuse_instance(mock_vm_instance, "new-experiment-id")


# === Tests for allocate_instance_for_experiment (async) ===

# Path to patch StageCtxManager - it's imported inside the method
STAGE_CTX_MANAGER_PATCH_PATH = 'adare.backend.experiment.stagectxmanager.StageCtxManager'


class TestAllocateInstanceForExperiment:
    """Tests for allocate_instance_for_experiment async method."""

    @pytest.fixture
    def mock_stage_context(self):
        """Create a mock stage context manager."""
        mock_stage_instance = MagicMock()
        mock_stage_instance.__enter__ = MagicMock(return_value=mock_stage_instance)
        mock_stage_instance.__exit__ = MagicMock(return_value=False)
        mock_stage_instance.stage = MagicMock()
        mock_stage_instance.stage.sub_msg = ""
        mock_stage_instance.set_status = MagicMock()
        return mock_stage_instance

    @pytest.mark.asyncio
    async def test_reuses_available_instance(self, instance_manager, mock_vm_api, mock_vm_instance, mock_stage_context):
        """Test reuses existing available instance when one exists."""
        mock_vm_instance.status = "available"
        mock_vm_instance.vbox_uuid = None

        mock_vm_api.get_vm_instances_for_vm.return_value = [mock_vm_instance]
        mock_vm_api.get_all_vm_instances.return_value = []
        mock_vm_api.get_vm_instance_by_id.return_value = mock_vm_instance

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            with patch.object(instance_manager, 'sync_instance_states', new_callable=AsyncMock, return_value=0):
                with patch(STAGE_CTX_MANAGER_PATCH_PATH, return_value=mock_stage_context):
                    result = await instance_manager.allocate_instance_for_experiment(
                        "test-vm-id", "experiment-123"
                    )

        assert result is not None

    @pytest.mark.asyncio
    async def test_creates_new_instance_when_none_available(self, instance_manager, mock_vm_api, mock_vm_record, mock_vm_instance, mock_stage_context):
        """Test creates new instance when no available instances."""
        mock_vm_api.get_vm_instances_for_vm.return_value = []
        mock_vm_api.get_vm_instance_by_name.return_value = mock_vm_instance
        mock_vm_api.get_vm_instance_by_id.return_value = mock_vm_instance

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            with patch(VM_DATABASE_PATCH_PATH + '.get_vm_by_id', return_value=mock_vm_record):
                with patch.object(instance_manager, 'sync_instance_states', new_callable=AsyncMock, return_value=0):
                    with patch.object(instance_manager, 'get_instance_count_for_vm', return_value=0):
                        with patch('adare.backend.vm.instance_manager.reserve_port_atomically', return_value=18765):
                            with patch(STAGE_CTX_MANAGER_PATCH_PATH, return_value=mock_stage_context):
                                result = await instance_manager.allocate_instance_for_experiment(
                                    "test-vm-id", "experiment-123"
                                )

        assert result is not None

    @pytest.mark.asyncio
    async def test_acquires_and_releases_lock(self, instance_manager, mock_vm_api, mock_vm_instance, mock_stage_context):
        """Test that lock is properly acquired and released."""
        mock_vm_instance.status = "available"
        mock_vm_instance.vbox_uuid = None

        mock_vm_api.get_vm_instances_for_vm.return_value = [mock_vm_instance]
        mock_vm_api.get_all_vm_instances.return_value = []
        mock_vm_api.get_vm_instance_by_id.return_value = mock_vm_instance

        # Create a tracking lock that records acquisition and release
        lock_acquired = threading.Event()
        lock_released = threading.Event()

        class TrackingLock:
            """A lock that tracks when it's acquired and released."""
            def __init__(self):
                self._real_lock = threading.Lock()

            def acquire(self, timeout=None):
                if timeout is not None:
                    result = self._real_lock.acquire(timeout=timeout)
                else:
                    result = self._real_lock.acquire()
                lock_acquired.set()
                return result

            def release(self):
                lock_released.set()
                return self._real_lock.release()

        # Replace the lock with our tracking lock
        original_lock = instance_manager._lock
        instance_manager._lock = TrackingLock()

        try:
            with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
                with patch.object(instance_manager, 'sync_instance_states', new_callable=AsyncMock, return_value=0):
                    with patch(STAGE_CTX_MANAGER_PATCH_PATH, return_value=mock_stage_context):
                        await instance_manager.allocate_instance_for_experiment(
                            "test-vm-id", "experiment-123"
                        )

            assert lock_acquired.is_set()
            assert lock_released.is_set()
        finally:
            # Restore original lock
            instance_manager._lock = original_lock


# === Tests for sync_instance_states (async) ===

class TestSyncInstanceStates:
    """Tests for sync_instance_states async method."""

    @pytest.mark.asyncio
    async def test_updates_stopped_instance_to_available(self, instance_manager, mock_vm_api, mock_vm_instance):
        """Test that stopped instances are marked as available."""
        mock_vm_instance.status = "active"
        mock_vm_api.get_vm_instances_for_vm.return_value = [mock_vm_instance]

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            with patch.object(instance_manager, '_get_hypervisor_vm_state', return_value="poweroff"):
                count = await instance_manager.sync_instance_states("test-vm-id")

        assert count == 1
        mock_vm_api.update_vm_instance.assert_called_once()
        call_args = mock_vm_api.update_vm_instance.call_args
        assert call_args[1]['status'] == 'available'

    @pytest.mark.asyncio
    async def test_updates_not_found_instance_to_available(self, instance_manager, mock_vm_api, mock_vm_instance):
        """Test that instances not found in hypervisor are marked as available."""
        mock_vm_instance.status = "active"
        mock_vm_api.get_vm_instances_for_vm.return_value = [mock_vm_instance]

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            with patch.object(instance_manager, '_get_hypervisor_vm_state', return_value="not_found"):
                count = await instance_manager.sync_instance_states("test-vm-id")

        assert count == 1

    @pytest.mark.asyncio
    async def test_does_not_update_running_instance(self, instance_manager, mock_vm_api, mock_vm_instance):
        """Test that running instances are not updated."""
        mock_vm_instance.status = "active"
        mock_vm_api.get_vm_instances_for_vm.return_value = [mock_vm_instance]

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            with patch.object(instance_manager, '_get_hypervisor_vm_state', return_value="running"):
                count = await instance_manager.sync_instance_states("test-vm-id")

        assert count == 0
        mock_vm_api.update_vm_instance.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_shutoff_qemu_state(self, instance_manager, mock_vm_api, mock_vm_instance):
        """Test handles QEMU 'shutoff' state (equivalent to poweroff)."""
        mock_vm_instance.status = "active"
        mock_vm_api.get_vm_instances_for_vm.return_value = [mock_vm_instance]

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            with patch.object(instance_manager, '_get_hypervisor_vm_state', return_value="shutoff"):
                count = await instance_manager.sync_instance_states("test-vm-id")

        assert count == 1


# === Tests for cleanup_old_instances (async) ===

class TestCleanupOldInstances:
    """Tests for cleanup_old_instances async method."""

    @pytest.mark.asyncio
    async def test_uses_default_cleanup_age(self, instance_manager, mock_vm_api):
        """Test uses CLEANUP_AGE_DAYS when no age specified."""
        mock_vm_api.get_old_vm_instances.return_value = []

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            await instance_manager.cleanup_old_instances()

        call_args = mock_vm_api.get_old_vm_instances.call_args
        cutoff = call_args[0][0]
        # Should be roughly 7 days ago (CLEANUP_AGE_DAYS)
        expected_cutoff = datetime.now(UTC) - timedelta(days=7)
        assert abs((cutoff - expected_cutoff).total_seconds()) < 60  # Within 1 minute

    @pytest.mark.asyncio
    async def test_uses_custom_cleanup_age(self, instance_manager, mock_vm_api):
        """Test uses custom age when specified."""
        mock_vm_api.get_old_vm_instances.return_value = []

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            await instance_manager.cleanup_old_instances(age_days=14)

        call_args = mock_vm_api.get_old_vm_instances.call_args
        cutoff = call_args[0][0]
        expected_cutoff = datetime.now(UTC) - timedelta(days=14)
        assert abs((cutoff - expected_cutoff).total_seconds()) < 60

    @pytest.mark.asyncio
    async def test_cleans_up_old_instances(self, instance_manager, mock_vm_api, mock_vm_instance):
        """Test that old instances are cleaned up."""
        mock_vm_instance.last_used_at = datetime.now(UTC) - timedelta(days=10)
        mock_vm_api.get_old_vm_instances.return_value = [mock_vm_instance]
        mock_vm_api.get_vm_instance_by_id.return_value = mock_vm_instance

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            with patch.object(instance_manager, '_get_hypervisor_vm_state', return_value="poweroff"):
                with patch.object(instance_manager, '_cleanup_hypervisor_instance', new_callable=AsyncMock):
                    await instance_manager.cleanup_old_instances()

        mock_vm_api.delete_vm_instance.assert_called_once_with(mock_vm_instance.id)


# === Tests for remove_all_instances (async) ===

class TestRemoveAllInstances:
    """Tests for remove_all_instances async method."""

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_instances(self, instance_manager, mock_vm_api):
        """Test returns empty list when no instances exist."""
        mock_vm_api.get_all_vm_instances.return_value = []

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            result = await instance_manager.remove_all_instances()

        assert result == []

    @pytest.mark.asyncio
    async def test_removes_stopped_instances(self, instance_manager, mock_vm_api, mock_vm_instance):
        """Test removes stopped instances and returns their IDs."""
        mock_vm_api.get_all_vm_instances.return_value = [mock_vm_instance]
        mock_vm_api.get_vm_instance_by_id.return_value = mock_vm_instance

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            with patch.object(instance_manager, '_get_hypervisor_vm_state', return_value="poweroff"):
                with patch.object(instance_manager, '_cleanup_hypervisor_instance', new_callable=AsyncMock):
                    result = await instance_manager.remove_all_instances()

        assert mock_vm_instance.id in result

    @pytest.mark.asyncio
    async def test_skips_running_instances(self, instance_manager, mock_vm_api, mock_vm_instance):
        """Test skips running instances without error."""
        mock_vm_api.get_all_vm_instances.return_value = [mock_vm_instance]
        mock_vm_api.get_vm_instance_by_id.return_value = mock_vm_instance

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            with patch.object(instance_manager, '_get_hypervisor_vm_state', return_value="running"):
                result = await instance_manager.remove_all_instances()

        assert result == []
        mock_vm_api.delete_vm_instance.assert_not_called()


# === Tests for Global Singleton Functions ===

class TestGlobalSingletonFunctions:
    """Tests for the global singleton functions."""

    @pytest.mark.asyncio
    async def test_allocate_vm_instance_for_experiment_uses_singleton(self):
        """Test that global function uses singleton instance."""
        with patch.object(_instance_manager, 'allocate_instance_for_experiment',
                         new_callable=AsyncMock) as mock_method:
            mock_method.return_value = MagicMock()
            await allocate_vm_instance_for_experiment("vm-id", "exp-id")

        mock_method.assert_called_once_with("vm-id", "exp-id")

    @pytest.mark.asyncio
    async def test_release_vm_instance_uses_singleton(self):
        """Test that global function uses singleton instance."""
        with patch.object(_instance_manager, 'release_instance',
                         new_callable=AsyncMock) as mock_method:
            await release_vm_instance("instance-id")

        mock_method.assert_called_once_with("instance-id")

    @pytest.mark.asyncio
    async def test_cleanup_vm_instance_uses_singleton(self):
        """Test that global function uses singleton instance."""
        with patch.object(_instance_manager, 'cleanup_instance',
                         new_callable=AsyncMock) as mock_method:
            await cleanup_vm_instance("instance-id")

        mock_method.assert_called_once_with("instance-id")

    @pytest.mark.asyncio
    async def test_cleanup_old_vm_instances_uses_singleton(self):
        """Test that global function uses singleton instance."""
        with patch.object(_instance_manager, 'cleanup_old_instances',
                         new_callable=AsyncMock) as mock_method:
            await cleanup_old_vm_instances(10)

        mock_method.assert_called_once_with(10)

    @pytest.mark.asyncio
    async def test_remove_all_instances_uses_singleton(self):
        """Test that global function uses singleton instance."""
        with patch.object(_instance_manager, 'remove_all_instances',
                         new_callable=AsyncMock) as mock_method:
            mock_method.return_value = []
            await remove_all_instances()

        mock_method.assert_called_once()

    def test_get_vm_instance_stats_uses_singleton(self):
        """Test that global function uses singleton instance."""
        with patch.object(_instance_manager, 'get_instance_stats') as mock_method:
            mock_method.return_value = {}
            get_vm_instance_stats()

        mock_method.assert_called_once()


# === Tests for Locking Behavior ===

class TestLockingBehavior:
    """Tests for thread locking behavior."""

    def test_instance_manager_has_lock(self, instance_manager):
        """Test that instance manager has a threading lock."""
        assert hasattr(instance_manager, '_lock')
        assert isinstance(instance_manager._lock, type(threading.Lock()))

    @pytest.mark.asyncio
    async def test_lock_timeout_raises_error(self, instance_manager, mock_vm_api):
        """Test that lock timeout raises VMError."""
        # Create a mock lock that always fails to acquire
        class FailingLock:
            """A lock that always fails to acquire (simulating timeout)."""
            def acquire(self, timeout=None):
                return False  # Simulate timeout

            def release(self):
                pass

        # Replace the lock with our failing lock
        original_lock = instance_manager._lock
        instance_manager._lock = FailingLock()

        try:
            with pytest.raises(VMError, match="Timeout acquiring instance manager lock"):
                await instance_manager.allocate_instance_for_experiment("vm-id", "exp-id")
        finally:
            # Restore original lock
            instance_manager._lock = original_lock


# === Tests for _cleanup_hypervisor_instance (async) ===

class TestCleanupHypervisorInstance:
    """Tests for _cleanup_hypervisor_instance async method."""

    @pytest.mark.asyncio
    async def test_calls_virtualbox_cleanup_for_vbox_vms(self, instance_manager, mock_vm_api, mock_vm_instance):
        """Test calls VirtualBox cleanup for VirtualBox VMs."""
        mock_vm_instance.vm.hypervisor = "virtualbox"

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            with patch.object(instance_manager, '_cleanup_virtualbox_vm', new_callable=AsyncMock) as mock_vbox:
                await instance_manager._cleanup_hypervisor_instance(mock_vm_instance)

        mock_vbox.assert_called_once_with(mock_vm_instance)

    @pytest.mark.asyncio
    async def test_calls_qemu_cleanup_for_qemu_vms(self, instance_manager, mock_vm_api, mock_vm_instance):
        """Test calls QEMU cleanup for QEMU VMs."""
        mock_vm_instance.vm.hypervisor = "qemu"

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            with patch.object(instance_manager, '_cleanup_qemu_vm', new_callable=AsyncMock) as mock_qemu:
                await instance_manager._cleanup_hypervisor_instance(mock_vm_instance)

        mock_qemu.assert_called_once_with(mock_vm_instance)

    @pytest.mark.asyncio
    async def test_handles_unknown_hypervisor(self, instance_manager, mock_vm_api, mock_vm_instance):
        """Test handles unknown hypervisor gracefully."""
        mock_vm_instance.vm.hypervisor = "unknown-hypervisor"

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            # Should not raise, just log warning
            await instance_manager._cleanup_hypervisor_instance(mock_vm_instance)


# === Tests for Backward Compatibility ===

class TestBackwardCompatibility:
    """Tests for backward compatibility aliases."""

    def test_get_virtualbox_vm_state_is_alias(self, instance_manager, mock_vm_instance):
        """Test that _get_virtualbox_vm_state is an alias for _get_hypervisor_vm_state."""
        mock_strategy = MagicMock()
        mock_strategy.get_identifier.return_value = "uuid"
        mock_strategy.get_vm_state.return_value = "running"

        with patch('adare.backend.vm.instance_manager.get_identifier_strategy', return_value=mock_strategy):
            result1 = instance_manager._get_virtualbox_vm_state(mock_vm_instance)
            result2 = instance_manager._get_hypervisor_vm_state(mock_vm_instance)

        assert result1 == result2

    @pytest.mark.asyncio
    async def test_cleanup_virtualbox_instance_is_alias(self, instance_manager, mock_vm_instance, mock_vm_api):
        """Test that _cleanup_virtualbox_instance is an alias for _cleanup_hypervisor_instance."""
        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            with patch.object(instance_manager, '_cleanup_virtualbox_vm', new_callable=AsyncMock):
                await instance_manager._cleanup_virtualbox_instance(mock_vm_instance)

        # Should call the correct method based on hypervisor type


# === Tests for edge cases ===

class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_generate_instance_name_short_experiment_id(self, instance_manager):
        """Test instance name generation with experiment ID shorter than 8 chars."""
        result = instance_manager._generate_instance_name("vm", "abc")
        assert result == "vm_exp_abc"

    def test_generate_instance_name_empty_experiment_id(self, instance_manager):
        """Test instance name generation with empty experiment ID."""
        result = instance_manager._generate_instance_name("vm", "")
        assert result == "vm_exp_"

    @pytest.mark.asyncio
    async def test_sync_already_available_instance(self, instance_manager, mock_vm_api, mock_vm_instance):
        """Test sync does not update already available instance."""
        mock_vm_instance.status = "available"
        mock_vm_api.get_vm_instances_for_vm.return_value = [mock_vm_instance]

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            with patch.object(instance_manager, '_get_hypervisor_vm_state', return_value="poweroff"):
                count = await instance_manager.sync_instance_states("test-vm-id")

        # Already available, no update needed
        assert count == 0
        mock_vm_api.update_vm_instance.assert_not_called()

    def test_stats_with_no_instances(self, instance_manager, mock_vm_api):
        """Test stats with empty instance list."""
        mock_vm_api.get_all_vm_instances.return_value = []

        with patch(VM_API_PATCH_PATH, return_value=mock_vm_api):
            result = instance_manager.get_instance_stats()

        assert result['total_instances'] == 0
        assert result['running_instances'] == 0
        assert result['stopped_instances'] == 0
        assert result['total_disk_gb'] == 0
        assert result['top_disk_consumers'] == []
