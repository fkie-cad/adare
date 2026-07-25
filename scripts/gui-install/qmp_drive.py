#!/usr/bin/env python3
"""QMP driver for headless, LLM-free GUI-installer automation.

Talks to a running QEMU instance over its QMP unix socket to:

  * capture the guest screen (``screendump`` -> PPM, optional PNG),
  * send keyboard chords / type text (``send-key``),
  * move + click an absolute mouse (``input-send-event`` + usb-tablet),
  * wait until the screen stops changing (``wait_stable``) — the key primitive
    that makes replay robust to host speed without any image recognition.

It has no third-party dependencies: PPM frames are diffed as raw bytes, so
``wait_stable`` needs only the stdlib. PNG conversion (for saved screenshots)
is best-effort via ``pnmtopng`` or Pillow if present, else the ``.ppm`` is kept.

CLI (handy for interactive poking):

  qmp_drive.py --sock S shot out.png
  qmp_drive.py --sock S key ret
  qmp_drive.py --sock S type "hello world"
  qmp_drive.py --sock S tap 512 384 1024 768
  qmp_drive.py --sock S stable --settle 20 --timeout 600
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import time

# --- character -> QEMU qcode (QKeyCode) mapping for type() -------------------
_BASE = {
    '\n': ('ret', False), ' ': ('spc', False), '\t': ('tab', False),
    '-': ('minus', False), '=': ('equal', False), '.': ('dot', False),
    ',': ('comma', False), '/': ('slash', False), ';': ('semicolon', False),
    "'": ('apostrophe', False), '`': ('grave_accent', False),
    '[': ('bracket_left', False), ']': ('bracket_right', False),
    '\\': ('backslash', False),
}
_SHIFTED = {
    '_': 'minus', '+': 'equal', ':': 'semicolon', '"': 'apostrophe',
    '?': 'slash', '<': 'comma', '>': 'dot', '~': 'grave_accent',
    '{': 'bracket_left', '}': 'bracket_right', '|': 'backslash',
    '!': '1', '@': '2', '#': '3', '$': '4', '%': '5', '^': '6',
    '&': '7', '*': '8', '(': '9', ')': '0',
}


def _char_to_keys(ch: str) -> tuple[list[str], bool]:
    if ch.isalpha():
        return [ch.lower()], ch.isupper()
    if ch.isdigit():
        return [ch], False
    if ch in _BASE:
        q, sh = _BASE[ch]
        return [q], sh
    if ch in _SHIFTED:
        return [_SHIFTED[ch]], True
    raise ValueError(f'unmapped character {ch!r} for send-key')


class QMP:
    """Minimal synchronous QMP client with input + framebuffer helpers."""

    def __init__(self, sock_path: str, connect_timeout: float = 30.0):
        self.sock_path = sock_path
        self._ppm = f'/tmp/.qmp_drive_{os.getpid()}.ppm'
        self.s = socket.socket(socket.AF_UNIX)
        deadline = time.time() + connect_timeout
        while True:
            try:
                self.s.connect(sock_path)
                break
            except (FileNotFoundError, ConnectionRefusedError):
                if time.time() > deadline:
                    raise SystemExit(f'QMP socket not ready: {sock_path}')
                time.sleep(0.2)
        self.f = self.s.makefile('r')
        self._readline()             # greeting
        self.cmd('qmp_capabilities')

    # -- low level ----------------------------------------------------------
    def _readline(self):
        return json.loads(self.f.readline())

    def cmd(self, execute: str, **args):
        obj = {'execute': execute}
        if args:
            obj['arguments'] = args
        self.s.sendall((json.dumps(obj) + '\n').encode())
        while True:
            resp = self._readline()
            if 'error' in resp:
                raise RuntimeError(f'QMP error on {execute}: {resp["error"]}')
            if 'return' in resp:
                return resp['return']

    def close(self):
        try:
            self.s.close()
        except OSError:
            pass

    # -- input --------------------------------------------------------------
    def key(self, qcodes, shift: bool = False):
        keys = (['shift'] if shift else []) + list(qcodes)
        self.cmd('send-key', keys=[{'type': 'qcode', 'data': k} for k in keys])

    def type_text(self, text: str, per_key_delay: float = 0.03):
        for ch in text:
            qcodes, shift = _char_to_keys(ch)
            self.key(qcodes, shift)
            time.sleep(per_key_delay)

    def move(self, x: int, y: int, w: int, h: int):
        ax = round(x / max(w - 1, 1) * 32767)
        ay = round(y / max(h - 1, 1) * 32767)
        self.cmd('input-send-event', events=[
            {'type': 'abs', 'data': {'axis': 'x', 'value': ax}},
            {'type': 'abs', 'data': {'axis': 'y', 'value': ay}},
        ])

    def click(self, button: str = 'left'):
        self.cmd('input-send-event',
                 events=[{'type': 'btn', 'data': {'button': button, 'down': True}}])
        time.sleep(0.05)
        self.cmd('input-send-event',
                 events=[{'type': 'btn', 'data': {'button': button, 'down': False}}])

    def tap(self, x: int, y: int, w: int, h: int):
        self.move(x, y, w, h)
        time.sleep(0.1)
        self.click()

    def powerdown(self):
        self.cmd('system_powerdown')

    # -- framebuffer --------------------------------------------------------
    def _dump_ppm(self) -> bytes:
        self.cmd('screendump', filename=self._ppm)
        with open(self._ppm, 'rb') as fh:
            return fh.read()

    def shot(self, out_path: str) -> str:
        """Save a screenshot. Converts PPM->PNG if a converter exists."""
        data = self._dump_ppm()
        if out_path.endswith('.png'):
            if _pnmtopng(self._ppm, out_path) or _pil_convert(self._ppm, out_path):
                return out_path
            out_path = out_path[:-4] + '.ppm'   # fall back to PPM
        with open(out_path, 'wb') as fh:
            fh.write(data)
        return out_path

    def wait_stable(self, settle: float = 20.0, timeout: float = 600.0,
                    poll: float = 3.0, tol: float = 0.001,
                    min_elapsed: float = 0.0) -> bool:
        """Block until the screen is unchanged for ``settle`` seconds.

        Two consecutive frames count as "same" when fewer than ``tol`` of their
        bytes differ (ignores cursor blink / tiny redraws). Returns True on
        settle, False on timeout. During an install the progress bar keeps the
        frame changing, so this only settles once the installer is idle
        (e.g. the 'Installation Complete' dialog).

        ``min_elapsed`` is a floor: it will not return before that many seconds
        have passed, even if the screen looks stable. Use it to skip past the
        static early-boot / plymouth screens that would otherwise settle
        immediately before the real UI has rendered.
        """
        start = time.time()
        deadline = start + timeout
        prev = self._dump_ppm()
        stable_since = None
        while time.time() < deadline:
            time.sleep(poll)
            cur = self._dump_ppm()
            same = len(cur) == len(prev) and _diff_ratio(prev, cur) < tol
            prev = cur
            if same:
                if stable_since is None:
                    stable_since = time.time()
                elif (time.time() - stable_since >= settle
                      and time.time() - start >= min_elapsed):
                    return True
            else:
                stable_since = None
        return False


def _diff_ratio(a: bytes, b: bytes) -> float:
    n = min(len(a), len(b))
    if n == 0:
        return 1.0
    # sample every 7th byte for speed on multi-MB frames
    step = 7
    diff = sum(1 for i in range(0, n, step) if a[i] != b[i])
    return diff / (n / step)


def _pnmtopng(ppm: str, png: str) -> bool:
    if not shutil.which('pnmtopng'):
        return False
    try:
        with open(png, 'wb') as out:
            subprocess.run(['pnmtopng', ppm], stdout=out, stderr=subprocess.DEVNULL,
                           check=True)
        return True
    except (subprocess.CalledProcessError, OSError):
        return False


def _pil_convert(ppm: str, png: str) -> bool:
    try:
        from PIL import Image
    except ImportError:
        return False
    try:
        Image.open(ppm).save(png)
        return True
    except OSError:
        return False


def _main():
    ap = argparse.ArgumentParser(description='QMP GUI-drive helper')
    ap.add_argument('--sock', default=os.environ.get('QMP_SOCK', '/tmp/gui-install/qmp.sock'))
    sub = ap.add_subparsers(dest='op', required=True)
    sub.add_parser('shot').add_argument('out')
    kp = sub.add_parser('key'); kp.add_argument('qcodes', nargs='+')
    tp = sub.add_parser('type'); tp.add_argument('text')
    mp = sub.add_parser('tap'); mp.add_argument('coords', nargs=4, type=int)
    st = sub.add_parser('stable')
    st.add_argument('--settle', type=float, default=20.0)
    st.add_argument('--timeout', type=float, default=600.0)
    a = ap.parse_args()
    q = QMP(a.sock)
    if a.op == 'shot':
        print(q.shot(a.out))
    elif a.op == 'key':
        q.key(a.qcodes)
    elif a.op == 'type':
        q.type_text(a.text)
    elif a.op == 'tap':
        q.tap(*a.coords)
    elif a.op == 'stable':
        print('stable' if q.wait_stable(a.settle, a.timeout) else 'timeout')
    q.close()


if __name__ == '__main__':
    _main()
