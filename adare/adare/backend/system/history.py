"""Host usage history: a sample per minute while the web server runs, kept for 30 days."""

import asyncio
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import SQLAlchemyError

from adare.backend.system.host import HostSnapshot, host_snapshot

log = logging.getLogger(__name__)

SAMPLE_INTERVAL_SECONDS = 60
RETENTION = timedelta(days=30)
MAX_POINTS = 360


@dataclass
class HistoryPoint:
    taken_at: datetime
    cpu_percent: float
    memory_used_bytes: int
    memory_total_bytes: int
    disk_used_bytes: int
    disk_total_bytes: int
    vm_count: int
    vm_rss_bytes: int


def record_sample(snapshot: HostSnapshot | None = None) -> None:
    """Store one host sample and drop the ones past retention."""
    from adare.database.api.system import SystemDbApi

    snapshot = snapshot or host_snapshot()
    disk = snapshot.disks[0] if snapshot.disks else None
    now = datetime.now(UTC).replace(tzinfo=None)
    with SystemDbApi() as api:
        api.add_sample(
            taken_at=now,
            cpu_percent=snapshot.cpu_percent,
            load_1m=snapshot.load_average[0] if snapshot.load_average else None,
            memory_total_bytes=snapshot.memory_total_bytes,
            memory_used_bytes=snapshot.memory_used_bytes,
            disk_total_bytes=disk.total_bytes if disk else 0,
            disk_used_bytes=disk.used_bytes if disk else 0,
            vm_count=len(snapshot.vms),
            vm_rss_bytes=snapshot.vm_rss_bytes,
            vm_cpu_percent=snapshot.vm_cpu_percent,
        )
        api.delete_samples_before(now - RETENTION)


def load_history(hours: float) -> list[HistoryPoint]:
    """Samples of the last ``hours``, averaged into at most :data:`MAX_POINTS` buckets (peaks kept for VMs)."""
    from adare.database.api.system import SystemDbApi

    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(hours=hours)
    with SystemDbApi() as api:
        rows = [
            HistoryPoint(
                taken_at=r.taken_at,
                cpu_percent=r.cpu_percent,
                memory_used_bytes=r.memory_used_bytes,
                memory_total_bytes=r.memory_total_bytes,
                disk_used_bytes=r.disk_used_bytes,
                disk_total_bytes=r.disk_total_bytes,
                vm_count=r.vm_count,
                vm_rss_bytes=r.vm_rss_bytes,
            )
            for r in api.samples_since(since)
        ]
    return downsample(rows, MAX_POINTS)


def downsample(points: list[HistoryPoint], max_points: int) -> list[HistoryPoint]:
    if len(points) <= max_points:
        return points
    size = -(-len(points) // max_points)  # ceil
    buckets = [points[i : i + size] for i in range(0, len(points), size)]
    return [
        HistoryPoint(
            taken_at=bucket[-1].taken_at,
            cpu_percent=sum(p.cpu_percent for p in bucket) / len(bucket),
            memory_used_bytes=sum(p.memory_used_bytes for p in bucket) // len(bucket),
            memory_total_bytes=bucket[-1].memory_total_bytes,
            disk_used_bytes=bucket[-1].disk_used_bytes,
            disk_total_bytes=bucket[-1].disk_total_bytes,
            vm_count=max(p.vm_count for p in bucket),
            vm_rss_bytes=max(p.vm_rss_bytes for p in bucket),
        )
        for bucket in buckets
    ]


async def sample_forever(interval: float = SAMPLE_INTERVAL_SECONDS) -> None:
    """Background task for the web server; a failed sample is logged and the next one tried."""
    while True:
        try:
            await asyncio.to_thread(record_sample)
        except (SQLAlchemyError, OSError) as e:
            log.warning(f'Resource sample failed: {e}')
        await asyncio.sleep(interval)
