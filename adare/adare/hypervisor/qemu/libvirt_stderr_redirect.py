"""Context manager for redirecting libvirt stderr to experiment log.

Libvirt's C library writes error messages directly to stderr, bypassing
Python's logging system. This module provides a context manager that
redirects stderr at the file descriptor level to capture these messages
in the experiment log instead of polluting console output.
"""

import contextlib

# configure logging
import logging
import os
import sys
import threading
from pathlib import Path

log = logging.getLogger(__name__)


def get_experiment_log_file() -> str | None:
    """Get the path to the current experiment log file.

    Returns:
        Path to experiment log file or None if not available
    """
    from adare.logger.logger import get_current_logfile
    return get_current_logfile()


class LibvirtStderrRedirect(contextlib.AbstractContextManager):
    """Thread-safe context manager for redirecting stderr to log file.

    This context manager redirects stderr at the file descriptor level
    (fd=2) to capture output from C libraries like libvirt that bypass
    Python's logging system.

    Example:
        >>> log_file = get_experiment_log_file()
        >>> with LibvirtStderrRedirect(log_file=log_file):
        ...     # libvirt warnings redirected to log file
        ...     libvirt_qemu.qemuAgentCommand(...)

    Args:
        log_file: Path to log file for capturing stderr. If None, uses /dev/null
        suppress_console: If True, suppresses stderr from console (default: True)
    """

    # Class-level lock for thread safety
    _redirect_lock = threading.Lock()

    def __init__(self, log_file: str | None = None, suppress_console: bool = True):
        """Initialize stderr redirect context manager.

        Args:
            log_file: Path to log file for stderr output. If None, uses /dev/null
            suppress_console: If True, stderr is redirected away from console
        """
        self.log_file = log_file
        self.suppress_console = suppress_console
        self._saved_stderr_fd: int | None = None
        self._redirect_file = None
        self._lock_acquired = False

    def __enter__(self):
        """Enter context: redirect stderr to log file or /dev/null.

        Returns:
            self for context manager protocol
        """
        try:
            # Acquire lock to prevent concurrent stderr redirections
            self._redirect_lock.acquire()
            self._lock_acquired = True

            # Save original stderr file descriptor
            self._saved_stderr_fd = os.dup(2)  # fd 2 = stderr

            # Determine redirect target
            if self.log_file and Path(self.log_file).exists():
                redirect_target = self.log_file
            else:
                redirect_target = "/dev/null"

            # Open redirect target for appending
            self._redirect_file = open(redirect_target, 'a', encoding='utf-8')

            # Write start marker if redirecting to log file
            if redirect_target != "/dev/null":
                self._redirect_file.write("[LIBVIRT START]")
                self._redirect_file.flush()

            # Redirect stderr at file descriptor level
            # This captures C library output that bypasses sys.stderr
            os.dup2(self._redirect_file.fileno(), 2)

            return self

        except OSError as e:
            log.warning(f"Failed to redirect stderr: {e}")
            # Clean up on failure
            self._cleanup()
            raise

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context: restore original stderr.

        Args:
            exc_type: Exception type if raised
            exc_val: Exception value if raised
            exc_tb: Exception traceback if raised

        Returns:
            False to propagate exceptions
        """
        try:
            # Flush any pending output
            if self._redirect_file and not self._redirect_file.closed:
                sys.stderr.flush()

                # Write end marker if we wrote to a real log file
                if self.log_file and Path(self.log_file).exists():
                    try:
                        self._redirect_file.write("[LIBVIRT END]")
                        self._redirect_file.flush()
                    except (OSError, ValueError):
                        # File might be closed or invalid, ignore
                        pass

            # Restore original stderr
            if self._saved_stderr_fd is not None:
                try:
                    os.dup2(self._saved_stderr_fd, 2)
                except OSError as e:
                    log.warning(f"Failed to restore stderr: {e}")

        finally:
            # Always cleanup resources
            self._cleanup()

        # Don't suppress exceptions
        return False

    def _cleanup(self):
        """Clean up file descriptors and release lock."""
        try:
            # Close saved stderr file descriptor
            if self._saved_stderr_fd is not None:
                try:
                    os.close(self._saved_stderr_fd)
                except OSError:
                    pass  # Already closed
                self._saved_stderr_fd = None

            # Close redirect file
            if self._redirect_file and not self._redirect_file.closed:
                try:
                    self._redirect_file.close()
                except OSError:
                    pass  # Already closed
                self._redirect_file = None
        finally:
            # Always release lock
            if self._lock_acquired:
                self._redirect_lock.release()
                self._lock_acquired = False
