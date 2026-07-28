"""Record a whole GUI-agent/experiment run to MP4 by capturing real SPICE
display frames — a higher-fps, higher-quality alternative to
:class:`~adare.backend.experiment.execution.qemu_video_recorder.QemuVideoRecorder`'s
QMP-screendump polling.

QEMU has no push-based frame export; the only monitor primitive is a
synchronous ``screendump`` pull, which is why the existing recorder is capped
to a low fps. SPICE itself *is* push-based (the server sends only changed
regions), so this recorder connects directly to the VM's SPICE display as its
own client via ``libvirt`` (to resolve the port) + PyGObject's
``SpiceClientGLib`` bindings (the same approach the reference ``spice-record``
project uses), and streams raw frames into ``ffmpeg``.

This is deliberately independent of ADARE's own Rust ``VirtualSpice``
client/relay (``adare-web``'s live browser viewer) — no shared code, no shared
process. But a SPICE server accepts only **one** client connection at a time,
so this recorder and VirtualSpice's live viewer are mutually exclusive per VM:
:meth:`start` proactively checks (via QMP ``query-spice``) whether a client is
already connected and raises a clear error instead of silently kicking it off.

Mirrors :class:`QemuVideoRecorder`'s contract (``start``/``stop``,
``ensure_ffmpeg``, :class:`VideoUnavailable`) so it is a drop-in alternative
wherever that class is used today.

Frame delivery crosses a thread boundary: ``SpiceClientGLib`` dispatches its
signals on a GLib main loop, which this class runs on a dedicated background
thread; each display-invalidate callback copies the current primary surface
and hands the bytes to the asyncio side via ``call_soon_threadsafe``. The
exact GObject-introspection call shapes below (``get_primary()``'s return
shape, the ``display-primary-create``/``display-invalidate`` signal
signatures, channel-type detection) follow the documented spice-gtk C API and
common PyGObject usage, but — per the design doc for this recorder — should be
confirmed interactively against the installed spice-gtk version before relying
on this in an unattended run.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

from adare.backend.experiment.execution.qemu_video_recorder import VideoUnavailable

log = logging.getLogger(__name__)

# SPICE surface format codes (spice/enums.h SpiceSurfaceFmt) -> ffmpeg rawvideo
# -pix_fmt. Only the common 32-bit xRGB surface (what virtio-gpu/qxl emit for
# ADARE's Windows/macOS SPICE graphics) is handled; anything else fails clearly
# rather than guessing a byte layout.
_SPICE_FMT_32_XRGB = 32
_PIXMAN_TO_FFMPEG = {_SPICE_FMT_32_XRGB: 'bgra'}


class SpiceClientUnavailable(VideoUnavailable):
    """PyGObject / SpiceClientGLib bindings are missing."""


class SpiceDisplayBusy(VideoUnavailable):
    """The VM's SPICE display already has a connected client."""


