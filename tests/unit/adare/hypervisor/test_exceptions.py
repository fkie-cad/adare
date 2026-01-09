"""
Comprehensive unit tests for adare.hypervisor.exceptions module.

Tests all exception classes in the hypervisor exception hierarchy:
- HypervisorException (base)
- VMOperationException and subclasses
- SnapshotOperationException and subclasses
- InstanceOperationException and subclasses
- DiskOperationException and subclasses
- UnsupportedFeatureException
"""
import pytest
from adare.hypervisor.exceptions import (
    # Base exception
    HypervisorException,
    # VM Operation exceptions
    VMOperationException,
    VMNotFoundException,
    VMImportException,
    VMStartException,
    VMStopException,
    VMAlreadyRunningException,
    GuestAgentTimeoutException,
    # Snapshot Operation exceptions
    SnapshotOperationException,
    SnapshotNotFoundException,
    SnapshotCreationException,
    SnapshotRestoreException,
    # Instance Operation exceptions
    InstanceOperationException,
    PortAllocationException,
    InstanceNotFoundException,
    InstanceStateException,
    # Disk Operation exceptions
    DiskOperationException,
    DiskConversionException,
    DiskNotFoundException,
    # Feature Support exceptions
    UnsupportedFeatureException,
)


# =============================================================================
# HypervisorException Tests
# =============================================================================

class TestHypervisorException:
    """Tests for the base HypervisorException class."""

    def test_init_with_message(self):
        """Test HypervisorException can be initialized with a message."""
        exc = HypervisorException("Test error message")
        assert str(exc) == "Test error message"

    def test_inherits_from_exception(self):
        """Test HypervisorException inherits from Exception."""
        exc = HypervisorException("Test")
        assert isinstance(exc, Exception)

    def test_can_be_raised_and_caught(self):
        """Test HypervisorException can be raised and caught."""
        with pytest.raises(HypervisorException) as exc_info:
            raise HypervisorException("Hypervisor error")
        assert "Hypervisor error" in str(exc_info.value)


# =============================================================================
# VMOperationException Tests
# =============================================================================

class TestVMOperationException:
    """Tests for VMOperationException and its subclasses."""

    def test_init_with_all_parameters(self):
        """Test VMOperationException initialization with all parameters."""
        exc = VMOperationException(
            vm_identifier="test-vm",
            operation="custom_op",
            reason="something went wrong"
        )
        assert exc.vm_identifier == "test-vm"
        assert exc.operation == "custom_op"
        assert exc.reason == "something went wrong"
        assert "test-vm" in str(exc)
        assert "custom_op" in str(exc)
        assert "something went wrong" in str(exc)

    def test_init_with_custom_message(self):
        """Test VMOperationException with custom message overrides default."""
        exc = VMOperationException(
            vm_identifier="test-vm",
            operation="test_op",
            reason="error reason",
            message="Custom error message"
        )
        assert str(exc) == "Custom error message"
        # Attributes should still be set
        assert exc.vm_identifier == "test-vm"
        assert exc.operation == "test_op"
        assert exc.reason == "error reason"

    def test_default_message_format(self):
        """Test the default message format."""
        exc = VMOperationException(
            vm_identifier="my-vm",
            operation="start",
            reason="timeout"
        )
        expected = "VM 'my-vm': start failed - timeout"
        assert str(exc) == expected

    def test_inherits_from_hypervisor_exception(self):
        """Test VMOperationException inherits from HypervisorException."""
        exc = VMOperationException("vm", "op", "reason")
        assert isinstance(exc, HypervisorException)


