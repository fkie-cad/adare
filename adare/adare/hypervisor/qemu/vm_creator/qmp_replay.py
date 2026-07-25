"""QMP replay primitives — deterministic GUI-installer driving with no vision model.

This is the packaged form of ``scripts/gui-install/qmp_drive.py``. It talks to a
running QEMU over its QMP unix socket to capture the guest screen, send keyboard
chords, type text, and click an absolute-positioned mouse.

The primitive that makes replay robust is :meth:`QMPReplaySession.wait_stable`:
successive ``screendump`` frames are diffed **as raw bytes** until the screen
stops changing. There is no template matching, no OCR and no model in the loop,
so a step never waits on a fixed sleep that is too short on a slow host or
wastefully long on a fast one. During an install the progress bar keeps the frame
changing, so a ``wait_stable`` only returns once the installer is genuinely idle
(e.g. sitting on its "Installation Complete" dialog).

Two hard-won constraints, both learned by breaking them:

* **Use ``-vga qxl``, never ``-vga std``.** The std adapter's tablet applies a 2x
  coordinate scaling, so absolute clicks land at double the intended offset and
  the right half of the screen is simply unreachable.
* **Click buttons with :meth:`tap`, not the keyboard.** ubiquity does not reliably
  hold keyboard focus at live-session start, and its timezone screen traps focus
  in the city-entry field. A mouse click both focuses the window and activates the
  button.
"""

import json
import logging
import os
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path

from adare.backend.experiment.execution.qemu_host_gui_executor import (
    PYAUTOGUI_TO_QCODE,
    SHIFT_MAP,
)
from adare.hypervisor.exceptions import HypervisorException

log = logging.getLogger(__name__)

# Frames are multi-MB; comparing every byte is needless work for a change
# detector, so sample every Nth byte.
_DIFF_SAMPLE_STEP = 7

# Fraction of sampled bytes that may differ while still counting two frames as
# "the same screen". Absorbs cursor blink and one-character redraws.
_DEFAULT_DIFF_TOLERANCE = 0.001

_SUPPORTED_ACTIONS = ('key', 'type', 'tap', 'wait', 'wait_stable', 'shot')


class QMPReplayError(HypervisorException):
    """Raised when the QMP replay session cannot drive the guest."""


def char_to_qcode(ch: str) -> tuple[str, bool]:
    """Map a single character to ``(qcode, needs_shift)``.

    Uses the same tables as the experiment-time GUI executor so that a playbook
    types identically whether it is replayed during an install or during a run.
    """
    if ch.isalpha():
        qcode = PYAUTOGUI_TO_QCODE.get(ch.lower())
        if qcode is None:
            raise QMPReplayError(f'unmapped character {ch!r}')
        return qcode, ch.isupper()

    if ch in SHIFT_MAP:
        base = SHIFT_MAP[ch]
        qcode = PYAUTOGUI_TO_QCODE.get(base)
        if qcode is None:
            raise QMPReplayError(f'unmapped shifted character {ch!r} (base {base!r})')
        return qcode, True

    qcode = PYAUTOGUI_TO_QCODE.get(ch)
    if qcode is None:
        raise QMPReplayError(f'unmapped character {ch!r}')
    return qcode, False


