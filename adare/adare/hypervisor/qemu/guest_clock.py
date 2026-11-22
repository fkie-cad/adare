"""Read and resynchronise a QEMU guest's clock through libvirt's guest-agent channel.

libvirt owns the guest agent socket (the ``org.qemu.guest_agent.0`` channel), so
QGA commands go through libvirt (``qemuAgentCommand``) instead of the socket.

A RAM snapshot (``virsh restore`` / ``loadvm``) resumes the guest with the wall
clock it had when the snapshot was taken, so it runs behind by however long the
snapshot sat on disk. Everything the guest writes afterwards carries that stale
time until its own time sync (if any) steps the clock mid-session. Setting the
guest clock to the host's right after the restore closes that window; this is
what ``virsh domtime --sync`` and Proxmox's ``set-time-on-resume`` do. libvirt's
``virDomainSetTime`` also issues ``rtc-reset-reinjection`` on x86, so the RTC
interrupts missed while saved are not replayed on top.
"""

import logging
import time
from typing import Any

log = logging.getLogger(__name__)

# The guest agent comes back with the restored RAM, but libvirt can take a moment
# to reconnect to it.
_RESYNC_ATTEMPTS = 10
_RESYNC_RETRY_S = 1.0


class GuestClockError(Exception):
    """The guest agent did not answer a clock command."""


async def agent_command(vm: Any, execute: str, timeout: int = 2) -> Any:
    """Run one argument-less guest-agent command through libvirt and return its ``return``."""
    response = await vm._send_qga_command_via_libvirt({'execute': execute}, timeout=timeout)
    if 'error' in response:
        raise GuestClockError(f"{execute}: {response['error'].get('desc', response['error'])}")
    return response['return']


async def read_guest_time(vm: Any) -> float:
    """The guest's wall clock (``guest-get-time``) as seconds since the epoch (UTC)."""
    return int(await agent_command(vm, 'guest-get-time')) / 1e9


async def read_guest_utc_offset(vm: Any) -> str:
    """The guest's current UTC offset (``guest-get-timezone``) as '+HH:MM'."""
    seconds = int((await agent_command(vm, 'guest-get-timezone'))['offset'])
    sign = '-' if seconds < 0 else '+'
    hours, minutes = divmod(abs(seconds) // 60, 60)
    return f'{sign}{hours:02d}:{minutes:02d}'


def resync_guest_clock(vm: Any) -> bool:
    """Set the guest clock to the host's UTC time after a restore. Best effort: never raises.

    Returns:
        True if the guest clock was set.
    """
    import libvirt

    from adare.hypervisor.exceptions import HypervisorException

    for attempt in range(1, _RESYNC_ATTEMPTS + 1):
        try:
            domain = vm._ensure_libvirt_domain()
            behind = time.time() - _stale_guest_time(domain)
            now = time.time()
            try:
                domain.setTime({'seconds': int(now), 'nseconds': int((now % 1) * 1e9)})
            except libvirt.libvirtError as e:
                # libvirt sets the time first, then resets RTC reinjection, which only x86
                # machines have; on others (aarch64 virt) the time is set and this step fails.
                if 'rtc-reset-reinjection' not in str(e):
                    raise
            log.info(f"Guest clock resynced after restore (it was {behind:+.3f}s behind the host)")
            return True
        except (libvirt.libvirtError, HypervisorException, KeyError, ValueError) as e:
            if attempt == _RESYNC_ATTEMPTS:
                log.warning(f"Guest clock not resynced after restore; it may run behind ({e})")
                return False
            time.sleep(_RESYNC_RETRY_S)
    return False


def _stale_guest_time(domain: Any) -> float:
    """The guest wall clock right after the restore, before it is corrected (seconds since the epoch)."""
    import json

    import libvirt_qemu

    reply = libvirt_qemu.qemuAgentCommand(domain, json.dumps({'execute': 'guest-get-time'}), 5, 0)
    return int(json.loads(reply)['return']) / 1e9
