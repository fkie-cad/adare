"""Record a whole GUI-agent run to an MP4 by piping QMP screendumps to ffmpeg.

The QEMU VM already exposes an always-on QMP ``screendump`` (PPM) via
:meth:`~adare.hypervisor.qemu.vm.QEMUVM.send_qmp_screenshot`. This recorder polls
it on a fixed cadence and streams each PPM frame into an ``ffmpeg`` process
reading ``image2pipe``, producing an ``.mp4`` of the session.

It mirrors the spawn / attach / teardown shape of the grounding
:class:`~adare.backend.experiment.grounding.locate_process_manager.LocateGroundingManager`:
:meth:`start` brings the pipeline up (and raises :class:`VideoUnavailable` if the
``ffmpeg`` binary is missing), :meth:`stop` cancels the poller, closes ffmpeg's
stdin and waits for it to finalize the file — so an interrupted run still yields
a valid (truncated) clip.

QMP contention is a non-issue: :meth:`send_qmp_screenshot` runs on the same
asyncio loop as the agent's per-step ``executor.screenshot()`` and the underlying
QMP call has no ``await`` points, so the loop serializes the two callers; a low
default fps (config ``AGENT_VIDEO_FPS``) keeps the recorder from starving
perception.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import shutil
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class VideoUnavailable(RuntimeError):
    """Video recording was requested but cannot run (e.g. ffmpeg is missing)."""


class QemuVideoRecorder:
    """Streams QMP screendumps into ffmpeg to record a session as MP4."""

    def __init__(
        self,
        vm: Any,
        out_path: str | Path,
        *,
        fps: int = 2,
        ffmpeg: str = 'ffmpeg',
    ):
        self.vm = vm
        self.out_path = Path(out_path)
        self.fps = max(1, int(fps))
        self.ffmpeg = ffmpeg
        # One reused temp PPM path (frames are serialized, so no per-frame file).
        self._frame_path = self.out_path.parent / f'.{self.out_path.stem}.frame.ppm'
        self._proc: asyncio.subprocess.Process | None = None
        self._poller: asyncio.Task | None = None
        self._frames = 0
        self._stopping = False

    # -- preflight ----------------------------------------------------------

    @staticmethod
    def ensure_ffmpeg(ffmpeg: str = 'ffmpeg') -> str:
        """Resolve the ffmpeg binary or raise :class:`VideoUnavailable`.

        A cheap ``shutil.which`` probe callers can run up front (before spinning
        up grounding / VM work) so a missing-ffmpeg ``--video`` run fails fast.
        Returns the resolved absolute path.
        """
        exe = shutil.which(ffmpeg)
        if not exe:
            raise VideoUnavailable(
                f'ffmpeg not found (looked for {ffmpeg!r}). Install ffmpeg '
                'or set ADARE_FFMPEG to its path, or drop --video.'
            )
        return exe

    # -- lifecycle ----------------------------------------------------------

    async def start(self) -> None:
        """Spawn ffmpeg and begin polling frames. Raise if ffmpeg is missing."""
        exe = self.ensure_ffmpeg(self.ffmpeg)
        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            exe, '-y', '-loglevel', 'error',
            '-f', 'image2pipe', '-vcodec', 'ppm',
            '-framerate', str(self.fps),
            '-i', '-',
            # yuv420p needs even dimensions; pad odd screens up by one pixel.
            '-vf', 'pad=ceil(iw/2)*2:ceil(ih/2)*2',
            '-pix_fmt', 'yuv420p',
            '-an', str(self.out_path),
        ]
        try:
            self._proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except OSError as exc:
            raise VideoUnavailable(f'could not launch ffmpeg ({exe}): {exc}') from exc
        log.info('Recording run video to %s (%d fps via %s)', self.out_path, self.fps, exe)
        self._poller = asyncio.create_task(self._poll_loop())

    async def stop(self) -> Path | None:
        """Stop polling, finalize the MP4, and return its path (or None if empty)."""
        if self._stopping:
            return self.out_path if self._frames else None
        self._stopping = True

        if self._poller is not None:
            self._poller.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._poller
            self._poller = None

        if self._proc is not None:
            proc = self._proc
            self._proc = None
            try:
                if proc.stdin is not None and not proc.stdin.is_closing():
                    proc.stdin.close()
            except OSError as exc:
                log.debug('closing ffmpeg stdin failed: %s', exc)
            try:
                await asyncio.wait_for(proc.wait(), timeout=15)
            except TimeoutError:
                log.warning('ffmpeg did not exit in time; killing')
                proc.kill()
                await proc.wait()

        with contextlib.suppress(OSError):
            self._frame_path.unlink()

        if not self._frames:
            log.warning('Video recorder captured no frames; %s may be empty', self.out_path)
            return None
        log.info('Wrote run video (%d frames) to %s', self._frames, self.out_path)
        return self.out_path

    # -- polling ------------------------------------------------------------

    async def _poll_loop(self) -> None:
        loop = asyncio.get_running_loop()
        interval = 1.0 / self.fps
        while True:
            t0 = loop.time()
            try:
                await self._grab_frame()
            except (BrokenPipeError, ConnectionResetError):
                log.warning('ffmpeg pipe closed; stopping video capture')
                return
            elapsed = loop.time() - t0
            await asyncio.sleep(max(0.0, interval - elapsed))

    async def _grab_frame(self) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None or proc.returncode is not None:
            return
        ok, err = await self.vm.send_qmp_screenshot(str(self._frame_path))
        if not ok:
            log.debug('video frame screendump failed: %s', err)
            return
        # screendump returns before the file is fully flushed; give it a beat.
        await asyncio.sleep(0.05)
        try:
            data = self._frame_path.read_bytes()
        except OSError as exc:
            log.debug('could not read video frame: %s', exc)
            return
        if not data:
            return
        proc.stdin.write(data)
        await proc.stdin.drain()
        self._frames += 1
