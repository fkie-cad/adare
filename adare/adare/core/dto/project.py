"""
Data Transfer Objects for Project domain.

These DTOs provide type-safe request/response objects for the ProjectService.
They decouple the API layer from database models and presentation concerns.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class ProjectCreateRequest:
    """Request DTO for creating a new project."""
    name: str
    path: Path
    description: str = ""


@dataclass
class ProjectRemoveRequest:
    """Request DTO for removing a project."""
    path: Path


@dataclass
class ProjectInfo:
    """
    Response DTO for project creation.

    Contains the created project info plus presentation data (next_steps, tip)
    that the CLI can use for display without mixing presentation into service logic.
    """
    id: str
    name: str
    path: Path
    description: str
    next_steps: list[str] = field(default_factory=list)
    tip: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'name': self.name,
            'path': str(self.path),
            'description': self.description,
            'next_steps': self.next_steps,
            'tip': self.tip,
        }


@dataclass
class ProjectListItem:
    """DTO for a single project in the list view."""
    id: str
    name: str
    path: Path
    description: str
    experiment_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            'id': self.id,
            'name': self.name,
            'path': str(self.path),
            'description': self.description,
            'experiment_count': self.experiment_count,
        }

    @classmethod
    def from_model(cls, project) -> "ProjectListItem":
        """Create from SQLAlchemy Project model."""
        return cls(
            id=project.id,
            name=project.name,
            path=Path(project.path),
            description=project.description or "",
        )
