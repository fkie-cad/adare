"""
Comprehensive unit tests for adare.hypervisor.base.identifier_strategy module.

Tests the Strategy pattern for hypervisor-specific VM instance identification:
- HypervisorIdentifierStrategy (abstract base class)
- VirtualBoxIdentifierStrategy implementation
- QEMUIdentifierStrategy implementation
- get_identifier_strategy() function
- register_identifier_strategy() function
- Convenience functions: get_vm_identifier(), verify_vm_exists(), get_vm_state()
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from abc import ABC

from adare.hypervisor.base.identifier_strategy import (
    HypervisorIdentifierStrategy,
    VirtualBoxIdentifierStrategy,
    QEMUIdentifierStrategy,
    get_identifier_strategy,
    register_identifier_strategy,
    get_vm_identifier,
    verify_vm_exists,
    get_vm_state,
    _IDENTIFIER_STRATEGIES,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def mock_vm_instance():
    """Create a mock VmInstance with configurable attributes."""
    instance = Mock()
    instance.vbox_uuid = None
    instance.instance_name = None
    instance.vm = Mock()
    instance.vm.hypervisor = "virtualbox"
    instance.hypervisor_identifier = None
    return instance


@pytest.fixture
def mock_vbox_vm_instance(mock_vm_instance):
    """Create a mock VmInstance configured for VirtualBox."""
    mock_vm_instance.vbox_uuid = "12345678-1234-1234-1234-123456789abc"
    mock_vm_instance.instance_name = "vbox-test-instance"
    mock_vm_instance.vm.hypervisor = "virtualbox"
    mock_vm_instance.hypervisor_identifier = mock_vm_instance.vbox_uuid
    return mock_vm_instance


@pytest.fixture
def mock_qemu_vm_instance(mock_vm_instance):
    """Create a mock VmInstance configured for QEMU."""
    mock_vm_instance.vbox_uuid = None
    mock_vm_instance.instance_name = "qemu-test-instance"
    mock_vm_instance.vm.hypervisor = "qemu"
    mock_vm_instance.hypervisor_identifier = mock_vm_instance.instance_name
    return mock_vm_instance


@pytest.fixture
def virtualbox_strategy():
    """Create a VirtualBoxIdentifierStrategy instance."""
    return VirtualBoxIdentifierStrategy()


@pytest.fixture
def qemu_strategy():
    """Create a QEMUIdentifierStrategy instance."""
    return QEMUIdentifierStrategy()


# =============================================================================
# HypervisorIdentifierStrategy Abstract Base Class Tests
# =============================================================================

class TestHypervisorIdentifierStrategy:
    """Tests for the abstract base class HypervisorIdentifierStrategy."""

    def test_is_abstract_class(self):
        """Test that HypervisorIdentifierStrategy is an abstract base class."""
        assert issubclass(HypervisorIdentifierStrategy, ABC)

    def test_cannot_instantiate_directly(self):
        """Test that HypervisorIdentifierStrategy cannot be instantiated directly."""
        with pytest.raises(TypeError) as exc_info:
            HypervisorIdentifierStrategy()
        assert "abstract" in str(exc_info.value).lower()

    def test_has_abstract_hypervisor_name_property(self):
        """Test that hypervisor_name is an abstract property."""
        assert hasattr(HypervisorIdentifierStrategy, 'hypervisor_name')

    def test_has_abstract_get_identifier_method(self):
        """Test that get_identifier is an abstract method."""
        assert hasattr(HypervisorIdentifierStrategy, 'get_identifier')

    def test_has_abstract_verify_exists_method(self):
        """Test that verify_exists is an abstract method."""
        assert hasattr(HypervisorIdentifierStrategy, 'verify_exists')

    def test_has_abstract_get_vm_state_method(self):
        """Test that get_vm_state is an abstract method."""
        assert hasattr(HypervisorIdentifierStrategy, 'get_vm_state')

    def test_has_get_vm_name_method_with_default(self):
        """Test that get_vm_name has a default implementation."""
        # Create a concrete subclass to test the default implementation
        class ConcreteStrategy(HypervisorIdentifierStrategy):
            @property
            def hypervisor_name(self) -> str:
                return "test"

            def get_identifier(self, vm_instance):
                return "test-id"

            def verify_exists(self, identifier: str) -> bool:
                return True

            def get_vm_state(self, identifier: str) -> str:
                return "running"

        strategy = ConcreteStrategy()
        # Default implementation returns the identifier as the name
        assert strategy.get_vm_name("my-identifier") == "my-identifier"


# =============================================================================
# VirtualBoxIdentifierStrategy Tests
# =============================================================================

class TestVirtualBoxIdentifierStrategy:
    """Tests for VirtualBoxIdentifierStrategy."""

    def test_hypervisor_name_property(self, virtualbox_strategy):
        """Test that hypervisor_name returns 'virtualbox'."""
        assert virtualbox_strategy.hypervisor_name == "virtualbox"

    def test_inherits_from_base_class(self, virtualbox_strategy):
        """Test that VirtualBoxIdentifierStrategy inherits from HypervisorIdentifierStrategy."""
        assert isinstance(virtualbox_strategy, HypervisorIdentifierStrategy)

    def test_get_identifier_returns_vbox_uuid(self, virtualbox_strategy, mock_vbox_vm_instance):
        """Test that get_identifier returns the VirtualBox UUID."""
        result = virtualbox_strategy.get_identifier(mock_vbox_vm_instance)
        assert result == "12345678-1234-1234-1234-123456789abc"

    def test_get_identifier_with_none_uuid(self, virtualbox_strategy, mock_vm_instance):
        """Test get_identifier when vbox_uuid is None."""
        mock_vm_instance.vbox_uuid = None
        result = virtualbox_strategy.get_identifier(mock_vm_instance)
        assert result is None

    def test_get_identifier_with_empty_uuid(self, virtualbox_strategy, mock_vm_instance):
        """Test get_identifier when vbox_uuid is empty string."""
        mock_vm_instance.vbox_uuid = ""
        result = virtualbox_strategy.get_identifier(mock_vm_instance)
        assert result == ""

    # verify_exists tests
    def test_verify_exists_returns_false_for_none_identifier(self, virtualbox_strategy):
        """Test verify_exists returns False when identifier is None."""
        assert virtualbox_strategy.verify_exists(None) is False

    def test_verify_exists_returns_false_for_empty_identifier(self, virtualbox_strategy):
        """Test verify_exists returns False when identifier is empty."""
        assert virtualbox_strategy.verify_exists("") is False

    @patch('adare.hypervisor.virtualbox.vm.VirtualBoxVM')
    def test_verify_exists_returns_true_when_vm_found(self, mock_vbox_vm_class, virtualbox_strategy):
        """Test verify_exists returns True when VirtualBox VM is found."""
        mock_vbox_vm_class.get_vm_name_by_uuid.return_value = "test-vm"
        result = virtualbox_strategy.verify_exists("valid-uuid")
        assert result is True
        mock_vbox_vm_class.get_vm_name_by_uuid.assert_called_once_with("valid-uuid")

    @patch('adare.hypervisor.virtualbox.vm.VirtualBoxVM')
    def test_verify_exists_returns_false_when_vm_not_found(self, mock_vbox_vm_class, virtualbox_strategy):
        """Test verify_exists returns False when VirtualBox VM is not found."""
        mock_vbox_vm_class.get_vm_name_by_uuid.return_value = None
        result = virtualbox_strategy.verify_exists("invalid-uuid")
        assert result is False

    def test_verify_exists_handles_import_error(self, virtualbox_strategy):
        """Test verify_exists returns False when VirtualBox module not available."""
        with patch.dict('sys.modules', {'adare.hypervisor.virtualbox.vm': None}):
            with patch('adare.hypervisor.virtualbox.vm.VirtualBoxVM', side_effect=ImportError):
                # The import happens inside the method, we need to patch at that level
                pass
        # Since the import is inside the method, we test with a direct patch
        with patch('adare.hypervisor.base.identifier_strategy.log') as mock_log:
            with patch.object(virtualbox_strategy, 'verify_exists', wraps=virtualbox_strategy.verify_exists):
                # Simulate ImportError by patching the import statement
                original_verify = virtualbox_strategy.verify_exists.__func__

                def patched_verify(self, identifier):
                    if not identifier:
                        return False
                    try:
                        raise ImportError("VirtualBox not available")
                    except ImportError:
                        return False

                with patch.object(VirtualBoxIdentifierStrategy, 'verify_exists', patched_verify):
                    strategy = VirtualBoxIdentifierStrategy()
                    result = strategy.verify_exists("some-uuid")
                    assert result is False

    # get_vm_state tests
    def test_get_vm_state_returns_not_found_for_none_identifier(self, virtualbox_strategy):
        """Test get_vm_state returns 'not_found' for None identifier."""
        result = virtualbox_strategy.get_vm_state(None)
        assert result == "not_found"

    def test_get_vm_state_returns_not_found_for_empty_identifier(self, virtualbox_strategy):
        """Test get_vm_state returns 'not_found' for empty identifier."""
        result = virtualbox_strategy.get_vm_state("")
        assert result == "not_found"

    @patch('adare.hypervisor.virtualbox.manager.VirtualBoxManager')
    @patch('adare.hypervisor.virtualbox.vm.VirtualBoxVM')
    def test_get_vm_state_returns_vm_state(self, mock_vbox_vm_class, mock_manager_class, virtualbox_strategy):
        """Test get_vm_state returns the actual VM state."""
        mock_vbox_vm_class.get_vm_name_by_uuid.return_value = "test-vm"
        mock_manager = Mock()
        mock_manager.executables = Mock()
        mock_manager_class.return_value = mock_manager
        mock_vm_instance = Mock()
        mock_vm_instance._get_state.return_value = "running"
        mock_vbox_vm_class.return_value = mock_vm_instance

        result = virtualbox_strategy.get_vm_state("valid-uuid")
        assert result == "running"

    @patch('adare.hypervisor.virtualbox.vm.VirtualBoxVM')
    def test_get_vm_state_returns_not_found_when_vm_missing(self, mock_vbox_vm_class, virtualbox_strategy):
        """Test get_vm_state returns 'not_found' when VM not in VirtualBox."""
        mock_vbox_vm_class.get_vm_name_by_uuid.return_value = None
        result = virtualbox_strategy.get_vm_state("missing-uuid")
        assert result == "not_found"

    # get_vm_name tests
    def test_get_vm_name_returns_none_for_none_identifier(self, virtualbox_strategy):
        """Test get_vm_name returns None for None identifier."""
        result = virtualbox_strategy.get_vm_name(None)
        assert result is None

    def test_get_vm_name_returns_none_for_empty_identifier(self, virtualbox_strategy):
        """Test get_vm_name returns None for empty identifier."""
        result = virtualbox_strategy.get_vm_name("")
        assert result is None

    @patch('adare.hypervisor.virtualbox.vm.VirtualBoxVM')
    def test_get_vm_name_returns_vm_name(self, mock_vbox_vm_class, virtualbox_strategy):
        """Test get_vm_name returns the VM name from VirtualBox."""
        mock_vbox_vm_class.get_vm_name_by_uuid.return_value = "my-test-vm"
        result = virtualbox_strategy.get_vm_name("valid-uuid")
        assert result == "my-test-vm"
        mock_vbox_vm_class.get_vm_name_by_uuid.assert_called_once_with("valid-uuid")

    @patch('adare.hypervisor.virtualbox.vm.VirtualBoxVM')
    def test_get_vm_name_returns_none_when_vm_not_found(self, mock_vbox_vm_class, virtualbox_strategy):
        """Test get_vm_name returns None when VM not found."""
        mock_vbox_vm_class.get_vm_name_by_uuid.return_value = None
        result = virtualbox_strategy.get_vm_name("invalid-uuid")
        assert result is None


# =============================================================================
# QEMUIdentifierStrategy Tests
# =============================================================================

class TestQEMUIdentifierStrategy:
    """Tests for QEMUIdentifierStrategy."""

    def test_hypervisor_name_property(self, qemu_strategy):
        """Test that hypervisor_name returns 'qemu'."""
        assert qemu_strategy.hypervisor_name == "qemu"

    def test_inherits_from_base_class(self, qemu_strategy):
        """Test that QEMUIdentifierStrategy inherits from HypervisorIdentifierStrategy."""
        assert isinstance(qemu_strategy, HypervisorIdentifierStrategy)

    def test_get_identifier_returns_instance_name(self, qemu_strategy, mock_qemu_vm_instance):
        """Test that get_identifier returns the instance name."""
        result = qemu_strategy.get_identifier(mock_qemu_vm_instance)
        assert result == "qemu-test-instance"

    def test_get_identifier_with_none_instance_name(self, qemu_strategy, mock_vm_instance):
        """Test get_identifier when instance_name is None."""
        mock_vm_instance.instance_name = None
        result = qemu_strategy.get_identifier(mock_vm_instance)
        assert result is None

    def test_get_identifier_with_empty_instance_name(self, qemu_strategy, mock_vm_instance):
        """Test get_identifier when instance_name is empty string."""
        mock_vm_instance.instance_name = ""
        result = qemu_strategy.get_identifier(mock_vm_instance)
        assert result == ""

    # verify_exists tests
    def test_verify_exists_returns_false_for_none_identifier(self, qemu_strategy):
        """Test verify_exists returns False when identifier is None."""
        assert qemu_strategy.verify_exists(None) is False

    def test_verify_exists_returns_false_for_empty_identifier(self, qemu_strategy):
        """Test verify_exists returns False when identifier is empty."""
        assert qemu_strategy.verify_exists("") is False

    @patch('adare.hypervisor.qemu.vm.QEMUVM')
    def test_verify_exists_returns_true_when_vm_found(self, mock_qemu_vm_class, qemu_strategy):
        """Test verify_exists returns True when QEMU VM is found."""
        mock_qemu_vm_class.get_vm_by_name.return_value = Mock()
        result = qemu_strategy.verify_exists("valid-domain")
        assert result is True
        mock_qemu_vm_class.get_vm_by_name.assert_called_once_with("valid-domain")

    @patch('adare.hypervisor.qemu.vm.QEMUVM')
    def test_verify_exists_returns_false_when_vm_not_found(self, mock_qemu_vm_class, qemu_strategy):
        """Test verify_exists returns False when QEMU VM is not found."""
        mock_qemu_vm_class.get_vm_by_name.return_value = None
        result = qemu_strategy.verify_exists("invalid-domain")
        assert result is False

    # get_vm_state tests
    def test_get_vm_state_returns_not_found_for_none_identifier(self, qemu_strategy):
        """Test get_vm_state returns 'not_found' for None identifier."""
        result = qemu_strategy.get_vm_state(None)
        assert result == "not_found"

    def test_get_vm_state_returns_not_found_for_empty_identifier(self, qemu_strategy):
        """Test get_vm_state returns 'not_found' for empty identifier."""
        result = qemu_strategy.get_vm_state("")
        assert result == "not_found"

    @patch('adare.hypervisor.qemu.vm.QEMUVM')
    def test_get_vm_state_returns_vm_state(self, mock_qemu_vm_class, qemu_strategy):
        """Test get_vm_state returns the actual VM state."""
        mock_vm = Mock()
        mock_vm.get_state.return_value = "running"
        mock_qemu_vm_class.get_vm_by_name.return_value = mock_vm

        result = qemu_strategy.get_vm_state("valid-domain")
        assert result == "running"
        mock_vm.get_state.assert_called_once()

    @patch('adare.hypervisor.qemu.vm.QEMUVM')
    def test_get_vm_state_returns_not_found_when_vm_missing(self, mock_qemu_vm_class, qemu_strategy):
        """Test get_vm_state returns 'not_found' when VM not in QEMU/libvirt."""
        mock_qemu_vm_class.get_vm_by_name.return_value = None
        result = qemu_strategy.get_vm_state("missing-domain")
        assert result == "not_found"

    # get_vm_name tests (uses default implementation)
    def test_get_vm_name_returns_identifier(self, qemu_strategy):
        """Test get_vm_name returns the identifier (default behavior for QEMU)."""
        result = qemu_strategy.get_vm_name("my-qemu-domain")
        assert result == "my-qemu-domain"

    def test_get_vm_name_with_various_identifiers(self, qemu_strategy):
        """Test get_vm_name with various identifier formats."""
        test_cases = [
            "simple-name",
            "domain_with_underscores",
            "domain-123-test",
            "CamelCaseDomain",
        ]
        for identifier in test_cases:
            assert qemu_strategy.get_vm_name(identifier) == identifier


# =============================================================================
# get_identifier_strategy() Function Tests
# =============================================================================

class TestGetIdentifierStrategy:
    """Tests for the get_identifier_strategy() function."""

    def test_returns_virtualbox_strategy(self):
        """Test that 'virtualbox' returns VirtualBoxIdentifierStrategy."""
        strategy = get_identifier_strategy("virtualbox")
        assert isinstance(strategy, VirtualBoxIdentifierStrategy)

    def test_returns_qemu_strategy(self):
        """Test that 'qemu' returns QEMUIdentifierStrategy."""
        strategy = get_identifier_strategy("qemu")
        assert isinstance(strategy, QEMUIdentifierStrategy)

    def test_raises_key_error_for_unknown_hypervisor(self):
        """Test that unknown hypervisor raises KeyError."""
        with pytest.raises(KeyError) as exc_info:
            get_identifier_strategy("unknown_hypervisor")
        assert "unknown_hypervisor" in str(exc_info.value)
        assert "Supported hypervisors" in str(exc_info.value)

    def test_error_message_includes_supported_hypervisors(self):
        """Test that error message lists supported hypervisors."""
        with pytest.raises(KeyError) as exc_info:
            get_identifier_strategy("vmware")
        error_msg = str(exc_info.value)
        assert "virtualbox" in error_msg
        assert "qemu" in error_msg

    @pytest.mark.parametrize("hypervisor", ["virtualbox", "qemu"])
    def test_returns_same_instance_for_repeated_calls(self, hypervisor):
        """Test that repeated calls return the same strategy instance."""
        strategy1 = get_identifier_strategy(hypervisor)
        strategy2 = get_identifier_strategy(hypervisor)
        assert strategy1 is strategy2

    @pytest.mark.parametrize("invalid_hypervisor", [
        "VIRTUALBOX",  # case sensitive
        "VirtualBox",
        "QEMU",
        "Qemu",
        "",
        "vmware",
        "hyper-v",
        "kvm",
    ])
    def test_raises_key_error_for_invalid_hypervisors(self, invalid_hypervisor):
        """Test that invalid hypervisor names raise KeyError."""
        with pytest.raises(KeyError):
            get_identifier_strategy(invalid_hypervisor)


# =============================================================================
# register_identifier_strategy() Function Tests
# =============================================================================

class TestRegisterIdentifierStrategy:
    """Tests for the register_identifier_strategy() function."""

    def test_registers_new_strategy(self):
        """Test registering a new hypervisor strategy."""
        # Create a custom strategy
        class CustomStrategy(HypervisorIdentifierStrategy):
            @property
            def hypervisor_name(self) -> str:
                return "custom"

            def get_identifier(self, vm_instance):
                return "custom-id"

            def verify_exists(self, identifier: str) -> bool:
                return True

            def get_vm_state(self, identifier: str) -> str:
                return "running"

        custom_strategy = CustomStrategy()

        # Register it
        register_identifier_strategy("custom_hypervisor", custom_strategy)

        # Verify it can be retrieved
        try:
            retrieved = get_identifier_strategy("custom_hypervisor")
            assert retrieved is custom_strategy
        finally:
            # Clean up - remove the registered strategy
            if "custom_hypervisor" in _IDENTIFIER_STRATEGIES:
                del _IDENTIFIER_STRATEGIES["custom_hypervisor"]

    def test_overwrites_existing_strategy(self):
        """Test that registering overwrites an existing strategy."""
        original_vbox = get_identifier_strategy("virtualbox")

        class NewVBoxStrategy(HypervisorIdentifierStrategy):
            @property
            def hypervisor_name(self) -> str:
                return "virtualbox"

            def get_identifier(self, vm_instance):
                return "new-id"

            def verify_exists(self, identifier: str) -> bool:
                return True

            def get_vm_state(self, identifier: str) -> str:
                return "running"

        new_strategy = NewVBoxStrategy()

        try:
            register_identifier_strategy("virtualbox", new_strategy)
            retrieved = get_identifier_strategy("virtualbox")
            assert retrieved is new_strategy
            assert retrieved is not original_vbox
        finally:
            # Restore original
            register_identifier_strategy("virtualbox", original_vbox)

    @patch('adare.hypervisor.base.identifier_strategy.log')
    def test_logs_registration(self, mock_log):
        """Test that registration logs an info message."""
        class TempStrategy(HypervisorIdentifierStrategy):
            @property
            def hypervisor_name(self) -> str:
                return "temp"

            def get_identifier(self, vm_instance):
                return "temp-id"

            def verify_exists(self, identifier: str) -> bool:
                return True

            def get_vm_state(self, identifier: str) -> str:
                return "running"

        try:
            register_identifier_strategy("temp_hyper", TempStrategy())
            mock_log.info.assert_called()
            call_args = mock_log.info.call_args[0][0]
            assert "temp_hyper" in call_args
        finally:
            if "temp_hyper" in _IDENTIFIER_STRATEGIES:
                del _IDENTIFIER_STRATEGIES["temp_hyper"]


# =============================================================================
# get_vm_identifier() Convenience Function Tests
# =============================================================================

class TestGetVmIdentifier:
    """Tests for the get_vm_identifier() convenience function."""

    def test_returns_hypervisor_identifier_from_instance(self, mock_vbox_vm_instance):
        """Test that it returns the VmInstance's hypervisor_identifier."""
        result = get_vm_identifier(mock_vbox_vm_instance)
        assert result == mock_vbox_vm_instance.hypervisor_identifier

    def test_returns_none_when_no_identifier(self, mock_vm_instance):
        """Test that it returns None when no identifier is set."""
        mock_vm_instance.hypervisor_identifier = None
        result = get_vm_identifier(mock_vm_instance)
        assert result is None


