"""Stage 2 of a recipe build: run build-time provisioning against a booted disk.

Boots a throwaway overlay of the cached base disk with a QEMU guest-agent
channel, runs each expanded provision command as its own ``guest-exec``, shuts
the guest down cleanly, and flattens the overlay into the final standalone disk.

Why one guest-exec per step, host-driven
========================================

Rejected alternatives, and why:

* **``FirstLogonCommands`` / cloud-init.** No failure channel back to the host: a
  silently-incomplete disk is exactly what must be impossible here. It would also
  blow ``_run_qemu_install_phase``'s 90-minute timeout, and folding the steps into
  the answer file would make the answer-file hash provision-dependent — which
  destroys the base-disk cache that makes solr4 and solr8 share one Windows
  install.
* **One rendered monolithic script.** One exit code for three hours of work. When
  MSI number 11 of 16 fails you learn only "the script failed".

Per-step host-driven execution gives real exit codes, per-step timeouts, live
progress, and a truthful abort.

Note the shipped ``appdata/templates/windows/installations.ps1`` cannot be reused
verbatim: it dot-sources ``helperfunctions.ps1`` from the experiment *run*
directory, which does not exist on a bare built disk.

The failure contract
====================

**Invariant: the caller reaches disk registration only after every step succeeded
and the guest shut down cleanly.** A partially-provisioned disk must never become
a registered environment nor occupy a ``recipe_hash`` cache slot — its hash would
promise contents it does not have.

Concretely, this module raises rather than returning a disk on: a step exiting
outside its ``allow_exit_codes``, a non-zero ``verify``, a step timeout, the
overall deadline, the agent never becoming ready, and — importantly — a guest
that will not shut down cleanly. **Never flatten a dirty NTFS volume**; that is
the documented cause of the Startup-Repair flakiness in the Autopsy
case-study provisioning README.

Step-level resume is deliberately not implemented. A half-installed MSI is not a
clean resume point, and pretending otherwise produces disks whose contents do not
match their hash. The retry story is base-level: the base disk is cached, so
``--reprovision`` replays provisioning in minutes, and a ``for_each`` list can be
bisected to isolate a bad item.
"""

import logging
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from adare.console import console, print_section, print_step
from adare.hypervisor.exceptions import HypervisorException
from adare.hypervisor.qemu.firmware import create_nvram_for_vm
from adare.hypervisor.qemu.vm_creator.interactive import build_post_install_qemu_cmd
from adare.hypervisor.qemu.vm_creator.os_catalog import OsDefinition
from adare.hypervisor.qemu.vm_creator.overlay import create_work_overlay, flatten_overlay
from adare.hypervisor.qemu.vm_creator.qga_utils import (
    QgaError,
    qga_exec,
    qga_pull_file,
    qga_reboot,
    qga_wait_ready,
)
from adare.hypervisor.qemu.vm_creator.qmp_utils import send_acpi_shutdown
from adare.types.environment import ProvisionCommand

log = logging.getLogger(__name__)

__all__ = ['run_provision', 'RecipeProvisionError']

# Fixed names inside the throwaway work directory.
_WORK_NAME = 'provision-overlay'

# The guest agent must answer within this long after boot. Generous because the
# base disk's very first boot after an unattended install can run OOBE tasks;
# measured cold-boot-to-agent on the windows11arm64 recipe disk was ~3 s.
_QGA_READY_TIMEOUT = 15 * 60.0

# Overall budget for the whole provisioning stage.
_DEFAULT_DEADLINE_MINUTES = 12 * 60

# How long to wait for the guest to power off after the ACPI request. Deliberately
# generous: a Windows guest that just installed 16 MSIs has real shutdown work to
# do, and a too-tight bound here would turn the abort contract into false
# failures — an operator who is told "dirty shutdown" on a clean build stops
# trusting the message.
_SHUTDOWN_TIMEOUT = 20 * 60.0

# Set to keep the failed overlay on disk for post-mortem instead of deleting it.
KEEP_FAILED_ENV = 'ADARE_KEEP_FAILED_PROVISION'


class RecipeProvisionError(HypervisorException):
    """Build-time provisioning failed. The disk must not be registered."""


def _fmt_duration(seconds: float) -> str:
    """Render a wall-clock duration compactly ('7s', '4m12s', '1h03m')."""
    seconds = int(seconds)
    if seconds < 60:
        return f'{seconds}s'
    if seconds < 3600:
        return f'{seconds // 60}m{seconds % 60:02d}s'
    return f'{seconds // 3600}h{(seconds % 3600) // 60:02d}m'


