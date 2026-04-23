"""
DTO adapters for converting ADARE internal types to JSON-serializable formats.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

from adare.core.result import Result
from adare.types.devmode import (
    CheckpointInfo,
    DevSessionInfo,
    DevSessionListItem,
    DevSessionState,
)

T = TypeVar("T")


def serialize_value(value: Any) -> Any:
    """
    Recursively serialize a value to JSON-compatible format.

    Handles Path, datetime, and other non-JSON types.
    """
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: serialize_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialize_value(item) for item in value]
    if hasattr(value, "__dict__"):
        # For dataclasses and similar objects
        return serialize_value(vars(value))
    return value


def result_to_response[T](result: Result[T]) -> dict[str, Any]:
    """
    Convert a Result[T] to a FastAPI response dict.

    Args:
        result: Result object from ADARE API

    Returns:
        Dict with 'success', 'data', and optional 'error' fields
    """
    if result.is_success():
        return {
            "success": True,
            "data": serialize_value(result.value),
        }
    return {
        "success": False,
        "error": {
            "type": type(result.error).__name__,
            "message": str(result.error),
        },
    }


def session_info_to_dict(session_info: DevSessionInfo) -> dict[str, Any]:
    """Convert DevSessionInfo to JSON-serializable dict."""
    return {
        "session_id": session_info.session_id,
        "project_name": session_info.project_name,
        "experiment_name": session_info.experiment_name,
        "environment_name": session_info.environment_name,
        "vm_running": session_info.vm_running,
        "websocket_connected": session_info.websocket_connected,
        "hypervisor_type": session_info.hypervisor_type,
        "created_at": session_info.created_at.isoformat(),
        "last_activity": session_info.last_activity.isoformat(),
    }


def session_list_item_to_dict(item: DevSessionListItem) -> dict[str, Any]:
    """Convert DevSessionListItem to JSON-serializable dict."""
    return {
        "session_id": item.session_id,
        "project_name": item.project_name,
        "experiment_name": item.experiment_name,
        "environment_name": item.environment_name,
        "status": item.status,
        "created_at": item.created_at.isoformat(),
        "action_count": item.action_count,
    }


def session_state_to_dict(state: DevSessionState) -> dict[str, Any]:
    """Convert DevSessionState to JSON-serializable dict."""
    return {
        "session_id": state.session_id,
        "variables": serialize_value(state.variables),
        "checkpoints": [checkpoint_info_to_dict(cp) for cp in state.checkpoints],
        "last_action": state.last_action,
        "action_count": state.action_count,
        "vm_status": state.vm_status,
    }


def checkpoint_info_to_dict(checkpoint: CheckpointInfo) -> dict[str, Any]:
    """Convert CheckpointInfo to JSON-serializable dict."""
    return {
        "name": checkpoint.name,
        "description": checkpoint.description,
        "created_at": checkpoint.created_at.isoformat(),
        "memory_size_mb": checkpoint.memory_size_mb,
        "disk_size_mb": checkpoint.disk_size_mb,
        "variables_snapshot": serialize_value(checkpoint.variables_snapshot),
    }


def actions_to_yaml(actions: list[dict[str, Any]], settings: dict[str, Any]) -> str:
    """
    Convert action list and settings to YAML format.

    Args:
        actions: List of action dictionaries
        settings: Playbook settings (idle, timeout, etc.)

    Returns:
        YAML string
    """
    import yaml

    playbook_dict = {
        "settings": settings,
        "actions": actions,
    }

    return yaml.dump(playbook_dict, default_flow_style=False, sort_keys=False)


def yaml_to_actions(yaml_content: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Parse YAML content into actions and settings.

    Args:
        yaml_content: YAML string

    Returns:
        Tuple of (actions, settings)
    """
    import yaml

    playbook_dict = yaml.safe_load(yaml_content)

    actions = playbook_dict.get("actions", [])
    settings = playbook_dict.get("settings", {})

    return actions, settings
