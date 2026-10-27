"""Tear down a process's QEMU runs when that process dies without doing it itself.

A run's VM is a libvirt domain, owned by libvirt rather than by the ``adare``
process, so a crashed or killed run (``kill -9``, a closed terminal, an
interrupted agent session) left the VM running with its RAM until the next run
or ``adare vm prune`` called :func:`~adare.backend.vm.run_instances.reconcile_instances`.

The first QEMU run of a process starts one reaper (``python -m
adare.backend.vm.run_reaper``) in its own session, so Ctrl-C does not reach it.
It idles until its parent is gone and then runs ``reconcile_instances()``,
which removes only runs whose owning process is dead and never a dev session's,
so it is safe next to concurrent runs. After a clean exit there is nothing left
and the pass is a no-op.

The wait is pid-reuse proof on POSIX (an orphan's ``getppid()`` changes); on
Windows the parent pid is polled.
"""

import logging
import os
import subprocess
import sys
import time

log = logging.getLogger(__name__)

POLL_SECONDS = 2.0

_started_for_pid: int | None = None


def start_run_reaper() -> None:
    """Start this process's reaper once (later calls do nothing)."""
    global _started_for_pid
    if _started_for_pid == os.getpid():
        return
    kwargs: dict = {'start_new_session': True} if os.name != 'nt' else {}
    try:
        subprocess.Popen(
            [sys.executable, '-m', 'adare.backend.vm.run_reaper', str(os.getpid())],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            close_fds=True,  # never inherit the run's VM-slot or port locks
            **kwargs,
        )
    except OSError as e:
        log.warning(f"Could not start the run reaper (crashed runs are reaped by the next run): {e}")
        return
    _started_for_pid = os.getpid()


def wait_for_parent_exit(parent: int, poll_seconds: float = POLL_SECONDS) -> None:
    if os.name == 'nt':
        from adare.backend.vm.run_instances import pid_alive

        while pid_alive(parent):
            time.sleep(poll_seconds)
        return
    while os.getppid() == parent:
        time.sleep(poll_seconds)


def main(argv: list[str]) -> None:
    import asyncio

    wait_for_parent_exit(int(argv[0]))

    from adare.backend.vm.run_instances import reconcile_instances

    asyncio.run(reconcile_instances())


if __name__ == '__main__':
    main(sys.argv[1:])
