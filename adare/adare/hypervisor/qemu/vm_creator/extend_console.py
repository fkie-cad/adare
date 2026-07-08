"""Interactive command console for ``adare env extend --interactive``.

Runs in the terminal alongside the QEMU GUI window and drives the guest via the
QEMU guest agent (QGA). Each shell command is executed inside the guest, its
stdout/stderr streamed back, and -- while recording is on -- captured as a
post-setup installation so the extend is reproducible declaratively.

Known limitation (surfaced in ``:help``): each command is a fresh guest process,
so exported environment variables do NOT persist between commands. The working
directory IS tracked manually (``:cd`` / ``cd``) and folded into each command.
This matches the record-as-installs model, where every install is a standalone
step.
"""

import logging
import shlex
import subprocess
import sys
from pathlib import Path

from adare.console import console, print_section, print_step
from adare.hypervisor.qemu.vm_creator.qga_utils import (
    QgaError,
    qga_exec,
    qga_pull_file,
    qga_push_file,
    qga_wait_ready,
)
from adare.hypervisor.qemu.vm_creator.qmp_utils import (
    send_acpi_shutdown,
    wait_for_input_or_exit,
)

log = logging.getLogger(__name__)


def _print_banner(windows: bool) -> None:
    print_section('Interactive Extend Console')
    console.print('  Commands you type run [bold]inside the guest[/bold]; output is shown here.')
    console.print('  Successful commands are [bold]recorded[/bold] as the new environment\'s installs.')
    console.print('  Type [cyan]:help[/cyan] for meta-commands, [cyan]:store[/cyan] to save, '
                  '[cyan]:discard[/cyan] to abandon recording.')
    if windows:
        console.print('  [dim]Guest shell: PowerShell.[/dim]')
    console.print()


def _print_help(windows: bool) -> None:
    shell = 'PowerShell' if windows else '/bin/bash'
    console.print()
    console.print('  [bold]Meta-commands[/bold]')
    console.print('    [cyan]:help[/cyan]                 show this help')
    console.print('    [cyan]:cd <dir>[/cyan] / [cyan]cd <dir>[/cyan]  change the tracked working directory')
    console.print('    [cyan]:push <local> <remote>[/cyan]  copy a host file into the guest')
    console.print('    [cyan]:pull <remote> <local>[/cyan]  copy a guest file out to the host')
    console.print('    [cyan]:record on|off[/cyan]        toggle recording (default: on)')
    console.print('    [cyan]:store[/cyan]                shut the guest down, flatten, and keep the recorded installs')
    console.print('    [cyan]:discard[/cyan] / [cyan]:quit[/cyan]      shut down and flatten WITHOUT recording')
    console.print()
    console.print(f'  Anything else runs in the guest via {shell}.')
    console.print('  [dim]Note: env vars do not persist across commands (each is a fresh process);[/dim]')
    console.print('  [dim]the working directory is tracked manually via :cd / cd.[/dim]')
    console.print()


def _prompt(cwd: str) -> str:
    location = cwd if cwd else '~'
    return f'guest:{location}$ '


def _write_output(text: str) -> None:
    """Write raw guest output verbatim (no Rich markup interpretation)."""
    if not text:
        return
    sys.stdout.write(text)
    if not text.endswith('\n'):
        sys.stdout.write('\n')
    sys.stdout.flush()


def _shutdown(qmp_sock: Path, process: subprocess.Popen) -> None:
    """ACPI-shutdown the guest and wait for QEMU to exit (terminate on failure)."""
    if process.poll() is not None:
        return
    if send_acpi_shutdown(qmp_sock):
        try:
            process.wait(timeout=180)
            console.print('  [green]VM shut down successfully.[/green]')
            return
        except subprocess.TimeoutExpired:
            console.print('  [yellow]VM did not shut down within 180s, terminating...[/yellow]')
    else:
        console.print('  [yellow]ACPI shutdown failed, terminating QEMU...[/yellow]')
    process.terminate()
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        process.kill()


def _resolve_cd(qga_sock: Path, cwd: str, target: str, windows: bool) -> str:
    """Resolve a ``cd`` in the guest and return the new tracked cwd.

    The guest itself resolves the path (via ``cd ... && pwd``), so ``..``, ``~``,
    ``$HOME`` and symlinks behave correctly. On failure the old cwd is kept.
    """
    if windows:
        base = f'Set-Location "{cwd}"; ' if cwd else ''
        dest = target if target else '$env:USERPROFILE'
        probe = f'{base}Set-Location {dest}; (Get-Location).Path'
    else:
        base = f'cd "{cwd}" && ' if cwd else ''
        dest = target if target else '$HOME'
        probe = f'{base}cd {dest} && pwd'
    try:
        rc, out, err = qga_exec(qga_sock, probe, cwd=None, windows=windows)
    except QgaError as e:
        console.print(f'  [red]cd failed:[/red] {e}')
        return cwd
    if rc != 0:
        _write_output(err or out)
        console.print(f'  [red]cd failed (exit {rc}); working directory unchanged.[/red]')
        return cwd
    new_cwd = out.strip().splitlines()[-1] if out.strip() else cwd
    console.print(f'  [dim]cwd -> {new_cwd}[/dim]')
    return new_cwd


