"""
Environment Recipe Service - shared YAML builder for environment descriptors.

Extracted from `adare.cli.vm_create` so both the CLI and the webapi can emit
the same environment YAML (recipe or baked) without duplicating the assembly
logic. Field names/types must match `CONTRACT.md` exactly — the publishing
server validates against them byte-for-byte.
"""
import logging
from pathlib import Path

from adare.backend.project.directory import ProjectDirectory
from adare.console import print_step
from adare.helperfunctions.hash import hash_file_sha256
from adare.hypervisor.qemu.vm_creator.os_catalog import OsDefinition, SetupLevel
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
    iso_path: Path,
    iso_sha256: str,
    setup_level: SetupLevel,
    disk_size: str | None,
    ram: int | None,
    cpus: int | None,
    arch: str | None,
    env_name: str,
    project_path: Path | None = None,
) -> Path:
    """Generate a declarative recipe environment YAML.

    The disk is NOT built here — `adare environment load` builds it once from
    these inputs and caches it (keyed on the recipe hash). Only user-specified
    params are written so profile defaults keep flowing and the recipe identity
    stays host-independent.
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
        'iso': str(iso_path),
        'iso_sha256': iso_sha256,
    }
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
