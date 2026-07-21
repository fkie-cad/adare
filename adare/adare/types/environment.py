# external imports
# configure logging
import logging
from pathlib import Path
from typing import Literal

import attrs
import cattrs

from adare.exceptions import DataStructuringError
from adarelib.helper.yaml import yaml_to_dict

log = logging.getLogger(__name__)


@attrs.define
class PostsetupInstallations:
    """
    Class to store information about installations that should be done after boot but before the experiment.
    """
    name: str
    command: str
    description: str | None = ''
    cwd: str | None = ''
    shell: bool = attrs.field(default=False)


@attrs.define
class OsInfo:
    """
    Operating system information for environments.
    """
    os: str
    platform: Literal['windows', 'linux']
    distribution: str
    version: str = ''
    language: str = ''
    architecture: str = ''
    details: str = ''


@attrs.define
class RecipeParams:
    """
    Optional build parameters for a recipe environment.

    Any field left as ``None`` falls back to the OS profile default at build
    time. These values participate in the recipe integrity hash, so changing
    any of them yields a new environment identity (a fresh build).
    """
    disk_size: str | None = None
    ram_mb: int | None = None
    cpus: int | None = None
    arch: str | None = None
    setup_level: int | None = None


@attrs.define
class Recipe:
    """
    Declarative build recipe for an environment.

    Instead of anchoring integrity on a frozen baked disk (``Vm.hash``), a
    recipe environment is defined by its *build inputs*: an OS profile, a
    user-supplied installer ISO plus its expected SHA256, an optional
    unattended-install template override, and build parameters. "Same inputs →
    forensically equivalent system"; the produced disk is still hashed per run
    into ``Vm.hash`` for tamper detection, but the reproducible identity is the
    recipe hash (see :func:`adare.helperfunctions.hash.hash_recipe`).

    Post-install steps reuse the existing ``postsetupinstallations`` field on
    :class:`EnvironmentMetadata`; those are folded into the recipe hash so a
    change to them also produces a new environment identity.
    """
    profile: str            # resolves via os_catalog.get_os_definition
    iso: str                # path to the user-supplied installer ISO
    iso_sha256: str         # expected SHA256 of the ISO (hard-checked at build)
    template: str | None = None   # optional Autounattend/autoinstall override
    params: RecipeParams = attrs.Factory(RecipeParams)


@attrs.define
class EnvironmentMetadata:
    """
    Consolidated class to store the configuration of an environment.

    Supports both modern VM-based environments (with OVA files) and legacy Vagrant-based environments.

    Hypervisor Configuration:
        The hypervisor_config field allows hypervisor-specific settings:

        QEMU hypervisor supports:
        - boot_mode: 'bios' or 'uefi' (default: auto-detected based on OS)
            - Windows VMs automatically use 'uefi'
            - Linux VMs automatically use 'bios'
            - Override with explicit boot_mode setting

        Example environment YAML:
            vm: windows-10
            os:
              platform: windows
              os: Windows 10
            hypervisor: qemu
            hypervisor_config:
              boot_mode: uefi  # Optional: override auto-detection
    """
    vm: str | None = None
    os: OsInfo | None = None

    # Expected SHA256 of the disk referenced by `vm` (baked envs only). When
    # `vm` resolves to a URL, this is checked against the downloaded file's
    # actual hash on load; absent/empty skips the check (back-compat for local
    # `path` envs). URL sources REQUIRE it (verified after download).
    vm_sha256: str | None = None

    # Disk-image format hint for a baked URL source. Required when the URL has no
    # recognized disk extension (e.g. an owncloud `.../s/TOKEN/download` share
    # link); optional when the URL already ends in one. Names the download cache
    # file and selects the validator/hypervisor without relying on a URL suffix.
    vm_format: Literal['qcow2', 'ova', 'vmdk', 'vdi', 'img', 'raw'] | None = None

    name: str | None = None
    postsetupinstallations: list[PostsetupInstallations] = attrs.Factory(list)
    tags: list[str] = attrs.Factory(list)
    description: str = attrs.Factory(str)

    vm_type: Literal["auto", "path", "url", "recipe"] = "auto"

    # Declarative build recipe (recipe environments only). When set, the disk
    # is built on load from these inputs instead of referencing a baked disk.
    # In recipe mode ``os`` is optional and derived from ``recipe.profile``.
    recipe: Recipe | None = None

    # Hypervisor configuration
    hypervisor: str = "virtualbox"  # Default hypervisor
    hypervisor_config: dict = attrs.Factory(dict)  # Hypervisor-specific configuration

    # Legacy Vagrant-based environment fields (for backward compatibility)
    vagrantbox: str | None = None

    def __attrs_post_init__(self):
        """Validate that a VM source (baked disk, recipe, or vagrantbox) is specified."""
        if self.vm_type == "recipe" and self.recipe is None:
            raise ValueError("vm_type 'recipe' requires a 'recipe' block")
        if not self.vm and not self.vagrantbox and self.recipe is None:
            raise ValueError("One of 'vm', 'recipe', or 'vagrantbox' must be specified")

    @property
    def is_vagrant_environment(self) -> bool:
        """Check if this is a legacy Vagrant-based environment."""
        return self.vagrantbox is not None

    @property
    def is_recipe_environment(self) -> bool:
        """Check if this environment is built from a declarative recipe."""
        return self.recipe is not None

    @property
    def is_vm_environment(self) -> bool:
        """Check if this is a modern VM-based environment (baked disk or recipe)."""
        return self.vm is not None or self.recipe is not None


def parse_environment_file(environment_file: Path) -> EnvironmentMetadata|None:
    environment_dict = yaml_to_dict(environment_file)
    try:
        environment = cattrs.structure(environment_dict, EnvironmentMetadata)
    except cattrs.BaseValidationError as e:
        error_msg = "\n".join(cattrs.transform_error(e))
        raise DataStructuringError(
            log,
            message=f'parsing errors while parsing environment file {environment_file}:{error_msg}',
            possible_solutions=[
                'fix the structure of the environment file',
            ]
        ) from e
    return environment
