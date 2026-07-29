"""Deterministic playbook replay (no LLM) with optional VLM self-heal.

Replay drives ADARE's existing :class:`ActionExecutor` +
:class:`MCPTargetResolver` — the same CV/OCR engine used by ordinary
experiments — over a recorded playbook. No vision model is involved.

If a click's target no longer matches (the CV engine returns nothing), and a
:class:`VLMClient` is supplied, the miss falls back to the vision model to
re-locate the element, clicks it directly over QMP, and re-crops the image
target in place so the playbook stays current across installer releases.
"""

from __future__ import annotations

import base64
import io
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from adare.types.playbook import ClickAction, parse_playbook

from ..action_executor import ActionExecutor
from ..target_resolver import MCPConditionChecker, MCPTargetResolver
from .actions import _extract_json_object, _scale_coord
from .client import VLMClient
from .exceptions import VLMError
from .recorder import crop_around

log = logging.getLogger(__name__)

_DEFAULT_MCP_GUI_URL = 'http://localhost:13109/mcp'


@dataclass
class ReplayResult:
    success: bool
    total: int
    executed: int
    healed: list[int] = field(default_factory=list)
    failures: list[dict[str, Any]] = field(default_factory=list)


def _decode_png(b64: str) -> tuple[bytes, int, int]:
    png = base64.b64decode(b64)
    with Image.open(io.BytesIO(png)) as img:
        w, h = img.size
    return png, w, h


async def _capture(gui_executor) -> tuple[str, bytes, int, int]:
    result = await gui_executor.screenshot()
    if result.get('status') != 'success':
        raise VLMError(f'Screenshot failed during heal: {result.get("message")}')
    image = result.get('image')
    b64 = image.get('data') if isinstance(image, dict) else None
    b64 = b64 or result.get('screenshot')
    if not b64:
        raise VLMError('Screenshot result contained no image data during heal')
    png, w, h = _decode_png(b64)
    return b64, png, w, h


async def _locate(
    client: VLMClient,
    describe: str,
    goal: str,
    screenshot_b64: str,
    width: int,
    height: int,
    coord_space: str,
) -> tuple[int, int]:
    """Ask the vision model for the pixel coordinates of a described element."""
    prompt = (
        f'Goal context: {goal}\n\n'
        f'Locate this UI element on the screenshot: "{describe}".\n'
        'Reply with a single JSON object: {"x": <int>, "y": <int>} giving the '
        'point to click. Coordinates refer to the exact image shown.'
    )
    messages = [
        {'role': 'user', 'content': [
            client.text_content(prompt),
            client.image_content(screenshot_b64),
        ]},
    ]
    reply = await client.chat(messages, temperature=0.0, max_tokens=200)
    obj = _extract_json_object(reply)
    if 'x' not in obj or 'y' not in obj:
        raise VLMError(f'Locate reply missing x/y: {obj!r}')
    x = _scale_coord(int(obj['x']), width, coord_space)
    y = _scale_coord(int(obj['y']), height, coord_space)
    return x, y


async def _heal_click(
    gui_executor,
    client: VLMClient,
    action: ClickAction,
    img_dir: Path,
    goal: str,
    coord_space: str,
) -> bool:
    """Re-locate a missed click with the VLM, click it, and re-crop the target."""
    describe = action.description or (action.target.text or action.target.image or 'target')
    b64, png, w, h = await _capture(gui_executor)
    try:
        x, y = await _locate(client, describe, goal, b64, w, h, coord_space)
    except VLMError as exc:
        log.warning('Self-heal locate failed: %s', exc)
        return False

    click_type = action.type if action.type in ('left', 'right', 'double') else 'left'
    res = await gui_executor.click(x, y, click_type)
    if res.get('status') != 'success':
        log.warning('Self-heal click failed: %s', res.get('message'))
        return False

    # Patch the playbook's image target in place (same filename → stable YAML).
    if action.target.image:
        try:
            cropped, _ = crop_around(png, x, y)
            cropped.save(img_dir / action.target.image)
            log.info('Self-heal re-cropped image target %s', action.target.image)
        except (OSError, ValueError) as exc:
            log.warning('Self-heal re-crop failed (click still applied): %s', exc)
    return True


async def run_playbook(
    vm,
    playbook_path: str | Path,
    *,
    mcp_gui_url: str = _DEFAULT_MCP_GUI_URL,
    os_key: str = 'linux',
    heal: bool = False,
    client: VLMClient | None = None,
    coord_space: str = 'absolute',
    goal: str = '',
) -> ReplayResult:
    """Replay a recorded playbook against a running QEMU ``vm``.

    Args:
        vm: a started ``QEMUVM`` (host-side QMP GUI executor is selected
            automatically for QEMU).
        playbook_path: path to the ``.play.yaml`` playbook.
        mcp_gui_url: the MCP GUI (CV/OCR) server used by the resolver.
        heal: when True and ``client`` is set, fall back to the VLM on a
            click miss to re-locate + re-crop the target.
    """
    playbook_path = Path(playbook_path)
    playbook = parse_playbook(playbook_path)
    experiment_dir = playbook_path.parent
    img_dir = experiment_dir / 'img'

    resolver = MCPTargetResolver(
        experiment_dir=experiment_dir, mcp_gui_url=mcp_gui_url,
        vm_client=None, os_key=os_key,
    )
    checker = MCPConditionChecker(resolver)
    executor = ActionExecutor(
        websocket_client=None, target_resolver=resolver, condition_checker=checker,
        vm=vm, experiment_run_directory=experiment_dir, playbook=playbook,
    )
    gui_executor = executor.simple_actions.gui_executor

    healed: list[int] = []
    failures: list[dict[str, Any]] = []
    executed = 0

    for i, action in enumerate(playbook.actions):
        result = await executor.execute_action(action)
        executed += 1
        if result.success:
            continue

        recovered = False
        if heal and client is not None and isinstance(action, ClickAction):
            recovered = await _heal_click(gui_executor, client, action, img_dir, goal, coord_space)
            if recovered:
                healed.append(i)

        if not recovered:
            failures.append({
                'index': i,
                'action': type(action).__name__,
                'message': result.message,
            })

    return ReplayResult(
        success=not failures, total=len(playbook.actions),
        executed=executed, healed=healed, failures=failures,
    )