class TestVMNotFoundException:
    """Tests for VMNotFoundException."""

    def test_init_with_default_reason(self):
        """Test VMNotFoundException with default reason."""
        exc = VMNotFoundException("missing-vm")
        assert exc.vm_identifier == "missing-vm"
        assert exc.operation == "lookup"
        assert exc.reason == "VM not found"
        assert "missing-vm" in str(exc)
        assert "lookup" in str(exc)

    def test_init_with_custom_reason(self):
        """Test VMNotFoundException with custom reason."""
        exc = VMNotFoundException("missing-vm", reason="UUID not in registry")
        assert exc.reason == "UUID not in registry"
        assert "UUID not in registry" in str(exc)

    def test_inherits_from_vm_operation_exception(self):
        """Test VMNotFoundException inherits from VMOperationException."""
        exc = VMNotFoundException("vm")
        assert isinstance(exc, VMOperationException)
        assert isinstance(exc, HypervisorException)


class TestVMImportException:
    """Tests for VMImportException."""

    def test_init(self):
        """Test VMImportException initialization."""
        exc = VMImportException("import-vm", "OVA file corrupted")
        assert exc.vm_identifier == "import-vm"
        assert exc.operation == "import"
        assert exc.reason == "OVA file corrupted"

    def test_message_format(self):
        """Test VMImportException message format."""
        exc = VMImportException("vm123", "disk space insufficient")
        assert "vm123" in str(exc)
        assert "import" in str(exc)
        assert "disk space insufficient" in str(exc)


class TestVMStartException:
    """Tests for VMStartException."""

    def test_init(self):
        """Test VMStartException initialization."""
        exc = VMStartException("start-vm", "host resources exhausted")
        assert exc.vm_identifier == "start-vm"
        assert exc.operation == "start"
        assert exc.reason == "host resources exhausted"

    def test_message_format(self):
        """Test VMStartException message format."""
        exc = VMStartException("vm-fail", "CPU not available")
        expected = "VM 'vm-fail': start failed - CPU not available"
        assert str(exc) == expected


class TestVMStopException:
    """Tests for VMStopException."""

    def test_init(self):
        """Test VMStopException initialization."""
        exc = VMStopException("stop-vm", "guest not responding")
        assert exc.vm_identifier == "stop-vm"
        assert exc.operation == "stop"
        assert exc.reason == "guest not responding"

    def test_message_format(self):
        """Test VMStopException message format."""
        exc = VMStopException("vm-hang", "ACPI shutdown timeout")
        expected = "VM 'vm-hang': stop failed - ACPI shutdown timeout"
        assert str(exc) == expected


class TestVMAlreadyRunningException:
    """Tests for VMAlreadyRunningException."""

    def test_init(self):
        """Test VMAlreadyRunningException initialization."""
        exc = VMAlreadyRunningException("running-vm")
        assert exc.vm_identifier == "running-vm"
        assert exc.operation == "start"
        assert exc.reason == "VM is already running"

    def test_message_format(self):
        """Test VMAlreadyRunningException message format."""
        exc = VMAlreadyRunningException("active-vm")
        expected = "VM 'active-vm': start failed - VM is already running"
        assert str(exc) == expected


class TestGuestAgentTimeoutException:
    """Tests for GuestAgentTimeoutException."""

    def test_init(self):
        """Test GuestAgentTimeoutException initialization."""
        exc = GuestAgentTimeoutException("guest-vm", 60.0)
        assert exc.vm_identifier == "guest-vm"
        assert exc.operation == "guest_agent_connect"
        assert exc.timeout_seconds == 60.0
        assert "60.0s" in exc.reason

    def test_message_format(self):
        """Test GuestAgentTimeoutException message format."""
        exc = GuestAgentTimeoutException("agent-vm", 30.5)
        assert "agent-vm" in str(exc)
        assert "guest_agent_connect" in str(exc)
        assert "30.5s" in str(exc)

    @pytest.mark.parametrize("timeout", [0.1, 1.0, 30, 120.5, 3600])
    def test_various_timeout_values(self, timeout):
        """Test GuestAgentTimeoutException with various timeout values."""
        exc = GuestAgentTimeoutException("vm", timeout)
        assert exc.timeout_seconds == timeout
        assert str(timeout) in str(exc)


