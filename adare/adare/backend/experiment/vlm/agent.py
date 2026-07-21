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
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

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


# Substrings that mark a recoverable JSON *syntax* failure raised by
# ``actions._extract_json_object`` (the raw blob is present, only the JSON is
# broken). Anything else from ``parse_action`` is a *schema* failure (a missing
# coordinate / unknown action) that a text JSON-fixer cannot invent.
_SYNTAX_ERROR_MARKERS = (
    'No JSON object',
    'Malformed JSON in model reply',
    'Unbalanced JSON braces',
)


def _is_syntax_error(exc: Exception) -> bool:
    """True when ``exc`` is a recoverable-by-text JSON syntax failure."""
    msg = str(exc)
    return any(marker in msg for marker in _SYNTAX_ERROR_MARKERS)


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
        locate_click: bool = False,
        locate_crop_margin: int = 16,
        locate_crop_min: int = 72,
        max_steps: int = 80,
        stall_limit: int = 6,
        wall_clock_seconds: int = 3600,
        step_settle_seconds: float = 1.5,
        interactive: bool = False,
        decision_retry_limit: int = 2,
        repair_client: Any = None,
        progress: Callable[[dict], None] | None = None,
    ):
        self.executor = gui_executor
        self.client = client
        self.goal = goal
        self.acceptance_spec = acceptance_spec or {}
        self.recorder = recorder
        # Self-heal budget for a malformed / incomplete model decision. A pure
        # JSON-syntax slip is repaired by a cheap text-only call (no screenshot
        # re-sent) via ``repair_client`` if given, else the main client
        # text-only; a genuinely missing coordinate/choice costs a full vision
        # re-ask. ``decision_retry_limit`` recovery attempts follow the first
        # decision (default 2 -> 3 total) before ``run()`` fails the run.
        self.decision_retry_limit = decision_retry_limit
        self.repair_client = repair_client
        # Optional described-element grounding backend (LocateAnythingClient).
        # When set, a click's recorded image crop is tightened to the true
        # element bounding box (plus a small context margin) instead of the
        # fixed box around the click point.
        self.locate_client = locate_client
        # When True, LocateAnything owns the click coordinate (the VLM point
        # becomes a disambiguating hint + miss fallback). When False, LA only
        # tightens the recorded crop and the click lands at the VLM's point.
        self.locate_click = locate_click
        self.locate_crop_margin = locate_crop_margin
        self.locate_crop_min = locate_crop_min
        self.run_dir = Path(run_dir) if run_dir else None
        self.hints = hints or []
        self.coord_space = coord_space
        self.max_steps = max_steps
        self.stall_limit = stall_limit
        self.wall_clock_seconds = wall_clock_seconds
        self.step_settle_seconds = step_settle_seconds
        # Human-in-the-loop: when True, each proposed action pauses for the
        # user to approve / skip / quit before it is executed and recorded.
        self.interactive = interactive
        # Optional live-progress sink (a sync callback taking one event dict);
        # default None -> no-op. See :class:`.progress.AgentProgressReporter`.
        self.progress = progress
        # Cooperative graceful-stop flag (set by :meth:`request_stop`, e.g. from
        # a SIGINT handler). Checked at each loop boundary; a set flag ends the
        # run via ``_finish`` so the partial playbook / report are finalized.
        self._stop_requested = False

        self._steps_dir: Path | None = None
        if self.run_dir:
            self._steps_dir = self.run_dir / 'steps'
            self._steps_dir.mkdir(parents=True, exist_ok=True)

        self._history: list[str] = []
        self._records: list[StepRecord] = []
        # Set by ``execute_subgoal`` while the reactive loop is scoped to one
        # sub-goal (the planning orchestrator); ``None`` in whole-goal ``run()``.
        self._subgoal: str | None = None

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
        if self._subgoal:
            parts.append(
                f'SUB-GOAL (focus only on this now): {self._subgoal}\n'
                'Emit "step_done" as soon as THIS sub-goal is satisfied.')
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
        try:
            return parse_action(
                reply, coord_space=self.coord_space,
                screen_width=width, screen_height=height,
            )
        except VLMError as exc:
            # The model's intent was likely fine; only the serialization broke.
            # Try to recover cheaply before letting the run die on one glitch.
            return await self._recover_decision(reply, exc, screenshot_b64, width, height)

    async def _recover_decision(
        self, bad_reply: str, exc: VLMError,
        screenshot_b64: str, width: int, height: int,
    ) -> AgentAction:
        """Two-tier self-heal for a failed decision parse.

        A JSON *syntax* slip (recoverable blob, broken JSON) is fixed by a cheap
        text-only repair call; a *schema* failure (missing coordinate / unknown
        action) needs the screen again, so it costs a full vision re-ask. Up to
        ``self.decision_retry_limit`` attempts; on exhaustion the last
        :class:`VLMError` is re-raised so ``run()`` finishes false as today.
        """
        last_exc = exc
        last_reply = bad_reply
        n = self.decision_retry_limit
        for attempt in range(1, n + 1):
            reply: str | None = None
            try:
                if _is_syntax_error(last_exc):
                    log.warning(
                        'Decision parse failed (attempt %d/%d): %s; '
                        'repairing via cheap text repair', attempt, n, last_exc)
                    reply = await self._repair_json(last_reply, last_exc)
                else:
                    log.warning(
                        'Decision parse failed (attempt %d/%d): %s; '
                        'repairing via vision re-ask', attempt, n, last_exc)
                    reply = await self._vision_reask(screenshot_b64, last_exc)
                return parse_action(
                    reply, coord_space=self.coord_space,
                    screen_width=width, screen_height=height,
                )
            except VLMError as rexc:
                last_exc = rexc
                # Only carry a fresh reply forward for the next syntax repair;
                # if the chat call itself failed, keep the prior blob.
                if reply is not None:
                    last_reply = reply
        raise last_exc

    async def _repair_json(self, bad_reply: str, exc: VLMError) -> str:
        """Cheap text-only fix for a malformed-JSON decision.

        Sends NO screenshot — just the broken blob and the parser error — to the
        repair model (``self.repair_client`` if set, else the main client
        text-only), asking for only the corrected JSON object.
        """
        repair = self.repair_client or self.client
        system = (
            'You repair malformed JSON. You are given a broken JSON object that '
            'was meant to be a single GUI action, plus the parser error. Return '
            'ONLY the corrected JSON object — no prose, no code fence, no '
            "explanation. Preserve every field's intent; fix the syntax only. "
            'Do not invent missing coordinates or values.'
        )
        user_text = (
            f'The JSON parser failed with: {exc}\n\n'
            f'Broken reply:\n{bad_reply}\n\n'
            'Return the corrected single JSON object.'
        )
        messages = [
            {'role': 'system', 'content': system},
            {'role': 'user', 'content': [repair.text_content(user_text)]},
        ]
        return await repair.chat(messages, temperature=0.0, max_tokens=400)

    async def _vision_reask(self, screenshot_b64: str, exc: VLMError) -> str:
        """Full vision re-ask for a semantic decision failure.

        Rebuilds the normal decision messages (with the screenshot) and appends
        a short repair hint, sampling at a higher temperature so the model does
        not deterministically reproduce the same broken choice.
        """
        messages = self._build_messages(screenshot_b64)
        hint = (
            f'Your last reply could not be used: {exc}. Reply with ONE valid '
            'JSON action for THIS screen, including every required field '
            '(e.g. both "x" and "y" for a click, a known "action").'
        )
        messages.append({'role': 'user', 'content': [self.client.text_content(hint)]})
        return await self.client.chat(messages, temperature=0.4, max_tokens=800)

    # -- progress + graceful stop -------------------------------------------

    def request_stop(self) -> None:
        """Ask the run to stop cleanly at the next loop boundary.

        Safe to call from a signal handler: it only flips a flag. The reactive
        loop breaks to ``_finish(False, 'interrupted by user')`` which finalizes
        the partial playbook and report; the VM is left running.
        """
        self._stop_requested = True

    def _emit(self, event: dict) -> None:
        """Send one progress event to the sink; never raises."""
        if not self.progress:
            return
        try:
            self.progress(event)
        except (ValueError, RuntimeError, TypeError, KeyError) as exc:
            log.debug('progress sink error (ignored): %s', exc)

    def _emit_decided(self, index: int, action: AgentAction) -> None:
        coords = None
        if action.kind in (A.CLICK, A.DOUBLE_CLICK) and action.x is not None:
            coords = (action.x, action.y)
        self._emit({
            'type': 'decided', 'index': index, 'kind': action.kind,
            'describe': action.describe or action.summary or '',
            'coords': coords,
            'grounded': bool(action.crop_bbox) or bool(action.vlm_point),
            'reasoning': action.reasoning,
        })

    def _emit_executed(self, index: int, status: str, screenshot: str | None = None) -> None:
        self._emit({
            'type': 'executed', 'index': index, 'status': status,
            'screenshot': screenshot,
        })

    # -- interactive gate ---------------------------------------------------

    async def _confirm_step(self, action: AgentAction, index: int) -> str:
        """Pause and ask the user to approve the proposed action.

        Renders the action with a ``rich`` panel and reads a single keystroke
        on the CLI's real stdin (via a worker thread, so the asyncio loop is
        not blocked). Returns ``'approve'``, ``'skip'`` or ``'quit'``. On
        ``continue`` the gate is disabled for the rest of the run
        (``self.interactive = False``) and ``'approve'`` is returned.
        """
        from adare.console import console
        from rich.panel import Panel

        detail = action.describe or action.summary or ''
        header = f'Step {index} — {action.kind.upper()}'
        if detail:
            header += f'  "{detail}"'
        if action.kind in (A.CLICK, A.DOUBLE_CLICK) and action.x is not None:
            header += f'  @ ({action.x}, {action.y})'
        elif action.kind == A.TYPE and action.text is not None:
            header += f'  text={action.text!r}'
        elif action.kind == A.KEY and action.combo:
            header += f'  combo={action.combo!r}'

        body = [header]
        if action.reasoning:
            body.append(f'reason: {action.reasoning}')
        console.print(Panel('\n'.join(body), title='Confirm action', border_style='cyan'))

        prompt = '[a]pprove / [s]kip / [q]uit / [c]ontinue (run rest autonomously) > '
        while True:
            choice = (await asyncio.to_thread(input, prompt)).strip().lower()
            if choice in ('', 'a', 'approve'):
                return 'approve'
            if choice in ('s', 'skip'):
                return 'skip'
            if choice in ('q', 'quit'):
                return 'quit'
            if choice in ('c', 'continue'):
                self.interactive = False
                return 'approve'
            console.print("Please enter 'a', 's', 'q', or 'c'.")

    # -- grounding ----------------------------------------------------------

    def _ground_click(
        self, pre_png: bytes, action: AgentAction, width: int, height: int,
    ) -> None:
        """Ground a click's element before it executes (best-effort, never raises).

        Asks the grounding backend to locate ``action.describe`` on the screen,
        biased toward the box *containing* the VLM's own point (``near=``). On a
        hit it always sets ``action.crop_bbox`` (the padded element box for the
        recorder); and when :attr:`locate_click` is on it *also* overrides the
        click coordinate with the element centre (rounded, clamped to the
        screen), keeping the VLM's point only as the hint/fallback.

        A no-op (leaves the VLM point + fixed crop — today's behaviour) when no
        backend is configured, the action has no description, or the result
        would be used by neither the click nor the recorder. On a miss or any
        error it logs and returns, so the VLM point and fixed crop stand.
        """
        if not self.locate_client or not action.describe:
            return
        if not self.locate_click and not self.recorder:
            return
        try:
            b64 = base64.b64encode(pre_png).decode('ascii')
            det = self.locate_client.best_for(
                b64, action.describe, near=(float(action.x), float(action.y)),
            )
        # LocateAnythingError is a RuntimeError; also guard malformed responses.
        # Grounding is best-effort — a miss must never abort the agent run.
        except (RuntimeError, OSError, ValueError, TypeError, KeyError, IndexError) as exc:
            log.warning('LocateAnything grounding failed (%s); using VLM point + fixed crop', exc)
            return
        if det is None:
            log.info('LocateAnything found no box for %r; using VLM point + fixed crop',
                     action.describe)
            return
        action.crop_bbox = self._pad_box(det.box)
        if self.locate_click:
            cx, cy = det.center
            vlm_x, vlm_y = action.x, action.y
            action.vlm_point = (vlm_x, vlm_y)
            action.x = max(0, min(width - 1, round(cx)))
            action.y = max(0, min(height - 1, round(cy)))
            log.info(
                'LocateAnything grounded click %r to element centre (%d, %d); '
                'VLM point was (%s, %s); crop %s',
                action.describe, action.x, action.y, vlm_x, vlm_y, action.crop_bbox)
        else:
            log.info('LocateAnything grounded %r to box %s (crop %s)',
                     action.describe, det.box, action.crop_bbox)

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
                # crop_bbox was grounded in run() before this executed (or is
                # None -> recorder falls back to the fixed box around the point).
                self.recorder.record_click(
                    pre_png, action.x, action.y, action.describe,
                    button=button, double=double, bbox=action.crop_bbox,
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
        if kind == A.STEP_DONE:
            return 'step_done'
        return 'unknown'

    # -- documentation ------------------------------------------------------

    def _persist_step(self, index: int, png: bytes, action: AgentAction, status: str) -> str | None:
        if not self._steps_dir:
            return None
        shot = self._steps_dir / f'step_{index:03d}.png'
        # Visual log: for clicks, draw what was found (the grounded crop box) and
        # where we clicked (crosshair) — plus, if grounding moved the click, the
        # model's original point and a FROM->TO arrow — so a human can verify at
        # a glance. Best-effort: any drawing error falls back to the raw shot.
        shot.write_bytes(self._annotate_click_png(png, action, index))
        note = self._steps_dir / f'step_{index:03d}.json'
        note.write_text(_json_step(index, action, status))
        return shot.name

    def _annotate_click_png(self, png: bytes, action: AgentAction, index: int) -> bytes:
        """Overlay click markers on a click screenshot; return PNG bytes.

        Draws the grounded crop box (green, what was found/recorded), the
        executed click point (red crosshair), and — when LocateAnything moved
        the click — the model's original point (orange) with a line to the final
        point. Returns the input bytes unchanged for non-click actions or on any
        rendering error, so the visual log never breaks the run.
        """
        if action.kind not in (A.CLICK, A.DOUBLE_CLICK) or action.x is None:
            return png
        try:
            with Image.open(io.BytesIO(png)) as im:
                img = im.convert('RGB')
            draw = ImageDraw.Draw(img)
            green, red, orange, black = (
                (0, 210, 0), (255, 40, 40), (255, 150, 0), (0, 0, 0))

            if action.crop_bbox:
                x1, y1, x2, y2 = (round(v) for v in action.crop_bbox)
                draw.rectangle([x1, y1, x2, y2], outline=green, width=3)

            # From the model's original point (if grounding moved it) to the click.
            if action.vlm_point and action.vlm_point != (action.x, action.y):
                ox, oy = action.vlm_point
                draw.line([ox, oy, action.x, action.y], fill=orange, width=2)
                self._mark(draw, ox, oy, orange, r=7)

            cx, cy = action.x, action.y
            draw.line([cx - 11, cy, cx + 11, cy], fill=red, width=3)
            draw.line([cx, cy - 11, cx, cy + 11], fill=red, width=3)
            draw.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], outline=red, width=2)

            label = f'#{index} {action.kind} ({cx},{cy})'
            if action.vlm_point and action.vlm_point != (cx, cy):
                label += f'  [grounded from {action.vlm_point}]'
            if action.describe:
                label += f'  {action.describe[:70]}'
            font = _label_font(max(13, round(img.width / 110)))
            tb = draw.textbbox((0, 0), label, font=font)
            tw, th = tb[2] - tb[0], tb[3] - tb[1]
            draw.rectangle([0, 0, tw + 12, th + 12], fill=green)
            draw.text((6, 4), label, fill=black, font=font)

            buf = io.BytesIO()
            img.save(buf, format='PNG')
            return buf.getvalue()
        except (OSError, ValueError) as exc:
            log.warning('Could not annotate step %d screenshot (%s); saving raw', index, exc)
            return png

    @staticmethod
    def _mark(draw: ImageDraw.ImageDraw, x: int, y: int, color: tuple, *, r: int) -> None:
        draw.ellipse([x - r, y - r, x + r, y + r], outline=color, width=2)

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
            if self._stop_requested:
                return self._finish(False, 'interrupted by user')
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

            # Ground click coordinates before the human sees them and before
            # execution, so the interactive gate, the click and the recorded
            # crop all use the same (grounded) coordinate. Best-effort: on a
            # miss/error the VLM's own point + fixed crop stand.
            if action.kind in (A.CLICK, A.DOUBLE_CLICK):
                self._ground_click(png, action, width, height)

            self._emit_decided(index, action)

            if self.interactive:
                self._emit({'type': 'pause'})
                choice = await self._confirm_step(action, index)
                self._emit({'type': 'resume'})
                if choice == 'skip':
                    note = action.describe or action.summary or action.kind
                    self._records.append(StepRecord(
                        index=index, action_kind=action.kind, describe=action.describe,
                        reasoning=action.reasoning, result_status='skipped',
                    ))
                    self._emit_executed(index, 'skipped')
                    self._history.append(
                        f'{index}. {action.kind}({action.describe or action.summary}) '
                        f'-> user skipped: {note}')
                    await asyncio.sleep(self.step_settle_seconds)
                    continue
                if choice == 'quit':
                    return self._finish(False, 'stopped by user')
                # 'approve' (or 'continue', which also cleared self.interactive)
                # falls through to execute + record as normal.

            status = await self._execute(action, png)
            shot_file = self._persist_step(index, png, action, status)
            self._emit_executed(index, status, screenshot=shot_file)

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

    # -- sub-goal loop (used by the planning orchestrator) ------------------

    async def execute_subgoal(
        self,
        subgoal: str,
        plan_context: str = '',
        *,
        max_steps: int = 25,
        stall_limit: int = 4,
    ) -> str:
        """Run the reactive loop scoped to ONE sub-goal; return a short reason.

        This is the same perceive->decide->act loop as :meth:`run`, but budgeted
        per sub-goal and ended as soon as the model emits ``step_done`` (this
        sub-goal is satisfied) or ``done`` (the whole goal is). It reuses
        ``_capture``/``_decide``/``_ground_click``/``_execute``/``_persist_step``
        and appends to the shared history, records, and recorder so the verified
        blocks accumulate into one playbook. ``plan_context`` (the full plan and
        what is already done) is injected via the hints channel and a ``SUB-GOAL``
        line for the duration; both are restored on exit so a later ``run()`` is
        unaffected. Never raises for a stall/budget/decision failure — it returns
        a reason and lets the orchestrator's checker decide whether to backtrack.
        """
        start = time.monotonic()
        last_hash: str | None = None
        stall = 0
        prev_subgoal = self._subgoal
        prev_hints = self.hints
        self._subgoal = subgoal
        if plan_context:
            self.hints = [*self.hints, plan_context]
        try:
            for _ in range(max_steps):
                if self._stop_requested:
                    return 'interrupted by user'
                if time.monotonic() - start > self.wall_clock_seconds:
                    return 'wall-clock budget exceeded'

                b64, png, width, height = await self._capture()

                digest = hashlib.sha256(png).hexdigest()
                stall = stall + 1 if digest == last_hash else 0
                last_hash = digest
                if stall >= stall_limit:
                    return f'screen unchanged for {stall} steps (stalled)'

                try:
                    action = await self._decide(b64, width, height)
                except VLMError as exc:
                    log.warning('Sub-goal decision failed: %s', exc)
                    return f'model decision failed: {exc}'

                index = len(self._records) + 1

                if action.kind in (A.CLICK, A.DOUBLE_CLICK):
                    self._ground_click(png, action, width, height)

                self._emit_decided(index, action)

                if self.interactive:
                    self._emit({'type': 'pause'})
                    choice = await self._confirm_step(action, index)
                    self._emit({'type': 'resume'})
                    if choice == 'skip':
                        note = action.describe or action.summary or action.kind
                        self._records.append(StepRecord(
                            index=index, action_kind=action.kind, describe=action.describe,
                            reasoning=action.reasoning, result_status='skipped',
                        ))
                        self._emit_executed(index, 'skipped')
                        self._history.append(
                            f'{index}. {action.kind}({action.describe or action.summary}) '
                            f'-> user skipped: {note}')
                        await asyncio.sleep(self.step_settle_seconds)
                        continue
                    if choice == 'quit':
                        return 'stopped by user'

                status = await self._execute(action, png)
                shot_file = self._persist_step(index, png, action, status)
                self._emit_executed(index, status, screenshot=shot_file)

                self._records.append(StepRecord(
                    index=index, action_kind=action.kind, describe=action.describe,
                    reasoning=action.reasoning, result_status=status, screenshot_file=shot_file,
                ))
                self._history.append(
                    f'{index}. {action.kind}({action.describe or action.summary}) -> {status}')

                if action.kind in (A.STEP_DONE, A.DONE):
                    return status  # 'step_done' or 'done'

                await asyncio.sleep(self.step_settle_seconds)

            return f'reached sub-goal step budget ({max_steps})'
        finally:
            self._subgoal = prev_subgoal
            self.hints = prev_hints


def _label_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """A truetype font at ``size`` for the visual-log banner, else the default.

    Tries a few common bundled fonts (Linux DejaVu, macOS Helvetica) so the
    label is readable on high-res screenshots; falls back to PIL's default
    bitmap font (fixed small size) if none are present.
    """
    for path in (
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        '/System/Library/Fonts/Helvetica.ttc',
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def _json_step(index: int, action: AgentAction, status: str) -> str:
    import json
    return json.dumps({
        'step': index, 'action': action.kind, 'describe': action.describe,
        'reasoning': action.reasoning, 'status': status, 'raw': action.raw,
    }, indent=2)
