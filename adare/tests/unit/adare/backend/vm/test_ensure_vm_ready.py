"""ensure_vm_ready_for_experiment: QEMU run instances vs. pooled VirtualBox instances."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from adare.backend.vm import commands

pytestmark = pytest.mark.unit


def _instance(**overrides):
    fields = {
        'id': 'inst-1',
        'instance_name': 'win10_exp_1',
        'websocket_port': 18765,
        'vbox_uuid': None,
        'base_snapshot_name': None,
    }
    return SimpleNamespace(**{**fields, **overrides})


@pytest.fixture
def env():
    source_vm = SimpleNamespace(id='vm-1', hypervisor='virtualbox', file='/disks/win10.ova')
    api = MagicMock()
    api.__enter__.return_value = api
    api.get_vm_by_id.return_value = source_vm
    with (
        patch('adare.database.api.vm.VmApi', return_value=api),
        patch('adare.backend.vm.instance_manager.allocate_vm_instance_for_experiment', new_callable=AsyncMock) as alloc,
        patch('adare.backend.vm.snapshot_manager.create_base_snapshot_for_instance', return_value=True) as snap,
        patch('adare.backend.vm.snapshot_manager.restore_instance_to_base_snapshot', return_value=True) as restore,
        patch.object(commands, 'verify_vm_integrity', new_callable=AsyncMock) as verify,
        patch.object(commands, '_import_vm_instance', new_callable=AsyncMock) as import_vm,
        patch.object(commands, '_prepare_qemu_run_instance', new_callable=AsyncMock) as qemu,
    ):
        yield SimpleNamespace(
            source_vm=source_vm,
            api=api,
            alloc=alloc,
            snap=snap,
            restore=restore,
            verify=verify,
            import_vm=import_vm,
            qemu=qemu,
        )


@pytest.mark.asyncio
async def test_qemu_gets_a_run_instance(env):
    env.source_vm.hypervisor = 'qemu'
    env.qemu.return_value = 'run-inst'

    assert await commands.ensure_vm_ready_for_experiment('vm-1', experiment_run_ulid='01J') == 'run-inst'
    env.alloc.assert_not_awaited()


@pytest.mark.asyncio
async def test_reused_virtualbox_instance_is_restored_not_reimported(env):
    env.alloc.return_value = _instance(vbox_uuid='uuid', base_snapshot_name='win10_exp_1_base')

    assert await commands.ensure_vm_ready_for_experiment('vm-1') == 'inst-1'
    env.restore.assert_called_once()
    env.import_vm.assert_not_awaited()
    env.snap.assert_not_called()


@pytest.mark.asyncio
async def test_reused_instance_without_base_snapshot_takes_one_first(env):
    env.alloc.return_value = _instance(vbox_uuid='uuid')
    env.api.get_vm_instance_by_id.return_value = _instance(vbox_uuid='uuid', base_snapshot_name='b')

    await commands.ensure_vm_ready_for_experiment('vm-1')

    env.snap.assert_called_once()
    assert env.restore.call_args.args[0].base_snapshot_name == 'b'


@pytest.mark.asyncio
async def test_new_virtualbox_instance_is_verified_imported_and_snapshotted(env):
    env.alloc.return_value = _instance()
    env.import_vm.return_value = _instance(vbox_uuid='uuid')

    assert await commands.ensure_vm_ready_for_experiment('vm-1', test_mode=True) == 'inst-1'
    env.verify.assert_awaited_once()
    env.import_vm.assert_awaited_once()
    env.snap.assert_called_once()
    env.restore.assert_not_called()


@pytest.mark.asyncio
async def test_interrupt_during_restore_returns_none(env):
    env.alloc.return_value = _instance(vbox_uuid='uuid', base_snapshot_name='b')
    interrupt = MagicMock()
    interrupt.is_set.side_effect = [False, True]

    assert await commands.ensure_vm_ready_for_experiment('vm-1', interrupt_event=interrupt) is None