class _BuildLog:
    """Append-only host-side provenance record for one provisioning run.

    Records, per command: name, interpreter, the full command text, exit code,
    wall time, stdout and stderr. This is the artifact worth attaching to a paper
    — it is the only complete account of what was done to the disk, since the
    guest itself keeps no such record.
    """

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open('a', encoding='utf-8')

    def write(self, text: str) -> None:
        self._handle.write(text)
        self._handle.flush()

    def header(self, disk: Path, count: int) -> None:
        # `platform.system/release/machine` are cheap attribute reads.
        # `platform.platform()` would be more descriptive but shells out to `uname
        # -p`, and a build log has no business spawning a subprocess.
        host = f'{platform.system()} {platform.release()} ({platform.machine()})'
        self.write(
            f'\n{"=" * 78}\n'
            f'provisioning run: {count} command(s)\n'
            f'disk:  {disk}\n'
            f'host:  {host}\n'
            f'{"=" * 78}\n'
        )

    def command(self, index: int, total: int, command: ProvisionCommand,
                kind: str, returncode: int, elapsed: float,
                stdout: str, stderr: str) -> None:
        self.write(
            f'\n--- [{index}/{total}] {command.name} ({kind}) ---\n'
            f'interpreter:  {command.shell}\n'
            f'cwd:          {command.cwd or "(guest default)"}\n'
            f'allow_exit:   {command.allow_exit_codes}\n'
            f'command:\n{command.command if kind == "command" else command.verify}\n'
            f'exit code:    {returncode}\n'
            f'wall time:    {_fmt_duration(elapsed)}\n'
            f'--- stdout ---\n{stdout}\n'
            f'--- stderr ---\n{stderr}\n'
        )

    def note(self, text: str) -> None:
        self.write(f'\n### {text}\n')

    def close(self) -> None:
        self._handle.close()


def _socket_path(kind: str) -> Path:
    """A short Unix-socket path for a provisioning channel.

    Always in ADARE's managed run dir rather than beside the disk: the macOS
    ``sun_path`` limit is 104 bytes and a work overlay under ``$TMPDIR`` already
    eats ~49 of them.
    """
    run_dir = Path.home() / '.adare' / 'qemu' / 'run'
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir / f'.provision-{os.getpid()}-{kind}.sock'


def _boot_with_qga(overlay: Path, nvram: Path | None, os_def: OsDefinition,
                   ram_mb: int, cpus: int, qmp_sock: Path, qga_sock: Path,
                   allow_emulation: bool) -> subprocess.Popen:
    """Boot *overlay* with a guest-agent channel and return the running process.

    Raises:
        RecipeProvisionError: If QEMU exits immediately.
    """
    cmd = build_post_install_qemu_cmd(
        overlay, nvram, os_def, ram_mb, cpus,
        qmp_sock_path=qmp_sock,
        qga_sock_path=qga_sock,
        allow_emulation=allow_emulation,
        # An unwatched GUI window in CI or a background build is pure overhead;
        # on a terminal, showing it lets the operator see a stuck installer.
        headless=not sys.stdout.isatty(),
    )
    log.info('Booting provisioning session: %s', ' '.join(cmd))
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    time.sleep(3)
    if process.poll() is not None:
        stderr = process.stderr.read().decode() if process.stderr else ''
        raise RecipeProvisionError(
            f'QEMU exited immediately while starting provisioning '
            f'(code {process.returncode}): {stderr.strip()}'
        )
    return process


def _pull_log_files(qga_sock: Path, command: ProvisionCommand,
                    log_dir: Path, build_log: _BuildLog) -> None:
    """Best-effort copy of a failed step's ``log_files`` to the host.

    Best-effort on purpose: the step already failed, and losing the installer log
    must not replace the real error with a transport error. Each outcome is
    recorded in the build log either way.
    """
    if not command.log_files:
        return
    log_dir.mkdir(parents=True, exist_ok=True)
    for remote in command.log_files:
        local = log_dir / f'{command.name}-{Path(remote.replace(chr(92), "/")).name}'
        try:
            size = qga_pull_file(qga_sock, remote, local)
            build_log.note(f'pulled {remote} -> {local} ({size} bytes)')
            print_step(f'  Pulled guest log: [dim]{local}[/dim]')
        except (QgaError, OSError) as e:
            build_log.note(f'could not pull {remote}: {e}')
            log.warning('Could not pull guest log %s: %s', remote, e)


