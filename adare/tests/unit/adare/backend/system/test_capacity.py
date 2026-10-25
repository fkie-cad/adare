"""Run capacity: host reserve, configured vs measured need, the limiting resource."""

from types import SimpleNamespace

import pytest

from adare.backend.system import capacity
from adare.backend.system.host import DiskUsage, HostSnapshot

pytestmark = pytest.mark.unit

GIB = 1024**3


def _host(available_gib=64, total_gib=128, cpu_count=16, cpu_percent=0.0, disk_free_gib=500, disk_total_gib=1000):
    return HostSnapshot(
        cpu_count=cpu_count,
        cpu_percent=cpu_percent,
        load_average=None,
        memory_total_bytes=total_gib * GIB,
        memory_available_bytes=available_gib * GIB,
        memory_used_bytes=(total_gib - available_gib) * GIB,
        swap_total_bytes=0,
        swap_used_bytes=0,
        disks=[DiskUsage('/x', disk_total_gib * GIB, (disk_total_gib - disk_free_gib) * GIB, disk_free_gib * GIB)],
    )


def _usage(peak_gib, cpu=50.0, disk_gib=5, samples=10):
    return SimpleNamespace(
        samples=samples, peak_rss_bytes=int(peak_gib * GIB), avg_cpu_percent=cpu, disk_bytes=int(disk_gib * GIB)
    )


def test_headroom_keeps_a_reserve_for_the_host():
    room = capacity.headroom(_host(available_gib=64, total_gib=128, cpu_count=16, cpu_percent=25.0))

    assert room.memory_bytes == 64 * GIB - int(128 * GIB * 0.10)  # 10% of 128 GiB > the 4 GiB minimum
    assert room.cpu_cores == 12.0
    assert room.disk_bytes == 500 * GIB - 50 * GIB  # 5% of 1000 GiB > the 20 GiB minimum


def test_headroom_never_goes_negative():
    room = capacity.headroom(_host(available_gib=2, total_gib=8, disk_free_gib=10, disk_total_gib=100))

    assert room.memory_bytes == 0
    assert room.disk_bytes == 0


def test_configured_need_depends_on_platform():
    windows = capacity.configured_need('windows')
    linux = capacity.configured_need('linux')

    assert windows.memory_bytes == 8192 * 1024**2 + capacity.QEMU_OVERHEAD_BYTES
    assert linux.memory_bytes == 4096 * 1024**2 + capacity.QEMU_OVERHEAD_BYTES
    assert linux.cpu_cores == capacity.DEFAULT_VCPUS * capacity.CONFIGURED_CPU_SHARE
    assert windows.source == linux.source == 'configured'


def test_measured_need_takes_peak_memory_and_disk_and_median_cpu():
    fallback = capacity.configured_need('linux')
    usages = [_usage(3, cpu=40, disk_gib=4), _usage(5, cpu=120, disk_gib=9), _usage(4, cpu=60, disk_gib=2)]

    need = capacity.measured_need(usages, fallback)

    assert need.source == 'measured'
    assert need.measured_runs == 3
    assert need.memory_bytes == 5 * GIB
    assert need.disk_bytes == 9 * GIB
    assert need.cpu_cores == 0.6


def test_measured_need_ignores_runs_without_samples():
    fallback = capacity.configured_need('linux')

    assert capacity.measured_need([_usage(3, samples=0)], fallback) is fallback


def test_estimate_reports_the_scarcest_resource():
    host = _host(available_gib=40, total_gib=64, cpu_count=16, disk_free_gib=1000, disk_total_gib=2000)
    usage = {'ubuntu': [_usage(6, cpu=100, disk_gib=10)]}

    result = {c.environment: c for c in capacity.estimate(host, [('ubuntu', 'linux'), ('win', 'windows')], usage)}

    # 40 GiB - 6.4 GiB reserve = 33.6 GiB free
    assert (result['ubuntu'].fits_by_memory, result['ubuntu'].fits_by_cpu) == (5, 16)
    assert (result['ubuntu'].fits, result['ubuntu'].limited_by) == (5, 'memory')
    assert result['ubuntu'].need.source == 'measured'
    assert result['win'].fits == 3  # 8.5 GiB per Windows run
    assert result['win'].need.source == 'configured'
