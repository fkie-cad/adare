"""Read-only view of an environment descriptor file, for display (list / detail).

Kept apart from ``show_service`` so that module stays small and so the "one bad file must
never break the whole list" guarantee lives in one place.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class EnvSource:
    """What an environment YAML says about where its disk comes from."""

    vm: str = ""
    vm_type: str = ""
    vm_sha256: str = ""
    source_profile: str = ""
    source_iso_sha256: str = ""
    recipe: dict[str, Any] | None = None


_EMPTY = EnvSource()


def parse_env_source(file: str | None) -> EnvSource:
    """Parse an environment YAML file into an :class:`EnvSource`.

    Best-effort: a missing or unparseable file yields an empty ``EnvSource`` so the list
    still renders. A recipe environment has no baked ``vm`` but carries a ``recipe`` dict
    (profile, iso, disk_size, ram_mb, cpus, ...). ``source_profile`` / ``source_iso_sha256``
    are optional, informational provenance of a baked source.
    """
    if not file:
        return _EMPTY
    env_path = Path(file)
    if not env_path.exists():
        return _EMPTY
    try:
        from adare.exceptions import DataStructuringError
        from adare.types.environment import parse_environment_file

        metadata = parse_environment_file(env_path)
    except (OSError, ValueError, DataStructuringError, yaml.YAMLError) as e:
        # A single malformed file must never break the whole list.
        log.warning(f"Could not parse environment source from {env_path}: {e}")
        return _EMPTY
    if metadata is None:
        return _EMPTY

    recipe = None
    if metadata.recipe is not None:
        r = metadata.recipe
        recipe = {
            'profile': r.profile,
            'iso': r.iso,
            'iso_name': r.iso_name,
            'iso_sha256': r.iso_sha256,
            'template': r.template,
            'setup_level': r.params.setup_level,
            'disk_size': r.params.disk_size,
            'ram_mb': r.params.ram_mb,
            'cpus': r.params.cpus,
            'arch': r.params.arch,
        }
    return EnvSource(
        vm=metadata.vm or "",
        vm_type=metadata.vm_type or "",
        vm_sha256=metadata.vm_sha256 or "",
        source_profile=metadata.source_profile or "",
        source_iso_sha256=metadata.source_iso_sha256 or "",
        recipe=recipe,
    )


def os_label(osinfo_os: str, osinfo_distribution: str, osinfo_version: str = "", os_info: str = "") -> str:
    """Human OS label for an environment: ``"Ubuntu 24.04"``.

    Uses the registered VM's OS name plus its distribution (falling back to the version when
    there is no distribution) and, for a VM without an OS name, the raw ``os_info`` string.
    """
    label = osinfo_os
    # Append the release only when the OS name doesn't already carry it: a VM's OS name is
    # often the full product name ("Ubuntu 25.10", distribution "ubuntu").
    for release in (osinfo_distribution, osinfo_version):
        if release and release.lower() not in (label or "").lower():
            label = f"{label} {release}" if label else release
            break
    return label or os_info
