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
class ProvisionCommand:
    """One build-time provisioning command, run in the guest via the QEMU guest agent.

    Build-time is the whole point: unlike :class:`PostsetupInstallations` (which
    runs inside *every* experiment run) a provision command runs exactly once,
    while the recipe disk is being built. For forensic work that difference is
    load-bearing -- installing software writes Prefetch / registry / MFT entries,
    so doing it per-run would contaminate the very artifact set under measurement.

    Success is decided by the **exit code** alone (``allow_exit_codes``), never by
    stderr being empty: PowerShell writes CLIXML progress records to stderr even
    on a fully successful command.

    Attributes:
        name: Unique step name. Also the host-log label and the error identity, so
            it must survive ``for_each`` expansion as a unique string.
        command: The command text, interpreted by ``shell``.
        description: Free text for the operator. Deliberately NOT part of the
            recipe hash -- a typo in prose must not cost a multi-hour rebuild.
        cwd: Working directory, folded in as a leading ``cd`` (each guest-exec is
            an independent process).
        shell: Interpreter. ``auto`` resolves to ``powershell`` on Windows guests
            and ``bash`` elsewhere (see
            :func:`adare.backend.vm.provision.resolve_shell`).
        allow_exit_codes: Exit codes treated as success. Defaults to ``[0]``;
            Windows installers commonly also need ``3010`` ("reboot required").
        verify: Optional second command run after ``command`` succeeds. A non-zero
            exit fails the build -- this is how a step asserts it actually did
            something, rather than trusting an installer's exit code.
        log_files: Guest paths pulled to the host build-log directory when the
            step fails. Also excluded from the recipe hash (they cannot affect
            the disk).
        timeout_minutes: Per-step wall-clock budget.
        reboot: Reboot the guest and wait for the agent again after this step.
    """
    name: str
    command: str = ''
    description: str | None = ''
    cwd: str | None = ''
    shell: Literal['powershell', 'cmd', 'bash', 'auto'] = 'auto'
    allow_exit_codes: list[int] = attrs.Factory(lambda: [0])
    verify: str | None = None
    log_files: list[str] = attrs.Factory(list)
    timeout_minutes: int = 30
    reboot: bool = False

    def __attrs_post_init__(self):
        """Validate a leaf command (a step group overrides this -- see below)."""
        if not (self.command or '').strip():
            raise ValueError(f"provision command '{self.name}' requires a non-empty 'command'")
        if self.timeout_minutes <= 0:
            raise ValueError(
                f"provision command '{self.name}': timeout_minutes must be > 0 "
                f"(got {self.timeout_minutes})"
            )


