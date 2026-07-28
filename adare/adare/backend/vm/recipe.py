"""Recipe-based environment builds.

A *recipe* environment is defined by its build inputs — an OS profile, an
installer ISO plus its expected SHA256, an optional unattended-install template
override, build parameters, and optional build-time provisioning — rather than by
a frozen baked disk. This module orchestrates the recipe flow invoked from
:func:`adare.backend.environment.commands.environment_load`:

1. Resolve the OS profile and (if absent) synthesise the environment ``os``.
2. Enforce the ISO-source contract for a *consumer* (gate 5; see
   :mod:`adare.services.recipe_contract`), resolve the ISO to a local file, and
   verify its SHA256 matches ``recipe.iso_sha256`` (hard-fail on mismatch — an
   ISO change is always a *new* environment, never a silent refresh).
3. Compute the two build hashes (see
   :func:`adare.helperfunctions.hash.hash_recipe`).
4. If a VM with the recipe hash already exists and its disk is present, reuse it
   (build cache hit — no rebuild).
5. Otherwise build in two stages and register the result through
   :func:`adare.backend.vm.commands.load_vm_file_for_environment`, recording
   ``build_source='recipe'`` and the provenance columns.

Two-stage build, two-level cache
================================

::

    base_hash   = hash_recipe(iso_sha256, answer_file_hash, identity WITHOUT provision)
    recipe_hash = hash_recipe(iso_sha256, answer_file_hash, identity WITH    provision)

    Stage 1  base disk   RECIPE_BASE_CACHE_DIR/{profile}-recipebase-{base_hash[:12]}.qcow2
                         existing creator machinery, unchanged
    Stage 2  provision   overlay on base → boot with QGA → run steps → clean
                         shutdown → flatten
                         → VMS_DIR/{profile}-{recipe_hash[:12]}.qcow2

With no provision steps ``base_hash == recipe_hash``, Stage 2 is skipped, and the
result is byte-identical to the pre-provisioning behaviour.

Provisioning runs as a post-build stage *here* rather than as a
``BaseVMCreator`` phase, because ``BaseVMCreator.create()`` calls
``_cleanup_on_failure``, which deletes the disk — that would throw away a
two-hour Windows install on every failed MSI. With the base cached, a retry
(``--reprovision``) re-overlays in seconds. It also lets two recipes that differ
only in their provision lists (e.g. the Autopsy solr4 / solr8 environments) share
**one** Windows base build, and it leaves ``vm create`` untouched.

Integrity note: OS installs are never bit-reproducible, so the recipe hash is
anchored on the *inputs*. The produced disk is still hashed per run into
``Vm.hash`` for tamper detection.

Two kinds of post-install work, deliberately distinct:

* ``recipe.provision`` runs **once at build time** and is baked into the disk. For
  forensic work this is the point: installing software writes Prefetch, registry
  and MFT entries, so doing it per-run would contaminate the artifact set under
  measurement.
* ``postsetupinstallations`` keeps its exact previous meaning — applied inside
  every experiment run.

Both are folded into the recipe hash, so changing either yields a new
environment identity.
"""

import hashlib
import logging
import os
import shutil
from dataclasses import replace
from pathlib import Path
from urllib.parse import urlparse

import attrs