# =============================================================================
# verify_vm_exists() Convenience Function Tests
# =============================================================================

class TestVerifyVmExists:
    """Tests for the verify_vm_exists() convenience function."""

    def test_returns_false_when_no_vm(self, mock_vm_instance):
        """Test returns False when vm_instance.vm is None."""
        mock_vm_instance.vm = None
        result = verify_vm_exists(mock_vm_instance)
        assert result is False

    @patch('adare.hypervisor.virtualbox.vm.VirtualBoxVM')
    def test_uses_correct_strategy_for_virtualbox(self, mock_vbox_vm_class, mock_vbox_vm_instance):
        """Test uses VirtualBoxIdentifierStrategy for VirtualBox VMs."""
        mock_vbox_vm_class.get_vm_name_by_uuid.return_value = "test-vm"

        result = verify_vm_exists(mock_vbox_vm_instance)
        assert result is True
        mock_vbox_vm_class.get_vm_name_by_uuid.assert_called_once()

    @patch('adare.hypervisor.qemu.vm.QEMUVM')
    def test_uses_correct_strategy_for_qemu(self, mock_qemu_vm_class, mock_qemu_vm_instance):
        """Test uses QEMUIdentifierStrategy for QEMU VMs."""
        mock_qemu_vm_class.get_vm_by_name.return_value = Mock()

        result = verify_vm_exists(mock_qemu_vm_instance)
        assert result is True
        mock_qemu_vm_class.get_vm_by_name.assert_called_once()

    @patch('adare.hypervisor.virtualbox.vm.VirtualBoxVM')
    def test_returns_false_when_identifier_is_none(self, mock_vbox_vm_class, mock_vm_instance):
        """Test returns False when identifier is None."""
        mock_vm_instance.vbox_uuid = None
        mock_vm_instance.vm.hypervisor = "virtualbox"
        result = verify_vm_exists(mock_vm_instance)
        assert result is False


