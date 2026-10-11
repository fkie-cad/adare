"""Multi-machine VM orchestration.

``VMLifecycleManager`` itself is left untouched: it is ~900+ lines of
safety-critical QEMU/VirtualBox branching, and multiplying that risk by
teaching it about multiple machines internally is exactly what this module
avoids. Instead ``MultiVMOrchestrator`` holds one real ``VMLifecycleManager``
per machine and fans calls out across them, handing each one a
``_MachineContextView`` that makes it believe it is driving an ordinary
single-VM ``ExperimentRunCtx``.

``get_vm_orchestrator()`` is the only new call site production code needs:
for today's single-VM playbooks (no ``machines:`` key) it returns a plain,
unmodified ``VMLifecycleManager`` -- the exact object every existing call site
already expects, with zero behavior change.
"""

import asyncio
import logging

from adare.backend.experiment.runctx import ExperimentRunCtx, MachineRunCtx
from adare.backend.experiment.vm_lifecycle_manager import VMLifecycleManager
from adare.exceptions import LoggedException
from adare.types.playbook import MachineSpec

log = logging.getLogger(__name__)

# The per-machine fields extracted onto MachineRunCtx (runctx.py). Anything not in
# this set is shared experiment-run state and is forwarded straight to the parent
# context untouched (config, playbook, experiment_run_directory, stop_event, ...).
_MACHINE_SCOPED_ATTRS = frozenset(
    {
        'environment_file',
        'environment_ulid',
        'guest_platform',
        'guest_architecture',
        'hypervisor_type',
        'vm',
        'vm_file',
        'vm_name',
        'client',
        'mcp_server',
        'adarevm',
        'adarevm_pid',
    }
)

# Boot-pipeline methods that must run in dependency order rather than being fanned
# out in a single indiscriminate parallel gather. Phase 1 MVP boots serially, in
# `machines` dict order -- see `_boot_waves` below for the Phase 2 dependency-aware
# sequencing this will graduate to.
_BOOT_PIPELINE_METHODS = (
    'create_and_prepare_vm',
    'setup_file_transfer',
    'setup_networking',
    'start_vm',
    'wait_until_ready',
    'mount_shared_directories',
)


class BootDependencyError(LoggedException):
    """Raised when a playbook's `machines:` `depends_on:` graph is invalid (cycle or unknown reference)."""


class _MachineConfigView:
    """Proxies one machine's ``websocket_port`` over an otherwise-shared ``ExperimentConfig``.

    ``ExperimentConfig`` is genuinely shared experiment-run state, with one
    exception: ``websocket_port`` is a per-VM host-forwarded port, and
    ``VMLifecycleManager``/``hypervisor/qemu/lifecycle.py`` read and write
    ``context.config.websocket_port`` directly, assuming one VM per config.
    Without this, two machines fanned out through ``MultiVMOrchestrator`` would
    clobber each other's forwarded port in the shared config object. Every other
    attribute reads/writes straight through to the real config.
    """

    def __init__(self, real_config, machine_ctx: MachineRunCtx):
        object.__setattr__(self, '_real_config', real_config)
        object.__setattr__(self, '_machine_ctx', machine_ctx)

    def __getattr__(self, name):
        if name == 'websocket_port':
            return self._machine_ctx.websocket_port
        return getattr(self._real_config, name)

    def __setattr__(self, name, value):
        if name == 'websocket_port':
            self._machine_ctx.websocket_port = value
        else:
            setattr(self._real_config, name, value)


class _MachineContextView:
    """Proxies one machine's slice of an ``ExperimentRunCtx``.

    Forwards the per-machine field names (``vm``, ``client``, ``hypervisor_type``,
    ...) to ``parent_context.machines[machine_key]``, and every other attribute
    (``config``, ``playbook``, ``experiment_run_directory``, ``stop_event``, ...)
    straight through to ``parent_context`` unchanged. An unmodified
    ``VMLifecycleManager`` method that receives one of these believes it was
    handed an ordinary single-VM ``ExperimentRunCtx``.
    """

    def __init__(self, parent_context: ExperimentRunCtx, machine_key: str):
        object.__setattr__(self, '_parent_context', parent_context)
        object.__setattr__(self, '_machine_key', machine_key)

    def _machine_ctx(self) -> MachineRunCtx:
        return self._parent_context.machines[self._machine_key]

    def __getattr__(self, name):
        if name in _MACHINE_SCOPED_ATTRS:
            return getattr(self._machine_ctx(), name)
        if name == 'config':
            return _MachineConfigView(self._parent_context.config, self._machine_ctx())
        return getattr(self._parent_context, name)

    def __setattr__(self, name, value):
        if name in _MACHINE_SCOPED_ATTRS:
            setattr(self._machine_ctx(), name, value)
        else:
            setattr(self._parent_context, name, value)

    def __repr__(self):
        return f"_MachineContextView(machine_key={self._machine_key!r})"


