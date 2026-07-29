"""Action schema shared by the GUI agent and its playbook recorder.

The vision model replies with exactly one structured action per turn. This
module defines the vocabulary, the JSON contract sent to the model, and a
robust parser that tolerates chatty models (code fences, leading reasoning).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from .exceptions import VLMError

log = logging.getLogger(__name__)

# Action kinds the model may emit.
CLICK = 'click'
DOUBLE_CLICK = 'double_click'
TYPE = 'type'
KEY = 'key'
SCROLL = 'scroll'
WAIT = 'wait'
NOTE = 'note'
DONE = 'done'
STEP_DONE = 'step_done'
RESTART_VM = 'restart_vm'

_KINDS = {CLICK, DOUBLE_CLICK, TYPE, KEY, SCROLL, WAIT, NOTE, DONE, STEP_DONE, RESTART_VM}

# The human-readable schema handed to the model in the system prompt.
ACTION_SCHEMA_DOC = """\
Reply with a SINGLE JSON object (no prose outside it) describing the next
action. Fields depend on "action":

  {"reasoning": "<why>", "action": "click", "x": <int>, "y": <int>,
   "button": "left|right", "describe": "<what you are clicking, in words>"}
  {"reasoning": "...", "action": "double_click", "x": <int>, "y": <int>,
   "describe": "..."}
  {"reasoning": "...", "action": "type", "text": "<text to type>",
   "describe": "<the field being filled>"}
  {"reasoning": "...", "action": "key", "combo": "<e.g. enter, tab, ctrl+a>",
   "describe": "<intent>"}
  {"reasoning": "...", "action": "scroll", "direction": "up|down",
   "amount": <int>, "describe": "..."}
  {"reasoning": "...", "action": "wait",
   "until_describe": "<what should appear on screen before continuing>"}
  {"reasoning": "...", "action": "note"}          # observe, take no action
  {"reasoning": "...", "action": "step_done", "summary": "<what was accomplished>"}
  {"reasoning": "...", "action": "done", "summary": "<what was accomplished>"}
  {"reasoning": "...", "action": "restart_vm", "memory_mb": <int optional>,
   "reason": "<why the VM seems under-resourced/unresponsive>"}

Use "step_done" when the CURRENT sub-goal is satisfied (more sub-goals may
follow); use "done" only when the WHOLE goal is complete. When no sub-goal is
named, treat "step_done" and "done" the same.

Use "restart_vm" ONLY when the screen is persistently unresponsive across
several steps or you suspect the VM is under-resourced (e.g. the guest agent /
window keeps freezing). It cold-reboots the VM — optionally with more RAM via
"memory_mb" (in MB) — and DISCARDS all in-VM progress so far, so use it early
or as a last resort. After a restart you begin the goal again from a clean boot
on the resized VM. Omit "memory_mb" to reboot at the current size.

Coordinates MUST refer to the exact image you were shown."""


@dataclass
class AgentAction:
    """One parsed action from the model."""

    kind: str
    reasoning: str = ''
    describe: str = ''
    # click / double_click
    x: int | None = None
    y: int | None = None
    button: str = 'left'
    # type
    text: str | None = None
    # key
    combo: str | None = None
    # scroll
    direction: str | None = None
    amount: int | None = None
    # wait
    until_describe: str | None = None
    # done
    summary: str = ''
    # restart_vm: optional new RAM size in MB (None -> reboot at current size)
    memory_mb: int | None = None
    # step_done: set True when the model signals the current sub-goal (not the
    # whole goal) is complete; the planning orchestrator ends the sub-goal run.
    step_done: bool = False
    raw: dict[str, Any] = field(default_factory=dict)
    # Transient, populated by the agent loop (not part of the model JSON
    # contract): the grounded element crop box the recorder should use for a
    # click, as ``[x1, y1, x2, y2]``. ``None`` -> recorder falls back to the
    # fixed box around the click point.
    crop_bbox: list[float] | None = None
    # Transient: the model's original click point before a LocateAnything
    # override (only set when locate_click actually moved x/y). Kept so the
    # visual step log can show where the click was moved FROM -> TO.
    vlm_point: tuple[int, int] | None = None


def _extract_json_object(reply: str) -> dict[str, Any]:
    """Pull the first balanced ``{...}`` object out of a model reply."""
    text = reply.strip()

    # Strip a ```json ... ``` fence if present.
    fence = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if fence:
        text = fence.group(1)

    # Find the first balanced brace span.
    start = text.find('{')
    if start == -1:
        raise VLMError(f'No JSON object in model reply: {reply!r}')
    depth = 0
    for idx in range(start, len(text)):
        ch = text[idx]
        if ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                blob = text[start:idx + 1]
                try:
                    return json.loads(blob)
                except json.JSONDecodeError as exc:
                    raise VLMError(f'Malformed JSON in model reply: {exc}: {blob!r}') from exc
    raise VLMError(f'Unbalanced JSON braces in model reply: {reply!r}')


def _scale_coord(value: int, extent: int, coord_space: str) -> int:
    """Reconcile the model's coordinate convention to absolute pixels."""
    if coord_space == 'normalized_1000':
        return max(0, min(extent - 1, round(value / 1000.0 * extent)))
    return max(0, min(extent - 1, int(value)))


