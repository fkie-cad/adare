"""
Unit tests for VmApi class.

Tests database operations for VM management including CRUD operations for VMs,
VM instances, snapshots, and port allocation. Uses mock SQLAlchemy sessions.
"""
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from datetime import datetime, UTC
from pathlib import Path
import sys


# === Fixtures ===

@pytest.fixture(scope="module")
def mock_db_setup():
    """Set up mocks before importing VmApi."""
    with patch.dict(sys.modules, {'adare.config.database': MagicMock()}):
        yield


def create_vm_api():
    """Factory function to create VmApi with mocked dependencies."""
    with patch('adare.config.database.get_global_database_location', return_value=MagicMock()):
        with patch('adare.database.api.base.GlobalDatabaseApi.__init__', return_value=None):
            from adare.database.api.vm import VmApi
            api = VmApi.__new__(VmApi)
            # Create a persistent mock session
            mock_session = MagicMock()
            api._session = mock_session
            api._engine = MagicMock()
            # Override context manager to preserve session
            api.__enter__ = MagicMock(return_value=api)
            api.__exit__ = MagicMock(return_value=None)
            return api


@pytest.fixture
def vm_api():
    """Create a VmApi instance with mocked database connection."""
    return create_vm_api()


# === Mock Model Factories ===

def create_mock_vm(
    vm_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
    name="test-vm",
    file="/path/to/vm.ova",
    hash="abc123def456",
    description="Test VM",
    hypervisor="virtualbox",
    osinfo=None,
    osinfo_id=None,
):
    """Create a mock Vm for testing."""
    vm = MagicMock()
    vm.id = vm_id
    vm.name = name
    vm.file = file
    vm.hash = hash
    vm.description = description
    vm.hypervisor = hypervisor
    vm.osinfo = osinfo
    vm.osinfo_id = osinfo_id
    return vm


def create_mock_osinfo(
    osinfo_id="01ARZ3NDEKTSV4RRFFQ69G5OSI",
    platform="linux",
    os="Ubuntu",
    distribution="ubuntu",
    version="22.04",
    language="en",
    architecture="x86_64",
):
    """Create a mock OsInfo for testing."""
    osinfo = MagicMock()
    osinfo.id = osinfo_id
    osinfo.platform = platform
    osinfo.os = os
    osinfo.distribution = distribution
    osinfo.version = version
    osinfo.language = language
    osinfo.architecture = architecture
    return osinfo


def create_mock_vm_instance(
    instance_id="01ARZ3NDEKTSV4RRFFQ69G5INS",
    vm_id="01ARZ3NDEKTSV4RRFFQ69G5FAV",
    instance_name="test-vm-instance",
    current_experiment_run_id="run_123",
    websocket_port=8765,
    status="active",
    created_at=None,
    last_used_at=None,
    vm=None,
):
    """Create a mock VmInstance for testing."""
    instance = MagicMock()
    instance.id = instance_id
    instance.vm_id = vm_id
    instance.instance_name = instance_name
    instance.current_experiment_run_id = current_experiment_run_id
    instance.websocket_port = websocket_port
    instance.status = status
    instance.created_at = created_at or datetime.now(UTC)
    instance.last_used_at = last_used_at or datetime.now(UTC)
    instance.vm = vm
    return instance


def create_mock_vm_snapshot(
    snapshot_id="01ARZ3NDEKTSV4RRFFQ69G5SNP",
    vm_instance_id="01ARZ3NDEKTSV4RRFFQ69G5INS",
    name="base-snapshot",
    snapshot_type="base",
    description="Base snapshot",
):
    """Create a mock VmSnapshot for testing."""
    snapshot = MagicMock()
    snapshot.id = snapshot_id
    snapshot.vm_instance_id = vm_instance_id
    snapshot.name = name
    snapshot.snapshot_type = snapshot_type
    snapshot.description = description
    return snapshot


# === INITIALIZATION TESTS ===