class QMPReplaySession:
    """Synchronous QMP client with input and framebuffer helpers.

    Usable as a context manager; the socket is closed on exit.
    """

    def __init__(self, sock_path: Path, connect_timeout: float = 60.0):
        self.sock_path = Path(sock_path)
        self._tmpdir = tempfile.mkdtemp(prefix='adare-qmp-replay-')
        # screendump writes host-side, so the path must be host-writable.
        self._frame_path = Path(self._tmpdir) / 'frame.ppm'
        self._sock: socket.socket | None = None
        self._reader = None
        self._connect(connect_timeout)

    # ── lifecycle ────────────────────────────────────────────────────

    def _connect(self, timeout: float) -> None:
        """Connect and complete the QMP handshake (greeting + capabilities)."""
        deadline = time.monotonic() + timeout
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        while True:
            try:
                sock.connect(str(self.sock_path))
                break
            except (FileNotFoundError, ConnectionRefusedError):
                if time.monotonic() > deadline:
                    sock.close()
                    raise QMPReplayError(
                        f'QMP socket never became ready after {timeout:.0f}s: {self.sock_path}'
                    ) from None
                time.sleep(0.2)

        self._sock = sock
        self._reader = sock.makefile('r')
        self._readline()                # server greeting
        self.cmd('qmp_capabilities')    # leave negotiation mode
        log.info('QMP replay session attached to %s', self.sock_path)

    def close(self) -> None:
        if self._reader is not None:
            try:
                self._reader.close()
            except OSError:
                pass
            self._reader = None
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
            self._sock = None
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def __enter__(self) -> 'QMPReplaySession':
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    # ── low level ────────────────────────────────────────────────────

    def _readline(self) -> dict:
        line = self._reader.readline()
        if not line:
            raise QMPReplayError('QMP connection closed by QEMU (guest died?)')
        try:
            return json.loads(line)
        except json.JSONDecodeError as e:
            raise QMPReplayError(f'malformed QMP response: {line!r}') from e

    def cmd(self, execute: str, **arguments):
        """Send one QMP command and return its ``return`` payload."""
        obj = {'execute': execute}
        if arguments:
            obj['arguments'] = arguments
        try:
            self._sock.sendall((json.dumps(obj) + '\n').encode())
        except OSError as e:
            raise QMPReplayError(f'QMP send failed for {execute}: {e}') from e

        while True:
            resp = self._readline()
            if 'error' in resp:
                raise QMPReplayError(f'QMP error on {execute}: {resp["error"]}')
            if 'return' in resp:
                return resp['return']
            # Anything else is an asynchronous event; keep reading.

    # ── input ────────────────────────────────────────────────────────

    def key(self, qcodes, shift: bool = False) -> None:
        """Press ``qcodes`` together as one chord, optionally with shift held."""
        keys = (['shift'] if shift else []) + [
            PYAUTOGUI_TO_QCODE.get(str(k).lower(), str(k).lower()) for k in qcodes
        ]
        self.cmd('send-key', keys=[{'type': 'qcode', 'data': k} for k in keys])

    def type_text(self, text: str, per_key_delay: float = 0.03) -> None:
        for ch in text:
            qcode, shift = char_to_qcode(ch)
            self.key([qcode], shift=shift)
            time.sleep(per_key_delay)

    def move(self, x: int, y: int, width: int, height: int) -> None:
        """Move the absolute pointer to ``(x, y)`` in a ``width x height`` frame.

        usb-tablet takes absolute coordinates in a fixed 0..32767 range, so the
        playbook's pixel coordinates are scaled against the frame they were
        recorded at.
        """
        ax = round(x / max(width - 1, 1) * 32767)
        ay = round(y / max(height - 1, 1) * 32767)
        self.cmd('input-send-event', events=[
            {'type': 'abs', 'data': {'axis': 'x', 'value': ax}},
            {'type': 'abs', 'data': {'axis': 'y', 'value': ay}},
        ])

    def click(self, button: str = 'left') -> None:
        self.cmd('input-send-event',
                 events=[{'type': 'btn', 'data': {'button': button, 'down': True}}])
        time.sleep(0.05)
        self.cmd('input-send-event',
                 events=[{'type': 'btn', 'data': {'button': button, 'down': False}}])

    def tap(self, x: int, y: int, width: int, height: int) -> None:
        """Move then click — the preferred way to hit installer buttons."""
        self.move(x, y, width, height)
        time.sleep(0.1)
        self.click()

    def powerdown(self) -> None:
        self.cmd('system_powerdown')

    # ── framebuffer ──────────────────────────────────────────────────

    def _dump_frame(self) -> bytes:
        self.cmd('screendump', filename=str(self._frame_path))
        try:
            return self._frame_path.read_bytes()
        except OSError as e:
            raise QMPReplayError(f'could not read screendump {self._frame_path}: {e}') from e

    def shot(self, out_path: Path) -> Path:
        """Save a screenshot, converting PPM to PNG when a converter is available."""
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        data = self._dump_frame()

        if out_path.suffix.lower() == '.png':
            if _ppm_to_png(self._frame_path, out_path):
                return out_path
            out_path = out_path.with_suffix('.ppm')   # keep the raw frame instead

        out_path.write_bytes(data)
        return out_path

    def wait_stable(
        self,
        settle: float = 20.0,
        timeout: float = 600.0,
        poll: float = 3.0,
        tolerance: float = _DEFAULT_DIFF_TOLERANCE,
        min_elapsed: float = 0.0,
    ) -> bool:
        """Block until the screen has been unchanged for ``settle`` seconds.

        Returns True once the screen settles, False if ``timeout`` elapses first
        (a timeout is reported by the caller, not raised — a slow screen is often
        still recoverable and the per-step screenshot shows what was on it).

        ``min_elapsed`` is a floor on the return time. It exists because the
        static early-boot / plymouth screens are perfectly stable and would
        otherwise satisfy ``settle`` before the real UI has even rendered.
        """
        start = time.monotonic()
        deadline = start + timeout
        previous = self._dump_frame()
        stable_since: float | None = None

        while time.monotonic() < deadline:
            time.sleep(poll)
            current = self._dump_frame()
            unchanged = (
                len(current) == len(previous)
                and _diff_ratio(previous, current) < tolerance
            )
            previous = current

            if not unchanged:
                stable_since = None
                continue

            now = time.monotonic()
            if stable_since is None:
                stable_since = now
            elif now - stable_since >= settle and now - start >= min_elapsed:
                return True

        return False