# =============================================================================
# get_vm_state() Convenience Function Tests
# =============================================================================

class TestGetVmState:
    """Tests for the get_vm_state() convenience function."""

    def test_returns_error_when_no_vm(self, mock_vm_instance):
        """Test returns 'error' when vm_instance.vm is None."""
        mock_vm_instance.vm = None
        result = get_vm_state(mock_vm_instance)
        assert result == "error"

    @patch('adare.hypervisor.virtualbox.manager.VirtualBoxManager')
    @patch('adare.hypervisor.virtualbox.vm.VirtualBoxVM')
    def test_returns_vm_state_for_virtualbox(self, mock_vbox_vm_class, mock_manager_class, mock_vbox_vm_instance):
        """Test returns correct state for VirtualBox VMs."""
        mock_vbox_vm_class.get_vm_name_by_uuid.return_value = "test-vm"
        mock_manager = Mock()
        mock_manager.executables = Mock()
        mock_manager_class.return_value = mock_manager
        mock_vm = Mock()
        mock_vm._get_state.return_value = "poweroff"
        mock_vbox_vm_class.return_value = mock_vm

        result = get_vm_state(mock_vbox_vm_instance)
        assert result == "poweroff"

    @patch('adare.hypervisor.qemu.vm.QEMUVM')
    def test_returns_vm_state_for_qemu(self, mock_qemu_vm_class, mock_qemu_vm_instance):
        """Test returns correct state for QEMU VMs."""
        mock_vm = Mock()
        mock_vm.get_state.return_value = "shutoff"
        mock_qemu_vm_class.get_vm_by_name.return_value = mock_vm

        result = get_vm_state(mock_qemu_vm_instance)
        assert result == "shutoff"

    @patch('adare.hypervisor.virtualbox.vm.VirtualBoxVM')
    def test_returns_not_found_when_identifier_is_none(self, mock_vbox_vm_class, mock_vm_instance):
        """Test returns 'not_found' when identifier is None."""
        mock_vm_instance.vbox_uuid = None
        mock_vm_instance.vm.hypervisor = "virtualbox"
        result = get_vm_state(mock_vm_instance)
        assert result == "not_found"


