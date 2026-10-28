"""
Manage Data Transfer Objects for API layer.

These DTOs provide type-safe request/response objects for database and system management,
enabling consistent interfaces across CLI, REST API, and Web UI.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
    pending_migrations: list[str] = field(default_factory=list)
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
class DbMigrateResult:
    """Result of applying pending schema migrations."""

    migrated: bool
    applied: list[str] = field(default_factory=list)
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
# Database Maintenance DTOs (adare db compact / adare db check)
# =============================================================================


@dataclass
class DbCompactEntry:
    """What ``adare db compact`` did (or would do) to one database file.

    ``status`` is ``compacted``, ``dry-run``, ``in-use`` (another process held the
    write lock, or a recently active run or a live dev session may write; nothing
    changed), ``missing`` (no project directory or database file) or ``error``.

    Row counts: ``stripped`` rows had their images replaced by a marker; rows with
    images are kept unchanged when no referenced screenshot file is on disk
    (``kept_missing_file``) or a file is there but differs from the image
    (``kept_mismatch``). ``non_image_kept`` counts rows holding oversized text that
    is not an image (command output, ...): that text is never removed.
    ``stale_runs_ignored`` counts unfinished runs without recent activity (crashed).
    """

    label: str
    path: Path
    status: str
    message: str | None = None
    rows_examined: int = 0
    rows_stripped: int = 0
    rows_kept_missing_file: int = 0
    rows_kept_mismatch: int = 0
    rows_non_image_kept: int = 0
    stale_runs_ignored: int = 0
    reclaimable_bytes: int = 0
    free_pages_bytes: int = 0
    vacuumed: bool = False
    vacuum_message: str | None = None
    size_before: int = 0
    wal_size_before: int = 0
    size_after: int = 0
    wal_size_after: int = 0
    duration_seconds: float = 0.0

    @property
    def failed(self) -> bool:
        """True when the database could not be compacted (in use, unreadable)."""
        return self.status in ('in-use', 'error')

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON/YAML serialization."""
        return {
            'label': self.label,
            'path': str(self.path),
            'status': self.status,
            'message': self.message,
            'rows': {
                'examined': self.rows_examined,
                'stripped': self.rows_stripped,
                'kept_missing_file': self.rows_kept_missing_file,
                'kept_mismatch': self.rows_kept_mismatch,
                'non_image_kept': self.rows_non_image_kept,
            },
            'stale_runs_ignored': self.stale_runs_ignored,
            'reclaimable_bytes': self.reclaimable_bytes,
            'free_pages_bytes': self.free_pages_bytes,
            'vacuum': {'done': self.vacuumed, 'message': self.vacuum_message},
            'size_before': {'db': self.size_before, 'wal': self.wal_size_before},
            'size_after': {'db': self.size_after, 'wal': self.wal_size_after},
            'duration_seconds': round(self.duration_seconds, 3),
        }


@dataclass
class DbCompactResult:
    """Result of ``adare db compact`` over one or more databases."""

    dry_run: bool
    databases: list[DbCompactEntry] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when no database failed."""
        return not any(entry.failed for entry in self.databases)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON/YAML serialization."""
        return {
            'dry_run': self.dry_run,
            'ok': self.ok,
            'databases': [entry.to_dict() for entry in self.databases],
        }


@dataclass
class ForeignKeyViolationCount:
    """Number of ``PRAGMA foreign_key_check`` rows for one (table, parent) pair."""

    table: str
    parent: str
    count: int

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON/YAML serialization."""
        return {'table': self.table, 'parent': self.parent, 'count': self.count}


@dataclass
class DbCheckEntry:
    """Read-only health report of one database file (``adare db check``).

    ``integrity_ok`` is False when ``PRAGMA quick_check`` found problems or the
    file could not be read as a database at all; orphans never make it False.
    ``status`` is ``checked``, or ``missing`` when the project directory or the
    database file does not exist (``message`` says which).
    """

    label: str
    path: Path
    integrity_ok: bool
    problems: list[str] = field(default_factory=list)
    foreign_key_violations: list[ForeignKeyViolationCount] = field(default_factory=list)
    orphans: dict[str, int] = field(default_factory=dict)
    message: str | None = None
    status: str = 'checked'

    @property
    def orphan_total(self) -> int:
        """Total number of orphaned rows over every orphan kind."""
        return sum(self.orphans.values())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON/YAML serialization."""
        return {
            'label': self.label,
            'path': str(self.path),
            'status': self.status,
            'integrity_ok': self.integrity_ok,
            'problems': list(self.problems),
            'foreign_key_violations': [violation.to_dict() for violation in self.foreign_key_violations],
            'orphans': dict(self.orphans),
            'message': self.message,
        }


@dataclass
class DbCheckResult:
    """Result of ``adare db check`` over one or more databases."""

    databases: list[DbCheckEntry] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when every database passed ``quick_check`` (orphans do not count)."""
        return all(entry.integrity_ok for entry in self.databases)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON/YAML serialization."""
        return {'ok': self.ok, 'databases': [entry.to_dict() for entry in self.databases]}


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
