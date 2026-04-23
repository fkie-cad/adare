"""
VM Data Transfer Objects for API layer.

These DTOs provide type-safe request/response objects for VM operations,
enabling consistent interfaces across CLI, REST API, and Web UI.
"""
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# =============================================================================
# VM Request DTOs
# =============================================================================

@dataclass
class VmLoadRequest:
    """Request to load a VM from file."""
    file_path: Path
    name: str | None = None
    description: str = ""
    os_platform: str = ""
    os_type: str = ""
    os_distribution: str = ""
    os_version: str = ""
    os_language: str = ""
    os_architecture: str = "x86_64"
    force: bool = False


@dataclass
class VmDeleteRequest:
    """Request to delete a VM."""
    vm_id: str
    force: bool = False


# =============================================================================
# VM Response DTOs
# =============================================================================

@dataclass
class VmInfo:
    """Detailed VM information."""
    id: str
    name: str
    file_path: str
    file_hash: str
    description: str
    hypervisor: str
    use_snapshots: bool
    os_platform: str | None = None
    os_type: str | None = None
    os_distribution: str | None = None
    os_version: str | None = None
    os_language: str | None = None
    os_architecture: str | None = None
    instance_count: int = 0
    is_external: bool = False
    next_steps: list[str] = field(default_factory=list)
    tip: str | None = None


@dataclass
class VmListItem:
    """VM item for listing (lighter than VmInfo)."""
    id: str
    name: str
    description: str
    file_hash: str
    hypervisor: str
    os_platform: str | None = None
    instance_count: int = 0


# =============================================================================
# VM Instance Request DTOs
# =============================================================================

@dataclass
class VmInstanceRemoveRequest:
    """Request to remove VM instance(s)."""
    instance_id: str | None = None  # Specific instance ULID
    all_stopped: bool = False  # Remove all stopped instances
    experiment_id: str | None = None  # Remove instances for specific experiment


# =============================================================================
# VM Instance Response DTOs
# =============================================================================

@dataclass
class VmInstanceInfo:
    """Detailed VM instance information."""
    id: str
    vm_id: str
    vm_name: str
    instance_name: str
    status: str  # active, available, stopped
    websocket_port: int | None
    vbox_uuid: str | None
    base_snapshot_name: str | None
    current_experiment_run_id: str | None
    created_at: datetime | None
    last_used_at: datetime | None
    hypervisor: str = "virtualbox"


@dataclass
class VmInstanceListItem:
    """VM instance item for listing (lighter than VmInstanceInfo)."""
    id: str
    vm_name: str
    instance_name: str
    status: str
    websocket_port: int | None
    hypervisor: str = "virtualbox"


@dataclass
class VmInstanceUsage:
    """VM instance usage statistics."""
    total_instances: int
    active_instances: int
    available_instances: int
    stopped_instances: int
    instances_by_vm: dict = field(default_factory=dict)  # vm_name -> count


# =============================================================================
# VM Snapshot DTOs
# =============================================================================

@dataclass
class VmSnapshotInfo:
    """VM snapshot information."""
    id: str
    name: str
    snapshot_type: str  # base, experiment, backup
    description: str | None
    created_at: datetime | None
    vm_id: str | None
    vm_instance_id: str | None
    vbox_uuid: str | None


@dataclass
class VmSnapshotDeleteRequest:
    """Request to delete a VM snapshot."""
    instance_id: str
    snapshot_name: str


# =============================================================================
# VM Clear/Cleanup DTOs
# =============================================================================

@dataclass
class VmClearResult:
    """Result of clearing VMs."""
    deleted_count: int
    deleted_vms: list[str]
    failed_count: int
    failed_vms: list[str]


@dataclass
class VmInstanceCleanupResult:
    """Result of cleaning up VM instances."""
    removed_count: int
    removed_instances: list[str]
    failed_count: int
    failed_instances: list[str]


# =============================================================================
# VM Test DTOs
# =============================================================================

@dataclass
class VmTestRequest:
    """Request to test OVA file compatibility with ADARE."""
    ova_file_path: Path
    guest_platform: str  # 'windows' or 'linux'
    verbose: bool = False
    vm_cleanup_mode: str = 'prompt'  # 'keep' or 'prompt'


@dataclass
class VmTestResult:
    """Result of VM compatibility test."""
    success: bool
    ova_file: str
    guest_platform: str
    message: str
