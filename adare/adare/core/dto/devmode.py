"""
Development Mode Data Transfer Objects for API layer.

These DTOs provide type-safe request/response objects for dev mode operations,
enabling consistent interfaces across CLI, REST API, and Web UI.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from adare.backend.devmode.session import DevModeSnapshot

# =============================================================================
# Request DTOs
# =============================================================================

@dataclass
class DevSessionStartRequest:
    """Request to start a new dev mode session."""
    project_path: Path
    environment_name: str
    gui_mode: str | None = None
    vm_memory: int | None = None
    vm_cpus: int | None = None
    debug_screenshots: bool = False
    log_file: Path | None = None
    console_ulid: str | None = None
    shared_directories: dict[str, dict[str, Path]] | None = None


@dataclass
class DevSessionStopRequest:
    """Request to stop a dev mode session."""
    session_id: str
    remove_resources: bool = False  # If True, delete all resources (VM, snapshots, database)


@dataclass
class DevActionExecuteRequest:
    """Request to execute a single action."""
    session_id: str
    action_source: str  # 'file', 'yaml', 'stdin'
    action_content: str  # file path, YAML string, or stdin content


@dataclass
class DevPlaybookExecuteRequest:
    """Request to execute a playbook."""
    session_id: str
    playbook_source: str  # 'file', 'url', 'stdin'
    playbook_content: str  # path, URL, or stdin content
    console_ulid: str | None = None  # For flow console routing
    restore_initial: bool = False  # Restore to initial checkpoint before execution
    indices: str | None = None  # Index specification string (e.g., "1-3,S-5,7,23-E")


@dataclass
class DevResetRequest:
    """Request to reset dev session state."""
    session_id: str
    reset_type: str  # 'soft', 'hard'


@dataclass
class DevCheckpointCreateRequest:
    """Request to create a checkpoint."""
    session_id: str
    name: str
    description: str = ""


@dataclass
class DevCheckpointRestoreRequest:
    """Request to restore a checkpoint."""
    session_id: str
    name: str


@dataclass
class DevCheckpointListRequest:
    """Request to list checkpoints."""
    session_id: str


@dataclass
class DevCheckpointDeleteRequest:
    """Request to delete a checkpoint."""
    session_id: str
    name: str


@dataclass
class DevSessionListRequest:
    """Request to list dev sessions."""
    project_path: Path | None = None


@dataclass
class DevSessionStateRequest:
    """Request to get session state."""
    session_id: str


@dataclass
class DevSessionCleanupRequest:
    """Request to cleanup stale sessions."""
    project_path: Path | None = None


@dataclass
class DevSessionRecordRequest:
    """Request to record a dev session."""
    session_id: str
    output_file: Path


@dataclass
class DevUpdateTestfunctionsRequest:
    """Request to update testfunctions in the VM."""
    session_id: str


@dataclass
class DevCVRestartRequest:
    """Request to restart the CV server."""
    session_id: str
    debug: bool | None = None
    debug_output_dir: Path | None = None


@dataclass
class DevCVStopRequest:
    """Request to stop the CV server."""
    session_id: str


@dataclass
class DevGuiAgentRequest:
    """Request to drive a dev session's VM with the vision-LLM GUI agent."""
    session_id: str
    goal: str
    output_file: Path | None = None  # when set, record a replayable playbook
    max_steps: int | None = None
    stall_limit: int | None = None
    interactive: bool = False  # pause before each action to approve / skip / stop


@dataclass
class DevGuiAuthorRequest:
    """Request to author a playbook from human text steps (no VLM planner).

    The human supplies the *what* as text steps; LocateAnything (ADARE_LOCATE_URL)
    grounds the *where* for described clicks. With ``script`` set, runs the whole
    sequence; otherwise (``interactive``) opens a step-at-a-time REPL.
    """
    session_id: str
    script: str | None = None          # text steps; None + interactive -> REPL
    output_file: Path | None = None    # when set, record a replayable playbook
    interactive: bool = False          # REPL mode when no script is given


@dataclass
class DevServeMcpRequest:
    """Request to serve a dev session's VM as a GUI-automation MCP server."""
    session_id: str
    host: str | None = None            # default: config.server.GUI_MCP_HOST
    port: int | None = None            # default: config.server.GUI_MCP_PORT
    project_path: Path | None = None   # for the testfunction catalog
    output_dir: Path | None = None     # where recordings land (default: project dir)



# =============================================================================
# Response DTOs
# =============================================================================

@dataclass
class DevSessionInfo:
    """Detailed dev session information."""
    session_id: str
    project_path: Path
    environment_name: str
    vm_running: bool
    actions_executed: int
    created_at: datetime
    current_variables: dict[str, Any]
    available_snapshots: list[DevModeSnapshot]
    experiment_name: str | None = None
    next_steps: list[str] = field(default_factory=list)
    tip: str | None = None


@dataclass
class DevActionResult:
    """Result of executing a single action."""
    success: bool
    message: str
    execution_time: float
    coordinates: tuple[int, int] | None = None
    data: Any | None = None


@dataclass
class DevGuiAgentResult:
    """Result of a vision-LLM GUI agent run against a dev session."""
    success: bool
    reason: str
    steps: int
    summary: str = ''
    playbook_path: str | None = None
    report_path: str | None = None


@dataclass
class DevPlaybookResult:
    """Result of executing a playbook."""
    success: bool
    total_actions: int
    successful_actions: int
    failed_actions: int
    execution_time: float
    action_results: list[DevActionResult] = field(default_factory=list)
    error_message: str | None = None
    test_stats: dict[str, Any] | None = None


@dataclass
class DevSessionListItem:
    """Compact session information for list views."""
    session_id: str
    experiment_name: str
    environment_name: str
    vm_running: bool
    actions_executed: int
    created_at: datetime
    project_path: Path
    status: str  # 'running', 'stopped', 'crashed'


@dataclass
class DevCheckpointInfo:
    """Information about a checkpoint."""
    name: str
    description: str
    created_at: datetime
    variable_count: int = 0
    checkpoint_id: str = ""
    memory_file_path: str = ""
    disk_file_path: str = ""
    file_size_mb: float = 0.0


@dataclass
class DevResetResult:
    """Result of a reset operation."""
    success: bool
    reset_type: str  # 'soft', 'hard'
    execution_time: float
    message: str


@dataclass
class DevCleanupResult:
    """Result of cleanup operation."""
    sessions_removed: int
    removed_session_ids: list[str] = field(default_factory=list)


@dataclass
class DevUpdateTestfunctionsResult:
    """Result of updating testfunctions."""
    success: bool
    message: str
    execution_time: float


@dataclass
class DevPlaybookBatchExecuteRequest:
    """Request to execute multiple playbooks in batch."""
    session_id: str
    playbook_patterns: list[str]
    checkpoint_name: str = "batch_base"
    timeout: int = 120
    console_ulid: str | None = None
