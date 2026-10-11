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
    vm_display_resolution: str | None = (
        None  # Guest display resolution "WxH" from playbook Settings.resolution; None = env/host default
    )
    websocket_port: int | None = None  # Allocated dynamically from database
    shared_directories: dict[str, dict[str, Path]] = field(default_factory=dict)
    gui_mode_override: str | None = None  # CLI override for GUI execution mode
    test_mode_override: str | None = None  # CLI override for test execution mode
    enable_diff: bool | None = None  # None=use playbook, True/False=override
    diff_mode: str = 'auto'  # 'auto', 'guest', or 'host'
    export_disk_image: bool | None = None  # None=use playbook, True/False=override
    capture_pcap: bool | None = None  # None=use playbook, True/False=override
    export_memory_dump: bool | None = None  # None=use playbook, True/False=override
    dev_mode: bool = False  # Track if running in dev mode
    installation_mode: str = "wheel"  # "wheel" (pip) or "editable" (Poetry)
    file_log_level: int = 20  # logging.INFO — level for adare.log file handler
    allow_emulation: bool = False  # Allow QEMU TCG when guest arch != host arch (--allow-emulation)


@dataclass
class MachineRunCtx:
    """Per-machine state for a single VM within an experiment run.

    Extracted from ``ExperimentRunCtx`` so a multi-machine experiment (e.g. a
    client VM and a server VM) can hold one of these per machine key, while
    single-VM experiments keep exactly one entry under the implicit ``None``
    key. See ``ExperimentRunCtx.machines``.
    """

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
    websocket_port: int | None = None  # Host-forwarded port for THIS machine's adarevm agent.
    # Lives here (not ExperimentConfig, which is otherwise genuinely shared) because
    # VMLifecycleManager/hypervisor/qemu/lifecycle.py read/write
    # context.config.websocket_port directly as *the* port for *the* VM; a
    # multi-machine run needs one per machine. See vm_orchestrator._MachineConfigView.


@dataclass
class ExperimentRunCtx:
    config: ExperimentConfig

    # --- Identity ---
    experiment_run_ulid: str | None = None
    project_directory: ProjectDirectory | None = None
    experiment_directory: ExperimentDirectory | None = None

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

    # --- Guest agent ---
    # Per-run secret the agent requires on connect (see agent_token.py); shared
    # by all machines of a run because they share the run's config.json.
    agent_token: str | None = None

    # --- Concurrency ---
    stop_event: threading.Event = field(default_factory=threading.Event)
    user_interrupt_event: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)

    # --- Caching ---
    cached_agent_commands: Any | None = None  # Cached CommandSet for dev mode restores
    cached_env_info: Any | None = None  # Cached EnvironmentInfo for dev mode restores

    # --- Machines ---
    # Keyed by machine name from the playbook's `machines:` section, or the
    # implicit `None` key for today's single-VM playbooks (no `machines:` key).
    machines: dict[str | None, MachineRunCtx] = field(default_factory=dict)
    primary_machine: str | None = None

    def __post_init__(self):
        # Guarantee the primary machine always has a slot, whether this context
        # was constructed with an empty `machines` dict (the common case) or a
        # pre-populated one (multi-machine setup).
        if self.primary_machine not in self.machines:
            self.machines[self.primary_machine] = MachineRunCtx()

    # --- Back-compat scalar properties ---
    #
    # These forward to the primary machine's MachineRunCtx, so every existing
    # single-VM read/write site (`context.vm`, `context.client`, ...) keeps
    # working unmodified after the multi-machine extraction above.

    @property
    def environment_file(self) -> Path | None:
        return self.machines[self.primary_machine].environment_file

    @environment_file.setter
    def environment_file(self, value: Path | None) -> None:
        self.machines[self.primary_machine].environment_file = value

    @property
    def environment_ulid(self) -> str | None:
        return self.machines[self.primary_machine].environment_ulid

    @environment_ulid.setter
    def environment_ulid(self, value: str | None) -> None:
        self.machines[self.primary_machine].environment_ulid = value

    @property
    def guest_platform(self) -> str | None:
        return self.machines[self.primary_machine].guest_platform

    @guest_platform.setter
    def guest_platform(self, value: str | None) -> None:
        self.machines[self.primary_machine].guest_platform = value

    @property
    def guest_architecture(self) -> str | None:
        return self.machines[self.primary_machine].guest_architecture

    @guest_architecture.setter
    def guest_architecture(self, value: str | None) -> None:
        self.machines[self.primary_machine].guest_architecture = value

    @property
    def hypervisor_type(self) -> str | None:
        return self.machines[self.primary_machine].hypervisor_type

    @hypervisor_type.setter
    def hypervisor_type(self, value: str | None) -> None:
        self.machines[self.primary_machine].hypervisor_type = value

    @property
    def vm(self) -> VirtualBoxVM | None:
        return self.machines[self.primary_machine].vm

    @vm.setter
    def vm(self, value: VirtualBoxVM | None) -> None:
        self.machines[self.primary_machine].vm = value

    @property
    def vm_file(self) -> Path | None:
        return self.machines[self.primary_machine].vm_file

    @vm_file.setter
    def vm_file(self, value: Path | None) -> None:
        self.machines[self.primary_machine].vm_file = value

    @property
    def vm_name(self) -> str | None:
        return self.machines[self.primary_machine].vm_name

    @vm_name.setter
    def vm_name(self, value: str | None) -> None:
        self.machines[self.primary_machine].vm_name = value

    @property
    def client(self) -> AdareVMClient | None:
        return self.machines[self.primary_machine].client

    @client.setter
    def client(self, value: AdareVMClient | None) -> None:
        self.machines[self.primary_machine].client = value

    @property
    def mcp_server(self) -> MCPServerManager | None:
        return self.machines[self.primary_machine].mcp_server

    @mcp_server.setter
    def mcp_server(self, value: MCPServerManager | None) -> None:
        self.machines[self.primary_machine].mcp_server = value

    @property
    def adarevm(self) -> Path | None:
        return self.machines[self.primary_machine].adarevm

    @adarevm.setter
    def adarevm(self, value: Path | None) -> None:
        self.machines[self.primary_machine].adarevm = value

    @property
    def adarevm_pid(self) -> int | None:
        return self.machines[self.primary_machine].adarevm_pid

    @adarevm_pid.setter
    def adarevm_pid(self, value: int | None) -> None:
        self.machines[self.primary_machine].adarevm_pid = value

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
