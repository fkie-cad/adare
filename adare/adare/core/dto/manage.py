"""
Manage Data Transfer Objects for API layer.

These DTOs provide type-safe request/response objects for database and system management,
enabling consistent interfaces across CLI, REST API, and Web UI.
"""
from dataclasses import dataclass, field
from pathlib import Path

# =============================================================================
# Database Management DTOs
# =============================================================================

@dataclass
class DbStatusResult:
    """Result of database status check."""
    global_db_exists: bool
    global_db_accessible: bool
    global_db_location: Path | None
    valid: bool
    errors: list[str] = field(default_factory=list)


@dataclass
class DbInitResult:
    """Result of database initialization."""
    global_db_initialized: bool
    global_db_location: Path | None
    errors: list[str] = field(default_factory=list)


@dataclass
class DbRepairResult:
    """Result of database repair."""
    repaired: bool
    actions_taken: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class DbCleanInstallResult:
    """Result of clean database installation."""
    installed: bool
    actions_taken: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


@dataclass
class DbResetResult:
    """Result of database reset."""
    was_reset: bool
    location: Path | None = None


# =============================================================================
# VM Management DTOs
# =============================================================================

@dataclass
class VmResetResult:
    """Result of VM reset operation."""
    deleted_count: int
    failed_count: int
    deleted_vms: list[str] = field(default_factory=list)
    failed_vms: list[str] = field(default_factory=list)


@dataclass
class VmRuntimeRefreshResult:
    """Result of VM runtime refresh."""
    refreshed: bool
    project_path: Path | None = None
    error_message: str | None = None


@dataclass
class VmRuntimeBuildResult:
    """Result of VM runtime wheel build."""
    built: bool
    project_path: Path | None = None
    wheels_dir: Path | None = None
    adarelib_wheel: str | None = None
    adarevm_wheel: str | None = None
    error_message: str | None = None
