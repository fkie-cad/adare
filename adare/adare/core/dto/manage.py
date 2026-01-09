"""
Manage Data Transfer Objects for API layer.

These DTOs provide type-safe request/response objects for database and system management,
enabling consistent interfaces across CLI, REST API, and Web UI.
"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


# =============================================================================
# Database Management DTOs
# =============================================================================

@dataclass
class DbStatusResult:
    """Result of database status check."""
    global_db_exists: bool
    global_db_accessible: bool
    global_db_location: Optional[Path]
    valid: bool
    errors: List[str] = field(default_factory=list)


@dataclass
class DbInitResult:
    """Result of database initialization."""
    global_db_initialized: bool
    global_db_location: Optional[Path]
    errors: List[str] = field(default_factory=list)


@dataclass
class DbRepairResult:
    """Result of database repair."""
    repaired: bool
    actions_taken: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class DbCleanInstallResult:
    """Result of clean database installation."""
    installed: bool
    actions_taken: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


@dataclass
class DbResetResult:
    """Result of database reset."""
    was_reset: bool
    location: Optional[Path] = None


# =============================================================================
# VM Management DTOs
# =============================================================================

@dataclass
class VmResetResult:
    """Result of VM reset operation."""
    deleted_count: int
    failed_count: int
    deleted_vms: List[str] = field(default_factory=list)
    failed_vms: List[str] = field(default_factory=list)


@dataclass
class VmRuntimeRefreshResult:
    """Result of VM runtime refresh."""
    refreshed: bool
    project_path: Optional[Path] = None
    error_message: Optional[str] = None