# =============================================================================
# SnapshotOperationException Tests
# =============================================================================

class TestSnapshotOperationException:
    """Tests for SnapshotOperationException and its subclasses."""

    def test_init_with_all_parameters(self):
        """Test SnapshotOperationException initialization with all parameters."""
        exc = SnapshotOperationException(
            vm_identifier="test-vm",
            snapshot_name="snap1",
            operation="custom",
            reason="custom reason"
        )
        assert exc.vm_identifier == "test-vm"
        assert exc.snapshot_name == "snap1"
        assert exc.operation == "custom"
        assert exc.reason == "custom reason"

    def test_init_with_custom_message(self):
        """Test SnapshotOperationException with custom message overrides default."""
        exc = SnapshotOperationException(
            vm_identifier="vm",
            snapshot_name="snap",
            operation="op",
            reason="reason",
            message="Custom snapshot message"
        )
        assert str(exc) == "Custom snapshot message"

    def test_default_message_format(self):
        """Test SnapshotOperationException default message format."""
        exc = SnapshotOperationException(
            vm_identifier="my-vm",
            snapshot_name="my-snapshot",
            operation="delete",
            reason="snapshot is protected"
        )
        expected = "Snapshot 'my-snapshot' on VM 'my-vm': delete failed - snapshot is protected"
        assert str(exc) == expected

    def test_inherits_from_hypervisor_exception(self):
        """Test SnapshotOperationException inherits from HypervisorException."""
        exc = SnapshotOperationException("vm", "snap", "op", "reason")
        assert isinstance(exc, HypervisorException)


class TestSnapshotNotFoundException:
    """Tests for SnapshotNotFoundException."""

    def test_init(self):
        """Test SnapshotNotFoundException initialization."""
        exc = SnapshotNotFoundException("vm1", "missing-snap")
        assert exc.vm_identifier == "vm1"
        assert exc.snapshot_name == "missing-snap"
        assert exc.operation == "lookup"
        assert exc.reason == "Snapshot not found"

    def test_message_format(self):
        """Test SnapshotNotFoundException message format."""
        exc = SnapshotNotFoundException("test-vm", "old-snap")
        assert "old-snap" in str(exc)
        assert "test-vm" in str(exc)
        assert "Snapshot not found" in str(exc)


class TestSnapshotCreationException:
    """Tests for SnapshotCreationException."""

    def test_init(self):
        """Test SnapshotCreationException initialization."""
        exc = SnapshotCreationException("vm", "new-snap", "disk full")
        assert exc.vm_identifier == "vm"
        assert exc.snapshot_name == "new-snap"
        assert exc.operation == "create"
        assert exc.reason == "disk full"

    def test_message_format(self):
        """Test SnapshotCreationException message format."""
        exc = SnapshotCreationException("vm2", "snap2", "IO error")
        expected = "Snapshot 'snap2' on VM 'vm2': create failed - IO error"
        assert str(exc) == expected


class TestSnapshotRestoreException:
    """Tests for SnapshotRestoreException."""

    def test_init(self):
        """Test SnapshotRestoreException initialization."""
        exc = SnapshotRestoreException("vm", "restore-snap", "VM must be stopped")
        assert exc.vm_identifier == "vm"
        assert exc.snapshot_name == "restore-snap"
        assert exc.operation == "restore"
        assert exc.reason == "VM must be stopped"

    def test_message_format(self):
        """Test SnapshotRestoreException message format."""
        exc = SnapshotRestoreException("vm3", "snap3", "corruption detected")
        expected = "Snapshot 'snap3' on VM 'vm3': restore failed - corruption detected"
        assert str(exc) == expected


# =============================================================================
# InstanceOperationException Tests
# =============================================================================

