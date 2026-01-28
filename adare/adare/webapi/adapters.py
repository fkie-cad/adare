"""
DTO adapters for converting ADARE internal types to JSON-serializable formats.
"""

from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar, Union

from adare.core.result import Result

T = TypeVar("T")


def serialize_value(value: Any) -> Any:
    """
    Recursively serialize a value to JSON-compatible format.

    Handles Path, datetime, and other non-JSON types.
    """
    if isinstance(value, Path):
        return str(value)
    elif isinstance(value, datetime):
        return value.isoformat()
    elif isinstance(value, dict):
        return {k: serialize_value(v) for k, v in value.items()}
    elif isinstance(value, (list, tuple)):
        return [serialize_value(item) for item in value]
    elif hasattr(value, "__dict__"):
        # For dataclasses and similar objects
        return serialize_value(vars(value))
    else:
        return value


def result_to_response(result: Result[T]) -> dict[str, Any]:
    """
    Convert a Result[T] to a FastAPI response dict.

    Args:
        result: Result object from ADARE API

    Returns:
        Dict with 'success', 'data', and optional 'error' fields
    """
    if result.success:
        return {
            "success": True,
            "data": serialize_value(result.data),
        }
    else:
        return {
            "success": False,
            "error": {
                "code": result.error.code if result.error else "UNKNOWN",
                "message": result.error.message if result.error else "Unknown error",
                "solutions": result.error.solutions if result.error and result.error.solutions else []
            },
        }


# Note: These converter functions are not currently used.
# The serialize_value() function handles DTO serialization automatically.
#
# def session_info_to_dict(session_info) -> dict[str, Any]:
#     """Convert DevSessionInfo to JSON-serializable dict."""
#     ...
#
# def session_list_item_to_dict(item) -> dict[str, Any]:
#     """Convert DevSessionListItem to JSON-serializable dict."""
#     ...
#
# def session_state_to_dict(state) -> dict[str, Any]:
#     """Convert DevSessionState to JSON-serializable dict."""
#     ...
#
# def checkpoint_info_to_dict(checkpoint) -> dict[str, Any]:
#     """Convert CheckpointInfo to JSON-serializable dict."""
#     ...


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
