"""Ephemeral HTTP server that hands a rendered seed directory to a booting installer.

Most installer families auto-detect their answer file from a labelled drive
(``cidata`` for cloud-init, ``OEMDRV`` for debian-installer / Anaconda), so ADARE
just attaches a seed ISO. **ubiquity** — the installer on the Ubuntu and Kubuntu
*desktop* ISOs — has no such auto-detect: casper's network-preseed init script
fetches the answer file from the ``url=`` given on the kernel command line.

Under QEMU user-mode networking the guest always reaches the host at ``10.0.2.2``,
so serving the seed directory on an ephemeral host port for the duration of the
install is enough. The port is substituted into ``OsDefinition.kernel_cmdline``
via ``{seed_port}``.
"""

import logging
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

log = logging.getLogger(__name__)


class _SeedRequestHandler(SimpleHTTPRequestHandler):
    """Static file handler that logs through ``logging`` instead of stderr."""

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - stdlib signature
        log.info('seed-http %s - %s', self.address_string(), format % args)


class SeedHTTPServer:
    """Serve ``seed_dir`` over HTTP on an ephemeral port, in a daemon thread.

    Usable as a context manager::

        with SeedHTTPServer(seed_dir) as srv:
            cmdline = tmpl.format(seed_port=srv.port)
    """

    def __init__(self, seed_dir: Path, bind: str = '0.0.0.0'):
        self.seed_dir = seed_dir
        handler = partial(_SeedRequestHandler, directory=str(seed_dir))
        self._httpd = ThreadingHTTPServer((bind, 0), handler)
        self._thread: threading.Thread | None = None

    @property
    def port(self) -> int:
        """The ephemeral port the server bound to."""
        return int(self._httpd.server_address[1])

    def start(self) -> 'SeedHTTPServer':
        if self._thread is not None:
            return self
        self._thread = threading.Thread(
            target=self._httpd.serve_forever,
            name='adare-seed-http',
            daemon=True,
        )
        self._thread.start()
        log.info('Serving seed dir %s on http://0.0.0.0:%d/', self.seed_dir, self.port)
        return self

    def stop(self) -> None:
        if self._thread is None:
            return
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=10)
        self._thread = None
        log.info('Stopped seed HTTP server for %s', self.seed_dir)

    def __enter__(self) -> 'SeedHTTPServer':
        return self.start()

    def __exit__(self, *_exc) -> None:
        self.stop()


def serves_seed_over_http(kernel_cmdline: str) -> bool:
    """True if ``kernel_cmdline`` expects a ``{seed_port}`` substitution.

    Profiles that fetch their answer file over HTTP (the ``ubiquity`` family)
    declare it by putting ``{seed_port}`` in their kernel command line; those get
    a ``SeedHTTPServer`` instead of an attached seed ISO.
    """
    return '{seed_port}' in kernel_cmdline
