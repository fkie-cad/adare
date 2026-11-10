"""Automatic effect check of GUI actions: did the screen change where the input went?

A click is "done" once the input is sent, so an absent artifact cannot tell "the app did
not store it" from "the click never took effect". After each click, keyboard, drag, scroll
and goto, :class:`EffectProbe` compares the screen *near the action* before and after it:

* click / goto / drag / scroll: a box around the input point(s)
* keyboard: the box of the last pointer action, else the full screen minus the panel edges

Only that region is compared, so a taskbar clock or an animation elsewhere does not count.
Change is polled for up to ``settle_timeout`` seconds, so a slow redraw is not missed.
The result goes into the action's event data as ``effect: changed | unchanged | unknown``;
for ``unchanged`` a WebP screenshot is kept as evidence. Under ``effect_check: strict`` an
unchanged action fails its step; under ``warn`` (default) it is recorded and makes a later
negative test INCONCLUSIVE; ``off`` disables the check. This is a weak proof (something
happened where the input went), not that the intended thing happened: ``verify:`` and
``controls:`` give stronger ones.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path

from adare.helperfunctions.image import count_changed_pixels, decode_base64_image, encode_webp

log = logging.getLogger(__name__)

EFFECT_MODES = ('off', 'warn', 'strict')
DEFAULT_EFFECT_MODE = 'warn'

#: Seconds to wait for a change before calling the action unchanged (ADARE_EFFECT_TIMEOUT overrides)
DEFAULT_SETTLE_TIMEOUT = 1.0
POLL_INTERVAL = 0.2
#: Changed pixels in the region needed to count as a change (above caret-blink/noise size)
MIN_CHANGED_PIXELS = 40
#: Box around an input point, as a fraction of the screen, and its minimum size in pixels
BOX_FRACTION = 0.25
MIN_BOX = (240, 160)
#: Screen edges left out of a full-screen keyboard check (panels, taskbar clock)
EDGE_FRACTION = 0.06
MIN_EDGE = 32

Region = tuple[int, int, int, int]  # x, y, w, h


def _clamp_box(cx: int, cy: int, width: int, height: int, screen_w: int, screen_h: int) -> Region:
    w, h = min(width, screen_w), min(height, screen_h)
    x = min(max(0, cx - w // 2), screen_w - w)
    y = min(max(0, cy - h // 2), screen_h - h)
    return x, y, w, h


def box_around(points: list[tuple[int, int]], screen_w: int, screen_h: int) -> Region:
    """The comparison box around one or more input points (a drag has two)."""
    bw = max(MIN_BOX[0], int(screen_w * BOX_FRACTION))
    bh = max(MIN_BOX[1], int(screen_h * BOX_FRACTION))
    boxes = [_clamp_box(int(px), int(py), bw, bh, screen_w, screen_h) for px, py in points]
    x0 = min(b[0] for b in boxes)
    y0 = min(b[1] for b in boxes)
    x1 = max(b[0] + b[2] for b in boxes)
    y1 = max(b[1] + b[3] for b in boxes)
    return x0, y0, x1 - x0, y1 - y0


def screen_without_edges(screen_w: int, screen_h: int) -> Region:
    """Full screen minus a band at each edge, where panels and the clock live."""
    ex = max(MIN_EDGE, int(screen_w * EDGE_FRACTION))
    ey = max(MIN_EDGE, int(screen_h * EDGE_FRACTION))
    if screen_w <= 2 * ex or screen_h <= 2 * ey:
        return 0, 0, screen_w, screen_h
    return ex, ey, screen_w - 2 * ex, screen_h - 2 * ey


def resolve_effect_mode(settings) -> str:
    """``settings.effect_check`` (off | warn | strict), defaulting to warn."""
    mode = getattr(settings, 'effect_check', None) or DEFAULT_EFFECT_MODE
    return mode if mode in EFFECT_MODES else DEFAULT_EFFECT_MODE


def _settle_timeout() -> float:
    try:
        return max(0.0, float(os.environ.get('ADARE_EFFECT_TIMEOUT', DEFAULT_SETTLE_TIMEOUT)))
    except ValueError:
        return DEFAULT_SETTLE_TIMEOUT


class EffectProbe:
    """Before/after screen comparison around one GUI action at a time.

    Call :meth:`begin_action` when an action starts, :meth:`arm` right before its input is
    sent (with the input point(s)), and :meth:`settle` after it. The frame target resolution
    just ran on is reused as the "before" frame when there is one, so a click on an
    image/text target costs one extra screenshot per poll and no OCR.
    """

    def __init__(self, target_resolution, mode: str = DEFAULT_EFFECT_MODE, settle_timeout: float | None = None):
        self.target_resolution = target_resolution
        self.mode = mode if mode in EFFECT_MODES else DEFAULT_EFFECT_MODE
        self.settle_timeout = _settle_timeout() if settle_timeout is None else settle_timeout
        self._before = None
        self._region: Region | None = None
        self._last_pointer_box: Region | None = None
        self._evidence_counter = 0

    @property
    def enabled(self) -> bool:
        return self.mode != 'off'

    def begin_action(self) -> None:
        """Forget the previous action's frames (and the resolution frame it ran on)."""
        self._before = None
        self._region = None
        self.target_resolution.resolution_frame = None

    async def arm(self, points: list[tuple[int, int]] | None = None) -> None:
        """Take the "before" frame and fix the region; ``points`` = where the input goes."""
        if not self.enabled:
            return
        frame = getattr(self.target_resolution, 'resolution_frame', None) or await self._capture()
        if not frame:
            log.warning("Effect check: no 'before' screenshot, the action's effect is unknown")
            return
        try:
            before = decode_base64_image(frame)
        except (ValueError, ImportError) as e:
            log.warning(f"Effect check: cannot decode the 'before' screenshot: {e}")
            return
        screen_h, screen_w = before.shape[:2]
        if points:
            region = box_around(points, screen_w, screen_h)
            self._last_pointer_box = box_around(points[-1:], screen_w, screen_h)
        elif self._last_pointer_box is not None:
            region = self._last_pointer_box
        else:
            region = screen_without_edges(screen_w, screen_h)
        self._before, self._region = before, region

    async def settle(self, label: str = 'action') -> dict:
        """Poll for a change in the region; return the event data for the action.

        Returns ``{'effect': ..., 'effect_info': {...}}``; ``{}`` when the check is off.
        """
        if not self.enabled:
            return {}
        if self._before is None or self._region is None:
            return {'effect': 'unknown', 'effect_info': {'reason': 'no before screenshot'}}
        started = time.monotonic()
        deadline = started + self.settle_timeout
        changed, after, polls = 0, None, 0
        while True:
            polls += 1
            frame = await self._capture()
            if frame:
                try:
                    after = decode_base64_image(frame)
                    changed = count_changed_pixels(self._before, after, self._region)
                except (ValueError, ImportError) as e:
                    log.warning(f"Effect check: cannot compare screenshots: {e}")
                    after = None
                if changed >= MIN_CHANGED_PIXELS:
                    break
            if time.monotonic() >= deadline:
                break
            await asyncio.sleep(min(POLL_INTERVAL, max(0.0, deadline - time.monotonic())))
        info = {
            'region': list(self._region),
            'changed_pixels': changed,
            'threshold': MIN_CHANGED_PIXELS,
            'polls': polls,
            'waited_s': round(time.monotonic() - started, 3),
        }
        if after is None:
            return {'effect': 'unknown', 'effect_info': {**info, 'reason': 'no after screenshot'}}
        if changed >= MIN_CHANGED_PIXELS:
            return {'effect': 'changed', 'effect_info': info}
        evidence = self._save_evidence(after, label)
        if evidence:
            info['evidence'] = evidence
        log.warning(
            f"Effect check: no screen change near {label} within {self.settle_timeout}s "
            f"({changed} px changed in region {self._region})"
        )
        return {'effect': 'unchanged', 'effect_info': info}

    async def _capture(self) -> str | None:
        capture = getattr(self.target_resolution, 'capture_frame', None)
        return await capture() if capture is not None else None

    def _save_evidence(self, image, label: str) -> str | None:
        """Keep the unchanged screen as WebP; returns its path relative to the run directory."""
        screenshots_dir: Path | None = getattr(self.target_resolution, 'screenshots_dir', None)
        if not screenshots_dir:
            return None
        from .simple_actions import sanitize_filename

        self._evidence_counter += 1
        name = f"effect_unchanged_{self._evidence_counter:03d}_{sanitize_filename(label)[:40]}.webp"
        try:
            screenshots_dir.mkdir(parents=True, exist_ok=True)
            (screenshots_dir / name).write_bytes(encode_webp(image))
        except (OSError, ValueError) as e:
            log.warning(f"Effect check: could not save evidence screenshot: {e}")
            return None
        return f"reporting/screenshots/{name}"