class TestVmApiInitialization:
    """Tests for VmApi initialization."""

    def test_init_creates_session(self):
        """VmApi initialization creates database session."""
        with patch('adare.config.database.get_global_database_location', return_value=Path('/tmp/test.db')):
            with patch('adare.database.api.base.GlobalDatabaseApi.__init__') as mock_init:
                mock_init.return_value = None
                from adare.database.api.vm import VmApi
                api = VmApi.__new__(VmApi)
                api._session = MagicMock()
                # Verify the API object is created
                assert api._session is not None


class TestVmApiContextManager:
    """Tests for VmApi context manager functionality."""

    def test_context_manager_enters_and_exits(self, vm_api):
        """Context manager enters and exits properly."""
        # The vm_api fixture has mocked __enter__ and __exit__
        with vm_api:
            pass

        vm_api.__enter__.assert_called()
        vm_api.__exit__.assert_called()


# === GET VM TESTS ===

class TestGetVmById:
    """Tests for get_vm_by_id method."""

    def test_returns_vm_when_found(self, vm_api):
        """Returns VM when found by ID."""
        mock_vm = create_mock_vm()
        mock_query = MagicMock()
        mock_query.options.return_value.filter.return_value.first.return_value = mock_vm
        vm_api._session.query.return_value = mock_query

        result = vm_api.get_vm_by_id("01ARZ3NDEKTSV4RRFFQ69G5FAV")

        assert result == mock_vm

    def test_returns_none_when_not_found(self, vm_api):
        """Returns None when VM not found."""
        mock_query = MagicMock()
        mock_query.options.return_value.filter.return_value.first.return_value = None
        vm_api._session.query.return_value = mock_query

        result = vm_api.get_vm_by_id("nonexistent_id")

        assert result is None

    def test_calls_expunge_when_vm_found(self, vm_api):
        """Calls expunge when VM is found."""
        mock_vm = create_mock_vm()
        mock_query = MagicMock()
        mock_query.options.return_value.filter.return_value.first.return_value = mock_vm
        vm_api._session.query.return_value = mock_query

        vm_api.get_vm_by_id("01ARZ3NDEKTSV4RRFFQ69G5FAV")

        vm_api._session.expunge.assert_called_with(mock_vm)


class TestGetVmByName:
    """Tests for get_vm_by_name method."""

    def test_returns_vm_when_found(self, vm_api):
        """Returns VM when found by name."""
        mock_vm = create_mock_vm(name="my-test-vm")
        mock_query = MagicMock()
        mock_query.options.return_value.filter_by.return_value.first.return_value = mock_vm
        vm_api._session.query.return_value = mock_query

        result = vm_api.get_vm_by_name("my-test-vm")

        assert result == mock_vm
        assert result.name == "my-test-vm"

    def test_returns_none_when_not_found(self, vm_api):
        """Returns None when VM not found by name."""
        mock_query = MagicMock()
        mock_query.options.return_value.filter_by.return_value.first.return_value = None
        vm_api._session.query.return_value = mock_query

        result = vm_api.get_vm_by_name("nonexistent-vm")

        assert result is None

    def test_calls_expunge_when_vm_found(self, vm_api):
        """Calls expunge when VM is found."""
        mock_vm = create_mock_vm()
        mock_query = MagicMock()
        mock_query.options.return_value.filter_by.return_value.first.return_value = mock_vm
        vm_api._session.query.return_value = mock_query

        vm_api.get_vm_by_name("test-vm")

        vm_api._session.expunge.assert_called_with(mock_vm)


class TestGetVmByHash:
    """Tests for get_vm_by_hash method."""

    def test_returns_vm_when_found(self, vm_api):
        """Returns VM when found by hash."""
        mock_vm = create_mock_vm(hash="abc123def456")
        mock_query = MagicMock()
        mock_query.options.return_value.filter_by.return_value.first.return_value = mock_vm
        vm_api._session.query.return_value = mock_query

        result = vm_api.get_vm_by_hash("abc123def456")

        assert result == mock_vm

    def test_returns_none_when_not_found(self, vm_api):
        """Returns None when VM not found by hash."""
        mock_query = MagicMock()
        mock_query.options.return_value.filter_by.return_value.first.return_value = None
        vm_api._session.query.return_value = mock_query

        result = vm_api.get_vm_by_hash("nonexistent_hash")

        assert result is None


