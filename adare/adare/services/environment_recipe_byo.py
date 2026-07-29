"""``adare env recipe-byo`` — convert a local recipe ISO path to consumer-supplied.

The ``publish-prepare`` analogue for recipe environments. A recipe with
``iso: /Users/someone/ISO/Win11_....iso`` is not publishable: the path is
meaningless on any other machine, and (for Windows) the ISO cannot lawfully be
rehosted at a URL either. This rewrites the descriptor into the BYO form —
``iso_name`` plus a plain-text ``iso_notes`` download pointer — so the consumer
supplies the ISO themselves and ``iso_sha256`` proves they got the right one.

Shipped with the feature rather than after it, because hand-editing the YAML is
precisely how the ``os.platform`` ↔ profile mismatch case gets created, and
several environments in the wild already carry absolute local ISO paths.

The recipe hash does not change: ``_recipe_identity`` folds neither ``iso`` nor
``iso_name``, since how a consumer obtained the ISO is not a build input. An
already-built disk therefore stays a build-cache hit. The *environment file*
hash does change — correctly, a different descriptor is a different descriptor.
"""

import logging
from pathlib import Path

from adare.core.dto.environment import EnvironmentInfo
from adare.core.result import Result
from adare.hypervisor.qemu.vm_creator.os_catalog import get_os_definition
from adare.services.recipe_contract import (
    ISO_NAME_RE,
    classify_iso_source,
    linux_url_hint,
    normalized_iso_sha256,
)

log = logging.getLogger(__name__)


def _find_environment_file(project_path: Path, name: str) -> Path | None:
    """Locate ``name``'s descriptor in the project, then in global storage."""
    from adare.backend.project.directory import ProjectDirectory
    from adare.config.configdirectory import ENVIRONMENTS_DIR

    # `ProjectDirectory.environments` currently resolves to the same global
    # ENVIRONMENTS_DIR, so dedupe rather than probing each path twice; listing both
    # keeps this correct if the project layout ever gains a local directory.
    directories = list(dict.fromkeys(
        [ProjectDirectory(project_path).environments, ENVIRONMENTS_DIR]
    ))
    for directory in directories:
        for ext in ('.yml', '.yaml'):
            candidate = directory / f'{name}{ext}'
            if candidate.is_file():
                return candidate
    return None


