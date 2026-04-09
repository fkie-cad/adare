"""Process manager for VirtualSpice backend."""

import subprocess
import shutil
import signal
import time
import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class VirtualSpiceManager:
    """Manages the VirtualSpice Rust backend as a subprocess."""

    def __init__(self, port: int = 8081, binary_path: str | None = None):
        self.port = port
        self.binary_path = binary_path or self._find_binary()
        self.process: subprocess.Popen | None = None

    def _find_binary(self) -> str | None:
        """Find the VirtualSpice binary."""
        # Check environment variable first
        env_path = os.environ.get("VIRTUALSPICE_BINARY")
        if env_path and os.path.isfile(env_path):
            return env_path

        # Check common locations
        candidates = [
            Path.home() / ".local" / "bin" / "virtualspice",
            Path("/usr/local/bin/virtualspice"),
            # Development build location
            Path.home()
            / "Documents"
            / "Projects"
            / "SpiceMacOS"
            / "backend"
            / "target"
            / "release"
            / "virtualspice",
            Path.home()
            / "Documents"
            / "Projects"
            / "SpiceMacOS"
            / "backend"
            / "target"
            / "debug"
            / "virtualspice",
        ]

        for path in candidates:
            if path.is_file():
                return str(path)

        # Try PATH
        found = shutil.which("virtualspice")
        return found

    @property
    def available(self) -> bool:
        """Whether the VirtualSpice binary was found."""
        return self.binary_path is not None

    def start(self) -> bool:
        """Start the VirtualSpice backend. Returns True if started successfully."""
        if self.process and self.process.poll() is None:
            return True  # Already running

        if not self.binary_path:
            return False

        try:
            self.process = subprocess.Popen(
                [self.binary_path, "--port", str(self.port)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            # Give it a moment to start
            time.sleep(0.5)
            if self.process.poll() is not None:
                logger.warning("VirtualSpice process exited immediately after start")
                return False
            logger.info(
                "VirtualSpice started on port %d (pid=%d)",
                self.port,
                self.process.pid,
            )
            return True
        except FileNotFoundError:
            logger.warning("VirtualSpice binary not found at %s", self.binary_path)
            return False
        except PermissionError:
            logger.warning(
                "Permission denied when starting VirtualSpice at %s", self.binary_path
            )
            return False

    def stop(self):
        """Stop the VirtualSpice backend gracefully."""
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
        import urllib.request
        import urllib.error

        try:
            req = urllib.request.urlopen(
                f"http://127.0.0.1:{self.port}/api/system/info", timeout=2
            )
            return req.status == 200
        except (urllib.error.URLError, OSError, TimeoutError):
            return False
