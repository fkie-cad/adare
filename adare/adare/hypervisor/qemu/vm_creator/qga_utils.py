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
        # `execute` already carries the `guest-` prefix (e.g. 'guest-exec'); adding
        # another produced "guest-guest-exec" in operator-facing build logs.
        raise QgaError(f'{execute} transport error: {e}') from e
    finally:
        sock.close()
    if 'error' in resp:
        desc = resp['error'].get('desc', 'unknown error')
        raise QgaError(f'{execute} failed: {desc}')
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


def _encode_powershell(script: str) -> str:
    """Base64 (UTF-16LE) a script for ``powershell.exe -EncodedCommand``.

    Same encoding as ``hypervisor/qemu/mixins/commands.py``. Carrying the script
    this way means the agent's spawn never sees the script's own quoting, spaces or
    operators.
    """
    return base64.b64encode(script.encode('utf-16le')).decode('utf-8')


def _build_exec_args(command: str, cwd: str | None, windows: bool,
                     shell: str | None = None) -> list[str]:
    """Build the (path, arg[]) for ``guest-exec``.

    Reuses the shape of ``hypervisor/qemu/mixins/commands.py`` -- PowerShell with
    a base64 (UTF-16LE) ``-EncodedCommand`` for Windows, ``/bin/bash -c`` for
    everything else. ``cwd`` is folded in as a leading ``cd`` since each
    guest-exec is an independent process.

    ``shell`` overrides the ``windows`` heuristic with an explicit interpreter
    (``'powershell'`` / ``'cmd'`` / ``'bash'``). ``cmd.exe`` matters for build-time
    provisioning: PowerShell parses ``{default}`` in
    ``bcdedit /set {default} ...`` as a script block, so such a command has to
    reach cmd verbatim.
    """
    if shell is None:
        shell = 'powershell' if windows else 'bash'

    if shell == 'powershell':
        script = f'cd {cwd}; {command}' if cwd else command
        return ['powershell.exe', '-EncodedCommand', _encode_powershell(script)]
    if shell == 'cmd':
        # NOT `['cmd.exe', '/c', script]`, even though that is the obvious form.
        # The guest agent's spawn (glib on Windows) rejects certain cmd argument
        # strings outright with "Failed to execute helper program (Permission
        # denied)" -- reproducibly, and before cmd ever parses them. Measured on a
        # real Win11-ARM64 guest: `bcdedit /set {default} bootstatuspolicy
        # ignoreallfailures && bcdedit /set {default} recoveryenabled No` fails 2/2,
        # while each half alone, `bcdedit /enum && bcdedit /enum`, `bcdedit /set &&
        # echo`, and a 1000-character `echo` all succeed. So it is neither length,
        # nor `&&`, nor the braces.
        #
        # Rather than enumerate which argument strings glib dislikes, we never hand
        # it one: PowerShell is the only interpreter we spawn, and it spawns cmd.
        # The command line the agent sees is then always the same shape (an
        # -EncodedCommand blob), which is immune to the whole class of problem.
        # PowerShell's own spawn handles the text fine -- verified by running the
        # identical failing command this way.
        script = f'cd /d {cwd} && {command}' if cwd else command
        # The cmd text is carried base64-encoded and decoded inside PowerShell, so
        # it is never quoted or escaped at any layer. `cmd.exe /c $s` passes it as a
        # single argument, exactly as a direct spawn would have.
        payload = base64.b64encode(script.encode('utf-8')).decode('ascii')
        wrapper = (
            f"$s = [Text.Encoding]::UTF8.GetString("
            f"[Convert]::FromBase64String('{payload}')); "
            f"& cmd.exe /c $s; exit $LASTEXITCODE"
        )
        return ['powershell.exe', '-EncodedCommand', _encode_powershell(wrapper)]
    if shell == 'bash':
        script = f'cd {cwd} && {command}' if cwd else command
        return ['/bin/bash', '-c', script]
    raise QgaError(f'Unsupported guest shell: {shell!r}')


