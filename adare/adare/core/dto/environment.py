"""
Data Transfer Objects for Environment domain.

These DTOs provide type-safe request/response objects for the EnvironmentService.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Any


@dataclass
class EnvironmentLoadRequest:
    """Request DTO for loading an environment from YAML file."""
    environment: str  # Path or name
    force: bool = False
    no_copy: bool = False


@dataclass
class EnvironmentCreateRequest:
    """Request DTO for creating a new environment template."""
    project_path: Path
    name: str
    vm_path: Optional[Path] = None


@dataclass
class EnvironmentDeleteRequest:
    """Request DTO for deleting an environment."""
    identifier: str  # Name or ULID
    force: bool = False


@dataclass
class EnvironmentInfo:
    """
    Response DTO for environment operations.

    Contains full environment details including VM and OS information.
    """
    id: str
    name: str
    description: str
    vm_name: Optional[str]
    hypervisor: str
    os_platform: Optional[str]
    file_path: Optional[Path]
    next_steps: List[str] = field(default_factory=list)
    tip: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
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
        }


@dataclass
class EnvironmentListItem:
    """DTO for a single environment in the list view."""
    id: str
    name: str
    description: str
    vm_name: Optional[str]
    hypervisor: str
    os_platform: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
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
