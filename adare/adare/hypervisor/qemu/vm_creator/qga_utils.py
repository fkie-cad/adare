"""QEMU Guest Agent (QGA) socket client for the interactive-extend console.

Speaks the guest-agent JSON protocol over a virtio-serial Unix socket, mirroring
the connect/send/recv idiom in ``qmp_utils.py`` but for guest-side command
execution and file transfer.

Two differences from QMP matter here:

- QGA sends **no greeting** and needs **no capabilities handshake** -- you
  connect and send ``{"execute": ...}`` directly.
- A **fresh connection is opened per command**. The guest agent's exec PIDs and
  file handles are global to the agent (not per-connection), so a request/reply
  over its own short-lived socket is safe and avoids any stale buffered data
  bleeding between requests.
"""

import base64
import json
import logging
import socket
import time
from pathlib import Path

log = logging.getLogger(__name__)

# Raw bytes of file data moved per guest-file-read / guest-file-write round-trip.
_FILE_CHUNK = 256 * 1024


class QgaError(Exception):
    """Raised when a guest-agent command fails or the agent is unreachable."""


def _connect(sock_path: Path, timeout: float = 10.0) -> socket.socket:
    """Open a single connection to the QGA Unix socket (one attempt)."""
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        sock.connect(str(sock_path))
        return sock
    except (ConnectionRefusedError, FileNotFoundError) as e:
        raise QgaError(f'Could not connect to QGA socket {sock_path}: {e}') from e


def _recv_json(sock: socket.socket) -> dict:
    """Read one newline-delimited JSON object from *sock*."""
    buf = b''
    while b'\n' not in buf:
        chunk = sock.recv(65536)
        if not chunk:
            break
        buf += chunk
    line, _, _ = buf.partition(b'\n')
    if not line.strip():
        raise QgaError('Empty response from guest agent')
    try:
        return json.loads(line.decode('utf-8', errors='replace'))
    except json.JSONDecodeError as e:
        raise QgaError(f'Malformed JSON from guest agent: {e}') from e


def _command(sock_path: Path, execute: str, arguments: dict | None = None,
             timeout: float = 10.0):
    """Run one guest-agent command over a fresh connection; return its ``return``.

    Raises QgaError if the agent replies with an ``error`` object or is
    unreachable. The ``return`` value is passed through verbatim -- it may be a
    dict (most commands), an int (``guest-file-open`` handle), or ``{}``.
    """
    cmd: dict = {'execute': execute}
    if arguments is not None:
        cmd['arguments'] = arguments
    sock = _connect(sock_path, timeout=timeout)
    try:
        sock.sendall(json.dumps(cmd).encode() + b'\n')
        resp = _recv_json(sock)
    except OSError as e:
        raise QgaError(f'guest-{execute} transport error: {e}') from e
    finally:
        sock.close()
    if 'error' in resp:
        desc = resp['error'].get('desc', 'unknown error')
        raise QgaError(f'guest-{execute} failed: {desc}')
    return resp.get('return', {})


