"""Terminals in the browser: PTY sessions (a shell, or Claude Code) bridged over WebSocket.

A session is a process on a pseudo-terminal that outlives any one browser
connection: navigating away or reloading the page reattaches, and the recent
output is replayed. Sessions end when their process exits or when they are
closed, and all of them are hung up when the web server stops.

This is a shell for whoever can reach the endpoint, so every route checks
:func:`require_local`: the client must be on loopback, the Host header must
name localhost (defeats DNS rebinding) and a browser Origin, when sent, must be
local too (defeats cross-site WebSocket hijacking from any other page).

POSIX only (pty/termios); on Windows the routes report that terminals are unavailable.

Protocol on ``/ws/terminals/{id}``: the server sends output as binary frames and
``{"type": "exit", "code": n}`` as text; the client sends
``{"type": "input", "data": "..."}`` and ``{"type": "resize", "cols": c, "rows": r}``.
"""

import asyncio
import contextlib
import json
import logging
import os
import shlex
import signal
import struct
import sys
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

import ulid
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(tags=["terminals"])

MAX_SESSIONS = 8
SCROLLBACK_BYTES = 512 * 1024
READ_CHUNK = 65536
LOCAL_HOSTS = {'localhost', '127.0.0.1', '::1'}

# Variables tying a process to the Claude Code session that started the web server
# (when it was launched from one). A terminal tab is its own session: Claude Code
# refuses to start nested, and the messaging token must not leak into it. User
# configuration such as CLAUDE_CODE_USE_BEDROCK is kept.
_SESSION_ENV = (
    'CLAUDECODE',
    'CLAUDE_PID',
    'CLAUDE_EFFORT',
    'CLAUDE_CODE_ENTRYPOINT',
    'CLAUDE_CODE_EXECPATH',
    'CLAUDE_CODE_SESSION_ID',
    'CLAUDE_CODE_CHILD_SESSION',
    'CLAUDE_CODE_SESSION_ATTENDED',
    'CLAUDE_CODE_MESSAGING_SOCKET',
    'CLAUDE_CODE_MESSAGING_TOKEN',
    'CLAUDE_CODE_SSE_PORT',
)


# ---- Access control ----


def _hostname(value: str) -> str | None:
    """Hostname of a Host header ("127.0.0.1:8089", "[::1]:8089") or an Origin URL."""
    if '://' not in value:
        value = f'http://{value}'
    return urlparse(value).hostname


def is_local_request(client_host: str | None, host_header: str | None, origin: str | None) -> bool:
    if client_host not in LOCAL_HOSTS:
        return False
    if not host_header or _hostname(host_header) not in LOCAL_HOSTS:
        return False
    return origin is None or _hostname(origin) in LOCAL_HOSTS


def require_local(request: Request) -> None:
    if not is_local_request(
        request.client.host if request.client else None, request.headers.get('host'), request.headers.get('origin')
    ):
        raise HTTPException(status_code=403, detail='Terminals are only available from this machine.')


# ---- Sessions ----


@dataclass
class TerminalSession:
    id: str
    title: str
    kind: str
    cwd: str
    argv: list[str]
    pid: int
    fd: int
    created_at: float = field(default_factory=time.time)
    buffer: bytearray = field(default_factory=bytearray)
    listeners: set[asyncio.Queue] = field(default_factory=set)
    exit_code: int | None = None
    fd_open: bool = True  # False once fd is closed: its number may already belong to another file
    outbox: bytearray = field(default_factory=bytearray)  # input the pty has not taken yet

    def info(self) -> dict:
        return {
            'id': self.id,
            'title': self.title,
            'kind': self.kind,
            'cwd': self.cwd,
            'created_at': self.created_at,
            'running': self.exit_code is None,
            'exit_code': self.exit_code,
        }


def _login_shell() -> str:
    return os.environ.get('SHELL') or '/bin/sh'


def build_argv(kind: str, prompt: str | None) -> list[str]:
    """The command for a session kind.

    Claude Code runs through an interactive login shell, so it starts exactly as in
    the user's own terminal (PATH, aliases and wrapper functions included), and the
    tab drops to that shell when Claude exits.
    """
    shell = _login_shell()
    if kind == 'shell':
        return [shell, '-l']
    args = ' '.join(shlex.quote(a) for a in ([prompt] if prompt else []))
    return [shell, '-l', '-i', '-c', f'claude {args}; exec {shlex.quote(shell)} -l']


def terminal_env(base: Mapping[str, str]) -> dict[str, str]:
    env = {k: v for k, v in base.items() if k not in _SESSION_ENV}
    return {**env, 'TERM': 'xterm-256color', 'COLORTERM': 'truecolor', 'ADARE_WEB_TERMINAL': '1'}


