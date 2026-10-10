"""
Live guest-RAM capture via QEMU's ``dump-guest-memory`` QMP command, for
ingestion into memory-forensics tooling (e.g. Volatility3).

Issued through the same libvirt-passthrough QMP transport already used for
runtime GUI automation (``QEMUVM._send_qmp_command`` / ``send_qmp_screenshot``
in ``vm.py``) -- not a second raw QMP socket like ``qmp_internal_snapshot.py``
opens, since that one exists only because internal-snapshot work needs the
``-qmp`` unix socket libvirt doesn't already own. Here libvirt's own QMP
monitor is available and sufficient.

A multi-GB dump can take tens of seconds to minutes, so the command is issued
with ``detach: true`` (QEMU runs it as a background job) and ``query-dump`` is
polled until it concludes.
"""

import asyncio
import logging
from pathlib import Path

from adare.hypervisor.exceptions import MemoryDumpException

log = logging.getLogger(__name__)

#: Formats memory-forensics tooling (Volatility3) can ingest directly.
SUPPORTED_FORMATS = ('elf',)


async def dump_guest_memory(
        vm,
        dest_path: Path | str,
        fmt: str = 'elf',
        timeout: float = 600.0,
        poll_interval: float = 2.0,
) -> Path:
    """Capture the guest's live RAM to ``dest_path`` via QMP ``dump-guest-memory``.

    Runs against the live guest -- no pause/quiesce beforehand, since
    ``dump-guest-memory`` is designed to run against a running VM and pausing
    first would itself be a forensically-visible side effect.

    Args:
        vm: A ``QEMUVM`` instance (must expose ``_send_qmp_command``).
        dest_path: Destination file path; parent directories are created.
        fmt: Output format, one of :data:`SUPPORTED_FORMATS`.
        timeout: Max seconds to wait for the background dump job to conclude.
        poll_interval: Seconds between ``query-dump`` polls.

    Returns:
        ``dest_path``, for chaining.

    Raises:
        ValueError: If ``fmt`` is not supported.
        MemoryDumpException: If the QMP command is rejected, the dump job
            fails, or it does not conclude within ``timeout``.
    """
    if fmt not in SUPPORTED_FORMATS:
        raise ValueError(f"dump_guest_memory: unsupported format '{fmt}', expected one of {SUPPORTED_FORMATS}")

    dest_path = Path(dest_path)
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    command = {
        "execute": "dump-guest-memory",
        "arguments": {
            "protocol": f"file:{dest_path}",
            "detach": True,
            "format": fmt,
        },
    }
    log.info(f"Starting guest memory dump ({fmt}) to {dest_path}")
    response = await vm._send_qmp_command(command)
    if 'error' in response:
        raise MemoryDumpException(
            str(dest_path), 'dump-guest-memory', response['error'].get('desc', str(response['error']))
        )

    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    status = None
    while True:
        status_response = await vm._send_qmp_command({"execute": "query-dump"})
        if 'error' in status_response:
            raise MemoryDumpException(
                str(dest_path), 'query-dump', status_response['error'].get('desc', str(status_response['error']))
            )

        status = status_response.get('return', {}).get('status')
        if status == 'completed':
            log.info(f"Guest memory dump completed: {dest_path}")
            return dest_path
        if status == 'failed':
            raise MemoryDumpException(str(dest_path), 'dump-guest-memory', 'QEMU reported dump status=failed')

        if loop.time() >= deadline:
            raise MemoryDumpException(
                str(dest_path), 'dump-guest-memory', f'timed out after {timeout}s (last status: {status})'
            )

        await asyncio.sleep(poll_interval)
