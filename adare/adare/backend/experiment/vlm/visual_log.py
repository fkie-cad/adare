"""Visual log: draw what a click found and where it landed onto the step screenshot."""

from __future__ import annotations

import io
import logging

from PIL import Image, ImageDraw, ImageFont

from . import actions as A
from .actions import AgentAction

log = logging.getLogger(__name__)


def annotate_click_png(png: bytes, action: AgentAction, index: int) -> bytes:
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
        green, red, orange, black = ((0, 210, 0), (255, 40, 40), (255, 150, 0), (0, 0, 0))

        if action.crop_bbox:
            x1, y1, x2, y2 = (round(v) for v in action.crop_bbox)
            draw.rectangle([x1, y1, x2, y2], outline=green, width=3)

        # From the model's original point (if grounding moved it) to the click.
        if action.vlm_point and action.vlm_point != (action.x, action.y):
            ox, oy = action.vlm_point
            draw.line([ox, oy, action.x, action.y], fill=orange, width=2)
            _mark(draw, ox, oy, orange, r=7)

        cx, cy = action.x, action.y
        draw.line([cx - 11, cy, cx + 11, cy], fill=red, width=3)
        draw.line([cx, cy - 11, cx, cy + 11], fill=red, width=3)
        draw.ellipse([cx - 5, cy - 5, cx + 5, cy + 5], outline=red, width=2)

        label = f'#{index} {action.kind} ({cx},{cy})'
        if action.vlm_point and action.vlm_point != (cx, cy):
            label += f'  [grounded from {action.vlm_point}]'
        if action.describe:
            label += f'  {action.describe[:70]}'
        font = label_font(max(13, round(img.width / 110)))
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


def _mark(draw: ImageDraw.ImageDraw, x: int, y: int, color: tuple, *, r: int) -> None:
    draw.ellipse([x - r, y - r, x + r, y + r], outline=color, width=2)


def label_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
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
