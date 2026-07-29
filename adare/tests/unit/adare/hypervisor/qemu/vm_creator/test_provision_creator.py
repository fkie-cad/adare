"""Tests for `run_provision` against a fake QEMU guest agent (T7, T8).

Every QEMU/QGA touchpoint is patched at module level, so the whole host-side
provisioning engine — command sequencing, exit-code policy, verify, reboot,
log pulling, clean shutdown, flatten — is exercised without a hypervisor.

The tests that matter most are the abort ones: the module's central invariant is
that a partially-provisioned disk can NEVER be flattened or registered, because
its recipe hash would vouch for contents it does not have.
"""

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

from adare.hypervisor.qemu.vm_creator.os_catalog import OsDefinition
from adare.hypervisor.qemu.vm_creator.provision_creator import (
    RecipeProvisionError,
    run_provision,
)
from adare.hypervisor.qemu.vm_creator.qga_utils import QgaError
from adare.types.environment import ProvisionCommand

_MODULE = 'adare.hypervisor.qemu.vm_creator.provision_creator'


# --- Helpers ---

def _os_def(**overrides) -> OsDefinition:
    defaults = dict(
        name='windows11arm64', display_name='Windows 11 (ARM64)', platform='windows',
        distribution='windows', version='11', iso_url='', iso_sha256='',
        iso_filename='', default_disk_size='160G', default_ram_mb=8192,
        default_cpus=4, architecture='aarch64', requires_uefi=True,
    )
    defaults.update(overrides)
    return OsDefinition(**defaults)


def _commands(count: int = 3) -> list[ProvisionCommand]:
    return [
        ProvisionCommand(name=f'step-{i}', command=f'do-thing-{i}', shell='powershell')
        for i in range(1, count + 1)
    ]


class _FakeAgent:
    """Records every exec and returns scripted results.

    `results` maps a command string to (returncode, stdout, stderr); anything not
    listed succeeds with rc 0. A QgaError can be scripted by mapping to an
    exception instance.
    """

    def __init__(self, results: dict | None = None, ready: bool = True):
        self.results = results or {}
        self.ready = ready
        self.calls: list[str] = []
        self.pulled: list[tuple[str, str]] = []
        self.reboots = 0

    def wait_ready(self, sock, timeout=None):
        return self.ready

    def exec(self, sock, command, cwd=None, shell=None, timeout=None,
             progress_callback=None, **kwargs):
        self.calls.append(command)
        outcome = self.results.get(command, (0, '', ''))
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def pull(self, sock, remote, local):
        self.pulled.append((remote, str(local)))
        Path(local).write_text('fake guest log')
        return 14

    def reboot(self, sock, ready_timeout=None):
        self.reboots += 1


