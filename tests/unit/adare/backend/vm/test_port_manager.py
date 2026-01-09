"""
Unit tests for port_manager module.

Tests port allocation, reservation, and management functions.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError, OperationalError

from adare.backend.vm.port_manager import (
    PORT_RANGE_START,
    PORT_RANGE_END,
    find_available_port,
    reserve_port_atomically,
    is_port_available,
    get_port_usage_stats,
    cleanup_orphaned_ports,
    detect_port_conflicts,
    allocate_websocket_port,
    deallocate_websocket_port,
    is_websocket_port_allocated,
    reset_all_port_allocations,
)
from adare.hypervisor.exceptions import PortAllocationException


# Path for patching VmApi (imported locally in functions)
VM_API_PATH = 'adare.database.api.vm.VmApi'


# === Mock VM Instance Factory ===

_UNSET = object()  # Sentinel for unset values


class MockVmInstance:
    """Mock VM instance object for testing."""

    def __init__(
        self,
        id: str = "test-id",
        instance_name: str = "test-instance",
        websocket_port: int = None,
        status: str = "active",
        current_experiment_run_id: str = None,
        created_at: datetime = _UNSET
    ):
        self.id = id
        self.instance_name = instance_name
        self.websocket_port = websocket_port
        self.status = status
        self.current_experiment_run_id = current_experiment_run_id
        # Use sentinel to distinguish between None and unset
        if created_at is _UNSET:
            self.created_at = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        else:
            self.created_at = created_at


@pytest.fixture
def mock_vm_api():
    """Create a mock VmApi for testing."""
    api_mock = MagicMock()
    api_mock.get_all_vm_instances.return_value = []
    api_mock.session = MagicMock()
    api_mock.__enter__ = MagicMock(return_value=api_mock)
    api_mock.__exit__ = MagicMock(return_value=False)
    return api_mock


# === Tests for Constants ===

class TestPortConstants:
    """Test port range constants."""

    def test_port_range_start_value(self):
        """Verify PORT_RANGE_START is set correctly."""
        assert PORT_RANGE_START == 18765

    def test_port_range_end_value(self):
        """Verify PORT_RANGE_END is set correctly."""
        assert PORT_RANGE_END == 18799

    def test_port_range_valid(self):
        """Verify port range is valid (start <= end)."""
        assert PORT_RANGE_START <= PORT_RANGE_END

    def test_port_range_size(self):
        """Verify total number of available ports."""
        total_ports = PORT_RANGE_END - PORT_RANGE_START + 1
        assert total_ports == 35


# === Tests for find_available_port ===

class TestFindAvailablePort:
    """Test find_available_port function."""

    def test_returns_first_port_when_all_available(self, mock_vm_api):
        """Should return PORT_RANGE_START when no ports are in use."""
        mock_vm_api.get_all_vm_instances.return_value = []

        with patch(VM_API_PATH, return_value=mock_vm_api):
            port = find_available_port()

        assert port == PORT_RANGE_START

    def test_returns_next_available_port(self, mock_vm_api):
        """Should skip ports that are in use by active instances."""
        mock_vm_api.get_all_vm_instances.return_value = [
            MockVmInstance(websocket_port=PORT_RANGE_START, status='active'),
            MockVmInstance(websocket_port=PORT_RANGE_START + 1, status='active'),
        ]

        with patch(VM_API_PATH, return_value=mock_vm_api):
            port = find_available_port()

        assert port == PORT_RANGE_START + 2

    def test_ignores_non_active_instances(self, mock_vm_api):
        """Should ignore ports from non-active instances."""
        mock_vm_api.get_all_vm_instances.return_value = [
            MockVmInstance(websocket_port=PORT_RANGE_START, status='stopped'),
            MockVmInstance(websocket_port=PORT_RANGE_START + 1, status='available'),
        ]

        with patch(VM_API_PATH, return_value=mock_vm_api):
            port = find_available_port()

        assert port == PORT_RANGE_START

    def test_ignores_instances_without_port(self, mock_vm_api):
        """Should ignore instances with no websocket port."""
        mock_vm_api.get_all_vm_instances.return_value = [
            MockVmInstance(websocket_port=None, status='active'),
        ]

        with patch(VM_API_PATH, return_value=mock_vm_api):
            port = find_available_port()

        assert port == PORT_RANGE_START

    def test_ignores_ports_outside_range(self, mock_vm_api):
        """Should ignore ports outside the valid range."""
        mock_vm_api.get_all_vm_instances.return_value = [
            MockVmInstance(websocket_port=PORT_RANGE_START - 1, status='active'),
            MockVmInstance(websocket_port=PORT_RANGE_END + 1, status='active'),
        ]

        with patch(VM_API_PATH, return_value=mock_vm_api):
            port = find_available_port()

        assert port == PORT_RANGE_START

    def test_returns_none_when_all_ports_used(self, mock_vm_api):
        """Should return None when all ports in range are in use."""
        all_ports = [
            MockVmInstance(
                id=f"vm-{i}",
                websocket_port=port,
                status='active'
            )
            for i, port in enumerate(range(PORT_RANGE_START, PORT_RANGE_END + 1))
        ]
        mock_vm_api.get_all_vm_instances.return_value = all_ports

        with patch(VM_API_PATH, return_value=mock_vm_api):
            port = find_available_port()

        assert port is None

    def test_finds_gap_in_middle_of_range(self, mock_vm_api):
        """Should find available port in gap within the range."""
        # Use first two and skip third
        mock_vm_api.get_all_vm_instances.return_value = [
            MockVmInstance(websocket_port=PORT_RANGE_START, status='active'),
            MockVmInstance(websocket_port=PORT_RANGE_START + 1, status='active'),
            MockVmInstance(websocket_port=PORT_RANGE_START + 3, status='active'),
        ]

        with patch(VM_API_PATH, return_value=mock_vm_api):
            port = find_available_port()

        assert port == PORT_RANGE_START + 2

    def test_finds_last_port_when_only_one_available(self, mock_vm_api):
        """Should find the last port when it's the only one available."""
        # Use all ports except the last one
        all_but_last = [
            MockVmInstance(
                id=f"vm-{i}",
                websocket_port=port,
                status='active'
            )
            for i, port in enumerate(range(PORT_RANGE_START, PORT_RANGE_END))
        ]
        mock_vm_api.get_all_vm_instances.return_value = all_but_last

        with patch(VM_API_PATH, return_value=mock_vm_api):
            port = find_available_port()

        assert port == PORT_RANGE_END