# === GET ALL VMS TESTS ===

class TestGetAllVms:
    """Tests for get_all_vms method."""

    def test_returns_all_vms(self, vm_api):
        """Returns all VMs from database."""
        mock_vms = [
            create_mock_vm(vm_id="id1", name="vm1"),
            create_mock_vm(vm_id="id2", name="vm2"),
            create_mock_vm(vm_id="id3", name="vm3"),
        ]
        mock_query = MagicMock()
        mock_query.options.return_value.all.return_value = mock_vms
        vm_api._session.query.return_value = mock_query

        result = vm_api.get_all_vms()

        assert len(result) == 3
        assert result[0].name == "vm1"
        assert result[1].name == "vm2"
        assert result[2].name == "vm3"

    def test_returns_empty_list_when_no_vms(self, vm_api):
        """Returns empty list when no VMs exist."""
        mock_query = MagicMock()
        mock_query.options.return_value.all.return_value = []
        vm_api._session.query.return_value = mock_query

        result = vm_api.get_all_vms()

        assert result == []

    def test_expunges_all_vms_from_session(self, vm_api):
        """Expunges all VMs from session."""
        mock_vms = [create_mock_vm(vm_id="id1"), create_mock_vm(vm_id="id2")]
        mock_query = MagicMock()
        mock_query.options.return_value.all.return_value = mock_vms
        vm_api._session.query.return_value = mock_query

        vm_api.get_all_vms()

        assert vm_api._session.expunge.call_count == 2


# === GET ALL VM INSTANCES TESTS ===

class TestGetAllVmInstances:
    """Tests for get_all_vm_instances method."""

    def test_returns_all_vm_instances(self, vm_api):
        """Returns all VM instances from database."""
        mock_instances = [
            create_mock_vm_instance(instance_id="id1", instance_name="inst1"),
            create_mock_vm_instance(instance_id="id2", instance_name="inst2"),
        ]
        mock_query = MagicMock()
        mock_query.options.return_value.all.return_value = mock_instances
        vm_api._session.query.return_value = mock_query

        result = vm_api.get_all_vm_instances()

        assert len(result) == 2

    def test_returns_empty_list_when_no_instances(self, vm_api):
        """Returns empty list when no VM instances exist."""
        mock_query = MagicMock()
        mock_query.options.return_value.all.return_value = []
        vm_api._session.query.return_value = mock_query

        result = vm_api.get_all_vm_instances()

        assert result == []


# === CREATE VM TESTS ===

