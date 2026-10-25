"""Usage history sampling and per-run resource measurement (against a real global DB file)."""

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import psutil
import pytest

from adare.backend.system import history, run_monitor
from adare.backend.system.history import HistoryPoint, downsample, load_history, record_sample
from adare.backend.system.host import DiskUsage, HostSnapshot, VmProcess
from adare.backend.system.run_monitor import MachineUsage, RunResourceMonitor
from adare.database.api.system import SystemDbApi

pytestmark = pytest.mark.unit


def _snapshot():
    return HostSnapshot(
        cpu_count=4,
        cpu_percent=30.0,
        load_average=(1.0, 1.0, 1.0),
        memory_total_bytes=1000,
        memory_available_bytes=400,
        memory_used_bytes=600,
        swap_total_bytes=0,
        swap_used_bytes=0,
        disks=[DiskUsage('/x', 100, 70, 30)],
        vms=[VmProcess(1, 'vm', 200, 80.0, 0.0)],
    )


def test_record_and_load_history_drops_expired_samples(global_db):
    with SystemDbApi() as api:
        api.add_sample(
            taken_at=datetime.now(UTC).replace(tzinfo=None) - timedelta(days=40),
            cpu_percent=1.0,
            memory_total_bytes=1,
            memory_used_bytes=1,
            disk_total_bytes=1,
            disk_used_bytes=1,
        )

    record_sample(_snapshot())
    points = load_history(hours=24)

    assert len(points) == 1
    assert (points[0].cpu_percent, points[0].memory_used_bytes, points[0].vm_count, points[0].vm_rss_bytes) == (
        30.0,
        600,
        1,
        200,
    )
    with SystemDbApi() as api:
        assert len(api.samples_since(datetime(2000, 1, 1))) == 1


def test_downsample_averages_load_and_keeps_vm_peaks():
    start = datetime(2026, 1, 1)
    points = [
        HistoryPoint(start + timedelta(minutes=i), float(i), i * 10, 100, i, 100, vm_count=i % 3, vm_rss_bytes=i)
        for i in range(10)
    ]

    result = downsample(points, 5)

    assert len(result) == 5
    assert result[0].cpu_percent == 0.5
    assert result[0].vm_count == 1
    assert result[-1].vm_rss_bytes == 9
    assert downsample(points, 50) is points


def test_sampler_survives_a_failed_sample():
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise OSError('disk gone')
        raise SystemExit  # stops the endless loop for the test

    with patch.object(history, 'record_sample', flaky), pytest.raises(SystemExit):
        asyncio.run(history.sample_forever(interval=0))

    assert len(calls) == 2


def test_machine_usage_accumulates():
    usage = MachineUsage(None, 'vm', None, 4, 4096)
    usage.add(100, 50.0)
    usage.add(300, 150.0)

    assert (usage.samples, usage.peak_rss_bytes, usage.avg_cpu_percent, usage.peak_cpu_percent) == (
        2,
        300,
        100.0,
        150.0,
    )


def _qemu(rss, cpu):
    process = MagicMock()
    process.is_running.return_value = True
    process.memory_info.return_value = SimpleNamespace(rss=rss)
    process.cpu_percent.return_value = cpu
    return process


def test_monitor_finds_the_process_then_samples_it():
    machine = MachineUsage(None, 'run_vm', 'env1', 2, 4096)
    monitor = RunResourceMonitor('RUN1', [machine])
    process = _qemu(500, 75.0)

    with patch.object(run_monitor, 'find_qemu_process', return_value=process) as find:
        monitor.sample()  # finds and primes
        monitor.sample()
        monitor.sample()

    find.assert_called_once_with('run_vm')
    assert (machine.samples, machine.peak_rss_bytes, machine.avg_cpu_percent) == (2, 500, 75.0)

    process.memory_info.side_effect = psutil.NoSuchProcess(1)
    monitor.sample()
    assert machine.process is None


def test_monitor_stop_persists_usage_with_disk_size(global_db, tmp_path):
    disk_dir = tmp_path / 'disks'
    disk_dir.mkdir()
    (disk_dir / 'run_vm-overlay-01X.qcow2').write_bytes(b'x' * 8192)
    (disk_dir / 'other_vm-overlay-01Y.qcow2').write_bytes(b'x' * 8192)
    seen = MachineUsage('client', 'run_vm', 'env1', 2, 4096)
    seen.add(1000, 20.0)
    never_up = MachineUsage('server', 'dead_vm', 'env1', 2, 4096)
    monitor = RunResourceMonitor(
        'RUN1', [seen, never_up], environment_names={'env1': 'ubuntu'}, project_path='/p', experiment_name='exp'
    )

    with (
        patch.object(run_monitor, 'find_qemu_process', return_value=None),
        patch('adare.hypervisor.qemu.mixins.configuration.get_qemu_disk_dir', return_value=disk_dir),
    ):
        monitor.stop()

    with SystemDbApi() as api:
        rows = api.run_usage()
        assert len(rows) == 1  # a machine that never came up records nothing
        row = rows[0]
        assert (row.experiment_run_id, row.machine, row.environment_name, row.experiment_name) == (
            'RUN1',
            'client',
            'ubuntu',
            'exp',
        )
        assert (row.peak_rss_bytes, row.vm_memory_mb, row.samples) == (1000, 4096, 1)
        assert 8192 <= row.disk_bytes < 16384  # only this run's files
        assert api.run_usage(environment_name='other') == []


def test_start_run_monitor_needs_a_running_machine():
    context = SimpleNamespace(
        machines={None: SimpleNamespace(vm_name=None, environment_ulid=None)},
        experiment_run_ulid='RUN1',
        config=SimpleNamespace(vm_cpus=4, vm_memory=4096, project_path='/p', experiment_name='e'),
    )

    assert run_monitor.start_run_monitor(context) is None
