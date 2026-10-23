"""`adare vm remove`: one command for registered VMs and instances, auto-detected."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from adare.backend.vm.removal import VmRemovalOutcome, VmRemovalPlan
from adare.backend.vm.resolve import VmTarget
from adare.core.result import Result

pytestmark = pytest.mark.unit

VM = VmTarget('vm', '01M5MJSFMZ7GXQQJ643ZYGBGPC', 'ubuntu2404-20261023')
INSTANCE = VmTarget('instance', '01M5MJSFMZ7GXQQJ643ZYGBGPD', 'ubuntu2404-20261023_run_12345678')


def _plan() -> VmRemovalPlan:
    return VmRemovalPlan(
        vm_id=VM.id,
        vm_name=VM.name,
        disk=Path('/adare/vms/u.qcow2'),
        disk_managed=True,
        environments={'ubuntu2404-20261023': ['ENV1']},
    )


@pytest.fixture
def backend():
    outcome = VmRemovalOutcome(
        vm_name=VM.name, environments=['ubuntu2404-20261023'], disk=Path('/adare/vms/u.qcow2'), disk_deleted=True
    )
    api = MagicMock()
    with (
        patch('adare.backend.vm.resolve.resolve_vm_target') as resolve,
        patch('adare.backend.vm.removal.plan_vm_removal', return_value=_plan()),
        patch('adare.backend.vm.removal.remove_vm', return_value=outcome) as remove_vm,
        patch('adare.cli.vm.AdareAPI', return_value=api),
        patch('adare.cli.vm._stdin_is_terminal', return_value=True),
    ):
        yield MagicMock(resolve=resolve, remove_vm=remove_vm, api=api)


def _invoke(*args, input=None):
    from adare.run import cli

    return CliRunner().invoke(cli, ['vm', 'remove', *args], input=input)


class TestRegisteredVm:
    def test_positional_name_removes_after_confirmation(self, backend):
        backend.resolve.return_value = VM

        result = _invoke(VM.name, input='y\n')

        assert result.exit_code == 0, result.output
        backend.resolve.assert_called_once_with(VM.name)
        backend.remove_vm.assert_called_once_with(VM.id, force=False)
        assert 'environment ubuntu2404-20261023 (1 version(s))' in result.output
        assert '(deleted)' in result.output

    def test_answering_no_removes_nothing(self, backend):
        backend.resolve.return_value = VM

        result = _invoke(VM.name, input='n\n')

        assert result.exit_code == 0
        backend.remove_vm.assert_not_called()

    def test_yes_skips_the_prompt_and_force_is_passed_on(self, backend):
        backend.resolve.return_value = VM

        result = _invoke(VM.name, '--yes', '--force')

        assert result.exit_code == 0, result.output
        backend.remove_vm.assert_called_once_with(VM.id, force=True)

    def test_without_a_terminal_it_needs_yes(self, backend):
        backend.resolve.return_value = VM

        with patch('adare.cli.vm._stdin_is_terminal', return_value=False):
            result = _invoke(VM.name)

        assert result.exit_code == 2
        backend.remove_vm.assert_not_called()

    def test_legacy_id_option_takes_a_registered_vm_too(self, backend):
        backend.resolve.return_value = VM

        result = _invoke('--id', VM.id, '-y')

        assert result.exit_code == 0, result.output
        backend.resolve.assert_called_once_with(VM.id)


class TestInstance:
    def test_positional_instance_is_removed_with_force_forwarded(self, backend):
        backend.resolve.return_value = INSTANCE

        async def remove_instance(instance_id, force=False):
            return Result.ok(None)

        backend.api.vm.remove_instance = MagicMock(side_effect=remove_instance)

        result = _invoke(INSTANCE.name, '--force')

        assert result.exit_code == 0, result.output
        backend.api.vm.remove_instance.assert_called_once_with(INSTANCE.id, force=True)
        backend.remove_vm.assert_not_called()


class TestUsage:
    def test_target_and_a_bulk_selector_conflict(self, backend):
        result = _invoke(VM.name, '--stopped')

        assert result.exit_code == 2
        backend.resolve.assert_not_called()

    def test_nothing_to_remove_is_a_usage_error(self, backend):
        assert _invoke().exit_code == 2

    def test_all_without_force_is_a_usage_error(self, backend):
        assert _invoke('--all').exit_code == 2
