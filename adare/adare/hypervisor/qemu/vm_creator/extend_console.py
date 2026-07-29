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
    console.print('  Type [cyan]:help[/cyan] for meta-commands, [cyan]:store[/cyan] to create the '
                  'environment,')
    console.print('  [cyan]:discard[/cyan] to shut down and [bold]create nothing[/bold].')
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
    console.print('    [cyan]:store[/cyan]                shut the guest down and [bold]create[/bold] the new environment')
    console.print('    [cyan]:discard[/cyan] / [cyan]:quit[/cyan]      shut down and exit WITHOUT creating an environment')
    console.print('    [cyan]:q[/cyan]                    quick exit -- choose store / discard / cancel')
    console.print()
    console.print(f'  Anything else runs in the guest via {shell}.')
    console.print('  [dim]Note: env vars do not persist across commands (each is a fresh process);[/dim]')
    console.print('  [dim]the working directory is tracked manually via :cd / cd.[/dim]')
    console.print()


def _confirm(question: str, default_yes: bool) -> bool:
    """Prompt for a yes/no answer; empty input takes the default.

    Guards EOF / Ctrl-C by returning False ("not confirmed"), mirroring
    ``cli/vm.py:_confirm_removal``.
    """
    suffix = '[Y/n]' if default_yes else '[y/N]'
    try:
        response = input(f'  {question} {suffix} ').strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    if not response:
        return default_yes
    return response in ('y', 'yes')


def _prompt_quit_choice() -> str:
    """Ask what a quick ``:q`` should do; return 'store' / 'discard' / 'cancel'.

    Cancel returns to the shell. EOF / Ctrl-C default to 'discard' (create
    nothing) since stdin can no longer be prompted.
    """
    try:
        response = input('  Quit: [s]tore, [d]iscard, or [c]ancel? [s/d/c] ').strip().lower()
    except (EOFError, KeyboardInterrupt):
        return 'discard'
    if response in ('s', 'store'):
        return 'store'
    if response in ('d', 'discard'):
        return 'discard'
    return 'cancel'


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
) -> tuple[bool, list[dict]]:
    """Drive the running guest from a terminal REPL; return the store decision.

    Waits for the guest agent to come up, then loops a prompt. Each non-meta line
    runs in the guest; successful commands (exit 0) are recorded while recording
    is on. ``:store`` (after confirmation) shuts the guest down and requests that
    the caller flatten + register the new environment; ``:discard`` / ``:quit``
    shut down and create nothing.

    Ambiguous exits default to DISCARD (create nothing): EOF / Ctrl-D, and any
    fallback path where no console is available. A guest shut down from inside the
    QEMU window prompts on a TTY, otherwise discards.

    Falls back to the legacy press-Enter wait when stdin is not a TTY or the guest
    agent never responds (e.g. a GUI-only base without a usable agent).

    Returns:
        Tuple of ``(store, recorded)``: ``store`` True means the caller should
        flatten the overlay and register the environment; ``recorded`` is the list
        of install dicts to fold in (empty when discarded).
    """
    recorded: list[dict] = []

    if not sys.stdin.isatty():
        console.print('  [dim]Non-interactive mode: no console. Waiting for VM to shut down.[/dim]\n')
        wait_for_input_or_exit(process, qmp_sock)
        return False, []

    print_step('Waiting for the guest agent to come up...')
    if not qga_wait_ready(qga_sock):
        console.print('  [yellow]Guest agent did not respond in time; falling back to '
                      'press-Enter shutdown.[/yellow]')
        console.print('  [dim](The base may lack qemu-guest-agent, or the guest is still '
                      'booting.)[/dim]')
        wait_for_input_or_exit(process, qmp_sock)
        return False, []

    _print_banner(windows)

    cwd = ''
    recording = True
    step = 0

    while True:
        if process.poll() is not None:
            # Guest was shut down from inside the QEMU window. Ask on a TTY
            # whether to keep the result; default to discard when we can't.
            console.print('  [dim]VM process exited (guest shut down).[/dim]')
            if sys.stdin.isatty() and _confirm(
                    'Create the new environment from this session?', default_yes=True):
                return True, recorded
            return False, []

        try:
            line = input(_prompt(cwd))
        except EOFError:
            console.print('\n  [dim]EOF -- discarding session and shutting down '
                          '(no environment created).[/dim]')
            _shutdown(qmp_sock, process)
            return False, []
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
        if line == ':store':
            if not _confirm('Shut down the VM and create the new environment?',
                            default_yes=True):
                continue
            if recorded:
                print_step(f'Recorded [bold]{len(recorded)}[/bold] command(s) as '
                           'post-setup installations.')
            print_step('Storing: sending ACPI shutdown...')
            _shutdown(qmp_sock, process)
            return True, recorded
        if line in (':discard', ':quit'):
            if not _confirm('Discard this session and shut down WITHOUT creating an '
                            'environment?', default_yes=False):
                continue
            console.print('  [yellow]Discarding session; shutting down. No environment '
                          'will be created.[/yellow]')
            _shutdown(qmp_sock, process)
            return False, []
        if line == ':q':
            choice = _prompt_quit_choice()
            if choice == 'cancel':
                continue
            _shutdown(qmp_sock, process)
            if choice == 'store':
                return True, recorded
            return False, []
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