class TestInstanceOperationException:
    """Tests for InstanceOperationException and its subclasses."""

    def test_inherits_from_hypervisor_exception(self):
        """Test InstanceOperationException inherits from HypervisorException."""
        exc = InstanceOperationException("Instance error")
        assert isinstance(exc, HypervisorException)

    def test_can_be_raised_and_caught(self):
        """Test InstanceOperationException can be raised and caught."""
        with pytest.raises(InstanceOperationException):
            raise InstanceOperationException("Instance failed")


class TestPortAllocationException:
    """Tests for PortAllocationException."""

    def test_init_without_port_range(self):
        """Test PortAllocationException without port range."""
        exc = PortAllocationException("no ports available")
        assert exc.port_range is None
        assert "Port allocation failed: no ports available" == str(exc)

    def test_init_with_port_range(self):
        """Test PortAllocationException with port range."""
        exc = PortAllocationException("all ports in use", port_range=(5000, 5100))
        assert exc.port_range == (5000, 5100)
        assert "5000-5100" in str(exc)
        assert "all ports in use" in str(exc)

    def test_message_format_with_range(self):
        """Test PortAllocationException message format with range."""
        exc = PortAllocationException("race condition", port_range=(10000, 10050))
        expected = "Port allocation failed in range 10000-10050: race condition"
        assert str(exc) == expected

    @pytest.mark.parametrize("port_range", [
        (1024, 2048),
        (49152, 65535),
        (8000, 8100),
    ])
    def test_various_port_ranges(self, port_range):
        """Test PortAllocationException with various port ranges."""
        exc = PortAllocationException("error", port_range=port_range)
        assert exc.port_range == port_range
        assert f"{port_range[0]}-{port_range[1]}" in str(exc)


class TestInstanceNotFoundException:
    """Tests for InstanceNotFoundException."""

    def test_init(self):
        """Test InstanceNotFoundException initialization."""
        exc = InstanceNotFoundException("inst-12345")
        assert exc.instance_identifier == "inst-12345"

    def test_message_format(self):
        """Test InstanceNotFoundException message format."""
        exc = InstanceNotFoundException("my-instance")
        expected = "VM instance 'my-instance' not found in database"
        assert str(exc) == expected


class TestInstanceStateException:
    """Tests for InstanceStateException."""

    def test_init(self):
        """Test InstanceStateException initialization."""
        exc = InstanceStateException("inst-1", "stopped", ["running", "paused"])
        assert exc.instance_identifier == "inst-1"
        assert exc.current_state == "stopped"
        assert exc.expected_states == ["running", "paused"]

    def test_message_format(self):
        """Test InstanceStateException message format."""
        exc = InstanceStateException("vm-inst", "starting", ["running"])
        assert "vm-inst" in str(exc)
        assert "starting" in str(exc)
        assert "running" in str(exc)

    def test_multiple_expected_states(self):
        """Test InstanceStateException with multiple expected states."""
        exc = InstanceStateException("inst", "error", ["running", "paused", "stopped"])
        assert "running, paused, stopped" in str(exc)

    @pytest.mark.parametrize("current,expected", [
        ("stopped", ["running"]),
        ("running", ["stopped", "paused"]),
        ("error", ["running", "stopped", "paused"]),
    ])
    def test_various_state_combinations(self, current, expected):
        """Test InstanceStateException with various state combinations."""
        exc = InstanceStateException("inst", current, expected)
        assert exc.current_state == current
        assert exc.expected_states == expected


# =============================================================================
# DiskOperationException Tests
# =============================================================================

class TestDiskOperationException:
    """Tests for DiskOperationException and its subclasses."""

    def test_init(self):
        """Test DiskOperationException initialization."""
        exc = DiskOperationException("/path/to/disk.vdi", "resize", "insufficient space")
        assert exc.disk_path == "/path/to/disk.vdi"
        assert exc.operation == "resize"
        assert exc.reason == "insufficient space"

    def test_message_format(self):
        """Test DiskOperationException message format."""
        exc = DiskOperationException("/disks/test.qcow2", "read", "permission denied")
        expected = "Disk '/disks/test.qcow2': read failed - permission denied"
        assert str(exc) == expected

    def test_inherits_from_hypervisor_exception(self):
        """Test DiskOperationException inherits from HypervisorException."""
        exc = DiskOperationException("/path", "op", "reason")
        assert isinstance(exc, HypervisorException)


