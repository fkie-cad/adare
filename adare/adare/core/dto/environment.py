"""
Data Transfer Objects for Environment domain.

These DTOs provide type-safe request/response objects for the EnvironmentService.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class EnvironmentLoadRequest:
    """Request DTO for loading an environment from YAML file."""
    environment: str  # Path or name
    force: bool = False
    no_copy: bool = False


@dataclass
class EnvironmentCreateRequest:
    """Request DTO for creating a new environment template.

    Two shapes: a baked template or a declarative recipe (`os_profile` plus an
    ISO source) that defers the actual VM build to `environment load`. Each
    source can be given as a local path (CLI, offline use) or a published
    `http(s)` URL + sha256 (the web variant's publish-ready BYO-URL model). See
    `is_recipe`.
    """
    project_path: Path
    name: str
    vm_path: Path | None = None
    vm_url: str | None = None
    vm_sha256: str | None = None
    os_profile: str | None = None
    iso_path: Path | None = None
    iso_url: str | None = None
    iso_sha256: str | None = None
    disk_size: str | None = None
    ram_mb: int | None = None
    cpus: int | None = None
    arch: str | None = None
    setup_level: int | None = None

    @property
    def is_recipe(self) -> bool:
        """True when enough recipe inputs were given to build a recipe env.

        A recipe needs an OS profile plus an ISO source — either a local path
        (CLI) or a published URL (web).
        """
        return bool(self.os_profile and (self.iso_path or self.iso_url))


@dataclass
class EnvironmentDeleteRequest:
    """Request DTO for deleting an environment."""
    identifier: str  # Name or ULID
    force: bool = False


@dataclass
class EnvironmentExtendRequest:
    """
    Request DTO for extending an environment (or VM) into a new environment
    that reuses the same base disk plus additional post-setup installations.

    Declarative mode (default) is driven by `installs`/`from_file`/`shell`/`cwd`.
    Interactive mode (`interactive`, QEMU only) boots the base in a GUI window;
    `console` additionally opens the recording REPL, and the Mode-B-only fields
    (`ram`, `cpus`, `disk_name`) tune the boot window and flattened disk name.
    """
    source: str  # Environment name/ULID or VM name
    name: str  # Name for the new environment (must be unique)
    installs: list[tuple[str, str]] = field(default_factory=list)  # (name, command) from --install
    from_file: Path | None = None
    shell: bool = False
    cwd: str | None = None
    interactive: bool = False
    console: bool = False
    ram: int | None = None
    cpus: int | None = None
    disk_name: str | None = None
    description: str | None = None
    tags: list[str] = field(default_factory=list)
    force: bool = False
    project: str | None = None


@dataclass
class EnvironmentInfo:
    """
    Response DTO for environment operations.

    Contains full environment details including VM and OS information.
    """
    id: str
    name: str
    description: str
    vm_name: str | None
    hypervisor: str
    os_platform: str | None
    file_path: Path | None
    next_steps: list[str] = field(default_factory=list)
    tip: str | None = None
    reused_existing: bool = False
    discarded: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'vm_name': self.vm_name,
            'hypervisor': self.hypervisor,
            'os_platform': self.os_platform,
            'file_path': str(self.file_path) if self.file_path else None,
            'next_steps': self.next_steps,
            'tip': self.tip,
            'reused_existing': self.reused_existing,
            'discarded': self.discarded,
        }


@dataclass
class EnvironmentListItem:
    """DTO for a single environment in the list view."""
    id: str
    name: str
    description: str
    vm_name: str | None
    hypervisor: str
    os_platform: str | None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'vm_name': self.vm_name,
            'hypervisor': self.hypervisor,
            'os_platform': self.os_platform,
        }

    @classmethod
    def from_model(cls, env) -> "EnvironmentListItem":
        """Create from SQLAlchemy Environment model."""
        vm_name = None
        if hasattr(env, 'vm') and env.vm:
            vm_name = env.vm.name

        os_platform = None
        if hasattr(env, 'vm') and env.vm and hasattr(env.vm, 'osinfo') and env.vm.osinfo:
            os_platform = env.vm.osinfo.platform

        return cls(
            id=env.id,
            name=env.name,
            description=env.description or "",
            vm_name=vm_name,
            hypervisor=env.hypervisor or "virtualbox",
            os_platform=os_platform,
        )
