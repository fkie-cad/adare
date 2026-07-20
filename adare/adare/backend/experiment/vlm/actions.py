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

_KINDS = {CLICK, DOUBLE_CLICK, TYPE, KEY, SCROLL, WAIT, NOTE, DONE}

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
  {"reasoning": "...", "action": "done", "summary": "<what was accomplished>"}

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
        if 'x' not in obj or 'y' not in obj:
            raise VLMError(f'{kind} action missing x/y: {obj!r}')
        w = screen_width or 1
        h = screen_height or 1
        action.x = _scale_coord(int(obj['x']), w, coord_space)
        action.y = _scale_coord(int(obj['y']), h, coord_space)
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

    return action