# === Tests for reserve_port_atomically ===

class TestReservePortAtomically:
    """Test reserve_port_atomically function."""

    @pytest.fixture
    def api_session(self):
        """Create mock API session for atomic reservation."""
        session = MagicMock()
        session.get_all_vm_instances.return_value = []
        session.create_vm_instance.return_value = MockVmInstance()
        session.session = MagicMock()
        return session

    def test_reserves_first_available_port(self, api_session):
        """Should reserve PORT_RANGE_START when no ports in use."""
        api_session.get_all_vm_instances.return_value = []

        port = reserve_port_atomically(
            api_session,
            vm_id="vm-123",
            instance_name="test-instance",
            experiment_run_id="exp-456"
        )

        assert port == PORT_RANGE_START
        api_session.create_vm_instance.assert_called_once_with(
            vm_id="vm-123",
            instance_name="test-instance",
            experiment_run_id="exp-456",
            websocket_port=PORT_RANGE_START,
            status='active'
        )

    def test_reserves_next_available_port(self, api_session):
        """Should skip ports already in use."""
        api_session.get_all_vm_instances.return_value = [
            MockVmInstance(websocket_port=PORT_RANGE_START, status='active'),
        ]

        port = reserve_port_atomically(
            api_session,
            vm_id="vm-123",
            instance_name="test-instance",
            experiment_run_id="exp-456"
        )

        assert port == PORT_RANGE_START + 1

    def test_returns_none_when_all_ports_used(self, api_session):
        """Should return None when all ports are in use."""
        all_ports = [
            MockVmInstance(websocket_port=port, status='active')
            for port in range(PORT_RANGE_START, PORT_RANGE_END + 1)
        ]
        api_session.get_all_vm_instances.return_value = all_ports

        port = reserve_port_atomically(
            api_session,
            vm_id="vm-123",
            instance_name="test-instance",
            experiment_run_id="exp-456"
        )

        assert port is None
        api_session.create_vm_instance.assert_not_called()

    def test_retries_on_integrity_error(self, api_session):
        """Should try next port on IntegrityError."""
        api_session.get_all_vm_instances.return_value = []
        # First call raises IntegrityError, second succeeds
        api_session.create_vm_instance.side_effect = [
            IntegrityError("statement", "params", "orig"),
            MockVmInstance(websocket_port=PORT_RANGE_START + 1)
        ]

        port = reserve_port_atomically(
            api_session,
            vm_id="vm-123",
            instance_name="test-instance",
            experiment_run_id="exp-456"
        )

        assert port == PORT_RANGE_START + 1
        assert api_session.create_vm_instance.call_count == 2
        api_session.session.rollback.assert_called_once()

    def test_raises_on_operational_error(self, api_session):
        """Should raise PortAllocationException on OperationalError."""
        api_session.get_all_vm_instances.return_value = []
        api_session.create_vm_instance.side_effect = OperationalError(
            "statement", "params", "orig"
        )

        with pytest.raises(PortAllocationException) as exc_info:
            reserve_port_atomically(
                api_session,
                vm_id="vm-123",
                instance_name="test-instance",
                experiment_run_id="exp-456"
            )

        assert exc_info.value.port_range == (PORT_RANGE_START, PORT_RANGE_END)

    def test_ignores_non_active_instances(self, api_session):
        """Should ignore ports from non-active instances."""
        api_session.get_all_vm_instances.return_value = [
            MockVmInstance(websocket_port=PORT_RANGE_START, status='stopped'),
        ]

        port = reserve_port_atomically(
            api_session,
            vm_id="vm-123",
            instance_name="test-instance",
            experiment_run_id="exp-456"
        )

        assert port == PORT_RANGE_START

    @pytest.mark.parametrize("num_integrity_errors", [1, 5, 10])
    def test_handles_multiple_integrity_errors(self, api_session, num_integrity_errors):
        """Should keep trying ports on multiple IntegrityErrors."""
        api_session.get_all_vm_instances.return_value = []

        # Multiple IntegrityErrors followed by success
        side_effects = [
            IntegrityError("statement", "params", "orig")
            for _ in range(num_integrity_errors)
        ]
        side_effects.append(MockVmInstance(websocket_port=PORT_RANGE_START + num_integrity_errors))
        api_session.create_vm_instance.side_effect = side_effects

        port = reserve_port_atomically(
            api_session,
            vm_id="vm-123",
            instance_name="test-instance",
            experiment_run_id="exp-456"
        )

        assert port == PORT_RANGE_START + num_integrity_errors