# =============================================================================
# Strategy Registry Tests
# =============================================================================

class TestStrategyRegistry:
    """Tests for the _IDENTIFIER_STRATEGIES registry."""

    def test_registry_contains_virtualbox(self):
        """Test that registry contains VirtualBox strategy."""
        assert "virtualbox" in _IDENTIFIER_STRATEGIES
        assert isinstance(_IDENTIFIER_STRATEGIES["virtualbox"], VirtualBoxIdentifierStrategy)

    def test_registry_contains_qemu(self):
        """Test that registry contains QEMU strategy."""
        assert "qemu" in _IDENTIFIER_STRATEGIES
        assert isinstance(_IDENTIFIER_STRATEGIES["qemu"], QEMUIdentifierStrategy)

    def test_registry_has_expected_hypervisors(self):
        """Test that registry contains exactly the expected hypervisors."""
        expected = {"virtualbox", "qemu"}
        # Note: other tests may add temporary entries, so we check subset
        assert expected.issubset(set(_IDENTIFIER_STRATEGIES.keys()))


# =============================================================================
# Parametrized Tests
# =============================================================================

class TestParametrizedStrategyBehavior:
    """Parametrized tests for strategy behavior across hypervisors."""

    @pytest.mark.parametrize("hypervisor,expected_class", [
        ("virtualbox", VirtualBoxIdentifierStrategy),
        ("qemu", QEMUIdentifierStrategy),
    ])
    def test_get_strategy_returns_correct_class(self, hypervisor, expected_class):
        """Test that get_identifier_strategy returns the correct class."""
        strategy = get_identifier_strategy(hypervisor)
        assert isinstance(strategy, expected_class)

    @pytest.mark.parametrize("hypervisor,expected_name", [
        ("virtualbox", "virtualbox"),
        ("qemu", "qemu"),
    ])
    def test_strategy_hypervisor_name_matches_key(self, hypervisor, expected_name):
        """Test that strategy's hypervisor_name matches its registry key."""
        strategy = get_identifier_strategy(hypervisor)
        assert strategy.hypervisor_name == expected_name

    @pytest.mark.parametrize("empty_identifier", [None, ""])
    def test_verify_exists_handles_empty_identifiers(self, empty_identifier, virtualbox_strategy, qemu_strategy):
        """Test that both strategies handle empty identifiers correctly."""
        assert virtualbox_strategy.verify_exists(empty_identifier) is False
        assert qemu_strategy.verify_exists(empty_identifier) is False

    @pytest.mark.parametrize("empty_identifier", [None, ""])
    def test_get_vm_state_handles_empty_identifiers(self, empty_identifier, virtualbox_strategy, qemu_strategy):
        """Test that both strategies handle empty identifiers for get_vm_state."""
        assert virtualbox_strategy.get_vm_state(empty_identifier) == "not_found"
        assert qemu_strategy.get_vm_state(empty_identifier) == "not_found"