class TestCreateVm:
    """Tests for create_vm method."""

    def test_creates_new_vm_with_valid_file(self, vm_api):
        """Creates new VM when file is valid and no conflicts."""
        # Mock the validation and file operations
        vm_api.validate_vm_file = MagicMock()
        vm_api.get_vm_by_name = MagicMock(return_value=None)
        vm_api.get_vm_by_hash = MagicMock(return_value=None)
        vm_api._copy_vm_file = MagicMock(return_value=Path("/storage/test-vm.ova"))

        mock_created_vm = create_mock_vm(name="new-vm")

        # Mock session operations
        vm_api._session.add = MagicMock()
        vm_api._session.flush = MagicMock()

        # After create, get_vm_by_name should return the new VM
        vm_api.get_vm_by_name = MagicMock(side_effect=[None, mock_created_vm])

        result = vm_api.create_vm(
            project_path=Path("/project"),
            name="new-vm",
            file_path=Path("/path/to/vm.ova"),
            file_hash="abc123",
            description="New test VM",
            hypervisor="virtualbox"
        )

        vm_api.validate_vm_file.assert_called_once()

    def test_returns_existing_vm_when_name_and_hash_match(self, vm_api):
        """Returns existing VM when name and hash both match."""
        existing_vm = create_mock_vm(vm_id="existing_id", name="existing-vm", hash="abc123")

        vm_api.validate_vm_file = MagicMock()
        vm_api.get_vm_by_name = MagicMock(return_value=existing_vm)
        vm_api.get_vm_by_hash = MagicMock(return_value=existing_vm)

        result = vm_api.create_vm(
            project_path=Path("/project"),
            name="existing-vm",
            file_path=Path("/path/to/vm.ova"),
            file_hash="abc123"
        )

        assert result == existing_vm

    def test_raises_error_when_name_exists_with_different_hash(self, vm_api):
        """Raises VMNameConflictError when name exists with different hash."""
        from adare.database.api.vm import VMNameConflictError

        existing_vm = create_mock_vm(vm_id="existing_id", name="test-vm", hash="different_hash")

        vm_api.validate_vm_file = MagicMock()
        vm_api.get_vm_by_name = MagicMock(return_value=existing_vm)
        vm_api.get_vm_by_hash = MagicMock(return_value=None)

        with pytest.raises(VMNameConflictError):
            vm_api.create_vm(
                project_path=Path("/project"),
                name="test-vm",
                file_path=Path("/path/to/vm.ova"),
                file_hash="new_hash"
            )

    def test_returns_existing_vm_when_hash_matches_different_name(self, vm_api):
        """Returns existing VM when hash matches but name differs."""
        existing_vm = create_mock_vm(vm_id="existing_id", name="other-name", hash="abc123")

        vm_api.validate_vm_file = MagicMock()
        vm_api.get_vm_by_name = MagicMock(return_value=None)
        vm_api.get_vm_by_hash = MagicMock(return_value=existing_vm)

        result = vm_api.create_vm(
            project_path=Path("/project"),
            name="new-name",
            file_path=Path("/path/to/vm.ova"),
            file_hash="abc123"
        )

        assert result == existing_vm

    def test_uses_no_copy_mode_when_specified(self, vm_api):
        """Uses no_copy mode when specified."""
        vm_api.validate_vm_file = MagicMock()
        vm_api.get_vm_by_name = MagicMock(return_value=None)
        vm_api.get_vm_by_hash = MagicMock(return_value=None)
        vm_api._copy_vm_file = MagicMock()

        mock_created_vm = create_mock_vm(name="new-vm")
        vm_api._session.add = MagicMock()
        vm_api._session.flush = MagicMock()

        # Need to return None first, then the created VM
        vm_api.get_vm_by_name = MagicMock(side_effect=[None, mock_created_vm])

        vm_api.create_vm(
            project_path=Path("/project"),
            name="new-vm",
            file_path=Path("/path/to/vm.ova"),
            file_hash="abc123",
            no_copy=True
        )

        # _copy_vm_file should not be called in no_copy mode
        vm_api._copy_vm_file.assert_not_called()


# === UPDATE VM TESTS ===

class TestUpdateVmName:
    """Tests for update_vm_name method."""

    def test_updates_vm_name(self, vm_api):
        """Updates VM name successfully."""
        mock_vm = create_mock_vm(name="old-name")
        vm_api._session.query.return_value.filter_by.return_value.first.return_value = mock_vm

        result = vm_api.update_vm_name("vm_id", "new-name")

        assert result is True
        assert mock_vm.name == "new-name"
        vm_api._session.commit.assert_called()

    def test_returns_false_when_vm_not_found(self, vm_api):
        """Returns False when VM not found."""
        vm_api._session.query.return_value.filter_by.return_value.first.return_value = None

        result = vm_api.update_vm_name("nonexistent_id", "new-name")

        assert result is False


# === DELETE VM TESTS ===

class TestDeleteVm:
    """Tests for delete_vm method."""

    def test_deletes_vm_successfully(self, vm_api):
        """Deletes VM successfully."""
        mock_vm = create_mock_vm()
        vm_api._session.query.return_value.filter_by.return_value.first.return_value = mock_vm

        result = vm_api.delete_vm("vm_id")

        assert result is True
        vm_api._session.delete.assert_called_with(mock_vm)
        vm_api._session.commit.assert_called()

    def test_raises_error_when_vm_not_found(self, vm_api):
        """Raises VMNotFoundError when VM not found."""
        from adare.database.api.vm import VMNotFoundError

        vm_api._session.query.return_value.filter_by.return_value.first.return_value = None

        with pytest.raises(VMNotFoundError):
            vm_api.delete_vm("nonexistent_id")