@pytest.fixture
def harness(tmp_path):
    """Patch every QEMU/QGA seam and yield (agent, calls_recorder, tmp paths)."""
    agent = _FakeAgent()
    base = tmp_path / 'base.qcow2'
    base.write_bytes(b'fake base disk')
    dest = tmp_path / 'out' / 'provisioned.qcow2'
    dest.parent.mkdir()
    build_log = tmp_path / 'logs' / 'provision-abc123.log'

    # Not spec'd to subprocess.Popen: `stderr` is an instance attribute rather than
    # a class one, so a spec'd mock rejects setting it.
    process = MagicMock()
    process.poll.return_value = None
    process.returncode = 0
    process.wait.return_value = 0
    process.stderr.read.return_value = b''

    flattened: list[tuple[Path, Path]] = []

    def _flatten(overlay, dst, compress=True):
        flattened.append((Path(overlay), Path(dst)))
        Path(dst).write_bytes(b'flattened')
        return Path(dst)

    overlays: list[Path] = []

    def _overlay(base_disk, overlay_path):
        overlays.append(Path(overlay_path))
        Path(overlay_path).parent.mkdir(parents=True, exist_ok=True)
        Path(overlay_path).write_bytes(b'overlay')
        return Path(overlay_path)

    # Replace the module's whole `subprocess` reference rather than patching
    # `subprocess.Popen` in place: the latter mutates the real stdlib module, which
    # other code reached through it during a test would also see.
    fake_subprocess = MagicMock()
    fake_subprocess.Popen.return_value = process
    fake_subprocess.PIPE = subprocess.PIPE
    fake_subprocess.TimeoutExpired = subprocess.TimeoutExpired

    with (
        patch(f'{_MODULE}.qga_wait_ready', side_effect=agent.wait_ready),
        patch(f'{_MODULE}.qga_exec', side_effect=agent.exec),
        patch(f'{_MODULE}.qga_pull_file', side_effect=agent.pull),
        patch(f'{_MODULE}.qga_reboot', side_effect=agent.reboot),
        patch(f'{_MODULE}.send_acpi_shutdown', return_value=True) as shutdown,
        patch(f'{_MODULE}.subprocess', fake_subprocess),
        patch(f'{_MODULE}.create_work_overlay', side_effect=_overlay),
        patch(f'{_MODULE}.flatten_overlay', side_effect=_flatten) as flatten,
        patch(f'{_MODULE}.create_nvram_for_vm',
              side_effect=lambda name, d, arch: str(Path(d) / f'{name}-nvram.fd')),
        patch(f'{_MODULE}.build_post_install_qemu_cmd', return_value=['qemu-system-fake']),
        patch(f'{_MODULE}.time.sleep'),
    ):
        yield {
            'agent': agent, 'base': base, 'dest': dest, 'build_log': build_log,
            'process': process, 'flatten': flatten, 'shutdown': shutdown,
            'flattened': flattened, 'overlays': overlays,
        }


def _run(harness, commands, **kwargs):
    return run_provision(
        base_disk=harness['base'], dest_disk=harness['dest'], commands=commands,
        os_def=_os_def(), ram_mb=8192, cpus=4,
        build_log_path=harness['build_log'], **kwargs,
    )


# --- T7: the happy path, end to end ---

def test_runs_every_command_in_order(harness):
    commands = _commands(4)
    _run(harness, commands)
    assert harness['agent'].calls == ['do-thing-1', 'do-thing-2', 'do-thing-3', 'do-thing-4']


def test_returns_the_flattened_destination_disk(harness):
    result = _run(harness, _commands(1))
    assert result == harness['dest']
    assert harness['dest'].is_file()


def test_flattens_the_overlay_not_the_base(harness):
    """The base must be read through the backing chain, never mutated."""
    _run(harness, _commands(1))
    overlay, dest = harness['flattened'][0]
    assert overlay == harness['overlays'][0]
    assert overlay != harness['base']
    assert dest == harness['dest']
    assert harness['base'].read_bytes() == b'fake base disk'


def test_shuts_the_guest_down_before_flattening(harness):
    """Order matters: flattening a still-running guest captures a dirty filesystem."""
    order = []
    harness['shutdown'].side_effect = lambda sock: order.append('shutdown') or True
    harness['flatten'].side_effect = lambda o, d, compress=True: (
        order.append('flatten'), Path(d).write_text('x'), Path(d))[2]
    _run(harness, _commands(1))
    assert order == ['shutdown', 'flatten']


def test_exit_code_3010_is_accepted_when_allowed(harness):
    """Windows installers use 3010 for "success, reboot required"."""
    harness['agent'].results = {'msiexec': (3010, '', '')}
    command = ProvisionCommand(name='install', command='msiexec',
                               shell='powershell', allow_exit_codes=[0, 3010])
    _run(harness, [command])
    assert harness['dest'].is_file()


def test_verify_runs_after_the_command_and_only_on_success(harness):
    command = ProvisionCommand(
        name='install', command='do-install', shell='powershell',
        verify='assert-installed',
    )
    _run(harness, [command])
    assert harness['agent'].calls == ['do-install', 'assert-installed']


def test_reboot_step_reboots_and_waits_for_the_agent_again(harness):
    command = ProvisionCommand(name='patch', command='apply-patch',
                               shell='powershell', reboot=True)
    _run(harness, [command])
    assert harness['agent'].reboots == 1


def test_no_reboot_by_default(harness):
    _run(harness, _commands(2))
    assert harness['agent'].reboots == 0


