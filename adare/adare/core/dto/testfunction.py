"""
Testfunction Data Transfer Objects for API layer.

These DTOs provide type-safe request/response objects for testfunction operations,
enabling consistent interfaces across CLI, REST API, and Web UI.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


# =============================================================================
# Testfunction Request DTOs
# =============================================================================

@dataclass
class TestfunctionCreateRequest:
    """Request to create a new testfunction."""
    project_path: Path
    name: str


@dataclass
class TestfunctionLoadRequest:
    """Request to load a testfunction."""
    path: Path  # Path to testfunction (file or directory)
    force: bool = False


@dataclass
class TestfunctionRemoveRequest:
    """Request to remove a testfunction."""
    name: str
    force: bool = False


# =============================================================================
# Testfunction Response DTOs
# =============================================================================

@dataclass
class TestfunctionInfo:
    """Detailed testfunction information."""
    id: str
    name: str
    file_path: Optional[Path]
    is_published: bool = False
    remote_url: Optional[str] = None
    usage_count: int = 0
    experiments_using: List[str] = field(default_factory=list)
    next_steps: List[str] = field(default_factory=list)
    tip: Optional[str] = None


@dataclass
class TestfunctionListItem:
    """Testfunction item for listing (lighter than TestfunctionInfo)."""
    id: str
    name: str
    dotnotation: str
    is_published: bool = False


@dataclass
class TestfunctionUsage:
    """Usage information for a testfunction."""
    exists: bool
    testfunction_file_id: Optional[int]
    can_safely_delete: bool
    projects_affected: List[str]
    experiments: List[str]
    runs_count: int


@dataclass
class TestfunctionRemoveResult:
    """Result of removing a testfunction."""
    name: str
    was_removed: bool
    experiments_affected: int = 0
    runs_deleted: int = 0


@dataclass
class TestfunctionExistsResult:
    """Result of checking if testfunction exists."""
    name: str
    exists: bool
