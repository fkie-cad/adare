"""QEMU process monitoring for VM installations."""

import contextlib
import logging
import subprocess
import time

from rich.status import Status

from adare.console import console

log = logging.getLogger(__name__)


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
