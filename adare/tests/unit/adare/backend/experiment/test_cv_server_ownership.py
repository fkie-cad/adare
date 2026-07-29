"""Tests for the cv-server ownership gate in ``MCPServerManager``.

``stop(force_external=True)`` — which dev-session teardown always passes
(``devmode/session/lifecycle.py``) — reaches ``_kill_process_on_port``, which sends
SIGTERM to whatever ``_is_our_cv_server`` vouches for. That gate is the ONLY thing
standing between an attached dev session and a concurrent experiment run's cv-server,
and it had no test at all: ``test_session_cv.py`` mocks the manager wholesale and
covers only call wiring.

Everything here is mocked at the ``ps`` / ``lsof`` / ``os.kill`` boundary: no
cv-server is started and no signal reaches a real process.
"""

import subprocess

import pytest

pytestmark = pytest.mark.unit

from adare.backend.experiment.mcp_server_manager import MCPServerManager


@pytest.fixture
def manager():
    return MCPServerManager(server_port=13109)


def _fake_ps(cmdlines: dict[int, str]):
    """Return a ``subprocess.check_output`` stand-in answering ``ps -o command= -p``.

    A PID absent from ``cmdlines`` behaves like a process that has already exited:
    ``ps`` exits non-zero, which is a ``CalledProcessError``.
    """
    def check_output(argv, **kwargs):
        assert argv[0] == 'ps', f"unexpected subprocess call: {argv}"
        pid = int(argv[-1])
        if pid not in cmdlines:
            raise subprocess.CalledProcessError(1, argv)
        return cmdlines[pid].encode()
    return check_output


class TestOwnershipRequiresARecordedPid:
    def test_refuses_when_known_server_pid_is_none(self, manager, monkeypatch):
        """The bug: an attached manager must not claim a stranger's server.

        ``start(allow_existing=True)`` returns True without recording a PID when the
        port was already taken, which is exactly what happens when two runs lose the
        ``find_free_cv_port`` TOCTOU race. The listener then looks perfectly like
        "an adare-cv-server on our port" — because it IS one, just not ours.
        """
        monkeypatch.setattr(
            subprocess, 'check_output',
            _fake_ps({4242: 'adare-cv-server --port 13109'}),
        )
        assert manager.known_server_pid is None
        assert manager._is_our_cv_server(4242, 13109) is False

    def test_leaks_rather_than_kills_when_no_pid_recorded(self, manager, monkeypatch):
        """The accepted cost of the gate: our own unrecorded server is left running.

        Asserted explicitly so the trade-off is visible in the suite rather than only
        in a docstring — leaking one port beats killing another session's experiment.
        """
        killed: list[int] = []
        monkeypatch.setattr(manager, '_pids_on_port', lambda port: [4242])
        monkeypatch.setattr(
            subprocess, 'check_output',
            _fake_ps({4242: 'adare-cv-server --port 13109'}),
        )
        monkeypatch.setattr(
            'os.kill', lambda pid, sig: killed.append(pid),
        )

        assert manager._kill_process_on_port(13109) is False
        assert killed == []

    def test_kills_the_server_it_recorded(self, manager, monkeypatch):
        """The gate must still allow the legitimate case, or dev sessions leak forever."""
        killed: list[int] = []
        manager.known_server_pid = 4242
        monkeypatch.setattr(manager, '_pids_on_port', lambda port: [4242])
        monkeypatch.setattr(
            subprocess, 'check_output',
            _fake_ps({4242: 'adare-cv-server --port 13109'}),
        )
        monkeypatch.setattr('os.kill', lambda pid, sig: killed.append(pid))

        assert manager._kill_process_on_port(13109) is True
        assert killed == [4242]

    def test_refuses_a_pid_that_is_not_the_recorded_one(self, manager, monkeypatch):
        """A recycled port held by an unrelated cv-server is not ours."""
        manager.known_server_pid = 4242
        monkeypatch.setattr(
            subprocess, 'check_output',
            _fake_ps({9999: 'adare-cv-server --port 13109'}),
        )
        assert manager._is_our_cv_server(9999, 13109) is False


