"""
Backend orchestration for `adare environment extend`.

Declarative mode builds a new environment YAML that references the SAME
base VM disk as the source (environment or VM) plus a merged, deduped set
of post-setup installations, then hands off to the existing
`environment_load` primitive. Because the base disk is unchanged, its hash
matches the existing `Vm` row, so `environment_load` reuses that row and
only creates a new `Environment` + its installations — the source
environment, its `Vm`, and its installations are never mutated.

Interactive/manual mode (Mode B) is a placeholder for a later task.
"""
import logging
import tempfile
from pathlib import Path

import attrs
import cattrs

from adare.backend.environment.commands import environment_load
from adare.backend.environment.database import resolve_environment_identifier
from adare.backend.environment.exceptions import EnvironmentDoesNotExistInDatabase
from adare.backend.vm.database import get_vm_by_name
from adare.database.api.environment import EnvironmentDbApi
from adare.exceptions import DataStructuringError
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
                'hypervisor': env.vm.hypervisor or env.hypervisor or 'qemu',
                'os': os_dict,
                'installations': [_installation_dict(inst) for inst in env.installations],
                'tags': [tag.name for tag in env.tags],
                'description': env.description or '',
            }

    vm = get_vm_by_name(source, fields=['file', 'hypervisor', 'osinfo'])
    if vm:
        return {
            'vm_file': vm['file'],
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


def environment_extend(request) -> tuple[str, bool]:
    """
    Extend `request.source` into a new environment `request.name`, reusing
    the same base VM disk and merging in additional post-setup installs.

    Declarative mode only. Return shape mirrors `environment_load`.

    Args:
        request: EnvironmentExtendRequest

    Returns:
        Tuple of (environment_ulid, created).

    Raises:
        NotImplementedError: If `request.interactive` is set (Mode B is a
            later task).
        EnvironmentDoesNotExistInDatabase: If the source cannot be resolved.
        EnvironmentAlreadyExists / EnvironmentUpdateError / EnvironmentLoadFailed:
            Propagated from `environment_load`.
    """
    if request.interactive:
        raise NotImplementedError('Interactive extend is implemented in a later task')

    source_view = _resolve_source(request.source)

    installations = _merged_installations(
        source_view['installations'], request.installs, request.from_file,
        request.shell, request.cwd
    )
    tags = list(dict.fromkeys([*source_view['tags'], *request.tags]))

    environment_content = {
        'name': request.name,
        'vm': source_view['vm_file'],
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
