"""Run-scoped QEMU instances and reconciliation of crashed runs."""

import os
from unittest.mock import AsyncMock, patch

import pytest

from adare.backend.vm import run_instances
from adare.database.api.vm import VmApi
from adare.database.models.global_models import Vm, VmInstance

pytestmark = pytest.mark.unit

DEAD_PID = 2**22 + 12345  # above the default pid_max: never a live process


@pytest.fixture
def global_db(tmp_path):
    with patch('adare.config.database.get_global_database_location', return_value=tmp_path / 'global.db'):
        yield


def _vm(name='ubuntu', hypervisor='qemu') -> Vm:
    with VmApi() as api:
        vm = Vm(name=name, file=f'/disks/{name}.qcow2', hash='a' * 64, hypervisor=hypervisor)
        api._session.add(vm)
        api._session.commit()
        api._session.expunge(vm)
        return vm


def _instance(vm: Vm, name: str, status='active', owner_pid=None, port=None) -> None:
    with VmApi() as api:
        api._session.add(
            VmInstance(vm_id=vm.id, instance_name=name, status=status, owner_pid=owner_pid, websocket_port=port)
        )
        api._session.commit()


def _names() -> set[str]:
    with VmApi() as api:
        return {i.instance_name for i in api.get_all_vm_instances()}


class TestRunInstanceName:
    def test_concurrent_runs_and_machines_get_distinct_names(self):
        a = run_instances.run_instance_name('ubuntu', '01JAAAAAAAAAAAAAAAAAAAAAAA')
        b = run_instances.run_instance_name('ubuntu', '01JAAAAAAAAAAAAAAAAAAAAAAB')
        client = run_instances.run_instance_name('ubuntu', '01JAAAAAAAAAAAAAAAAAAAAAAA', 'client')
        server = run_instances.run_instance_name('ubuntu', '01JAAAAAAAAAAAAAAAAAAAAAAA', 'server')

        assert len({a, b, client, server}) == 4
        assert '_run_' in a


class TestAllocate:
    def test_reserves_a_port_and_records_the_owner(self, global_db):
        vm = _vm()

        first = run_instances.allocate_qemu_run_instance(vm, '01JAAAAAAAAAAAAAAAAAAAAAAA')
        second = run_instances.allocate_qemu_run_instance(vm, '01JAAAAAAAAAAAAAAAAAAAAAAB')

        assert first.owner_pid == os.getpid() and first.status == 'active'
        assert first.websocket_port != second.websocket_port


class TestPidAlive:
    def test_own_process_is_alive_and_an_unused_pid_is_not(self):
        assert run_instances.pid_alive(os.getpid())
        assert not run_instances.pid_alive(DEAD_PID)
        assert not run_instances.pid_alive(None)


class TestReconcile:
    @pytest.fixture
    def hooks(self):
        with (
            patch.object(run_instances, '_dev_session_vm_names', return_value={'ubuntu_run_DEVSESSN'}),
            patch.object(run_instances, 'remove_qemu_run_instance') as remove_run,
            patch('adare.backend.vm.instance_manager.cleanup_vm_instance', new_callable=AsyncMock) as cleanup,
            patch('adare.backend.vm.instance_manager.release_vm_instance', new_callable=AsyncMock) as release,
            patch('adare.hypervisor.qemu.run_resources.remove_run_files') as remove_files,
            patch.object(run_instances, '_orphaned_run_names', return_value={'ubuntu_run_ORPHANED'}),
        ):
            yield {'remove_run': remove_run, 'cleanup': cleanup, 'release': release, 'remove_files': remove_files}

    @pytest.mark.asyncio
    async def test_classifies_every_kind_of_leftover(self, global_db, hooks):
        qemu, vbox = _vm('ubuntu'), _vm('win10', hypervisor='virtualbox')
        _instance(qemu, 'ubuntu_run_CRASHED1', owner_pid=DEAD_PID, port=18765)
        _instance(qemu, 'ubuntu_run_LIVE0001', owner_pid=os.getpid(), port=18766)
        _instance(qemu, 'ubuntu_run_DEVSESSN', owner_pid=DEAD_PID, port=18767)
        _instance(qemu, 'ubuntu_exp_POOLED01', status='available')
        _instance(vbox, 'win10_exp_CRASHED2', owner_pid=DEAD_PID, port=18768)
        _instance(vbox, 'win10_exp_LIVE0002', owner_pid=os.getpid(), port=18769)

        report = await run_instances.reconcile_instances()

        assert report.removed_runs == ['ubuntu_run_CRASHED1']
        assert report.removed_pooled_qemu == ['ubuntu_exp_POOLED01']
        assert report.released_instances == ['win10_exp_CRASHED2']
        assert report.orphaned_run_files == ['ubuntu_run_ORPHANED']
        hooks['remove_run'].assert_called_once_with('ubuntu_run_CRASHED1')
        hooks['remove_files'].assert_called_once_with('ubuntu_run_ORPHANED')
        assert hooks['cleanup'].await_count == 1 and hooks['release'].await_count == 1

    @pytest.mark.asyncio
    async def test_dry_run_changes_nothing(self, global_db, hooks):
        qemu = _vm('ubuntu')
        _instance(qemu, 'ubuntu_run_CRASHED1', owner_pid=DEAD_PID)

        report = await run_instances.reconcile_instances(dry_run=True)

        assert report.removed_runs == ['ubuntu_run_CRASHED1']
        hooks['remove_run'].assert_not_called()
        hooks['remove_files'].assert_not_called()
        assert _names() == {'ubuntu_run_CRASHED1'}

    @pytest.mark.asyncio
    async def test_unreadable_dev_sessions_mean_hands_off(self, global_db, hooks):
        qemu = _vm('ubuntu')
        _instance(qemu, 'ubuntu_run_CRASHED1', owner_pid=DEAD_PID)

        with patch.object(run_instances, '_dev_session_vm_names', return_value=None):
            report = await run_instances.reconcile_instances()

        assert report.empty
        hooks['remove_run'].assert_not_called()
