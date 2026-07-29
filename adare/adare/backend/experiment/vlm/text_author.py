"""Author a replayable playbook from human text steps — no VLM planner.

Where :class:`GuiAgent` lets a vision model decide *what* and *where*, this
driver lets a **human** supply the "what" as text and uses the LocateAnything
grounding backend to resolve the "where" — the same describe->element->click
path the agent uses under ``ADARE_LOCATE_CLICK``, but with the person as the
planner. Each step is executed against a live VM and recorded via the shared
:class:`PlaybookRecorder`, so the result replays deterministically through the
CV/OCR engine exactly like an agent-recorded playbook.

Two modes:

* **script** — a text block, one action per line, run top to bottom.
* **interactive** — a REPL: type one step, see the grounded target drawn on the
  screenshot (the visual log), approve / re-ground / place it by hand, repeat.

Line grammar (one action per line; ``#`` comments and blank lines ignored)::

    click        the Bold button
    click        @542,130 the Bold button   # explicit pixel target, no grounding
    double_click the document icon
    right_click  the selected word
    type         ADARE FORENSIC REPORT
    key          ctrl+a
    scroll       down 3
    wait         the Insert Table dialog is visible
    note         (an observation; not recorded)
    done         heading formatted

Clicks with no ``@x,y`` need a grounding backend; on a miss the interactive
mode prompts to rephrase or place the click by hand, and script mode records a
skip so authoring never silently clicks the wrong thing.
"""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import re
from typing import Any

from PIL import Image, ImageDraw

from . import actions as A
from .actions import AgentAction
from .agent import AgentRunResult, GuiAgent, StepRecord, _label_font

log = logging.getLogger(__name__)


# Verbs the author may use -> the canonical action kind.
_VERBS = {
    'click': A.CLICK,
    'double_click': A.DOUBLE_CLICK, 'doubleclick': A.DOUBLE_CLICK,
    'right_click': A.CLICK, 'rightclick': A.CLICK,  # button set to 'right' below
    'type': A.TYPE,
    'key': A.KEY, 'press': A.KEY,
    'scroll': A.SCROLL,
    'wait': A.WAIT,
    'note': A.NOTE,
    'done': A.DONE,
}
_CLICK_VERBS = {'click', 'double_click', 'doubleclick', 'right_click', 'rightclick'}
_COORD_RE = re.compile(r'^@\s*(\d+)\s*,\s*(\d+)\s*(.*)$', re.DOTALL)


class AuthoringError(ValueError):
    """A text step could not be parsed into an action."""


