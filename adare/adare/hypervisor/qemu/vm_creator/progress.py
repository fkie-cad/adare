"""QEMU process monitoring for VM installations."""

import contextlib
import logging
import signal
import subprocess
import threading
import time
from collections.abc import Iterator

from rich.status import Status

from adare.console import console

log = logging.getLogger(__name__)

# Signals that mean "shut down": converted into QemuInstallTerminated so the
# cleanup in terminate_qemu_on_exit actually runs. Their default disposition
# kills the interpreter outright, skipping every finally block.
_TERMINATION_SIGNALS = (signal.SIGTERM, signal.SIGHUP)


class QemuInstallTerminated(Exception):
    """A termination signal arrived while a QEMU child was still running."""


def reap_qemu(process: subprocess.Popen, label: str = 'VM installation') -> None:
    """Terminate a QEMU child if it is still alive, escalating to SIGKILL.

    A no-op when the process has already exited, so it is safe to call on the
    success path.
    """
    if process.poll() is not None:
        return
    log.warning('%s: reaping QEMU child (pid %d)', label, process.pid)
    process.terminate()
    try:
        process.wait(timeout=30)
    except subprocess.TimeoutExpired:
        log.warning('%s: QEMU pid %d ignored SIGTERM, sending SIGKILL', label, process.pid)
        process.kill()
        with contextlib.suppress(subprocess.TimeoutExpired):
            process.wait(timeout=10)


@contextlib.contextmanager
def terminate_qemu_on_exit(
    process: subprocess.Popen,
    label: str = 'VM installation',
) -> Iterator[None]:
    """Guarantee a ``Popen``-started QEMU is reaped on *any* exit from the block.

    Nothing in the OS ties QEMU's lifetime to ours, so an interrupted
    ``adare vm create`` used to exit and leave a full installer VM running with
    ``ppid=1``, still appending to its serial install log. Two such orphans once
    wrote to the same log for ~15 hours and made the install failure they were
    supposed to document impossible to read.

    Only ``SIGKILL`` on our own process can still leak the child — there is no
    in-process defence against that.
    """
    previous: list[tuple[signal.Signals, object]] = []

    def _on_signal(signum: int, _frame: object) -> None:
        raise QemuInstallTerminated(
            f'{label} terminated by {signal.Signals(signum).name}'
        )

    # signal.signal() is main-thread only; without it we still reap on exceptions.
    if threading.current_thread() is threading.main_thread():
        for sig in _TERMINATION_SIGNALS:
            with contextlib.suppress(ValueError, OSError):
                previous.append((sig, signal.signal(sig, _on_signal)))

    try:
        yield
    finally:
        for sig, handler in previous:
            with contextlib.suppress(ValueError, OSError):
                signal.signal(sig, handler)
        reap_qemu(process, label)


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
                ) from None

            # Periodic status update
            now = time.monotonic()
            if now - last_status >= status_interval:
                mins = elapsed / 60
                if status is not None:
                    status.update(f'  [cyan]{label}[/cyan] in progress [bold]({mins:.0f} min elapsed)[/bold]')
                else:
                    console.print(f'  [dim]...[/dim] {label} in progress [bold]({mins:.0f} min elapsed)[/bold]')
                last_status = now
