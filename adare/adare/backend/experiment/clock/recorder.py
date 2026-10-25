"""Record the guest clock around every playbook action.

Artifacts carry the guest's clock, so a run's timestamps are only as good as
that clock. The recorder samples it before and after each action and writes
one JSON line per sample to ``clock.jsonl`` in the run directory:

- the guest-host offset (with its uncertainty) shows how far the guest clock
  was from real time, and every step of it (NTP, a restore) is flagged as a jump;
- the guest times before and after an action bound when the action's effects
  could have been written (see ``!timestamp {after: ..., before: ...}``);
- the guest's timezone, refreshed before each test, is what tests use to read
  artifacts that store local time without an offset.

Probing never fails an action: a probe that cannot reach the guest is counted
and logged, and the run continues.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

from adare.backend.experiment.clock.samples import ClockSample, ClockSummary
from adare.backend.experiment.websocket_client import WebSocketTimeoutError
from adare.hypervisor.qemu.guest_clock import GuestClockError, read_guest_time, read_guest_utc_offset

log = logging.getLogger(__name__)

CLOCK_LOG = 'clock.jsonl'
CLOCK_SUMMARY = 'clock_summary.json'

# execution_context key tests read the guest timezone from (see test_loader).
GUEST_UTC_OFFSET_KEY = '_adare_guest_utc_offset'

_PROBE_ERRORS = (
    GuestClockError,
    OSError,
    asyncio.TimeoutError,
    WebSocketTimeoutError,
    RuntimeError,
    KeyError,
    TypeError,
)


class ClockRecorder:
    """Samples the guest clock of each machine and keeps the run's clock record."""

    def __init__(self, run_directory: Path | None, execution_context: dict[str, Any], enabled: bool = True):
        self.enabled = enabled
        self.execution_context = execution_context
        self.log_path = run_directory / CLOCK_LOG if run_directory else None
        self.summary_path = run_directory / CLOCK_SUMMARY if run_directory else None
        self._previous: dict[str | None, ClockSample] = {}
        self._summaries: dict[str | None, ClockSummary] = {}
        self._sequence = 0

    async def probe(
        self,
        phase: str,
        action_type: str,
        description: str,
        machine: str | None,
        client: Any,
        vm: Any,
        with_timezone: bool = False,
    ) -> ClockSample | None:
        """Sample one machine's guest clock and log it. Returns None if the guest was unreachable."""
        if not self.enabled:
            return None
        summary = self._summaries.setdefault(machine, ClockSummary())
        try:
            sample = await _read_guest_clock(client, vm, with_timezone)
            reason = 'no guest agent socket and no connected in-guest agent'
        except _PROBE_ERRORS as e:
            sample, reason = None, f"{type(e).__name__}: {e}"
        if sample is None:
            summary.failed_probes += 1
            # The first failure says why; later ones would repeat it for every action.
            level = logging.WARNING if summary.failed_probes == 1 else logging.DEBUG
            log.log(level, f"Guest clock probe {phase} {action_type} failed ({reason})")
            return None

        self._sequence += 1
        label = f"{self._sequence}:{phase}:{action_type}"
        jump = summary.add(sample, self._previous.get(machine), label)
        if jump:
            log.warning(
                f"Guest clock jumped by {summary.jumps[-1]['step']:+.3f}s around {action_type} "
                f"({description or 'no description'}); timestamps across this point are not comparable"
            )
        self._previous[machine] = sample
        if sample.guest_utc_offset:
            self.execution_context[GUEST_UTC_OFFSET_KEY] = sample.guest_utc_offset

        self._append(
            {
                'seq': self._sequence,
                'phase': phase,
                'action': action_type,
                'description': description,
                'machine': machine,
                'jump': jump,
                **sample.to_dict(),
            }
        )
        return sample

    def write_summary(self) -> dict[str | None, dict]:
        """Write and return the per-machine clock summary (called once at the end of a run)."""
        summaries = {machine: summary.to_dict() for machine, summary in self._summaries.items()}
        if not self.enabled or not self.summary_path or not summaries:
            return summaries
        payload = {(machine or 'default'): data for machine, data in summaries.items()}
        try:
            self.summary_path.write_text(json.dumps(payload, indent=2))
        except OSError as e:
            log.warning(f"Could not write clock summary: {e}")
        for machine, data in payload.items():
            state = 'stable' if data['stable'] else f"UNSTABLE ({len(data['jumps'])} jump(s))"
            log.info(
                f"Guest clock [{machine}]: {state}, offset {data['min_offset']}..{data['max_offset']}s "
                f"over {data['samples']} samples, {data['failed_probes']} failed probes, "
                f"timezone(s) {data['guest_utc_offsets'] or 'unknown'}"
            )
        return summaries

    def _append(self, record: dict) -> None:
        if not self.log_path:
            return
        try:
            with self.log_path.open('a') as f:
                f.write(json.dumps(record) + '\n')
        except OSError as e:
            log.warning(f"Could not write clock log: {e}")


async def _read_guest_clock(client: Any, vm: Any, with_timezone: bool) -> ClockSample | None:
    """Read the guest clock via the QEMU guest agent (through libvirt) or the in-guest agent.

    QGA is preferred: it is cheap, works without the in-guest agent (host mode)
    and leaves no agent log events. The in-guest agent is the fallback when there
    is no QGA (VirtualBox).
    """
    if hasattr(vm, '_send_qga_command_via_libvirt'):
        host_before = time.time()
        guest = await read_guest_time(vm)
        host_after = time.time()
        utc_offset = None
        if with_timezone:
            try:
                utc_offset = await read_guest_utc_offset(vm)
            except (GuestClockError, KeyError, ValueError) as e:  # older qemu-ga lacks guest-get-timezone
                log.debug(f"Guest timezone unavailable via QGA: {e}")
        return ClockSample(host_before, guest, host_after, source='qga', guest_utc_offset=utc_offset)

    if client is None or not getattr(client, 'connected', False):
        return None
    host_before = time.time()
    result = await client.get_timestamp(use_local=with_timezone, timeout=5.0)
    host_after = time.time()
    utc_offset = result.get('timezone') if with_timezone else None
    if utc_offset == 'UTC':
        utc_offset = '+00:00'
    return ClockSample(host_before, float(result['timestamp']), host_after, source='agent', guest_utc_offset=utc_offset)
