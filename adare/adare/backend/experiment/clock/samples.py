"""Guest clock samples: offset against the host and jump detection.

A sample brackets one read of the guest's wall clock between two reads of the
host's wall clock. The guest read happened somewhere inside [host_before,
host_after], so the guest-host offset is known up to half that round trip.
All values are seconds since the Unix epoch (UTC); timezones never enter here.
"""

from __future__ import annotations

import attrs

# A change in offset larger than this (beyond the two samples' uncertainty) is a
# step of the guest clock: NTP stepping it, a snapshot restore, a manual change.
# Slewing (at most 0.5 ms/s) and the round-trip noise stay well below it.
JUMP_THRESHOLD_S = 1.0


@attrs.frozen
class ClockSample:
    """One guest clock read, bracketed by two host clock reads."""

    host_before: float
    guest: float
    host_after: float
    source: str  # 'qga' or 'agent': where the guest time came from
    guest_utc_offset: str | None = None  # guest timezone at that moment, e.g. '+02:00'

    @property
    def offset(self) -> float:
        """Guest clock minus host clock, in seconds (positive: guest is ahead)."""
        return self.guest - (self.host_before + self.host_after) / 2

    @property
    def uncertainty(self) -> float:
        """Half the round trip: the offset is exact up to this many seconds."""
        return (self.host_after - self.host_before) / 2

    def to_dict(self) -> dict:
        return {
            'host_before': self.host_before,
            'guest': self.guest,
            'host_after': self.host_after,
            'offset': round(self.offset, 6),
            'uncertainty': round(self.uncertainty, 6),
            'source': self.source,
            'guest_utc_offset': self.guest_utc_offset,
        }


def is_jump(previous: ClockSample, current: ClockSample, threshold: float = JUMP_THRESHOLD_S) -> bool:
    """True if the guest clock stepped between two samples."""
    slack = threshold + previous.uncertainty + current.uncertainty
    return abs(current.offset - previous.offset) > slack


@attrs.define
class ClockSummary:
    """What a run's clock did, for the run's records."""

    samples: int = 0
    failed_probes: int = 0
    min_offset: float | None = None
    max_offset: float | None = None
    max_uncertainty: float = 0.0
    jumps: list[dict] = attrs.Factory(list)
    utc_offsets: list[str] = attrs.Factory(list)  # distinct guest timezones seen, in order

    def add(self, sample: ClockSample, previous: ClockSample | None, label: str) -> bool:
        """Account for a sample; return True if it is a jump from the previous one."""
        self.samples += 1
        offset = sample.offset
        self.min_offset = offset if self.min_offset is None else min(self.min_offset, offset)
        self.max_offset = offset if self.max_offset is None else max(self.max_offset, offset)
        self.max_uncertainty = max(self.max_uncertainty, sample.uncertainty)
        if sample.guest_utc_offset and sample.guest_utc_offset not in self.utc_offsets:
            self.utc_offsets.append(sample.guest_utc_offset)
        if previous is not None and is_jump(previous, sample):
            self.jumps.append({'at': label, 'step': round(offset - previous.offset, 6), 'host_time': sample.host_after})
            return True
        return False

    @property
    def stable(self) -> bool:
        """No jumps and no timezone change: guest timestamps are comparable across the run."""
        return not self.jumps and len(self.utc_offsets) <= 1

    def to_dict(self) -> dict:
        return {
            'stable': self.stable,
            'samples': self.samples,
            'failed_probes': self.failed_probes,
            'min_offset': self.min_offset,
            'max_offset': self.max_offset,
            'max_uncertainty': self.max_uncertainty,
            'jumps': self.jumps,
            'guest_utc_offsets': self.utc_offsets,
        }