from adare.backend.environment.exceptions import EnvironmentLoadFailed
from adare.backend.vm import database as vm_database
from adare.backend.vm.provision import (
    ProvisionSchemaError,
    expand_provision,
    provision_identity,
)
from adare.config.configdirectory import (
    QEMU_CACHE_DIR,
    RECIPE_BASE_CACHE_DIR,
    RECIPE_BUILD_LOG_DIR,
    VM_TEMPLATES_DIR,
    VMS_DIR,
)
from adare.console import console, print_section, print_step
from adare.helperfunctions.hash import hash_file_sha256, hash_recipe, hash_string_sha256
from adare.helperfunctions.web.download import download
from adare.hypervisor.qemu.vm_creator.os_catalog import (
    OsDefinition,
    SetupLevel,
    default_host_cpus,
    get_os_definition,
)
from adare.services.recipe_contract import (
    RecipeContractError,
    check_recipe_publish_contract,
    classify_iso_source,
    normalized_iso_sha256,
)
from adare.types.environment import EnvironmentMetadata, OsInfo, ProvisionCommand, Recipe

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
                'Run: adare os-profile list',
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
                     postsetupinstallations: list,
                     provision_commands: list[ProvisionCommand] = ()) -> dict:
    """Build the order-insensitive identity dict for the recipe hash.

    Uses the *declared* params (``None`` where unset) rather than host-resolved
    defaults so the identity stays host-independent: e.g. an unspecified CPU
    count must not make the same recipe hash to a different value on a machine
    with a different core count.

    The ``'provision'`` key is added **only when the list is non-empty**. This is
    load-bearing, not tidiness: ``hash_dict_sha256`` is
    ``yaml.dump(sort_keys=True)``, so an unconditional ``'provision': []`` would
    change the digest of every recipe environment ever built and force full
    rebuilds. The golden-hash test guards it.

    Note also what is NOT folded in: ``iso`` / ``iso_name`` / ``iso_notes``. *How*
    a consumer obtained the ISO is not a build input — only which bytes they got,
    which ``iso_sha256`` already pins. Consequence, intended: the URL form and the
    BYO form of the same ISO share a recipe hash, so converting an environment to
    BYO is a build-cache hit rather than a rebuild.

    Args:
        provision_commands: The **expanded** command list, not the declared YAML.
            Hashing the expansion means refactoring 16 literal steps into an
            equivalent ``for_each`` does not invalidate a cached disk, while
            reordering the items does.
    """
    identity = {
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
    if provision_commands:
        identity['provision'] = provision_identity(list(provision_commands))
    return identity


def _expanded_provision(recipe: Recipe, os_def: OsDefinition) -> list[ProvisionCommand]:
    """Expand ``recipe.provision`` for *os_def*'s platform, or raise cleanly.

    Wraps the pure expander's :class:`ProvisionSchemaError` in the
    ``EnvironmentLoadFailed`` the CLI knows how to render. Called before any build
    starts, so a schema mistake costs seconds rather than hours.
    """
    if not recipe.provision:
        return []
    try:
        return expand_provision(recipe.provision, os_def.platform)
    except ProvisionSchemaError as e:
        raise EnvironmentLoadFailed(
            log,
            f'recipe provision block is invalid: {e}',
            possible_solutions=[
                'Fix the "provision" entry named in the message',
                'Inside a for_each group only {{ item }} is available',
            ],
        ) from e


def compute_recipe_hash(environment_metadata: EnvironmentMetadata) -> str:
    """Compute the recipe integrity anchor for an environment.

    Folds in build-time provisioning, so two environments differing only in their
    provision steps are different environments with different cached disks.

    Raises:
        EnvironmentLoadFailed: If the metadata has no recipe, or the provision
            block cannot be expanded.
    """
    recipe = environment_metadata.recipe
    if recipe is None:
        raise EnvironmentLoadFailed(log, 'compute_recipe_hash called on a non-recipe environment')
    os_def = _effective_os_def(recipe)
    return hash_recipe(
        iso_sha256=normalized_iso_sha256(recipe.iso_sha256),
        answer_file_hash=_answer_file_hash(os_def),
        identity=_recipe_identity(
            recipe, os_def, environment_metadata.postsetupinstallations,
            _expanded_provision(recipe, os_def),
        ),
    )


def compute_base_hash(environment_metadata: EnvironmentMetadata) -> str:
    """Compute the hash of the recipe's OS install *before* provisioning.

    This is the Stage 1 cache key. It equals :func:`compute_recipe_hash` exactly
    when there are no provision steps, and differs otherwise — which is what lets
    several recipes that share an OS install (same ISO, same answer file, same
    params) share one multi-hour base build.
    """
    recipe = environment_metadata.recipe
    if recipe is None:
        raise EnvironmentLoadFailed(log, 'compute_base_hash called on a non-recipe environment')
    os_def = _effective_os_def(recipe)
    return hash_recipe(
        iso_sha256=normalized_iso_sha256(recipe.iso_sha256),
        answer_file_hash=_answer_file_hash(os_def),
        identity=_recipe_identity(
            recipe, os_def, environment_metadata.postsetupinstallations,
        ),
    )


def resolve_iso_from_url(url: str) -> Path:
    """Download and cache an installer ISO from a URL into the QEMU cache dir.

    Mirrors :func:`adare.backend.environment.commands.resolve_vm_from_url` for
    recipe ISOs: caches by a URL-derived filename so repeated loads reuse the
    same download. Integrity is checked separately by :func:`_verify_iso`
    against ``recipe.iso_sha256`` after this returns.

    Raises:
        EnvironmentLoadFailed: If the download fails or produces an empty file.
    """
    iso_dir = QEMU_CACHE_DIR
    iso_dir.mkdir(parents=True, exist_ok=True)

    parsed_url = urlparse(url)
    original_filename = Path(parsed_url.path).name
    url_hash = hashlib.md5(url.encode()).hexdigest()[:8]

    if original_filename and original_filename.lower().endswith('.iso'):
        filename = f"{url_hash}_{original_filename}"
    else:
        filename = f"{url_hash}_downloaded.iso"

    cached_file_path = iso_dir / filename

    if cached_file_path.exists() and cached_file_path.stat().st_size > 0:
        log.info(f"Using cached ISO file: {cached_file_path}")
        return cached_file_path

    try:
        log.info(f"Downloading ISO from URL: {url}")
        download(url, cached_file_path, quiet=False)

        if not cached_file_path.exists() or cached_file_path.stat().st_size == 0:
            raise EnvironmentLoadFailed(
                log,
                f'Downloaded ISO file {cached_file_path} is empty or missing',
                possible_solutions=['Check if the URL is valid', 'Check network connectivity'],
            )

        log.info(f"Successfully downloaded ISO to: {cached_file_path}")
        return cached_file_path

    except (OSError, ConnectionError, TimeoutError, ValueError) as e:
        if cached_file_path.exists():
            cached_file_path.unlink()
        raise EnvironmentLoadFailed(
            log,
            f'Failed to download ISO from URL {url}: {e}',
            possible_solutions=[
                'Check if the URL is accessible',
                'Check network connectivity',
                'Ensure the URL points to a valid ISO file',
            ],
        ) from e


def _check_consumer_contract(recipe: Recipe, environment_metadata: EnvironmentMetadata,
                             os_def: OsDefinition) -> None:
    """Gate 5 — the authoritative consume-side ISO contract check.

    Resolves ``recipe.profile`` against *this* host's catalog, so a recipe that
    claims ``os.platform: windows`` over a Linux profile is rejected here even
    though it passed server ingest (which has no profile catalog and therefore
    cannot check it — see :mod:`adare.services.recipe_contract`).

    ``publishing=False``: a local ``iso`` path is perfectly legitimate for a
    consumer, and a non-canonical digest is harmless here because every consumer of
    ``iso_sha256`` normalizes on read. Only the publish gate insists on both.
    """
    declared_platform = (
        environment_metadata.os.platform if environment_metadata.os is not None else None
    )
    try:
        check_recipe_publish_contract(
            recipe, declared_platform, publishing=False,
        )
    except RecipeContractError as e:
        raise EnvironmentLoadFailed(
            log, str(e), possible_solutions=e.possible_solutions,
        ) from e


def _resolve_iso_path(recipe: Recipe, base_dir: Path | None,
                      os_def: OsDefinition,
                      iso_override: Path | None = None) -> Path:
    """Resolve the declared ISO source to a local path.

    Delegates to :mod:`adare.backend.vm.recipe_iso`: the URL/path form downloads
    or resolves relative to the environment file, and the BYO form searches the
    consumer's ISO locations by filename. Either way the returned path is a local
    file whose bytes :func:`_verify_iso` checks against ``recipe.iso_sha256``.
    """
    from adare.backend.vm.recipe_iso import resolve_byo_iso, resolve_url_iso

    if classify_iso_source(recipe) == 'byo':
        return resolve_byo_iso(recipe, os_def, iso_override=iso_override, base_dir=base_dir)
    return resolve_url_iso(recipe, base_dir, iso_override=iso_override)


def _verify_iso(recipe: Recipe, iso_path: Path) -> None:
    """Verify the ISO exists and matches the declared SHA256 (hard-fail)."""
    from adare.backend.vm.recipe_iso import verify_iso

    verify_iso(recipe, iso_path)


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


def _setup_level(recipe: Recipe) -> SetupLevel:
    """Resolve the recipe's declared setup level (default FULL)."""
    return (
        SetupLevel(recipe.params.setup_level)
        if recipe.params.setup_level is not None
        else SetupLevel.FULL
    )


def _build_disk(os_def: OsDefinition, recipe: Recipe, iso_path: Path,
                vm_name: str, force: bool, vm_dir: Path | None = None,
                allow_emulation: bool = False) -> Path:
    """Build the disk image using the existing creator machinery.

    Creator selection is delegated to :func:`vm_creator.dispatch.create_vm_disk`,
    the same function `adare vm create` uses. It must be shared: this function
    once dispatched on ``manual`` and then fell through to *platform*, so a recipe
    over a ``gui-auto`` / ``gui-script`` / ``playbook`` profile silently built via
    the seed-file ``linux_creator``.
    """
    from adare.hypervisor.qemu.vm_creator.dispatch import DispatchError, create_vm_disk

    try:
        return create_vm_disk(
            os_def=os_def,
            iso_path=iso_path,
            vm_name=vm_name,
            disk_size=recipe.params.disk_size,
            ram_mb=recipe.params.ram_mb,
            cpus=recipe.params.cpus,
            force=force,
            vm_dir=vm_dir,
            setup_level=_setup_level(recipe),
            allow_emulation=allow_emulation,
        )
    except DispatchError as e:
        raise EnvironmentLoadFailed(
            log,
            f'recipe build unsupported for profile {recipe.profile!r}: {e.title}',
            possible_solutions=e.next_steps,
        ) from e


def _preflight_provision(recipe: Recipe, os_def: OsDefinition,
                         commands: list[ProvisionCommand],
                         base_exists: bool) -> None:
    """Fail before any build starts if provisioning cannot possibly work.

    The point is that a mistake costs seconds, not a two-hour Windows install
    followed by a guaranteed failure.

    Checks:

    * ``setup_level: 0`` (bare) — the QEMU guest agent ships from level 1 (base)
      on, so there is nothing to talk to.
    * ``install_mode: manual`` — the build waits on a human at the console, which
      cannot be composed with unattended provisioning.
    * Free disk space, roughly: the base disk plus the declared disk size, because
      Stage 2 keeps the base and its overlay simultaneously and then writes the
      flattened output.
    """
    if not commands:
        return

    if int(_setup_level(recipe)) < int(SetupLevel.BASE):
        raise EnvironmentLoadFailed(
            log,
            "recipe.provision needs the QEMU guest agent, which is only installed "
            "from setup_level 1 (base) upwards; this recipe declares setup_level "
            f"{int(_setup_level(recipe))} (bare)",
            possible_solutions=[
                'Raise params.setup_level to 1 (base) or 2 (full)',
                'Or move the work to postsetupinstallations (runs per experiment run)',
            ],
        )

    if os_def.install_mode == 'manual':
        raise EnvironmentLoadFailed(
            log,
            f"recipe profile '{recipe.profile}' installs interactively "
            f"(install_mode: manual), which cannot be combined with unattended "
            f"build-time provisioning",
            possible_solutions=[
                'Use a profile with an unattended install mode',
                'Or build the disk by hand: adare env extend --interactive',
            ],
        )

    # Rough headroom estimate. The declared disk size is a virtual maximum, so
    # this deliberately over-asks rather than letting a 16-MSI build die at 90%.
    declared = recipe.params.disk_size or os_def.default_disk_size or '80G'
    try:
        needed_gb = float(declared.rstrip('Gg')) * (1.0 if base_exists else 1.5)
    except ValueError:
        needed_gb = 120.0
    # Measure on a directory that certainly exists: VMS_DIR itself is only created
    # in _provision_disk, i.e. after this preflight.
    probe_dir = next(
        (path for path in (VMS_DIR, VMS_DIR.parent, Path.home()) if path.is_dir()),
        Path.home(),
    )
    free_gb = shutil.disk_usage(probe_dir).free / (1024 ** 3)
    if free_gb < needed_gb:
        raise EnvironmentLoadFailed(
            log,
            f'not enough free disk space for a provisioned recipe build: about '
            f'{needed_gb:.0f} GB needed, {free_gb:.0f} GB free. Stage 2 holds the '
            f'base disk, its work overlay and the flattened output at the same time.',
            possible_solutions=[
                'Free space, or run: adare vm prune',
                f'Reduce params.disk_size (currently {declared})',
            ],
        )


def _build_base_disk(environment_metadata: EnvironmentMetadata, os_def: OsDefinition,
                     iso_path: Path, base_hash: str, force: bool,
                     allow_emulation: bool) -> Path:
    """Stage 1 — return the cached base disk, building it only if absent.

    Cached by ``base_hash`` in :data:`RECIPE_BASE_CACHE_DIR`, keyed on the recipe
    identity *without* provisioning. That is what lets two recipes over the same
    OS install share one build: the second one prints a cache-hit line and goes
    straight to Stage 2.

    **The cache entry is published by an atomic rename, never written in place.**
    The install runs against ``{base_name}.partial.qcow2`` and is moved onto the
    real cache name only after the creator returns successfully, so the presence of
    ``{base_name}.qcow2`` *implies* a completed OS install.

    Without that, an interrupted Stage 1 poisons the cache permanently: the very
    first thing the creator does is ``qemu-img create``, so a build killed at any
    point afterwards (SIGKILL, host crash, a failure outside the creator's own
    ``_cleanup_on_failure``) leaves an OS-less qcow2 sitting at exactly the path
    every later build treats as a hit. Those builds then skip the install, boot a
    disk with no operating system, and fail 15 minutes later with "the guest agent
    did not respond" — which is true, and says nothing about the real cause.
    Observed for real: a killed build left a 196 KB "base" that two later runs
    happily reused.
    """
    recipe = environment_metadata.recipe
    base_name = f'{recipe.profile}-recipebase-{base_hash[:12]}'
    base_path = RECIPE_BASE_CACHE_DIR / f'{base_name}.qcow2'

    print_section('Base disk (Stage 1/2)')
    if base_path.is_file() and not force:
        size = base_path.stat().st_size
        # Defence in depth for caches poisoned before the rename existed: the same
        # floor `BaseVMCreator._validate_disk_after_install` uses for "QEMU never
        # wrote to it". Cheap, and it cannot false-positive — no real OS install
        # fits in 1 MB.
        if size < 1_000_000:
            console.print(
                f'  [yellow]Discarding an unusable cached base disk[/yellow] '
                f'({size} bytes — no OS install could fit): {base_path}'
            )
            log.warning('Discarding truncated recipe base disk %s (%d bytes)',
                        base_path, size)
            base_path.unlink()
        else:
            console.print(
                f'  [green]Recipe base cache hit — reusing {base_path}[/green] '
                f'({size / (1024 ** 3):.1f} GB)'
            )
            console.print('  [dim]Skipping the OS install entirely.[/dim]')
            return base_path

    RECIPE_BASE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    console.print(f'  Building the base OS install (this takes a while): {base_name}')
    partial_name = f'{base_name}.partial'
    built = _build_disk(
        os_def, recipe, iso_path, partial_name, force=True,
        vm_dir=RECIPE_BASE_CACHE_DIR, allow_emulation=allow_emulation,
    )
    # Same directory, therefore the same filesystem, therefore atomic: a reader
    # either sees no cache entry or sees a complete one.
    os.replace(built, base_path)
    for suffix in ('-nvram.fd', '_install.log'):
        sibling = RECIPE_BASE_CACHE_DIR / f'{partial_name}{suffix}'
        if sibling.exists():
            os.replace(sibling, RECIPE_BASE_CACHE_DIR / f'{base_name}{suffix}')
    log.info('Published recipe base disk: %s', base_path)
    return base_path


def _provision_disk(base_path: Path, os_def: OsDefinition, recipe: Recipe,
                    commands: list[ProvisionCommand], recipe_hash: str,
                    allow_emulation: bool, force: bool) -> Path:
    """Stage 2 — provision *base_path* into the final recipe disk.

    Returns the flattened standalone disk. Raises rather than returning a
    partially-provisioned disk: the caller must reach
    ``load_vm_file_for_environment`` ONLY on complete success, or a disk would be
    registered — and would occupy this ``recipe_hash``'s cache slot — while
    lacking the contents its hash promises.
    """
    from adare.hypervisor.qemu.vm_creator.provision_creator import (
        RecipeProvisionError,
        run_provision,
    )

    dest_path = VMS_DIR / f'{recipe.profile}-{recipe_hash[:12]}.qcow2'
    if dest_path.exists():
        if not force:
            raise EnvironmentLoadFailed(
                log,
                f'a provisioned recipe disk already exists at {dest_path} but no VM '
                f'record references it',
                possible_solutions=[
                    'Rebuild over it: adare env load <env> --force',
                    'Or remove the orphaned file',
                ],
            )
        print_step(f'[yellow]Removing existing disk image[/yellow]: [dim]{dest_path}[/dim]')
        dest_path.unlink()

    VMS_DIR.mkdir(parents=True, exist_ok=True)
    build_log_path = RECIPE_BUILD_LOG_DIR / f'provision-{recipe_hash[:12]}.log'
    try:
        return run_provision(
            base_disk=base_path,
            dest_disk=dest_path,
            commands=commands,
            os_def=os_def,
            ram_mb=recipe.params.ram_mb or os_def.default_ram_mb,
            # `default_cpus` is 0 in several profiles, meaning "derive from the
            # host" — the same fallback the creators use.
            cpus=recipe.params.cpus or os_def.default_cpus or default_host_cpus(),
            build_log_path=build_log_path,
            allow_emulation=allow_emulation,
        )
    except RecipeProvisionError as e:
        # Never leave a half-provisioned artifact behind: it would look like a
        # valid cached disk for this recipe hash on the next load.
        dest_path.unlink(missing_ok=True)
        raise EnvironmentLoadFailed(
            log,
            f'build-time provisioning failed, so no environment was created: {e}',
            possible_solutions=[
                'Read the build log named in the message above',
                'Retry provisioning only (the base OS install is cached): '
                'adare env load <env> --reprovision',
                'Keep the failed overlay for post-mortem: '
                'ADARE_KEEP_FAILED_PROVISION=1 adare env load <env> --reprovision',
                'If one for_each item is at fault, bisect the list',
            ],
        ) from e


def build_or_reuse_recipe_vm(environment_metadata: EnvironmentMetadata,
                             project_path: Path | None = None,
                             base_dir: Path | None = None,
                             force: bool = False,
                             reprovision: bool = False,
                             iso_override: Path | None = None,
                             allow_emulation: bool = False) -> dict:
    """Build (or reuse a cached) disk for a recipe environment.

    Args:
        environment_metadata: Parsed environment metadata (``recipe`` set).
        project_path: Project path (VMs are global; passed through for the API).
        base_dir: Directory to resolve a relative ISO path against (the
            environment file's directory).
        force: Force rebuild / overwrite semantics from ``environment load``.
            Rebuilds BOTH stages.
        reprovision: Reuse the cached base disk but re-run Stage 2 from scratch.
            The retry path after a failed provisioning step — roughly an hour
            instead of three, because the OS install is not repeated.
        iso_override: ``--iso``: a file, or a directory to search for the ISO.
        allow_emulation: Permit QEMU TCG when the recipe's guest architecture does
            not match the host.

    Returns:
        Dict with ``vm_id`` and ``was_existing`` (matching
        :func:`load_vm_file_for_environment`).

    Raises:
        EnvironmentLoadFailed: On any contract, ISO, schema, or build failure. A
            partially-provisioned disk is never registered.
    """
    recipe = environment_metadata.recipe
    if recipe is None:
        raise EnvironmentLoadFailed(log, 'build_or_reuse_recipe_vm called on a non-recipe environment')

    os_def = _effective_os_def(recipe)
    _synthesize_os(environment_metadata, os_def)

    # Gate 5 — authoritative for consumption. Runs before the ISO is resolved so a
    # non-Windows BYO recipe fails on the contract, not on a confusing "file not
    # found" for an ISO it should never have been asked for.
    _check_consumer_contract(recipe, environment_metadata, os_def)

    # Everything that can fail cheaply fails here, before any multi-hour build:
    # provision schema, for_each rendering, duplicate names, setup level, free disk.
    commands = _expanded_provision(recipe, os_def)

    iso_path = _resolve_iso_path(recipe, base_dir, os_def, iso_override=iso_override)
    _verify_iso(recipe, iso_path)

    base_hash = compute_base_hash(environment_metadata)
    recipe_hash = compute_recipe_hash(environment_metadata)
    log.info(f'Recipe integrity hash: {recipe_hash} (base: {base_hash})')

    # Build cache: reuse an already-built disk for identical recipe inputs.
    # `--reprovision` deliberately bypasses this — its whole purpose is to redo
    # Stage 2 — while still reusing the Stage 1 base below.
    stale_record = False
    existing = vm_database.get_vm_by_recipe_hash(recipe_hash)
    if existing is not None and not (force or reprovision):
        if Path(existing.file).exists():
            log.info(f"Recipe cache hit — reusing VM '{existing.name}' (ID: {existing.id})")
            return {'vm_id': existing.id, 'was_existing': True}
        log.warning(
            f"Recipe VM '{existing.name}' matches recipe hash but its cached disk is missing "
            f"({existing.file}); rebuilding from the recipe."
        )
        stale_record = True

    base_candidate = RECIPE_BASE_CACHE_DIR / (
        f'{recipe.profile}-recipebase-{base_hash[:12]}.qcow2'
    )
    _preflight_provision(recipe, os_def, commands, base_exists=base_candidate.is_file())

    if not commands:
        # No provisioning: identical to the pre-provisioning behaviour, including
        # the disk's name and location. base_hash == recipe_hash here.
        vm_name = f'{recipe.profile}-{recipe_hash[:12]}'
        log.info(f'Building recipe disk (profile={recipe.profile}, name={vm_name})')
        disk_path = _build_disk(
            os_def, recipe, iso_path, vm_name, force=force or stale_record,
            allow_emulation=allow_emulation,
        )
    else:
        # `--force` rebuilds the base too; `--reprovision` explicitly keeps it.
        base_path = _build_base_disk(
            environment_metadata, os_def, iso_path, base_hash,
            force=force and not reprovision, allow_emulation=allow_emulation,
        )
        disk_path = _provision_disk(
            base_path, os_def, recipe, commands, recipe_hash,
            allow_emulation=allow_emulation, force=force or reprovision or stale_record,
        )

    from adare.backend.vm.commands import load_vm_file_for_environment
    return load_vm_file_for_environment(
        project_path=project_path,
        vm_path=disk_path,
        environment_metadata=environment_metadata,
        no_copy=False,  # keep the produced disk in managed, tamper-checkable storage
        force=force or reprovision or stale_record,
        build_source='recipe',
        recipe_hash=recipe_hash,
        iso_sha256=normalized_iso_sha256(recipe.iso_sha256),
        profile_name=recipe.profile,
    )


def rebuild_recipe_vm_by_id(vm_id: str, force: bool = True) -> str | None:
    """Rebuild a recipe VM whose cached disk went missing.

    Locates the environment that references ``vm_id``, re-parses its recipe, and
    rebuilds the disk — the recovery advantage a baked disk lacks. Returns the
    (possibly unchanged) VM id on success, or ``None`` if the VM is not a recipe
    VM or no referencing recipe environment can be found.

    Needs no provisioning-specific handling: it re-enters
    :func:`build_or_reuse_recipe_vm`, which replays both stages (reusing the
    cached base if it is still there).
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
