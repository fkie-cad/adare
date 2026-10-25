"""QEMU command-line parsing and host snapshot assembly."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from adare.backend.system import host
from adare.backend.system.host import DiskUsage, HostSnapshot, VmProcess, _parse_memory, _parse_qemu_cmdline

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    'cmdline,expected',
    [
        # libvirt
        (
            [
                'qemu-system-aarch64',
                '-name',
                'guest=ubuntu_exp_01ABC,debug-threads=on',
                '-m',
                'size=4194304k',
                '-smp',
                '4,sockets=4,cores=1,threads=1',
            ],
            ('ubuntu_exp_01ABC', 4096, 4),
        ),
        # direct QEMU
        (
            ['qemu-system-x86_64', '-name', 'win11_exp_X', '-m', '8G', '-smp', 'cpus=2,cores=2'],
            ('win11_exp_X', 8192, 2),
        ),
        # unnamed image build: named after its scratch dir
        (
            [
                'qemu-system-aarch64',
                '-m',
                '8192',
                '-smp',
                '4',
                '-drive',
                'if=virtio,file=/tmp/T/adare-extend-6mgk/work-overlay.qcow2',
            ],
            ('adare-extend-6mgk', 8192, 4),
        ),
        # unnamed, plain disk: the disk's name
        (['qemu-system-aarch64', '-drive', 'file=/x/fedora42.qcow2,if=virtio'], ('fedora42', None, None)),
        (['qemu-system-aarch64'], (None, None, None)),
    ],
)
def test_parse_qemu_cmdline(cmdline, expected):
    assert _parse_qemu_cmdline(cmdline) == expected


@pytest.mark.parametrize(
    'value,mb',
    [('4096', 4096), ('4G', 4096), ('512M', 512), ('size=2097152k,slots=2', 2048), ('1T', 1024 * 1024), ('lots', None)],
)
def test_parse_memory(value, mb):
    assert _parse_memory(value) == mb


def test_snapshot_totals_and_disk_percent():
    snapshot = HostSnapshot(
        cpu_count=8,
        cpu_percent=10.0,
        load_average=None,
        memory_total_bytes=100,
        memory_available_bytes=60,
        memory_used_bytes=40,
        swap_total_bytes=0,
        swap_used_bytes=0,
        disks=[DiskUsage('/x', total_bytes=200, used_bytes=50, free_bytes=150)],
        vms=[VmProcess(1, 'a', 10, 50.0, 0.0), VmProcess(2, 'b', 30, 25.0, 0.0)],
    )

    assert snapshot.vm_rss_bytes == 40
    assert snapshot.vm_cpu_percent == 75.0
    assert snapshot.disks[0].percent == 25.0
    assert DiskUsage('/y', 0, 0, 0).percent == 0.0


def test_vm_processes_reads_only_qemu_and_forgets_dead_ones():
    qemu = MagicMock(pid=11)
    qemu.cmdline.return_value = ['qemu-system-aarch64', '-name', 'guest=run1', '-m', '4096', '-smp', '2']
    qemu.memory_info.return_value = SimpleNamespace(rss=123)
    qemu.cpu_percent.return_value = 40.0
    qemu.create_time.return_value = 1000.0
    listing = [
        SimpleNamespace(info={'pid': 11, 'name': 'qemu-system-aarch64'}),
        SimpleNamespace(info={'pid': 12, 'name': 'python3'}),
    ]
    host._process_cache.clear()
    host._process_cache[99] = MagicMock()  # a process that has exited since

    with (
        patch.object(host.psutil, 'process_iter', return_value=listing),
        patch.object(host.psutil, 'Process', return_value=qemu),
        patch.object(host.time, 'sleep') as sleep,
    ):
        vms = host.vm_processes()

    assert [(v.pid, v.name, v.rss_bytes, v.cpu_percent, v.memory_mb, v.cpus) for v in vms] == [
        (11, 'run1', 123, 40.0, 4096, 2)
    ]
    sleep.assert_called_once()  # a new process is measured over a short pause
    assert set(host._process_cache) == {11}
    host._process_cache.clear()


class _Times(tuple):
    """psutil.cpu_times()-like: iterable over fields, with named access."""

    def __new__(cls, user, idle):
        obj = super().__new__(cls, (user, idle))
        obj.user, obj.idle = user, idle
        return obj


def test_host_cpu_percent_from_deltas_and_reused_when_too_soon():
    host._cpu_last = None
    readings = [_Times(100, 900), _Times(130, 970), _Times(190, 1010)]
    with (
        patch.object(host.psutil, 'cpu_times', side_effect=readings) as cpu_times,
        patch.object(host.time, 'sleep'),
    ):
        assert host.host_cpu_percent() == 30.0  # 30 busy of 100 over the first pause
        assert host.host_cpu_percent() == 30.0  # too soon: same reading, no new sample
        host._cpu_last = (host._cpu_last[0] - 5, *host._cpu_last[1:])
        assert host.host_cpu_percent() == 60.0  # 60 busy of 100 since the last reading
    assert cpu_times.call_count == 3
    host._cpu_last = None