# === CREATE VM INSTANCE TESTS ===

class TestCreateVmInstance:
    """Tests for create_vm_instance method."""

    def test_creates_vm_instance(self, vm_api):
        """Creates VM instance with correct attributes."""
        mock_instance = create_mock_vm_instance()
        mock_query = MagicMock()
        mock_query.options.return_value.filter_by.return_value.first.return_value = mock_instance
        vm_api._session.query.return_value = mock_query

        result = vm_api.create_vm_instance(
            vm_id="vm_123",
            instance_name="test-instance",
            experiment_run_id="run_123",
            websocket_port=8765
        )

        vm_api._session.add.assert_called()

    def test_sets_default_status_to_active(self, vm_api):
        """Sets default status to 'active'."""
        mock_instance = create_mock_vm_instance(status="active")
        mock_query = MagicMock()
        mock_query.options.return_value.filter_by.return_value.first.return_value = mock_instance
        vm_api._session.query.return_value = mock_query

        result = vm_api.create_vm_instance(
            vm_id="vm_123",
            instance_name="test-instance",
            experiment_run_id="run_123",
            websocket_port=8765
        )

        # Verify the instance was created with correct status
        call_args = vm_api._session.add.call_args
        created_instance = call_args[0][0]
        assert created_instance.status == "active"


# === UPDATE VM INSTANCE TESTS ===

class TestUpdateVmInstance:
    """Tests for update_vm_instance method."""

    def test_updates_vm_instance_attributes(self, vm_api):
        """Updates VM instance attributes."""
        mock_instance = create_mock_vm_instance(status="active")
        vm_api._session.query.return_value.filter_by.return_value.first.return_value = mock_instance

        vm_api.update_vm_instance("instance_id", status="available", websocket_port=9999)

        assert mock_instance.status == "available"
        assert mock_instance.websocket_port == 9999
        vm_api._session.commit.assert_called()

    def test_raises_error_when_instance_not_found(self, vm_api):
        """Raises VMNotFoundError when instance not found."""
        from adare.database.api.vm import VMNotFoundError

        vm_api._session.query.return_value.filter_by.return_value.first.return_value = None

        with pytest.raises(VMNotFoundError):
            vm_api.update_vm_instance("nonexistent_id", status="available")


# === GET VM INSTANCE TESTS ===

class TestGetVmInstanceById:
    """Tests for get_vm_instance_by_id method."""

    def test_returns_instance_when_found(self, vm_api):
        """Returns VM instance when found."""
        mock_instance = create_mock_vm_instance()
        mock_query = MagicMock()
        mock_query.options.return_value.filter_by.return_value.first.return_value = mock_instance
        vm_api._session.query.return_value = mock_query

        result = vm_api.get_vm_instance_by_id("instance_id")

        assert result == mock_instance

    def test_returns_none_when_not_found(self, vm_api):
        """Returns None when instance not found."""
        mock_query = MagicMock()
        mock_query.options.return_value.filter_by.return_value.first.return_value = None
        vm_api._session.query.return_value = mock_query

        result = vm_api.get_vm_instance_by_id("nonexistent_id")

        assert result is None


class TestGetVmInstanceByName:
    """Tests for get_vm_instance_by_name method."""

    def test_returns_instance_when_found(self, vm_api):
        """Returns VM instance when found by name."""
        mock_instance = create_mock_vm_instance(instance_name="my-instance")
        mock_query = MagicMock()
        mock_query.options.return_value.filter_by.return_value.first.return_value = mock_instance
        vm_api._session.query.return_value = mock_query

        result = vm_api.get_vm_instance_by_name("my-instance")

        assert result == mock_instance

    def test_returns_none_when_not_found(self, vm_api):
        """Returns None when instance not found by name."""
        mock_query = MagicMock()
        mock_query.options.return_value.filter_by.return_value.first.return_value = None
        vm_api._session.query.return_value = mock_query

        result = vm_api.get_vm_instance_by_name("nonexistent-instance")

        assert result is None


