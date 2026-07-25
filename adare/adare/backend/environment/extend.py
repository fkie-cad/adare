"""
Backend orchestration for `adare environment extend`.

Declarative mode builds a new environment YAML that references the SAME
base VM disk as the source (environment or VM) plus a merged, deduped set
of post-setup installations, then hands off to the existing
`environment_load` primitive. Because the base disk is unchanged, its hash
matches the existing `Vm` row, so `environment_load` reuses that row and
only creates a new `Environment` + its installations — the source
environment, its `Vm`, and its installations are never mutated.

Interactive/manual mode (Mode B) boots a throwaway overlay of the base disk
in a GUI QEMU window, lets the user install software by hand, then flattens
the overlay into a NEW standalone qcow2 (fresh hash) and registers it as a new
base VM + environment via the same `environment_load` primitive. QEMU only.
"""
import logging
import tempfile
from pathlib import Path

import attrs
import cattrs
from sqlalchemy.exc import SQLAlchemyError

from adare.backend.environment.commands import environment_load
from adare.backend.environment.database import resolve_environment_identifier
from adare.backend.environment.exceptions import EnvironmentDoesNotExistInDatabase
from adare.backend.vm.database import get_vm_by_name
from adare.database.api.environment import EnvironmentDbApi
from adare.exceptions import DataStructuringError
from adare.hypervisor.exceptions import HypervisorException
from adare.types.environment import PostsetupInstallations, parse_environment_file
from adarelib.helper.yaml import dict_to_yaml, yaml_to_dict

log = logging.getLogger(__name__)


def _os_dict(osinfo) -> dict:
    """Build the environment-file `os:` block from an OsInfo row, or a
    minimal default if the source has no osinfo attached."""
    if not osinfo:
        return {'os': '', 'platform': 'linux', 'distribution': ''}
    return {
        'os': osinfo.os or '',
        'platform': osinfo.platform or 'linux',
        'distribution': osinfo.distribution or '',
        'version': osinfo.version or '',
        'language': osinfo.language or '',
        'architecture': osinfo.architecture or '',
    }


def _installation_dict(installation) -> dict:
    """Convert a PostSetupInstallation row (or PostsetupInstallations attrs
    instance) to the plain dict shape used in the generated YAML."""
    return {
        'name': installation.name,
        'command': installation.command,
        'description': installation.description or '',
        'cwd': installation.cwd or '',
        'shell': bool(installation.shell),
    }


def _resolve_source(source: str) -> dict:
    """
    Resolve `source` as an environment (name or ULID) or, failing that, a VM
    name. Returns a plain dict describing the base disk, OS, hypervisor, and
    any installs/tags/description to carry forward.

    All ORM relationship access happens inside the DB session so the
    returned dict is fully detached-safe.

    Raises:
        EnvironmentDoesNotExistInDatabase: If `source` matches neither an
            environment nor a VM.
    """
    env_ulid = resolve_environment_identifier(source, trigger_exception=False)
    if env_ulid:
        with EnvironmentDbApi() as db:
            env = db.get_environment_by_ulid(env_ulid)
            if not env or not env.vm:
                raise EnvironmentDoesNotExistInDatabase(
                    log,
                    f'Environment "{source}" has no base VM to extend from',
                )

            os_dict = _os_dict(env.vm.osinfo)
            if not env.vm.osinfo and env.file:
                # Legacy VM without osinfo - fall back to the source's own
                # environment file for OS metadata.
                try:
                    os_dict = attrs.asdict(parse_environment_file(Path(env.file)).os)
                except (OSError, DataStructuringError) as e:
                    log.warning(f'Could not fall back to source environment file for OS info: {e}')

            return {
                'vm_file': env.vm.file,
                'vm_id': env.vm.id,
                'hypervisor': env.vm.hypervisor or env.hypervisor or 'qemu',
                'os': os_dict,
                'installations': [_installation_dict(inst) for inst in env.installations],
                'tags': [tag.name for tag in env.tags],
                'description': env.description or '',
            }

    vm = get_vm_by_name(source, fields=['file', 'hypervisor', 'osinfo', 'id'])
    if vm:
        return {
            'vm_file': vm['file'],
            'vm_id': vm.get('id'),
            'hypervisor': vm.get('hypervisor') or 'qemu',
            'os': _os_dict(vm.get('osinfo')),
            'installations': [],
            'tags': [],
            'description': '',
        }

    raise EnvironmentDoesNotExistInDatabase(
        log,
        f'Source "{source}" not found as an environment name/ULID or VM name',
        possible_solutions=[
            'List available environments with: adare env list',
            'List available VMs with: adare vm list',
        ]
    )


def _merged_installations(existing: list[dict], installs: list[tuple[str, str]],
                          from_file: Path | None, shell: bool, cwd: str | None) -> list[dict]:
    """
    Merge the source's existing installs with new ones from --install and
    --from-file, deduped by name (later entries win). Existing installs are
    inserted first so the result is a strict superset of the source.
    """
    merged: dict[str, dict] = {inst['name']: inst for inst in existing}

    for name, command in installs:
        merged[name] = {
            'name': name,
            'command': command,
            'description': '',
            'cwd': cwd or '',
            'shell': shell,
        }

    if from_file:
        file_installs = cattrs.structure(yaml_to_dict(from_file), list[PostsetupInstallations])
        for inst in file_installs:
            merged[inst.name] = _installation_dict(inst)

    return list(merged.values())


