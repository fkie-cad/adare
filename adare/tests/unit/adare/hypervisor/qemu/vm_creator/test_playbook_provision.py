"""Tests for making a playbook-installed desktop ADARE-ready (--setup base and up)."""

import shutil
import subprocess
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

import adare
from adare.hypervisor.qemu.vm_creator.os_catalog import SetupLevel, get_os_definition
from adare.hypervisor.qemu.vm_creator.playbook_creator import (
    PlaybookVMCreationError,
    PlaybookVMCreator,
    _char_to_keys,
)
from adare.hypervisor.qemu.vm_creator.playbook_provision import (
    AUTOLOGIN_CHECK_LINUX,
    bootstrap_steps,
    provision_steps,
)

pytestmark = pytest.mark.unit

MOD = 'adare.hypervisor.qemu.vm_creator.playbook_creator'
PROFILES_DIR = Path(adare.__file__).parent.parent / 'appdata' / 'os-profiles'


def _playbook_profile_names() -> list[str]:
    return [
        p.stem
        for p in sorted(PROFILES_DIR.glob('*.yml'))
        if yaml.safe_load(p.read_text()).get('install_mode') == 'playbook'
    ]


def _creator(setup_level: SetupLevel = SetupLevel.FULL, os_name: str = 'ubuntu2404') -> PlaybookVMCreator:
    creator = PlaybookVMCreator.__new__(PlaybookVMCreator)
    creator.os_def = get_os_definition(os_name)
    creator.setup_level = setup_level
    creator.ram_mb = 4096
    creator.cpus = 2
    return creator


