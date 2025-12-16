from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import threading
from typing import Optional, Tuple, Dict
from adare.hypervisor.virtualbox.vm import VirtualBoxVM
from adare.backend.project.directory import ProjectDirectory
from adare.backend.experiment.directory import ExperimentDirectory, ExperimentRunDirectory
from adare.backend.experiment.websocket_client import AdareVMClient
from adare.backend.experiment.mcp_server_manager import MCPServerManager
from adare.types.playbook import Playbook

@dataclass
class ExperimentConfig:
    project_path: Path
    experiment_name: str
    environment_name: str
    disable_printing: bool = False
    test_mode: bool = False
    preserve_snapshot: bool = False
    runlog: bool = True
    vm_cpus: int = 4
    vm_memory: int = 4096  # Default, can be overridden based on guest platform or CLI
    vm_resolution: Tuple[int, int] = (1920, 1080)
    websocket_port: Optional[int] = None  # Allocated dynamically from database
    shared_directories: Dict[str, Dict[str, Path]] = field(default_factory=dict)

@dataclass
class ExperimentRunCtx:
    config: ExperimentConfig
    experiment_run_ulid: Optional[str] = None
    adarevm: Optional[Path] = None
    vm: Optional[VirtualBoxVM] = None
    vm_file: Optional[Path] = None
    project_directory: Optional[ProjectDirectory] = None
    experiment_directory: Optional[ExperimentDirectory] = None
    environment_file: Optional[Path] = None
    environment_ulid: Optional[str] = None
    guest_platform: Optional[str] = None
    hypervisor_type: Optional[str] = None
    experiment_run_directory: Optional[ExperimentRunDirectory] = None
    vm_name: Optional[str] = None
    client: Optional[AdareVMClient] = None
    timestamp_start: Optional[datetime] = None
    timestamp_before_vm_start: Optional[datetime] = None
    timestamp_end: Optional[datetime] = None
    stop_event: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)
    mcp_server: Optional[MCPServerManager] = None
    debug_screenshots: bool = False
    playbook: Optional[Playbook] = None
    test_mode: bool = False