def _finalize_environment(request, vm_file: str, source_view: dict,
                          installations: list[dict], tags: list[str]) -> tuple[str, bool]:
    """
    Build the new environment YAML referencing `vm_file`, write it to a temp
    file, and hand off to `environment_load`. Shared by both modes; the only
    thing that differs is `vm_file` (the source base for declarative mode, the
    freshly-flattened disk for interactive mode).

    Returns:
        Tuple of (environment_ulid, created).
    """
    environment_content = {
        'name': request.name,
        'vm': vm_file,
        'os': source_view['os'],
        'hypervisor': source_view['hypervisor'],
        'postsetupinstallations': installations,
        'tags': tags,
        'description': request.description or source_view['description'],
    }

    with tempfile.TemporaryDirectory() as tmp_dir:
        yaml_path = Path(tmp_dir) / f'{request.name}.yml'
        dict_to_yaml(yaml_path, environment_content)
        return environment_load(str(yaml_path), force=request.force, no_copy=False)


def _warn_if_base_in_use(vm_id: str | None) -> None:
    """Log a warning if the base VM has active `VmInstance` rows.

    The interactive overlay reads the base read-only through its backing chain,
    so this is advisory rather than blocking. Any DB hiccup degrades to a
    warning rather than aborting the extend.
    """
    if not vm_id:
        return
    from adare.database.api.vm import VmApi
    try:
        with VmApi() as api:
            active = api.get_vm_instances_for_vm(vm_id, status='active')
    except SQLAlchemyError as e:
        log.warning('Could not check for active VM instances on the base disk: %s', e)
        return
    if active:
        log.warning(
            'Base VM has %d active instance(s). The interactive overlay reads '
            'the base read-only, so this is safe, but note the base is in use.',
            len(active),
        )


def _interactive_extend(request, source_view: dict, installations: list[dict],
                        tags: list[str]) -> tuple[str | None, bool]:
    """
    Interactive/manual extend (Mode B), QEMU only.

    Boots a throwaway overlay of the base disk in a GUI window. If the user
    chooses to store, flattens the result into a new standalone qcow2 and
    registers that disk as a NEW base VM + environment. If the user discards,
    nothing is created and `(None, False)` is returned. See
    `hypervisor/qemu/vm_creator/extend_creator.py`.

    Returns:
        Tuple of (environment_ulid, created), or `(None, False)` when the user
        discarded the session (no environment created).

    Raises:
        HypervisorException: If the source is not a QEMU environment, or the
            overlay/boot/flatten step fails (caught cleanly by the service).
    """
    if source_view['hypervisor'] != 'qemu':
        raise HypervisorException(
            f"Interactive extend is QEMU-only (source hypervisor is "
            f"'{source_view['hypervisor']}')."
        )

    # Imported lazily so the declarative path never pulls in the QEMU creator.
    from adare.hypervisor.qemu.vm_creator.extend_creator import run_interactive_extend

    base_disk = Path(source_view['vm_file'])
    dest = Path.cwd() / f'{request.disk_name or request.name}.qcow2'

    _warn_if_base_in_use(source_view.get('vm_id'))

    store, recorded = run_interactive_extend(
        base_disk, dest, source_view['os'], request.ram, request.cpus,
        console=request.console, compress=request.compress,
    )

    # User discarded the session: nothing was flattened or written. Signal "no
    # environment created" with the (None, False) sentinel.
    if not store:
        return None, False

    # Fold the commands typed in the console into the recorded installs (dedup by
    # name, later wins) so the new environment is reproducible declaratively.
    if recorded:
        merged = {inst['name']: inst for inst in installations}
        for inst in recorded:
            merged[inst['name']] = inst
        installations = list(merged.values())

    return _finalize_environment(request, str(dest), source_view, installations, tags)


def environment_extend(request) -> tuple[str | None, bool]:
    """
    Extend `request.source` into a new environment `request.name`.

    Declarative mode reuses the SAME base disk plus merged post-setup installs.
    Interactive mode (`request.interactive`, QEMU only) boots an overlay of the
    base for manual customization; on store it flattens into a NEW standalone
    disk and registers that as a new base VM, on discard it creates nothing.
    Both modes may also carry `--install` entries. Return shape mirrors
    `environment_load`.

    Args:
        request: EnvironmentExtendRequest

    Returns:
        Tuple of (environment_ulid, created). Interactive mode returns
        `(None, False)` when the user discarded the session (nothing created).

    Raises:
        EnvironmentDoesNotExistInDatabase: If the source cannot be resolved.
        HypervisorException: Interactive mode on a non-QEMU source, or a QEMU
            overlay/boot/flatten failure.
        EnvironmentAlreadyExists / EnvironmentUpdateError / EnvironmentLoadFailed:
            Propagated from `environment_load`.
    """
    source_view = _resolve_source(request.source)

    installations = _merged_installations(
        source_view['installations'], request.installs, request.from_file,
        request.shell, request.cwd
    )
    tags = list(dict.fromkeys([*source_view['tags'], *request.tags]))

    if request.interactive:
        return _interactive_extend(request, source_view, installations, tags)

    return _finalize_environment(request, source_view['vm_file'], source_view, installations, tags)
