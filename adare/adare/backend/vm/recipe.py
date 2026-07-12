"""Recipe-based environment builds.

A *recipe* environment is defined by its build inputs — an OS profile, a
user-supplied installer ISO plus its expected SHA256, an optional
unattended-install template override, and build parameters — rather than by a
frozen baked disk. This module orchestrates the recipe flow invoked from
:func:`adare.backend.environment.commands.environment_load`:

1. Resolve the OS profile and (if absent) synthesise the environment ``os``.
2. Verify the ISO exists and its SHA256 matches ``recipe.iso_sha256`` (hard-fail
   on mismatch — an ISO change is always a *new* environment, never a silent
   refresh).
3. Compute the recipe integrity hash (see
   :func:`adare.helperfunctions.hash.hash_recipe`).
4. If a VM with that recipe hash already exists and its disk is present, reuse
   it (build cache hit — no rebuild).
5. Otherwise build the disk with the existing creator machinery and register it
   through :func:`adare.backend.vm.commands.load_vm_file_for_environment`,
   recording ``build_source='recipe'`` and the provenance columns.

Integrity note: OS installs are never bit-reproducible, so the recipe hash is
anchored on the *inputs*. The produced disk is still hashed per run into
``Vm.hash`` for tamper detection. Post-install steps reuse the existing
``postsetupinstallations`` field (applied at experiment time as today) and are
folded into the recipe hash, so changing them yields a new environment identity.
"""

import logging
from dataclasses import replace
from pathlib import Path

import attrs

from adare.backend.environment.exceptions import EnvironmentLoadFailed
from adare.backend.vm import database as vm_database
from adare.config.configdirectory import VM_TEMPLATES_DIR
from adare.helperfunctions.hash import hash_file_sha256, hash_recipe, hash_string_sha256
from adare.hypervisor.qemu.vm_creator.iso_utils import verify_iso_hash
from adare.hypervisor.qemu.vm_creator.os_catalog import (
    OsDefinition,
    SetupLevel,
    get_os_definition,
)
from adare.types.environment import EnvironmentMetadata, OsInfo, Recipe

log = logging.getLogger(__name__)

# Built-in template directory (shared by both creators). Autounattend templates
# for Windows are keyed by profile name when no explicit override is given.
_BUILTIN_TEMPLATES_DIR = (
    Path(__file__).parent.parent.parent
    / 'hypervisor' / 'qemu' / 'vm_creator' / 'templates'
)
_AUTOUNATTEND_MAP = {
    'windows11': 'autounattend_win11.xml',
    'windows10': 'autounattend_win10.xml',
}


def _effective_os_def(recipe: Recipe) -> OsDefinition:
    """Resolve the OS profile and apply recipe overrides (template, arch)."""
    try:
        os_def = get_os_definition(recipe.profile)
    except KeyError as e:
        raise EnvironmentLoadFailed(
            log,
            f"recipe profile '{recipe.profile}' is not a known OS profile: {e}",
            possible_solutions=[
                'Run: adare manage os-profile list',
                'Fix the "profile" field in the recipe block',
            ],
        ) from e

    overrides = {}
    if recipe.template:
        overrides['template'] = recipe.template
    if recipe.params.arch:
        overrides['architecture'] = recipe.params.arch
    return replace(os_def, **overrides) if overrides else os_def


def _resolve_answer_template(os_def: OsDefinition) -> Path | None:
    """Locate the unattended-install template file for hashing.

    Searches the user template directory first, then the built-in templates.
    Returns ``None`` for manual installs (no answer file) or when no template is
    found — the caller then folds a sentinel into the hash instead.
    """
    template_name = os_def.template or None
    if template_name is None:
        if os_def.platform == 'windows':
            template_name = _AUTOUNATTEND_MAP.get(os_def.name)
        elif os_def.install_mode != 'manual':
            # Linux auto installs resolve via the autoinstall discovery map.
            from adare.hypervisor.qemu.vm_creator.autoinstall import resolve_template
            template_name = resolve_template(os_def)

    if not template_name:
        return None

    for base in (VM_TEMPLATES_DIR, _BUILTIN_TEMPLATES_DIR):
        candidate = base / template_name
        if candidate.is_file():
            return candidate
    return None


def _answer_file_hash(os_def: OsDefinition) -> str:
    """Hash the install procedure (template source) that defines the build.

    We hash the *template source* rather than the fully-rendered answer file:
    the Linux autoinstall render injects a random password salt, so the rendered
    output is not deterministic and would break build caching. The template
    source captures the install procedure (including user overrides), and every
    render-affecting parameter is captured separately in the identity dict.
    """
    template_path = _resolve_answer_template(os_def)
    if template_path is not None:
        return hash_file_sha256(template_path)
    # No answer file (manual install, or template not found): fold a stable
    # sentinel so the hash still varies with the declared template name.
    return hash_string_sha256(f'no-template:{os_def.template or os_def.name}')


