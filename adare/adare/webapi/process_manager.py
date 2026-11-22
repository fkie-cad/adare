"""Process manager for VirtualSpice backend.

ADARE runs its own VirtualSpice server with its own data dir
(:data:`~adare.config.configdirectory.VIRTUALSPICE_DATA_DIR`): VirtualSpice
allows one server per data dir, so sharing the default one would fail whenever
the user's VirtualSpice app (or a server `vspice` started) is running, and it
would import every throwaway run domain into the user's VirtualSpice library.

That needs a VirtualSpice with the `--data-dir` option and the `serve`
subcommand; older builds found on disk are skipped.
"""

import logging
import os
import shutil
import signal
import subprocess
import time
from functools import lru_cache
from pathlib import Path

from adare.config.configdirectory import VIRTUALSPICE_DATA_DIR

logger = logging.getLogger(__name__)

LOG_FILE_NAME = "adare-server.log"
_START_TIMEOUT = 10.0  # seconds until the server must answer its health check


@lru_cache(maxsize=16)
def supports_data_dir(binary: str) -> bool:
    """Whether a VirtualSpice binary is new enough (has `--data-dir` and `serve`)."""
    try:
        result = subprocess.run([binary, "--help"], capture_output=True, text=True, timeout=10, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        logger.debug("Could not query %s --help: %s", binary, e)
        return False
    help_text = result.stdout + result.stderr
    return "--data-dir" in help_text and "serve" in help_text


class VirtualSpiceManager:
    """Manages the VirtualSpice Rust backend as a subprocess."""

    def __init__(self, port: int = 8081, binary_path: str | None = None):
        self.port = port
        self.binary_path = binary_path or self._find_binary()
        self.process: subprocess.Popen | None = None
        self.reused = False  # True when a server already answering on the port is used instead
        self.error: str | None = None  # why the last start failed

    @staticmethod
    def _candidates() -> list[str]:
        """Every place a VirtualSpice binary may be, in order of preference."""
        found: list[str] = []
        env_path = os.environ.get("VIRTUALSPICE_BINARY")
        if env_path and os.path.isfile(env_path):
            found.append(env_path)

        # The SpiceMacOS crate is a cargo *workspace* whose binary is named
        # `spice-client` and lands in the workspace-root `target/`; installed
        # copies are often renamed `virtualspice`.
        spice_root = Path.home() / "Documents" / "Projects" / "SpiceMacOS"
        for path in (
            Path.home() / ".local" / "bin" / "virtualspice",
            Path("/usr/local/bin/virtualspice"),
            spice_root / "target" / "release" / "spice-client",
            spice_root / "target" / "debug" / "spice-client",
        ):
            if path.is_file():
                found.append(str(path))

        # Managed cache tier: a release binary downloaded by virtualspice_release.
        # Network-free: cached_binary_path() only reports an already-present binary.
        from adare.webapi.virtualspice_release import cached_binary_path

        cached = cached_binary_path()
        if cached is not None:
            found.append(str(cached))

        for name in ("vspice", "virtualspice", "spice-client"):
            if on_path := shutil.which(name):
                found.append(on_path)
        return list(dict.fromkeys(found))

    def _find_binary(self) -> str | None:
        """The first VirtualSpice binary that is new enough; older builds are skipped with a warning."""
        for candidate in self._candidates():
            if supports_data_dir(candidate):
                return candidate
            logger.warning(
                "Skipping VirtualSpice at %s: it predates --data-dir/serve. "
                "Rebuild it or run `adare ui install-spice --force`.",
                candidate,
            )
        return None

    @property
    def available(self) -> bool:
        """Whether a usable VirtualSpice binary was found."""
        return self.binary_path is not None

    @property
    def log_file(self) -> Path:
        return VIRTUALSPICE_DATA_DIR / LOG_FILE_NAME

    def command(self) -> list[str]:
        assert self.binary_path is not None
        return [
            self.binary_path,
            "--data-dir",
            str(VIRTUALSPICE_DATA_DIR),
            "serve",
            "--port",
            str(self.port),
        ]

    def start(self) -> bool:
        """Start the VirtualSpice backend (or reuse one already on the port). True once it answers."""
        self.error = None
        if self.process and self.process.poll() is None:
            return True  # Already running
        if self.health_check():
            # Started by an earlier `adare ui start`, or by the user: use it rather
            # than fail to bind the port.
            logger.info("VirtualSpice already answering on port %d; using it", self.port)
            self.reused = True
            return True
        if not self.binary_path:
            self.error = "no VirtualSpice binary found"
            return False

        VIRTUALSPICE_DATA_DIR.mkdir(parents=True, exist_ok=True)
        try:
            # Its output goes to a file: an unread pipe fills up and then blocks the server.
            with open(self.log_file, "w") as log:
                self.process = subprocess.Popen(self.command(), stdout=log, stderr=subprocess.STDOUT)
        except OSError as e:
            self.error = f"cannot start {self.binary_path}: {e}"
            logger.warning("VirtualSpice: %s", self.error)
            return False

        deadline = time.monotonic() + _START_TIMEOUT
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                self.error = f"exited with code {self.process.returncode}: {self.log_tail() or 'no output'}"
                logger.warning("VirtualSpice %s (log: %s)", self.error, self.log_file)
                self.process = None
                return False
            if self.health_check():
                logger.info("VirtualSpice started on port %d (pid=%d)", self.port, self.process.pid)
                return True
            time.sleep(0.2)
        logger.warning("VirtualSpice (pid=%d) did not answer within %.0fs", self.process.pid, _START_TIMEOUT)
        return True

    def log_tail(self, lines: int = 3) -> str:
        """The last lines VirtualSpice printed, for error messages."""
        try:
            text = self.log_file.read_text(errors="replace")
        except OSError:
            return ""
        return " | ".join(line.strip() for line in text.strip().splitlines()[-lines:])

    def stop(self):
        """Stop the VirtualSpice backend gracefully (a reused server is left alone)."""
        if self.process and self.process.poll() is None:
            logger.info("Stopping VirtualSpice (pid=%d)...", self.process.pid)
            self.process.send_signal(signal.SIGTERM)
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                logger.warning("VirtualSpice did not stop gracefully, killing...")
                self.process.kill()
                self.process.wait()
            self.process = None

    def is_running(self) -> bool:
        """Check if the process is running."""
        if self.process is None:
            return False
        return self.process.poll() is None

    def health_check(self) -> bool:
        """Check if VirtualSpice is responding."""
        import urllib.error
        import urllib.request

        try:
            req = urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/system/info", timeout=2)
            return req.status == 200
        except (urllib.error.URLError, OSError, TimeoutError):
            return False
