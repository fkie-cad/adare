"""
System Service - host resources, storage, usage history and run capacity.

Returns plain JSON-ready dicts (sizes in bytes, CPU in percent) so the web UI,
the CLI's JSON output and Claude reading `adare system ...` see the same shape.
"""

import logging
from datetime import datetime
from typing import Any

import psutil
from sqlalchemy.exc import SQLAlchemyError

from adare.backend.system import capacity as capacity_model
from adare.backend.system.history import load_history
from adare.backend.system.host import HostSnapshot, host_snapshot
from adare.backend.system.storage import storage_report
from adare.core.result import Result
from adare.database.models.global_models import RunResourceUsage

log = logging.getLogger(__name__)

_ERRORS = (SQLAlchemyError, OSError, psutil.Error)


def _fail(what: str, e: Exception) -> Result:
    log.warning(f'{what} failed: {e}')
    return Result.fail('SystemInfoError', f'{what} failed: {e}')


def _iso(value: Any) -> str | None:
    # Any: legacy declarative columns type as Column[datetime], not datetime
    return value.isoformat() if value else None


def _instances_by_name() -> dict[str, dict]:
    from adare.database.api.vm import VmApi

    with VmApi() as api:
        return {
            i.instance_name: {
                'instance_id': i.id,
                'status': i.status,
                'vm_name': i.vm.name if i.vm else None,
                'experiment_run_id': i.current_experiment_run_id,
            }
            for i in api.get_all_vm_instances()
        }


def _resources_dict(host: HostSnapshot) -> dict:
    instances = _instances_by_name()
    return {
        'cpu': {
            'count': host.cpu_count,
            'percent': host.cpu_percent,
            'load_average': list(host.load_average) if host.load_average else None,
        },
        'memory': {
            'total_bytes': host.memory_total_bytes,
            'available_bytes': host.memory_available_bytes,
            'used_bytes': host.memory_used_bytes,
            'swap_total_bytes': host.swap_total_bytes,
            'swap_used_bytes': host.swap_used_bytes,
        },
        'disks': [
            {
                'path': d.path,
                'total_bytes': d.total_bytes,
                'used_bytes': d.used_bytes,
                'free_bytes': d.free_bytes,
                'percent': d.percent,
            }
            for d in host.disks
        ],
        'vms': [
            {
                'pid': vm.pid,
                'name': vm.name,
                'rss_bytes': vm.rss_bytes,
                'cpu_percent': vm.cpu_percent,
                'started_at': datetime.fromtimestamp(vm.started_at).isoformat(),
                'memory_mb': vm.memory_mb,
                'cpus': vm.cpus,
                **instances.get(vm.name, {}),
            }
            for vm in sorted(host.vms, key=lambda v: v.rss_bytes, reverse=True)
        ],
        'vm_totals': {'count': len(host.vms), 'rss_bytes': host.vm_rss_bytes, 'cpu_percent': host.vm_cpu_percent},
    }


def _usage_dict(u: RunResourceUsage) -> dict:
    return {
        'id': u.id,
        'experiment_run_id': u.experiment_run_id,
        'machine': u.machine,
        'environment_name': u.environment_name,
        'experiment_name': u.experiment_name,
        'project_path': u.project_path,
        'started_at': _iso(u.started_at),
        'ended_at': _iso(u.ended_at),
        'duration_seconds': (u.ended_at - u.started_at).total_seconds() if u.ended_at and u.started_at else None,
        'vm_cpus': u.vm_cpus,
        'vm_memory_mb': u.vm_memory_mb,
        'peak_rss_bytes': u.peak_rss_bytes,
        'avg_cpu_percent': u.avg_cpu_percent,
        'peak_cpu_percent': u.peak_cpu_percent,
        'disk_bytes': u.disk_bytes,
    }


class SystemService:
    def get_resources(self) -> Result[dict]:
        """Live CPU, memory, disk and the running VMs."""
        try:
            return Result.ok(_resources_dict(host_snapshot()))
        except _ERRORS as e:
            return _fail('Reading host resources', e)

    def get_storage(self, refresh: bool = False) -> Result[dict]:
        """Physical disk usage of ADARE's directories, run disks by owner, projects."""
        try:
            report = storage_report(refresh=refresh)
        except _ERRORS as e:
            return _fail('Measuring storage', e)
        return Result.ok(
            {
                'computed_at': datetime.fromtimestamp(report.computed_at).isoformat(),
                'categories': [vars(c) for c in report.categories],
                'disk_owners': [vars(o) for o in report.disk_owners],
                'projects': [vars(p) for p in report.projects],
                'reclaimable_bytes': report.reclaimable_bytes,
            }
        )

    def get_history(self, hours: float = 24) -> Result[list[dict]]:
        """Host usage samples of the last ``hours`` (recorded while the web UI runs)."""
        try:
            points = load_history(hours)
        except _ERRORS as e:
            return _fail('Loading usage history', e)
        return Result.ok([{**vars(p), 'taken_at': p.taken_at.isoformat()} for p in points])

    def get_run_usage(self, environment_name: str | None = None, limit: int = 100) -> Result[list[dict]]:
        """Measured resource usage of recent runs, newest first."""
        from adare.database.api.system import SystemDbApi

        try:
            with SystemDbApi() as api:
                return Result.ok([_usage_dict(u) for u in api.run_usage(environment_name, limit)])
        except _ERRORS as e:
            return _fail('Loading run usage', e)

    def get_capacity(self) -> Result[dict]:
        """How many more runs of each current environment fit on the host right now."""
        from adare.database.api.environment import EnvironmentDbApi
        from adare.database.api.system import SystemDbApi

        try:
            host = host_snapshot()
            with EnvironmentDbApi() as env_api:
                environments = [
                    (e.name, e.vm.osinfo.platform if e.vm and e.vm.osinfo else None) for e in env_api.get_environments()
                ]
            usage_by_env: dict[str, list] = {}
            with SystemDbApi() as api:
                for usage in api.run_usage(limit=2000):
                    if usage.environment_name:
                        usage_by_env.setdefault(usage.environment_name, []).append(usage)
                estimates = capacity_model.estimate(host, environments, usage_by_env)
        except _ERRORS as e:
            return _fail('Estimating capacity', e)
        room = capacity_model.headroom(host)
        return Result.ok(
            {
                'headroom': vars(room),
                'reserve': {
                    'memory_fraction': capacity_model.HOST_MEMORY_RESERVE,
                    'min_memory_bytes': capacity_model.MIN_MEMORY_RESERVE,
                    'disk_fraction': capacity_model.DISK_RESERVE,
                    'min_disk_bytes': capacity_model.MIN_DISK_RESERVE,
                },
                'environments': [{**vars(c), 'need': vars(c.need)} for c in estimates],
            }
        )
