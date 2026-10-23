"""Tell a guest that has no agent apart from one that is still booting.

From the host both look identical: the guest-agent virtio port is open on the
QEMU side and nobody answers in the guest. Waiting longer cannot separate them,
and a cold-boot retry cannot install a missing ``qemu-guest-agent``, so an image
built without one used to cost every boot attempt (180s + 360s + 600s on Linux)
before failing with a bare timeout.

The screen can separate them. A booting guest keeps repainting; one that has
finished booting sits on its login screen or desktop. :class:`BootScreenWatch`
samples the framebuffer over QMP (which needs no guest agent) during a boot
attempt and reports how long the picture has been still. A clock ticking on a
greeter changes far less than the tolerance, a blank (uniform) frame never counts
as settled, so a blanked display or an early black boot screen does not either.
"""

from __future__ import annotations

import asyncio
import contextlib
import io
import logging
import tempfile
import time
from pathlib import Path

log = logging.getLogger(__name__)

# Frames are compared as small grayscale thumbnails: cheap, and blind to the
# sub-pixel noise of a cursor or a minute tick on a clock.
_THUMB_SIZE = (160, 120)
# A pixel counts as changed past this gray-level difference...
_PIXEL_DELTA = 24
# ...and a frame as changed when more than this share of its pixels did.
_CHANGED_SHARE = 0.01


class BootScreenWatch:
    """Samples a booting guest's screen and measures how long it has been still."""

    POLL_S = 5.0

    def __init__(self, vm):
        self.vm = vm
        self._shot_dir = Path(tempfile.gettempdir()) / 'adare_qmp_screenshots'
        self._shot_dir.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            # QEMU may run as another user and has to write the screendump here.
            self._shot_dir.chmod(0o777)
        self._ppm = self._shot_dir / f'boot_watch_{id(self)}.ppm'
        self._last_png: bytes | None = None
        self._last_thumb = None
        self._settled_since: float | None = None

    def settled_for(self) -> float:
        """Seconds the screen has shown the same non-blank picture (0 if not)."""
        return time.monotonic() - self._settled_since if self._settled_since is not None else 0.0

    def save_last(self, path: Path) -> Path | None:
        """Write the latest frame as PNG to ``path``; None when there is none."""
        if self._last_png is None:
            return None
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(self._last_png)
        except OSError as e:
            log.warning(f'Could not save the boot screenshot to {path}: {e}')
            return None
        return path

    async def run(self) -> None:
        """Sample until cancelled."""
        try:
            while True:
                await self.sample()
                await asyncio.sleep(self.POLL_S)
        finally:
            with contextlib.suppress(OSError):
                self._ppm.unlink(missing_ok=True)

    async def sample(self) -> None:
        try:
            ok, error = await self.vm.send_qmp_screenshot(str(self._ppm))
        except (OSError, RuntimeError, ConnectionError, TimeoutError) as e:
            ok, error = False, str(e)
        if not ok:
            log.debug(f'Boot screen sample failed: {error}')
            return
        try:
            self.observe(self._ppm.read_bytes())
        except (OSError, ValueError) as e:
            # PIL.UnidentifiedImageError is an OSError.
            log.debug(f'Boot screen sample unreadable: {e}')

    def observe(self, frame: bytes) -> None:
        """Account one captured frame (any format PIL reads)."""
        from PIL import Image, ImageChops

        image = Image.open(io.BytesIO(frame))
        thumb = image.convert('L').resize(_THUMB_SIZE)
        png = io.BytesIO()
        image.save(png, 'PNG')
        self._last_png = png.getvalue()

        lo, hi = thumb.getextrema()
        if lo == hi:
            self._settled_since = None
        elif self._settled_since is None or self._changed(self._last_thumb, thumb, ImageChops):
            self._settled_since = time.monotonic()
        self._last_thumb = thumb

    @staticmethod
    def _changed(previous, current, image_chops) -> bool:
        diff = image_chops.difference(previous, current)
        changed: int = diff.point(lambda v: 255 if v > _PIXEL_DELTA else 0).histogram()[255]
        return changed > _CHANGED_SHARE * _THUMB_SIZE[0] * _THUMB_SIZE[1]