def _set_size(fd: int, cols: int, rows: int) -> None:
    import fcntl
    import termios

    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack('HHHH', max(rows, 1), max(cols, 1), 0, 0))


class TerminalManager:
    def __init__(self) -> None:
        self.sessions: dict[str, TerminalSession] = {}
        self._tasks: set[asyncio.Task] = set()

    def create(self, kind: str, cwd: Path, prompt: str | None, title: str, cols: int, rows: int) -> TerminalSession:
        import pty

        running = [s for s in self.sessions.values() if s.exit_code is None]
        if len(running) >= MAX_SESSIONS:
            raise HTTPException(status_code=429, detail=f'At most {MAX_SESSIONS} terminals can run at once.')
        argv = build_argv(kind, prompt)
        env = terminal_env(os.environ)
        pid, fd = pty.fork()
        if pid == 0:  # child: never returns
            try:
                os.chdir(cwd)
                os.execvpe(argv[0], argv, env)
            finally:
                os._exit(127)
        _set_size(fd, cols, rows)
        os.set_blocking(fd, False)
        session = TerminalSession(id=str(ulid.ULID()), title=title, kind=kind, cwd=str(cwd), argv=argv, pid=pid, fd=fd)
        self.sessions[session.id] = session
        asyncio.get_running_loop().add_reader(fd, self._on_output, session)
        logger.info('Terminal %s started: %s in %s (pid %d)', session.id, kind, cwd, pid)
        return session

    def _on_output(self, session: TerminalSession) -> None:
        try:
            data = os.read(session.fd, READ_CHUNK)
        except BlockingIOError:
            return
        except OSError:
            data = b''  # EIO: the child side closed
        if not data:
            self._on_exit(session)
            return
        session.buffer += data
        if len(session.buffer) > SCROLLBACK_BYTES:
            del session.buffer[: len(session.buffer) - SCROLLBACK_BYTES]
        for queue in session.listeners:
            queue.put_nowait(data)

    def _on_exit(self, session: TerminalSession) -> None:
        """The child side closed: stop reading, then reap the process and tell the listeners."""
        self._stop_reading(session)
        self._tasks.add(task := asyncio.get_running_loop().create_task(self._reap(session)))
        task.add_done_callback(self._tasks.discard)

    @staticmethod
    def _stop_reading(session: TerminalSession) -> None:
        """Close the pty once (never twice: the fd number may be reused right after)."""
        if not session.fd_open:
            return
        session.fd_open = False
        loop = asyncio.get_running_loop()
        with contextlib.suppress(ValueError, OSError):
            loop.remove_reader(session.fd)
        with contextlib.suppress(ValueError, OSError):
            loop.remove_writer(session.fd)
        session.outbox.clear()
        with contextlib.suppress(OSError):
            os.close(session.fd)

    @staticmethod
    async def _reap(session: TerminalSession, kill_after: float | None = None) -> None:
        """Wait for the process (SIGKILL it after ``kill_after`` seconds) and record its exit code."""

        def wait() -> int:
            _, status = os.waitpid(session.pid, 0)
            return os.waitstatus_to_exitcode(status)

        waiter = asyncio.ensure_future(asyncio.to_thread(wait))
        try:
            if kill_after is None:
                session.exit_code = await waiter
            else:
                done, _ = await asyncio.wait({waiter}, timeout=kill_after)
                if not done:
                    with contextlib.suppress(ProcessLookupError, PermissionError):
                        os.killpg(session.pid, signal.SIGKILL)
                session.exit_code = await waiter
        except ChildProcessError:
            session.exit_code = session.exit_code if session.exit_code is not None else -1
        logger.info('Terminal %s exited with %s', session.id, session.exit_code)
        for queue in session.listeners:
            queue.put_nowait(None)

    def write(self, session: TerminalSession, data: str) -> None:
        """Queue input; what the pty buffer (a few KB) cannot take now is flushed when it drains."""
        if not session.fd_open:
            return
        pending = bool(session.outbox)
        session.outbox += data.encode()
        if not pending:
            self._flush(session)

    def _flush(self, session: TerminalSession) -> None:
        loop = asyncio.get_running_loop()
        while session.outbox and session.fd_open:
            try:
                written = os.write(session.fd, session.outbox)
            except BlockingIOError:
                loop.add_writer(session.fd, self._flush, session)
                return
            except OSError:
                session.outbox.clear()  # the child side is gone; _on_output will notice
                break
            del session.outbox[:written]
        if session.fd_open:
            with contextlib.suppress(ValueError, OSError):
                loop.remove_writer(session.fd)

    def resize(self, session: TerminalSession, cols: int, rows: int) -> None:
        if session.fd_open:
            with contextlib.suppress(OSError):
                _set_size(session.fd, cols, rows)  # the kernel sends SIGWINCH

    def close(self, session_id: str) -> None:
        """Hang up a session (SIGHUP to its process group, SIGKILL if it lingers) and forget it."""
        session = self.sessions.pop(session_id, None)
        if session is None or not session.fd_open:
            return  # gone, or already exited and being reaped
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(session.pid, signal.SIGHUP)  # pty.fork made the child a session leader
        self._stop_reading(session)
        self._tasks.add(task := asyncio.get_running_loop().create_task(self._reap(session, kill_after=3.0)))
        task.add_done_callback(self._tasks.discard)

    async def shutdown(self) -> None:
        """Hang up every session and wait until they are gone (web server shutdown)."""
        for session_id in list(self.sessions):
            self.close(session_id)
        await asyncio.gather(*self._tasks, return_exceptions=True)


