"""The serial console of an unattended Linux install: logged, and writable.

QEMU logs everything the installer prints to the install log, as a plain
``-serial file:`` did, but the console is a socket chardev, so ADARE can also
type into it. A crashed subiquity (Ubuntu's installer) only says "An error
occurred. Press enter to start a shell" on the console; the traceback that names
the cause stays inside the installer (/var/crash, the installer debug log) and
dies with the VM. :meth:`InstallerConsole.dump_subiquity_crash` opens that shell
and prints both into the console, and so into the install log.
"""

import logging
import re
import shutil
import socket
import tempfile
import time
from pathlib import Path

log = logging.getLogger(__name__)

SUBIQUITY_RESCUE_PROMPT = 'An error occurred. Press enter to start a shell'

# What a crashed subiquity left behind: the Traceback field of its crash report,
# and the end of the server's debug log (the same traceback, in context). Markers
# are printf'd from split strings so the console's echo of the command line never
# contains them.
_MARKER = "printf '=== ADARE: %s ===\\n' '{}'"
_CRASH_SECTION = 'subiquity crash report'
_SUBIQUITY_CRASH_COMMANDS = (
    _MARKER.format(_CRASH_SECTION),
    "awk '/^Traceback:/{on=1; next} on && /^[^ ]/{exit} on' /var/crash/*.crash",
    _MARKER.format('subiquity-server-debug.log tail'),
    'tail -n 60 /var/log/installer/subiquity-server-debug.log',
    _MARKER.format('end'),
)
_END = b'=== ADARE: end ==='
_SHELL_PROMPT = b'# '
_SHELL_START_SECONDS = 15.0
_DUMP_SECONDS = 60.0
# Terminal control sequences in the console output, e.g. bash's bracketed-paste toggles
_ANSI_ESCAPE = re.compile(r'\x1b\[[0-9;?]*[a-zA-Z]')


class InstallerConsole:
    """A QEMU serial chardev that logs to ``install_log`` and accepts input over a Unix socket."""

    def __init__(self, install_log: Path):
        self.install_log = install_log
        # A short private directory: Unix socket paths are limited to 108 bytes
        self._dir = Path(tempfile.mkdtemp(prefix='adare-console-'))
        self.socket_path = self._dir / 'serial.sock'

    def qemu_args(self) -> list[str]:
        """QEMU arguments that attach the guest's first serial port to this console."""
        # wait=off: QEMU must not block at startup until a client connects. logfile=
        # records the guest's output whether or not anyone is connected.
        chardev = f'socket,id=installer-console,path={self.socket_path},server=on,wait=off,logfile={self.install_log}'
        return ['-chardev', chardev, '-serial', 'chardev:installer-console']

    def dump_subiquity_crash(self) -> None:
        """Open subiquity's rescue shell and print its crash traceback into the install log.

        Best effort: a console that cannot be reached leaves the log as it was.
        """
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as console:
                console.connect(str(self.socket_path))
                console.sendall(b'\r')  # "Press enter to start a shell"
                _read_until(console, _SHELL_PROMPT, _SHELL_START_SECONDS)
                console.sendall(b''.join(command.encode() + b'\r' for command in _SUBIQUITY_CRASH_COMMANDS))
                if not _read_until(console, _END, _DUMP_SECONDS):
                    log.warning('The installer crash report did not finish printing; the install log may lack it')
        except OSError as e:
            log.warning(f'Could not fetch the installer crash report over the serial console: {e}')

    def close(self) -> None:
        shutil.rmtree(self._dir, ignore_errors=True)


def _read_until(console: socket.socket, pattern: bytes, seconds: float) -> bool:
    """Read the console until ``pattern`` shows up; whether it did within ``seconds``.

    The reading is load-bearing: the guest writes the console a character at a
    time, and once the unread socket buffer fills, QEMU stalls the serial port --
    and with it the install log, which gets the output only as it is sent.
    """
    console.settimeout(0.5)
    seen = b''
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            chunk = console.recv(65536)
        except TimeoutError:
            continue
        if not chunk:
            return False
        seen = (seen + chunk)[-4096:]
        if pattern in seen:
            return True
    return False


def subiquity_traceback(install_log_text: str) -> str:
    """The end of the crash traceback ADARE fetched into the install log: last frame and exception ('' if none)."""
    install_log_text = _ANSI_ESCAPE.sub('', install_log_text)
    start = install_log_text.rfind(f'=== ADARE: {_CRASH_SECTION} ===')
    if start == -1:
        return ''
    traceback: list[str] = []
    for line in install_log_text[start:].splitlines()[1:]:
        if line.startswith('=== ADARE:'):
            break
        # Skip the shell prompt with the echoed command, and the header line
        if line.strip() and not line.startswith('root@') and line.strip() != 'Traceback (most recent call last):':
            traceback.append(line.strip())
    return '\n'.join(traceback[-3:])