def _coerce_coord(value) -> int:
    """Coerce a single coordinate (int/float/str) to int, or raise ValueError.

    Booleans are rejected (``True`` must not silently become ``1``). Non-numeric
    types raise so the caller can turn it into a *repairable* ``VLMError`` rather
    than letting an unhandled ``TypeError`` abort the whole run.
    """
    if isinstance(value, bool):
        raise ValueError(f'boolean is not a coordinate: {value!r}')
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        return int(float(value.strip()))
    raise ValueError(f'non-numeric coordinate {type(value).__name__}: {value!r}')


def _normalize_point(x_raw, y_raw):
    """Normalise a model's click point when it uses list-valued coordinates.

    Some vision models return the point packed into a single field —
    ``x: [px, py]`` (often with ``y`` omitted), or nested as ``x: [[px, py]]`` —
    or wrap each coordinate in a list (``x: [px]``). Returns ``(x, y)`` as raw
    scalars (``None`` where unrecoverable, so the caller raises a repairable
    "missing x/y").
    """
    # Unwrap one nested level: [[px, py]] -> [px, py].
    if (isinstance(x_raw, (list, tuple)) and len(x_raw) == 1
            and isinstance(x_raw[0], (list, tuple))):
        x_raw = x_raw[0]
    # A 2+ element point in x with no usable y -> x carries the whole point.
    y_empty = y_raw is None or (isinstance(y_raw, (list, tuple)) and not y_raw)
    if isinstance(x_raw, (list, tuple)) and len(x_raw) >= 2 and y_empty:
        return x_raw[0], x_raw[1]
    # Otherwise take the first element of any list-valued coordinate.
    if isinstance(x_raw, (list, tuple)):
        x_raw = x_raw[0] if x_raw else None
    if isinstance(y_raw, (list, tuple)):
        y_raw = y_raw[0] if y_raw else None
    return x_raw, y_raw


def parse_action(
    reply: str,
    *,
    coord_space: str = 'absolute',
    screen_width: int | None = None,
    screen_height: int | None = None,
) -> AgentAction:
    """Parse a model reply into an :class:`AgentAction`.

    Click coordinates are converted to absolute pixels using ``coord_space``
    and the current screen dimensions.

    Raises:
        VLMError: if the reply is not a recognised action.
    """
    obj = _extract_json_object(reply)
    kind = str(obj.get('action', '')).strip().lower()
    if kind not in _KINDS:
        raise VLMError(f'Unknown action {kind!r} in reply: {obj!r}')

    action = AgentAction(
        kind=kind,
        reasoning=str(obj.get('reasoning', '')),
        describe=str(obj.get('describe', '')),
        raw=obj,
    )

    if kind in (CLICK, DOUBLE_CLICK):
        # Models sometimes pack the point into one list field or wrap coords in
        # lists; normalise to scalars first so a list value cannot raise an
        # unhandled TypeError (which would abort the run instead of repairing).
        x_raw, y_raw = _normalize_point(obj.get('x'), obj.get('y'))
        if x_raw is None or y_raw is None:
            raise VLMError(f'{kind} action missing x/y: {obj!r}')
        w = screen_width or 1
        h = screen_height or 1
        try:
            x_val = _coerce_coord(x_raw)
            y_val = _coerce_coord(y_raw)
        except ValueError as exc:
            raise VLMError(
                f'{kind} action has non-numeric x/y ({x_raw!r}, {y_raw!r}): {obj!r}'
            ) from exc
        action.x = _scale_coord(x_val, w, coord_space)
        action.y = _scale_coord(y_val, h, coord_space)
        action.button = str(obj.get('button', 'left')).lower()
    elif kind == TYPE:
        action.text = str(obj.get('text', ''))
    elif kind == KEY:
        combo = obj.get('combo') or obj.get('key')
        if not combo:
            raise VLMError(f'key action missing combo: {obj!r}')
        action.combo = str(combo)
    elif kind == SCROLL:
        action.direction = str(obj.get('direction', 'down')).lower()
        action.amount = int(obj.get('amount', 3))
    elif kind == WAIT:
        action.until_describe = str(obj.get('until_describe', '')) or None
    elif kind == DONE:
        action.summary = str(obj.get('summary', ''))
    elif kind == STEP_DONE:
        action.summary = str(obj.get('summary', ''))
        action.step_done = True
    elif kind == RESTART_VM:
        # "reason" is folded into describe/reasoning for the step log; memory_mb
        # is optional and only coerced when present (a bad value is repairable).
        reason = obj.get('reason')
        if reason and not action.describe:
            action.describe = str(reason)
        mem_raw = obj.get('memory_mb')
        if mem_raw is not None:
            try:
                action.memory_mb = int(float(mem_raw))
            except (TypeError, ValueError) as exc:
                raise VLMError(
                    f'restart_vm action has non-numeric memory_mb ({mem_raw!r}): {obj!r}'
                ) from exc

    return action