def _strip_quotes(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'"):
        return text[1:-1]
    return text


def parse_authored_line(line: str) -> AgentAction | None:
    """Parse one authoring line into an :class:`AgentAction` (or ``None``).

    Returns ``None`` for blank lines and ``#`` comments. Raises
    :class:`AuthoringError` for an unknown verb or a malformed argument so the
    caller can report the offending line rather than silently drop it.
    """
    raw = line.strip()
    if not raw or raw.startswith('#'):
        return None

    parts = raw.split(None, 1)
    verb = parts[0].lower()
    rest = parts[1].strip() if len(parts) > 1 else ''
    kind = _VERBS.get(verb)
    if kind is None:
        raise AuthoringError(f'unknown action {verb!r} (line: {line.strip()!r})')

    action = AgentAction(kind=kind)

    if verb in _CLICK_VERBS:
        if verb in ('right_click', 'rightclick'):
            action.button = 'right'
        m = _COORD_RE.match(rest)
        if m:
            action.x, action.y = int(m.group(1)), int(m.group(2))
            action.describe = _strip_quotes(m.group(3)) or f'{verb} at ({action.x},{action.y})'
        else:
            desc = _strip_quotes(rest)
            if not desc:
                raise AuthoringError(f'{verb} needs a description or @x,y (line: {line.strip()!r})')
            action.describe = desc
    elif kind == A.TYPE:
        action.text = _strip_quotes(rest)
        action.describe = f'type {action.text!r}'
    elif kind == A.KEY:
        combo = _strip_quotes(rest)
        if not combo:
            raise AuthoringError(f'key needs a combo, e.g. "key enter" (line: {line.strip()!r})')
        action.combo = combo
        action.describe = f'press {combo}'
    elif kind == A.SCROLL:
        toks = rest.split()
        action.direction = (toks[0].lower() if toks else 'down')
        action.amount = int(toks[1]) if len(toks) > 1 and toks[1].isdigit() else 3
        action.describe = f'scroll {action.direction} {action.amount}'
    elif kind == A.WAIT:
        action.until_describe = _strip_quotes(rest) or None
        action.describe = f'wait: {action.until_describe or ""}'
    elif kind == A.NOTE:
        action.describe = _strip_quotes(rest)
    elif kind == A.DONE:
        action.summary = _strip_quotes(rest)

    return action


class TextAuthorDriver:
    """Executes human-authored text steps against a VM, recording a playbook.

    Composes a :class:`GuiAgent` (with ``client=None`` — the model is never
    consulted) purely to reuse its capture / execute / record / persist and the
    visual-log rendering, so an authored playbook is byte-for-byte the same
    shape as an agent-recorded one.
    """

    def __init__(
        self,
        gui_executor: Any,
        *,
        recorder: Any = None,
        run_dir: Any = None,
        locate_client: Any = None,
        coord_space: str = 'absolute',
        locate_crop_margin: int = 16,
        locate_crop_min: int = 72,
        step_settle_seconds: float = 1.5,
        goal: str = 'Authored from text',
    ):
        self.locate_client = locate_client
        self.step_settle_seconds = step_settle_seconds
        # The inner agent owns capture/execute/record/persist + the visual log.
        # locate_click is irrelevant here (we ground explicitly), client is
        # never used because we never call _decide.
        self.agent = GuiAgent(
            gui_executor, client=None, goal=goal,
            recorder=recorder, run_dir=run_dir, coord_space=coord_space,
            locate_client=locate_client, locate_click=True,
            locate_crop_margin=locate_crop_margin, locate_crop_min=locate_crop_min,
            step_settle_seconds=step_settle_seconds,
        )

    # -- grounding ----------------------------------------------------------

    def _detections(self, png: bytes, describe: str) -> list[Any]:
        """All LocateAnything detections for ``describe`` (never raises)."""
        if not self.locate_client:
            return []
        try:
            b64 = base64.b64encode(png).decode('ascii')
            return list(self.locate_client.locate(b64, describe))
        except (RuntimeError, OSError, ValueError, TypeError, KeyError, IndexError) as exc:
            log.warning('LocateAnything failed for %r (%s)', describe, exc)
            return []

    def _apply_detection(self, action: AgentAction, det: Any, width: int, height: int) -> None:
        """Set the click coordinate + recorded crop from a chosen detection."""
        cx, cy = det.center
        action.x = max(0, min(width - 1, round(cx)))
        action.y = max(0, min(height - 1, round(cy)))
        action.crop_bbox = self.agent._pad_box(det.box)

    def _draw_candidates(self, png: bytes, dets: list[Any], index: int) -> str | None:
        """Save the screenshot with every candidate box numbered; return path.

        Lets the human disambiguate visually in interactive mode. Returns the
        saved file path, or ``None`` if no steps dir is configured / on error.
        """
        steps_dir = self.agent._steps_dir
        if not steps_dir:
            return None
        try:
            with Image.open(io.BytesIO(png)) as im:
                img = im.convert('RGB')
            draw = ImageDraw.Draw(img)
            font = _label_font(max(14, round(img.width / 90)))
            for i, d in enumerate(dets, 1):
                x1, y1, x2, y2 = (round(v) for v in d.box)
                draw.rectangle([x1, y1, x2, y2], outline=(0, 160, 255), width=3)
                tag = f'[{i}]'
                tb = draw.textbbox((0, 0), tag, font=font)
                draw.rectangle([x1, max(0, y1 - (tb[3] - tb[1]) - 8), x1 + (tb[2] - tb[0]) + 8, y1],
                               fill=(0, 160, 255))
                draw.text((x1 + 3, max(0, y1 - (tb[3] - tb[1]) - 6)), tag, fill=(0, 0, 0), font=font)
            path = steps_dir / f'candidates_{index:03d}.png'
            img.save(path)
            return str(path)
        except (OSError, ValueError) as exc:
            log.warning('Could not render candidate overlay (%s)', exc)
            return None

    # -- one step -----------------------------------------------------------

    async def _ground_for_author(
        self, action: AgentAction, png: bytes, b64_width: int, height: int, index: int,
        *, interactive: bool,
    ) -> bool:
        """Resolve a click's coordinate from its description. Returns True if the
        click is ready to execute, False to skip it.

        Explicit ``@x,y`` clicks are already ready. Otherwise ground via
        LocateAnything: one hit -> use it; several -> pick smallest (script) or
        ask (interactive); none -> skip (script) or prompt to rephrase / place
        by hand (interactive).
        """
        width = b64_width
        if action.x is not None:  # explicit @x,y — nothing to ground
            return True
        if not self.locate_client:
            log.error('Click %r needs @x,y or a grounding backend (ADARE_LOCATE_URL)', action.describe)
            return False

        while True:
            dets = self._detections(png, action.describe)
            if len(dets) == 1:
                self._apply_detection(action, dets[0], width, height)
                return True
            if len(dets) > 1 and not interactive:
                best = min(dets, key=lambda d: (d.box[2] - d.box[0]) * (d.box[3] - d.box[1]))
                log.warning('%d matches for %r; picking smallest box', len(dets), action.describe)
                self._apply_detection(action, best, width, height)
                return True
            if len(dets) >= 1 and interactive:
                overlay = self._draw_candidates(png, dets, index)
                print(f'  {len(dets)} matches for "{action.describe}":')
                for i, d in enumerate(dets, 1):
                    cx, cy = round(d.center[0]), round(d.center[1])
                    print(f'    [{i}] {d.label!r} centre ({cx},{cy}) box {[round(v) for v in d.box]}')
                if overlay:
                    print(f'  (candidates drawn: {overlay})')
                choice = (await asyncio.to_thread(
                    input, '  pick number / [r]e-ground / xy X,Y / [s]kip > ')).strip().lower()
                if choice in ('s', 'skip'):
                    return False
                if choice in ('r', 're', ''):
                    continue
                mxy = re.match(r'^xy\s+(\d+)\s*,\s*(\d+)$', choice)
                if mxy:
                    action.x, action.y = int(mxy.group(1)), int(mxy.group(2))
                    return True
                if choice.isdigit() and 1 <= int(choice) <= len(dets):
                    self._apply_detection(action, dets[int(choice) - 1], width, height)
                    return True
                print('  (did not understand; try again)')
                continue
            # No detections.
            if not interactive:
                log.warning('No match for %r; skipping (author with @x,y to force)', action.describe)
                return False
            print(f'  No match for "{action.describe}".')
            choice = (await asyncio.to_thread(
                input, '  [r]etype a new description / xy X,Y / [s]kip > ')).strip()
            low = choice.lower()
            if low in ('s', 'skip'):
                return False
            mxy = re.match(r'^xy\s+(\d+)\s*,\s*(\d+)$', low)
            if mxy:
                action.x, action.y = int(mxy.group(1)), int(mxy.group(2))
                return True
            if choice:
                action.describe = _strip_quotes(choice)
            continue

    async def _confirm(self, action: AgentAction, index: int) -> str:
        """Interactive per-step gate after grounding. Returns approve/skip/quit."""
        where = f' @ ({action.x},{action.y})' if action.x is not None else ''
        print(f'  step {index}: {action.kind}{where}  "{action.describe}"')
        choice = (await asyncio.to_thread(
            input, '  [a]pprove / [s]kip / [q]uit > ')).strip().lower()
        if choice in ('', 'a', 'approve'):
            return 'approve'
        if choice in ('s', 'skip'):
            return 'skip'
        if choice in ('q', 'quit'):
            return 'quit'
        return 'approve'

    async def _run_action(self, action: AgentAction, *, interactive: bool) -> str:
        """Ground (clicks), optionally confirm, execute + record + visual-log."""
        ag = self.agent
        b64, png, width, height = await ag._capture()
        index = len(ag._records) + 1

        if action.kind in (A.CLICK, A.DOUBLE_CLICK):
            ready = await self._ground_for_author(action, png, width, height, index,
                                                   interactive=interactive)
            if not ready:
                ag._records.append(StepRecord(
                    index=index, action_kind=action.kind, describe=action.describe,
                    reasoning='authored', result_status='skipped'))
                return 'skipped'

        if interactive:
            decision = await self._confirm(action, index)
            if decision == 'skip':
                ag._records.append(StepRecord(
                    index=index, action_kind=action.kind, describe=action.describe,
                    reasoning='authored', result_status='skipped'))
                return 'skipped'
            if decision == 'quit':
                return 'quit'

        status = await ag._execute(action, png)
        ag._persist_step(index, png, action, status)
        ag._records.append(StepRecord(
            index=index, action_kind=action.kind, describe=action.describe,
            reasoning='authored', result_status=status))
        await asyncio.sleep(self.step_settle_seconds)
        return status

    # -- public entry points ------------------------------------------------

    async def run_script(self, script: str) -> AgentRunResult:
        """Execute a whole text script top to bottom, then finalize."""
        for lineno, line in enumerate(script.splitlines(), 1):
            try:
                action = parse_authored_line(line)
            except AuthoringError as exc:
                log.error('Line %d: %s', lineno, exc)
                return self.agent._finish(False, f'parse error on line {lineno}: {exc}')
            if action is None:
                continue
            if action.kind == A.DONE:
                return self.agent._finish(True, 'authored (done)', summary=action.summary)
            if action.kind == A.NOTE:
                log.info('note: %s', action.describe)
                continue
            status = await self._run_action(action, interactive=False)
            if status == 'quit':
                return self.agent._finish(False, 'stopped')
        return self.agent._finish(True, 'authored (end of script)')

    async def run_interactive(self) -> AgentRunResult:
        """REPL: read one step at a time, ground+preview+confirm, record."""
        print('Text playbook authoring. One action per line. '
              ':help for commands, :done to finish, :quit to abort.')
        while True:
            line = await asyncio.to_thread(input, 'step> ')
            cmd = line.strip().lower()
            if cmd in (':q', ':quit', ':abort'):
                return self.agent._finish(False, 'aborted by user')
            if cmd in (':done', ':finish', ':d'):
                return self.agent._finish(True, 'authored (done)')
            if cmd in (':help', ':h', '?'):
                print('  verbs: click | double_click | right_click | type | key | '
                      'scroll | wait | note | done')
                print('  clicks: `click the Save button`  or  `click @542,130 Save`')
                print('  commands: :done  :quit  :help')
                continue
            try:
                action = parse_authored_line(line)
            except AuthoringError as exc:
                print(f'  ! {exc}')
                continue
            if action is None:
                continue
            if action.kind == A.DONE:
                return self.agent._finish(True, 'authored (done)', summary=action.summary)
            if action.kind == A.NOTE:
                print(f'  (note) {action.describe}')
                continue
            status = await self._run_action(action, interactive=True)
            if status == 'quit':
                return self.agent._finish(False, 'aborted by user')
            print(f'  -> {status}')
