"""
Playbook Data Transfer Objects for the API layer.

Type-safe request/response objects for reading, validating, and writing an
experiment's ``playbook.yml`` — the file/DB half of the conversational
"fix a playbook" loop (read -> edit -> validate -> replay -> write-back).
These are deliberately file/DB operations only; they never touch a VM.
"""
from dataclasses import dataclass
from pathlib import Path

# =============================================================================
# Request DTOs
# =============================================================================


@dataclass
class PlaybookReadRequest:
    """Request to read an experiment's playbook YAML."""
    project_path: Path
    experiment: str


@dataclass
class PlaybookValidateRequest:
    """Request to statically validate a playbook YAML string (no VM)."""
    yaml: str


@dataclass
class PlaybookWriteRequest:
    """Request to write a validated playbook YAML back to an experiment."""
    project_path: Path
    experiment: str
    yaml: str
    backup: bool = True


# =============================================================================
# Response DTOs
# =============================================================================


@dataclass
class PlaybookReadResult:
    """Raw playbook YAML plus where it came from."""
    path: Path
    yaml: str
    source: str  # 'file' or 'database'


@dataclass
class PlaybookValidateResult:
    """Static validation outcome. ``errors`` is empty when ``valid``."""
    valid: bool
    errors: list[str]


@dataclass
class PlaybookWriteResult:
    """Result of a validated write-back + DB re-ingest."""
    path: Path
    version: int | None
    backup_path: Path | None = None
    db_ingested: bool = False
