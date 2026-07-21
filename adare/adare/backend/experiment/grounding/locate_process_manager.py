"""Spawn / attach lifecycle for the vendored LocateAnything grounding server.

``adare dev agent --ground`` needs a grounding endpoint without the user having
pre-started one. This manager provides it:

* **attach** — if an endpoint is already configured (``base_url``) or a server is
  already listening on the port, use it and never spawn (so we also never kill a
  server the user is running).
* **spawn** — otherwise launch :mod:`.locate_server` as a detached subprocess and
  poll ``GET /health`` until the model has loaded (a generous budget, since the
  first ``/health`` blocks on the ~7 GB weight load / cold HF download).
* **teardown** — :meth:`stop` SIGTERMs (then kills) the child, but only if *we*
  spawned it.

By default the server runs in adare's own interpreter (``sys.executable -m
adare.backend.experiment.grounding.locate_server``), which needs the ``grounding``
extra. If ``python_exe`` (``ADARE_LOCATE_PYTHON``) points at another interpreter
— e.g. a venv that already has torch + the model's ``trust_remote_code`` deps —
the server is launched by its **file path** with that interpreter instead
(``locate_server`` deliberately imports nothing from ``adare``).
"""
from __future__ import annotations

import logging
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import locate_server

log = logging.getLogger(__name__)

_SERVER_MODULE = 'adare.backend.experiment.grounding.locate_server'
_SERVER_FILE = str(Path(locate_server.__file__).resolve())


class GroundingUnavailable(RuntimeError):
    """The auto-started grounding server could not be brought up."""


class LocateGroundingManager:
    """Manages the vendored LocateAnything grounding server subprocess."""

    def __init__(
        self,
        *,
        host: str = '127.0.0.1',
        port: int = 13111,
        base_url: str | None = None,
        model_path: str | None = None,
        python_exe: str | None = None,
        start_timeout: float = 180.0,
        log_file: Path | None = None,
    ):
        self.host = host
        self.port = port
        # An explicitly configured endpoint (e.g. ADARE_LOCATE_URL) -> attach.
        self.base_url = base_url.rstrip('/') if base_url else None
        self.model_path = model_path or None
        self.python_exe = python_exe or None
        self.start_timeout = start_timeout
        self.log_file = log_file
        self.process: subprocess.Popen | None = None
        self.spawned = False
        self._log_handle = None

    @property
    def _local_url(self) -> str:
        return f'http://{self.host}:{self.port}'

    def start(self) -> str:
        """Ensure a grounding endpoint is reachable and return its base URL.

        Attaches to a configured / already-listening server, otherwise spawns
        one and blocks until it answers ``/health``.
        """
        if self.base_url:
            log.info('LocateAnything grounding: attaching to configured %s', self.base_url)
            return self.base_url

        if self._is_port_in_use():
            log.info('LocateAnything grounding: attaching to server already on %s', self._local_url)
            return self._local_url

        self._spawn()
        self._await_health()
        return self._local_url

    def _spawn(self) -> None:
        if self.python_exe:
            # Foreign interpreter -> run by file path (server has no adare imports).
            cmd = [self.python_exe, _SERVER_FILE, '--host', self.host, '--port', str(self.port)]
        else:
            cmd = [sys.executable, '-m', _SERVER_MODULE, '--host', self.host, '--port', str(self.port)]
        if self.model_path:
            cmd += ['--model', self.model_path]

        if self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
            self._log_handle = open(self.log_file, 'w')  # noqa: SIM115 (lifetime = server)
            stdout = self._log_handle
            stderr = subprocess.STDOUT
        else:
            stdout = subprocess.DEVNULL
            stderr = subprocess.DEVNULL

        log.info('auto-starting LocateAnything grounding: %s', ' '.join(cmd))
        try:
            self.process = subprocess.Popen(  # noqa: S603 (fixed argv, no shell)
                cmd, stdout=stdout, stderr=stderr, start_new_session=True,
            )
        except OSError as exc:  # bad ADARE_LOCATE_PYTHON, permissions, etc.
            if self._log_handle:
                self._log_handle.close()
                self._log_handle = None
            raise GroundingUnavailable(
                f'could not launch grounding server ({cmd[0]}): {exc}'
            ) from exc
        self.spawned = True

    def _await_health(self) -> None:
        deadline = time.monotonic() + self.start_timeout
        url = f'{self._local_url}/health'
        last_err: str | None = None
        while time.monotonic() < deadline:
            if self.process and self.process.poll() is not None:
                self.spawned = False  # it's dead; nothing for us to stop
                raise GroundingUnavailable(
                    f'LocateAnything grounding server exited early (code '
                    f'{self.process.returncode}). Is the grounding backend installed '
                    f'(uv sync --extra grounding) or ADARE_LOCATE_PYTHON set?'
                    + self._log_hint()
                )
            try:
                with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310 (localhost)
                    if resp.status == 200:
                        log.info('LocateAnything grounding ready on %s', self._local_url)
                        return
                    last_err = f'HTTP {resp.status}'
            except urllib.error.HTTPError as exc:
                # 503 -> extra missing / still loading; keep the body for the message.
                last_err = f'HTTP {exc.code}: {exc.read().decode("utf-8", "replace")[:200]}'
            except (urllib.error.URLError, TimeoutError, OSError):
                last_err = 'not up yet'
            time.sleep(2.0)

        self.stop()
        raise GroundingUnavailable(
            f'LocateAnything grounding server not ready within {self.start_timeout:.0f}s '
            f'(last: {last_err}).' + self._log_hint()
        )

    def stop(self) -> None:
        """Tear down the server — only if we spawned it (never a user's server)."""
        if self.process and self.spawned and self.process.poll() is None:
            log.info('stopping auto-started LocateAnything grounding server (pid=%d)',
                     self.process.pid)
            self.process.send_signal(signal.SIGTERM)
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                log.warning('grounding server did not stop gracefully, killing')
                self.process.kill()
                self.process.wait()
        self.process = None
        self.spawned = False
        if self._log_handle:
            self._log_handle.close()
            self._log_handle = None

    def _is_port_in_use(self) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            try:
                return s.connect_ex((self.host, self.port)) == 0
            except OSError:
                return False

    def _log_hint(self) -> str:
        return f' See the server log: {self.log_file}' if self.log_file else ''
