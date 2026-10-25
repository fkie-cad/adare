"""Browser terminals: who may open one, what they run, and a real PTY round trip."""

import json
import sys
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adare.webapi import terminal
from adare.webapi.terminal import build_argv, is_local_request

pytestmark = pytest.mark.unit

posix_only = pytest.mark.skipif(sys.platform == 'win32', reason='terminals need a POSIX pty')


@pytest.mark.parametrize(
    'client,host,origin,allowed',
    [
        ('127.0.0.1', '127.0.0.1:8089', None, True),
        ('127.0.0.1', 'localhost:8089', 'http://localhost:8089', True),
        ('::1', '[::1]:8089', 'http://[::1]:8089', True),
        ('127.0.0.1', '127.0.0.1:8089', 'http://localhost:5173', True),  # vite dev server
        ('127.0.0.1', '127.0.0.1:8089', 'https://evil.example', False),  # cross-site WebSocket hijacking
        ('127.0.0.1', 'evil.example:8089', 'http://evil.example:8089', False),  # DNS rebinding
        ('192.168.1.20', '192.168.1.5:8089', None, False),  # another machine
        ('127.0.0.1', None, None, False),
        (None, '127.0.0.1:8089', None, False),
    ],
)
def test_only_local_clients_get_a_terminal(client, host, origin, allowed):
    assert is_local_request(client, host, origin) is allowed


def test_build_argv(monkeypatch):
    monkeypatch.setenv('SHELL', '/bin/zsh')

    assert build_argv('shell', None) == ['/bin/zsh', '-l']
    claude = build_argv('claude', "fix the playbook's wait_until")
    assert claude[:4] == ['/bin/zsh', '-l', '-i', '-c']
    # the prompt is one quoted argument; the tab falls back to the shell when Claude exits
    assert claude[4] == "claude 'fix the playbook'\"'\"'s wait_until'; exec /bin/zsh -l"
    assert build_argv('claude', None)[4] == 'claude ; exec /bin/zsh -l'


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(terminal.router)
    return app


def test_remote_requests_are_refused(app):
    # TestClient presents itself as host "testclient" / "testserver": not local
    client = TestClient(app)

    assert client.get('/api/terminals').status_code == 403
    assert client.post('/api/terminals', json={'kind': 'shell'}).status_code == 403


@posix_only
def test_shell_session_round_trip(app, tmp_path, monkeypatch):
    monkeypatch.setenv('SHELL', '/bin/sh')
    monkeypatch.setattr(terminal, 'manager', terminal.TerminalManager())
    with patch.object(terminal, 'is_local_request', return_value=True), TestClient(app) as client:
        created = client.post('/api/terminals', json={'kind': 'shell', 'cwd': str(tmp_path)}).json()
        assert created['success'] is True
        session_id = created['data']['id']
        assert created['data']['running'] is True
        assert [s['id'] for s in client.get('/api/terminals').json()['data']] == [session_id]

        with client.websocket_connect(f'/ws/terminals/{session_id}') as ws:
            ws.send_text(json.dumps({'type': 'resize', 'cols': 100, 'rows': 30}))
            ws.send_text(json.dumps({'type': 'input', 'data': 'pwd; echo ADARE_$((40+2)); exit 3\n'}))
            output, exit_code = b'', None
            while exit_code is None:
                message = ws.receive()
                if message.get('bytes'):
                    output += message['bytes']
                elif message.get('text'):
                    exit_code = json.loads(message['text'])['code']

        assert b'ADARE_42' in output
        assert tmp_path.name.encode() in output
        assert exit_code == 3
        info = client.get('/api/terminals').json()['data'][0]
        assert (info['running'], info['exit_code']) == (False, 3)

        # reattaching to a finished session replays its output, then reports the exit
        with client.websocket_connect(f'/ws/terminals/{session_id}') as ws:
            assert b'ADARE_42' in ws.receive_bytes()
            assert json.loads(ws.receive_text()) == {'type': 'exit', 'code': 3}

        client.delete(f'/api/terminals/{session_id}')
        assert client.get('/api/terminals').json()['data'] == []


@posix_only
def test_closing_a_running_session_hangs_it_up(app, tmp_path, monkeypatch):
    monkeypatch.setenv('SHELL', '/bin/sh')
    manager = terminal.TerminalManager()
    monkeypatch.setattr(terminal, 'manager', manager)
    with patch.object(terminal, 'is_local_request', return_value=True), TestClient(app) as client:
        session_id = client.post('/api/terminals', json={'kind': 'shell', 'cwd': str(tmp_path)}).json()['data']['id']
        session = manager.sessions[session_id]

        client.delete(f'/api/terminals/{session_id}')
        client.portal.call(manager.shutdown)  # waits for the reap

    assert session.exit_code is not None
    assert manager.sessions == {}


@posix_only
def test_missing_directory_is_reported(app, tmp_path):
    with patch.object(terminal, 'is_local_request', return_value=True), TestClient(app) as client:
        body = client.post('/api/terminals', json={'kind': 'shell', 'cwd': str(tmp_path / 'nope')}).json()

    assert body['success'] is False
    assert 'No such directory' in body['error']['message']


def test_terminal_env_drops_the_parent_claude_session():
    env = terminal.terminal_env(
        {
            'PATH': '/usr/bin',
            'CLAUDECODE': '1',
            'CLAUDE_CODE_MESSAGING_TOKEN': 'secret',
            'CLAUDE_CODE_USE_BEDROCK': '1',
        }
    )

    assert 'CLAUDECODE' not in env
    assert 'CLAUDE_CODE_MESSAGING_TOKEN' not in env
    assert env['CLAUDE_CODE_USE_BEDROCK'] == '1'  # user configuration stays
    assert (env['PATH'], env['TERM']) == ('/usr/bin', 'xterm-256color')


@posix_only
def test_large_paste_reaches_the_process_whole(app, tmp_path, monkeypatch):
    """More input than the pty buffer takes at once is queued, not dropped."""
    monkeypatch.setenv('SHELL', '/bin/sh')
    monkeypatch.setattr(terminal, 'manager', terminal.TerminalManager())
    payload = 'x' * 200_000
    target = tmp_path / 'pasted.txt'
    with patch.object(terminal, 'is_local_request', return_value=True), TestClient(app) as client:
        session_id = client.post('/api/terminals', json={'kind': 'shell', 'cwd': str(tmp_path)}).json()['data']['id']
        with client.websocket_connect(f'/ws/terminals/{session_id}') as ws:
            # Raw mode so the line discipline does not cap the line length. The paste
            # must wait until stty took effect (canonical mode drops what does not fit
            # its ~1 KiB line buffer): READY only appears in the output once it has,
            # since the echoed command line reads RE""ADY.
            ws.send_text(
                json.dumps(
                    {
                        'type': 'input',
                        'data': f'stty raw -echo; echo RE""ADY; head -c {len(payload)} > {target}; exit\n',
                    }
                )
            )
            output = b''
            while b'READY' not in output:
                output += ws.receive_bytes()
            ws.send_text(json.dumps({'type': 'input', 'data': payload}))
            while True:
                message = ws.receive()
                if message.get('text'):
                    break

    assert target.read_text() == payload
