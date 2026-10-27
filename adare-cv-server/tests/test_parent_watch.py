"""--exit-with-parent: the CV server must not outlive the process that started it."""

import os
import signal
import subprocess
import sys
import textwrap
import time

import pytest

# The parent starts a child that runs the watch, prints the child's pid, then waits to be killed.
_PARENT = textwrap.dedent(
    """
    import subprocess, sys, time
    child = subprocess.Popen(
        [sys.executable, '-c',
         'import time; from adare_cv_server.parent_watch import exit_when_parent_dies; '
         'exit_when_parent_dies(poll_seconds=0.1); time.sleep(60)'],
        start_new_session=True,  # detached like the real server
    )
    print(child.pid, flush=True)
    time.sleep(60)
    """
)


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


@pytest.mark.skipif(os.name == 'nt', reason='POSIX signals')
def test_server_exits_when_its_parent_is_killed():
    parent = subprocess.Popen([sys.executable, '-c', _PARENT], stdout=subprocess.PIPE, text=True)
    child = int(parent.stdout.readline())
    try:
        time.sleep(0.5)
        assert _alive(child)
        parent.send_signal(signal.SIGKILL)  # no cleanup runs, like a killed run
        parent.wait()
        deadline = time.monotonic() + 10
        while _alive(child) and time.monotonic() < deadline:
            time.sleep(0.1)
        assert not _alive(child)
    finally:
        if _alive(child):
            os.kill(child, signal.SIGKILL)


def test_server_keeps_running_while_its_parent_lives():
    exited = []
    from adare_cv_server.parent_watch import exit_when_parent_dies

    thread = exit_when_parent_dies(poll_seconds=0.05, on_exit=lambda: exited.append(True))
    time.sleep(0.3)
    assert thread.is_alive() and not exited