def _handle_transfer(qga_sock: Path, line: str) -> None:
    """Handle a ``:push`` / ``:pull`` meta-command line."""
    try:
        parts = shlex.split(line)
    except ValueError as e:
        console.print(f'  [red]could not parse arguments:[/red] {e}')
        return
    verb = parts[0]
    if len(parts) != 3:
        usage = ':push <local> <remote>' if verb == ':push' else ':pull <remote> <local>'
        console.print(f'  [dim]usage: {usage}[/dim]')
        return
    try:
        if verb == ':push':
            n = qga_push_file(qga_sock, parts[1], parts[2])
            console.print(f'  [green]pushed {n} bytes -> guest:{parts[2]}[/green]')
        else:
            n = qga_pull_file(qga_sock, parts[1], parts[2])
            console.print(f'  [green]pulled {n} bytes -> {parts[2]}[/green]')
    except QgaError as e:
        console.print(f'  [red]transfer failed:[/red] {e}')


def run_extend_console(
    qga_sock: Path,
    qmp_sock: Path,
    process: subprocess.Popen,
    windows: bool = False,
) -> list[dict]:
    """Drive the running guest from a terminal REPL; return recorded installs.

    Waits for the guest agent to come up, then loops a prompt. Each non-meta line
    runs in the guest; successful commands (exit 0) are recorded while recording
    is on. ``:store`` finalizes (ACPI shutdown -> caller flattens); ``:discard`` /
    ``:quit`` shut down without keeping the recording.

    Falls back to the legacy press-Enter wait when stdin is not a TTY or the guest
    agent never responds (e.g. a GUI-only base without a usable agent).

    Returns:
        The recorded installs as a list of install dicts (empty if none / discarded).
    """
    recorded: list[dict] = []

    if not sys.stdin.isatty():
        console.print('  [dim]Non-interactive mode: no console. Waiting for VM to shut down.[/dim]\n')
        wait_for_input_or_exit(process, qmp_sock)
        return recorded

    print_step('Waiting for the guest agent to come up...')
    if not qga_wait_ready(qga_sock):
        console.print('  [yellow]Guest agent did not respond in time; falling back to '
                      'press-Enter shutdown.[/yellow]')
        console.print('  [dim](The base may lack qemu-guest-agent, or the guest is still '
                      'booting.)[/dim]')
        wait_for_input_or_exit(process, qmp_sock)
        return recorded

    _print_banner(windows)

    cwd = ''
    recording = True
    step = 0

    while True:
        if process.poll() is not None:
            console.print('  [dim]VM process exited.[/dim]')
            break

        try:
            line = input(_prompt(cwd))
        except EOFError:
            console.print('\n  [dim]EOF -- storing recorded commands and shutting down.[/dim]')
            _shutdown(qmp_sock, process)
            break
        except KeyboardInterrupt:
            console.print('\n  [yellow]Terminating QEMU...[/yellow]')
            process.terminate()
            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                process.kill()
            raise

        line = line.strip()
        if not line:
            continue

        # --- meta-commands ---------------------------------------------------
        if line == ':help':
            _print_help(windows)
            continue
        if line in (':store',):
            print_step('Storing: sending ACPI shutdown...')
            _shutdown(qmp_sock, process)
            break
        if line in (':discard', ':quit'):
            console.print('  [yellow]Discarding recorded commands; shutting down to flatten '
                          'current disk state.[/yellow]')
            _shutdown(qmp_sock, process)
            recorded = []
            break
        if line == ':record' or line.startswith(':record '):
            arg = line[len(':record'):].strip().lower()
            if arg == 'on':
                recording = True
            elif arg == 'off':
                recording = False
            elif arg:
                console.print('  [dim]usage: :record on|off[/dim]')
                continue
            console.print(f'  recording is [bold]{"on" if recording else "off"}[/bold]')
            continue
        if line == ':cd' or line.startswith(':cd ') or line == 'cd' or line.startswith('cd '):
            target = (line[3:] if line.startswith(':cd') else line[2:]).strip()
            cwd = _resolve_cd(qga_sock, cwd, target, windows)
            continue
        if line.startswith(':push') or line.startswith(':pull'):
            _handle_transfer(qga_sock, line)
            continue
        if line.startswith(':'):
            console.print(f'  [red]unknown meta-command:[/red] {line}  [dim](try :help)[/dim]')
            continue

        # --- guest command ---------------------------------------------------
        try:
            rc, out, err = qga_exec(qga_sock, line, cwd=cwd or None, windows=windows)
        except QgaError as e:
            console.print(f'  [red]guest-exec failed:[/red] {e}')
            continue

        _write_output(out)
        _write_output(err)
        color = 'green' if rc == 0 else 'red'
        console.print(f'  [{color}]exit {rc}[/{color}]')

        if recording and rc == 0:
            step += 1
            recorded.append({
                'name': f'step-{step}',
                'command': line,
                'description': '',
                'cwd': cwd,
                'shell': True,
            })

    if recorded:
        print_step(f'Recorded [bold]{len(recorded)}[/bold] command(s) as post-setup installations.')
    return recorded
