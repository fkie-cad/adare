"""Shared recipe publish/consume contract — the ISO-source rules in one place.

Companion to the shared recipe *builder* (:mod:`adare.services.environment_recipe`):
this module is the shared recipe *validator*. It imports only
:mod:`adare.types.environment` and the OS catalog, so ``webappaccess``,
``webapi``, ``services`` and ``backend/vm`` can all use it without an import
cycle.

Two ISO forms exist for a recipe environment:

* **URL form** — ``recipe.iso`` is an ``http(s)`` URL the publisher hosts.
* **BYO form** — ``recipe.iso_name`` is a bare filename the *consumer* supplies
  locally, with ``recipe.iso_notes`` carrying the download pointer. Allowed for
  **Windows profiles only**, because a Microsoft installer ISO cannot lawfully be
  rehosted; for Linux the ISO is freely redistributable and a published URL is a
  quality requirement.

``iso_sha256`` is required in **both** forms and is the actual integrity
boundary. The Windows-only restriction on BYO is a *quality* rule, not a security
boundary: see :func:`check_recipe_publish_contract` for where each gate sits and
which of them is authoritative.

Five gates enforce this contract, in two authoritative places:

===== ============================================== ==========================
Gate  Where                                          Role
===== ============================================== ==========================
1     ``webappaccess/experiment_export.py``          **Authoritative (publish)**
2     ``webapi/routes/environments.py``              local web-variant create
3     ``adare-web`` create-environment dialog        UX only, never trusted
4     server ``giteaeventmanager`` ingest            coarse filter, not a
                                                     trust boundary
5     ``backend/vm/recipe.py`` (consumer load)       **Authoritative (consume)**
===== ============================================== ==========================

Gate 4 cannot be made authoritative: the server has no OS-profile catalog
(``Recipe.profile`` is a free-form ``CharField``) and shipping a snapshot of the
client's was rejected because profiles are host-extensible — ``os_catalog``
merges ``~/.adare/os-profiles/*.yml`` *over* the built-ins, so a server-side
snapshot would false-reject legitimate custom profiles. A publisher who spoofs
``os.platform: windows`` over a Linux profile therefore passes gate 4, and is
rejected by gate 5 on *every* consumer — so the spoof buys an environment nobody
can build, and ``profile: ubuntu2404`` sitting next to ``platform: windows`` is
glaring in a PR diff.
"""

import re

from adare.hypervisor.qemu.vm_creator.os_catalog import get_os_definition
from adare.types.environment import Recipe

# A BYO `iso_name` is a bare filename and nothing else: no directory separators
# (either flavour), no `..`, no scheme, no drive letter, `.iso` required. The
# 200-char bound matches the server's `Recipe.iso_name` column.
#
# CONTRACT MIRROR — this regex must stay character-for-character identical in:
#   * here (client, authoritative for publish + consume)
#   * adare-server `giteaeventmanager/action/environment_contract.py`
#   * adare-web `src/components/dialogs/create-environment-dialog.tsx`
# Divergence between the three copies reintroduces exactly the bug class the
# `iso_sha256` letter-case mismatch documents (a value that passes publish and
# ingest but can never build). Same discipline as the sha256 and vm_format
# contract mirrors elsewhere in this tree.
ISO_NAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._+-]{0,199}\.iso$')

# Lowercase ONLY, deliberately. `iso_utils.verify_iso_hash` compares digests
# case-sensitively, so an uppercase digest that passes a case-insensitive gate
# produces an environment that can never build. Every gate normalizes with
# `normalized_iso_sha256` first and matches against this.
SHA256_HEX_RE = re.compile(r'^[0-9a-f]{64}$')


class RecipeContractError(ValueError):
    """A recipe violates the ISO-source contract.

    Carries ``possible_solutions`` so callers that render rich CLI errors can
    reuse them; ``str(e)`` alone is always a complete, self-contained message.
    """

    def __init__(self, message: str, possible_solutions: list[str] | None = None):
        super().__init__(message)
        self.possible_solutions = possible_solutions or []


