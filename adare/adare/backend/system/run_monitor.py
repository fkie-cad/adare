"""Measure what an experiment run's VMs actually consume.

A daemon thread samples each machine's QEMU process (found by its instance name
on the command line) every few seconds while the run is up, and on stop writes
one :class:`RunResourceUsage` row per machine: peak RSS, average and peak CPU,
and the physical size of the run's disk files. Capacity planning reads these
instead of guessing from configured sizes.

Monitoring is best-effort: nothing here may fail or slow down the run.
"""

import logging
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime

import psutil
from sqlalchemy.exc import SQLAlchemyError

from adare.backend.system.host import _parse_qemu_cmdline

log = logging.getLogger(__name__)

SAMPLE_INTERVAL = 5.0


@dataclass
class MachineUsage:
    """Accumulated readings for one machine of a run."""

    machine: str | None
    instance_name: str
    environment_id: str | None
    vm_cpus: int | None
    vm_memory_mb: int | None
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    process: psutil.Process | None = None
    samples: int = 0
    peak_rss_bytes: int = 0
    cpu_total: float = 0.0
    peak_cpu_percent: float = 0.0

    def add(self, rss_bytes: int, cpu_percent: float) -> None:
        self.samples += 1
        self.peak_rss_bytes = max(self.peak_rss_bytes, rss_bytes)
        self.cpu_total += cpu_percent
        self.peak_cpu_percent = max(self.peak_cpu_percent, cpu_percent)

    @property
    def avg_cpu_percent(self) -> float:
        return self.cpu_total / self.samples if self.samples else 0.0


def find_qemu_process(instance_name: str) -> psutil.Process | None:
    """The QEMU process whose `-name` is ``instance_name``."""
    for proc in psutil.process_iter(['name']):
        if not (proc.info['name'] or '').startswith('qemu-system'):
            continue
        try:
            name, _, _ = _parse_qemu_cmdline(proc.cmdline())
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
        if name == instance_name:
            return proc
    return None


class RunResourceMonitor:
    """Samples a run's QEMU processes on a background thread; :meth:`stop` persists the result."""

    def __init__(
        self,
        experiment_run_id: str,
        machines: list[MachineUsage],
        environment_names: dict[str, str] | None = None,
        project_path: str | None = None,
        experiment_name: str | None = None,
        interval: float = SAMPLE_INTERVAL,
    ):
        self.experiment_run_id = experiment_run_id
        self.machines = machines
        self.environment_names = environment_names or {}
        self.project_path = project_path
        self.experiment_name = experiment_name
        self.interval = interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name=f'run-monitor-{self.experiment_run_id}', daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        while True:
            self.sample()
            if self._stop.wait(self.interval):
                return

    def sample(self) -> None:
        for machine in self.machines:
            try:
                if machine.process is None or not machine.process.is_running():
                    machine.process = find_qemu_process(machine.instance_name)
                    if machine.process is None:
                        continue
                    machine.process.cpu_percent(None)  # prime
                    continue
                with machine.process.oneshot():
                    machine.add(machine.process.memory_info().rss, machine.process.cpu_percent(None))
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                machine.process = None

    def stop(self) -> None:
        """Stop sampling and record the usage (call while the run's disk files still exist)."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval + 1)
        self.sample()
        try:
            self._persist()
        except (SQLAlchemyError, OSError) as e:
            log.warning(f'Could not record resource usage of run {self.experiment_run_id}: {e}')

    def _persist(self) -> None:
        from adare.backend.system.storage import physical_size
        from adare.database.api.system import SystemDbApi
        from adare.hypervisor.qemu.mixins.configuration import get_qemu_disk_dir

        disk_dir = get_qemu_disk_dir()
        ended_at = datetime.now(UTC)
        with SystemDbApi() as api:
            for machine in self.machines:
                if machine.samples == 0:
                    continue  # the VM never came up; nothing worth planning with
                disk_bytes = sum(physical_size(p)[0] for p in disk_dir.glob(f'{machine.instance_name}-*'))
                api.add_run_usage(
                    experiment_run_id=self.experiment_run_id,
                    machine=machine.machine,
                    instance_name=machine.instance_name,
                    environment_id=machine.environment_id,
                    environment_name=self.environment_names.get(machine.environment_id or ''),
                    project_path=self.project_path,
                    experiment_name=self.experiment_name,
                    started_at=machine.started_at,
                    ended_at=ended_at,
                    samples=machine.samples,
                    vm_cpus=machine.vm_cpus,
                    vm_memory_mb=machine.vm_memory_mb,
                    peak_rss_bytes=machine.peak_rss_bytes,
                    avg_cpu_percent=machine.avg_cpu_percent,
                    peak_cpu_percent=machine.peak_cpu_percent,
                    disk_bytes=disk_bytes,
                )


def start_run_monitor(context) -> RunResourceMonitor | None:
    """Start monitoring the machines of an :class:`ExperimentRunCtx` whose VMs are up."""
    machines = [
        MachineUsage(
            machine=key,
            instance_name=machine.vm_name,
            environment_id=machine.environment_ulid,
            vm_cpus=context.config.vm_cpus,
            vm_memory_mb=context.config.vm_memory,
        )
        for key, machine in context.machines.items()
        if machine.vm_name
    ]
    if not machines or not context.experiment_run_ulid:
        return None
    monitor = RunResourceMonitor(
        experiment_run_id=context.experiment_run_ulid,
        machines=machines,
        environment_names=_environment_names({m.environment_id for m in machines if m.environment_id}),
        project_path=str(context.config.project_path),
        experiment_name=context.config.experiment_name,
    )
    monitor.start()
    return monitor


def _environment_names(ids: set[str]) -> dict[str, str]:
    from adare.database.api.environment import EnvironmentDbApi

    names = {}
    try:
        with EnvironmentDbApi() as api:
            for env_id in ids:
                env = api.get_environment_by_ulid(env_id)
                if env is not None:
                    names[env_id] = env.name
    except SQLAlchemyError as e:
        log.debug(f'environment names for run monitor unavailable: {e}')
    return names
