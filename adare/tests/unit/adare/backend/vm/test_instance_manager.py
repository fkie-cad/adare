"""Tests for VmInstanceManager reuse-claim race handling and instance naming."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import ulid
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

pytestmark = pytest.mark.unit

MODULE = "adare.backend.vm.instance_manager"
DB_MODULE = "adare.database.api.vm"


@pytest.fixture
def mock_vm_api():
    """Create a mock VmApi context manager."""
    api_instance = MagicMock()
    api_cls = MagicMock()
    api_cls.return_value.__enter__ = MagicMock(return_value=api_instance)
    api_cls.return_value.__exit__ = MagicMock(return_value=False)
    return api_cls, api_instance


class TestClaimAvailableVmInstance:
    """Two racing claims on the same instance: first wins, second loses."""

    def test_second_claim_on_same_instance_fails(self):
        from adare.database.models.global_models import VmInstance

        # Simulate SQLite's serialized single-statement UPDATE semantics:
        # the first UPDATE ... WHERE status='available' matches and flips
        # the row; the second UPDATE against the now-'active' row matches 0.
        class FakeSession:
            def __init__(self):
                self.status = 'available'
                self.commits = 0

            def query(self, model):
                return self

            def filter_by(self, **kwargs):
                self._matches = kwargs.get('status') == self.status
                return self

            def update(self, values, synchronize_session=False):
                if not self._matches:
                    return 0
                self.status = values['status']
                return 1

            def commit(self):
                self.commits += 1

            def rollback(self):
                pass

        from adare.database.api.vm.instances import VmInstanceMixin

        class FakeApi(VmInstanceMixin):
            def __init__(self, session):
                self._session = session

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        session = FakeSession()
        api = FakeApi(session)

        first = api.claim_available_vm_instance("inst-1", "run-1", 5555)
        second = api.claim_available_vm_instance("inst-1", "run-2", 5556)

        assert first is True
        assert second is False


class TestAllocateInstanceForExperimentFallsBackOnLostRace:
    @pytest.mark.asyncio
    async def test_falls_back_to_create_new_instance_when_reuse_returns_none(self, mock_vm_api):
        from adare.backend.vm.instance_manager import VmInstanceManager

        api_cls, api_instance = mock_vm_api
        api_instance.get_vm_instances_for_vm.return_value = []

        manager = VmInstanceManager()

        available_instance = MagicMock()
        available_instance.instance_name = "vm_exp_abcd1234"

        new_instance = MagicMock()
        new_instance.instance_name = "vm_exp_new"

        with patch(f"{DB_MODULE}.VmApi", api_cls), \
             patch.object(manager, "find_available_instance", return_value=available_instance), \
             patch.object(manager, "sync_instance_states", new=AsyncMock(return_value=0)), \
             patch.object(manager, "reuse_instance", new=AsyncMock(return_value=None)) as mock_reuse, \
             patch.object(manager, "create_new_instance", new=AsyncMock(return_value=new_instance)) as mock_create:

            result = await manager.allocate_instance_for_experiment("vm-1", "run-1")

        mock_reuse.assert_awaited_once_with(available_instance, "run-1")
        mock_create.assert_awaited_once_with("vm-1", "run-1")
        assert result is new_instance


class TestGenerateInstanceName:
    def test_no_collision_for_ulids_sharing_timestamp_prefix(self):
        from adare.backend.vm.instance_manager import VmInstanceManager

        manager = VmInstanceManager()

        # Same first 8 chars (timestamp-derived), different random suffixes.
        run_id_a = "01ARZ3NDEKTSV4RRFFQ69G5FAV"
        run_id_b = "01ARZ3NDEKTSV4RRFFQ69G5FBW"

        name_a = manager._generate_instance_name("base_vm", run_id_a)
        name_b = manager._generate_instance_name("base_vm", run_id_b)

        assert name_a != name_b
        assert name_a == "base_vm_exp_Q69G5FAV"
        assert name_b == "base_vm_exp_Q69G5FBW"


class TestIntegrityErrorPropagation:
    """A unique-constraint violation (port or name) must reach the caller
    unwrapped, not get rewrapped into VMLoadError — otherwise the retry
    loops in reserve_port_atomically() / reuse_instance() never fire."""

    def test_create_vm_instance_propagates_integrity_error(self):
        from adare.database.api.vm.instances import VmInstanceMixin

        class FakeSession:
            def add(self, obj):
                pass

            def commit(self):
                raise IntegrityError("INSERT", {}, Exception("UNIQUE constraint failed"))

            def rollback(self):
                pass

        class FakeApi(VmInstanceMixin):
            def __init__(self, session):
                self._session = session

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        api = FakeApi(FakeSession())

        with pytest.raises(IntegrityError):
            api.create_vm_instance(
                vm_id="vm-1",
                instance_name="inst-1",
                experiment_run_id="run-1",
                websocket_port=18765,
            )

    def test_claim_available_vm_instance_propagates_integrity_error(self):
        from adare.database.api.vm.instances import VmInstanceMixin

        class FakeQuery:
            def filter_by(self, **kwargs):
                return self

            def update(self, values, synchronize_session=False):
                raise IntegrityError("UPDATE", {}, Exception("UNIQUE constraint failed"))

        class FakeSession:
            def query(self, model):
                return FakeQuery()

            def commit(self):
                pass

            def rollback(self):
                pass

        class FakeApi(VmInstanceMixin):
            def __init__(self, session):
                self._session = session

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        api = FakeApi(FakeSession())

        with pytest.raises(IntegrityError):
            api.claim_available_vm_instance("inst-1", "run-1", 18765)


class TestReuseInstancePortRetry:
    """reuse_instance() must retry the next candidate port when the
    unique-active-port index rejects one, instead of giving up entirely."""

    @pytest.mark.asyncio
    async def test_retries_next_port_on_integrity_error(self, mock_vm_api):
        from adare.backend.vm.instance_manager import VmInstanceManager
        from adare.backend.vm.port_manager import PORT_RANGE_START

        api_cls, api_instance = mock_vm_api
        api_instance.get_all_vm_instances.return_value = []
        api_instance.get_vm_by_id.return_value = MagicMock(hypervisor="qemu")

        updated_instance = MagicMock()
        api_instance.get_vm_instance_by_id.return_value = updated_instance

        # First candidate port raises IntegrityError (taken by another
        # process), second candidate succeeds.
        api_instance.claim_available_vm_instance.side_effect = [
            IntegrityError("UPDATE", {}, Exception("UNIQUE constraint failed")),
            True,
        ]

        instance = MagicMock()
        instance.instance_name = "vm_exp_abcd1234"
        instance.base_snapshot_name = None
        instance.vbox_uuid = None

        manager = VmInstanceManager()

        with patch(f"{DB_MODULE}.VmApi", api_cls):
            result = await manager.reuse_instance(instance, "run-1")

        assert result is updated_instance
        assert api_instance.claim_available_vm_instance.call_count == 2
        first_call, second_call = api_instance.claim_available_vm_instance.call_args_list
        assert first_call.kwargs["websocket_port"] == PORT_RANGE_START
        assert second_call.kwargs["websocket_port"] == PORT_RANGE_START + 1

    @pytest.mark.asyncio
    async def test_stops_retrying_when_instance_itself_is_claimed(self, mock_vm_api):
        from adare.backend.vm.instance_manager import VmInstanceManager

        api_cls, api_instance = mock_vm_api
        api_instance.get_all_vm_instances.return_value = []
        api_instance.get_vm_by_id.return_value = MagicMock(hypervisor="qemu")

        # Instance itself was claimed by another process first — no
        # IntegrityError, just a plain False. Must not try further ports.
        api_instance.claim_available_vm_instance.return_value = False

        instance = MagicMock()
        instance.instance_name = "vm_exp_abcd1234"
        instance.base_snapshot_name = None
        instance.vbox_uuid = None

        manager = VmInstanceManager()

        with patch(f"{DB_MODULE}.VmApi", api_cls):
            result = await manager.reuse_instance(instance, "run-1")

        assert result is None
        assert api_instance.claim_available_vm_instance.call_count == 1


class TestActiveWebsocketPortUniqueConstraint:
    """Integration test against a real temp-file SQLite engine: this is the
    one test that would catch a wrong `sqlite_where` expression, since the
    mocked tests above can't verify the real constraint exists."""

    def test_duplicate_active_port_raises_integrity_error(self, tmp_path):
        from adare.database.models.global_models import GlobalBase, Vm, VmInstance

        db_path = tmp_path / "test.db"
        engine = create_engine(f"sqlite:///{db_path.as_posix()}")
        GlobalBase.metadata.create_all(engine)

        session_starter = sessionmaker(bind=engine)
        session = session_starter()

        vm = Vm(id=str(ulid.ULID()), name="vm1", file="f", hash="h")
        session.add(vm)
        session.commit()

        first = VmInstance(
            id=str(ulid.ULID()), vm_id=vm.id, instance_name="inst-1",
            websocket_port=18765, status="active",
        )
        session.add(first)
        session.commit()

        second = VmInstance(
            id=str(ulid.ULID()), vm_id=vm.id, instance_name="inst-2",
            websocket_port=18765, status="active",
        )
        session.add(second)

        with pytest.raises(IntegrityError):
            session.commit()

        session.rollback()
        session.close()
