"""Remove a registered VM -- together with the environments that run on it.

A registered VM is the disk environments run on (`adare env load` registers it),
so removing it removes those environments too: `adare vm remove <vm>` ends where
`adare env remove <env>` does. The web API removes only VMs no environment uses
(``cascade=False``); it has no confirmation step for taking environments along.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import cast

from adare.backend.vm.exceptions import VMInUseByEnvironmentError, VMRemovalError
from adare.database.api.environment import EnvironmentDbApi
from adare.database.api.vm import VmApi
from adare.database.api.vm.exceptions import VMNotFoundError
from adare.database.models.global_models import VmInstance

log = logging.getLogger(__name__)


@dataclass
class VmRemovalPlan:
    """What removing a registered VM takes along -- computed without changing anything."""

    vm_id: str
    vm_name: str
    disk: Path | None
    disk_managed: bool
    # environment name -> its version ids; every version runs on this VM
    environments: dict[str, list[str]] = field(default_factory=dict)
    # environment name -> what its other versions run on: removing it would take those along
    mixed_environments: dict[str, list[str]] = field(default_factory=dict)
    live_instances: list[str] = field(default_factory=list)
    stopped_instances: list[str] = field(default_factory=list)
    runs_per_project: dict[Path, int] = field(default_factory=dict)
    orphaned_experiments: list[tuple[Path, str]] = field(default_factory=list)
    unscanned_projects: list[str] = field(default_factory=list)

    @property
    def run_count(self) -> int:
        return sum(self.runs_per_project.values())

    def check(self, force: bool = False, cascade: bool = True) -> None:
        """Raise if the removal must not go ahead; nothing has been changed at that point.

        ``force`` allows deleting the runs (and detaching the experiments) of the
        environments removed along -- as `adare env remove --force` does.
        """
        if self.live_instances:
            raise VMRemovalError(
                log,
                f'VM {self.vm_name} has running instances ({", ".join(self.live_instances)}): '
                'an experiment run or dev session is using it',
                possible_solutions=[
                    'Wait for the run to finish (`adare vm usage` shows the instances)',
                    'Or stop an instance first: `adare vm remove <instance> --force`',
                ],
            )
        names = sorted([*self.environments, *self.mixed_environments])
        if names and not cascade:
            raise VMInUseByEnvironmentError(
                log,
                f'VM {self.vm_name} is used by environment(s) {", ".join(names)}',
                possible_solutions=[
                    f'Remove the environment instead, which removes the VM with it: `adare env remove {names[0]}`'
                ],
            )
        if self.mixed_environments:
            details = '; '.join(
                f'{name} also has versions on {", ".join(others)}' for name, others in self.mixed_environments.items()
            )
            raise VMRemovalError(
                log,
                f'VM {self.vm_name} cannot be removed on its own: removing its environments would also remove '
                f'what their other versions run on ({details})',
                possible_solutions=[
                    f'Remove the whole environment, every version and VM: `adare env remove {name}`'
                    for name in self.mixed_environments
                ],
            )
        if force:
            return
        if self.unscanned_projects:
            raise VMRemovalError(
                log,
                f'VM {self.vm_name} cannot be removed because these projects could not be checked for runs '
                f'using its environments: {", ".join(self.unscanned_projects)}',
                possible_solutions=[
                    'Make the project available again (or remove it from ADARE) and retry',
                    'Run with --force to remove it anyway',
                ],
            )
        if self.orphaned_experiments:
            experiments = ', '.join(f'{name} (project: {path.name})' for path, name in self.orphaned_experiments)
            raise VMRemovalError(
                log,
                f'VM {self.vm_name} cannot be removed because these experiments use no other environment: '
                f'{experiments}',
                possible_solutions=[
                    'Run with --force to remove it and those runs (the experiments are kept, without an environment)',
                    'Add other environments to the experiments first',
                ],
            )
        if self.run_count:
            raise VMRemovalError(
                log,
                f'VM {self.vm_name} has {self.run_count} experiment run(s) across {len(self.runs_per_project)} '
                'project(s), so it cannot be removed because this would invalidate the results',
                possible_solutions=['Run with --force to delete those runs and remove the VM'],
            )


@dataclass
class VmRemovalOutcome:
    vm_name: str
    environments: list[str]
    disk: Path | None
    disk_deleted: bool


def _is_managed(disk: Path) -> bool:
    from adare.config.configdirectory import VMS_DIR

    return disk.resolve().is_relative_to(VMS_DIR.resolve())


def _is_live(instance: VmInstance) -> bool:
    """A live owner process or a running/paused domain -- the database status can be stale after a crash."""
    from adare.backend.vm.instance_manager import get_instance_hypervisor_state
    from adare.backend.vm.run_instances import pid_alive

    if instance.owner_pid is not None and pid_alive(cast(int, instance.owner_pid)):
        return True
    return get_instance_hypervisor_state(instance) in ('running', 'paused')


def plan_vm_removal(vm_id: str) -> VmRemovalPlan:
    """Work out what removing registered VM ``vm_id`` would remove or be refused by."""
    from adare.backend.environment.database import find_environment_references

    with VmApi() as api:
        vm = api.get_vm_by_id(vm_id)
        if not vm:
            raise VMNotFoundError(log, f'VM with ID {vm_id} not found')
        disk = Path(vm.file) if vm.file else None
        plan = VmRemovalPlan(
            vm_id=vm_id, vm_name=vm.name, disk=disk, disk_managed=bool(disk) and _is_managed(cast(Path, disk))
        )
        for instance in api.get_vm_instances_for_vm(vm_id):
            (plan.live_instances if _is_live(instance) else plan.stopped_instances).append(instance.instance_name)

    with EnvironmentDbApi() as db:
        for name in db.get_environment_names_using_vm(vm_id):
            versions = db.get_environment_versions(name)
            others = sorted(
                {
                    (version.vm.name if version.vm else version.vm_id or 'no VM')
                    for version in versions
                    if version.vm_id != vm_id
                }
            )
            if others:
                plan.mixed_environments[name] = others
            else:
                plan.environments[name] = [version.id for version in versions]

    version_ids = {version_id for ids in plan.environments.values() for version_id in ids}
    if version_ids and not plan.mixed_environments:
        plan.runs_per_project, plan.orphaned_experiments, plan.unscanned_projects = find_environment_references(
            version_ids
        )
    return plan


def teardown_unreferenced_vm(vm_id: str, force: bool = False) -> VmRemovalOutcome | None:
    """Delete a VM no environment uses: its instances, hypervisor state, row and managed disk.

    Returns None if there is no such VM. A disk outside ADARE's managed storage is kept.
    """
    from adare.backend.environment.database import delete_managed_file
    from adare.backend.vm import commands as vm_commands
    from adare.backend.vm.database import run_blocking
    from adare.config.configdirectory import VMS_DIR

    with EnvironmentDbApi() as db:
        names = db.get_environment_names_using_vm(vm_id)
    if names:
        raise VMInUseByEnvironmentError(log, f'VM {vm_id} is used by environment(s) {", ".join(names)}')
    with VmApi() as api:
        vm = api.get_vm_by_id(vm_id)
        if not vm:
            return None
        vm_name = vm.name
        disk = Path(vm.file) if vm.file else None

    # Instances, domains, overlays, templates and the row. run_blocking: callers
    # may already be inside an event loop (TUI, async CLI handlers).
    if not run_blocking(vm_commands.delete_vm(vm_id, force=force)):
        raise VMRemovalError(log, f'VM {vm_name} could not be deleted (see the log above)')
    log.info(f'Deleted VM (hypervisor + database record): {vm_name} ({vm_id})')
    disk_deleted = bool(disk) and delete_managed_file(cast(Path, disk), VMS_DIR)
    if disk_deleted:
        from adare.backend.vm.image_record import packages_path, record_path

        # The image's record and package list describe the deleted disk
        for sidecar in (record_path(cast(Path, disk)), packages_path(cast(Path, disk))):
            sidecar.unlink(missing_ok=True)
    return VmRemovalOutcome(vm_name=vm_name, environments=[], disk=disk, disk_deleted=disk_deleted)


def remove_vm(vm_id: str, force: bool = False, cascade: bool = True) -> VmRemovalOutcome:
    """Remove registered VM ``vm_id`` and, with ``cascade``, the environments that run on it.

    Every refusal is checked before anything is deleted. A run started between
    that check and the deletion of a later environment can still stop the removal
    halfway (without ``force``); the environments removed so far stay removed.
    """
    from adare.backend.environment.database import delete_environment

    plan = plan_vm_removal(vm_id)
    plan.check(force=force, cascade=cascade)
    for version_ids in plan.environments.values():
        delete_environment(version_ids[0], force=force, cleanup_vm=False)
    outcome = teardown_unreferenced_vm(vm_id, force=force) or VmRemovalOutcome(
        vm_name=plan.vm_name, environments=[], disk=plan.disk, disk_deleted=False
    )
    outcome.environments = sorted(plan.environments)
    return outcome


def find_unreferenced_vms() -> list[tuple[str, str]]:
    """(name, id) of the registered VMs no environment version uses."""
    with VmApi() as api:
        vms = [(vm.name, vm.id) for vm in api.get_all_vms()]
    with EnvironmentDbApi() as db:
        return sorted((name, vm_id) for name, vm_id in vms if not db.is_vm_referenced(vm_id))
