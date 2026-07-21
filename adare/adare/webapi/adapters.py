"""
DTO adapters for converting ADARE internal types to JSON-serializable formats.
"""

import enum
import inspect
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, TypeVar

from adare.core.result import Result

T = TypeVar("T")

log = logging.getLogger(__name__)


def serialize_value(value: Any) -> Any:
    """
    Recursively serialize a value to JSON-compatible format.

    Handles Path, datetime, Enum members, and other non-JSON types.
    """
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, enum.Enum):
        # Enum members (e.g. StatusEnum) must serialize to their name, not be
        # vars()'d — vars() reaches __objclass__ -> the class -> enum machinery
        # (a builtin_function_or_method) that FastAPI's encoder cannot handle.
        return value.name
    if isinstance(value, dict):
        return {k: serialize_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialize_value(item) for item in value]
    if callable(value) or isinstance(value, type) or inspect.ismodule(value):
        # Defense-in-depth: never pass a callable/class/module through to the
        # encoder. Surface it as a named warning + serializable placeholder so a
        # future stray leak is visible instead of an opaque FastAPI 500.
        log.warning("serialize_value: refusing to serialize non-data value %r", value)
        return repr(value)
    if hasattr(value, "__dict__") and not isinstance(value, type):
        # For dataclasses and similar instances (never a class/type).
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
    if result.success:
        return {
            "success": True,
            "data": serialize_value(result.data),
        }
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