@attrs.define
class ProvisionStep(ProvisionCommand):
    """A top-level ``recipe.provision`` entry: one command, or a repeated group.

    Two shapes, exactly one of which must be used:

    * **single command** -- set ``command`` (plus any of the inherited fields).
    * **group** -- set ``steps`` (a list of :class:`ProvisionCommand`), optionally
      with ``for_each``, which replays the whole group once per item with
      ``{{ item }}`` substituted through every string field.

    ``for_each`` substitution is Jinja2 with ``StrictUndefined`` on purpose: with
    Jinja's default ``Undefined`` a typo like ``{{ version }}`` instead of
    ``{{ item }}`` renders to the empty string and yields a plausible-but-wrong
    disk. A build that silently installs the wrong thing is the one outcome the
    recipe model cannot tolerate, so an unknown variable is a hard error.

    This class is a faithful mirror of the YAML: the single-command shorthand is
    normalized into a uniform command list by
    :func:`adare.backend.vm.provision.expand_provision`, not here, so nothing
    mutates parsed input behind the caller's back.
    """
    for_each: list[str] = attrs.Factory(list)
    steps: list[ProvisionCommand] = attrs.Factory(list)

    def __attrs_post_init__(self):
        """Enforce exactly-one-of ``command`` / ``steps``.

        Note this deliberately does NOT raise for an unknown-variable
        ``for_each`` template -- rendering happens in ``expand_provision`` where a
        rich error can name the offending field. cattrs' detailed validation would
        otherwise flatten the reason text to ``invalid value @ $.recipe``.
        """
        has_command = bool((self.command or '').strip())
        has_steps = bool(self.steps)
        if has_command and has_steps:
            raise ValueError(
                f"provision entry '{self.name}' sets both 'command' and 'steps'; "
                "use 'command' for a single step or 'steps' for a group, not both"
            )
        if not has_command and not has_steps:
            raise ValueError(
                f"provision entry '{self.name}' must set either 'command' "
                "(single step) or 'steps' (a group)"
            )
        if self.for_each and not has_steps:
            raise ValueError(
                f"provision entry '{self.name}' sets 'for_each' without 'steps'; "
                "for_each replays a group, so wrap the work in 'steps'"
            )
        if has_command and self.timeout_minutes <= 0:
            raise ValueError(
                f"provision entry '{self.name}': timeout_minutes must be > 0 "
                f"(got {self.timeout_minutes})"
            )


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
    unattended-install template override, build parameters, and optional
    build-time provisioning steps. "Same inputs → forensically equivalent
    system"; the produced disk is still hashed per run into ``Vm.hash`` for
    tamper detection, but the reproducible identity is the recipe hash (see
    :func:`adare.helperfunctions.hash.hash_recipe`).

    Two kinds of post-install work exist, and they are NOT interchangeable:

    * ``provision`` (here) runs **once, at build time**, in the guest via the
      QEMU guest agent, and is baked into the resulting disk.
    * ``postsetupinstallations`` (on :class:`EnvironmentMetadata`) runs **inside
      every experiment run**, unchanged from before this field existed.

    Both are folded into the recipe hash, so changing either yields a new
    environment identity.

    ISO source -- exactly one of two forms:

    * ``iso`` -- a path, or an ``http(s)`` URL for a published environment.
    * ``iso_name`` -- a bare filename the *consumer* must supply locally
      ("BYO ISO"), permitted only for **Windows** OS profiles, where the ISO
      cannot lawfully be rehosted. ``iso_notes`` then carries the download
      pointer.

    ``iso_sha256`` is required in both forms and is the integrity boundary; for a
    BYO recipe it is the consumer's only handle on the correct file.

    The exactly-one-of invariant is deliberately NOT enforced in
    ``__attrs_post_init__``: cattrs' detailed validation collapses a nested
    ``ValueError`` to ``invalid value @ $.recipe``, discarding the reason text --
    which would defeat the point of a legible "which ISO do I need" error. It is
    enforced instead at the publish / create / consume gates in
    :mod:`adare.services.recipe_contract`, which can produce rich messages.
    """
    profile: str            # resolves via os_catalog.get_os_definition
    iso_sha256: str         # expected SHA256 of the ISO (hard-checked at build)
    # Publisher-hosted ISO: a local path, or an http(s) URL when published.
    # Mutually exclusive with `iso_name`.
    iso: str = ''
    # BYO ISO (Windows profiles only): the bare filename the consumer supplies.
    # Never a path -- see services.recipe_contract.ISO_NAME_RE.
    iso_name: str = ''
    # Plain-text download pointer shown to a consumer who lacks the ISO. Plain
    # text ONLY: it is publisher-supplied and is rendered in web UIs.
    iso_notes: str = ''
    template: str | None = None   # optional Autounattend/autoinstall override
    params: RecipeParams = attrs.Factory(RecipeParams)
    # Build-time provisioning, applied once to the built disk (see above).
    provision: list[ProvisionStep] = attrs.Factory(list)


@attrs.define
class EnvironmentMetadata:
    """
    Consolidated class to store the configuration of an environment.

    Supports both modern VM-based environments (with OVA files) and legacy Vagrant-based environments.

    Hypervisor Configuration:
        The hypervisor_config field allows hypervisor-specific settings:

        QEMU hypervisor supports:
        - boot_mode: 'uefi', 'bios', or 'auto' (default: 'uefi' for all OSes)
            - Both Windows and Linux VMs default to UEFI boot
            - Override with explicit boot_mode setting for legacy BIOS boot

        Example environment YAML:
            vm: windows-10
            os:
              platform: windows
              os: Windows 10
            hypervisor: qemu
            hypervisor_config:
              boot_mode: bios  # Optional: override default UEFI to use BIOS
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