class MultiVMOrchestrator:
    """Drives one ``VMLifecycleManager`` per machine of a multi-machine experiment.

    Exposes the same method names as ``VMLifecycleManager`` on its hot path
    (``create_and_prepare_vm``, ``setup_networking``, ``start_vm``,
    ``retrieve_artifacts``, ``perform_memory_dump``, ``perform_disk_export``,
    ``perform_host_diff``, ``stop_vm``, ``cleanup_vm``, ...) via a generic
    attribute-based fanout, so every existing call site
    (``step_runner.run_async_step(vm_manager.<method>, context)`` /
    ``run_cleanup_step(vm_manager.<method>, context, post_interrupt=...)``) works
    unmodified against either a plain ``VMLifecycleManager`` or this orchestrator.
    """

    def __init__(self, hypervisor_type: str, machine_keys: list[str]):
        self._machine_keys = list(machine_keys)
        self._managers: dict[str, VMLifecycleManager] = {
            key: VMLifecycleManager(hypervisor_type=hypervisor_type) for key in machine_keys
        }

    def __getattr__(self, name: str):
        if name.startswith('_'):
            raise AttributeError(name)
        if not all(hasattr(mgr, name) for mgr in self._managers.values()):
            raise AttributeError(name)

        serial = name in _BOOT_PIPELINE_METHODS

        async def fanout(context: ExperimentRunCtx, *args, **kwargs):
            results = {}
            if serial:
                for key in self._machine_keys:
                    view = _MachineContextView(context, key)
                    results[key] = await getattr(self._managers[key], name)(view, *args, **kwargs)
            else:

                async def call_one(key):
                    view = _MachineContextView(context, key)
                    return await getattr(self._managers[key], name)(view, *args, **kwargs)

                values = await asyncio.gather(*(call_one(key) for key in self._machine_keys))
                results = dict(zip(self._machine_keys, values, strict=True))
            return results

        fanout.__name__ = name
        return fanout


def get_vm_orchestrator(context: ExperimentRunCtx) -> VMLifecycleManager | MultiVMOrchestrator:
    """Return the VM lifecycle driver for this run.

    Single-VM playbooks (no ``playbook.machines``, or exactly one entry) get back
    a plain, unmodified ``VMLifecycleManager`` -- the exact object every existing
    call site already constructs and uses, so this is a zero-behavior-change path.
    Multi-machine playbooks get a ``MultiVMOrchestrator`` fanning the same calls
    out across one ``VMLifecycleManager`` per machine.

    QEMU-only for v1: every machine of a multi-machine playbook is expected to
    resolve to hypervisor_type == 'qemu' (enforced indirectly -- there is no
    libvirt `<network>` story for VirtualBox in this codebase).
    """
    machines_spec: dict[str, MachineSpec] | None = (
        getattr(context.playbook, 'machines', None) if context.playbook else None
    )

    if not machines_spec or len(machines_spec) <= 1:
        hypervisor = context.hypervisor_type or 'virtualbox'
        return VMLifecycleManager(hypervisor_type=hypervisor)

    machine_keys = list(machines_spec.keys())
    hypervisor_types = {context.machines[key].hypervisor_type for key in machine_keys}
    if hypervisor_types != {'qemu'}:
        raise LoggedException(
            log,
            "Multi-machine experiments require every machine's environment to use "
            f"the QEMU hypervisor; got: {hypervisor_types}",
        )

    return MultiVMOrchestrator(hypervisor_type='qemu', machine_keys=machine_keys)


def _boot_waves(machines: dict[str, MachineSpec]) -> list[list[str]]:
    """Topologically sort `machines` on `depends_on` into parallel-safe boot waves.

    Kahn's algorithm. Each returned wave is a list of machine keys with no
    dependency on each other or on any later wave; all of one wave's machines can
    boot concurrently once every earlier wave has finished. Phase 2: wire this
    into ``MultiVMOrchestrator``'s boot pipeline in place of today's plain
    machines-dict-order serial boot.

    Raises ``BootDependencyCycleError`` if `depends_on` contains a cycle.
    """
    remaining_deps = {key: set(spec.depends_on) for key, spec in machines.items()}
    for key, deps in remaining_deps.items():
        unknown = deps - machines.keys()
        if unknown:
            raise BootDependencyError(log, f"machine '{key}' depends_on unknown machine(s): {sorted(unknown)}")

    waves: list[list[str]] = []
    scheduled: set[str] = set()
    while len(scheduled) < len(machines):
        wave = sorted(key for key, deps in remaining_deps.items() if key not in scheduled and deps <= scheduled)
        if not wave:
            unresolved = sorted(set(machines.keys()) - scheduled)
            raise BootDependencyError(log, f"machines.depends_on has a cycle among: {unresolved}")
        waves.append(wave)
        scheduled.update(wave)

    return waves