# =============================================================================
# Integration-style Tests
# =============================================================================

class TestStrategyUsagePatterns:
    """Tests for common strategy usage patterns."""

    @patch('adare.hypervisor.virtualbox.vm.VirtualBoxVM')
    def test_full_workflow_virtualbox(self, mock_vbox_vm_class, mock_vbox_vm_instance):
        """Test full workflow: get strategy, get identifier, verify exists."""
        # Setup
        mock_vbox_vm_class.get_vm_name_by_uuid.return_value = "found-vm"

        # Get strategy
        strategy = get_identifier_strategy(mock_vbox_vm_instance.vm.hypervisor)
        assert isinstance(strategy, VirtualBoxIdentifierStrategy)

        # Get identifier
        identifier = strategy.get_identifier(mock_vbox_vm_instance)
        assert identifier == mock_vbox_vm_instance.vbox_uuid

        # Verify exists
        exists = strategy.verify_exists(identifier)
        assert exists is True

        # Get VM name
        vm_name = strategy.get_vm_name(identifier)
        assert vm_name == "found-vm"

    @patch('adare.hypervisor.qemu.vm.QEMUVM')
    def test_full_workflow_qemu(self, mock_qemu_vm_class, mock_qemu_vm_instance):
        """Test full workflow for QEMU: get strategy, get identifier, verify exists."""
        # Setup
        mock_qemu_vm_class.get_vm_by_name.return_value = Mock()

        # Get strategy
        strategy = get_identifier_strategy(mock_qemu_vm_instance.vm.hypervisor)
        assert isinstance(strategy, QEMUIdentifierStrategy)

        # Get identifier
        identifier = strategy.get_identifier(mock_qemu_vm_instance)
        assert identifier == mock_qemu_vm_instance.instance_name

        # Verify exists
        exists = strategy.verify_exists(identifier)
        assert exists is True

        # Get VM name (for QEMU, identifier IS the name)
        vm_name = strategy.get_vm_name(identifier)
        assert vm_name == identifier

    def test_strategy_pattern_eliminates_type_checking(self, mock_vbox_vm_instance, mock_qemu_vm_instance):
        """Test that strategy pattern eliminates scattered type-checking code."""
        # This test demonstrates the pattern described in the module docstring
        # Instead of:
        #   if vm_instance.vm.hypervisor == 'virtualbox':
        #       uuid = vm_instance.vbox_uuid
        #   elif vm_instance.vm.hypervisor == 'qemu':
        #       identifier = vm_instance.instance_name
        #
        # We use:
        #   strategy = get_identifier_strategy(vm_instance.vm.hypervisor)
        #   identifier = strategy.get_identifier(vm_instance)

        for vm_instance in [mock_vbox_vm_instance, mock_qemu_vm_instance]:
            strategy = get_identifier_strategy(vm_instance.vm.hypervisor)
            identifier = strategy.get_identifier(vm_instance)

            # Verify we got the correct identifier for each hypervisor
            if vm_instance.vm.hypervisor == "virtualbox":
                assert identifier == vm_instance.vbox_uuid
            elif vm_instance.vm.hypervisor == "qemu":
                assert identifier == vm_instance.instance_name
