"""
MCP GUI Server Management Module.

This module provides functionality to start, stop, and manage the MCP GUI server
subprocess for target detection in experiments.
"""

import asyncio
import logging
import subprocess
from datetime import datetime
from pathlib import Path

import httpx

log = logging.getLogger(__name__)

# The cv-server's own default (adare_cv_server.constants.DEFAULT_PORT). Duplicated
# rather than imported because adare must not hard-depend on the cv-server package.
DEFAULT_CV_PORT = 13109

# How many consecutive ports to try when DEFAULT_CV_PORT is taken. A small window
# keeps a pathological scan from wandering into unrelated services' territory while
# still allowing a realistic number of concurrent runs on one host.
CV_PORT_SCAN_WINDOW = 32


def find_free_cv_port(preferred: int = DEFAULT_CV_PORT, window: int = CV_PORT_SCAN_WINDOW) -> int:
    """Return the first bindable port at or above ``preferred``.

    Concurrent ``adare experiment run`` invocations otherwise all land on
    :data:`DEFAULT_CV_PORT`. Sharing one cv-server across runs is worse than it
    looks: ``--debug-output-dir`` and the log file are fixed in the *spawned*
    process's argv, so a second run that merely attaches writes its CV debug
    images into the FIRST run's directory and leaves its own ``mcp_gui.log``
    empty — silently attributing evidence to the wrong run. Giving each run its
    own port keeps that per-run isolation intact.

    Bind (not connect) is the right test here: ``connect_ex`` cannot distinguish
    "free" from "bound but not listening yet", which is exactly the state a
    sibling run's cv-server is in while it imports cv2/PaddleOCR.

    Note the residual TOCTOU window — the socket is closed again before the
    cv-server binds it, so two runs starting in the same instant can still pick
    the same port. The loser attaches to the winner's server (``start()`` with
    ``allow_existing=True``) rather than crashing.

    Args:
        preferred: First port to try.
        window: How many consecutive ports to try before giving up.

    Returns:
        A port that was bindable at the moment of the check.

    Raises:
        LoggedException: If no port in the window is free.
    """
    from adare.helperfunctions.port import is_localhost_port_free

    for port in range(preferred, preferred + window):
        if is_localhost_port_free(port):
            if port != preferred:
                log.info(
                    f"CV/OCR port {preferred} is in use (likely a concurrent run); "
                    f"using {port} instead"
                )
            return port

    from adare.exceptions import LoggedException
    raise LoggedException(
        log,
        message=(
            f"No free CV/OCR server port in range "
            f"{preferred}-{preferred + window - 1}; is something holding these ports?"
        ),
    )


# Filename, inside a run's logs/ directory, recording which cv-server that run or
# dev session owns. Lives beside mcp_gui.log rather than in the dev_sessions table
# because the run directory is ALREADY persisted (dev_sessions.run_directory_path)
# and restored on resume, so this needs no schema change to survive a process exit.
CV_STATE_FILENAME = 'cv_server.json'


def cv_state_file(run_directory: Path) -> Path:
    """Path of the CV ownership record for ``run_directory``.

    Derived from the run directory path rather than added as an
    ``ExperimentRunDirectory`` attribute on purpose: the dev-session restorer
    rebuilds that object via ``__new__`` and hand-sets only a few attributes
    (session_restorer.py), so a new attribute would silently be missing there.
    """
    return run_directory / 'logs' / CV_STATE_FILENAME


def save_cv_state(run_directory: Path, port: int, pid: int | None) -> None:
    """Record which port/PID this run's cv-server owns. Best-effort."""
    import json

    target = cv_state_file(run_directory)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({'port': port, 'pid': pid}), encoding='utf-8')
        log.debug(f"Recorded CV server ownership ({port}, pid={pid}) in {target}")
    except OSError as e:
        # Losing this only costs a resumed session its ability to reclaim the
        # port; it must never fail a run.
        log.warning(f"Could not record CV server state to {target}: {e}")


def load_cv_state(run_directory: Path) -> tuple[int | None, int | None]:
    """Return the ``(port, pid)`` recorded for ``run_directory``, or ``(None, None)``."""
    import json

    source = cv_state_file(run_directory)
    if not source.exists():
        return None, None
    try:
        data = json.loads(source.read_text(encoding='utf-8'))
    except (OSError, ValueError) as e:
        log.warning(f"Could not read CV server state from {source}: {e}")
        return None, None

    port = data.get('port')
    pid = data.get('pid')
    if not isinstance(port, int):
        log.warning(f"Ignoring CV server state with non-integer port in {source}")
        return None, None
    return port, pid if isinstance(pid, int) else None


