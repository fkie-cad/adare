"""
Environment Recipe Service - shared YAML builder for environment descriptors.

Extracted from `adare.cli.vm_create` so both the CLI and the webapi can emit
the same environment YAML (recipe or baked) without duplicating the assembly
logic. Field names/types must match `adare.types.environment.EnvironmentMetadata`
exactly — the publishing server validates the emitted YAML against a mirror of
those rules in `giteaeventmanager/action/environment_contract.py`.

The shared *validator* for the recipe ISO contract lives alongside this shared
*builder*, in :mod:`adare.services.recipe_contract`.
"""
import logging
from pathlib import Path

from adare.backend.project.directory import ProjectDirectory
from adare.console import print_step
from adare.helperfunctions.hash import hash_file_sha256
from adare.hypervisor.qemu.vm_creator.os_catalog import OsDefinition, SetupLevel
from adare.services.recipe_contract import normalized_iso_sha256
from adarelib.helper.yaml import dict_to_yaml

log = logging.getLogger(__name__)


def _os_block(os_def: OsDefinition) -> dict:
    """Build the shared `os:` block emitted by both recipe and baked envs."""
    return {
        'os': os_def.display_name,
        'platform': os_def.platform,
        'distribution': os_def.distribution_label or os_def.distribution,
        'version': os_def.version,
        'language': 'English',
        'architecture': os_def.architecture,
    }


def _placeholder_os_block() -> dict:
    """A stand-in ``os:`` block for baked-URL envs created without a profile.

    Baked create has never asked for OS details (the disk is opaque), but the
    publishing server still needs an ``os:`` block to store the environment.
    Mirrors the values in the ``environment.yml`` create template so the analyst
    edits the same placeholder afterwards.
    """
    return {
        'os': 'Windows 10',
        'platform': 'windows',
        'distribution': 'Home',
        'version': '21H1',
        'language': 'English',
    }


def _target_env_path(env_name: str, project_path: Path | None) -> Path:
    """Resolve the environment YAML's target path.

    With no `project_path` this mirrors the CLI's original behavior of
    writing next to the caller (cwd). Callers that supply `project_path`
    (e.g. `environment_service.create()`) get the project's managed
    environments directory instead.
    """
    if project_path is not None:
        target_dir = ProjectDirectory(project_path).environments
        target_dir.mkdir(parents=True, exist_ok=True)
        return target_dir / f'{env_name}.yml'
    return Path.cwd() / f'{env_name}.yml'


def build_recipe_environment_file(
    *,
    os_name: str,
    os_def: OsDefinition,
    iso_path: Path | str | None,
    iso_sha256: str,
    setup_level: SetupLevel,
    disk_size: str | None,
    ram: int | None,
    cpus: int | None,
    arch: str | None,
    env_name: str,
    project_path: Path | None = None,
    byo_iso: bool = False,
    iso_name: str | None = None,
    iso_notes: str | None = None,
) -> Path:
    """Generate a declarative recipe environment YAML.

    The disk is NOT built here — `adare environment load` builds it once from
    these inputs and caches it (keyed on the recipe hash). Only user-specified
    params are written so profile defaults keep flowing and the recipe identity
    stays host-independent.

    Args:
        byo_iso: Emit the consumer-supplied ISO form (``iso_name`` + ``iso_notes``)
            instead of ``iso``. Windows profiles only — enforced by the gates in
            :mod:`adare.services.recipe_contract`, not here.
        iso_name: Bare ISO filename for the BYO form. Defaults to
            ``iso_path``'s basename.
        iso_notes: Plain-text download pointer. Defaults to the OS profile's
            ``iso_notes``, so a publisher who says nothing still gives the
            consumer somewhere to go.
    """
    params: dict = {'setup_level': int(setup_level)}
    if disk_size:
        params['disk_size'] = disk_size
    if ram:
        params['ram_mb'] = ram
    if cpus:
        params['cpus'] = cpus
    if arch:
        params['arch'] = arch

    recipe_block: dict = {
        'profile': os_name,
        # Normalize on write: `verify_iso_hash` compares case-sensitively, so an
        # uppercase digest would pass every gate and then never build.
        'iso_sha256': normalized_iso_sha256(iso_sha256),
    }
    if byo_iso:
        resolved_name = iso_name or (Path(iso_path).name if iso_path else '')
        recipe_block['iso_name'] = resolved_name
        notes = iso_notes if iso_notes is not None else os_def.iso_notes
        if notes:
            recipe_block['iso_notes'] = notes
    else:
        recipe_block['iso'] = str(iso_path)
    if os_def.template:
        recipe_block['template'] = os_def.template
    recipe_block['params'] = params

    env_content = {
        'vm_type': 'recipe',
        'hypervisor': 'qemu',
        'recipe': recipe_block,
        'os': _os_block(os_def),
    }

    env_path = _target_env_path(env_name, project_path)
    dict_to_yaml(env_path, env_content)
    return env_path


def build_baked_environment_file(
    *,
    disk_path: Path,
    os_def: OsDefinition,
    vm_name: str,
    env_name: str | None = None,
    project_path: Path | None = None,
) -> Path:
    """Generate an environment YAML file for a baked (already-built) VM disk.

    Hashes the disk into `vm_sha256` so a later `environment load` from a
    published URL can verify the downloaded disk hasn't been tampered with.
    """
    print_step(f'Hashing disk for integrity (this may take a while for large disks): [dim]{disk_path}[/dim]')
    vm_sha256 = hash_file_sha256(disk_path)

    env_content = {
        'vm': str(disk_path),
        'vm_type': 'path',
        'vm_sha256': vm_sha256,
        'os': _os_block(os_def),
        'hypervisor': 'qemu',
    }

    filename = env_name or vm_name
    env_path = _target_env_path(filename, project_path)
    dict_to_yaml(env_path, env_content)
    return env_path


def build_baked_url_environment_file(
    *,
    vm_url: str,
    vm_sha256: str,
    env_name: str,
    project_path: Path | None = None,
    os_def: OsDefinition | None = None,
    vm_format: str | None = None,
) -> Path:
    """Generate an environment YAML for a baked VM hosted at a published URL.

    Unlike :func:`build_baked_environment_file`, nothing is hashed here — the
    disk lives remotely and the analyst supplies its expected ``vm_sha256`` (the
    BYO-URL model). The result is publish-ready: ``vm`` is an ``http(s)`` URL,
    ``vm_type`` is ``url``, and ``vm_sha256`` is carried through for the
    download-time integrity check on ``environment load``.

    ``vm_format`` (qcow2/ova/vmdk/vdi/img/raw) is written when supplied; it names
    the download cache file and picks the validator/hypervisor for URLs that
    carry no disk extension (owncloud/Nextcloud share links).

    When no ``os_def`` is given a placeholder ``os:`` block is emitted (baked
    create has never collected OS details), which the analyst edits afterwards.
    """
    env_content = {
        'vm': vm_url,
        'vm_type': 'url',
        'vm_sha256': vm_sha256,
        'os': _os_block(os_def) if os_def is not None else _placeholder_os_block(),
        'hypervisor': 'qemu',
    }
    if vm_format:
        env_content['vm_format'] = vm_format

    env_path = _target_env_path(env_name, project_path)
    dict_to_yaml(env_path, env_content)
    return env_path