manager = TerminalManager()


def _require_posix() -> None:
    if sys.platform == 'win32':
        raise HTTPException(status_code=501, detail='Terminals need a POSIX host (macOS or Linux).')


# ---- REST ----


class TerminalCreateBody(BaseModel):
    kind: Literal['claude', 'shell'] = 'claude'
    cwd: str | None = Field(None, description='Working directory; the home directory when omitted')
    prompt: str | None = Field(None, description='Initial prompt for Claude')
    title: str | None = None
    cols: int = Field(120, ge=10, le=1000)
    rows: int = Field(32, ge=5, le=500)


@router.get('/api/terminals', dependencies=[Depends(require_local)])
def list_terminals():
    return {'success': True, 'data': [s.info() for s in manager.sessions.values()]}


@router.post('/api/terminals', dependencies=[Depends(require_local)])
async def create_terminal(body: TerminalCreateBody):
    _require_posix()
    cwd = Path(body.cwd).expanduser() if body.cwd else Path.home()
    if not cwd.is_dir():
        return {'success': False, 'error': {'code': 'NOT_FOUND', 'message': f'No such directory: {cwd}'}}
    title = body.title or ('Claude' if body.kind == 'claude' else 'Shell') + f' · {cwd.name or cwd}'
    session = manager.create(body.kind, cwd, body.prompt, title, body.cols, body.rows)
    return {'success': True, 'data': session.info()}


@router.delete('/api/terminals/{session_id}', dependencies=[Depends(require_local)])
async def close_terminal(session_id: str):
    manager.close(session_id)
    return {'success': True, 'data': None}


# ---- WebSocket ----


async def _pump_output(websocket: WebSocket, session: TerminalSession, queue: asyncio.Queue) -> None:
    while True:
        data = await queue.get()
        if data is None:
            await websocket.send_text(json.dumps({'type': 'exit', 'code': session.exit_code}))
            return
        await websocket.send_bytes(data)


async def _pump_input(websocket: WebSocket, session: TerminalSession) -> None:
    while True:
        message = json.loads(await websocket.receive_text())
        if message.get('type') == 'input':
            manager.write(session, str(message.get('data', '')))
        elif message.get('type') == 'resize':
            manager.resize(session, int(message.get('cols', 80)), int(message.get('rows', 24)))


@router.websocket('/ws/terminals/{session_id}')
async def attach_terminal(websocket: WebSocket, session_id: str) -> None:
    if not is_local_request(
        websocket.client.host if websocket.client else None,
        websocket.headers.get('host'),
        websocket.headers.get('origin'),
    ):
        await websocket.close(code=1008, reason='Terminals are only available from this machine.')
        return
    session = manager.sessions.get(session_id)
    if session is None:
        await websocket.close(code=1008, reason='No such terminal.')
        return
    await websocket.accept()
    queue: asyncio.Queue = asyncio.Queue()
    if session.buffer:
        await websocket.send_bytes(bytes(session.buffer))
    if session.exit_code is not None:
        await websocket.send_text(json.dumps({'type': 'exit', 'code': session.exit_code}))
        await websocket.close()
        return
    session.listeners.add(queue)
    tasks = [
        asyncio.create_task(_pump_output(websocket, session, queue)),
        asyncio.create_task(_pump_input(websocket, session)),
    ]
    try:
        _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, (WebSocketDisconnect, asyncio.CancelledError, RuntimeError)):
                continue
            if isinstance(result, (ValueError, TypeError)):
                logger.debug('Terminal %s: bad client message: %s', session_id, result)
    finally:
        session.listeners.discard(queue)
        with contextlib.suppress(RuntimeError, WebSocketDisconnect):
            await websocket.close()