class TestGetVmInstancesForVm:
    """Tests for get_vm_instances_for_vm method."""

    def test_returns_instances_for_vm(self, vm_api):
        """Returns all instances for a VM."""
        mock_instances = [
            create_mock_vm_instance(instance_id="id1"),
            create_mock_vm_instance(instance_id="id2"),
        ]
        mock_query = MagicMock()
        mock_query.options.return_value.filter_by.return_value.all.return_value = mock_instances
        mock_query.options.return_value.filter_by.return_value.filter_by.return_value.all.return_value = mock_instances
        vm_api._session.query.return_value = mock_query

        result = vm_api.get_vm_instances_for_vm("vm_id")

        assert len(result) == 2

    def test_filters_by_status_when_provided(self, vm_api):
        """Filters instances by status when provided."""
        mock_instances = [create_mock_vm_instance(status="active")]
        mock_query = MagicMock()
        mock_filter = MagicMock()
        mock_filter.filter_by.return_value.all.return_value = mock_instances
        mock_query.options.return_value.filter_by.return_value = mock_filter
        vm_api._session.query.return_value = mock_query

        result = vm_api.get_vm_instances_for_vm("vm_id", status="active")

        assert len(result) == 1


class TestGetOldVmInstances:
    """Tests for get_old_vm_instances method."""

    def test_returns_old_instances(self, vm_api):
        """Returns instances older than cutoff date."""
        cutoff = datetime(2024, 1, 1)
        mock_instances = [create_mock_vm_instance()]
        mock_query = MagicMock()
        mock_query.options.return_value.filter.return_value.all.return_value = mock_instances
        mock_query.options.return_value.filter.return_value.filter_by.return_value.all.return_value = mock_instances
        vm_api._session.query.return_value = mock_query

        result = vm_api.get_old_vm_instances(cutoff)

        assert len(result) == 1


class TestDeleteVmInstance:
    """Tests for delete_vm_instance method."""

    def test_deletes_instance_successfully(self, vm_api):
        """Deletes VM instance successfully."""
        mock_instance = create_mock_vm_instance()
        vm_api._session.query.return_value.filter_by.return_value.first.return_value = mock_instance

        result = vm_api.delete_vm_instance("instance_id")

        assert result is True
        vm_api._session.delete.assert_called_with(mock_instance)

    def test_raises_error_when_instance_not_found(self, vm_api):
        """Raises VMNotFoundError when instance not found."""
        from adare.database.api.vm import VMNotFoundError

        vm_api._session.query.return_value.filter_by.return_value.first.return_value = None

        with pytest.raises(VMNotFoundError):
            vm_api.delete_vm_instance("nonexistent_id")


# === PORT ALLOCATION TESTS ===

class TestGetWebsocketPortForInstance:
    """Tests for get_websocket_port_for_instance method."""

    def test_returns_port_for_active_instance(self, vm_api):
        """Returns websocket port for active instance."""
        mock_instance = create_mock_vm_instance(
            instance_name="test-instance",
            websocket_port=8765,
            status="active"
        )
        vm_api.get_vm_instance_by_name = MagicMock(return_value=mock_instance)

        result = vm_api.get_websocket_port_for_instance("test-instance")

        assert result == 8765

    def test_returns_none_for_nonexistent_instance(self, vm_api):
        """Returns None for nonexistent instance."""
        vm_api.get_vm_instance_by_name = MagicMock(return_value=None)

        result = vm_api.get_websocket_port_for_instance("nonexistent")

        assert result is None

    def test_returns_none_for_inactive_instance(self, vm_api):
        """Returns None for inactive instance."""
        mock_instance = create_mock_vm_instance(
            status="available",
            websocket_port=8765
        )
        vm_api.get_vm_instance_by_name = MagicMock(return_value=mock_instance)

        result = vm_api.get_websocket_port_for_instance("test-instance")

        assert result is None

    def test_returns_none_when_no_port_allocated(self, vm_api):
        """Returns None when no port is allocated."""
        mock_instance = create_mock_vm_instance(
            status="active",
            websocket_port=None
        )
        vm_api.get_vm_instance_by_name = MagicMock(return_value=mock_instance)

        result = vm_api.get_websocket_port_for_instance("test-instance")

        assert result is None