class SpiceVideoRecorder:
    """Streams real SPICE display frames into ffmpeg to record a session as MP4."""

    def __init__(
        self,
        vm: Any,
        out_path: str | Path,
        *,
        fps: int | None = None,
        ffmpeg: str = 'ffmpeg',
    ):
        self.vm = vm
        self.out_path = Path(out_path)
        # Advisory max-rate only: frames are push-driven (display-invalidate),
        # not polled, so unlike QemuVideoRecorder this is a ceiling, not a cadence.
        self.fps = int(fps) if fps else None
        self.ffmpeg = ffmpeg

        self._proc: asyncio.subprocess.Process | None = None
        self._frames = 0
        self._stopping = False

        self._asyncio_loop: asyncio.AbstractEventLoop | None = None
        self._frame_queue: asyncio.Queue | None = None
        self._writer_task: asyncio.Task | None = None

        self._glib_thread: threading.Thread | None = None
        self._glib_mainloop = None  # GLib.MainLoop, set on the GLib thread
        self._session = None  # SpiceClientGLib.Session, set on the GLib thread
        self._ready_event = threading.Event()
        self._connect_error: str | None = None
        self._frame_size: tuple[int, int] | None = None
        self._pix_fmt: str | None = None
        self._last_frame_at = 0.0

    # -- preflight ----------------------------------------------------------

    @staticmethod
    def ensure_ffmpeg(ffmpeg: str = 'ffmpeg') -> str:
        """Resolve the ffmpeg binary or raise :class:`VideoUnavailable`."""
        from adare.backend.experiment.execution.qemu_video_recorder import (
            QemuVideoRecorder,
        )
        return QemuVideoRecorder.ensure_ffmpeg(ffmpeg)

    @staticmethod
    def ensure_spice_client() -> None:
        """Confirm PyGObject's SpiceClientGLib bindings are importable.

        Raises :class:`SpiceClientUnavailable` (a :class:`VideoUnavailable`
        subclass) otherwise, so callers can fail fast the same way a missing
        ffmpeg does.
        """
        try:
            import gi
            gi.require_version('SpiceClientGLib', '2.0')
            from gi.repository import SpiceClientGLib  # noqa: F401
        except (ImportError, ValueError) as exc:
            raise SpiceClientUnavailable(
                'PyGObject SpiceClientGLib bindings not found. Install the '
                "spice-gtk GObject-introspection typelib (e.g. Debian/Ubuntu: "
                "'apt install gir1.2-spice-client-glib-2.0 python3-gi'), or "
                'use --video-backend=screendump instead.'
            ) from exc

    # -- lifecycle ----------------------------------------------------------

    async def start(self) -> None:
        """Connect to the VM's SPICE display and begin streaming frames to ffmpeg.

        Raises :class:`VideoUnavailable` if ffmpeg or the SpiceClientGLib
        bindings are missing, or :class:`SpiceDisplayBusy` if the SPICE
        display already has a connected client (e.g. the live browser viewer).
        """
        exe = self.ensure_ffmpeg(self.ffmpeg)
        self.ensure_spice_client()
        await self._check_no_existing_client()
        host, port = await self._resolve_spice_endpoint()

        self.out_path.parent.mkdir(parents=True, exist_ok=True)
        self._asyncio_loop = asyncio.get_running_loop()
        self._frame_queue = asyncio.Queue()

        self._glib_thread = threading.Thread(
            target=self._run_glib_thread, args=(host, port),
            daemon=True, name='spice-video-recorder',
        )
        self._glib_thread.start()

        try:
            await asyncio.wait_for(self._wait_for_ready(), timeout=15)
        except TimeoutError as exc:
            self._shutdown_glib()
            raise VideoUnavailable(
                f'Timed out connecting to SPICE display at {host}:{port}'
            ) from exc
        if self._connect_error:
            self._shutdown_glib()
            raise VideoUnavailable(
                f'Could not connect to SPICE display at {host}:{port}: {self._connect_error}'
            )

        width, height = self._frame_size
        cmd = [
            exe, '-y', '-loglevel', 'error',
            '-f', 'rawvideo', '-pix_fmt', self._pix_fmt,
            '-s', f'{width}x{height}',
            '-use_wallclock_as_timestamps', '1',
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
            self._shutdown_glib()
            raise VideoUnavailable(f'could not launch ffmpeg ({exe}): {exc}') from exc

        log.info(
            'Recording SPICE video to %s (%dx%d %s via %s -> %s:%d)',
            self.out_path, width, height, self._pix_fmt, exe, host, port,
        )
        self._writer_task = asyncio.create_task(self._writer_loop())

    async def stop(self) -> Path | None:
        """Stop capturing, finalize the MP4, and return its path (or None if empty)."""
        if self._stopping:
            return self.out_path if self._frames else None
        self._stopping = True

        if self._writer_task is not None:
            self._writer_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._writer_task
            self._writer_task = None

        self._shutdown_glib()

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

        if not self._frames:
            log.warning('SPICE video recorder captured no frames; %s may be empty', self.out_path)
            return None
        log.info('Wrote SPICE run video (%d frames) to %s', self._frames, self.out_path)
        return self.out_path

    # -- single-client guard --------------------------------------------------

    async def _check_no_existing_client(self) -> None:
        """Raise :class:`SpiceDisplayBusy` if the VM's SPICE display already has a client.

        Uses QEMU's own QMP ``query-spice`` (the same monitor channel
        QemuVideoRecorder/host-GUI-executor already use), not VirtualSpice's
        API — VirtualSpice exposes no per-VM "is a browser watching" state, so
        asking QEMU directly is the only reliable signal without touching the
        Rust client.
        """
        response = await self.vm._send_qmp_command({'execute': 'query-spice'})
        info = response.get('return') or {}
        channels = info.get('channels') or []
        if channels:
            vm_name = getattr(self.vm, 'vm_name', '?')
            raise SpiceDisplayBusy(
                f"VM {vm_name!r} SPICE display already has {len(channels)} connected "
                'channel(s) — likely the live browser viewer (VirtualSpice). SPICE '
                'accepts only one client at a time. Stop watching this VM live before '
                'recording, or use --video-backend=screendump instead.'
            )

    # -- SPICE endpoint resolution --------------------------------------------

    async def _resolve_spice_endpoint(self) -> tuple[str, int]:
        """Resolve the VM's SPICE (host, port) from its live libvirt XML."""
        return await asyncio.get_running_loop().run_in_executor(None, self._resolve_spice_endpoint_sync)

    def _resolve_spice_endpoint_sync(self) -> tuple[str, int]:
        import libvirt

        conn = self.vm._get_libvirt_connection()
        if conn is None:
            raise VideoUnavailable('No libvirt connection available to resolve the SPICE port')
        vm_name = getattr(self.vm, 'vm_name', None)
        try:
            domain = conn.lookupByName(vm_name)
            xml_desc = domain.XMLDesc(0)
        except libvirt.libvirtError as exc:
            raise VideoUnavailable(f'Could not read libvirt XML for {vm_name!r}: {exc}') from exc

        root = ET.fromstring(xml_desc)
        graphics = root.find(".//graphics[@type='spice']")
        if graphics is None:
            raise VideoUnavailable(f'VM {vm_name!r} has no SPICE graphics device configured')
        port = graphics.get('port')
        if not port or port == '-1':
            raise VideoUnavailable(f'VM {vm_name!r} SPICE port not yet allocated')
        listen_el = graphics.find('listen')
        host = None
        if listen_el is not None:
            host = listen_el.get('address')
        host = host or graphics.get('listen') or '127.0.0.1'
        return host, int(port)

    # -- GLib thread / SpiceClientGLib bridge ---------------------------------

    def _run_glib_thread(self, host: str, port: int) -> None:
        try:
            import gi
            gi.require_version('SpiceClientGLib', '2.0')
            from gi.repository import GLib, SpiceClientGLib
        except (ImportError, ValueError) as exc:
            self._fail(f'SpiceClientGLib import failed on capture thread: {exc}')
            return

        context = GLib.MainContext.new()
        context.push_thread_default()
        try:
            self._glib_mainloop = GLib.MainLoop.new(context, False)

            session = SpiceClientGLib.Session.new()
            self._session = session
            session.set_property('host', host)
            session.set_property('port', str(port))
            # ADARE's SPICE graphics (_add_spice_graphics) sets no password —
            # localhost-only listen is the access control.
            session.set_property('password', '')

            session.connect('channel-new', self._on_channel_new, SpiceClientGLib)

            if not session.connect():
                self._fail('SpiceSession.connect() returned False')
                return

            self._glib_mainloop.run()
        finally:
            with contextlib.suppress(Exception):
                if self._session is not None:
                    self._session.disconnect()
            context.pop_thread_default()

    def _on_channel_new(self, session, channel, spice_glib_module) -> None:
        if isinstance(channel, spice_glib_module.DisplayChannel):
            channel.connect('display-primary-create', self._on_primary_create)
            channel.connect('display-invalidate', self._on_invalidate)
        channel.connect('channel-event', self._on_channel_event, spice_glib_module)

    def _on_channel_event(self, channel, event, spice_glib_module) -> None:
        bad_events = {
            spice_glib_module.ChannelEvent.ERROR_CONNECT,
            spice_glib_module.ChannelEvent.ERROR_TLS,
            spice_glib_module.ChannelEvent.ERROR_LINK,
            spice_glib_module.ChannelEvent.ERROR_AUTH,
            spice_glib_module.ChannelEvent.ERROR_IO,
        }
        if event in bad_events and not self._ready_event.is_set():
            self._fail(f'SPICE channel error: {event}')

    def _on_primary_create(self, channel, fmt, width, height, stride, shmid, imgdata) -> None:
        self._frame_size = (width, height)
        self._pix_fmt = _PIXMAN_TO_FFMPEG.get(fmt)
        if self._pix_fmt is None:
            self._fail(f'Unsupported SPICE surface format {fmt} (only 32-bit xRGB is handled)')
            return
        self._mark_ready()
        self._grab_and_enqueue(channel)

    def _on_invalidate(self, channel, x, y, w, h) -> None:
        self._grab_and_enqueue(channel)

    def _grab_and_enqueue(self, channel) -> None:
        if self._pix_fmt is None:
            return  # primary surface not created yet
        if self.fps:
            now = time.monotonic()
            if now - self._last_frame_at < (1.0 / self.fps):
                return
            self._last_frame_at = now
        ok, primary = channel.get_primary(0)
        if not ok:
            return
        data = bytes(primary.data)
        loop = self._asyncio_loop
        if loop is None:
            return
        loop.call_soon_threadsafe(self._enqueue_frame, data)

    def _enqueue_frame(self, data: bytes) -> None:
        if self._frame_queue is not None:
            self._frame_queue.put_nowait(data)

    def _mark_ready(self) -> None:
        self._ready_event.set()

    def _fail(self, message: str) -> None:
        log.warning('SPICE video recorder: %s', message)
        self._connect_error = self._connect_error or message
        self._ready_event.set()

    async def _wait_for_ready(self) -> None:
        await asyncio.get_running_loop().run_in_executor(None, self._ready_event.wait)

    def _shutdown_glib(self) -> None:
        mainloop = self._glib_mainloop
        self._glib_mainloop = None
        if mainloop is not None:
            with contextlib.suppress(Exception):
                mainloop.quit()
        if self._glib_thread is not None:
            self._glib_thread.join(timeout=5)
            if self._glib_thread.is_alive():
                log.warning('SPICE capture thread did not exit within timeout')
            self._glib_thread = None

    # -- frame writer ---------------------------------------------------------

    async def _writer_loop(self) -> None:
        while True:
            data = await self._frame_queue.get()
            proc = self._proc
            if proc is None or proc.stdin is None or proc.returncode is not None:
                return
            try:
                proc.stdin.write(data)
                await proc.stdin.drain()
            except (BrokenPipeError, ConnectionResetError):
                log.warning('ffmpeg pipe closed; stopping SPICE video capture')
                return
            self._frames += 1
