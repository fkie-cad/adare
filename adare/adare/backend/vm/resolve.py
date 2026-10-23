"""Resolve a name or ID given on the command line to a registered VM or a VM instance."""

import logging
from dataclasses import dataclass
from typing import Literal

from adare.backend.vm.exceptions import AmbiguousVmTargetError
from adare.database.api.vm import VmApi
from adare.database.api.vm.exceptions import VMNotFoundError

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class VmTarget:
    """A registered VM (``kind='vm'``, what `adare vm list` shows) or a VM instance (`adare vm usage`)."""

    kind: Literal['vm', 'instance']
    id: str
    name: str


def resolve_vm_target(identifier: str) -> VmTarget:
    """Find the registered VM or VM instance with this ID or name.

    Raises:
        VMNotFoundError: nothing matches (exit 3 at the CLI); suggests similar VM names
        AmbiguousVmTargetError: a registered VM and an instance share the name
    """
    with VmApi() as api:
        vm = api.get_vm_by_id(identifier) or api.get_vm_by_name(identifier)
        instance = api.get_vm_instance_by_id(identifier) or api.get_vm_instance_by_name(identifier)
        if vm and instance:
            raise AmbiguousVmTargetError(
                log,
                f"'{identifier}' names both registered VM {vm.id} and VM instance {instance.id}",
                possible_solutions=[f'Pass the ID instead: {vm.id} (registered VM) or {instance.id} (instance)'],
            )
        if vm:
            return VmTarget('vm', vm.id, vm.name)
        if instance:
            return VmTarget('instance', instance.id, instance.instance_name)
        suggestions = [suggestion.name for suggestion in api.suggest_similar_vms(identifier)]

    solutions = [f'Did you mean: {", ".join(suggestions)}?'] if suggestions else []
    solutions.append('Run `adare vm list` for registered VMs and `adare vm usage` for VM instances')
    raise VMNotFoundError(log, f"VM or instance '{identifier}' not found", possible_solutions=solutions)
