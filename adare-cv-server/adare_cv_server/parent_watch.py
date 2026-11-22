"""Exit the CV server when the process that started it is gone.

ADARE starts the server detached (its own session), so it survives a crashed or
killed run and keeps its port and its OCR models (up to ~1.6 GB) in memory.
``--exit-with-parent`` makes it watch its parent instead:

* POSIX: an orphan is re-parented (to init or a subreaper), so ``getppid()``
  changes. Comparing against the pid seen at startup cannot be fooled by pid reuse.
* Windows: the parent pid never changes, so a handle to the parent is opened at
  startup and waited on; the handle keeps the process object, so reuse is no issue.
"""

import ctypes
import logging
import os
import threading
import time
from collections.abc import Callable

log = logging.getLogger(__name__)

POLL_SECONDS = 2.0


def _wait_for_parent_posix(parent: int, poll_seconds: float) -> None:
    while os.getppid() == parent:
        time.sleep(poll_seconds)


def _wait_for_parent_windows(parent: int) -> None:
    synchronize = 0x00100000
    infinite = 0xFFFFFFFF
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    handle = kernel32.OpenProcess(synchronize, False, parent)
    if not handle:
        return  # already gone
    try:
        kernel32.WaitForSingleObject(handle, infinite)
    finally:
        kernel32.CloseHandle(handle)


def exit_when_parent_dies(
    poll_seconds: float = POLL_SECONDS, on_exit: Callable[[], None] = lambda: os._exit(0)
) -> threading.Thread:
    """Start a daemon thread that calls ``on_exit`` (default: end the process) once the parent is gone."""
    parent = os.getppid()

    def watch() -> None:
        if os.name == 'nt':
            _wait_for_parent_windows(parent)
        else:
            _wait_for_parent_posix(parent, poll_seconds)
        log.info(f"Parent process {parent} is gone; shutting down the CV server")
        on_exit()

    thread = threading.Thread(target=watch, name='parent-watch', daemon=True)
    thread.start()
    log.info(f"Watching parent process {parent}: the CV server exits when it does")
    return thread