class TestProvisionSteps:
    def test_bare_adds_nothing(self):
        assert provision_steps(SetupLevel.BARE, 'x86_64') == []

    def test_base_readies_the_desktop_without_python_tooling(self):
        names = [s.name for s in provision_steps(SetupLevel.BASE, 'x86_64')]
        assert 'automatic login' in names and 'no screen lock or blanking' in names
        assert 'no first-login welcome wizard' in names
        assert 'uv' not in names and 'python3-pip' not in names

    def test_full_adds_uv_for_the_guest_architecture(self):
        steps = {s.name: s for s in provision_steps(SetupLevel.FULL, 'aarch64')}
        assert 'uv-aarch64-unknown-linux-gnu' in steps['uv'].command

    @pytest.mark.skipif(shutil.which('bash') is None, reason='needs bash')
    @pytest.mark.parametrize('step', provision_steps(SetupLevel.FULL, 'x86_64'), ids=lambda s: s.name)
    def test_every_command_is_valid_bash(self, step):
        result = subprocess.run(['bash', '-n', '-c', step.command], capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr

    @pytest.mark.skipif(shutil.which('bash') is None, reason='needs bash')
    def test_autologin_check_is_valid_bash(self):
        assert subprocess.run(['bash', '-n', '-c', AUTOLOGIN_CHECK_LINUX], check=False).returncode == 0


class TestBootstrapSteps:
    def test_default_installs_the_agent_from_a_text_console(self):
        steps = bootstrap_steps(get_os_definition('ubuntu2404'))
        assert steps[0] == {'action': 'key', 'keys': ['ctrl', 'alt', 'f3'], 'note': 'switch to a text console'}
        assert 'qemu-guest-agent' in steps[-1]['text'] and steps[-1]['text'].endswith('\n')

    def test_every_typed_character_has_a_key(self):
        for step in bootstrap_steps(get_os_definition('ubuntu2404')):
            for ch in step.get('text', ''):
                _char_to_keys(ch)  # raises on an unmapped character

    def test_profile_override_wins(self):
        custom = [{'action': 'type', 'text': 'x\n'}]
        assert bootstrap_steps(replace(get_os_definition('ubuntu2404'), bootstrap_steps=custom)) == custom

    @pytest.mark.parametrize('name', _playbook_profile_names())
    def test_default_bootstrap_only_serves_apt_profiles(self, name):
        os_def = get_os_definition(name)
        assert os_def.bootstrap_steps or os_def.distribution in ('ubuntu', 'kubuntu', 'debian'), (
            f'{name}: the default bootstrap installs the agent with apt; give the profile its own bootstrap_steps'
        )


class TestLaunch:
    def _cmd(self, tmp_path, qga_sock):
        with (
            patch(f'{MOD}.qemu_params_for_arch', return_value={'exe': 'qemu-system-x86_64'}),
            patch(f'{MOD}.subprocess.Popen') as popen,
        ):
            _creator()._launch(tmp_path / 'd.qcow2', None, tmp_path / 'qmp.sock', tmp_path, None, qga_sock=qga_sock)
        return popen.call_args.args[0]

    def test_provisioning_boot_gets_a_guest_agent_port(self, tmp_path):
        cmd = self._cmd(tmp_path, tmp_path / 'qga.sock')
        assert f'socket,path={tmp_path / "qga.sock"},server=on,wait=off,id=qga0' in cmd
        assert 'virtserialport,chardev=qga0,name=org.qemu.guest_agent.0' in cmd

    def test_installer_boot_has_no_guest_agent_port(self, tmp_path):
        assert not any('guest_agent' in arg for arg in self._cmd(tmp_path, None))


class TestRunInstallation:
    def _run(self, tmp_path, setup_level):
        creator = _creator(setup_level)
        creator.iso_path = tmp_path / 'x.iso'
        creator.vm_name = 'vm'
        with (
            patch.object(PlaybookVMCreator, '_launch'),
            patch(f'{MOD}._QMP'),
            patch.object(PlaybookVMCreator, '_run_steps'),
            patch.object(PlaybookVMCreator, '_shutdown') as shutdown,
            patch.object(PlaybookVMCreator, '_stop'),
            patch.object(PlaybookVMCreator, '_make_adare_ready') as ready,
            patch.object(PlaybookVMCreator, '_shutdown_via_agent') as agent_shutdown,
        ):
            creator._run_installation(tmp_path / 'disk.qcow2', None)
        return ready, agent_shutdown, shutdown

    def test_default_setup_makes_the_guest_ready(self, tmp_path):
        ready, agent_shutdown, shutdown = self._run(tmp_path, SetupLevel.FULL)
        ready.assert_called_once()
        agent_shutdown.assert_called_once()
        assert shutdown.call_count == 1  # only the installer's live session

    def test_bare_leaves_the_stock_install(self, tmp_path):
        ready, agent_shutdown, shutdown = self._run(tmp_path, SetupLevel.BARE)
        ready.assert_not_called()
        agent_shutdown.assert_not_called()
        assert shutdown.call_count == 2


class TestMakeAdareReady:
    @pytest.fixture(autouse=True)
    def _quiet(self):
        with (
            patch.object(PlaybookVMCreator, '_run_steps'),
            patch.object(PlaybookVMCreator, '_save_shot') as save_shot,
            patch(f'{MOD}.qga_shutdown') as shutdown,
            patch(f'{MOD}.time.sleep'),
        ):
            self.save_shot = save_shot
            self.qga_shutdown = shutdown
            yield

    def test_agent_never_up_fails_with_a_screenshot(self, tmp_path):
        with (
            patch.object(PlaybookVMCreator, '_wait_for_agent', return_value=False),
            pytest.raises(PlaybookVMCreationError, match='guest agent did not come up'),
        ):
            _creator()._make_adare_ready(MagicMock(), tmp_path / 'qga.sock', tmp_path)
        assert self.save_shot.call_args.args[1] == tmp_path / 'bootstrap_FAILED.png'

    def test_failing_step_names_itself_and_its_error(self, tmp_path):
        with (
            patch.object(PlaybookVMCreator, '_wait_for_agent', return_value=True),
            patch(f'{MOD}.qga_exec', return_value=(100, '', 'E: Unable to locate package cifs-utils\n')),
            pytest.raises(PlaybookVMCreationError, match=r"'passwordless sudo' exited 100: E: Unable to locate"),
        ):
            _creator()._make_adare_ready(MagicMock(), tmp_path / 'qga.sock', tmp_path)

    def test_success_runs_every_step_then_checks_after_reboot(self, tmp_path):
        exec_mock = MagicMock(return_value=(0, '', ''))
        with (
            patch.object(PlaybookVMCreator, '_wait_for_agent', return_value=True),
            patch(f'{MOD}.qga_exec', exec_mock),
        ):
            _creator(SetupLevel.BASE)._make_adare_ready(MagicMock(), tmp_path / 'qga.sock', tmp_path)
        commands = [c.args[1] for c in exec_mock.call_args_list]
        expected = [s.command for s in provision_steps(SetupLevel.BASE, 'x86_64')]
        assert commands == [*expected, AUTOLOGIN_CHECK_LINUX]
        self.qga_shutdown.assert_called_once_with(tmp_path / 'qga.sock', 'reboot')

    def test_missing_autologin_fails(self, tmp_path):
        def fake_exec(_sock, command, **_kw):
            return (1, '', '') if command == AUTOLOGIN_CHECK_LINUX else (0, '', '')

        with (
            patch.object(PlaybookVMCreator, '_wait_for_agent', return_value=True),
            patch(f'{MOD}.qga_exec', side_effect=fake_exec),
            patch(f'{MOD}.AUTOLOGIN_TIMEOUT_S', 0),
            pytest.raises(PlaybookVMCreationError, match='automatic login is not working'),
        ):
            _creator()._make_adare_ready(MagicMock(), tmp_path / 'qga.sock', tmp_path)
