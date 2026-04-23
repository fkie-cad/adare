"""
Base classes and utilities for action execution.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Any


class GUIExecutionMode(Enum):
    """GUI automation execution modes."""
    AGENT = "agent"  # WebSocket to adarevm agent (pyautogui)
    HOST = "host"    # Direct hypervisor commands (QMP for QEMU)


class TestExecutionMode(Enum):
    """Test execution modes."""
    AGENT = "agent"  # WebSocket to adarevm agent (tests run inside VM)
    HOST = "host"    # Tests run on host, files pulled via QGA


@dataclass
class ActionResult:
    """Result of a playbook action execution."""
    success: bool
    message: str = ""
    coordinates: tuple[int, int] | None = None
    data: dict | None = None
    execution_time: float | None = None


def serialize_target(target) -> dict[str, Any] | None:
    """Serialize Target object for JSON storage."""
    if not target:
        return None
    from adare.types.actions import converter
    return converter.unstructure(target)


def get_target_info(target) -> dict[str, Any] | None:
    """Extract target information for event logging."""
    if not target:
        return None

    info = {}
    if hasattr(target, 'image') and target.image:
        info['image'] = target.image
    if hasattr(target, 'text') and target.text:
        info['text'] = target.text
    if hasattr(target, 'position') and target.position:
        info['position'] = target.position
    if hasattr(target, 'strategy') and target.strategy:
        strategy_name = target.strategy.__class__.__name__
        info['strategy'] = strategy_name
        # Add strategy parameters if available
        if hasattr(target.strategy, '__dict__'):
            import attrs
            if attrs.has(target.strategy):
                strategy_params = attrs.asdict(target.strategy)
                if strategy_params:
                    info['strategy_params'] = strategy_params

    return info if info else None