def qga_exec(sock_path: Path, command: str, cwd: str | None = None,
             windows: bool = False, timeout: float = 3600.0,
             poll_interval: float = 0.5, shell: str | None = None,
             progress_callback=None,
             progress_interval: float = 60.0) -> tuple[int, str, str]:
    """Run *command* in the guest and return ``(returncode, stdout, stderr)``.

    Sends ``guest-exec`` then polls ``guest-exec-status`` until the process has
    exited, base64-decoding captured output (same decode as
    ``mixins/commands.py``).

    Note the caller must judge success by the **exit code** alone. A successful
    PowerShell command routinely writes CLIXML progress records to stderr
    (``#< CLIXML ... Preparing modules for first use ...``), so "stderr is
    non-empty" is not a failure signal.

    Args:
        shell: Explicit interpreter (``'powershell'`` / ``'cmd'`` / ``'bash'``).
            Overrides the ``windows`` heuristic.
        progress_callback: Called as ``callback(elapsed_seconds)`` roughly every
            ``progress_interval`` seconds while the command is still running, so a
            45-minute ``msiexec`` can drive a live spinner instead of looking hung.
        progress_interval: Seconds between ``progress_callback`` invocations.

    Raises:
        QgaError: On agent/transport failure, a missing pid, or *timeout*.
    """
    args = _build_exec_args(command, cwd, windows, shell)
    ret = _command(sock_path, 'guest-exec', {
        'path': args[0],
        'arg': args[1:],
        'capture-output': True,
    })
    pid = ret.get('pid') if isinstance(ret, dict) else None
    if pid is None:
        raise QgaError('guest-exec returned no pid')

    started = time.monotonic()
    deadline = started + timeout
    next_progress = started + progress_interval
    while time.monotonic() < deadline:
        status = _command(sock_path, 'guest-exec-status', {'pid': pid})
        if status.get('exited', False):
            returncode = status.get('exitcode', status.get('signal', -1))
            out_b64 = status.get('out-data', '')
            err_b64 = status.get('err-data', '')
            stdout = base64.b64decode(out_b64).decode('utf-8', errors='replace') if out_b64 else ''
            stderr = base64.b64decode(err_b64).decode('utf-8', errors='replace') if err_b64 else ''
            return returncode, stdout, stderr
        now = time.monotonic()
        if progress_callback is not None and now >= next_progress:
            progress_callback(now - started)
            next_progress = now + progress_interval
        time.sleep(poll_interval)
    raise QgaError(f'Timeout waiting for guest command (pid {pid}) after {timeout:.0f}s')


def qga_reboot(sock_path: Path, ready_timeout: float = 900.0) -> None:
    """Reboot the guest via ``guest-shutdown`` mode ``reboot`` and wait for the agent.

    Used by a provisioning step declaring ``reboot: true`` -- an installer that
    only finishes its work on the next boot (a pending file-rename operation, a
    driver install) needs the reboot to happen *inside* the build, not on the
    consumer's first experiment run.

    The agent stops answering during the reboot, so a brief settle wait precedes
    :func:`qga_wait_ready`; without it the ping can succeed against the
    still-running pre-reboot agent and the function would return before the guest
    has actually gone down.

    Raises:
        QgaError: If the agent does not come back within *ready_timeout*.
    """
    # The guest tears down the agent as part of shutting down, so the request
    # itself often gets no reply. That is success, not failure.
    try:
        _command(sock_path, 'guest-shutdown', {'mode': 'reboot'}, timeout=5.0)
    except QgaError as e:
        log.debug('guest-shutdown(reboot) returned no clean reply (expected): %s', e)

    time.sleep(15.0)
    if not qga_wait_ready(sock_path, timeout=ready_timeout):
        raise QgaError(
            f'guest agent did not come back within {ready_timeout:.0f}s after reboot'
        )


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