def recipe_byo(project_path: Path, name: str, iso_name: str | None = None,
               iso_notes: str | None = None) -> Result[EnvironmentInfo]:
    """Rewrite ``name``'s recipe ISO source into the consumer-supplied form.

    Args:
        project_path: Project whose environments directory is searched first.
        name: Environment name (descriptor stem).
        iso_name: Bare ISO filename. Defaults to the basename of the current
            ``iso`` value.
        iso_notes: Plain-text download pointer. Defaults to the OS profile's
            ``iso_notes``, so a Windows environment always ends up with one.

    Returns:
        ``Result[EnvironmentInfo]`` describing the rewritten descriptor.
    """
    from adare.types.environment import parse_environment_file
    from adarelib.helper.yaml import dict_to_yaml, yaml_to_dict

    env_file = _find_environment_file(project_path, name)
    if env_file is None:
        return Result.fail(
            code='EnvironmentFileNotFound',
            message=f'No environment descriptor found for "{name}".',
            solutions=['Run: adare env list', 'Check the name for typos'],
        )

    metadata = parse_environment_file(env_file)
    if metadata is None or metadata.recipe is None:
        return Result.fail(
            code='NotARecipeEnvironment',
            message=(
                f'"{name}" is not a recipe environment, so it has no ISO source to '
                f'convert. Use "adare env publish-prepare" for a baked environment.'
            ),
            solutions=['adare env publish-prepare ' + name + ' --vm-url <url>'],
        )

    recipe = metadata.recipe
    source = classify_iso_source(recipe)
    if source == 'byo':
        return Result.fail(
            code='AlreadyByoIso',
            message=(
                f'"{name}" already declares a consumer-supplied ISO '
                f'({recipe.iso_name!r}); nothing to convert.'
            ),
            solutions=['Edit recipe.iso_notes directly to change the download pointer'],
        )
    if source in ('both', 'none'):
        return Result.fail(
            code='AmbiguousIsoSource',
            message=(
                f'"{name}" declares {"both an iso and an iso_name" if source == "both" else "no ISO source"}; '
                f'fix the recipe block before converting.'
            ),
            solutions=['Leave exactly one of "iso" / "iso_name" in the recipe block'],
        )

    try:
        os_def = get_os_definition(recipe.profile)
    except KeyError:
        return Result.fail(
            code='UnknownOsProfileError',
            message=f'Recipe profile {recipe.profile!r} is not a known OS profile.',
            solutions=['Run: adare os-profile list'],
        )

    if os_def.platform != 'windows':
        return Result.fail(
            code='ByoIsoRequiresWindowsProfile',
            message=(
                f'Consumer-supplied ISOs are allowed for Windows profiles only; '
                f'{recipe.profile!r} is a {os_def.platform} profile. A Linux ISO is '
                f'freely redistributable, so publish it as a URL instead.'
            ),
            solutions=[linux_url_hint(recipe.profile).capitalize()],
        )

    resolved_name = (iso_name or Path(recipe.iso).name).strip()
    if not ISO_NAME_RE.match(resolved_name):
        return Result.fail(
            code='InvalidIsoName',
            message=(
                f'Cannot derive a valid bare ISO filename (got {resolved_name!r}): it '
                f"must have no directory separators, no '..', and end in '.iso'."
            ),
            solutions=[f'Pass one explicitly: adare env recipe-byo {name} '
                       f'--iso-name Win11_25H2_English_Arm64_v2.iso'],
        )

    digest = normalized_iso_sha256(recipe.iso_sha256)
    if not digest:
        return Result.fail(
            code='MissingIsoSha256Error',
            message=(
                'This recipe has no iso_sha256. For a consumer-supplied ISO the digest '
                'is the ONLY handle the consumer has on the correct file, so it cannot '
                'be omitted.'
            ),
            solutions=[f'shasum -a 256 {recipe.iso}',
                       'Add the result as recipe.iso_sha256, then re-run this command'],
        )

    # Surgical edit of the parsed YAML rather than re-serializing from the attrs
    # model: the descriptor may carry keys this tool has no opinion about, and
    # rewriting the whole file would silently drop or reorder them.
    env_dict = yaml_to_dict(env_file)
    recipe_block = env_dict.get('recipe') or {}
    previous_iso = recipe_block.pop('iso', '')
    recipe_block['iso_name'] = resolved_name
    resolved_notes = iso_notes if iso_notes is not None else os_def.iso_notes
    if resolved_notes:
        recipe_block['iso_notes'] = resolved_notes
    recipe_block['iso_sha256'] = digest
    env_dict['recipe'] = recipe_block
    dict_to_yaml(env_file, env_dict)

    log.info('Converted %s to a consumer-supplied ISO (%s)', env_file, resolved_name)
    return Result.ok(EnvironmentInfo(
        id='',
        name=name,
        description=metadata.description or '',
        vm_name=None,
        hypervisor=metadata.hypervisor,
        os_platform=os_def.platform,
        file_path=env_file,
        next_steps=[
            f'Confirm it still builds here: adare env load {env_file} --iso {previous_iso}'
            if previous_iso else f'Confirm it still builds here: adare env load {env_file}',
            f'Publish it: adare web submit environment {name}',
        ],
        tip=(
            f'Consumers need "{resolved_name}" (sha256 {digest[:12]}...) in '
            f'~/.adare/isos/. The recipe hash is unchanged, so any disk you have '
            f'already built stays a cache hit.'
        ),
    ))