def qga_wait_ready(sock_path: Path, timeout: float = 240.0) -> bool:
    """Retry-connect + ``guest-ping`` until the agent answers or *timeout* elapses.

    Mirrors the retry loop in ``qmp_utils.send_keypress_via_qmp`` -- the guest is
    still booting until the agent starts responding.

    Returns:
        True once the agent responds; False if it never does within *timeout*.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            _command(sock_path, 'guest-ping', timeout=5.0)
            return True
        except QgaError:
            time.sleep(1.0)
    return False


def _build_exec_args(command: str, cwd: str | None, windows: bool) -> list[str]:
    """Build the (path, arg[]) for ``guest-exec``.

    Reuses the shape of ``hypervisor/qemu/mixins/commands.py`` -- PowerShell with
    a base64 (UTF-16LE) ``-EncodedCommand`` for Windows, ``/bin/bash -c`` for
    everything else. ``cwd`` is folded in as a leading ``cd`` since each
    guest-exec is an independent process.
    """
    if windows:
        script = f'cd {cwd}; {command}' if cwd else command
        encoded = base64.b64encode(script.encode('utf-16le')).decode('utf-8')
        return ['powershell.exe', '-EncodedCommand', encoded]
    script = f'cd {cwd} && {command}' if cwd else command
    return ['/bin/bash', '-c', script]


def qga_exec(sock_path: Path, command: str, cwd: str | None = None,
             windows: bool = False, timeout: float = 3600.0,
             poll_interval: float = 0.5) -> tuple[int, str, str]:
    """Run *command* in the guest and return ``(returncode, stdout, stderr)``.

    Sends ``guest-exec`` then polls ``guest-exec-status`` until the process has
    exited, base64-decoding captured output (same decode as
    ``mixins/commands.py``).

    Raises:
        QgaError: On agent/transport failure, a missing pid, or *timeout*.
    """
    args = _build_exec_args(command, cwd, windows)
    ret = _command(sock_path, 'guest-exec', {
        'path': args[0],
        'arg': args[1:],
        'capture-output': True,
    })
    pid = ret.get('pid') if isinstance(ret, dict) else None
    if pid is None:
        raise QgaError('guest-exec returned no pid')

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        status = _command(sock_path, 'guest-exec-status', {'pid': pid})
        if status.get('exited', False):
            returncode = status.get('exitcode', status.get('signal', -1))
            out_b64 = status.get('out-data', '')
            err_b64 = status.get('err-data', '')
            stdout = base64.b64decode(out_b64).decode('utf-8', errors='replace') if out_b64 else ''
            stderr = base64.b64decode(err_b64).decode('utf-8', errors='replace') if err_b64 else ''
            return returncode, stdout, stderr
        time.sleep(poll_interval)
    raise QgaError(f'Timeout waiting for guest command (pid {pid}) after {timeout:.0f}s')


def qga_push_file(sock_path: Path, local: str | Path, remote: str) -> int:
    """Copy a host file *local* into the guest at *remote*. Returns bytes written.

    Chunked via ``guest-file-open`` / ``guest-file-write`` / ``guest-file-close``
    (base64 per chunk).
    """
    local = Path(local)
    if not local.is_file():
        raise QgaError(f'Local file not found: {local}')
    data = local.read_bytes()

    handle = _command(sock_path, 'guest-file-open', {'path': remote, 'mode': 'wb'})
    try:
        offset = 0
        while offset < len(data):
            chunk = data[offset:offset + _FILE_CHUNK]
            buf_b64 = base64.b64encode(chunk).decode('utf-8')
            _command(sock_path, 'guest-file-write', {'handle': handle, 'buf-b64': buf_b64})
            offset += len(chunk)
    finally:
        _command(sock_path, 'guest-file-close', {'handle': handle})
    return len(data)


def qga_pull_file(sock_path: Path, remote: str, local: str | Path) -> int:
    """Copy a guest file *remote* out to the host at *local*. Returns bytes read.

    Chunked via ``guest-file-open`` / ``guest-file-read`` / ``guest-file-close``
    (base64 per chunk), reading until EOF.
    """
    handle = _command(sock_path, 'guest-file-open', {'path': remote, 'mode': 'rb'})
    chunks: list[bytes] = []
    try:
        while True:
            res = _command(sock_path, 'guest-file-read',
                           {'handle': handle, 'count': _FILE_CHUNK})
            buf_b64 = res.get('buf-b64', '')
            if buf_b64:
                chunks.append(base64.b64decode(buf_b64))
            if res.get('eof', False) or not buf_b64:
                break
    finally:
        _command(sock_path, 'guest-file-close', {'handle': handle})

    data = b''.join(chunks)
    local = Path(local)
    local.write_bytes(data)
    return len(data)
