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
            force_external: If True, check for and kill process on port even if not child.
                           If False, only stop local child process.
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
                return

            # 2. If no local process, check if server is running on port and kill it
            # Only done if force_external is True (e.g. during final cleanup)
            if force_external and self._is_port_in_use(self.server_port):
                log.info(f"Stopping external MCP GUI server on port {self.server_port}...")
                if self._kill_process_on_port(self.server_port):
                    log.info("External MCP GUI server stopped")
                else:
                    log.warning("Failed to stop external MCP GUI server")

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

    def _kill_process_on_port(self, port: int) -> bool:
        """
        Kill process listening on the specified port.

        Uses lsof or fuser to find PID and terminate it.
        """
        try:
            # Try finding PID using lsof
            cmd = f"lsof -t -i:{port}"
            try:
                pid_str = subprocess.check_output(cmd.split(), stderr=subprocess.DEVNULL).decode().strip()
                if pid_str:
                    pid = int(pid_str)
                    log.info(f"Killing process {pid} on port {port}")
                    import os
                    import signal
                    os.kill(pid, signal.SIGTERM)
                    return True
            except subprocess.CalledProcessError:
                # No process found with lsof
                pass
            except (OSError, ValueError) as e:
                log.warning(f"Error using lsof: {e}")

            # Fallback to fuser (common on some linux distros)
            cmd = f"fuser -k {port}/tcp"
            try:
                subprocess.run(cmd.split(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
                # We assume if it ran without crashing, it might have worked?
                # fuser returns non-zero if no process killed.
                return True
            except OSError as e:
                log.warning(f"Error using fuser: {e}")

            return False

        except OSError as e:
            log.error(f"Failed to kill process on port {port}: {e}")
            return False
