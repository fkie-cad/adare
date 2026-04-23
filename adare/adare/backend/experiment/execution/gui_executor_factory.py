"""
Factory for creating appropriate GUI executor based on VM type and settings.
"""

import logging
from pathlib import Path

from .base import GUIExecutionMode
from .gui_executor_interface import AbstractGUIExecutor

log = logging.getLogger(__name__)


def resolve_gui_execution_mode(vm, playbook_settings, cli_override: str | None = None) -> GUIExecutionMode:
    """
    Resolve GUI execution mode based on hypervisor and playbook settings.

    Logic:
    1. Check CLI override (highest priority)
    2. Check playbook.settings.gui_execution_mode
    3. Auto mode: QEMU → host, VirtualBox → agent

    Args:
        vm: VM instance (QEMUVM or VirtualBoxVM)
        playbook_settings: Playbook settings object (optional)
        cli_override: CLI-specified mode override (optional)

    Returns:
        GUIExecutionMode enum value

    Raises:
        ValueError: If 'host' mode requested for VirtualBox or invalid mode string
    """
    # Import here to avoid circular dependency
    from adare.hypervisor.qemu.vm import QEMUVM
    from adare.hypervisor.virtualbox.vm import VirtualBoxVM

    # Priority 1: CLI override
    if cli_override is not None:
        mode_str = cli_override
        log.info(f"Using CLI-specified GUI mode: {cli_override}")
    # Priority 2: Playbook settings
    elif playbook_settings and hasattr(playbook_settings, 'gui_execution_mode'):
        mode_str = playbook_settings.gui_execution_mode or 'auto'
        log.debug(f"Using playbook GUI mode: {mode_str}")
    # Priority 3: Default to auto
    else:
        mode_str = 'auto'
        log.debug("Using default GUI mode: auto")

    log.debug(f"Resolving GUI execution mode: mode={mode_str}, vm_type={type(vm).__name__}")

    # Validate mode string
    if mode_str not in ('auto', 'agent', 'host'):
        raise ValueError(
            f"Invalid gui_execution_mode '{mode_str}'. "
            f"Must be one of: 'auto', 'agent', 'host'"
        )

    # Handle explicit mode settings
    if mode_str == 'agent':
        log.info("Using agent-based GUI execution (explicit setting)")
        return GUIExecutionMode.AGENT

    if mode_str == 'host':
        # Validate host mode is only for QEMU
        if not isinstance(vm, QEMUVM):
            raise ValueError(
                "gui_execution_mode='host' is only supported for QEMU VMs. "
                "VirtualBox requires agent-based execution (gui_execution_mode='agent'). "
                "Use gui_execution_mode='auto' for automatic selection."
            )
        log.info("Using host-based GUI execution (explicit setting)")
        return GUIExecutionMode.HOST

    # Auto mode: decide based on hypervisor type
    if isinstance(vm, QEMUVM):
        log.info("Using host-based GUI execution for QEMU (auto mode)")
        return GUIExecutionMode.HOST
    if isinstance(vm, VirtualBoxVM):
        log.info("Using agent-based GUI execution for VirtualBox (auto mode)")
        return GUIExecutionMode.AGENT
    # Fallback to agent mode for unknown VM types
    log.warning(f"Unknown VM type {type(vm).__name__}, defaulting to agent mode")
    return GUIExecutionMode.AGENT


def create_gui_executor(
    mode: GUIExecutionMode,
    websocket_client,
    vm,
    target_resolution_executor,
    experiment_run_id: str | None = None,
    playbook = None,
    execution_context: dict = None,
    experiment_run_directory: Path | None = None
) -> AbstractGUIExecutor:
    """
    Create appropriate GUI executor based on execution mode.

    Args:
        mode: GUI execution mode
        websocket_client: WebSocket client for agent mode
        vm: VM instance for host mode
        target_resolution_executor: Target resolution executor
        experiment_run_id: Experiment run ID
        playbook: Playbook reference
        execution_context: Execution context
        experiment_run_directory: Run directory

    Returns:
        Appropriate GUI executor instance

    Raises:
        ValueError: If mode is invalid or required dependencies missing
    """
    if mode == GUIExecutionMode.AGENT:
        from .agent_gui_executor import AgentGUIExecutor
        log.debug("Creating AgentGUIExecutor")
        return AgentGUIExecutor(
            websocket_client=websocket_client,
            target_resolution_executor=target_resolution_executor,
            experiment_run_id=experiment_run_id,
            playbook=playbook,
            execution_context=execution_context,
            experiment_run_directory=experiment_run_directory
        )
    if mode == GUIExecutionMode.HOST:
        from .qemu_host_gui_executor import QEMUHostGUIExecutor
        log.debug("Creating QEMUHostGUIExecutor")
        return QEMUHostGUIExecutor(
            vm=vm,
            target_resolution_executor=target_resolution_executor,
            experiment_run_id=experiment_run_id,
            playbook=playbook,
            execution_context=execution_context,
            experiment_run_directory=experiment_run_directory
        )
    raise ValueError(f"Invalid GUI execution mode: {mode}")
