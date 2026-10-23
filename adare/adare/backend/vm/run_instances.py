"""Run-scoped QEMU instances and instance reconciliation.

A QEMU experiment run does not reuse a pooled machine: it boots a throwaway
overlay on the environment's read-only disk (see
:mod:`adare.hypervisor.qemu.run_resources`). Its ``VmInstance`` row exists only
for the run's lifetime -- it reserves the websocket port and names the run's
files -- and is deleted together with those files when the run ends.

VirtualBox keeps the pooled instances of :mod:`adare.backend.vm.instance_manager`.

:func:`reconcile_instances` is the single place that brings the database back in
line with reality after crashes: rows whose owning process is gone, run files
without a row, and QEMU instances left over from the pooled design.
"""

import ctypes
import logging
import os
import re
from dataclasses import dataclass, field
from typing import cast

from adare.backend.vm.exceptions import VMError
from adare.database.api.vm import VmApi
from adare.database.exceptions import DatabaseError
from adare.database.models.global_models import Vm, VmInstance

log = logging.getLogger(__name__)


def pid_alive(pid: int | None) -> bool:
    """True if a process with this PID exists (on this host)."""
    if not pid or pid <= 0:
        return False
    if os.name == 'nt':
        # os.kill(pid, 0) would *terminate* the process on Windows (signal 0 is CTRL_C_EVENT).
        process_query_limited_information = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(process_query_limited_information, False, pid)  # type: ignore[attr-defined]
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)  # type: ignore[attr-defined]
        return True
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def run_instance_name(vm_name: str, experiment_run_ulid: str, machine_key: str | None = None) -> str:
    """Name of a run's QEMU instance (libvirt domain + file prefix).

    The run ULID's random tail keeps concurrent runs apart; the machine key keeps
    the machines of one multi-machine run apart.
    """
    name = f'{vm_name}_run_{experiment_run_ulid[-8:]}'
    if machine_key:
        name += '_' + re.sub(r'[^A-Za-z0-9-]', '-', machine_key)
    return name


def allocate_qemu_run_instance(source_vm: Vm, experiment_run_ulid: str, machine_key: str | None = None) -> VmInstance:
    """Create the run's instance row with a reserved websocket port. No disk is copied."""
    from adare.backend.vm.port_manager import reserve_port_atomically

    name = run_instance_name(source_vm.name, experiment_run_ulid, machine_key)
    with VmApi() as api:
        port = reserve_port_atomically(api, source_vm.id, name, experiment_run_ulid)
    if port is None:
        raise VMError(
            log,
            f"No free websocket port for run instance {name}",
            possible_solutions=[
                'Wait for running experiments to finish',
                'Reclaim crashed runs: adare vm prune --force',
            ],
        )
    with VmApi() as api:
        instance = api.get_vm_instance_by_name(name)
    if instance is None:
        raise VMError(log, f"Run instance {name} was reserved but cannot be read back")
    log.info(f"Run instance {name} on port {port}")
    return instance


def remove_qemu_run_instance(instance_name: str) -> None:
    """Tear down a QEMU run: domain, every run file, and the instance row."""
    from adare.hypervisor.qemu.run_resources import destroy_run_domain, remove_run_files

    destroy_run_domain(instance_name)
    remove_run_files(instance_name)
    with VmApi() as api:
        instance = api.get_vm_instance_by_name(instance_name)
        if instance is not None:
            api.delete_vm_instance(instance.id)


@dataclass
class ReconcileReport:
    """What :func:`reconcile_instances` did (or, in a dry run, would do)."""

    removed_runs: list[str] = field(default_factory=list)
    released_instances: list[str] = field(default_factory=list)
    removed_pooled_qemu: list[str] = field(default_factory=list)
    orphaned_run_files: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not (self.removed_runs or self.released_instances or self.removed_pooled_qemu or self.orphaned_run_files)


def _dev_session_vm_names() -> set[str] | None:
    """Instance names held by dev sessions -- they outlive the process that started them.

    None if the sessions cannot be read; reconciliation then touches nothing.
    """
    from adare.database.api.devmode import DevModeApi

    try:
        with DevModeApi() as api:
            return {session.vm_name for session in api.list_sessions()}
    except DatabaseError as e:
        log.warning(f"Could not read dev sessions, skipping instance reconciliation: {e}")
        return None


def _is_stale(instance: VmInstance) -> bool:
    """An active row whose run can no longer be in progress."""
    if instance.owner_pid is not None:
        return not pid_alive(cast(int, instance.owner_pid))
    # Rows from before owner tracking: only trust a domain that is not running.
    if instance.vm is not None and instance.vm.hypervisor == 'qemu':
        from adare.hypervisor.qemu.run_resources import is_domain_running

        return not is_domain_running(instance.instance_name)
    return False


def _run_names_on_disk() -> set[str]:
    """Instance names that have run files (config or overlay) on disk."""
    from adare.hypervisor.qemu.mixins.configuration import get_qemu_disk_dir, get_qemu_vm_config_dir

    names = {path.stem for path in get_qemu_vm_config_dir().glob('*_run_*.json')}
    names |= {path.name.split('-overlay-')[0] for path in get_qemu_disk_dir().glob('*_run_*-overlay-*.qcow2')}
    return names


async def reconcile_instances(dry_run: bool = False) -> ReconcileReport:
    """Bring instance rows and run files back in line with what is actually running.

    - QEMU run rows whose owning process is gone: domain, files and row removed.
    - VirtualBox rows whose owning process is gone: released back to the pool.
    - QEMU instances left over from the pooled design (``available`` rows with a
      full disk copy each): removed, including that copy.
    - QEMU run files (overlay, varstore, config, vTPM copy) without a row: removed.

    Rows held by a dev session are never touched; ``adare dev remove`` owns them.
    """
    from adare.backend.vm.instance_manager import cleanup_vm_instance
    from adare.hypervisor.qemu.run_resources import remove_run_files

    report = ReconcileReport()
    dev_names = _dev_session_vm_names()
    if dev_names is None:
        return report
    # Scan run files BEFORE reading rows: a run inserts its row before it creates
    # files, so every file seen here belongs to a row the read below includes.
    # The other order lets a concurrent run's fresh files look orphaned.
    run_names_on_disk = _run_names_on_disk()
    with VmApi() as api:
        instances = api.get_all_vm_instances()

    for instance in instances:
        if instance.instance_name in dev_names:
            continue
        is_qemu = instance.vm is not None and instance.vm.hypervisor == 'qemu'
        if instance.status == 'available' and is_qemu:
            report.removed_pooled_qemu.append(instance.instance_name)
            if not dry_run:
                await cleanup_vm_instance(instance.id, force=True)
        elif instance.status in ('active', 'cleanup_pending') and _is_stale(instance):
            if is_qemu:
                report.removed_runs.append(instance.instance_name)
                if not dry_run:
                    remove_qemu_run_instance(instance.instance_name)
            else:
                report.released_instances.append(instance.instance_name)
                if not dry_run:
                    from adare.backend.vm.instance_manager import release_vm_instance

                    await release_vm_instance(instance.id)

    known = {instance.instance_name for instance in instances}
    for name in sorted(run_names_on_disk - known - dev_names):
        report.orphaned_run_files.append(name)
        if not dry_run:
            remove_run_files(name)
    return report