# === Tests for is_port_available ===

class TestIsPortAvailable:
    """Test is_port_available function."""

    def test_returns_true_for_unused_port(self, mock_vm_api):
        """Should return True when port is not in use."""
        mock_vm_api.get_all_vm_instances.return_value = []

        with patch(VM_API_PATH, return_value=mock_vm_api):
            result = is_port_available(PORT_RANGE_START)

        assert result is True

    def test_returns_false_for_used_port(self, mock_vm_api):
        """Should return False when port is in use by active instance."""
        mock_vm_api.get_all_vm_instances.return_value = [
            MockVmInstance(websocket_port=PORT_RANGE_START, status='active'),
        ]

        with patch(VM_API_PATH, return_value=mock_vm_api):
            result = is_port_available(PORT_RANGE_START)

        assert result is False

    def test_returns_false_for_port_below_range(self, mock_vm_api):
        """Should return False for ports below the valid range."""
        with patch(VM_API_PATH, return_value=mock_vm_api):
            result = is_port_available(PORT_RANGE_START - 1)

        assert result is False
        # Should not even query database
        mock_vm_api.get_all_vm_instances.assert_not_called()

    def test_returns_false_for_port_above_range(self, mock_vm_api):
        """Should return False for ports above the valid range."""
        with patch(VM_API_PATH, return_value=mock_vm_api):
            result = is_port_available(PORT_RANGE_END + 1)

        assert result is False
        mock_vm_api.get_all_vm_instances.assert_not_called()

    def test_returns_true_for_port_from_non_active_instance(self, mock_vm_api):
        """Should return True if port is only used by non-active instance."""
        mock_vm_api.get_all_vm_instances.return_value = [
            MockVmInstance(websocket_port=PORT_RANGE_START, status='stopped'),
        ]

        with patch(VM_API_PATH, return_value=mock_vm_api):
            result = is_port_available(PORT_RANGE_START)

        assert result is True

    @pytest.mark.parametrize("port", [PORT_RANGE_START, PORT_RANGE_END, (PORT_RANGE_START + PORT_RANGE_END) // 2])
    def test_boundary_ports_valid(self, mock_vm_api, port):
        """Should accept ports at boundaries and middle of range."""
        mock_vm_api.get_all_vm_instances.return_value = []

        with patch(VM_API_PATH, return_value=mock_vm_api):
            result = is_port_available(port)

        assert result is True


# === Tests for get_port_usage_stats ===

class TestGetPortUsageStats:
    """Test get_port_usage_stats function."""

    def test_returns_empty_stats_when_no_allocations(self, mock_vm_api):
        """Should return correct stats when no ports allocated."""
        mock_vm_api.get_all_vm_instances.return_value = []

        with patch(VM_API_PATH, return_value=mock_vm_api):
            stats = get_port_usage_stats()

        expected_total = PORT_RANGE_END - PORT_RANGE_START + 1
        assert stats['total_ports'] == expected_total
        assert stats['allocated_ports'] == []
        assert stats['allocated_count'] == 0
        assert stats['available_count'] == expected_total
        assert stats['port_range'] == f"{PORT_RANGE_START}-{PORT_RANGE_END}"

    def test_returns_correct_stats_with_allocations(self, mock_vm_api):
        """Should return correct stats when some ports allocated."""
        mock_vm_api.get_all_vm_instances.return_value = [
            MockVmInstance(websocket_port=PORT_RANGE_START, status='active'),
            MockVmInstance(websocket_port=PORT_RANGE_START + 2, status='active'),
        ]

        with patch(VM_API_PATH, return_value=mock_vm_api):
            stats = get_port_usage_stats()

        expected_total = PORT_RANGE_END - PORT_RANGE_START + 1
        assert stats['total_ports'] == expected_total
        assert stats['allocated_ports'] == sorted([PORT_RANGE_START, PORT_RANGE_START + 2])
        assert stats['allocated_count'] == 2
        assert stats['available_count'] == expected_total - 2

    def test_ignores_non_active_instances(self, mock_vm_api):
        """Should not count ports from non-active instances."""
        mock_vm_api.get_all_vm_instances.return_value = [
            MockVmInstance(websocket_port=PORT_RANGE_START, status='active'),
            MockVmInstance(websocket_port=PORT_RANGE_START + 1, status='stopped'),
        ]

        with patch(VM_API_PATH, return_value=mock_vm_api):
            stats = get_port_usage_stats()

        assert stats['allocated_count'] == 1
        assert stats['allocated_ports'] == [PORT_RANGE_START]

    def test_ignores_ports_outside_range(self, mock_vm_api):
        """Should not count ports outside the valid range."""
        mock_vm_api.get_all_vm_instances.return_value = [
            MockVmInstance(websocket_port=PORT_RANGE_START, status='active'),
            MockVmInstance(websocket_port=PORT_RANGE_START - 100, status='active'),
            MockVmInstance(websocket_port=PORT_RANGE_END + 100, status='active'),
        ]

        with patch(VM_API_PATH, return_value=mock_vm_api):
            stats = get_port_usage_stats()

        assert stats['allocated_count'] == 1

    def test_returns_sorted_allocated_ports(self, mock_vm_api):
        """Should return allocated ports in sorted order."""
        mock_vm_api.get_all_vm_instances.return_value = [
            MockVmInstance(websocket_port=PORT_RANGE_START + 5, status='active'),
            MockVmInstance(websocket_port=PORT_RANGE_START + 1, status='active'),
            MockVmInstance(websocket_port=PORT_RANGE_START + 10, status='active'),
        ]

        with patch(VM_API_PATH, return_value=mock_vm_api):
            stats = get_port_usage_stats()

        assert stats['allocated_ports'] == sorted(stats['allocated_ports'])


# === Tests for cleanup_orphaned_ports ===

class TestCleanupOrphanedPorts:
    """Test cleanup_orphaned_ports function."""

    def test_returns_zero_when_no_orphans(self, mock_vm_api):
        """Should return 0 when no orphaned ports exist."""
        mock_vm_api.get_all_vm_instances.return_value = [
            MockVmInstance(websocket_port=PORT_RANGE_START, status='active'),
        ]

        with patch(VM_API_PATH, return_value=mock_vm_api):
            cleaned = cleanup_orphaned_ports()

        assert cleaned == 0

    def test_cleans_up_stopped_instance_with_port(self, mock_vm_api):
        """Should clean up port from stopped instance."""
        orphan = MockVmInstance(
            websocket_port=PORT_RANGE_START,
            status='stopped',
            instance_name='orphan-instance'
        )
        mock_vm_api.get_all_vm_instances.return_value = [orphan]

        with patch(VM_API_PATH, return_value=mock_vm_api):
            cleaned = cleanup_orphaned_ports()

        assert cleaned == 1
        assert orphan.websocket_port is None
        mock_vm_api.session.commit.assert_called()

    def test_cleans_up_multiple_orphans(self, mock_vm_api):
        """Should clean up all orphaned ports."""
        orphan1 = MockVmInstance(websocket_port=PORT_RANGE_START, status='stopped')
        orphan2 = MockVmInstance(websocket_port=PORT_RANGE_START + 1, status='available')
        mock_vm_api.get_all_vm_instances.return_value = [orphan1, orphan2]

        with patch(VM_API_PATH, return_value=mock_vm_api):
            cleaned = cleanup_orphaned_ports()

        assert cleaned == 2
        assert orphan1.websocket_port is None
        assert orphan2.websocket_port is None

    def test_ignores_active_instances(self, mock_vm_api):
        """Should not clean up ports from active instances."""
        active = MockVmInstance(websocket_port=PORT_RANGE_START, status='active')
        mock_vm_api.get_all_vm_instances.return_value = [active]

        with patch(VM_API_PATH, return_value=mock_vm_api):
            cleaned = cleanup_orphaned_ports()

        assert cleaned == 0
        assert active.websocket_port == PORT_RANGE_START

    def test_ignores_instances_without_port(self, mock_vm_api):
        """Should not count instances without websocket port."""
        no_port = MockVmInstance(websocket_port=None, status='stopped')
        mock_vm_api.get_all_vm_instances.return_value = [no_port]

        with patch(VM_API_PATH, return_value=mock_vm_api):
            cleaned = cleanup_orphaned_ports()

        assert cleaned == 0

    def test_ignores_ports_outside_range(self, mock_vm_api):
        """Should not clean up ports outside the valid range."""
        outside = MockVmInstance(websocket_port=PORT_RANGE_START - 100, status='stopped')
        mock_vm_api.get_all_vm_instances.return_value = [outside]

        with patch(VM_API_PATH, return_value=mock_vm_api):
            cleaned = cleanup_orphaned_ports()

        assert cleaned == 0


# === Tests for detect_port_conflicts ===

class TestDetectPortConflicts:
    """Test detect_port_conflicts function."""

    def test_returns_no_conflicts_when_unique_ports(self, mock_vm_api):
        """Should return no conflicts when all ports are unique."""
        mock_vm_api.get_all_vm_instances.return_value = [
            MockVmInstance(id='vm-1', websocket_port=PORT_RANGE_START, status='active'),
            MockVmInstance(id='vm-2', websocket_port=PORT_RANGE_START + 1, status='active'),
        ]

        with patch(VM_API_PATH, return_value=mock_vm_api):
            result = detect_port_conflicts()

        assert result['conflicts_found'] is False
        assert result['conflict_count'] == 0
        assert result['conflicted_ports'] == {}

    def test_detects_single_port_conflict(self, mock_vm_api):
        """Should detect when two instances share the same port."""
        mock_vm_api.get_all_vm_instances.return_value = [
            MockVmInstance(id='vm-1', instance_name='inst-1', websocket_port=PORT_RANGE_START, status='active'),
            MockVmInstance(id='vm-2', instance_name='inst-2', websocket_port=PORT_RANGE_START, status='active'),
        ]

        with patch(VM_API_PATH, return_value=mock_vm_api):
            result = detect_port_conflicts()

        assert result['conflicts_found'] is True
        assert result['conflict_count'] == 1
        assert PORT_RANGE_START in result['conflicted_ports']
        assert len(result['conflicted_ports'][PORT_RANGE_START]) == 2

    def test_detects_multiple_port_conflicts(self, mock_vm_api):
        """Should detect multiple conflicted ports."""
        mock_vm_api.get_all_vm_instances.return_value = [
            MockVmInstance(id='vm-1', websocket_port=PORT_RANGE_START, status='active'),
            MockVmInstance(id='vm-2', websocket_port=PORT_RANGE_START, status='active'),
            MockVmInstance(id='vm-3', websocket_port=PORT_RANGE_START + 1, status='active'),
            MockVmInstance(id='vm-4', websocket_port=PORT_RANGE_START + 1, status='active'),
        ]

        with patch(VM_API_PATH, return_value=mock_vm_api):
            result = detect_port_conflicts()

        assert result['conflicts_found'] is True
        assert result['conflict_count'] == 2

    def test_ignores_non_active_instances(self, mock_vm_api):
        """Should not report conflicts involving non-active instances."""
        mock_vm_api.get_all_vm_instances.return_value = [
            MockVmInstance(id='vm-1', websocket_port=PORT_RANGE_START, status='active'),
            MockVmInstance(id='vm-2', websocket_port=PORT_RANGE_START, status='stopped'),
        ]

        with patch(VM_API_PATH, return_value=mock_vm_api):
            result = detect_port_conflicts()

        assert result['conflicts_found'] is False

    def test_ignores_ports_outside_range(self, mock_vm_api):
        """Should not report conflicts for ports outside valid range."""
        mock_vm_api.get_all_vm_instances.return_value = [
            MockVmInstance(id='vm-1', websocket_port=PORT_RANGE_START - 100, status='active'),
            MockVmInstance(id='vm-2', websocket_port=PORT_RANGE_START - 100, status='active'),
        ]

        with patch(VM_API_PATH, return_value=mock_vm_api):
            result = detect_port_conflicts()

        assert result['conflicts_found'] is False

    def test_conflict_info_includes_all_fields(self, mock_vm_api):
        """Should include complete instance info in conflict report."""
        timestamp = datetime(2024, 1, 15, 10, 30, 0, tzinfo=timezone.utc)
        mock_vm_api.get_all_vm_instances.return_value = [
            MockVmInstance(
                id='vm-1',
                instance_name='inst-1',
                websocket_port=PORT_RANGE_START,
                status='active',
                current_experiment_run_id='exp-123',
                created_at=timestamp
            ),
            MockVmInstance(
                id='vm-2',
                instance_name='inst-2',
                websocket_port=PORT_RANGE_START,
                status='active',
                current_experiment_run_id='exp-456',
                created_at=timestamp
            ),
        ]

        with patch(VM_API_PATH, return_value=mock_vm_api):
            result = detect_port_conflicts()

        conflict_instances = result['conflicted_ports'][PORT_RANGE_START]
        for inst in conflict_instances:
            assert 'id' in inst
            assert 'name' in inst
            assert 'experiment_id' in inst
            assert 'created_at' in inst


# === Tests for backward compatibility functions ===

class TestBackwardCompatibility:
    """Test backward compatibility functions."""

    def test_allocate_websocket_port_calls_find_available(self, mock_vm_api):
        """allocate_websocket_port should call find_available_port."""
        mock_vm_api.get_all_vm_instances.return_value = []

        with patch(VM_API_PATH, return_value=mock_vm_api):
            port = allocate_websocket_port()

        assert port == PORT_RANGE_START

    def test_deallocate_websocket_port_returns_true(self):
        """deallocate_websocket_port should always return True."""
        result = deallocate_websocket_port(PORT_RANGE_START)
        assert result is True

    def test_is_websocket_port_allocated_inverse_of_available(self, mock_vm_api):
        """is_websocket_port_allocated should return inverse of is_port_available."""
        mock_vm_api.get_all_vm_instances.return_value = [
            MockVmInstance(websocket_port=PORT_RANGE_START, status='active'),
        ]

        with patch(VM_API_PATH, return_value=mock_vm_api):
            allocated = is_websocket_port_allocated(PORT_RANGE_START)
            not_allocated = is_websocket_port_allocated(PORT_RANGE_START + 1)

        assert allocated is True
        assert not_allocated is False


# === Tests for reset_all_port_allocations ===

class TestResetAllPortAllocations:
    """Test reset_all_port_allocations function."""

    def test_performs_cleanup_and_conflict_detection(self, mock_vm_api):
        """Should run cleanup and conflict detection."""
        mock_vm_api.get_all_vm_instances.return_value = []

        with patch(VM_API_PATH, return_value=mock_vm_api):
            result = reset_all_port_allocations()

        assert 'orphaned_cleaned' in result
        assert 'conflicts' in result
        assert result['conflicts']['conflicts_found'] is False

    def test_returns_cleanup_count(self, mock_vm_api):
        """Should return number of orphaned ports cleaned."""
        orphan = MockVmInstance(websocket_port=PORT_RANGE_START, status='stopped')
        mock_vm_api.get_all_vm_instances.return_value = [orphan]

        with patch(VM_API_PATH, return_value=mock_vm_api):
            result = reset_all_port_allocations()

        assert result['orphaned_cleaned'] == 1


# === Edge case and integration tests ===

class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_handles_empty_instance_list(self, mock_vm_api):
        """Should handle empty instance list gracefully."""
        mock_vm_api.get_all_vm_instances.return_value = []

        with patch(VM_API_PATH, return_value=mock_vm_api):
            assert find_available_port() == PORT_RANGE_START
            assert is_port_available(PORT_RANGE_START) is True
            stats = get_port_usage_stats()
            assert stats['allocated_count'] == 0

    def test_handles_instance_with_none_created_at(self, mock_vm_api):
        """Should handle instance with None created_at in conflict detection."""
        mock_vm_api.get_all_vm_instances.return_value = [
            MockVmInstance(id='vm-1', websocket_port=PORT_RANGE_START, status='active', created_at=None),
            MockVmInstance(id='vm-2', websocket_port=PORT_RANGE_START, status='active', created_at=None),
        ]

        with patch(VM_API_PATH, return_value=mock_vm_api):
            result = detect_port_conflicts()

        assert result['conflicts_found'] is True
        # Should have None for created_at
        for inst in result['conflicted_ports'][PORT_RANGE_START]:
            assert inst['created_at'] is None

    @pytest.mark.parametrize("status", ['available', 'stopped', 'error', 'terminated'])
    def test_various_inactive_statuses(self, mock_vm_api, status):
        """Should treat various non-active statuses as inactive."""
        mock_vm_api.get_all_vm_instances.return_value = [
            MockVmInstance(websocket_port=PORT_RANGE_START, status=status),
        ]

        with patch(VM_API_PATH, return_value=mock_vm_api):
            assert find_available_port() == PORT_RANGE_START
            assert is_port_available(PORT_RANGE_START) is True