def normalized_iso_sha256(value: str | None) -> str:
    """Normalize a declared ISO digest to the one form that can ever match.

    ``.strip().lower()``. Used by *every* consumer of ``iso_sha256`` — the
    publish gate, the ingest gate, the recipe hash, and the build-time
    verification — so that letter case cannot silently fork an environment's
    identity.

    History: the regexes in this tree disagreed. ``_preflight_environment`` and
    the server used ``re.IGNORECASE`` / ``[0-9a-fA-F]`` while the webapi and the
    web dialog were lowercase-only, and ``verify_iso_hash`` compares
    case-sensitively. An uppercase digest therefore passed publish *and* ingest
    and was then unbuildable forever. Normalizing on read and write closes that.
    """
    return (value or '').strip().lower()


def classify_iso_source(recipe: Recipe) -> str:
    """Classify the recipe's declared ISO source.

    Returns:
        ``'url'`` when ``iso`` is an ``http(s)`` URL, ``'path'`` when ``iso`` is
        set but is not a URL, ``'byo'`` when only ``iso_name`` is set,
        ``'both'`` when both are set, and ``'none'`` when neither is.

    ``'both'`` and ``'none'`` are contract violations rather than usable sources;
    they are classified rather than raised so each gate can word its own error.
    ``'none'`` in particular must be rejected loudly: cattrs silently ignores
    unknown keys, so a misspelled ``iso_nmae:`` parses cleanly and would
    otherwise look like "no ISO declared".
    """
    has_iso = bool((recipe.iso or '').strip())
    has_name = bool((recipe.iso_name or '').strip())
    if has_iso and has_name:
        return 'both'
    if has_name:
        return 'byo'
    if has_iso:
        return 'url' if recipe.iso.strip().startswith(('http://', 'https://')) else 'path'
    return 'none'


def profile_platform(profile: str) -> str | None:
    """Resolve an OS-profile name to its platform, or ``None`` if unknown.

    Resolves against *this host's* catalog, which includes any user profiles in
    ``~/.adare/os-profiles/``. ``None`` (rather than a raise) lets a caller
    distinguish "unknown profile" from "known profile, wrong platform" and word
    the two differently.
    """
    try:
        return get_os_definition(profile).platform
    except KeyError:
        return None


def linux_url_hint(profile: str) -> str:
    """A concrete "host it here" pointer for a non-Windows BYO attempt.

    Names the catalog's own published ISO URL for the profile when it has one, so
    the publisher is told the exact URL to use rather than merely that BYO is
    forbidden. Falls back to generic wording for a profile whose catalog entry
    carries no URL (e.g. the ARM64 Ubuntu profiles, where the user supplies the
    ISO themselves).
    """
    try:
        iso_url = get_os_definition(profile).iso_url
    except KeyError:
        iso_url = ''
    if iso_url:
        return f"use the published ISO URL for this profile: {iso_url}"
    return (
        "host the ISO at an http(s) URL and set 'iso' to it (this profile's "
        "catalog entry declares no download URL)"
    )


