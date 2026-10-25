"""Live host readings: CPU, memory, the disk holding the ADARE state, QEMU processes.

CPU percentages need two readings to mean anything (psutil reports the load
since the previous call), so the process objects are cached between calls and a
process's first reading is reported as 0 until the next poll.
"""

import logging
import os
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import psutil

from adare.config.configdirectory import APPDATA_DIR, QEMU_STATE_DIR

log = logging.getLogger(__name__)

_QEMU_PREFIX = 'qemu-system'
_PRIME_SECONDS = 0.5

# pid -> Process, so cpu_percent() measures since the last poll
_process_cache: dict[int, psutil.Process] = {}
_cache_lock = threading.Lock()
_cpu_last: tuple[float, tuple[float, float], float] | None = None  # (monotonic time, (busy, total), percent)
_CPU_MIN_INTERVAL = 1.0


@dataclass
class DiskUsage:
    path: str
    total_bytes: int
    used_bytes: int
    free_bytes: int

    @property
    def percent(self) -> float:
        return 100.0 * self.used_bytes / self.total_bytes if self.total_bytes else 0.0


@dataclass
class VmProcess:
    """A running QEMU process, named after its VM instance / domain."""

    pid: int
    name: str
    rss_bytes: int
    cpu_percent: float  # in cores x 100, like `top`
    started_at: float  # epoch seconds
    memory_mb: int | None = None  # guest RAM from `-m`
    cpus: int | None = None  # guest vCPUs from `-smp`


@dataclass
class HostSnapshot:
    cpu_count: int
    cpu_percent: float  # whole host, 0-100
    load_average: tuple[float, float, float] | None
    memory_total_bytes: int
    memory_available_bytes: int
    memory_used_bytes: int
    swap_total_bytes: int
    swap_used_bytes: int
    disks: list[DiskUsage] = field(default_factory=list)
    vms: list[VmProcess] = field(default_factory=list)

    @property
    def vm_rss_bytes(self) -> int:
        return sum(vm.rss_bytes for vm in self.vms)

    @property
    def vm_cpu_percent(self) -> float:
        return sum(vm.cpu_percent for vm in self.vms)


def state_directories() -> list[Path]:
    """The directories ADARE keeps its disks in (they may sit on different filesystems)."""
    return [APPDATA_DIR, QEMU_STATE_DIR]


def disk_usage() -> list[DiskUsage]:
    """Usage of each distinct filesystem holding ADARE state, keyed by the first path on it."""
    seen: set[int] = set()
    disks: list[DiskUsage] = []
    for path in state_directories():
        probe = path if path.exists() else path.parent
        try:
            device = probe.stat().st_dev
            usage = shutil.disk_usage(probe)
        except OSError as e:
            log.debug(f'disk usage of {probe} unavailable: {e}')
            continue
        if device in seen:
            continue
        seen.add(device)
        disks.append(DiskUsage(str(path), usage.total, usage.used, usage.free))
    return disks


def _parse_qemu_cmdline(cmdline: list[str]) -> tuple[str | None, int | None, int | None]:
    """(name, memory MB, vCPUs) from a QEMU command line."""
    name = memory_mb = cpus = None
    disk = None
    for flag, value in zip(cmdline, cmdline[1:], strict=False):
        if flag in ('-drive', '-hda') and disk is None:
            disk = _disk_name(value)
        elif flag == '-name':
            # libvirt: "guest=<domain>,debug-threads=on"; direct QEMU: "<name>"
            first = value.split(',')[0]
            name = first.removeprefix('guest=')
        elif flag == '-m':
            memory_mb = _parse_memory(value)
        elif flag == '-smp':
            first = value.split(',')[0]
            if first.isdigit():
                cpus = int(first)
            else:
                for part in value.split(','):
                    if part.startswith('cpus='):
                        cpus = int(part.removeprefix('cpus='))
    return name or disk, memory_mb, cpus


def _disk_name(drive: str) -> str | None:
    """A name for an unnamed QEMU (e.g. an image build) from its qcow2 disk.

    Build scratch disks sit in a temp dir named after the job ("adare-extend-xyz");
    otherwise the disk's file name says what it is.
    """
    for part in drive.split(','):
        value = part.removeprefix('file=')
        if value.endswith('.qcow2'):
            path = Path(value)
            return path.parent.name if path.parent.name.startswith('adare-') else path.stem
    return None