# === SNAPSHOT RECORD TESTS ===

class TestCreateInstanceSnapshotRecord:
    """Tests for create_instance_snapshot_record method."""

    def test_creates_snapshot_record(self, vm_api):
        """Creates snapshot record successfully."""
        result = vm_api.create_instance_snapshot_record(
            vm_instance_id="instance_123",
            snapshot_name="base-snapshot",
            snapshot_type="base",
            description="Base snapshot for testing"
        )

        assert result is True
        vm_api._session.add.assert_called()
        vm_api._session.commit.assert_called()

    def test_creates_experiment_snapshot(self, vm_api):
        """Creates experiment snapshot record."""
        result = vm_api.create_instance_snapshot_record(
            vm_instance_id="instance_123",
            snapshot_name="experiment-snapshot",
            snapshot_type="experiment",
            experiment_id="exp_123"
        )

        assert result is True


class TestGetSnapshotsForInstance:
    """Tests for get_snapshots_for_instance method."""

    def test_returns_all_snapshots_for_instance(self, vm_api):
        """Returns all snapshots for VM instance."""
        mock_snapshots = [
            create_mock_vm_snapshot(name="snap1"),
            create_mock_vm_snapshot(name="snap2"),
        ]
        vm_api._session.query.return_value.filter_by.return_value.all.return_value = mock_snapshots

        result = vm_api.get_snapshots_for_instance("instance_123")

        assert len(result) == 2

    def test_returns_empty_list_when_no_snapshots(self, vm_api):
        """Returns empty list when no snapshots exist."""
        vm_api._session.query.return_value.filter_by.return_value.all.return_value = []

        result = vm_api.get_snapshots_for_instance("instance_123")

        assert result == []


class TestDeleteInstanceSnapshotRecord:
    """Tests for delete_instance_snapshot_record method."""

    def test_deletes_snapshot_record(self, vm_api):
        """Deletes snapshot record successfully."""
        mock_snapshot = create_mock_vm_snapshot()
        vm_api._session.query.return_value.filter_by.return_value.first.return_value = mock_snapshot

        result = vm_api.delete_instance_snapshot_record("instance_123", "base-snapshot")

        assert result is True
        vm_api._session.delete.assert_called_with(mock_snapshot)

    def test_returns_true_when_snapshot_not_found(self, vm_api):
        """Returns True even when snapshot not found (idempotent)."""
        vm_api._session.query.return_value.filter_by.return_value.first.return_value = None

        result = vm_api.delete_instance_snapshot_record("instance_123", "nonexistent")

        assert result is True


# === DEPRECATED METHOD TESTS ===

class TestDeprecatedMethods:
    """Tests for deprecated methods."""

    def test_create_snapshot_record_delegates_to_instance_method(self, vm_api):
        """create_snapshot_record delegates to create_instance_snapshot_record."""
        vm_api.create_instance_snapshot_record = MagicMock(return_value=True)

        result = vm_api.create_snapshot_record(
            vm_instance_id="instance_123",
            snapshot_name="snap",
            snapshot_type="base"
        )

        assert result is True
        vm_api.create_instance_snapshot_record.assert_called_once_with(
            vm_instance_id="instance_123",
            snapshot_name="snap",
            snapshot_type="base",
            experiment_id=None,
            description=None
        )

    def test_get_snapshots_for_vm_returns_empty_list(self, vm_api):
        """get_snapshots_for_vm returns empty list (deprecated)."""
        result = vm_api.get_snapshots_for_vm("vm_id")

        assert result == []

    def test_delete_snapshot_record_returns_false(self, vm_api):
        """delete_snapshot_record returns False (deprecated)."""
        result = vm_api.delete_snapshot_record("vm_id", "snapshot")

        assert result is False