def check_recipe_publish_contract(
    recipe: Recipe,
    declared_platform: str | None = None,
    *,
    publishing: bool = True,
) -> None:
    """Enforce the full recipe ISO contract. The authoritative check.

    Used verbatim by gate 1 (publish preflight) and — with ``publishing=False`` —
    by gate 5 (consumer load).

    Two rules apply only when publishing, and both exist because a published
    artifact must be usable by clients this one knows nothing about:

    * a non-BYO ``iso`` must be an ``http(s)`` URL — a local filesystem path is
      meaningless to a consumer and must never leak into the shared repo;
    * ``iso_sha256`` must already be canonical (lowercase, unpadded). Consumers
      normalize on read, so a non-canonical digest builds fine *here*; but the
      server stores the value verbatim and an older client does not normalize, so
      publishing one would hand out an environment that cannot be built. Consuming
      is therefore lenient and publishing is strict.

    Args:
        recipe: The parsed ``recipe:`` block.
        declared_platform: ``metadata.os.platform`` as written in the
            environment file, when available. Checked against the profile's real
            platform **in both directions** — a mismatch either way means the
            file describes a system it does not build.
        publishing: True at the publish gate, False at the consume gate.

    Raises:
        RecipeContractError: With a message naming the offending field and, where
            useful, the exact ISO the consumer needs.
    """
    source = classify_iso_source(recipe)

    if source == 'both':
        raise RecipeContractError(
            f"recipe declares both 'iso' ({recipe.iso!r}) and 'iso_name' "
            f"({recipe.iso_name!r}); exactly one ISO source is allowed",
            possible_solutions=[
                "Publisher-hosted ISO: keep 'iso' and remove 'iso_name'",
                "Consumer-supplied ISO (Windows only): keep 'iso_name' and remove 'iso'",
            ],
        )
    if source == 'none':
        raise RecipeContractError(
            "recipe declares no ISO source: set either 'iso' (an http(s) URL to a "
            "hosted ISO) or 'iso_name' (a bare filename the consumer supplies, "
            "Windows profiles only)",
            possible_solutions=[
                "Check for a misspelled key — unknown recipe keys are silently ignored",
                'Run: adare env recipe-byo <name>   (to convert a local iso path to BYO)',
            ],
        )

    # --- digest: required, and lowercase-only after normalization -------------
    digest = normalized_iso_sha256(recipe.iso_sha256)
    if not digest:
        raise RecipeContractError(
            "recipe 'iso_sha256' is required: it is the only integrity anchor a "
            "consumer has for the ISO",
            possible_solutions=['Compute it with: shasum -a 256 <iso>'],
        )
    if not SHA256_HEX_RE.match(digest):
        raise RecipeContractError(
            f"recipe 'iso_sha256' must be 64 hex characters (got {recipe.iso_sha256!r})",
            possible_solutions=['Compute it with: shasum -a 256 <iso>'],
        )
    if publishing and (recipe.iso_sha256 or '') != digest:
        raise RecipeContractError(
            f"recipe 'iso_sha256' must be written in canonical form — lowercase, no "
            f"surrounding whitespace (got {recipe.iso_sha256!r}, expected {digest!r}). "
            f"This client normalizes on read, but the server stores the value "
            f"verbatim and older clients compare it case-sensitively, so a "
            f"non-canonical digest would publish an environment nobody can build.",
            possible_solutions=[
                f'Set iso_sha256 to: {digest}',
                'Or regenerate the descriptor: adare env recipe-byo <name>',
            ],
        )

    # --- profile must resolve, and must agree with the declared os.platform ---
    actual_platform = profile_platform(recipe.profile)
    if actual_platform is None:
        raise RecipeContractError(
            f"recipe 'profile' is not a known OS profile on this host: "
            f"{recipe.profile!r}",
            possible_solutions=[
                'Run: adare os-profile list',
                'Fix the "profile" field in the recipe block',
            ],
        )
    if declared_platform and declared_platform != actual_platform:
        raise RecipeContractError(
            f"environment 'os.platform' is {declared_platform!r} but recipe profile "
            f"{recipe.profile!r} builds a {actual_platform!r} system; the "
            f"environment file describes a system it does not build",
            possible_solutions=[
                f"Set os.platform to {actual_platform!r}",
                'Or choose a profile matching the declared platform',
            ],
        )

    # --- per-form rules ------------------------------------------------------
    if source == 'byo':
        if actual_platform != 'windows':
            raise RecipeContractError(
                f"consumer-supplied ISOs ('iso_name') are allowed for Windows "
                f"profiles only; profile {recipe.profile!r} is {actual_platform!r}. "
                f"A Linux ISO is freely redistributable, so it must be published: "
                f"{linux_url_hint(recipe.profile)}",
                possible_solutions=[
                    "Replace 'iso_name' with 'iso' set to an http(s) URL",
                ],
            )
        if not ISO_NAME_RE.match(recipe.iso_name.strip()):
            raise RecipeContractError(
                f"recipe 'iso_name' must be a bare ISO filename (got "
                f"{recipe.iso_name!r}): no directory separators, no '..', no URL, "
                f"no drive letter, must end in '.iso', at most 200 characters",
                possible_solutions=[
                    "Use just the filename, e.g. 'Win11_25H2_English_Arm64_v2.iso'",
                    "The consumer locates the file themselves — a publisher's path is meaningless to them",
                ],
            )
        if recipe.iso_notes and len(recipe.iso_notes) > 1000:
            raise RecipeContractError(
                f"recipe 'iso_notes' exceeds 1000 characters "
                f"(got {len(recipe.iso_notes)})",
                possible_solutions=['Shorten iso_notes to a download pointer'],
            )
        return

    if source == 'path' and publishing:
        raise RecipeContractError(
            f"recipe 'iso' must be an http(s) URL to publish (got a local path: "
            f"{recipe.iso!r}); a local filesystem path is meaningless to a consumer "
            f"and must never reach the shared repo",
            possible_solutions=[
                'Host the ISO and reference its URL',
                'Windows only: run "adare env recipe-byo <name>" to convert it to a '
                'consumer-supplied ISO instead',
            ],
        )
