"""Record agent actions into a replayable ADARE ``Playbook``.

Each executed agent action is converted into a playbook action and appended
to an in-memory list; :meth:`PlaybookRecorder.finalize` writes it out as
``parse_playbook``-compatible YAML. Per click we build a robust ``image:``
target (a crop of the pre-click screenshot, saved under ``img/``) so the
deterministic CV/OCR replay engine can re-find it with no LLM. The model's
natural-language ``describe`` lands in the action ``description`` and in a
sidecar ``*.meta.json`` used by the self-heal path to re-plan and re-crop.
"""

from __future__ import annotations

import base64
import io
import json
import logging
import re
from pathlib import Path
from typing import Any

import yaml
from PIL import Image

from .exceptions import PlaybookRecordingError

log = logging.getLogger(__name__)

# Default crop box (pixels) captured around a click point for the image target.
_CROP_W = 220
_CROP_H = 90

# Timeout (seconds) for the wait_until gate recorded before every click, so the
# click only fires once its image target is actually present on screen.
_CLICK_WAIT_TIMEOUT = 30.0


def _slugify(text: str, *, max_len: int = 32) -> str:
    slug = re.sub(r'[^a-z0-9]+', '_', (text or '').lower()).strip('_')
    return (slug[:max_len] or 'target')