class TestDiskConversionException:
    """Tests for DiskConversionException."""

    def test_init(self):
        """Test DiskConversionException initialization."""
        exc = DiskConversionException("/disk.vmdk", "vmdk", "qcow2", "unsupported feature")
        assert exc.disk_path == "/disk.vmdk"
        assert exc.source_format == "vmdk"
        assert exc.target_format == "qcow2"
        assert exc.reason == "unsupported feature"
        assert "convert" in exc.operation

    def test_message_format(self):
        """Test DiskConversionException message format."""
        exc = DiskConversionException("/test.vdi", "vdi", "raw", "encryption not supported")
        assert "/test.vdi" in str(exc)
        assert "vdi -> raw" in str(exc)
        assert "encryption not supported" in str(exc)

    @pytest.mark.parametrize("source,target", [
        ("vmdk", "qcow2"),
        ("vdi", "raw"),
        ("qcow2", "vmdk"),
        ("raw", "vdi"),
    ])
    def test_various_format_conversions(self, source, target):
        """Test DiskConversionException with various format conversions."""
        exc = DiskConversionException("/disk", source, target, "error")
        assert exc.source_format == source
        assert exc.target_format == target
        assert f"{source} -> {target}" in str(exc)


class TestDiskNotFoundException:
    """Tests for DiskNotFoundException."""

    def test_init(self):
        """Test DiskNotFoundException initialization."""
        exc = DiskNotFoundException("/missing/disk.vdi")
        assert exc.disk_path == "/missing/disk.vdi"
        assert exc.operation == "lookup"
        assert exc.reason == "Disk file not found"

    def test_message_format(self):
        """Test DiskNotFoundException message format."""
        exc = DiskNotFoundException("/nonexistent/path.qcow2")
        expected = "Disk '/nonexistent/path.qcow2': lookup failed - Disk file not found"
        assert str(exc) == expected


# =============================================================================
# UnsupportedFeatureException Tests
# =============================================================================

class TestUnsupportedFeatureException:
    """Tests for UnsupportedFeatureException."""

    def test_init(self):
        """Test UnsupportedFeatureException initialization."""
        exc = UnsupportedFeatureException("VirtualBox", "nested virtualization")
        assert exc.hypervisor == "VirtualBox"
        assert exc.feature == "nested virtualization"

    def test_message_format(self):
        """Test UnsupportedFeatureException message format."""
        exc = UnsupportedFeatureException("QEMU", "GPU passthrough")
        expected = "Hypervisor 'QEMU' does not support feature: GPU passthrough"
        assert str(exc) == expected

    def test_inherits_from_hypervisor_exception(self):
        """Test UnsupportedFeatureException inherits from HypervisorException."""
        exc = UnsupportedFeatureException("hyper", "feature")
        assert isinstance(exc, HypervisorException)

    @pytest.mark.parametrize("hypervisor,feature", [
        ("VirtualBox", "UEFI boot"),
        ("QEMU", "snapshots"),
        ("Hyper-V", "live migration"),
        ("VMware", "TPM 2.0"),
    ])
    def test_various_hypervisor_features(self, hypervisor, feature):
        """Test UnsupportedFeatureException with various hypervisor/feature combinations."""
        exc = UnsupportedFeatureException(hypervisor, feature)
        assert exc.hypervisor == hypervisor
        assert exc.feature == feature
        assert hypervisor in str(exc)
        assert feature in str(exc)


# =============================================================================
# Exception Inheritance Tests
# =============================================================================

