"""
Development Mode Data Transfer Objects for API layer.

These DTOs provide type-safe request/response objects for dev mode operations,
enabling consistent interfaces across CLI, REST API, and Web UI.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple

from adare.backend.devmode.session import DevModeSnapshot


# =============================================================================
# Request DTOs
# =============================================================================

@dataclass
class DevSessionStartRequest:
    """Request to start a new dev mode session."""
    project_path: Path
    environment_name: str
    gui_mode: Optional[str] = None
    vm_memory: Optional[int] = None
    vm_cpus: Optional[int] = None
    debug_screenshots: bool = False
    log_file: Optional[Path] = None
    console_ulid: Optional[str] = None


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
    console_ulid: Optional[str] = None  # For flow console routing
    restore_initial: bool = False  # Restore to initial checkpoint before execution
    indices: Optional[List[int]] = None  # Specific action indices (1-based) to execute


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
    project_path: Optional[Path] = None


@dataclass
class DevSessionStateRequest:
    """Request to get session state."""
    session_id: str


@dataclass
class DevSessionCleanupRequest:
    """Request to cleanup stale sessions."""
    project_path: Optional[Path] = None


@dataclass
class DevSessionRecordRequest:
    """Request to record a dev session."""
    session_id: str
    output_file: Path



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
    current_variables: Dict[str, Any]
    available_snapshots: List[DevModeSnapshot]
    experiment_name: Optional[str] = None
    next_steps: List[str] = field(default_factory=list)
    tip: Optional[str] = None


@dataclass
class DevActionResult:
    """Result of executing a single action."""
    success: bool
    message: str
    execution_time: float
    coordinates: Optional[Tuple[int, int]] = None
    data: Optional[Any] = None


@dataclass
class DevPlaybookResult:
    """Result of executing a playbook."""
    success: bool
    total_actions: int
    successful_actions: int
    failed_actions: int
    execution_time: float
    action_results: List[DevActionResult] = field(default_factory=list)
    error_message: Optional[str] = None
    test_stats: Optional[Dict[str, Any]] = None


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
    removed_session_ids: List[str] = field(default_factory=list)
