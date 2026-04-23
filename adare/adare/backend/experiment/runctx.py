import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from adare.backend.experiment.directory import ExperimentDirectory, ExperimentRunDirectory
from adare.backend.experiment.mcp_server_manager import MCPServerManager
from adare.backend.experiment.websocket_client import AdareVMClient
from adare.backend.project.directory import ProjectDirectory
from adare.hypervisor.virtualbox.vm import VirtualBoxVM
from adare.types.playbook import Playbook


@dataclass
class ExperimentConfig:
    project_path: Path
    environment_name: str
    experiment_name: str | None = None
    disable_printing: bool = False
    test_mode: bool = False
    preserve_snapshot: bool = False
    runlog: bool = True
    vm_cpus: int = 4
    vm_memory: int = 4096  # Default, can be overridden based on guest platform or CLI
    vm_resolution: tuple[int, int] = (1920, 1080)
    websocket_port: int | None = None  # Allocated dynamically from database
    shared_directories: dict[str, dict[str, Path]] = field(default_factory=dict)
    gui_mode_override: str | None = None  # CLI override for GUI execution mode
    test_mode_override: str | None = None  # CLI override for test execution mode
    enable_diff: bool | None = None  # None=use playbook, True/False=override
    diff_mode: str = 'auto'  # 'auto', 'guest', or 'host'
    dev_mode: bool = False  # Track if running in dev mode
    installation_mode: str = "wheel"  # "wheel" (pip) or "editable" (Poetry)
    file_log_level: int = 20  # logging.INFO — level for adare.log file handler

@dataclass
class ExperimentRunCtx:
    config: ExperimentConfig

    # --- Identity ---
    experiment_run_ulid: str | None = None
    project_directory: ProjectDirectory | None = None
    experiment_directory: ExperimentDirectory | None = None

    # --- Environment ---
    environment_file: Path | None = None
    environment_ulid: str | None = None
    guest_platform: str | None = None
    guest_architecture: str | None = None
    hypervisor_type: str | None = None

    # --- VM Infrastructure ---
    vm: VirtualBoxVM | None = None
    vm_file: Path | None = None
    vm_name: str | None = None
    client: AdareVMClient | None = None
    mcp_server: MCPServerManager | None = None
    adarevm: Path | None = None
    adarevm_pid: int | None = None  # PID for process monitoring

    # --- Execution State ---
    playbook: Playbook | None = None
    test_mode: bool = False
    test_execution_mode: str | None = None  # Resolved test execution mode ('agent' or 'host')
    debug_screenshots: bool = False
    experiment_run_directory: ExperimentRunDirectory | None = None

    # --- Timestamps ---
    timestamp_start: datetime | None = None
    timestamp_before_vm_start: datetime | None = None
    timestamp_end: datetime | None = None

    # --- Concurrency ---
    stop_event: threading.Event = field(default_factory=threading.Event)
    user_interrupt_event: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)

    # --- Caching ---
    cached_agent_commands: Any | None = None  # Cached CommandSet for dev mode restores
    cached_env_info: Any | None = None  # Cached EnvironmentInfo for dev mode restores

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
