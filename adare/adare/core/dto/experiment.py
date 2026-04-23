"""
Experiment Data Transfer Objects for API layer.

These DTOs provide type-safe request/response objects for experiment operations,
enabling consistent interfaces across CLI, REST API, and Web UI.
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

# =============================================================================
# Experiment Request DTOs
# =============================================================================

@dataclass
class ExperimentCreateRequest:
    """Request to create a new experiment."""
    project_path: Path
    name: str


@dataclass
class ExperimentLoadRequest:
    """Request to load an experiment."""
    project_path: Path
    name: str
    force: bool = False
    silent: bool = False


@dataclass
class ExperimentRunRequest:
    """Request to run an experiment."""
    project_path: Path
    experiment_name: str
    environment_name: str
    test_mode: bool = True
    debug_screenshots: bool = False
    preserve_snapshot: bool = False
    vm_memory: int | None = None
    vm_cpus: int | None = None
    gui_mode: bool = False


@dataclass
class ExperimentCloneRequest:
    """Request to clone an experiment."""
    project_path: Path
    source_experiment: str
    target_experiment: str
    environments: list[str] | None = None


@dataclass
class ExperimentRemoveRequest:
    """Request to remove an experiment."""
    project_path: Path
    name: str
    force: bool = False
    keep_files: bool = False


@dataclass
class ExperimentEnvModifyRequest:
    """Request to add or remove environments from experiments."""
    project_path: Path
    experiment_pattern: str
    environments: list[str]
    force: bool = False


@dataclass
class ExperimentValidateRequest:
    """Request to validate an experiment configuration and integrity."""
    project_path: Path
    name: str
    environment: str | None = None


# =============================================================================
# Experiment Response DTOs
# =============================================================================

@dataclass
class ExperimentInfo:
    """Detailed experiment information."""
    id: str
    name: str
    description: str
    file_path: Path
    sha256: str
    environment_names: list[str]
    run_count: int = 0
    productive_run_count: int = 0
    is_loaded: bool = False
    next_steps: list[str] = field(default_factory=list)
    tip: str | None = None


@dataclass
class ExperimentListItem:
    """Experiment item for listing (lighter than ExperimentInfo)."""
    id: str
    name: str
    description: str
    environment_count: int
    run_count: int


@dataclass
class ExperimentRunInfo:
    """Information about an experiment run."""
    id: str
    experiment_id: str
    experiment_name: str
    environment_id: str
    environment_name: str
    status: str  # PENDING, RUNNING, SUCCESS, FAILED, INTERRUPTED
    is_test: bool
    start_time: datetime | None
    end_time: datetime | None
    duration: timedelta | None


@dataclass
class ExperimentRunResult:
    """Result of an experiment run."""
    was_interrupted: bool
    was_successful: bool
    run_info: ExperimentRunInfo | None = None
    error_message: str | None = None


@dataclass
class ExperimentCleanResult:
    """Result of cleaning experiment runs."""
    deleted_count: int
    experiment_name: str


@dataclass
class ExperimentRemoveResult:
    """Result of removing an experiment."""
    removed_from_db: bool
    files_deleted: bool
    experiment_name: str


@dataclass
class ExperimentEnvModifyResult:
    """Result of adding/removing environments from experiments."""
    affected_experiments: list[str]
    environments_changed: list[str]
    operation: str  # 'add' or 'remove'


# =============================================================================
# Batch Run DTOs
# =============================================================================

@dataclass
class BatchRunRequest:
    """Request to run experiments in batch."""
    project_path: Path
    experiment_pattern: str
    environment_pattern: str
    test_mode: bool = True
    debug_screenshots: bool = False
    preserve_snapshot: bool = False
    vm_memory: int | None = None
    vm_cpus: int | None = None
    gui_mode: bool = False


@dataclass
class BatchRunResultItem:
    """Result of a single run in a batch."""
    environment_name: str
    experiment_name: str
    status: str  # SUCCESS, FAILED, INTERRUPTED, SKIPPED
    duration: timedelta
    error_message: str | None = None
    run_id: str | None = None


@dataclass
class ValidationCheckResult:
    """Result of a single validation check."""
    name: str
    passed: bool
    message: str
    is_warning: bool = False


@dataclass
class ExperimentValidateResult:
    """Result of validating an experiment."""
    name: str
    checks: list[ValidationCheckResult] = field(default_factory=list)

    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.checks if c.passed and not c.is_warning)

    @property
    def failed_count(self) -> int:
        return sum(1 for c in self.checks if not c.passed and not c.is_warning)

    @property
    def warning_count(self) -> int:
        return sum(1 for c in self.checks if c.is_warning)

    @property
    def is_valid(self) -> bool:
        return self.failed_count == 0


@dataclass
class BatchRunSummary:
    """Summary of a batch run."""
    results: list[BatchRunResultItem]
    total_combinations: int
    successful_runs: int
    failed_runs: int
    interrupted_runs: int
    skipped_runs: int
    total_duration: timedelta