def _parse_memory(value: str) -> int | None:
    """QEMU `-m` value ("4096", "4G", "size=4194304k,...") in MB."""
    size = value.split(',')[0].removeprefix('size=')
    units = {'k': 1 / 1024, 'm': 1, 'g': 1024, 't': 1024 * 1024}
    suffix = size[-1:].lower()
    try:
        if suffix in units:
            return int(float(size[:-1]) * units[suffix])
        return int(size)
    except ValueError:
        return None


def _cached_process(pid: int) -> tuple[psutil.Process, bool]:
    """The cached process and whether it was just added (its CPU reading still needs priming)."""
    with _cache_lock:
        process = _process_cache.get(pid)
        if process is not None:
            return process, False
        process = psutil.Process(pid)
        process.cpu_percent(None)  # prime; the first reading is meaningless
        _process_cache[pid] = process
        return process, True


def _forget_dead(alive: set[int]) -> None:
    with _cache_lock:
        for pid in list(_process_cache):
            if pid not in alive:
                del _process_cache[pid]


def vm_processes() -> list[VmProcess]:
    """Every running QEMU system emulator on the host.

    Processes seen for the first time are measured over a short pause, so a
    one-shot call (the CLI) still gets a CPU reading.
    """
    processes: list[psutil.Process] = []
    primed = False
    for proc in psutil.process_iter(['pid', 'name']):
        if not (proc.info['name'] or '').startswith(_QEMU_PREFIX):
            continue
        try:
            process, new = _cached_process(proc.info['pid'])
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:
            log.debug(f'skipping QEMU process {proc.info["pid"]}: {e}')
            continue
        processes.append(process)
        primed = primed or new
    if primed:
        time.sleep(_PRIME_SECONDS)

    found: list[VmProcess] = []
    alive: set[int] = set()
    for process in processes:
        try:
            with process.oneshot():
                name, memory_mb, cpus = _parse_qemu_cmdline(process.cmdline())
                found.append(
                    VmProcess(
                        pid=process.pid,
                        name=name or f'qemu-{process.pid}',
                        rss_bytes=process.memory_info().rss,
                        cpu_percent=process.cpu_percent(None),
                        started_at=process.create_time(),
                        memory_mb=memory_mb,
                        cpus=cpus,
                    )
                )
            alive.add(process.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess) as e:
            log.debug(f'skipping QEMU process {process.pid}: {e}')
    _forget_dead(alive)
    return found


def _busy_and_total(times) -> tuple[float, float]:
    """(busy, total) seconds from psutil.cpu_times(); guest time is already in user/nice."""
    total = sum(times) - getattr(times, 'guest', 0.0) - getattr(times, 'guest_nice', 0.0)
    idle = times.idle + getattr(times, 'iowait', 0.0)
    return total - idle, total


def host_cpu_percent() -> float:
    """Host CPU load since the previous call, from our own cpu_times() deltas.

    psutil.cpu_percent(None) keeps its previous reading per *thread*, so every
    fresh web-server worker thread would read 0.0. A call within
    :data:`_CPU_MIN_INTERVAL` of the last one gets that last reading again; the
    very first call measures over a short pause.
    """
    global _cpu_last
    with _cache_lock:
        now = time.monotonic()
        if _cpu_last is not None and now - _cpu_last[0] < _CPU_MIN_INTERVAL:
            return _cpu_last[2]
        if _cpu_last is None:
            start = _busy_and_total(psutil.cpu_times())
            time.sleep(_PRIME_SECONDS)
        else:
            start = _cpu_last[1]
        current = _busy_and_total(psutil.cpu_times())
        busy, total = current[0] - start[0], current[1] - start[1]
        percent = max(0.0, min(100.0, 100.0 * busy / total)) if total > 0 else 0.0
        _cpu_last = (now, current, percent)
        return percent


def host_snapshot() -> HostSnapshot:
    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    try:
        load = os.getloadavg()
    except OSError:
        load = None
    return HostSnapshot(
        cpu_count=psutil.cpu_count(logical=True) or 1,
        cpu_percent=host_cpu_percent(),
        load_average=load,
        memory_total_bytes=memory.total,
        memory_available_bytes=memory.available,
        memory_used_bytes=memory.total - memory.available,
        swap_total_bytes=swap.total,
        swap_used_bytes=swap.used,
        disks=disk_usage(),
        vms=vm_processes(),
    )