class TestExceptionInheritance:
    """Tests for exception inheritance - catching base class catches subclasses."""

    def test_catch_vm_operation_exception_catches_vm_not_found(self):
        """Test catching VMOperationException catches VMNotFoundException."""
        with pytest.raises(VMOperationException):
            raise VMNotFoundException("vm")

    def test_catch_vm_operation_exception_catches_vm_start(self):
        """Test catching VMOperationException catches VMStartException."""
        with pytest.raises(VMOperationException):
            raise VMStartException("vm", "reason")

    def test_catch_vm_operation_exception_catches_vm_stop(self):
        """Test catching VMOperationException catches VMStopException."""
        with pytest.raises(VMOperationException):
            raise VMStopException("vm", "reason")

    def test_catch_vm_operation_exception_catches_vm_import(self):
        """Test catching VMOperationException catches VMImportException."""
        with pytest.raises(VMOperationException):
            raise VMImportException("vm", "reason")

    def test_catch_vm_operation_exception_catches_vm_already_running(self):
        """Test catching VMOperationException catches VMAlreadyRunningException."""
        with pytest.raises(VMOperationException):
            raise VMAlreadyRunningException("vm")

    def test_catch_vm_operation_exception_catches_guest_agent_timeout(self):
        """Test catching VMOperationException catches GuestAgentTimeoutException."""
        with pytest.raises(VMOperationException):
            raise GuestAgentTimeoutException("vm", 30)

    def test_catch_snapshot_operation_exception_catches_snapshot_not_found(self):
        """Test catching SnapshotOperationException catches SnapshotNotFoundException."""
        with pytest.raises(SnapshotOperationException):
            raise SnapshotNotFoundException("vm", "snap")

    def test_catch_snapshot_operation_exception_catches_snapshot_creation(self):
        """Test catching SnapshotOperationException catches SnapshotCreationException."""
        with pytest.raises(SnapshotOperationException):
            raise SnapshotCreationException("vm", "snap", "reason")

    def test_catch_snapshot_operation_exception_catches_snapshot_restore(self):
        """Test catching SnapshotOperationException catches SnapshotRestoreException."""
        with pytest.raises(SnapshotOperationException):
            raise SnapshotRestoreException("vm", "snap", "reason")

    def test_catch_instance_operation_exception_catches_port_allocation(self):
        """Test catching InstanceOperationException catches PortAllocationException."""
        with pytest.raises(InstanceOperationException):
            raise PortAllocationException("reason")

    def test_catch_instance_operation_exception_catches_instance_not_found(self):
        """Test catching InstanceOperationException catches InstanceNotFoundException."""
        with pytest.raises(InstanceOperationException):
            raise InstanceNotFoundException("inst")

    def test_catch_instance_operation_exception_catches_instance_state(self):
        """Test catching InstanceOperationException catches InstanceStateException."""
        with pytest.raises(InstanceOperationException):
            raise InstanceStateException("inst", "state", ["expected"])

    def test_catch_disk_operation_exception_catches_disk_conversion(self):
        """Test catching DiskOperationException catches DiskConversionException."""
        with pytest.raises(DiskOperationException):
            raise DiskConversionException("/path", "vdi", "qcow2", "reason")

    def test_catch_disk_operation_exception_catches_disk_not_found(self):
        """Test catching DiskOperationException catches DiskNotFoundException."""
        with pytest.raises(DiskOperationException):
            raise DiskNotFoundException("/path")

    def test_catch_hypervisor_exception_catches_all(self):
        """Test catching HypervisorException catches all hypervisor exceptions."""
        exceptions_to_test = [
            HypervisorException("base"),
            VMOperationException("vm", "op", "reason"),
            VMNotFoundException("vm"),
            VMImportException("vm", "reason"),
            VMStartException("vm", "reason"),
            VMStopException("vm", "reason"),
            VMAlreadyRunningException("vm"),
            GuestAgentTimeoutException("vm", 30),
            SnapshotOperationException("vm", "snap", "op", "reason"),
            SnapshotNotFoundException("vm", "snap"),
            SnapshotCreationException("vm", "snap", "reason"),
            SnapshotRestoreException("vm", "snap", "reason"),
            InstanceOperationException("instance error"),
            PortAllocationException("reason"),
            InstanceNotFoundException("inst"),
            InstanceStateException("inst", "state", ["expected"]),
            DiskOperationException("/path", "op", "reason"),
            DiskConversionException("/path", "src", "dst", "reason"),
            DiskNotFoundException("/path"),
            UnsupportedFeatureException("hyper", "feature"),
        ]
        for exc in exceptions_to_test:
            with pytest.raises(HypervisorException):
                raise exc


