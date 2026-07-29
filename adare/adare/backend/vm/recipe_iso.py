"""Consumer-side ISO resolution and verification for recipe environments.

Split out of :mod:`adare.backend.vm.recipe` (which was already at the edge of
this project's file-size budget) and covers everything between "the environment
file names an ISO" and "here is a local file whose bytes hash-match".

Two forms:

* **URL form** (``recipe.iso``) — an ``http(s)`` URL is downloaded and cached; a
  local path is used as-is.
* **BYO form** (``recipe.iso_name``) — the publisher named a file the consumer
  must already own. Windows only: Microsoft installer media cannot lawfully be
  rehosted, so for Windows the publisher ships the *recipe* and the consumer
  brings the ISO.

Whichever form, ``recipe.iso_sha256`` is verified against the actual bytes before
any build starts. That digest — not the filename, not the URL — is the integrity
boundary.
"""

import logging
import os
from pathlib import Path

from adare.backend.environment.exceptions import EnvironmentLoadFailed
from adare.config.configdirectory import ISO_DIR, QEMU_CACHE_DIR
from adare.hypervisor.qemu.vm_creator.iso_utils import iso_sha256 as compute_iso_sha256
from adare.hypervisor.qemu.vm_creator.iso_utils import verify_iso_hash
from adare.hypervisor.qemu.vm_creator.os_catalog import OsDefinition
from adare.services.recipe_contract import ISO_NAME_RE, normalized_iso_sha256
from adare.types.environment import Recipe

log = logging.getLogger(__name__)

# Environment variable naming an extra directory to search for a BYO ISO.
ISO_DIR_ENV = 'ADARE_ISO_DIR'


def resolve_byo_iso(recipe: Recipe, os_def: OsDefinition,
                    iso_override: Path | None = None,
                    base_dir: Path | None = None) -> Path:
    """Locate the consumer-supplied ISO named by ``recipe.iso_name``.

    Search order, first **existing** file wins:

    1. ``iso_override`` (``--iso``) — a file, or a directory to look inside.
    2. ``$ADARE_ISO_DIR/<iso_name>``
    3. ``~/.adare/isos/<iso_name>`` (:data:`ISO_DIR`)
    4. ``<environment file's directory>/<iso_name>`` — matches how a local
       ``recipe.iso`` relative path already resolves.
    5. ``~/.adare/qemu/cache/<iso_name>`` — where a URL-form ISO would have been
       cached, so a consumer who previously built the URL form of the same ISO
       gets a hit.

    Deliberately NOT implemented: an interactive prompt (``environment load``
    runs headless in CI and in download-and-run), and "if exactly one ``*.iso``
    sits in :data:`ISO_DIR`, use it" — silently building from the wrong ISO is the
    one failure that must never be silent. The digest check would catch it, but
    only after a multi-GB read, and the error would name the wrong problem.

    Raises:
        EnvironmentLoadFailed: If ``iso_name`` is not a bare filename, or the file
            cannot be found in any searched location. The not-found error names
            the required file, its digest, the profile, the publisher's download
            pointer, and every path searched.
    """
    iso_name = (recipe.iso_name or '').strip()

    # Validated BEFORE touching the filesystem: a traversal attempt must not get
    # as far as a stat() call on the path it constructed.
    if not ISO_NAME_RE.match(iso_name):
        raise EnvironmentLoadFailed(
            log,
            f"recipe 'iso_name' must be a bare ISO filename (got {recipe.iso_name!r}): "
            f"no directory separators, no '..', no URL, no drive letter, must end "
            f"in '.iso'",
            possible_solutions=[
                "Fix 'iso_name' in the recipe block to just the filename",
                'The consumer locates the file themselves, so a path from the '
                'publisher\'s machine is meaningless here',
            ],
        )

    searched: list[Path] = []

    if iso_override is not None:
        override = Path(iso_override).expanduser()
        if override.is_dir():
            candidate = override / iso_name
            searched.append(candidate)
            if candidate.is_file():
                return candidate
        else:
            # An explicit --iso FILE is honoured whatever it is called: the
            # digest, not the filename, decides whether it is the right ISO.
            searched.append(override)
            if override.is_file():
                return override

    env_dir = os.environ.get(ISO_DIR_ENV)
    search_dirs: list[Path] = []
    if env_dir:
        search_dirs.append(Path(env_dir).expanduser())
    search_dirs.append(ISO_DIR)
    if base_dir is not None:
        search_dirs.append(base_dir)
    search_dirs.append(QEMU_CACHE_DIR)

    for directory in search_dirs:
        candidate = directory / iso_name
        searched.append(candidate)
        if candidate.is_file():
            log.info('Resolved consumer-supplied ISO: %s', candidate)
            return candidate

    notes = (recipe.iso_notes or '').strip() or (os_def.iso_notes or '').strip()
    notes_block = f'\n\nWhere to get it:\n{notes}' if notes else ''
    searched_block = '\n'.join(f'  - {path}' for path in searched)
    raise EnvironmentLoadFailed(
        log,
        f"this environment is built from a consumer-supplied ISO that is not on "
        f"this machine.\n\n"
        f"  required file: {iso_name}\n"
        f"  sha256:        {normalized_iso_sha256(recipe.iso_sha256)}\n"
        f"  os profile:    {recipe.profile} ({os_def.display_name})"
        f"{notes_block}\n\n"
        f"Searched:\n{searched_block}",
        possible_solutions=[
            f'Put the ISO at: {ISO_DIR / iso_name}',
            'Or pass its location: adare env load <env> --iso /path/to/'
            f'{iso_name}   (a directory also works)',
            f'Or point {ISO_DIR_ENV} at the directory holding your ISOs',
            f'Confirm you have the right file: shasum -a 256 {iso_name}',
        ],
    )


