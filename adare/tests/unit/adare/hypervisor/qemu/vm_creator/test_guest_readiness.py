"""The readiness pass every unattended `vm create` ends with (--setup base and up)."""

import shutil
import subprocess
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from adare.hypervisor.qemu.vm_creator.base_creator import BaseVMCreator
from adare.hypervisor.qemu.vm_creator.guest_readiness import (
    AUTOLOGIN_LINUX,
    AUTOLOGIN_WINDOWS,
    NO_LOCK,
    NO_WELCOME,
    REBOOT,
    GuestNotReadyError,
    make_guest_ready,
    readiness_commands,
)
from adare.hypervisor.qemu.vm_creator.gui_creator import GUIVMCreator
from adare.hypervisor.qemu.vm_creator.linux_creator import LinuxVMCreator
from adare.hypervisor.qemu.vm_creator.manual_creator import ManualVMCreator
from adare.hypervisor.qemu.vm_creator.os_catalog import SetupLevel, get_os_definition
from adare.hypervisor.qemu.vm_creator.playbook_creator import PlaybookVMCreator
from adare.hypervisor.qemu.vm_creator.provision_creator import RecipeProvisionError
from adare.hypervisor.qemu.vm_creator.windows_creator import WindowsVMCreator

pytestmark = pytest.mark.unit

RUN_PROVISION = 'adare.hypervisor.qemu.vm_creator.provision_creator.run_provision'


class TestReadinessCommands:
    def test_linux_fills_desktop_gaps_then_checks_autologin_after_a_reboot(self):
        commands = readiness_commands(get_os_definition('fedora41'), SetupLevel.FULL)
        assert commands == [NO_LOCK, NO_WELCOME, REBOOT, AUTOLOGIN_LINUX]

    def test_windows_only_checks(self):
        commands = readiness_commands(get_os_definition('windows11'), SetupLevel.BASE)
        assert commands == [REBOOT, AUTOLOGIN_WINDOWS]

    def test_bare_has_no_agent_to_check_with(self):
        assert readiness_commands(get_os_definition('fedora41'), SetupLevel.BARE) == []

    @pytest.mark.skipif(shutil.which('bash') is None, reason='needs bash')
    @pytest.mark.parametrize('command', [NO_LOCK, NO_WELCOME, REBOOT, AUTOLOGIN_LINUX], ids=lambda c: c.name)
    def test_linux_commands_are_valid_bash(self, command):
        result = subprocess.run(['bash', '-n', '-c', command.command], capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr

    def test_windows_check_matches_the_autologon_user(self):
        assert "-like '*\\adare'" in AUTOLOGIN_WINDOWS.command and AUTOLOGIN_WINDOWS.shell == 'powershell'


class TestMakeGuestReady:
    def _disk(self, tmp_path) -> Path:
        disk = tmp_path / 'vm.qcow2'
        disk.write_bytes(b'installed')
        return disk

    def test_success_replaces_the_disk_with_the_checked_one(self, tmp_path):
        disk = self._disk(tmp_path)

        def fake_run(**kw):
            kw['dest_disk'].write_bytes(b'checked')
            return kw['dest_disk']

        with patch(RUN_PROVISION, side_effect=fake_run) as run:
            assert make_guest_ready(disk, get_os_definition('fedora41'), SetupLevel.FULL, 4096, 2) == disk
        assert disk.read_bytes() == b'checked'
        assert run.call_args.kwargs['title'] == 'ADARE readiness check'

    def test_failure_keeps_the_install_and_says_so(self, tmp_path):
        disk = self._disk(tmp_path)
        error = RecipeProvisionError("provision step 4/4 'automatic login works' failed with exit code 1")
        with patch(RUN_PROVISION, side_effect=error), pytest.raises(GuestNotReadyError) as err:
            make_guest_ready(disk, get_os_definition('fedora41'), SetupLevel.FULL, 4096, 2)
        assert disk.read_bytes() == b'installed'
        assert 'not ADARE-ready' in str(err.value) and f'kept at {disk}' in str(err.value)

    def test_bare_skips_the_boot(self, tmp_path):
        with patch(RUN_PROVISION) as run:
            make_guest_ready(self._disk(tmp_path), get_os_definition('fedora41'), SetupLevel.BARE, 4096, 2)
        run.assert_not_called()


class TestWhichCreatorsRunIt:
    @pytest.mark.parametrize(
        ('creator', 'runs'),
        [
            (LinuxVMCreator, True),
            (WindowsVMCreator, True),
            (PlaybookVMCreator, False),  # readies the guest in its own install session
            (ManualVMCreator, False),
            (GUIVMCreator, False),
        ],
    )
    def test_readiness_pass(self, creator, runs):
        assert creator.readiness_pass is runs

    def test_create_runs_it_instead_of_the_separate_compress(self, tmp_path):
        class Creator(BaseVMCreator):
            def _ensure_iso(self):
                pass

            def _run_installation(self, disk_path, nvram_path):
                pass

        os_def = replace(get_os_definition('fedora41'), requires_uefi=False)
        creator = Creator(os_def=os_def, vm_dir=tmp_path)
        with (
            patch.object(Creator, '_print_config_panel'),
            patch.object(Creator, '_check_prerequisites'),
            patch.object(Creator, '_create_disk', return_value=(tmp_path / 'd.qcow2', None)),
            patch.object(Creator, '_validate_disk_after_install'),
            patch.object(Creator, '_print_success'),
            patch.object(Creator, '_compress_disk') as compress,
            patch.object(Creator, '_make_guest_ready', MagicMock(return_value=tmp_path / 'd.qcow2')) as ready,
        ):
            creator.create()
        ready.assert_called_once()
        compress.assert_not_called()
