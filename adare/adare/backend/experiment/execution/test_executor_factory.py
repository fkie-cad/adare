"""
Factory for creating appropriate test executor based on VM type and settings.

Mirrors the pattern of gui_executor_factory.py for test execution mode resolution.
"""

import logging
from typing import Optional
from pathlib import Path

from .base import TestExecutionMode

log = logging.getLogger(__name__)


def resolve_test_execution_mode(vm, playbook_settings, cli_override: Optional[str] = None) -> TestExecutionMode:
    """
    Resolve test execution mode based on hypervisor and settings.

    Logic:
    1. Check CLI override (highest priority)
    2. Check playbook.settings.test_execution_mode
    3. Auto mode: QEMU → HOST, VirtualBox → AGENT

    Args:
        vm: VM instance (QEMUVM or VirtualBoxVM)
        playbook_settings: Playbook settings object (optional)
        cli_override: CLI-specified mode override (optional)

    Returns:
        TestExecutionMode enum value

    Raises:
        ValueError: If 'host' mode requested for VirtualBox or invalid mode string
    """
    from adare.hypervisor.qemu.vm import QEMUVM
    from adare.hypervisor.virtualbox.vm import VirtualBoxVM

    # Priority 1: CLI override
    if cli_override is not None:
        mode_str = cli_override
        log.info(f"Using CLI-specified test mode: {cli_override}")
    # Priority 2: Playbook settings
    elif playbook_settings and hasattr(playbook_settings, 'test_execution_mode'):
        mode_str = playbook_settings.test_execution_mode or 'auto'
        log.debug(f"Using playbook test mode: {mode_str}")
    # Priority 3: Default to auto
    else:
        mode_str = 'auto'
        log.debug(f"Using default test mode: auto")

    log.debug(f"Resolving test execution mode: mode={mode_str}, vm_type={type(vm).__name__}")

    if mode_str not in ('auto', 'agent', 'host'):
        raise ValueError(
            f"Invalid test_execution_mode '{mode_str}'. "
            f"Must be one of: 'auto', 'agent', 'host'"
        )

    if mode_str == 'agent':
        log.info("Using agent-based test execution (explicit setting)")
        return TestExecutionMode.AGENT

    if mode_str == 'host':
        if not isinstance(vm, QEMUVM):
            raise ValueError(
                "test_execution_mode='host' is only supported for QEMU VMs. "
                "VirtualBox requires agent-based execution (test_execution_mode='agent'). "
                "Use test_execution_mode='auto' for automatic selection."
            )
        log.info("Using host-based test execution (explicit setting)")
        return TestExecutionMode.HOST

    # Auto mode: agent for all hypervisors (host mode requires explicit opt-in)
    if isinstance(vm, QEMUVM):
        log.info("Using agent-based test execution for QEMU (auto mode)")
        return TestExecutionMode.AGENT
    elif isinstance(vm, VirtualBoxVM):
        log.info("Using agent-based test execution for VirtualBox (auto mode)")
        return TestExecutionMode.AGENT
    else:
        log.warning(f"Unknown VM type {type(vm).__name__}, defaulting to agent test mode")
        return TestExecutionMode.AGENT