def test_stderr_output_on_a_zero_exit_is_not_a_failure(harness):
    """PowerShell writes CLIXML progress records to stderr on success.

    Judging success by "stderr is empty" would fail every PowerShell step.
    """
    harness['agent'].results = {
        'do-thing-1': (0, 'fine', '#< CLIXML\r\n<Objs ...>Preparing modules for first use.'),
    }
    _run(harness, _commands(1))
    assert harness['dest'].is_file()


def test_host_log_records_each_command_with_its_exit_code_and_output(harness):
    harness['agent'].results = {'do-thing-2': (0, 'the stdout', 'the stderr')}
    _run(harness, _commands(2))
    text = harness['build_log'].read_text()
    assert 'step-1' in text and 'step-2' in text
    assert 'do-thing-2' in text
    assert 'the stdout' in text and 'the stderr' in text
    assert 'exit code:    0' in text
    assert 'interpreter:  powershell' in text
    assert 'clean shutdown' in text


def test_host_log_records_the_verify_separately_from_the_command(harness):
    command = ProvisionCommand(name='install', command='do-install',
                               shell='powershell', verify='assert-installed')
    _run(harness, [command])
    text = harness['build_log'].read_text()
    assert '(command)' in text
    assert '(verify)' in text


def test_empty_command_list_is_rejected(harness):
    """Stage 2 must not be entered at all when there is nothing to do."""
    with pytest.raises(RecipeProvisionError, match='no provision commands'):
        _run(harness, [])


# --- T8: abort semantics ---

def test_disallowed_exit_code_aborts_naming_the_step(harness):
    commands = _commands(3)
    harness['agent'].results = {'do-thing-2': (1, 'out', 'err')}
    with pytest.raises(RecipeProvisionError) as excinfo:
        _run(harness, commands)
    message = str(excinfo.value)
    assert 'step-2' in message
    assert '2/3' in message
    assert 'exit code 1' in message


def test_abort_stops_before_the_remaining_commands(harness):
    """Command 14 of 48 failing must not run 15..48."""
    commands = _commands(5)
    harness['agent'].results = {'do-thing-3': (1, '', '')}
    with pytest.raises(RecipeProvisionError):
        _run(harness, commands)
    assert harness['agent'].calls == ['do-thing-1', 'do-thing-2', 'do-thing-3']


def test_abort_never_flattens(harness):
    """THE invariant: no disk is produced from a partially-provisioned overlay."""
    harness['agent'].results = {'do-thing-2': (1, '', '')}
    with pytest.raises(RecipeProvisionError):
        _run(harness, _commands(3))
    harness['flatten'].assert_not_called()
    assert not harness['dest'].exists()


def test_abort_pulls_the_failed_step_log_files(harness):
    command = ProvisionCommand(
        name='install', command='msiexec', shell='powershell',
        log_files=['C:\\Windows\\Temp\\autopsy-4.12.0-msi.log'],
    )
    harness['agent'].results = {'msiexec': (1603, '', '')}
    with pytest.raises(RecipeProvisionError):
        _run(harness, [command])
    assert harness['agent'].pulled
    remote, local = harness['agent'].pulled[0]
    assert remote == 'C:\\Windows\\Temp\\autopsy-4.12.0-msi.log'
    assert Path(local).is_file()


def test_a_failed_log_pull_does_not_replace_the_real_error(harness):
    """Losing an installer log must not mask why the step failed."""
    command = ProvisionCommand(name='install', command='msiexec', shell='powershell',
                               log_files=['C:\\gone.log'])
    harness['agent'].results = {'msiexec': (1603, '', '')}
    with patch(f'{_MODULE}.qga_pull_file', side_effect=QgaError('no such file')):
        with pytest.raises(RecipeProvisionError, match='exit code 1603'):
            _run(harness, [command])


def test_failing_verify_aborts_even_though_the_command_succeeded(harness):
    """An installer's own exit code is not evidence it did anything."""
    command = ProvisionCommand(
        name='install', command='do-install', shell='powershell',
        verify='assert-installed',
    )
    harness['agent'].results = {'assert-installed': (1, '', '')}
    with pytest.raises(RecipeProvisionError) as excinfo:
        _run(harness, [command])
    assert 'verify failed' in str(excinfo.value)
    harness['flatten'].assert_not_called()