# =============================================================================
# Parametrized Tests for Similar Exception Patterns
# =============================================================================

class TestParametrizedVMExceptions:
    """Parametrized tests for VM operation exceptions with similar patterns."""

    @pytest.mark.parametrize("exception_class,vm_id,reason,expected_op", [
        (VMImportException, "import-vm", "file not found", "import"),
        (VMStartException, "start-vm", "insufficient resources", "start"),
        (VMStopException, "stop-vm", "process hung", "stop"),
    ])
    def test_vm_operation_subclass_pattern(self, exception_class, vm_id, reason, expected_op):
        """Test VM operation subclasses follow consistent pattern."""
        exc = exception_class(vm_id, reason)
        assert exc.vm_identifier == vm_id
        assert exc.operation == expected_op
        assert exc.reason == reason
        assert isinstance(exc, VMOperationException)
        assert isinstance(exc, HypervisorException)


class TestParametrizedSnapshotExceptions:
    """Parametrized tests for snapshot operation exceptions."""

    @pytest.mark.parametrize("exception_class,vm_id,snap_name,reason,expected_op", [
        (SnapshotCreationException, "vm1", "snap1", "disk full", "create"),
        (SnapshotRestoreException, "vm2", "snap2", "vm running", "restore"),
    ])
    def test_snapshot_operation_subclass_pattern(
        self, exception_class, vm_id, snap_name, reason, expected_op
    ):
        """Test snapshot operation subclasses follow consistent pattern."""
        exc = exception_class(vm_id, snap_name, reason)
        assert exc.vm_identifier == vm_id
        assert exc.snapshot_name == snap_name
        assert exc.operation == expected_op
        assert exc.reason == reason
        assert isinstance(exc, SnapshotOperationException)
        assert isinstance(exc, HypervisorException)


class TestParametrizedInstanceExceptions:
    """Parametrized tests for instance operation exceptions."""

    @pytest.mark.parametrize("exception_class", [
        PortAllocationException,
        InstanceNotFoundException,
        InstanceStateException,
    ])
    def test_instance_exceptions_inherit_correctly(self, exception_class):
        """Test all instance exceptions inherit from InstanceOperationException."""
        # Create exception with appropriate arguments based on class
        if exception_class == PortAllocationException:
            exc = exception_class("reason")
        elif exception_class == InstanceNotFoundException:
            exc = exception_class("inst-id")
        else:  # InstanceStateException
            exc = exception_class("inst-id", "current", ["expected"])

        assert isinstance(exc, InstanceOperationException)
        assert isinstance(exc, HypervisorException)


class TestParametrizedDiskExceptions:
    """Parametrized tests for disk operation exceptions."""

    @pytest.mark.parametrize("disk_path", [
        "/absolute/path/disk.vdi",
        "/home/user/vms/disk.qcow2",
        "/var/lib/libvirt/images/test.raw",
        "relative/path.vmdk",
        "simple.vdi",
    ])
    def test_disk_operation_with_various_paths(self, disk_path):
        """Test DiskOperationException handles various disk paths."""
        exc = DiskOperationException(disk_path, "test", "error")
        assert exc.disk_path == disk_path
        assert disk_path in str(exc)
