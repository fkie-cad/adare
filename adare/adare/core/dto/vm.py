"""
VM Data Transfer Objects for API layer.

These DTOs provide type-safe request/response objects for VM operations,
enabling consistent interfaces across CLI, REST API, and Web UI.
"""
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Optional


# =============================================================================
# VM Request DTOs
# =============================================================================

@dataclass
class VmLoadRequest:
    """Request to load a VM from file."""
    file_path: Path
    name: Optional[str] = None
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
    os_platform: Optional[str] = None
    os_type: Optional[str] = None
    os_distribution: Optional[str] = None
    os_version: Optional[str] = None
    os_language: Optional[str] = None
    os_architecture: Optional[str] = None
    instance_count: int = 0
    is_external: bool = False
    next_steps: List[str] = field(default_factory=list)
    tip: Optional[str] = None


@dataclass
class VmListItem:
    """VM item for listing (lighter than VmInfo)."""
    id: str
    name: str
    description: str
    file_hash: str
    hypervisor: str
    os_platform: Optional[str] = None
    instance_count: int = 0


# =============================================================================
# VM Instance Request DTOs
# =============================================================================

@dataclass
class VmInstanceRemoveRequest:
    """Request to remove VM instance(s)."""
    instance_id: Optional[str] = None  # Specific instance ULID
    all_stopped: bool = False  # Remove all stopped instances
    experiment_id: Optional[str] = None  # Remove instances for specific experiment


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
    websocket_port: Optional[int]
    vbox_uuid: Optional[str]
    base_snapshot_name: Optional[str]
    current_experiment_run_id: Optional[str]
    created_at: Optional[datetime]
    last_used_at: Optional[datetime]
    hypervisor: str = "virtualbox"


@dataclass
class VmInstanceListItem:
    """VM instance item for listing (lighter than VmInstanceInfo)."""
    id: str
    vm_name: str
    instance_name: str
    status: str
    websocket_port: Optional[int]
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
    description: Optional[str]
    created_at: Optional[datetime]
    vm_id: Optional[str]
    vm_instance_id: Optional[str]
    vbox_uuid: Optional[str]


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
    deleted_vms: List[str]
    failed_count: int
    failed_vms: List[str]


@dataclass
class VmInstanceCleanupResult:
    """Result of cleaning up VM instances."""
    removed_count: int
    removed_instances: List[str]
    failed_count: int
    failed_instances: List[str]


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