def resolve_url_iso(recipe: Recipe, base_dir: Path | None,
                    iso_override: Path | None = None) -> Path:
    """Resolve the publisher-declared ``recipe.iso`` to a local path.

    An ``http(s)`` value is downloaded and cached (the web variant's
    published-URL model); anything else is treated as a local path, absolute or
    relative to the environment file. ``iso_override`` (``--iso``) wins over both
    so a consumer can point at a file they already have instead of re-downloading
    several gigabytes.
    """
    if iso_override is not None:
        override = Path(iso_override).expanduser()
        if override.is_file():
            log.info('Using --iso override instead of the declared recipe ISO: %s', override)
            return override
        if override.is_dir():
            candidate = override / Path(recipe.iso).name
            if candidate.is_file():
                log.info('Using --iso directory match: %s', candidate)
                return candidate

    if recipe.iso.startswith(('http://', 'https://')):
        from adare.backend.vm.recipe import resolve_iso_from_url
        return resolve_iso_from_url(recipe.iso)

    iso_path = Path(recipe.iso).expanduser()
    if not iso_path.is_absolute() and base_dir is not None:
        iso_path = base_dir / recipe.iso
    return iso_path


def verify_iso(recipe: Recipe, iso_path: Path) -> None:
    """Verify the ISO exists and its bytes match ``recipe.iso_sha256``. Hard-fail.

    Order matters: the "no digest declared" check comes FIRST because
    :func:`verify_iso_hash` returns ``True`` for an empty expectation (it treats a
    missing hash as "nothing to check"). Reaching it with an empty
    ``iso_sha256`` would therefore pass verification on any file at all.
    """
    declared = normalized_iso_sha256(recipe.iso_sha256)
    if not declared:
        raise EnvironmentLoadFailed(
            log,
            'recipe environments require an explicit "iso_sha256"',
            possible_solutions=[
                'Add the expected SHA256 of the ISO to the recipe block',
                'Compute it with: shasum -a 256 <iso>',
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
    if not verify_iso_hash(iso_path, declared):
        # Name both digests. `verify_iso_hash` already hashed the file, but it
        # only returns a bool, and re-hashing a 5 GB ISO purely to print the
        # actual value is the kind of avoidable minutes-long pause that makes
        # people stop reading error messages.
        actual = compute_iso_sha256(iso_path)
        raise EnvironmentLoadFailed(
            log,
            f'ISO SHA256 mismatch for {iso_path}:\n'
            f'  declared iso_sha256: {declared}\n'
            f'  actual file sha256:  {actual}',
            possible_solutions=[
                'A changed ISO is a NEW environment — update iso_sha256 to the new ISO hash',
                'Verify you supplied the correct ISO for this environment',
            ],
        )