class MCPServerManager:
    """
    Manager for the MCP GUI server subprocess.

    Handles starting, stopping, and health checking the MCP GUI server
    that provides image and text detection services for playbook execution.
    """


    # How long to wait for the freshly-launched server to actually serve its
    # /mcp endpoint. The cv-server imports cv2 + PaddleOCR at module load
    # (several seconds cold) before it binds, so a naive fixed sleep is not
    # enough — we poll the endpoint until it answers or this budget elapses.
    STARTUP_PROBE_TIMEOUT = 60.0
    STARTUP_PROBE_INTERVAL = 1.0

    def __init__(self, server_port: int = DEFAULT_CV_PORT, log_file: Path | None = None, debug: bool = False, debug_output_dir: Path | None = None):
        """
        Initialize MCP server manager.

        Args:
            server_port: Port for MCP server (default: DEFAULT_CV_PORT). Callers that
                may run concurrently with another run should pass
                ``find_free_cv_port()`` instead of relying on this default.
            log_file: Path to log file for MCP server output
            debug: Enable debug logging
            debug_output_dir: Directory for debug output images
        """
        self.server_port = server_port
        self.process: subprocess.Popen | None = None
        self.server_url = f"http://localhost:{server_port}/mcp"
        self.log_file = log_file
        self.debug = debug
        self.debug_output_dir = debug_output_dir
        # PID of the cv-server this manager is entitled to stop. Set when we spawn
        # one, or restored by a resumed dev session from its recorded state (see
        # save_cv_state / load_cv_state). None means "we have not identified a
        # server yet", in which case only a command-line match is required.
        # Never derived from ppid — start_new_session=True makes ppid=1 the normal
        # state for a healthy server, so ppid carries no ownership information.
        self.known_server_pid: int | None = None

    async def start(self, allow_existing: bool = True) -> bool:
        """
        Start the MCP GUI server as a non-blocking subprocess.

        Args:
            allow_existing: If True, attach to existing server on port.
                           If False, fail if port is already in use.

        Returns:
            True if server started successfully, False otherwise
        """
        # Check if port is already in use (server running from another session)
        if self._is_port_in_use(self.server_port):
            if allow_existing:
                log.info(f"MCP server already running on port {self.server_port}")
                return True
            log.error(f"Port {self.server_port} is already in use and allow_existing=False")
            return False

        if self.process and self.process.poll() is None:
            log.info("MCP server already running")
            return True

        try:
            log.info(f"Starting MCP GUI server on port {self.server_port}...")

            # Open log file if specified
            log_file_handle = None
            if self.log_file:
                self.log_file.parent.mkdir(parents=True, exist_ok=True)
                log_file_handle = open(self.log_file, 'w')
                log_file_handle.write(f"=== MCP GUI Server Log Started at {datetime.now()} ===\n")
                log_file_handle.flush()

            cmd = ["adare-cv-server", "--port", str(self.server_port)]
            if self.debug:
                cmd.append("--debug")

            if self.debug_output_dir:
                cmd.extend(["--debug-output-dir", str(self.debug_output_dir)])

            # Start process with start_new_session=True to detach from parent
            # This ensures it survives when the CLI tool exits
            self.process = subprocess.Popen(
                cmd,
                stdout=log_file_handle or subprocess.PIPE,
                stderr=subprocess.STDOUT if log_file_handle else subprocess.PIPE,
                text=True,
                start_new_session=True
            )
            # We spawned it, so we own it — this is what later entitles
            # stop(force_external=True) to terminate it after our Popen handle is
            # gone (e.g. in a resumed session).
            self.known_server_pid = self.process.pid

            # Wait for the server to actually serve /mcp — not just for the
            # process to still be alive. A silent crash on heavy imports (cv2 /
            # PaddleOCR) or a lazy model-load failure would otherwise report
            # "started successfully" and only surface later as a ConnectError
            # during replay. Probe the endpoint until it answers, failing fast
            # if the process dies meanwhile.
            if not await self._await_ready():
                await self._terminate_dead_process()
                return False

            log.info("MCP GUI server started successfully")
            return True

        except (OSError, subprocess.SubprocessError, ValueError) as e:
            log.error(f"Failed to start MCP server: {e}")
            self.process = None
            return False

    async def _await_ready(self) -> bool:
        """Poll the /mcp endpoint until it responds or the budget elapses.

        Returns True once a FastMCP handshake (``list_tools``) succeeds, False
        if the process exits or the endpoint never serves within
        :data:`STARTUP_PROBE_TIMEOUT`.
        """
        from fastmcp import Client

        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.STARTUP_PROBE_TIMEOUT
        last_error: str = "no response"

        while loop.time() < deadline:
            # Fail fast if the subprocess has already exited.
            if self.process is None or self.process.poll() is not None:
                log.error(
                    f"MCP server process exited during startup "
                    f"(rc={self.process.poll() if self.process else 'n/a'}); "
                    f"see {self.log_file or 'server log'} for details"
                )
                return False

            try:
                async with Client(self.server_url) as client:
                    await client.list_tools()
                log.info(f"MCP GUI server is serving at {self.server_url}")
                return True
            except (OSError, ConnectionError, TimeoutError, RuntimeError,
                    httpx.HTTPError) as exc:
                # httpx.ConnectError ("connection refused" while the server is
                # still binding) is an httpx.HTTPError, NOT an OSError — it must
                # be listed explicitly or the probe crashes instead of retrying.
                last_error = f"{type(exc).__name__}: {exc}"

            await asyncio.sleep(self.STARTUP_PROBE_INTERVAL)

        log.error(
            f"MCP server did not become ready at {self.server_url} within "
            f"{self.STARTUP_PROBE_TIMEOUT:.0f}s (last error: {last_error}); "
            f"see {self.log_file or 'server log'} for details"
        )
        return False

    async def _terminate_dead_process(self) -> None:
        """Reap a launched-but-unready process so it does not linger."""
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
            except (OSError, subprocess.SubprocessError) as exc:
                log.warning(f"Error reaping unready MCP server: {exc}")
        self.process = None

    async def stop(self, force_external: bool = False):
        """
        Stop the MCP GUI server subprocess gracefully.

        Args:
            force_external: If True, also stop a server we did not spawn in this
                           process — but only one that :meth:`_is_our_cv_server`
                           can vouch for on :attr:`server_port`. Needed by resumed
                           dev sessions, whose server outlived the Popen handle.
                           If False, only stop the local child process.
        """
        try:
            # 1. Try to stop local child process
            if self.process and self.process.poll() is None:
                log.info("Stopping local MCP GUI server process...")
                try:
                    self.process.terminate()
                    self.process.wait(timeout=5)
                    log.info("MCP GUI server stopped gracefully")
                except subprocess.TimeoutExpired:
                    log.warning("MCP server didn't respond to SIGTERM, forcing kill...")
                    self.process.kill()
                    self.process.wait()
                self.process = None
                self.known_server_pid = None
                return

            # 2. If no local process, check if server is running on port and kill it
            # Only done if force_external is True (e.g. during final cleanup)
            if force_external and self._is_port_in_use(self.server_port):
                log.info(f"Stopping external MCP GUI server on port {self.server_port}...")
                if self._kill_process_on_port(self.server_port):
                    log.info("External MCP GUI server stopped")
                    self.known_server_pid = None
                else:
                    log.warning(
                        f"Left port {self.server_port} alone — nothing there could be "
                        f"verified as this session's cv-server"
                    )

        except (OSError, subprocess.SubprocessError) as e:
            log.error(f"Error stopping MCP server: {e}")

    def is_running(self) -> bool:
        """
        Check if MCP server process is running (local or external).

        Returns:
            True if process is running, False otherwise
        """
        # Check local process
        if self.process and self.process.poll() is None:
            return True

        # Check port usage
        return self._is_port_in_use(self.server_port)

    def _is_port_in_use(self, port: int) -> bool:
        """Check if a port is in use."""
        import socket
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                # Set timeout to avoid hanging
                s.settimeout(1.0)
                return s.connect_ex(('localhost', port)) == 0
        except OSError:
            return False

    def _pids_on_port(self, port: int) -> list[int]:
        """Return every PID holding ``port``, or an empty list.

        ``lsof -t`` prints one PID per line and can legitimately return several,
        which the previous single-``int()`` parse turned into a ValueError.
        """
        try:
            out = subprocess.check_output(
                ["lsof", "-t", f"-i:{port}"], stderr=subprocess.DEVNULL
            ).decode()
        except subprocess.CalledProcessError:
            return []  # lsof exits non-zero when nothing holds the port
        except (OSError, ValueError) as e:
            log.warning(f"Could not enumerate PIDs on port {port} via lsof: {e}")
            return []

        pids = []
        for line in out.split():
            if line.strip().isdigit():
                pids.append(int(line.strip()))
        return pids

    def _is_our_cv_server(self, pid: int, port: int) -> bool:
        """Is ``pid`` the ``adare-cv-server`` **we own** on ``port``?

        Ownership requires a recorded PID. Identity is then established from the
        process's own command line, never from ``ppid``: the server is spawned
        with ``start_new_session=True``, so being reparented to init is the
        DESIGNED state and says nothing about ownership.

        A missing :attr:`known_server_pid` is a hard NO, not a fall-back to
        "any ``adare-cv-server`` on this port". That fall-back had a live hole:
        :meth:`start` returns True *without* recording a PID whenever the port
        was already in use and ``allow_existing=True`` (the default, used by
        ``run_setup.step_start_mcp_server``), which happens whenever two runs
        lose the ``find_free_cv_port`` TOCTOU race. Dev-session teardown then
        calls ``stop(force_external=True)``, and the name+port match would
        cheerfully SIGTERM a *concurrent run's* server mid-experiment.

        The trade-off is deliberate and asymmetric: with this gate we may LEAK
        our own server — a ``cv_server.json`` written before pid recording, or
        any record whose ``pid`` field is absent, now yields "left running"
        instead of a kill. Leaking your own process costs one stale port in a
        32-port scan window and is reclaimed by the next
        :func:`find_free_cv_port`; killing someone else's costs them a
        half-finished forensic experiment. Leak, never kill.
        """
        if self.known_server_pid is None:
            log.warning(
                f"Refusing to touch PID {pid} on port {port}: this manager has no "
                f"recorded cv-server PID, so it cannot prove the listener is its "
                f"own (a concurrent run's server looks identical). Leaving it alone"
            )
            return False

        if pid != self.known_server_pid:
            log.warning(
                f"Refusing to touch PID {pid} on port {port}: this manager owns "
                f"PID {self.known_server_pid}, so {pid} belongs to someone else"
            )
            return False

        try:
            cmdline = subprocess.check_output(
                ["ps", "-o", "command=", "-p", str(pid)], stderr=subprocess.DEVNULL
            ).decode().strip()
        except subprocess.CalledProcessError:
            return False  # process is already gone
        except (OSError, ValueError) as e:
            log.warning(f"Could not read command line of PID {pid}: {e}")
            return False

        if "adare-cv-server" not in cmdline:
            log.warning(
                f"Refusing to kill PID {pid} on port {port}: not an adare-cv-server "
                f"({cmdline[:120]!r})"
            )
            return False

        # The port is in the spawn argv (see start()), so this pins the match to the
        # exact server we mean rather than any cv-server on the box. Matched on whole
        # tokens, not as a substring: "--port 1310" IS a substring of
        # "--port 13109", which would let a manager for 1310 claim 13109's server.
        tokens = cmdline.split()
        names_port = any(
            (tok == "--port" and idx + 1 < len(tokens) and tokens[idx + 1] == str(port))
            or tok == f"--port={port}"
            for idx, tok in enumerate(tokens)
        )
        if not names_port:
            log.warning(
                f"Refusing to kill cv-server PID {pid}: its command line does not "
                f"name port {port} ({cmdline[:120]!r})"
            )
            return False

        return True

    def _kill_process_on_port(self, port: int) -> bool:
        """
        Terminate the adare-cv-server listening on ``port``.

        Only kills a process that :meth:`_is_our_cv_server` vouches for. This is
        what stops a dev session from killing a concurrent experiment run's CV
        server: an unverified listener is left strictly alone, and the previous
        blind ``fuser -k <port>/tcp`` fallback — which killed whatever held the
        port, cv-server or not — is gone.
        """
        import os
        import signal

        pids = self._pids_on_port(port)
        if not pids:
            log.info(f"No process holds port {port}; nothing to stop")
            return False

        killed = False
        for pid in pids:
            if not self._is_our_cv_server(pid, port):
                continue
            try:
                log.info(f"Terminating adare-cv-server PID {pid} on port {port}")
                os.kill(pid, signal.SIGTERM)
                killed = True
            except ProcessLookupError:
                log.info(f"cv-server PID {pid} already exited")
            except PermissionError as e:
                log.warning(f"Not permitted to terminate PID {pid}: {e}")
            except OSError as e:
                log.warning(f"Failed to terminate PID {pid} on port {port}: {e}")

        if not killed:
            log.warning(
                f"Port {port} is held by {pids}, but none of those could be "
                f"verified as this manager's cv-server — left running"
            )
        return killed
