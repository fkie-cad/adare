"""A failed unattended install is reported at once, with the installer's own traceback.

subiquity drops to a rescue shell on failure and waits there forever, so QEMU
never exits: the install used to sit out the whole 150-minute timeout.
"""

import socket
import subprocess
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from adare.hypervisor.qemu.vm_creator import installer_console, linux_creator
from adare.hypervisor.qemu.vm_creator.installer_console import InstallerConsole, subiquity_traceback
from adare.hypervisor.qemu.vm_creator.progress import wait_for_qemu_exit

pytestmark = pytest.mark.unit

# What the serial console shows after ADARE ran its crash commands in the rescue shell
CRASH_DUMP = """An error occurred. Press enter to start a shell
\x1b[?2004hroot@ubuntu-server:/# printf '=== ADARE: %s ===\\n' 'subiquity crash report'
=== ADARE: subiquity crash report ===
\x1b[?2004l\x1b[?2004hroot@ubuntu-server:/# awk '/^Traceback:/{on=1; next} on && /^[^ ]/{exit} on' /var/crash/*.crash
 Traceback (most recent call last):
   File "/snap/subiquity/7225/lib/python3.12/site-packages/subiquity/server/server.py", line 1055, in start
     self.load_autoinstall_config(only_early=False)
   File "/snap/subiquity/7225/lib/python3.12/site-packages/subiquity/models/source.py", line 147, in get_matching_source
     raise KeyError
 KeyError
root@ubuntu-server:/# printf '=== ADARE: %s ===\\n' 'subiquity-server-debug.log tail'
=== ADARE: subiquity-server-debug.log tail ===
"""


@pytest.fixture
def console(tmp_path):
    serial_console = InstallerConsole(tmp_path / 'vm_install.log')
    yield serial_console
    serial_console.close()


def test_console_logs_to_the_install_log_and_takes_input(console):
    (chardev,) = [arg for arg in console.qemu_args() if arg.startswith('socket,')]

    assert f'logfile={console.install_log}' in chardev
    assert f'path={console.socket_path}' in chardev
    assert 'server=on,wait=off' in chardev
    # Unix socket paths are limited to 108 bytes
    assert len(str(console.socket_path)) < 108


def test_crash_dump_types_into_the_rescue_shell_and_reads_until_done(console, monkeypatch):
    monkeypatch.setattr(installer_console, '_SHELL_START_SECONDS', 2)
    monkeypatch.setattr(installer_console, '_DUMP_SECONDS', 2)
    received = bytearray()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(str(console.socket_path))
        server.listen(1)

        def shell():
            connection, _ = server.accept()
            with connection:
                received.extend(connection.recv(1))  # the Enter
                connection.sendall(b'root@ubuntu-server:/# ')
                while b"'end'" not in received:
                    received.extend(connection.recv(4096))
                connection.sendall(b'=== ADARE: end ===\r\n')
                connection.recv(1)  # until the console hangs up

        reader = threading.Thread(target=shell)
        reader.start()
        started = time.monotonic()
        console.dump_subiquity_crash()
        reader.join(timeout=5)

    typed = received.decode()
    assert typed.startswith('\r')  # "Press enter to start a shell"
    assert '/var/crash/*.crash' in typed
    assert 'subiquity-server-debug.log' in typed
    assert time.monotonic() - started < 2  # returned on the end marker, not a timeout


def test_unreachable_console_leaves_the_log_alone(console):
    console.dump_subiquity_crash()  # nothing listens on the socket: no exception


def test_traceback_is_read_from_the_dump():
    assert subiquity_traceback(CRASH_DUMP) == (
        'File "/snap/subiquity/7225/lib/python3.12/site-packages/subiquity/models/source.py", '
        'line 147, in get_matching_source\nraise KeyError\nKeyError'
    )


def test_no_dump_no_traceback():
    assert subiquity_traceback('An error occurred. Press enter to start a shell\n') == ''


def test_crashed_subiquity_fails_with_its_traceback(console, monkeypatch):
    console.install_log.write_text('booting...\nAn error occurred. Press enter to start a shell\n')
    monkeypatch.setattr(console, 'dump_subiquity_crash', lambda: console.install_log.write_text(CRASH_DUMP))

    with pytest.raises(linux_creator.LinuxVMCreationError) as error:
        linux_creator._assert_install_succeeded(console)

    assert 'raise KeyError\nKeyError' in str(error.value)
    assert str(console.install_log) in str(error.value)


def test_other_installer_failures_fail_without_a_shell(console, monkeypatch):
    console.install_log.write_text("curtin: ... returned non-zero exit status 100\n")
    dump = MagicMock()
    monkeypatch.setattr(console, 'dump_subiquity_crash', dump)

    with pytest.raises(linux_creator.LinuxVMCreationError, match='exit status 100'):
        linux_creator._assert_install_succeeded(console)
    dump.assert_not_called()


def test_running_install_passes(console):
    console.install_log.write_text('subiquity/Install/install: running curtin\n')

    linux_creator._assert_install_succeeded(console)


def test_wait_gives_up_as_soon_as_the_check_fails():
    process = MagicMock()
    process.wait.side_effect = subprocess.TimeoutExpired('qemu', 10)

    class InstallerFailed(Exception):
        pass

    def check():
        raise InstallerFailed

    with pytest.raises(InstallerFailed):
        wait_for_qemu_exit(process, timeout_minutes=150, check=check)
    assert process.wait.call_count == 1


def test_missing_install_log_is_not_a_failure(tmp_path):
    assert linux_creator._install_failure(Path(tmp_path / 'absent.log')) is None
