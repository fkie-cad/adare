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
    PYTHON_ENV_WINDOWS,
    REBOOT,
    REBOOT_WINDOWS,
    WINFSP_WINDOWS,
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
        assert commands == [REBOOT_WINDOWS, AUTOLOGIN_WINDOWS, WINFSP_WINDOWS]

    def test_windows_full_also_checks_the_agent_python(self):
        # First logon's `conda create` once failed silently and left an empty env.
        commands = readiness_commands(get_os_definition('windows11'), SetupLevel.FULL)
        assert commands == [REBOOT_WINDOWS, AUTOLOGIN_WINDOWS, WINFSP_WINDOWS, PYTHON_ENV_WINDOWS]

    def test_windows_arm64_has_no_winfsp_or_conda_to_check(self):
        # Its answer file uses SMB shares and a system Python.
        commands = readiness_commands(get_os_definition('windows11arm64'), SetupLevel.FULL)
        assert commands == [REBOOT_WINDOWS, AUTOLOGIN_WINDOWS]

    def test_windows_never_runs_bash(self):
        # guest-exec of /bin/bash on a Windows guest never returns; the step timed out.
        commands = readiness_commands(get_os_definition('windows11'), SetupLevel.FULL)
        assert all(command.shell in ('powershell', 'cmd') for command in commands)

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


@pytest.mark.skipif(shutil.which('bash') is None, reason='needs bash')
@pytest.mark.parametrize(('version_id', 'stamp'), [('26.04', 'upgrade-26.04-done'), ('', None)])
def test_no_welcome_also_stamps_the_release_welcome(tmp_path, version_id, stamp):
    """Ubuntu 26.04 shows a per-release welcome whenever the done marker exists without its stamp."""
    home = tmp_path / 'home'
    os_release = tmp_path / 'os-release'
    os_release.write_text(f'NAME="Ubuntu"\nVERSION_ID="{version_id}"\n' if version_id else 'NAME="Other"\n')
    script = (
        NO_WELCOME.command.replace('$(getent passwd adare | cut -d: -f6)', str(home))
        .replace('/etc/os-release', str(os_release))
        .replace('/etc/xdg/autostart', str(tmp_path / 'xdg'))
        .replace('install -d -o adare -g adare', 'install -d')
        .replace('chown adare:adare', 'true')
    )

    subprocess.run(['bash', '-c', script], check=True)

    assert (home / '.config/gnome-initial-setup-done').read_text() == 'yes'
    stamps = [p.name for p in (home / '.config/gnome-initial-setup').iterdir()]
    assert stamps == ([stamp] if stamp else [])