def test_failing_verify_pulls_log_files_too(harness):
    command = ProvisionCommand(
        name='install', command='do-install', shell='powershell',
        verify='assert-installed', log_files=['C:\\Windows\\Temp\\x.log'],
    )
    harness['agent'].results = {'assert-installed': (1, '', '')}
    with pytest.raises(RecipeProvisionError):
        _run(harness, [command])
    assert harness['agent'].pulled


def test_step_timeout_aborts(harness):
    harness['agent'].results = {'do-thing-1': QgaError('Timeout waiting for guest command')}
    with pytest.raises(RecipeProvisionError, match='did not complete'):
        _run(harness, _commands(1))
    harness['flatten'].assert_not_called()


def test_agent_never_ready_aborts_and_leaves_the_base_intact(harness):
    """The cached base took hours to install; a failed Stage 2 must not touch it."""
    with patch(f'{_MODULE}.qga_wait_ready', return_value=False):
        with pytest.raises(RecipeProvisionError, match='guest agent did not respond'):
            _run(harness, _commands(2))
    assert harness['base'].read_bytes() == b'fake base disk'
    harness['flatten'].assert_not_called()
    assert harness['agent'].calls == []


def test_agent_never_ready_message_points_at_setup_level(harness):
    """The overwhelmingly likely cause is setup_level 0, which ships no agent."""
    with patch(f'{_MODULE}.qga_wait_ready', return_value=False):
        with pytest.raises(RecipeProvisionError, match='setup_level'):
            _run(harness, _commands(1))


def test_rejected_acpi_shutdown_is_a_hard_failure(harness):
    """Never flatten a volume whose consistency cannot be assumed."""
    harness['shutdown'].return_value = False
    with pytest.raises(RecipeProvisionError, match='ACPI shutdown'):
        _run(harness, _commands(1))
    harness['flatten'].assert_not_called()


def test_guest_that_will_not_power_off_is_a_hard_failure(harness):
    """A dirty NTFS volume boots the consumer into Startup Repair.

    The recipe hash would nonetheless vouch for that disk, so this must abort
    rather than flatten.
    """
    harness['process'].wait.side_effect = subprocess.TimeoutExpired('qemu', 1200)
    with pytest.raises(RecipeProvisionError, match='did not power off'):
        _run(harness, _commands(1))
    harness['flatten'].assert_not_called()
    assert not harness['dest'].exists()


def test_dirty_shutdown_error_explains_the_consequence(harness):
    harness['process'].wait.side_effect = subprocess.TimeoutExpired('qemu', 1200)
    with pytest.raises(RecipeProvisionError, match='Startup Repair'):
        _run(harness, _commands(1))


def test_qemu_exiting_immediately_aborts(harness):
    harness['process'].poll.return_value = 1
    harness['process'].returncode = 1
    harness['process'].stderr.read.return_value = b'could not open disk'
    with pytest.raises(RecipeProvisionError, match='exited immediately'):
        _run(harness, _commands(1))
    harness['flatten'].assert_not_called()


def test_overall_deadline_aborts_between_steps(harness):
    """A build that overruns its budget stops rather than running for ever."""
    with pytest.raises(RecipeProvisionError, match='overall deadline'):
        _run(harness, _commands(3), deadline_minutes=0)
    harness['flatten'].assert_not_called()


def test_abort_records_the_failure_in_the_host_log(harness):
    harness['agent'].results = {'do-thing-1': (1, 'bad', 'worse')}
    with pytest.raises(RecipeProvisionError):
        _run(harness, _commands(1))
    text = harness['build_log'].read_text()
    assert 'exit code:    1' in text
    assert 'bad' in text and 'worse' in text


def test_error_message_points_at_the_build_log(harness):
    harness['agent'].results = {'do-thing-1': (1, '', '')}
    with pytest.raises(RecipeProvisionError) as excinfo:
        _run(harness, _commands(1))
    assert str(harness['build_log']) in str(excinfo.value)
