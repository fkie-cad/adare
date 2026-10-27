"""A killed run must not leave its VM running: the reaper reconciles once its parent is gone."""

import os
import signal
import subprocess
import sys
import textwrap
import time
from unittest.mock import patch

import pytest

from adare.backend.vm import run_reaper

pytestmark = pytest.mark.unit


def _alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return True


def test_starts_one_reaper_per_process():
    with (
        patch.object(run_reaper, '_started_for_pid', None),
        patch.object(run_reaper.subprocess, 'Popen') as popen,
    ):
        run_reaper.start_run_reaper()
        run_reaper.start_run_reaper()
    assert popen.call_count == 1
    argv = popen.call_args.args[0]
    assert argv[1:3] == ['-m', 'adare.backend.vm.run_reaper'] and argv[3] == str(os.getpid())
    assert popen.call_args.kwargs['close_fds'] is True


@pytest.mark.skipif(os.name == 'nt', reason='POSIX signals')
def test_reaper_reconciles_and_exits_when_its_parent_is_killed(tmp_path):
    marker = tmp_path / 'reconciled'
    # Stand-in for reconcile_instances that leaves a marker, loaded via sitecustomize in the reaper.
    (tmp_path / 'sitecustomize.py').write_text(
        textwrap.dedent(
            f"""
            import adare.backend.vm.run_instances as ri
            async def _reconcile(dry_run=False):
                open({str(marker)!r}, 'w').close()
            ri.reconcile_instances = _reconcile
            """
        )
    )
    parent_src = textwrap.dedent(
        """
        import os, subprocess, sys, time
        from adare.backend.vm import run_reaper
        real_popen = subprocess.Popen
        def popen(*args, **kwargs):
            proc = real_popen(*args, **kwargs)
            print(proc.pid, flush=True)
            return proc
        run_reaper.subprocess.Popen = popen
        run_reaper.start_run_reaper()
        time.sleep(60)
        """
    )
    env = {**os.environ, 'PYTHONPATH': os.pathsep.join([str(tmp_path), os.environ.get('PYTHONPATH', '')])}
    parent = subprocess.Popen([sys.executable, '-c', parent_src], stdout=subprocess.PIPE, text=True, env=env)
    reaper = int(parent.stdout.readline())
    try:
        time.sleep(0.5)
        assert _alive(reaper) and not marker.exists()  # idles while the run lives
        parent.send_signal(signal.SIGKILL)
        parent.wait()
        deadline = time.monotonic() + 15
        while _alive(reaper) and time.monotonic() < deadline:
            time.sleep(0.1)
        assert marker.exists()
        assert not _alive(reaper)
    finally:
        if _alive(reaper):
            os.kill(reaper, signal.SIGKILL)
