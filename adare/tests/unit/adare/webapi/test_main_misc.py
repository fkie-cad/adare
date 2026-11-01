"""Contract tests for the non-session endpoints defined directly in ``adare/webapi/main.py``.

Playbook save/load, the action-type palette, the session websocket, the health check and the
SPA catch-all. Consumers on the React side: ``api/hooks/use-playbook.ts``, ``use-actions.ts``,
``services/websocket.ts`` and ``components/workbench/{playbook,manual-actions}-panel.tsx``.

Envelope: ``/api/playbooks/save``, ``/api/playbooks/{filename}`` (success) and ``/api/actions/types``
hand-roll ``{success: True, data}`` (same shape as ``result_to_response``); a missing playbook is a
plain FastAPI ``{"detail": ...}`` 404 (which ``api/client.ts`` reads via ``data.detail``);
``/api/health`` has no envelope at all.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import create_autospec, patch

import pytest
import yaml
from fastapi.testclient import TestClient

from adare.api import DevModeAPI
from adare.core.result import Result
from adare.webapi import main
from adare.webapi.websocket_manager import ws_manager

pytestmark = pytest.mark.unit


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """The handlers resolve ``playbooks/`` against the process cwd: run inside a scratch dir."""
    work = tmp_path / 'work'
    work.mkdir()
    monkeypatch.chdir(work)
    return work


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.fixture
def no_frontend(tmp_path):
    """Make unmatched GETs deterministic: no built frontend."""
    with patch.object(main, '_frontend_dist', tmp_path / 'absent-dist'):
        yield


ACTIONS = [{'click': {'target': {'text': 'OK'}}}, {'idle': {'duration': 2}}]


# --- /api/playbooks/save + /api/playbooks/{filename} -----------------------------------


def test_save_playbook_writes_yaml_and_returns_the_path(client, workdir):
    body = client.post(
        '/api/playbooks/save', json={'filename': 'demo', 'actions': ACTIONS, 'settings': {'idle': 1}}
    ).json()

    assert body == {'success': True, 'data': {'file_path': str(Path('playbooks') / 'demo.yml')}}
    assert yaml.safe_load((workdir / 'playbooks' / 'demo.yml').read_text()) == {
        'settings': {'idle': 1},
        'actions': ACTIONS,
    }


def test_save_playbook_settings_default_to_empty(client, workdir):
    """playbook-panel.tsx always sends ``settings: {}``; the field is optional on the wire."""
    client.post('/api/playbooks/save', json={'filename': 'demo', 'actions': []})

    assert yaml.safe_load((workdir / 'playbooks' / 'demo.yml').read_text()) == {'settings': {}, 'actions': []}


def test_save_playbook_keeps_an_explicit_extension(client, workdir):
    client.post('/api/playbooks/save', json={'filename': 'demo.yaml', 'actions': []})

    assert (workdir / 'playbooks' / 'demo.yaml').is_file()
    assert not (workdir / 'playbooks' / 'demo.yaml.yml').exists()


def test_save_playbook_requires_filename_and_actions(client, workdir):
    assert client.post('/api/playbooks/save', json={'actions': []}).status_code == 422
    assert client.post('/api/playbooks/save', json={'filename': 'x'}).status_code == 422


def test_load_playbook_returns_what_use_load_playbook_reads(client, workdir):
    """use-playbook.ts reads ``data.actions`` and ``data.settings``."""
    client.post('/api/playbooks/save', json={'filename': 'demo', 'actions': ACTIONS, 'settings': {'idle': 1}})

    body = client.get('/api/playbooks/demo').json()

    assert body == {'success': True, 'data': {'actions': ACTIONS, 'settings': {'idle': 1}}}


def test_load_playbook_accepts_names_with_extension_or_spaces(client, workdir):
    """Experiment names (``filename: experiment.name``) may contain spaces; the UI loads them by name."""
    client.post('/api/playbooks/save', json={'filename': 'my experiment', 'actions': ACTIONS})
    client.post('/api/playbooks/save', json={'filename': 'plain.yml', 'actions': []})

    assert client.get('/api/playbooks/my%20experiment').json()['data']['actions'] == ACTIONS
    assert client.get('/api/playbooks/plain.yml').json()['data']['actions'] == []


def test_load_playbook_missing_file_is_a_404_detail_not_an_envelope(client, workdir):
    response = client.get('/api/playbooks/nope')

    assert response.status_code == 404
    assert response.json() == {'detail': "Playbook 'nope' not found"}  # api/client.ts reads data.detail


def test_load_playbook_without_sections_defaults_them(client, workdir):
    (workdir / 'playbooks').mkdir()
    (workdir / 'playbooks' / 'bare.yml').write_text('other: 1\n')

    assert client.get('/api/playbooks/bare').json()['data'] == {'actions': [], 'settings': {}}


@pytest.mark.xfail(
    strict=True,
    reason='an empty playbook file makes yaml.safe_load return None and `.get` raises AttributeError -> HTTP 500',
)
def test_load_empty_playbook_file_is_not_a_server_error(workdir):
    (workdir / 'playbooks').mkdir()
    (workdir / 'playbooks' / 'empty.yml').write_text('')

    response = TestClient(main.app, raise_server_exceptions=False).get('/api/playbooks/empty')

    assert response.status_code < 500


@pytest.mark.xfail(
    strict=True,
    reason=(
        'save_playbook joins the client-supplied filename onto playbooks/ without validation, so '
        '`../escaped` writes <cwd>/escaped.yml outside the playbook directory (path traversal, arbitrary '
        '.yml write relative to the server cwd)'
    ),
)
def test_save_playbook_cannot_escape_the_playbook_directory_with_dotdot(client, workdir):
    client.post('/api/playbooks/save', json={'filename': '../escaped', 'actions': []})

    assert not (workdir / 'escaped.yml').exists()  # playbooks/../escaped.yml


@pytest.mark.xfail(
    strict=True,
    reason=(
        'an absolute `filename` replaces the playbooks/ prefix in `Path("playbooks") / filename`, so the '
        'server writes anywhere the process can write'
    ),
)
def test_save_playbook_cannot_write_to_an_absolute_path(client, workdir, tmp_path):
    target = tmp_path / 'outside' / 'abs.yml'
    target.parent.mkdir()

    client.post('/api/playbooks/save', json={'filename': str(target), 'actions': []})

    assert not target.exists()


def test_load_playbook_does_not_serve_files_outside_the_playbook_directory(client, workdir, no_frontend):
    """Encoded slashes never reach the handler (``{filename}`` is one path segment)."""
    (workdir / 'playbooks').mkdir()
    (workdir / 'secret.yml').write_text('actions: [SECRETACTION]\n')

    for name in ('..%2Fsecret', '%2e%2e%2fsecret', '..%2Fsecret.yml'):
        assert 'SECRETACTION' not in client.get(f'/api/playbooks/{name}').text


def test_load_playbook_dotdot_segment_is_not_found(client, workdir):
    assert client.get('/api/playbooks/%2e%2e').status_code == 404


def test_save_then_load_through_the_real_parser_is_lossless_for_backend_shaped_actions(client, workdir):
    from adare.types.playbook import parse_playbook

    client.post('/api/playbooks/save', json={'filename': 'real', 'actions': [{'idle': {'duration': 2}}]})

    playbook = parse_playbook(workdir / 'playbooks' / 'real.yml')

    assert playbook.actions[0].duration == 2


@pytest.mark.xfail(
    strict=True,
    reason=(
        'playbook-panel.tsx saves actions as the palette builds them (`{type: "Click", target: ...}`, types/action.ts) '
        'but types/playbook.py parse_playbook only accepts `{click: {...}}` style actions, so a playbook saved '
        'from the workbench cannot be parsed by ADARE (CLI run / experiment load)'
    ),
)
def test_playbook_saved_with_frontend_shaped_actions_is_parseable(client, workdir):
    from adare.types.playbook import parse_playbook

    frontend_action = {'type': 'Click', 'target': {'type': 'text', 'text': 'OK'}, 'strategy': 'sweep'}
    client.post('/api/playbooks/save', json={'filename': 'ui', 'actions': [frontend_action]})

    parse_playbook(workdir / 'playbooks' / 'ui.yml')


# --- /api/actions/types -----------------------------------------------------------------


def _action_type_entries(data):
    return list(data.values()) if isinstance(data, dict) else list(data)


def test_action_types_use_the_standard_envelope(client):
    response = client.get('/api/actions/types')

    assert response.status_code == 200
    body = response.json()
    assert body['success'] is True
    assert body['data']


def test_action_types_cover_the_actions_manual_panel_marks_structured(client):
    """manual-actions-panel.tsx STRUCTURED = Click, Keyboard, Wait, Scroll, Command, Screenshot."""
    data = client.get('/api/actions/types').json()['data']
    names = set(data) if isinstance(data, dict) else {e.get('type') for e in data}

    assert {'Click', 'Keyboard', 'Wait', 'Scroll', 'Command', 'Screenshot'} <= names


@pytest.mark.xfail(
    strict=True,
    reason=(
        'use-actions.ts types the payload as ActionTypeMetadata[] and the palette calls '
        '`groupByCategory(actionTypes)` (`items.reduce`) -- the route returns an object keyed by name, '
        'so the manual-actions palette cannot render'
    ),
)
def test_action_types_payload_is_a_list_like_the_frontend_expects(client):
    assert isinstance(client.get('/api/actions/types').json()['data'], list)


@pytest.mark.xfail(
    strict=True,
    reason=(
        'types/action.ts ActionTypeMetadata is {type, category: gui|control|data|system, display_name, '
        'description, icon, default_params}; the route entries carry category "GUI"/"Control Flow"/..., '
        'required_fields/optional_fields and no type/display_name/icon/default_params'
    ),
)
def test_action_types_entries_have_the_palette_fields(client):
    entries = _action_type_entries(client.get('/api/actions/types').json()['data'])

    for entry in entries:
        assert {'type', 'category', 'display_name', 'description', 'icon', 'default_params'} <= entry.keys()
        assert entry['category'] in {'gui', 'control', 'data', 'system'}


@pytest.mark.xfail(
    strict=True,
    reason=(
        'the palette advertises Wait, WaitFor, SetVariable, FileRead, FileWrite and RegistryRead, none of which '
        'is an action ADARE can parse (types/playbook.py _ACTION_CLASSES has idle, wait_until, save_variable, ...)'
    ),
)
def test_every_advertised_action_type_exists_in_the_playbook_parser(client):
    from adare.types.playbook import _ACTION_CLASSES

    names = set(client.get('/api/actions/types').json()['data'])

    assert {n for n in names if n.lower() not in _ACTION_CLASSES} == set()


@pytest.mark.xfail(
    strict=True,
    reason=(
        'advertised fields are not the real ones: Loop "count" (real: times), Screenshot "filename" (real: name), '
        'Test "function" (real: name), Scroll "clicks" (real: amount), Click "strategy"/"button"/"click_count" '
        '(not fields of ClickAction)'
    ),
)
def test_advertised_fields_exist_on_the_real_action_classes(client):
    import attrs

    from adare.types.playbook import _ACTION_CLASSES

    wrong = []
    for name, meta in client.get('/api/actions/types').json()['data'].items():
        cls = _ACTION_CLASSES.get(name.lower())
        if cls is None:
            continue
        fields = {f.name for f in attrs.fields(cls)}
        wrong += [f'{name}.{f}' for f in meta['required_fields'] + meta['optional_fields'] if f not in fields]

    assert wrong == []


# --- /api/health ------------------------------------------------------------------------


def test_health(client):
    response = client.get('/api/health')

    assert response.status_code == 200
    assert response.json() == {'status': 'healthy', 'service': 'adare-web-api'}  # no {success,data} envelope


def test_health_is_not_shadowed_by_the_spa_catch_all(client, tmp_path):
    dist = tmp_path / 'dist'
    dist.mkdir()
    (dist / 'index.html').write_text('<html>spa</html>')

    with patch.object(main, '_frontend_dist', dist):
        response = client.get('/api/health')

    assert response.headers['content-type'].startswith('application/json')


# --- websocket /ws/{session_id} ---------------------------------------------------------


def test_websocket_sends_connected_frame_first(client):
    with client.websocket_connect('/ws/s1') as sock:
        assert sock.receive_json() == {'type': 'connected', 'session_id': 's1', 'message': 'WebSocket connected'}


def test_websocket_answers_the_frontend_ping_with_pong(client):
    """services/websocket.ts sends ``{type: 'ping', session_id}`` every 30 s."""
    with client.websocket_connect('/ws/s1') as sock:
        sock.receive_json()
        sock.send_json({'type': 'ping', 'session_id': 's1'})

        assert sock.receive_json() == {'type': 'pong'}


def test_websocket_ignores_other_messages_and_stays_open(client):
    with client.websocket_connect('/ws/s1') as sock:
        sock.receive_json()
        sock.send_json({'type': 'something-else'})
        sock.send_json({'no': 'type'})
        sock.send_json({'type': 'ping'})

        assert sock.receive_json() == {'type': 'pong'}


def test_websocket_accepts_a_session_id_that_does_not_exist(client):
    """No validation: an unknown/stale session id still connects (and silently never receives anything)."""
    with client.websocket_connect('/ws/does-not-exist') as sock:
        assert sock.receive_json()['session_id'] == 'does-not-exist'


def test_websocket_registers_and_unregisters_the_connection(client):
    with client.websocket_connect('/ws/reg-1') as sock:
        sock.receive_json()
        assert ws_manager.get_connection_count('reg-1') == 1

    assert ws_manager.get_connection_count('reg-1') == 0


def test_websocket_handler_ends_and_unregisters_on_invalid_json(client):
    """A malformed frame ends the handler (the server then drops the socket); the manager forgets it."""
    with client.websocket_connect('/ws/bad-1') as sock:
        sock.receive_json()
        sock.send_text('not json')

    assert ws_manager.get_connection_count('bad-1') == 0


def test_websocket_receives_session_events_broadcast_by_the_rest_routes(client):
    """POST .../stop broadcasts ``{type: session_state, session_id, data: {status}}`` to subscribers."""
    devmode = create_autospec(DevModeAPI, instance=True)
    devmode.stop_session.return_value = Result.ok(True)

    with patch.object(main, 'api', SimpleNamespace(devmode=devmode)), client.websocket_connect('/ws/evt-1') as sock:
        sock.receive_json()
        assert client.post('/api/sessions/evt-1/stop').json()['success'] is True

        assert sock.receive_json() == {
            'type': 'session_state',
            'session_id': 'evt-1',
            'data': {'status': 'stopped'},
        }


def test_websocket_events_are_scoped_to_their_session(client):
    devmode = create_autospec(DevModeAPI, instance=True)
    devmode.stop_session.return_value = Result.ok(True)

    with (
        patch.object(main, 'api', SimpleNamespace(devmode=devmode)),
        client.websocket_connect('/ws/mine') as mine,
        client.websocket_connect('/ws/other') as other,
    ):
        mine.receive_json()
        other.receive_json()
        client.post('/api/sessions/mine/stop')

        assert mine.receive_json()['type'] == 'session_state'
        other.send_json({'type': 'ping'})
        assert other.receive_json() == {'type': 'pong'}  # nothing else was queued before the pong


@pytest.mark.xfail(
    strict=True,
    reason=(
        'types/api.ts ActionCompleteMessage is data: {action_type, result: ActionResult} with the success flag '
        'inside `result`; ws_manager.send_action_complete puts `success` beside `result` and the route '
        'passes a result without `success`. No component subscribes to action_complete yet'
    ),
)
def test_action_complete_frame_matches_the_frontend_message_type(client):
    from adare.core.dto.devmode import DevActionResult

    devmode = create_autospec(DevModeAPI, instance=True)
    devmode.execute_action.return_value = Result.ok(DevActionResult(True, 'ok', 0.1, coordinates=(1, 2)))

    with patch.object(main, 'api', SimpleNamespace(devmode=devmode)), client.websocket_connect('/ws/ac-1') as sock:
        sock.receive_json()
        client.post('/api/sessions/ac-1/actions/execute', json={'action_yaml': 'x'})
        sock.receive_json()  # action_start
        frame = sock.receive_json()

    assert frame['type'] == 'action_complete'
    assert frame['data']['result']['success'] is True


# --- SPA catch-all ----------------------------------------------------------------------


@pytest.fixture
def dist(tmp_path):
    root = (tmp_path / 'site' / 'dist').resolve()
    (root / 'assets').mkdir(parents=True)
    (root / 'index.html').write_text('<html>spa-index</html>')
    (root / 'assets' / 'app.js').write_text('console.log(1)')
    sibling = root.parent / 'dist-private'
    sibling.mkdir()
    (sibling / 'secret.txt').write_text('SECRET')
    with patch.object(main, '_frontend_dist', root):
        yield root


@pytest.mark.parametrize('path', ['/', '/develop', '/projects/some/deep/client/route'])
def test_spa_serves_index_html_for_client_routes(client, dist, path):
    response = client.get(path)

    assert response.status_code == 200
    assert response.headers['content-type'].startswith('text/html')
    assert response.text == '<html>spa-index</html>'


def test_spa_serves_real_static_files(client, dist):
    response = client.get('/assets/app.js')

    assert response.status_code == 200
    assert response.text == 'console.log(1)'
    assert 'javascript' in response.headers['content-type']


def test_spa_without_a_built_frontend_is_a_404_detail(client, no_frontend):
    response = client.get('/develop')

    assert response.status_code == 404
    assert 'Frontend not built' in response.json()['detail']


def test_spa_does_not_shadow_real_api_routes(client, dist):
    assert client.get('/api/actions/types').json()['success'] is True
    assert client.get('/api/sessions/nope/unknown-subroute').status_code in (200, 404)  # see xfail below


@pytest.mark.xfail(
    strict=True,
    reason=(
        'GET /{path:path} also matches unknown /api/... paths, so a typo or removed backend route answers '
        '200 text/html (index.html) instead of a JSON 404; axios in api/client.ts then hands HTML to the hooks '
        '(`data.data` undefined) and real backend 404s are invisible'
    ),
)
@pytest.mark.parametrize('path', ['/api/does-not-exist', '/api/sessions/s1/unknown-subroute', '/api/playbooks/a/b'])
def test_unknown_api_path_is_a_json_404_not_the_spa_index(client, dist, path):
    response = client.get(path)

    assert response.status_code == 404
    assert 'text/html' not in response.headers['content-type']


def test_unknown_api_path_with_wrong_method_is_405_json(client, dist):
    response = client.post('/api/does-not-exist')

    assert response.status_code == 405
    assert response.json() == {'detail': 'Method Not Allowed'}


def test_spa_blocks_parent_directory_traversal(client, dist):
    (dist.parent / 'outside.txt').write_text('OUTSIDE')

    for path in ('/%2e%2e/outside.txt', '/..%2foutside.txt', '/assets/%2e%2e/%2e%2e/outside.txt'):
        assert 'OUTSIDE' not in client.get(path).text


@pytest.mark.xfail(
    strict=True,
    reason=(
        'the traversal guard is `str(file_path).startswith(str(_frontend_dist))` without a path separator, so a '
        'sibling directory sharing the prefix (`dist-private` next to `dist`) is served: '
        'GET /%2e%2e/dist-private/secret.txt returns its content'
    ),
)
def test_spa_blocks_traversal_into_a_sibling_directory_with_the_same_prefix(client, dist):
    response = client.get('/%2e%2e/dist-private/secret.txt')

    assert 'SECRET' not in response.text
