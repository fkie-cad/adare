"""How many more runs of each environment the host can take right now.

For every environment the per-run need is taken from measured runs
(:class:`RunResourceUsage`) when there are any, else from the configured VM
size: RAM 8 GiB for Windows / 4 GiB otherwise (the run defaults), vCPUs from the
run config, disk a flat allowance for the run's overlay and artifacts. A run
then fits as often as the scarcest of RAM, CPU and disk allows after a reserve
for the host itself. RAM and disk are hard limits; CPU can be overcommitted, so
it only limits once the busy cores run out: the measured average, or until a
run was measured, half the configured vCPUs (a GUI-automation guest idles
between actions).
"""

import logging
import math
from dataclasses import dataclass

from adare.backend.system.host import HostSnapshot

log = logging.getLogger(__name__)

GIB = 1024**3

WINDOWS_MEMORY_MB = 8192
DEFAULT_MEMORY_MB = 4096
DEFAULT_VCPUS = 4
CONFIGURED_CPU_SHARE = 0.5  # busy fraction of the vCPUs assumed before a run is measured
QEMU_OVERHEAD_BYTES = 512 * 1024**2  # QEMU's own allocations beyond guest RAM
DEFAULT_RUN_DISK_BYTES = 8 * GIB  # overlay growth + artifacts of a typical run

HOST_MEMORY_RESERVE = 0.10  # of total RAM, at least MIN_MEMORY_RESERVE
MIN_MEMORY_RESERVE = 4 * GIB
DISK_RESERVE = 0.05  # of the filesystem, at least MIN_DISK_RESERVE
MIN_DISK_RESERVE = 20 * GIB
MEASURED_RUNS = 10  # how many recent runs the measured need is taken from


@dataclass
class RunNeed:
    """What one run of an environment needs."""

    memory_bytes: int
    cpu_cores: float  # busy cores, not vCPUs
    disk_bytes: int
    source: str  # 'measured' | 'configured'
    measured_runs: int = 0


@dataclass
class EnvironmentCapacity:
    environment: str
    platform: str | None
    need: RunNeed
    fits: int
    fits_by_memory: int
    fits_by_cpu: int
    fits_by_disk: int
    limited_by: str  # 'memory' | 'cpu' | 'disk'


@dataclass
class HostHeadroom:
    memory_bytes: int  # free for new VMs after the host reserve
    cpu_cores: float
    disk_bytes: int


def headroom(host: HostSnapshot) -> HostHeadroom:
    memory_reserve = max(int(host.memory_total_bytes * HOST_MEMORY_RESERVE), MIN_MEMORY_RESERVE)
    busy_cores = host.cpu_count * host.cpu_percent / 100
    disk = host.disks[-1] if host.disks else None  # the QEMU disk dir is probed last
    disk_free = 0
    if disk is not None:
        disk_reserve = max(int(disk.total_bytes * DISK_RESERVE), MIN_DISK_RESERVE)
        disk_free = disk.free_bytes - disk_reserve
    return HostHeadroom(
        memory_bytes=max(host.memory_available_bytes - memory_reserve, 0),
        cpu_cores=max(host.cpu_count - busy_cores, 0.0),
        disk_bytes=max(disk_free, 0),
    )


def configured_need(platform: str | None, vcpus: int = DEFAULT_VCPUS) -> RunNeed:
    memory_mb = WINDOWS_MEMORY_MB if platform and 'windows' in platform.lower() else DEFAULT_MEMORY_MB
    return RunNeed(
        memory_bytes=memory_mb * 1024**2 + QEMU_OVERHEAD_BYTES,
        cpu_cores=vcpus * CONFIGURED_CPU_SHARE,
        disk_bytes=DEFAULT_RUN_DISK_BYTES,
        source='configured',
    )


def measured_need(usages: list, fallback: RunNeed) -> RunNeed:
    """Need from recent measured runs: the peak RAM and disk seen, the typical busy cores.

    ``usages`` are :class:`RunResourceUsage` rows (or anything with the same fields).
    """
    usages = [u for u in usages if u.samples and u.peak_rss_bytes][:MEASURED_RUNS]
    if not usages:
        return fallback
    disks = [u.disk_bytes for u in usages if u.disk_bytes]
    cpu = sorted(u.avg_cpu_percent for u in usages)[len(usages) // 2] / 100
    return RunNeed(
        memory_bytes=max(u.peak_rss_bytes for u in usages),
        cpu_cores=max(cpu, 0.25),
        disk_bytes=max(disks) if disks else fallback.disk_bytes,
        source='measured',
        measured_runs=len(usages),
    )


def fits(room: HostHeadroom, need: RunNeed) -> tuple[int, int, int]:
    """How many runs fit by (memory, cpu, disk)."""
    by_memory = math.floor(room.memory_bytes / need.memory_bytes) if need.memory_bytes else 0
    by_cpu = math.floor(room.cpu_cores / need.cpu_cores) if need.cpu_cores else 0
    by_disk = math.floor(room.disk_bytes / need.disk_bytes) if need.disk_bytes else 0
    return by_memory, by_cpu, by_disk


def estimate(
    host: HostSnapshot, environments: list[tuple[str, str | None]], usage_by_env: dict
) -> list[EnvironmentCapacity]:
    """Capacity per environment.

    Args:
        environments: (name, platform) of each current environment
        usage_by_env: environment name -> its measured usages, newest first
    """
    room = headroom(host)
    result = []
    for name, platform in environments:
        need = measured_need(usage_by_env.get(name, []), configured_need(platform))
        by_memory, by_cpu, by_disk = fits(room, need)
        limits = {'memory': by_memory, 'disk': by_disk, 'cpu': by_cpu}
        limited_by = min(limits, key=lambda k: limits[k])
        result.append(
            EnvironmentCapacity(
                environment=name,
                platform=platform,
                need=need,
                fits=limits[limited_by],
                fits_by_memory=by_memory,
                fits_by_cpu=by_cpu,
                fits_by_disk=by_disk,
                limited_by=limited_by,
            )
        )
    result.sort(key=lambda c: c.environment)
    return result