def _recipe_identity(recipe: Recipe, os_def: OsDefinition,
                     postsetupinstallations: list) -> dict:
    """Build the order-insensitive identity dict for the recipe hash.

    Uses the *declared* params (``None`` where unset) rather than host-resolved
    defaults so the identity stays host-independent: e.g. an unspecified CPU
    count must not make the same recipe hash to a different value on a machine
    with a different core count.
    """
    return {
        'profile': recipe.profile,
        'platform': os_def.platform,
        'distribution': os_def.distribution,
        'version': os_def.version,
        'architecture': os_def.architecture,
        'installer': os_def.installer,
        'install_mode': os_def.install_mode,
        'template': os_def.template or '',
        'params': attrs.asdict(recipe.params),
        'post_install': [
            {
                'name': inst.name,
                'command': inst.command,
                'description': inst.description,
                'cwd': inst.cwd,
                'shell': inst.shell,
            }
            for inst in postsetupinstallations
        ],
    }


def compute_recipe_hash(environment_metadata: EnvironmentMetadata) -> str:
    """Compute the recipe integrity anchor for an environment.

    Raises:
        EnvironmentLoadFailed: If the metadata has no recipe or the ISO hash is
            missing / does not match the ISO file.
    """
    recipe = environment_metadata.recipe
    if recipe is None:
        raise EnvironmentLoadFailed(log, 'compute_recipe_hash called on a non-recipe environment')
    os_def = _effective_os_def(recipe)
    return hash_recipe(
        iso_sha256=recipe.iso_sha256,
        answer_file_hash=_answer_file_hash(os_def),
        identity=_recipe_identity(recipe, os_def, environment_metadata.postsetupinstallations),
    )


def _resolve_iso_path(recipe: Recipe, base_dir: Path | None) -> Path:
    """Resolve the ISO path (absolute, or relative to the environment file)."""
    iso_path = Path(recipe.iso)
    if not iso_path.is_absolute() and base_dir is not None:
        iso_path = (base_dir / recipe.iso)
    return iso_path


def _verify_iso(recipe: Recipe, iso_path: Path) -> None:
    """Verify the ISO exists and matches the declared SHA256 (hard-fail)."""
    if not recipe.iso_sha256:
        raise EnvironmentLoadFailed(
            log,
            'recipe environments require an explicit "iso_sha256"',
            possible_solutions=[
                'Add the expected SHA256 of the ISO to the recipe block',
                "Compute it with: shasum -a 256 <iso>",
            ],
        )
    if not iso_path.exists():
        raise EnvironmentLoadFailed(
            log,
            f'recipe ISO not found: {iso_path}',
            possible_solutions=[
                'Check the "iso" path in the recipe block',
                'Use an absolute path, or place the ISO next to the environment file',
            ],
        )
    if not verify_iso_hash(iso_path, recipe.iso_sha256):
        raise EnvironmentLoadFailed(
            log,
            f'ISO SHA256 mismatch for {iso_path}: declared iso_sha256 does not match the file.',
            possible_solutions=[
                'A changed ISO is a NEW environment — update iso_sha256 to the new ISO hash',
                'Verify you supplied the correct ISO for this environment',
            ],
        )


def _synthesize_os(environment_metadata: EnvironmentMetadata, os_def: OsDefinition) -> None:
    """Populate ``environment_metadata.os`` from the profile when omitted."""
    if environment_metadata.os is not None:
        return
    environment_metadata.os = OsInfo(
        os=os_def.display_name,
        platform=os_def.platform,
        distribution=os_def.distribution_label or os_def.distribution,
        version=os_def.version,
        language='English',
        architecture=os_def.architecture,
    )


def _build_disk(os_def: OsDefinition, recipe: Recipe, iso_path: Path,
                vm_name: str, force: bool) -> Path:
    """Build the disk image using the existing creator machinery."""
    setup_level = (
        SetupLevel(recipe.params.setup_level)
        if recipe.params.setup_level is not None
        else SetupLevel.FULL
    )
    common = {
        'os_def': os_def,
        'vm_name': vm_name,
        'disk_size': recipe.params.disk_size,
        'ram_mb': recipe.params.ram_mb,
        'cpus': recipe.params.cpus,
        'force': force,
        'vm_dir': None,  # recipe builds always land in managed VM storage
        'setup_level': setup_level,
    }

    if os_def.install_mode == 'manual':
        from adare.hypervisor.qemu.vm_creator.manual_creator import create_manual_vm
        return create_manual_vm(iso_path=iso_path, **common)
    if os_def.platform == 'linux':
        from adare.hypervisor.qemu.vm_creator.linux_creator import create_linux_vm
        return create_linux_vm(iso_path=iso_path, **common)
    if os_def.platform == 'windows':
        from adare.hypervisor.qemu.vm_creator.windows_creator import create_windows_vm
        return create_windows_vm(iso_path=iso_path, **common)
    raise EnvironmentLoadFailed(log, f'recipe build unsupported for platform: {os_def.platform}')


