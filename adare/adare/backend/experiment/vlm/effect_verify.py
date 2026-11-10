"""Derive a ``verify:`` image from the screens before and after a recorded step.

The recorder already sees the screen before each step; given the screen after it (and a
second "confirm" frame a moment later), :func:`derive_effect_crop` finds the region that
changed, checks that it has settled, and returns a crop of it. The recorder emits that
crop as ``verify: {exists: {image: ...}}`` on the step, so a replay proves the step
produced the screen state it produced while recording — with no authoring.

Skipped (no verify) when nothing changed, the change is tiny (caret, noise), lies only at
the screen edges (panels, the taskbar clock), or is still changing (a progress bar,
a ticking counter) between the after and confirm frames.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

log = logging.getLogger(__name__)

#: Grey-level difference that counts a pixel as changed
_NOISE = 25
#: Smallest change (pixels) and box side worth verifying
_MIN_CHANGED = 120
_MIN_SIDE = 16
#: Largest crop kept as a template (pixels); a bigger change is cropped around its centre
_MAX_W, _MAX_H = 480, 320
#: Share of the crop that may still change between after and confirm frames
_MAX_UNSETTLED = 0.01


@dataclass
class EffectCrop:
    png: bytes  # the crop, PNG-encoded
    box: list[int]  # [left, top, right, bottom] in screen pixels
    changed_pixels: int


def _decode(png: bytes):
    import cv2
    import numpy as np

    image = cv2.imdecode(np.frombuffer(png, dtype=np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError('cannot decode screenshot')
    return image


def derive_effect_crop(before_png: bytes, after_png: bytes, confirm_png: bytes | None = None):
    """Return ``(EffectCrop, None)`` or ``(None, reason)`` for why no verify is derived."""
    import cv2
    import numpy as np

    from adare.backend.experiment.execution.effect_check import screen_without_edges
    from adare.helperfunctions.image import count_changed_pixels

    try:
        before, after = _decode(before_png), _decode(after_png)
        confirm = _decode(confirm_png) if confirm_png else None
    except ValueError as e:
        return None, str(e)
    if before.shape != after.shape:
        return None, 'screen size changed'
    height, width = before.shape[:2]
    mask = (cv2.cvtColor(cv2.absdiff(before, after), cv2.COLOR_BGR2GRAY) > _NOISE).astype(np.uint8)
    ex, ey, ew, eh = screen_without_edges(width, height)
    inner = np.zeros_like(mask)
    inner[ey : ey + eh, ex : ex + ew] = 1
    mask &= inner
    if int(mask.sum()) < _MIN_CHANGED:
        return None, 'no screen change away from the edges'
    # Merge glyphs/neighbouring widgets into one region, then keep the biggest region
    merged = cv2.dilate(mask, np.ones((9, 9), np.uint8))
    count, _labels, stats, centroids = cv2.connectedComponentsWithStats(merged)
    best = max(range(1, count), key=lambda i: stats[i, cv2.CC_STAT_AREA])
    x, y, w, h = (int(v) for v in stats[best, :4])
    changed = int(mask[y : y + h, x : x + w].sum())
    if changed < _MIN_CHANGED or w < _MIN_SIDE or h < _MIN_SIDE:
        return None, 'change too small to verify'
    if w > _MAX_W or h > _MAX_H:
        cx, cy = (int(v) for v in centroids[best])
        nw, nh = min(w, _MAX_W), min(h, _MAX_H)
        x = min(max(x, cx - nw // 2), x + w - nw)
        y = min(max(y, cy - nh // 2), y + h - nh)
        w, h = nw, nh
    settled = confirm if confirm is not None and confirm.shape == after.shape else after
    if confirm is not None and count_changed_pixels(after, settled, (x, y, w, h)) > _MAX_UNSETTLED * w * h:
        return None, 'changed region is still changing'
    ok, buf = cv2.imencode('.png', settled[y : y + h, x : x + w])
    if not ok:
        return None, 'cannot encode crop'
    return EffectCrop(png=buf.tobytes(), box=[x, y, x + w, y + h], changed_pixels=changed), None
