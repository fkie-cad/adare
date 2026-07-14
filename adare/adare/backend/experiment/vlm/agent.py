"""Autonomous GUI agent: perceive -> decide -> act, recording a playbook.

Given an :class:`AbstractGUIExecutor` (any hypervisor), a natural-language
goal and (optionally) a :class:`PlaybookRecorder`, the agent runs a closed
loop: screenshot -> ask the vision model for the next action -> execute it
over the executor's QMP primitives -> record it -> repeat until the model
says ``done`` or a step / wall-clock / stall budget trips.

The agent is installer-agnostic and reusable by real experiments: hand it a
goal like "open Firefox and go to X" against a running experiment VM.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from ..execution.gui_executor_interface import AbstractGUIExecutor
from . import actions as A
from .actions import AgentAction, parse_action
from .client import VLMClient
from .exceptions import AgentError, PlaybookRecordingError, VLMError
from .recorder import PlaybookRecorder

log = logging.getLogger(__name__)


_SYSTEM_PROMPT = """\
You are an autonomous agent operating a computer through screenshots. You are \
shown the current screen and must decide the single next action that makes \
progress toward the goal. You control the mouse and keyboard only — there is \
no terminal and no file access.

{schema}

Rules:
- Emit exactly ONE JSON action per turn and nothing else.
- Prefer clicking visible buttons/fields over guessing keyboard shortcuts.
- After an action that changes the screen (e.g. clicking "Next"), use "wait" \
with until_describe naming what should appear before you continue.
- When the goal is fully achieved (e.g. installation finished / system \
rebooting), emit "done" with a short summary.
- If you are stuck or the screen has not changed, try a different element \
rather than repeating the same click.
"""


@dataclass
class StepRecord:
    index: int
    action_kind: str
    describe: str
    reasoning: str
    result_status: str
    screenshot_file: str | None = None


@dataclass
class AgentRunResult:
    success: bool
    reason: str
    steps: list[StepRecord] = field(default_factory=list)
    summary: str = ''
    playbook_path: Path | None = None
    report_path: Path | None = None


class GuiAgent:
    """Drives a GUI toward a goal and records a replayable playbook."""

    def __init__(
        self,
        gui_executor: AbstractGUIExecutor,
        client: VLMClient,
        goal: str,
        *,
        acceptance_spec: dict[str, Any] | None = None,
        recorder: PlaybookRecorder | None = None,
        run_dir: str | Path | None = None,
        hints: list[str] | None = None,
        coord_space: str = 'absolute',
        locate_client: Any = None,
        locate_crop_margin: int = 16,
        locate_crop_min: int = 72,
        max_steps: int = 80,
        stall_limit: int = 6,
        wall_clock_seconds: int = 3600,
        step_settle_seconds: float = 1.5,
    ):
        self.executor = gui_executor
        self.client = client
        self.goal = goal
        self.acceptance_spec = acceptance_spec or {}
        self.recorder = recorder
        # Optional described-element grounding backend (LocateAnythingClient).
        # When set, a click's recorded image crop is tightened to the true
        # element bounding box (plus a small context margin) instead of the
        # fixed box around the click point.
        self.locate_client = locate_client
        self.locate_crop_margin = locate_crop_margin
        self.locate_crop_min = locate_crop_min
        self.run_dir = Path(run_dir) if run_dir else None
        self.hints = hints or []
        self.coord_space = coord_space
        self.max_steps = max_steps
        self.stall_limit = stall_limit
        self.wall_clock_seconds = wall_clock_seconds
        self.step_settle_seconds = step_settle_seconds

        self._steps_dir: Path | None = None
        if self.run_dir:
            self._steps_dir = self.run_dir / 'steps'
            self._steps_dir.mkdir(parents=True, exist_ok=True)

        self._history: list[str] = []
        self._records: list[StepRecord] = []

    # -- perception ---------------------------------------------------------

    async def _capture(self) -> tuple[str, bytes, int, int]:
        """Screenshot the screen; return (base64, png bytes, width, height)."""
        result = await self.executor.screenshot()
        if result.get('status') != 'success':
            raise AgentError(f'Screenshot failed: {result.get("message")}')
        # QEMU host executor returns image.data; the interface documents 'screenshot'.
        b64 = None
        image = result.get('image')
        if isinstance(image, dict):
            b64 = image.get('data')
        b64 = b64 or result.get('screenshot')
        if not b64:
            raise AgentError('Screenshot result contained no image data')
        png = base64.b64decode(b64)
        with Image.open(io.BytesIO(png)) as img:
            width, height = img.size
        return b64, png, width, height

    # -- decision -----------------------------------------------------------

    def _build_messages(self, screenshot_b64: str) -> list[dict[str, Any]]:
        system = _SYSTEM_PROMPT.format(schema=A.ACTION_SCHEMA_DOC)
        parts: list[str] = [f'GOAL: {self.goal}']
        if self.hints:
            parts.append('HINTS:\n' + '\n'.join(f'- {h}' for h in self.hints))
        if self._history:
            recent = self._history[-12:]
            parts.append('ACTIONS SO FAR:\n' + '\n'.join(recent))
        parts.append('This is the current screen. Decide the next action.')
        user_text = '\n\n'.join(parts)
        return [
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': [
                self.client.text_content(user_text),
                self.client.image_content(screenshot_b64),
            ]},
        ]

    async def _decide(self, screenshot_b64: str, width: int, height: int) -> AgentAction:
        messages = self._build_messages(screenshot_b64)
        reply = await self.client.chat(messages, temperature=0.0, max_tokens=800)
        return parse_action(
            reply, coord_space=self.coord_space,
            screen_width=width, screen_height=height,
        )

    # -- grounding ----------------------------------------------------------

    def _ground_click_bbox(self, pre_png: bytes, action: AgentAction) -> list[float] | None:
        """Ask the grounding backend for the clicked element's bounding box.

        Returns an ``[x1, y1, x2, y2]`` box — the grounded element (preferring
        one that contains the model's own click point) expanded by the context
        margin — for the recorder to crop, or ``None`` when no backend is
        configured, the element has no
        description, or grounding fails/misses — in which case the recorder
        falls back to the fixed box around the click point.
        """
        if not self.locate_client or not action.describe:
            return None
        try:
            b64 = base64.b64encode(pre_png).decode('ascii')
            det = self.locate_client.best_for(
                b64, action.describe, near=(float(action.x), float(action.y)),
            )
        # LocateAnythingError is a RuntimeError; also guard malformed responses.
        # Grounding is best-effort — a miss must never abort the agent run.
        except (RuntimeError, OSError, ValueError, TypeError, KeyError, IndexError) as exc:
            log.warning('LocateAnything grounding failed (%s); using fixed crop', exc)
            return None
        if det is None:
            log.info('LocateAnything found no box for %r; using fixed crop', action.describe)
            return None
        box = self._pad_box(det.box)
        log.info('LocateAnything grounded %r to box %s (crop %s)', action.describe, det.box, box)
        return box

    def _pad_box(self, box: tuple[float, float, float, float]) -> list[float]:
        """Expand a grounded element box by the context margin + minimum size.

        Keeps the crop centred on the element but distinctive enough for the CV
        replay matcher (a bare box can be tiny or a generic glyph). The box is
        returned unclamped; :func:`recorder.crop_box` clamps it to the image.
        """
        x1, y1, x2, y2 = box
        m = self.locate_crop_margin
        x1, y1, x2, y2 = x1 - m, y1 - m, x2 + m, y2 + m
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        half = self.locate_crop_min / 2
        if x2 - x1 < self.locate_crop_min:
            x1, x2 = cx - half, cx + half
        if y2 - y1 < self.locate_crop_min:
            y1, y2 = cy - half, cy + half
        return [x1, y1, x2, y2]

    # -- action execution + recording --------------------------------------

    async def _execute(self, action: AgentAction, pre_png: bytes) -> str:
        """Execute one action over the GUI executor; record it. Return status."""
        kind = action.kind
        if kind in (A.CLICK, A.DOUBLE_CLICK):
            double = kind == A.DOUBLE_CLICK
            button = 'left' if double else action.button
            res = await self.executor.click(action.x, action.y,
                                             'double' if double else button)
            if self.recorder:
                bbox = self._ground_click_bbox(pre_png, action)
                self.recorder.record_click(
                    pre_png, action.x, action.y, action.describe,
                    button=button, double=double, bbox=bbox,
                )
            return res.get('status', 'unknown')
        if kind == A.TYPE:
            res = await self.executor.keyboard('type', action.text or '')
            if self.recorder:
                self.recorder.record_type(action.text or '', action.describe)
            return res.get('status', 'unknown')
        if kind == A.KEY:
            combo = action.combo or ''
            mode = 'hotkey' if '+' in combo else 'press'
            res = await self.executor.keyboard(mode, combo)
            if self.recorder:
                self.recorder.record_key(combo, action.describe)
            return res.get('status', 'unknown')
        if kind == A.SCROLL:
            res = await self.executor.scroll(action.direction or 'down', action.amount or 3)
            if self.recorder:
                self.recorder.record_scroll(action.direction or 'down',
                                            action.amount or 3, action.describe)
            return res.get('status', 'unknown')
        if kind == A.WAIT:
            if self.recorder and action.until_describe:
                self.recorder.record_wait(action.until_describe)
            await asyncio.sleep(self.step_settle_seconds * 2)
            return 'waited'
        if kind == A.NOTE:
            return 'noted'
        if kind == A.DONE:
            return 'done'
        return 'unknown'

    # -- documentation ------------------------------------------------------

    def _persist_step(self, index: int, png: bytes, action: AgentAction, status: str) -> str | None:
        if not self._steps_dir:
            return None
        shot = self._steps_dir / f'step_{index:03d}.png'
        shot.write_bytes(png)
        note = self._steps_dir / f'step_{index:03d}.json'
        note.write_text(_json_step(index, action, status))
        return shot.name

    def _write_report(self, result: AgentRunResult) -> Path | None:
        if not self.run_dir:
            return None
        lines = [
            f'# GUI agent install report',
            '',
            f'**Goal:** {self.goal}',
            f'**Outcome:** {"SUCCESS" if result.success else "FAILED"} — {result.reason}',
            f'**Steps:** {len(result.steps)}',
            '',
            '## Steps',
            '',
        ]
        for s in result.steps:
            lines.append(f'### Step {s.index}: {s.action_kind} — {s.describe or "(no description)"}')
            if s.screenshot_file:
                lines.append(f'![step {s.index}](steps/{s.screenshot_file})')
            lines.append(f'- reasoning: {s.reasoning}')
            lines.append(f'- result: {s.result_status}')
            lines.append('')
        report = self.run_dir / 'install_report.md'
        report.write_text('\n'.join(lines))
        return report

    # -- main loop ----------------------------------------------------------

    async def run(self) -> AgentRunResult:
        start = time.monotonic()
        last_hash: str | None = None
        stall = 0

        for _ in range(self.max_steps):
            if time.monotonic() - start > self.wall_clock_seconds:
                return self._finish(False, 'wall-clock budget exceeded')

            b64, png, width, height = await self._capture()

            digest = hashlib.sha256(png).hexdigest()
            if digest == last_hash:
                stall += 1
            else:
                stall = 0
            last_hash = digest
            if stall >= self.stall_limit:
                return self._finish(False, f'screen unchanged for {stall} steps (stalled)')

            try:
                action = await self._decide(b64, width, height)
            except VLMError as exc:
                log.warning('Decision failed: %s', exc)
                return self._finish(False, f'model decision failed: {exc}')

            index = len(self._records) + 1
            status = await self._execute(action, png)
            shot_file = self._persist_step(index, png, action, status)

            self._records.append(StepRecord(
                index=index, action_kind=action.kind, describe=action.describe,
                reasoning=action.reasoning, result_status=status, screenshot_file=shot_file,
            ))
            self._history.append(
                f'{index}. {action.kind}({action.describe or action.summary}) -> {status}')

            if action.kind == A.DONE:
                return self._finish(True, 'agent reported done', summary=action.summary)

            await asyncio.sleep(self.step_settle_seconds)

        return self._finish(False, f'reached max steps ({self.max_steps})')

    def _finish(self, success: bool, reason: str, *, summary: str = '') -> AgentRunResult:
        result = AgentRunResult(
            success=success, reason=reason, steps=self._records, summary=summary,
        )
        if self.recorder and self.recorder.action_count:
            try:
                result.playbook_path = self.recorder.finalize()
            except PlaybookRecordingError as exc:
                log.warning('Could not finalize playbook: %s', exc)
        result.report_path = self._write_report(result)
        return result


def _json_step(index: int, action: AgentAction, status: str) -> str:
    import json
    return json.dumps({
        'step': index, 'action': action.kind, 'describe': action.describe,
        'reasoning': action.reasoning, 'status': status, 'raw': action.raw,
    }, indent=2)
