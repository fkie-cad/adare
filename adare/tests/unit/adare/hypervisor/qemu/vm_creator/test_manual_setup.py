"""After a manual install, ADARE installs its guest agent the way a playbook install does."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from adare.hypervisor.qemu.vm_creator.manual_creator import ManualVMCreator
from adare.hypervisor.qemu.vm_creator.os_catalog import SetupLevel, get_os_definition
from adare.hypervisor.qemu.vm_creator.playbook_creator import PlaybookVMCreationError, PlaybookVMCreator

pytestmark = pytest.mark.unit

MOD = 'adare.hypervisor.qemu.vm_creator.manual_creator'


def _creator(os_name='mint', setup_level=SetupLevel.FULL, tmp_path=None) -> ManualVMCreator:
    return ManualVMCreator(
        os_def=get_os_definition(os_name), vm_dir=tmp_path, iso_path=Path('x.iso'), setup_level=setup_level
    )


class TestRunInstallation:
    @pytest.mark.parametrize(
        ('os_name', 'level', 'expected'),
        [
            ('mint', SetupLevel.FULL, True),
            ('mint', SetupLevel.BASE, True),
            ('mint', SetupLevel.BARE, False),
            ('windows11', SetupLevel.FULL, False),
        ],
    )
    def test_setup_follows_the_install_for_linux_base_and_up(self, tmp_path, os_name, level, expected):
        creator = _creator(os_name, level, tmp_path)
        with (
            patch(f'{MOD}._run_manual_installation') as install,
            patch.object(ManualVMCreator, '_make_manual_install_ready') as ready,
        ):
            creator._run_installation(tmp_path / 'd.qcow2', None)
        assert ready.called is expected
        assert install.call_args.kwargs['account_hint'] is expected


class TestMakeManualInstallReady:
    @pytest.fixture
    def boot(self):
        with (
            patch('adare.hypervisor.qemu.vm_creator.interactive.build_post_install_qemu_cmd', return_value=['qemu']),
            patch(f'{MOD}.subprocess.Popen') as popen,
            patch(f'{MOD}.console') as console,
        ):
            self.console = console
            yield popen

    def _printed(self) -> str:
        return ' '.join(str(c.args[0]) for c in self.console.print.call_args_list)

    def test_runs_the_playbook_engine_on_the_installed_disk(self, tmp_path, boot):
        with patch.object(PlaybookVMCreator, 'make_ready_in_session') as session:
            _creator(tmp_path=tmp_path)._make_manual_install_ready(tmp_path / 'd.qcow2', None)
        proc, qmp, qga, run_dir = session.call_args.args
        assert proc is boot.return_value and qga.name == 'qga.sock' and run_dir.name.endswith('_setup')
        assert 'ADARE-ready' in self._printed()

    def test_failure_only_warns_and_names_the_account(self, tmp_path, boot):
        error = PlaybookVMCreationError('the guest agent did not come up within 900s')
        with patch.object(PlaybookVMCreator, 'make_ready_in_session', side_effect=error):
            _creator(tmp_path=tmp_path)._make_manual_install_ready(tmp_path / 'd.qcow2', None)
        out = self._printed()
        assert 'not ADARE-ready' in out and 'did not come up' in out and 'password adare' in out

    def test_nixos_gets_instructions_instead_of_a_boot(self, tmp_path, boot):
        with patch.object(PlaybookVMCreator, 'make_ready_in_session', MagicMock()) as session:
            _creator('nixos', tmp_path=tmp_path)._make_manual_install_ready(tmp_path / 'd.qcow2', None)
        session.assert_not_called()
        boot.assert_not_called()
        assert 'services.qemuGuest.enable' in self._printed()