def _run_command(qga_sock: Path, command: ProvisionCommand, index: int, total: int,
                 build_log: _BuildLog, log_dir: Path) -> None:
    """Run one provision command (and its ``verify``), or raise.

    Success is the exit code being in ``allow_exit_codes`` — never "stderr was
    empty". PowerShell writes CLIXML progress records to stderr on perfectly
    successful commands.

    Raises:
        RecipeProvisionError: On a disallowed exit code, a failing ``verify``, or
            a step timeout.
    """
    label = command.description or command.name
    timeout = command.timeout_minutes * 60.0
    status_text = f'[{index}/{total}] {command.name} — {label}'
    print_step(status_text)

    def _tick(elapsed: float) -> None:
        console.print(
            f'    [dim]still running: {command.name} '
            f'({_fmt_duration(elapsed)} of up to {command.timeout_minutes}m)[/dim]'
        )

    started = time.monotonic()
    try:
        returncode, stdout, stderr = qga_exec(
            qga_sock, command.command, cwd=command.cwd or None,
            shell=command.shell, timeout=timeout,
            progress_callback=_tick,
        )
    except QgaError as e:
        build_log.note(f'[{index}/{total}] {command.name}: guest-exec failed: {e}')
        raise RecipeProvisionError(
            f"provision step {index}/{total} '{command.name}' did not complete: {e}"
        ) from e

    elapsed = time.monotonic() - started
    build_log.command(index, total, command, 'command', returncode, elapsed, stdout, stderr)

    if returncode not in command.allow_exit_codes:
        _pull_log_files(qga_sock, command, log_dir, build_log)
        raise RecipeProvisionError(
            f"provision step {index}/{total} '{command.name}' failed with exit code "
            f"{returncode} (allowed: {command.allow_exit_codes}) after "
            f"{_fmt_duration(elapsed)}.\n"
            f"  command: {command.command}\n"
            f"  stdout:  {stdout.strip()[-2000:] or '(empty)'}\n"
            f"  stderr:  {stderr.strip()[-2000:] or '(empty)'}\n"
            f"  build log: {build_log.path}"
        )

    if command.verify:
        verify_started = time.monotonic()
        try:
            v_rc, v_out, v_err = qga_exec(
                qga_sock, command.verify, cwd=command.cwd or None,
                shell=command.shell, timeout=timeout,
            )
        except QgaError as e:
            raise RecipeProvisionError(
                f"provision step {index}/{total} '{command.name}': verify did not "
                f"complete: {e}"
            ) from e
        v_elapsed = time.monotonic() - verify_started
        build_log.command(index, total, command, 'verify', v_rc, v_elapsed, v_out, v_err)
        if v_rc != 0:
            _pull_log_files(qga_sock, command, log_dir, build_log)
            raise RecipeProvisionError(
                f"provision step {index}/{total} '{command.name}' reported success "
                f"(exit {returncode}) but its verify failed with exit {v_rc}: the "
                f"step did not actually do what it claims.\n"
                f"  verify:  {command.verify}\n"
                f"  stdout:  {v_out.strip()[-2000:] or '(empty)'}\n"
                f"  stderr:  {v_err.strip()[-2000:] or '(empty)'}\n"
                f"  build log: {build_log.path}"
            )

    if command.reboot:
        print_step(f'    Rebooting guest after {command.name}...')
        try:
            qga_reboot(qga_sock)
        except QgaError as e:
            raise RecipeProvisionError(
                f"provision step {index}/{total} '{command.name}': guest did not come "
                f"back after the requested reboot: {e}"
            ) from e
        build_log.note(f'[{index}/{total}] {command.name}: rebooted, agent back')


def _clean_shutdown(process: subprocess.Popen, qmp_sock: Path,
                    build_log: _BuildLog) -> None:
    """ACPI-shut the guest down and wait for QEMU to exit, or raise.

    A guest that will not shut down cleanly is a HARD failure. Flattening a dirty
    NTFS volume produces a disk that boots into Startup Repair on the consumer's
    machine — a defect that would be attributed to the recipe rather than to the
    build, and which the recipe hash would nonetheless vouch for.
    """
    print_step('Shutting the guest down cleanly (ACPI)...')
    started = time.monotonic()
    if not send_acpi_shutdown(qmp_sock):
        process.terminate()
        process.wait(timeout=60)
        build_log.note('ACPI shutdown request failed')
        raise RecipeProvisionError(
            'the guest did not accept the ACPI shutdown request, so its filesystem '
            'cannot be assumed consistent. Refusing to flatten a possibly dirty '
            'volume into a cached disk.'
        )
    try:
        process.wait(timeout=_SHUTDOWN_TIMEOUT)
    except subprocess.TimeoutExpired as e:
        process.terminate()
        try:
            process.wait(timeout=60)
        except subprocess.TimeoutExpired:
            process.kill()
        build_log.note(f'dirty shutdown: guest still running after {_SHUTDOWN_TIMEOUT:.0f}s')
        raise RecipeProvisionError(
            f'the guest did not power off within {_SHUTDOWN_TIMEOUT / 60:.0f} minutes '
            f'of the ACPI shutdown request. Refusing to flatten a dirty filesystem '
            f'into a cached disk — the result would boot into Startup Repair.'
        ) from e

    elapsed = time.monotonic() - started
    build_log.note(f'clean shutdown in {_fmt_duration(elapsed)}')
    print_step(f'  Guest powered off cleanly in {_fmt_duration(elapsed)}.')