def build_or_reuse_recipe_vm(environment_metadata: EnvironmentMetadata,
                             project_path: Path | None = None,
                             base_dir: Path | None = None,
                             force: bool = False) -> dict:
    """Build (or reuse a cached) disk for a recipe environment.

    Args:
        environment_metadata: Parsed environment metadata (``recipe`` set).
        project_path: Project path (VMs are global; passed through for the API).
        base_dir: Directory to resolve a relative ISO path against (the
            environment file's directory).
        force: Force rebuild / overwrite semantics from ``environment load``.

    Returns:
        Dict with ``vm_id`` and ``was_existing`` (matching
        :func:`load_vm_file_for_environment`).
    """
    recipe = environment_metadata.recipe
    if recipe is None:
        raise EnvironmentLoadFailed(log, 'build_or_reuse_recipe_vm called on a non-recipe environment')

    os_def = _effective_os_def(recipe)
    _synthesize_os(environment_metadata, os_def)

    iso_path = _resolve_iso_path(recipe, base_dir)
    _verify_iso(recipe, iso_path)

    recipe_hash = hash_recipe(
        iso_sha256=recipe.iso_sha256,
        answer_file_hash=_answer_file_hash(os_def),
        identity=_recipe_identity(recipe, os_def, environment_metadata.postsetupinstallations),
    )
    log.info(f'Recipe integrity hash: {recipe_hash}')

    # Build cache: reuse an already-built disk for identical recipe inputs.
    stale_record = False
    existing = vm_database.get_vm_by_recipe_hash(recipe_hash)
    if existing is not None:
        if Path(existing.file).exists():
            log.info(f"Recipe cache hit — reusing VM '{existing.name}' (ID: {existing.id})")
            return {'vm_id': existing.id, 'was_existing': True}
        log.warning(
            f"Recipe VM '{existing.name}' matches recipe hash but its cached disk is missing "
            f"({existing.file}); rebuilding from the recipe."
        )
        stale_record = True

    vm_name = f'{recipe.profile}-{recipe_hash[:12]}'
    log.info(f'Building recipe disk (profile={recipe.profile}, name={vm_name})')
    disk_path = _build_disk(os_def, recipe, iso_path, vm_name, force=force or stale_record)

    from adare.backend.vm.commands import load_vm_file_for_environment
    return load_vm_file_for_environment(
        project_path=project_path,
        vm_path=disk_path,
        environment_metadata=environment_metadata,
        no_copy=False,  # keep the produced disk in managed, tamper-checkable storage
        force=force or stale_record,
        build_source='recipe',
        recipe_hash=recipe_hash,
        iso_sha256=recipe.iso_sha256,
        profile_name=recipe.profile,
    )


def rebuild_recipe_vm_by_id(vm_id: str, force: bool = True) -> str | None:
    """Rebuild a recipe VM whose cached disk went missing.

    Locates the environment that references ``vm_id``, re-parses its recipe, and
    rebuilds the disk — the recovery advantage a baked disk lacks. Returns the
    (possibly unchanged) VM id on success, or ``None`` if the VM is not a recipe
    VM or no referencing recipe environment can be found.
    """
    vm_record = vm_database.get_vm_by_id(vm_id)
    if not vm_record or getattr(vm_record, 'build_source', 'baked') != 'recipe':
        return None

    from adare.database.api.environment import EnvironmentDbApi
    from adare.types.environment import parse_environment_file

    # Read attributes inside the session (get_environments returns attached objects).
    with EnvironmentDbApi() as db:
        env_refs = [
            (env.name, env.file)
            for env in db.get_environments()
            if getattr(env, 'vm_id', None) == vm_id
        ]

    for env_name, env_file_str in env_refs:
        env_file = Path(env_file_str)
        if not env_file.exists():
            continue
        metadata = parse_environment_file(env_file)
        if metadata is None or metadata.recipe is None:
            continue
        log.info(f"Rebuilding recipe VM '{vm_record.name}' from environment '{env_name}'")
        result = build_or_reuse_recipe_vm(
            metadata, base_dir=env_file.parent, force=force,
        )
        return result.get('vm_id')

    log.warning(f"No recipe environment found referencing VM {vm_id}; cannot rebuild.")
    return None