# === OS INFO TESTS ===

class TestCreateOsInfo:
    """Tests for create_osinfo method."""

    def test_creates_osinfo(self, vm_api):
        """Creates OsInfo successfully."""
        result = vm_api.create_osinfo(
            platform="linux",
            os="Ubuntu",
            distribution="ubuntu",
            version="22.04"
        )

        vm_api._session.add.assert_called()
        vm_api._session.flush.assert_called()


# === VALIDATION TESTS ===

class TestValidateVmFile:
    """Tests for validate_vm_file method."""

    def test_validates_virtualbox_ova(self, vm_api):
        """Validates VirtualBox OVA file."""
        mock_validator = MagicMock()
        mock_validator.get_supported_extensions.return_value = ['.ova']
        mock_validator.validate_file = MagicMock()

        with patch('adare.database.api.vm.VMValidatorFactory.get_validator', return_value=mock_validator):
            vm_api.validate_vm_file(
                file_path=Path("/path/to/vm.ova"),
                name="test-vm",
                hypervisor="virtualbox"
            )

        mock_validator.validate_file.assert_called_once()

    def test_raises_error_for_unsupported_extension(self, vm_api):
        """Raises VMValidationError for unsupported file extension."""
        from adare.database.api.vm import VMValidationError

        mock_validator = MagicMock()
        mock_validator.get_supported_extensions.return_value = ['.ova']

        with patch('adare.database.api.vm.VMValidatorFactory.get_validator', return_value=mock_validator):
            with pytest.raises(VMValidationError):
                vm_api.validate_vm_file(
                    file_path=Path("/path/to/vm.qcow2"),
                    name="test-vm",
                    hypervisor="virtualbox"
                )


# === IS EXTERNAL VM TESTS ===

class TestIsVmExternal:
    """Tests for is_vm_external method."""

    def test_returns_false_when_vm_not_found(self, vm_api):
        """Returns False when VM not found."""
        vm_api.get_vm_by_id = MagicMock(return_value=None)

        result = vm_api.is_vm_external("nonexistent_id")

        assert result is False

    def test_returns_true_for_external_vm(self, vm_api):
        """Returns True for VM outside managed storage."""
        mock_vm = create_mock_vm(file="/external/path/vm.ova")
        vm_api.get_vm_by_id = MagicMock(return_value=mock_vm)

        with patch('adare.database.api.vm.VMS_DIR', Path("/managed/vms")):
            result = vm_api.is_vm_external("vm_id")

        assert result is True


# === EDGE CASES ===

class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_get_available_vms_returns_all_vms(self, vm_api):
        """get_available_vms returns all VMs."""
        mock_vms = [create_mock_vm(), create_mock_vm(vm_id="id2")]
        mock_query = MagicMock()
        mock_query.options.return_value.all.return_value = mock_vms
        vm_api._session.query.return_value = mock_query

        result = vm_api.get_available_vms()

        assert len(result) == 2

    def test_suggest_similar_vms_returns_suggestions(self, vm_api):
        """suggest_similar_vms returns suggestions."""
        mock_vms = [
            create_mock_vm(name="windows-10"),
            create_mock_vm(name="windows-11", vm_id="id2"),
            create_mock_vm(name="ubuntu-22", vm_id="id3"),
        ]
        mock_query = MagicMock()
        mock_query.options.return_value.all.return_value = mock_vms
        vm_api._session.query.return_value = mock_query
        vm_api.get_all_vms = MagicMock(return_value=mock_vms)

        mock_suggestion = MagicMock()
        mock_suggestion.name = "windows-10"

        with patch('adare.database.api.vm.suggest_similar_vm_names', return_value=[mock_suggestion]):
            result = vm_api.suggest_similar_vms("windows")

        assert len(result) == 1
        assert result[0].name == "windows-10"