def run_provision(
    base_disk: Path,
    dest_disk: Path,
    commands: list[ProvisionCommand],
    os_def: OsDefinition,
    ram_mb: int,
    cpus: int,
    build_log_path: Path,
    allow_emulation: bool = False,
    compress: bool = True,
    deadline_minutes: int = _DEFAULT_DEADLINE_MINUTES,
) -> Path:
    """Provision *base_disk* into a standalone *dest_disk*, or raise.

    *base_disk* is opened read-only through the overlay's backing chain and is
    never mutated — so a failed provisioning run cannot damage the cached base
    that took hours to install, and a retry re-overlays in seconds.

    Args:
        base_disk: Cached base disk (Stage 1 output). Read only.
        dest_disk: Final standalone qcow2. Created ONLY on full success.
        commands: Already-expanded provision commands, in execution order.
        build_log_path: Host log file recording every command and its output.
        deadline_minutes: Budget for the whole stage, checked between steps.

    Returns:
        *dest_disk*.

    Raises:
        RecipeProvisionError: On any step failure, timeout, deadline overrun,
            unreachable agent, or unclean shutdown. *dest_disk* is not created.
    """
    if not commands:
        raise RecipeProvisionError('run_provision called with no provision commands')

    total = len(commands)
    work_dir = Path(tempfile.mkdtemp(prefix='adare-provision-'))
    overlay = work_dir / f'{_WORK_NAME}.qcow2'
    qmp_sock = _socket_path('qmp')
    qga_sock = _socket_path('qga')
    guest_log_dir = build_log_path.parent / f'{build_log_path.stem}-guest-logs'
    build_log = _BuildLog(build_log_path)
    process: subprocess.Popen | None = None
    keep_failed = os.environ.get(KEEP_FAILED_ENV) == '1'
    succeeded = False

    print_section('Build-time provisioning (Stage 2/2)')
    console.print(f'  {total} command(s) to run in the guest.')
    console.print(f'  Host log: [dim]{build_log_path}[/dim]')

    try:
        build_log.header(base_disk, total)
        create_work_overlay(base_disk, overlay)

        nvram: Path | None = None
        if os_def.requires_uefi or os_def.architecture == 'aarch64':
            nvram = Path(create_nvram_for_vm(_WORK_NAME, work_dir, os_def.architecture))

        process = _boot_with_qga(
            overlay, nvram, os_def, ram_mb, cpus, qmp_sock, qga_sock, allow_emulation,
        )

        print_step('Waiting for the guest agent...')
        agent_started = time.monotonic()
        if not qga_wait_ready(qga_sock, timeout=_QGA_READY_TIMEOUT):
            build_log.note('guest agent never became ready')
            raise RecipeProvisionError(
                f'the QEMU guest agent did not respond within '
                f'{_QGA_READY_TIMEOUT / 60:.0f} minutes. Build-time provisioning '
                f'needs it, so the disk cannot be provisioned.\n'
                f'  The agent ships with setup_level >= 1 (base) — a recipe with '
                f'setup_level 0 has no agent to talk to.'
            )
        print_step(
            f'  Guest agent ready in {_fmt_duration(time.monotonic() - agent_started)}.'
        )

        deadline = time.monotonic() + deadline_minutes * 60
        for index, command in enumerate(commands, start=1):
            if time.monotonic() > deadline:
                build_log.note(f'overall deadline of {deadline_minutes} min exceeded')
                raise RecipeProvisionError(
                    f'provisioning exceeded its overall deadline of '
                    f'{deadline_minutes} minutes at step {index}/{total} '
                    f'({command.name}).'
                )
            _run_command(qga_sock, command, index, total, build_log, guest_log_dir)

        _clean_shutdown(process, qmp_sock, build_log)
        process = None

        print_step('Flattening the provisioned overlay into a standalone disk...')
        flatten_overlay(overlay, dest_disk, compress=compress)
        build_log.note(f'flattened to {dest_disk}')
        succeeded = True
        return dest_disk
    finally:
        if process is not None and process.poll() is None:
            # Only reached on a failure path — a successful run already waited for
            # a clean power-off. Kill rather than shut down: the overlay is about
            # to be discarded, so its consistency no longer matters.
            process.terminate()
            try:
                process.wait(timeout=60)
            except subprocess.TimeoutExpired:
                process.kill()
        for sock in (qmp_sock, qga_sock):
            if sock.exists():
                sock.unlink()
        build_log.close()
        if succeeded or not keep_failed:
            shutil.rmtree(work_dir, ignore_errors=True)
        else:
            console.print(
                f'  [yellow]{KEEP_FAILED_ENV}=1: keeping the failed overlay for '
                f'post-mortem:[/yellow] {overlay}'
            )
