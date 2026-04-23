"""Internal step action types used for step event tracking.

These actions represent the internal steps that make up higher-level playbook actions.
They are not user-facing and should not be included in playbook YAML files.
"""

from typing import Any

import attrs


@attrs.define
class FindAction:
    """Internal step action for finding targets using CV/OCR.

    This represents the step that resolves a target (image/text) to screen coordinates.
    Used for event tracking of target resolution steps.
    """
    description: str = ""
    target_info: dict[str, Any] | None = None


@attrs.define
class ExecuteAction:
    """Internal step action for executing at resolved coordinates.

    This represents the step that performs the actual interaction (click, drag, etc.)
    at coordinates resolved by FindAction. Used for event tracking of execution steps.
    """
    description: str = ""
    coordinates: tuple[int, int] | None = None