def _diff_ratio(a: bytes, b: bytes) -> float:
    """Fraction of sampled bytes that differ between two frames."""
    n = min(len(a), len(b))
    if n == 0:
        return 1.0
    sampled = range(0, n, _DIFF_SAMPLE_STEP)
    differing = sum(1 for i in sampled if a[i] != b[i])
    return differing / max(len(sampled), 1)


def _ppm_to_png(ppm: Path, png: Path) -> bool:
    """Best-effort PPM->PNG via Pillow, falling back to netpbm's pnmtopng."""
    try:
        from PIL import Image
    except ImportError:
        pass
    else:
        try:
            with Image.open(ppm) as img:
                img.save(png)
            return True
        except (OSError, ValueError) as e:
            log.debug('Pillow could not convert %s: %s', ppm, e)

    if shutil.which('pnmtopng') is None:
        return False
    try:
        with png.open('wb') as out:
            subprocess.run(['pnmtopng', str(ppm)], stdout=out,
                           stderr=subprocess.DEVNULL, check=True)
        return True
    except (subprocess.CalledProcessError, OSError) as e:
        log.debug('pnmtopng could not convert %s: %s', ppm, e)
        return False


def run_steps(
    session: QMPReplaySession,
    steps: list[dict],
    shot_dir: Path,
    on_progress=None,
) -> list[str]:
    """Execute playbook ``steps`` against the guest.

    Screenshots are written to ``shot_dir`` for every step that names one; they
    are the only debugging aid when a coordinate mis-clicks, so they stay on by
    default.

    Returns the list of non-fatal warnings (currently ``wait_stable`` timeouts).
    A malformed or unknown step is fatal and raises :class:`QMPReplayError`.
    """
    shot_dir = Path(shot_dir)
    shot_dir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []

    for index, step in enumerate(steps):
        action = step.get('action')
        if action not in _SUPPORTED_ACTIONS:
            raise QMPReplayError(
                f'step {index}: unknown action {action!r} '
                f'(known: {", ".join(_SUPPORTED_ACTIONS)})'
            )

        note = step.get('note', '')
        repeat = int(step.get('repeat', 1))
        label = f'[{index:02d}] {action}' + (f' x{repeat}' if repeat > 1 else '')
        if on_progress is not None:
            on_progress(label, note)
        log.info('replay %s %s', label, note)

        for _ in range(repeat):
            if action == 'key':
                session.key(step['keys'], shift=bool(step.get('shift', False)))
            elif action == 'type':
                session.type_text(str(step['text']))
            elif action == 'tap':
                session.tap(*step['coords'])
            elif action == 'wait':
                time.sleep(float(step['seconds']))
            elif action == 'wait_stable':
                settled = session.wait_stable(
                    settle=float(step.get('settle', 20)),
                    timeout=float(step.get('timeout', 600)),
                    poll=float(step.get('poll', 3)),
                    min_elapsed=float(step.get('min', 0)),
                )
                if not settled:
                    warning = (
                        f'step {index} (wait_stable{f": {note}" if note else ""}) '
                        f'timed out after {step.get("timeout", 600)}s'
                    )
                    warnings.append(warning)
                    log.warning('%s', warning)
            # 'shot' does nothing here; the screenshot is taken below.

            if action in ('key', 'tap'):
                time.sleep(float(step.get('pause', 0.4)))

        name = step.get('shot')
        if action == 'shot':
            name = name or step.get('name') or f'step{index:02d}'
        if name:
            saved = session.shot(shot_dir / f'{index:02d}_{name}.png')
            log.info('replay screenshot -> %s', saved)

    return warnings


def wait_for_qmp_socket(sock_path: Path, process: subprocess.Popen,
                        timeout: float = 60.0) -> None:
    """Wait for QEMU to create its QMP socket, failing fast if QEMU died.

    Without the liveness check a bad command line turns into a full ``timeout``
    of waiting for a socket that will never appear.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if sock_path.exists():
            return
        if process.poll() is not None:
            stderr = b''
            if process.stderr is not None:
                stderr = process.stderr.read() or b''
            raise QMPReplayError(
                f'QEMU exited with code {process.returncode} before opening its QMP '
                f'socket: {stderr.decode(errors="replace").strip()}'
            )
        time.sleep(0.2)
    raise QMPReplayError(f'QEMU did not create a QMP socket within {timeout:.0f}s')


def unlink_socket(sock_path: Path) -> None:
    """Remove a stale QMP socket; QEMU refuses to bind over an existing one."""
    try:
        os.unlink(sock_path)
    except FileNotFoundError:
        pass
    except OSError as e:
        log.warning('Could not remove stale QMP socket %s: %s', sock_path, e)