def crop_around(
    screenshot_png_bytes: bytes,
    x: int,
    y: int,
    *,
    crop_w: int = _CROP_W,
    crop_h: int = _CROP_H,
) -> tuple[Image.Image, list[int]]:
    """Crop a box centred on (x, y), clamped to the image; return (image, box).

    Shared by the recorder (initial capture) and the self-heal path (re-crop
    the same image target in place). Box is ``[left, top, right, bottom]``.
    """
    try:
        img = Image.open(io.BytesIO(screenshot_png_bytes)).convert('RGB')
    except (OSError, ValueError) as exc:
        raise PlaybookRecordingError(f'Could not decode screenshot for crop: {exc}') from exc
    w, h = img.size
    left = max(0, min(w - 1, x - crop_w // 2))
    top = max(0, min(h - 1, y - crop_h // 2))
    right = min(w, left + crop_w)
    bottom = min(h, top + crop_h)
    box = [left, top, right, bottom]
    return img.crop(box), box


def crop_box(
    screenshot_png_bytes: bytes,
    box: tuple[float, float, float, float] | list[float],
) -> tuple[Image.Image, list[int]]:
    """Crop the exact ``[x1, y1, x2, y2]`` box, clamped to the image.

    Used when a grounding backend (e.g. LocateAnything) returns a precise
    element bounding box, so the recorded image target is the tight icon crop
    instead of the fixed :func:`crop_around` box. Returns ``(image, box)`` with
    an integer ``[left, top, right, bottom]`` guaranteed to be non-empty.
    """
    try:
        img = Image.open(io.BytesIO(screenshot_png_bytes)).convert('RGB')
    except (OSError, ValueError) as exc:
        raise PlaybookRecordingError(f'Could not decode screenshot for crop: {exc}') from exc
    w, h = img.size
    x1, y1, x2, y2 = box
    left = max(0, min(w - 1, int(round(x1))))
    top = max(0, min(h - 1, int(round(y1))))
    right = max(left + 1, min(w, int(round(x2))))
    bottom = max(top + 1, min(h, int(round(y2))))
    clamped = [left, top, right, bottom]
    return img.crop(clamped), clamped


class PlaybookRecorder:
    """Accumulates playbook actions and writes YAML + a sidecar + image crops."""

    def __init__(
        self,
        playbook_path: str | Path,
        *,
        settings: dict[str, Any] | None = None,
        goal: str = '',
    ):
        self.playbook_path = Path(playbook_path)
        self.img_dir = self.playbook_path.parent / 'img'
        self.img_dir.mkdir(parents=True, exist_ok=True)
        self.meta_path = self.playbook_path.with_suffix('.meta.json')

        self._settings = settings or {'idle': 2.5, 'timeout': 1800}
        self._goal = goal
        self._actions: list[dict[str, Any]] = []
        self._meta: list[dict[str, Any]] = []
        self._tests: list[dict[str, Any]] = []
        self._variables: dict[str, Any] = {}
        self._step = 0

    # -- rollback (for the planning orchestrator) ---------------------------

    def mark(self) -> tuple[int, int, int, int, dict[str, Any]]:
        """Snapshot the recorder position so a failed sub-goal can be discarded.

        Returns an opaque token — the lengths of the action / meta / test lists,
        the step counter, and a copy of the variables — to hand back to
        :meth:`rollback`. Taken by the planning agent *before* it attempts a
        sub-goal, so a dead end can undo exactly the steps it recorded.
        """
        return (len(self._actions), len(self._meta), len(self._tests),
                self._step, dict(self._variables))

    def rollback(self, mark: tuple[int, int, int, int, dict[str, Any]]) -> None:
        """Discard everything recorded since ``mark`` (from :meth:`mark`).

        Truncates the action / meta / test lists back to their marked lengths
        and restores the step counter and variables. A ``record_click`` appends
        *two* actions/meta (the wait gate + the click), but truncation is by the
        saved length, so partial blocks are removed cleanly. Any crop PNGs
        written under ``img/`` since the mark are left on disk (harmless — only
        filenames referenced by the truncated actions replay).
        """
        actions_len, meta_len, tests_len, step, variables = mark
        del self._actions[actions_len:]
        del self._meta[meta_len:]
        del self._tests[tests_len:]
        self._step = step
        self._variables = dict(variables)

    # -- settings / restart -------------------------------------------------

    def set_vm_memory(self, memory_mb: int) -> None:
        """Persist the working VM RAM (MB) into the playbook ``settings:`` block.

        Written whenever the agent restarts the VM with more memory (or at
        finalize) so future runs/replays boot at this size without rediscovery.
        """
        self._settings['vm_memory'] = int(memory_mb)

    def reset_recorded_actions(self) -> None:
        """Drop all recorded actions/meta/tests/variables after a cold restart.

        A RAM change requires a cold reboot, which invalidates every prior
        screenshot/click, so the fresh attempt re-drives the goal from scratch.
        Settings — including a persisted ``vm_memory`` — are intentionally kept.
        """
        self._actions.clear()
        self._meta.clear()
        self._tests.clear()
        self._variables.clear()
        self._step = 0

    # -- helpers ------------------------------------------------------------

    def _next_index(self) -> int:
        self._step += 1
        return self._step

    def _save_crop(
        self,
        screenshot_png_bytes: bytes,
        x: int,
        y: int,
        slug: str,
        crop_w: int = _CROP_W,
        crop_h: int = _CROP_H,
        bbox: tuple[float, float, float, float] | list[float] | None = None,
    ) -> tuple[str, list[int]]:
        """Crop the click's image target and save it under ``img/``.

        With ``bbox`` (a precise ``[x1, y1, x2, y2]`` from a grounding backend)
        the crop is exactly that box; otherwise it is the fixed box centred on
        (x, y). Returns the bare filename (as referenced by the playbook) and
        the crop bounding box ``[left, top, right, bottom]`` for the sidecar.
        """
        if bbox is not None:
            cropped, box = crop_box(screenshot_png_bytes, bbox)
        else:
            cropped, box = crop_around(screenshot_png_bytes, x, y, crop_w=crop_w, crop_h=crop_h)
        filename = f'step_{self._step:03d}_{slug}.png'
        cropped.save(self.img_dir / filename)
        return filename, box

    # -- recording API ------------------------------------------------------

    def record_click(
        self,
        screenshot_png_bytes: bytes,
        x: int,
        y: int,
        describe: str,
        *,
        button: str = 'left',
        double: bool = False,
        bbox: tuple[float, float, float, float] | list[float] | None = None,
    ) -> None:
        """Record a click as an image-targeted ``ClickAction``.

        When ``bbox`` is supplied (a precise element box from a grounding
        backend such as LocateAnything) the recorded image target is that exact
        crop; otherwise the fixed box centred on (x, y) is used. Either way the
        target replays deterministically through the CV matcher — no model is
        needed at replay time.
        """
        slug = _slugify(describe)
        # The wait gate is its own step and precedes the click, so the click's
        # image filename is numbered against the click step below.
        wait_idx = self._next_index()
        idx = self._next_index()
        filename, box = self._save_crop(screenshot_png_bytes, x, y, slug, bbox=bbox)

        # Gate the click on its target actually being present, removing the
        # "click into the void" race: wait for the same image crop first.
        self._actions.append({
            'wait_until': {
                'condition': {'exists': {'image': filename}},
                'timeout': _CLICK_WAIT_TIMEOUT,
                'description': f'wait for {describe} before click',
            }
        })
        self._meta.append({
            'step': wait_idx, 'kind': 'wait_before_click',
            'image': filename, 'describe': describe,
        })

        click_type = 'double' if double else button
        self._actions.append({
            'click': {
                'target': {'image': filename},
                'type': click_type,
                'description': describe,
            }
        })
        meta: dict[str, Any] = {
            'step': idx, 'kind': 'click', 'image': filename,
            'coords': [x, y], 'crop_box': box, 'describe': describe,
            'click_type': click_type,
        }
        if bbox is not None:
            meta['grounding'] = 'locate_anything'
            meta['element_bbox'] = [float(v) for v in bbox]
        self._meta.append(meta)

    def record_type(self, text: str, describe: str = '') -> None:
        idx = self._next_index()
        self._actions.append({'keyboard': {'text': text, 'description': describe}})
        self._meta.append({'step': idx, 'kind': 'type', 'text': text, 'describe': describe})

    def record_key(self, combo: str, describe: str = '') -> None:
        idx = self._next_index()
        combo = combo.strip()
        if '+' in combo:
            keyboard: dict[str, Any] = {'combination': [k.strip() for k in combo.split('+')]}
        else:
            keyboard = {'key': combo}
        keyboard['description'] = describe
        self._actions.append({'keyboard': keyboard})
        self._meta.append({'step': idx, 'kind': 'key', 'combo': combo, 'describe': describe})

    def record_scroll(self, direction: str, amount: int, describe: str = '') -> None:
        idx = self._next_index()
        self._actions.append({
            'scroll': {'direction': direction, 'amount': int(amount), 'description': describe}
        })
        self._meta.append({'step': idx, 'kind': 'scroll', 'direction': direction,
                           'amount': int(amount), 'describe': describe})

    def record_wait(self, until_describe: str, *, timeout: float = 120.0) -> None:
        """Record a screen transition as a ``WaitUntilAction`` (OCR-text exists)."""
        idx = self._next_index()
        self._actions.append({
            'wait_until': {
                'condition': {'exists': {'text': until_describe}},
                'timeout': timeout,
                'description': f'wait until: {until_describe}',
            }
        })
        self._meta.append({'step': idx, 'kind': 'wait', 'until_describe': until_describe})

    def record_idle(self, duration: float, describe: str = '') -> None:
        idx = self._next_index()
        self._actions.append({'idle': {'duration': float(duration), 'description': describe}})
        self._meta.append({'step': idx, 'kind': 'idle', 'duration': float(duration)})

    def record_test(self, name: str, description: str = '') -> None:
        """Append an ``ActionTestAction`` (``- test:``) that runs a named test here.

        The test must also be defined in the top-level ``tests:`` block (see
        :meth:`add_test`); this only marks the point in the action sequence at
        which it executes.
        """
        idx = self._next_index()
        test_action: dict[str, Any] = {'name': name}
        if description:
            test_action['description'] = description
        self._actions.append({'test': test_action})
        self._meta.append({'step': idx, 'kind': 'test', 'name': name, 'describe': description})

    # -- variables & tests --------------------------------------------------

    def add_variable(self, name: str, value: Any) -> None:
        """Register a playbook ``variables:`` entry for the changing bits."""
        self._variables[name] = value

    def add_test(
        self,
        name: str,
        function: str,
        *,
        parameter: dict[str, Any] | None = None,
        description: str = '',
        expect_to_fail: bool = False,
        timeout: float = 120.0,
        run_here: bool = True,
    ) -> None:
        """Define a test in the top-level ``tests:`` block.

        When ``run_here`` is true (the default) a ``- test:`` action referencing
        it is appended at the current point so the deterministic replay runs it
        in sequence. Validation against the testfunction catalog is the caller's
        responsibility (the MCP server does it before calling this).
        """
        test_def: dict[str, Any] = {'name': name, 'function': function}
        if description:
            test_def['description'] = description
        if parameter:
            test_def['parameter'] = dict(parameter)
        if expect_to_fail:
            test_def['expect_to_fail'] = True
        if timeout != 120.0:
            test_def['timeout'] = timeout
        self._tests.append(test_def)
        if run_here:
            self.record_test(name, description)

    # -- output -------------------------------------------------------------

    @property
    def action_count(self) -> int:
        return len(self._actions)

    def to_yaml(self) -> str:
        """Render the accumulated actions as playbook YAML text."""
        doc: dict[str, Any] = {'settings': self._settings}
        if self._variables:
            doc['variables'] = self._variables
        doc['actions'] = self._actions
        if self._tests:
            doc['tests'] = self._tests
        header = ''
        if self._goal:
            header = f'# Generated by the ADARE GUI agent.\n# Goal: {self._goal}\n'
        return header + yaml.safe_dump(doc, sort_keys=False, default_flow_style=False)

    def finalize(self) -> Path:
        """Write the playbook YAML and the sidecar metadata; return the path."""
        if not self._actions:
            raise PlaybookRecordingError('Refusing to write an empty playbook')
        self.playbook_path.write_text(self.to_yaml())
        self.meta_path.write_text(json.dumps(
            {'goal': self._goal, 'steps': self._meta}, indent=2))
        log.info('Wrote playbook (%d actions) to %s', len(self._actions), self.playbook_path)
        return self.playbook_path
