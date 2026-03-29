from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import threading
from typing import Optional, Tuple, Dict, Any
from adare.hypervisor.virtualbox.vm import VirtualBoxVM
from adare.backend.project.directory import ProjectDirectory
from adare.backend.experiment.directory import ExperimentDirectory, ExperimentRunDirectory
from adare.backend.experiment.websocket_client import AdareVMClient
from adare.backend.experiment.mcp_server_manager import MCPServerManager
from adare.types.playbook import Playbook

@dataclass
class ExperimentConfig:
    project_path: Path
    environment_name: str
    experiment_name: Optional[str] = None
    disable_printing: bool = False
    test_mode: bool = False
    preserve_snapshot: bool = False
    runlog: bool = True
    vm_cpus: int = 4
    vm_memory: int = 4096  # Default, can be overridden based on guest platform or CLI
    vm_resolution: Tuple[int, int] = (1920, 1080)
    websocket_port: Optional[int] = None  # Allocated dynamically from database
    shared_directories: Dict[str, Dict[str, Path]] = field(default_factory=dict)
    gui_mode_override: Optional[str] = None  # CLI override for GUI execution mode
    test_mode_override: Optional[str] = None  # CLI override for test execution mode
    enable_diff: Optional[bool] = None  # None=use playbook, True/False=override
    diff_mode: str = 'auto'  # 'auto', 'guest', or 'host'
    dev_mode: bool = False  # Track if running in dev mode
    installation_mode: str = "wheel"  # "wheel" (pip) or "editable" (Poetry)

@dataclass
class ExperimentRunCtx:
    config: ExperimentConfig

    # --- Identity ---
    experiment_run_ulid: Optional[str] = None
    project_directory: Optional[ProjectDirectory] = None
    experiment_directory: Optional[ExperimentDirectory] = None

    # --- Environment ---
    environment_file: Optional[Path] = None
    environment_ulid: Optional[str] = None
    guest_platform: Optional[str] = None
    guest_architecture: Optional[str] = None
    hypervisor_type: Optional[str] = None

    # --- VM Infrastructure ---
    vm: Optional[VirtualBoxVM] = None
    vm_file: Optional[Path] = None
    vm_name: Optional[str] = None
    client: Optional[AdareVMClient] = None
    mcp_server: Optional[MCPServerManager] = None
    adarevm: Optional[Path] = None
    adarevm_pid: Optional[int] = None  # PID for process monitoring

    # --- Execution State ---
    playbook: Optional[Playbook] = None
    test_mode: bool = False
    test_execution_mode: Optional[str] = None  # Resolved test execution mode ('agent' or 'host')
    debug_screenshots: bool = False
    experiment_run_directory: Optional[ExperimentRunDirectory] = None

    # --- Timestamps ---
    timestamp_start: Optional[datetime] = None
    timestamp_before_vm_start: Optional[datetime] = None
    timestamp_end: Optional[datetime] = None

    # --- Concurrency ---
    stop_event: threading.Event = field(default_factory=threading.Event)
    user_interrupt_event: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)

    # --- Caching ---
    cached_agent_commands: Optional[Any] = None  # Cached CommandSet for dev mode restores
    cached_env_info: Optional[Any] = None  # Cached EnvironmentInfo for dev mode restores

    # --- Convenience Properties ---

    @property
    def is_interrupted(self) -> bool:
        """Check if user has requested interrupt."""
        return self.user_interrupt_event.is_set()

    @property
    def is_host_test_mode(self) -> bool:
        """Check if tests should run on host (not in-guest agent)."""
        return self.test_execution_mode == 'host'

    @property
    def is_host_gui_mode(self) -> bool:
        """Check if GUI automation should run on host."""
        if self.config.gui_mode_override == 'host':
            return True
        if self.config.gui_mode_override == 'agent':
            return False
        # Auto-detect: QEMU uses host mode by default
        return self.hypervisor_type == 'qemu'

    @property
    def needs_agent(self) -> bool:
        """Check if the in-guest adarevm agent is needed."""
        return not (self.is_host_test_mode and self.is_host_gui_mode)