class TestCommandLineMatching:
    def test_refuses_a_process_that_is_not_a_cv_server(self, manager, monkeypatch):
        """Whatever else holds the port — a webserver, an editor — stays untouched."""
        manager.known_server_pid = 4242
        monkeypatch.setattr(
            subprocess, 'check_output',
            _fake_ps({4242: 'python -m http.server 13109'}),
        )
        assert manager._is_our_cv_server(4242, 13109) is False

    def test_port_is_matched_on_whole_tokens_not_substrings(self, manager, monkeypatch):
        """The ``1310`` vs ``13109`` trap: a manager for 1310 must not claim 13109.

        ``"--port 1310" in "--port 13109"`` is True as a substring, which is how the
        pre-fix check would have let a low-numbered manager kill the default port's
        server.
        """
        low = MCPServerManager(server_port=1310)
        low.known_server_pid = 4242
        monkeypatch.setattr(
            subprocess, 'check_output',
            _fake_ps({4242: 'adare-cv-server --port 13109'}),
        )
        assert low._is_our_cv_server(4242, 1310) is False

    def test_accepts_the_equals_form_of_the_port_flag(self, manager, monkeypatch):
        manager.known_server_pid = 4242
        monkeypatch.setattr(
            subprocess, 'check_output',
            _fake_ps({4242: 'adare-cv-server --port=13109 --debug'}),
        )
        assert manager._is_our_cv_server(4242, 13109) is True

    def test_refuses_a_cv_server_serving_a_different_port(self, manager, monkeypatch):
        """Same recorded pid, wrong port in argv — argv is the authority, not lsof."""
        manager.known_server_pid = 4242
        monkeypatch.setattr(
            subprocess, 'check_output',
            _fake_ps({4242: 'adare-cv-server --port 13110'}),
        )
        assert manager._is_our_cv_server(4242, 13109) is False

    def test_a_vanished_process_is_not_ours(self, manager, monkeypatch):
        """``ps`` exiting non-zero means the pid is already gone; never a kill target."""
        manager.known_server_pid = 4242
        monkeypatch.setattr(subprocess, 'check_output', _fake_ps({}))
        assert manager._is_our_cv_server(4242, 13109) is False


class TestKillProcessOnPort:
    def test_no_listener_is_not_an_error(self, manager, monkeypatch):
        monkeypatch.setattr(manager, '_pids_on_port', lambda port: [])
        assert manager._kill_process_on_port(13109) is False

    def test_skips_the_stranger_and_kills_only_our_pid(self, manager, monkeypatch):
        """lsof can report several holders; only the vouched-for one may be signalled."""
        killed: list[int] = []
        manager.known_server_pid = 4242
        monkeypatch.setattr(manager, '_pids_on_port', lambda port: [7777, 4242])
        monkeypatch.setattr(
            subprocess, 'check_output',
            _fake_ps({
                7777: 'adare-cv-server --port 13109',
                4242: 'adare-cv-server --port 13109',
            }),
        )
        monkeypatch.setattr('os.kill', lambda pid, sig: killed.append(pid))

        assert manager._kill_process_on_port(13109) is True
        assert killed == [4242]

    def test_a_process_that_exits_between_lsof_and_kill_is_tolerated(self, manager, monkeypatch):
        """ProcessLookupError is a benign race, not a teardown failure."""
        def raising_kill(pid, sig):
            raise ProcessLookupError(pid)

        manager.known_server_pid = 4242
        monkeypatch.setattr(manager, '_pids_on_port', lambda port: [4242])
        monkeypatch.setattr(
            subprocess, 'check_output',
            _fake_ps({4242: 'adare-cv-server --port 13109'}),
        )
        monkeypatch.setattr('os.kill', raising_kill)

        assert manager._kill_process_on_port(13109) is False
