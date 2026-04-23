"""HTTP server for autoinstall config and QEMU process monitoring."""

import contextlib
import logging
import socket
import subprocess
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

from rich.status import Status

from adare.console import console

log = logging.getLogger(__name__)


class _QuietHandler(SimpleHTTPRequestHandler):
    """HTTP handler that serves files from a directory without noisy logging."""

    def log_message(self, format, *args):
        log.debug(f'HTTP: {format % args}')


def _find_free_port() -> int:
    """Find a free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class AutoinstallHTTPServer:
    """Temporary HTTP server that serves autoinstall config files to the VM.

    QEMU user-mode networking routes 10.0.2.2 to the host, so the VM
    can fetch autoinstall config from http://10.0.2.2:PORT/.

    Usage:
        with AutoinstallHTTPServer(serve_dir) as server:
            port = server.port
            # ... boot QEMU with ds=nocloud-net;seedfrom=http://10.0.2.2:{port}/
    """

    def __init__(self, serve_dir: Path):
        self.serve_dir = serve_dir
        self.port = _find_free_port()
        self._httpd: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def __enter__(self) -> 'AutoinstallHTTPServer':
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()

    def start(self) -> None:
        """Start the HTTP server in a background thread."""
        handler = type(
            'Handler',
            (_QuietHandler,),
            {'directory': str(self.serve_dir)},
        )
        # Python 3.13 needs the directory kwarg in the handler init
        # but SimpleHTTPRequestHandler reads it from self.directory attribute
        self._httpd = HTTPServer(('127.0.0.1', self.port), handler)
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            daemon=True,
            name='autoinstall-http',
        )
        self._thread.start()
        log.info(f'Autoinstall HTTP server started on port {self.port} serving {self.serve_dir}')

    def stop(self) -> None:
        """Stop the HTTP server."""
        if self._httpd:
            self._httpd.shutdown()
            self._httpd = None
            log.info('Autoinstall HTTP server stopped')


def wait_for_qemu_exit(
    process: subprocess.Popen,
    timeout_minutes: int = 60,
    label: str = 'VM installation',
    status: Status | None = None,
) -> int:
    """Wait for a QEMU process to exit (VM shutdown after install).

    Args:
        process: The QEMU subprocess
        timeout_minutes: Maximum time to wait in minutes
        label: Label for log messages
        status: Optional Rich Status for in-place spinner updates

    Returns:
        Process return code

    Raises:
        TimeoutError: If process doesn't exit within timeout
        subprocess.CalledProcessError: If process exits with non-zero code
    """
    timeout_seconds = timeout_minutes * 60
    log.info(f'Waiting for {label} to complete (timeout: {timeout_minutes} min)...')

    start = time.monotonic()
    status_interval = 120  # Log status every 2 minutes
    last_status = start

    while True:
        try:
            retcode = process.wait(timeout=10)
            elapsed = time.monotonic() - start
            log.info(f'{label} completed in {elapsed / 60:.1f} minutes (exit code: {retcode})')

            # Capture stderr for diagnostics (non-blocking read of piped output)
            stderr_output = ''
            if process.stderr:
                with contextlib.suppress(OSError, ValueError):
                    stderr_output = process.stderr.read().decode(errors='replace').strip()
                if stderr_output:
                    log.info(f'{label} QEMU stderr: {stderr_output[:2000]}')

            if retcode != 0:
                raise subprocess.CalledProcessError(retcode, process.args, stderr=stderr_output)
            if elapsed < 60:
                log.warning(
                    f'{label} completed suspiciously fast ({elapsed:.0f}s). '
                    f'QEMU may have failed to start.'
                )
            return retcode

        except subprocess.TimeoutExpired:
            elapsed = time.monotonic() - start

            if elapsed > timeout_seconds:
                log.error(f'{label} timed out after {timeout_minutes} minutes')
                process.terminate()
                try:
                    process.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    process.kill()
                raise TimeoutError(
                    f'{label} did not complete within {timeout_minutes} minutes'
                )

            # Periodic status update
            now = time.monotonic()
            if now - last_status >= status_interval:
                mins = elapsed / 60
                if status is not None:
                    status.update(f'  [cyan]{label}[/cyan] in progress [bold]({mins:.0f} min elapsed)[/bold]')
                else:
                    console.print(f'  [dim]...[/dim] {label} in progress [bold]({mins:.0f} min elapsed)[/bold]')
                last_status = now
