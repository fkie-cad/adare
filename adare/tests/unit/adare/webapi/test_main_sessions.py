"""Contract tests for the dev-session endpoints defined directly in ``adare/webapi/main.py``.

Layers
------
* Session/VM work is mocked at the ``api.devmode`` boundary with real DTO objects
  (``DevSessionInfo``, ``DevCheckpointInfo`` ...), so serialisation through
  ``result_to_response`` is the real one.
* Read-only routes and every "unknown session" path run against a *real*
  ``DevModeService`` backed by a throw-away SQLite file (no VM, libvirt or network).

The point of the file is the React workbench (``adare-web/src/components/workbench/*`` via
``api/hooks/use-sessions.ts`` / ``use-checkpoints.ts`` / ``use-actions.ts``): each test says
which field the frontend reads. Tests that assert a field the frontend reads but the backend
does not send are ``xfail(strict=True)`` and name the consumer.

Envelope: every route here that goes through ``result_to_response`` answers
``{success, data}`` / ``{success: False, error: {code, message, solutions}}`` and reports a
*failure with HTTP 200* (the frontend's ``api/client.ts`` interceptor therefore never sees it).
"""

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import call, create_autospec, patch

import pytest
from fastapi.testclient import TestClient

from adare.api import DevModeAPI
from adare.backend.devmode.session import DevModeSnapshot
from adare.core.dto.devmode import (
    DevActionResult,
    DevCheckpointCreateRequest,
    DevCheckpointDeleteRequest,
    DevCheckpointRestoreRequest,
    DevPlaybookExecuteRequest,
    DevPlaybookResult,
    DevResetRequest,
    DevResetResult,
    DevSessionInfo,
    DevSessionStartRequest,
    DevSessionStopRequest,
)
from adare.core.result import Result
from adare.database.api.devmode import DevModeApi
from adare.database.models.devcheckpoint import DevCheckpoint
from adare.services.devmode import DevModeService
from adare.webapi import main
from adare.webapi.websocket_manager import WebSocketManager

pytestmark = pytest.mark.unit

SESSION_ID = '01HZZZZZZZZZZZZZZZZZZZZZZZ'
NOW = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


# --- fixtures ---------------------------------------------------------------------------


@pytest.fixture
def devmode():
    """A DevModeAPI double that only allows the methods the real facade has."""
    return create_autospec(DevModeAPI, instance=True)


@pytest.fixture
def ws():
    """Stand-in for the websocket broadcaster (async methods become AsyncMocks)."""
    return create_autospec(WebSocketManager, instance=True)


@pytest.fixture
def client(devmode, ws):
    with patch.object(main, 'api', SimpleNamespace(devmode=devmode)), patch.object(main, 'ws_manager', ws):
        yield TestClient(main.app)


@pytest.fixture
def service_devmode():
    """A DevModeService double: the object that really has ``reset_soft`` / ``reset_hard``."""
    return create_autospec(DevModeService, instance=True)


@pytest.fixture
def service_client(service_devmode, ws):
    """``api.devmode`` bound straight to the service (bypasses the DevModeAPI facade)."""
    with patch.object(main, 'api', SimpleNamespace(devmode=service_devmode)), patch.object(main, 'ws_manager', ws):
        yield TestClient(main.app)


@pytest.fixture
def real_service(tmp_path):
    """A real DevModeService whose session/checkpoint tables live in a temp SQLite file."""
    service = DevModeService()
    service._db_api = DevModeApi(db_path=tmp_path / 'global.db')
    return service


@pytest.fixture
def real_client(real_service, ws):
    with (
        patch.object(main, 'api', SimpleNamespace(devmode=DevModeAPI(service=real_service))),
        patch.object(main, 'ws_manager', ws),
    ):
        yield TestClient(main.app)


@pytest.fixture
def real_service_client(real_service, ws):
    """Real service + real DB, ``api.devmode`` bound straight to the service."""
    with patch.object(main, 'api', SimpleNamespace(devmode=real_service)), patch.object(main, 'ws_manager', ws):
        yield TestClient(main.app)


def _session_info(**overrides) -> DevSessionInfo:
    values = {
        'session_id': SESSION_ID,
        'project_path': Path('/projects/demo'),
        'environment_name': 'ubuntu-env',
        'vm_running': True,
        'actions_executed': 0,
        'created_at': NOW,
        'current_variables': {},
        'available_snapshots': [
            DevModeSnapshot(snapshot_name='initial', created_at=NOW, variable_state={}, checkpoint_id='C1')
        ],
        'experiment_name': None,
        'name': 'my-session',
    }
    values.update(overrides)
    return DevSessionInfo(**values)


def _fail(code='ENVIRONMENT_NOT_FOUND', message='boom', solutions=('try again',)):
    return Result.fail(code, message, list(solutions))


def _seed_session(service, session_id=SESSION_ID, status='stopped', experiment='exp-a', environment='ubuntu-env'):
    service._db_api.save_session(session_id, Path('/projects/demo'), experiment, environment, 'vm-1', name='n1')
    if status != 'running':
        service._db_api.update_session_status(session_id, status)


# --- /api/sessions/start ----------------------------------------------------------------


def test_start_session_translates_request_into_dto(client, devmode):
    devmode.start_session.return_value = Result.ok(_session_info())

    body = {
        'project_path': '/projects/demo',
        'experiment_name': 'ignored-experiment',
        'environment_name': 'ubuntu-env',
        'gui_mode': 'headless',
        'vm_memory': 2048,
        'vm_cpus': 2,
        'debug_screenshots': True,
    }
    assert client.post('/api/sessions/start', json=body).status_code == 200

    dto = devmode.start_session.call_args.args[0]
    assert isinstance(dto, DevSessionStartRequest)
    assert dto.project_path == Path('/projects/demo')
    assert dto.environment_name == 'ubuntu-env'
    assert (dto.gui_mode, dto.vm_memory, dto.vm_cpus, dto.debug_screenshots) == ('headless', 2048, 2, True)


def test_start_session_accepts_a_request_without_experiment_name(client, devmode):
    """Dev sessions are bound to an environment; ``experiment_name`` is optional on the wire."""
    devmode.start_session.return_value = Result.ok(_session_info())

    response = client.post('/api/sessions/start', json={'project_path': '/p', 'environment_name': 'env'})

    assert response.status_code == 200
    assert response.json()['success'] is True


def test_start_session_response_carries_the_id_the_frontend_reads(client, devmode, ws):
    """use-sessions.ts ``useStartSession`` -> ``session.session_id`` (toast + onCreated selection)."""
    devmode.start_session.return_value = Result.ok(_session_info())

    body = client.post(
        '/api/sessions/start', json={'project_path': '/projects/demo', 'environment_name': 'ubuntu-env'}
    ).json()

    assert body['success'] is True
    data = body['data']
    assert data['session_id'] == SESSION_ID
    # real serialisation: Path -> str, datetime -> ISO string, nested dataclass -> dict
    assert data['project_path'] == '/projects/demo'
    assert data['created_at'] == NOW.isoformat()
    assert data['available_snapshots'][0]['snapshot_name'] == 'initial'
    assert data['available_snapshots'][0]['created_at'] == NOW.isoformat()
    ws.send_session_state.assert_awaited_once_with(SESSION_ID, {'status': 'started', 'vm_running': True})


def test_start_session_failure_is_http_200_envelope_and_sends_no_ws_event(client, devmode, ws):
    devmode.start_session.return_value = _fail('ENVIRONMENT_NOT_FOUND', "Environment 'x' not found", ['adare env list'])

    response = client.post('/api/sessions/start', json={'project_path': '/p', 'environment_name': 'x'})

    assert response.status_code == 200  # the frontend must check data.success itself
    assert response.json() == {
        'success': False,
        'error': {
            'code': 'ENVIRONMENT_NOT_FOUND',
            'message': "Environment 'x' not found",
            'solutions': ['adare env list'],
        },
    }
    ws.send_session_state.assert_not_awaited()


def test_start_session_requires_project_path_and_environment(client, devmode):
    assert client.post('/api/sessions/start', json={'environment_name': 'e'}).status_code == 422
    assert client.post('/api/sessions/start', json={'project_path': '/p'}).status_code == 422
    devmode.start_session.assert_not_called()


# --- /api/sessions/{id}/stop ------------------------------------------------------------


def test_stop_session_without_body_uses_defaults(client, devmode, ws):
    """use-sessions.ts posts with no body at all."""
    devmode.stop_session.return_value = Result.ok(True)

    body = client.post(f'/api/sessions/{SESSION_ID}/stop').json()

    assert body == {'success': True, 'data': True}
    devmode.stop_session.assert_called_once_with(DevSessionStopRequest(session_id=SESSION_ID, remove_resources=False))
    ws.send_session_state.assert_awaited_once_with(SESSION_ID, {'status': 'stopped'})


def test_stop_session_passes_remove_resources(client, devmode):
    devmode.stop_session.return_value = Result.ok(True)

    client.post(f'/api/sessions/{SESSION_ID}/stop', json={'remove_resources': True})

    assert devmode.stop_session.call_args.args[0].remove_resources is True


def test_stop_session_failure_is_enveloped_without_ws_event(client, devmode, ws):
    devmode.stop_session.return_value = _fail('STOP_FAILED', 'vm busy')

    response = client.post(f'/api/sessions/{SESSION_ID}/stop')

    assert response.status_code == 200
    assert response.json()['success'] is False
    assert response.json()['error']['code'] == 'STOP_FAILED'
    ws.send_session_state.assert_not_awaited()


# --- GET /api/sessions ------------------------------------------------------------------


def test_list_sessions_empty(real_client):
    assert real_client.get('/api/sessions').json() == {'success': True, 'data': []}


def test_list_sessions_items_have_the_fields_the_workbench_dropdown_reads(real_client, real_service):
    """session-controls.tsx / workbench.tsx read session_id, vm_running and vm_name per item."""
    _seed_session(real_service)

    with patch.object(real_service, '_session_vm_alive', return_value=False):
        body = real_client.get('/api/sessions').json()

    assert body['success'] is True
    (item,) = body['data']
    assert item['session_id'] == SESSION_ID
    assert item['vm_running'] is False
    assert item['vm_name'] == 'vm-1'
    assert item['status'] == 'stopped'
    assert isinstance(item['created_at'], str)
    assert item['project_path'] == '/projects/demo'


@pytest.mark.xfail(
    strict=True,
    reason=(
        'session-controls.tsx renders `{s.experiment} · {s.environment}` (types/session.ts '
        'DevSessionListItem) but DevSessionListItem sends experiment_name / environment_name, so '
        'every option reads "undefined · undefined"'
    ),
)
def test_list_sessions_items_use_the_keys_the_frontend_types_declare(real_client, real_service):
    _seed_session(real_service)

    with patch.object(real_service, '_session_vm_alive', return_value=False):
        (item,) = real_client.get('/api/sessions').json()['data']

    assert item['experiment'] == 'exp-a'
    assert item['environment'] == 'ubuntu-env'


def test_list_sessions_reconciles_stale_running_row_to_stopped(real_client, real_service):
    _seed_session(real_service, status='running')

    with patch.object(real_service, '_session_vm_alive', return_value=False):
        (item,) = real_client.get('/api/sessions').json()['data']

    assert item['status'] == 'stopped'
    assert item['vm_running'] is False


def test_list_sessions_filters_by_project_path(devmode, client):
    from adare.core.dto.devmode import DevSessionListRequest

    devmode.list_sessions.return_value = Result.ok([])

    client.get('/api/sessions', params={'project_path': '/projects/demo'})
    client.get('/api/sessions')

    assert devmode.list_sessions.call_args_list == [
        call(DevSessionListRequest(project_path=Path('/projects/demo'))),
        call(DevSessionListRequest(project_path=None)),
    ]


# --- GET /api/sessions/{id}/state -------------------------------------------------------


def test_session_state_serialises_dev_session_info(client, devmode):
    devmode.get_state.return_value = Result.ok(_session_info(current_variables={'x': 1}, actions_executed=3))

    data = client.get(f'/api/sessions/{SESSION_ID}/state').json()['data']

    assert data['session_id'] == SESSION_ID
    assert data['current_variables'] == {'x': 1}
    assert data['actions_executed'] == 3
    assert data['vm_running'] is True


@pytest.mark.xfail(
    strict=True,
    reason=(
        'types/session.ts SessionState (use-sessions.ts useSessionState) is {variables, checkpoints, '
        'execution_stats}; the route returns DevSessionInfo (current_variables, available_snapshots, '
        'actions_executed). No component calls the hook yet, so nothing breaks today'
    ),
)
def test_session_state_matches_the_frontend_session_state_type(client, devmode):
    devmode.get_state.return_value = Result.ok(_session_info())

    data = client.get(f'/api/sessions/{SESSION_ID}/state').json()['data']

    assert {'variables', 'checkpoints', 'execution_stats'} <= data.keys()


# --- POST /api/sessions/cleanup ---------------------------------------------------------


def test_cleanup_reconciles_dead_running_sessions(real_client, real_service):
    _seed_session(real_service, status='running')

    with patch.object(real_service, '_session_vm_alive', return_value=False):
        body = real_client.post('/api/sessions/cleanup').json()

    assert body['success'] is True
    assert body['data'] == {
        'sessions_reconciled': 1,
        'reconciled_session_ids': [SESSION_ID],
        'sessions_left_running': 0,
    }


@pytest.mark.xfail(
    strict=True,
    reason=(
        'use-sessions.ts useCleanupSessions types `data` as a number and session-controls.tsx toasts '
        '`${count} stale session(s) removed`; the route returns a DevCleanupResult object, so the toast '
        'reads "[object Object] stale session(s) removed"'
    ),
)
def test_cleanup_data_is_the_count_the_frontend_expects(real_client, real_service):
    _seed_session(real_service, status='running')

    with patch.object(real_service, '_session_vm_alive', return_value=False):
        data = real_client.post('/api/sessions/cleanup').json()['data']

    assert isinstance(data, int)


def test_cleanup_passes_project_filter(client, devmode):
    from adare.core.dto.devmode import DevCleanupResult, DevSessionCleanupRequest

    devmode.cleanup_stale_sessions.return_value = Result.ok(DevCleanupResult())

    client.post('/api/sessions/cleanup', params={'project_path': '/projects/demo'})

    devmode.cleanup_stale_sessions.assert_called_once_with(
        DevSessionCleanupRequest(project_path=Path('/projects/demo'))
    )


# --- POST /api/sessions/{id}/actions/execute --------------------------------------------


def test_execute_action_result_has_the_fields_the_manual_actions_panel_reads(client, devmode, ws):
    """manual-actions-panel.tsx reads result.success / message / error_message / execution_time / coordinates."""
    devmode.execute_action.return_value = Result.ok(
        DevActionResult(success=True, message='clicked', execution_time=0.25, coordinates=(10, 20))
    )

    body = client.post(
        f'/api/sessions/{SESSION_ID}/actions/execute', json={'action_yaml': 'idle:\n  duration: 1\n'}
    ).json()

    assert body['success'] is True
    data = body['data']
    assert data['success'] is True
    assert data['message'] == 'clicked'
    assert data['execution_time'] == 0.25
    assert data['coordinates'] == [10, 20]  # tuple -> JSON array, TS `[number, number]`

    dto = devmode.execute_action.call_args.args[0]
    assert (dto.session_id, dto.action_source, dto.action_content) == (
        SESSION_ID,
        'yaml',
        'idle:\n  duration: 1\n',
    )


def test_execute_action_failed_action_is_still_a_successful_request(client, devmode, ws):
    """An action that ran and failed is ``success: true`` + ``data.success: false`` (not an error envelope)."""
    devmode.execute_action.return_value = Result.ok(
        DevActionResult(success=False, message='target not found', execution_time=1.5)
    )

    body = client.post(f'/api/sessions/{SESSION_ID}/actions/execute', json={'action_yaml': 'x'}).json()

    assert body['success'] is True
    assert body['data']['success'] is False
    assert body['data']['message'] == 'target not found'
    assert body['data']['coordinates'] is None
    ws.send_action_complete.assert_awaited_once()
    assert ws.send_action_complete.await_args.kwargs['success'] is False


def test_execute_action_broadcasts_start_then_complete(client, devmode, ws):
    devmode.execute_action.return_value = Result.ok(
        DevActionResult(success=True, message='ok', execution_time=0.1, coordinates=(1, 2))
    )

    client.post(f'/api/sessions/{SESSION_ID}/actions/execute', json={'action_yaml': 'x'})

    ws.send_action_start.assert_awaited_once_with(SESSION_ID, action_type='action', description='Executing action')
    ws.send_action_complete.assert_awaited_once_with(
        SESSION_ID,
        action_type='action',
        success=True,
        result={'message': 'ok', 'execution_time': 0.1, 'coordinates': (1, 2)},
    )


def test_execute_action_failure_envelope_has_no_data_for_the_frontend_to_read(client, devmode, ws):
    """useExecuteAction does ``data.data!`` -> undefined when the route answers with an error envelope."""
    devmode.execute_action.return_value = _fail('INVALID_ACTION_SOURCE', 'Unknown action')

    response = client.post(f'/api/sessions/{SESSION_ID}/actions/execute', json={'action_yaml': 'x'})

    assert response.status_code == 200
    body = response.json()
    assert body['success'] is False
    assert 'data' not in body
    # an action_start was broadcast but no completion/error event follows
    ws.send_action_start.assert_awaited_once()
    ws.send_action_complete.assert_not_awaited()


def test_execute_action_requires_action_yaml(client, devmode):
    assert client.post(f'/api/sessions/{SESSION_ID}/actions/execute', json={}).status_code == 422
    devmode.execute_action.assert_not_called()


@pytest.mark.xfail(
    strict=True,
    reason=(
        'manual-actions-panel.tsx builds `type: Click` / `type: Wait` style drafts from /api/actions/types '
        '(`stringify({type: meta.type, ...})`) and posts them as action_yaml; the backend parser '
        '(types/playbook.py structure_action) only knows lower-case action keys (`click:`, `idle:` ...) '
        'and rejects "Unknown action", so the palette cannot execute anything'
    ),
)
def test_frontend_palette_yaml_is_accepted_by_the_real_action_parser():
    import yaml

    from adare.types.playbook import structure_action

    frontend_yaml = 'type: Click\ntarget:\n  type: image\n  image: ok.png\nstrategy: sweep\n'

    structure_action(yaml.safe_load(frontend_yaml))


# --- POST /api/sessions/{id}/playbooks/execute ------------------------------------------


def test_execute_playbook_writes_a_temp_yaml_for_the_service_and_removes_it(client, devmode):
    import yaml

    seen = {}

    def fake_execute(dto):
        seen['dto'] = dto
        seen['path'] = Path(dto.playbook_content)
        seen['yaml'] = yaml.safe_load(seen['path'].read_text())
        return Result.ok(
            DevPlaybookResult(
                success=True,
                total_actions=2,
                successful_actions=2,
                failed_actions=0,
                execution_time=1.0,
                action_results=[DevActionResult(success=True, message='ok', execution_time=0.5, coordinates=(3, 4))],
            )
        )

    devmode.execute_playbook.side_effect = fake_execute
    actions = [{'idle': {'duration': 1}}, {'command': {'command': 'ls'}}]

    body = client.post(
        f'/api/sessions/{SESSION_ID}/playbooks/execute', json={'actions': actions, 'settings': {'idle': 2}}
    ).json()

    dto = seen['dto']
    assert isinstance(dto, DevPlaybookExecuteRequest)
    assert (dto.session_id, dto.playbook_source) == (SESSION_ID, 'file')
    assert seen['yaml'] == {'settings': {'idle': 2}, 'actions': actions}
    assert not seen['path'].exists()
    assert body['success'] is True
    assert body['data']['total_actions'] == 2
    assert body['data']['action_results'][0] == {
        'success': True,
        'message': 'ok',
        'execution_time': 0.5,
        'coordinates': [3, 4],
        'data': None,
    }


def test_execute_playbook_cleans_up_temp_file_on_failure(client, devmode):
    paths = []

    def fake_execute(dto):
        paths.append(Path(dto.playbook_content))
        return _fail('PLAYBOOK_ERROR', 'bad playbook')

    devmode.execute_playbook.side_effect = fake_execute

    body = client.post(f'/api/sessions/{SESSION_ID}/playbooks/execute', json={'actions': []}).json()

    assert body['success'] is False
    assert not paths[0].exists()


def test_execute_playbook_requires_actions(client, devmode):
    assert client.post(f'/api/sessions/{SESSION_ID}/playbooks/execute', json={}).status_code == 422
    devmode.execute_playbook.assert_not_called()


# --- POST /api/sessions/{id}/reset ------------------------------------------------------


def test_reset_defaults_to_soft(service_client, service_devmode):
    service_devmode.reset_soft.return_value = Result.ok(
        DevResetResult(success=True, reset_type='soft', execution_time=0.1, message='done')
    )

    body = service_client.post(f'/api/sessions/{SESSION_ID}/reset').json()

    assert body['success'] is True
    assert body['data']['reset_type'] == 'soft'
    service_devmode.reset_soft.assert_called_once_with(DevResetRequest(session_id=SESSION_ID, reset_type='soft'))
    service_devmode.reset_hard.assert_not_called()


def test_reset_hard_via_reset_type_query(service_client, service_devmode):
    service_devmode.reset_hard.return_value = Result.ok(
        DevResetResult(success=True, reset_type='hard', execution_time=3.0, message='restored')
    )

    service_client.post(f'/api/sessions/{SESSION_ID}/reset', params={'reset_type': 'hard'})

    service_devmode.reset_hard.assert_called_once_with(DevResetRequest(session_id=SESSION_ID, reset_type='hard'))
    service_devmode.reset_soft.assert_not_called()


def test_reset_rejects_unknown_type(service_client, service_devmode):
    assert service_client.post(f'/api/sessions/{SESSION_ID}/reset', params={'reset_type': 'nuke'}).status_code == 422


@pytest.mark.xfail(
    strict=True,
    reason=(
        'api/endpoints.ts sessionReset builds `/sessions/{id}/reset?type=hard` (and the "Hard reset" '
        'button confirms a destructive VM rewind), but the route reads the query param `reset_type`; '
        '`type` is ignored so the default "soft" reset runs instead'
    ),
)
def test_reset_honours_the_query_param_the_frontend_sends(service_client, service_devmode):
    service_devmode.reset_soft.return_value = Result.ok(DevResetResult(True, 'soft', 0.1, 'soft done'))
    service_devmode.reset_hard.return_value = Result.ok(DevResetResult(True, 'hard', 3.0, 'hard done'))

    service_client.post(f'/api/sessions/{SESSION_ID}/reset?type=hard&_t=1730000000000')

    service_devmode.reset_hard.assert_called_once()
    service_devmode.reset_soft.assert_not_called()


def test_reset_failure_is_http_200_envelope(service_client, service_devmode):
    service_devmode.reset_soft.return_value = _fail('RESET_FAILED', 'vm unreachable')

    response = service_client.post(f'/api/sessions/{SESSION_ID}/reset')

    assert response.status_code == 200
    assert response.json()['error']['message'] == 'vm unreachable'


@pytest.mark.xfail(
    strict=True,
    reason=(
        'main.py reset_session calls api.devmode.reset_soft/reset_hard, but the DevModeAPI facade (adare/api.py) '
        'only defines reset_session (which itself calls a non-existent DevModeService.reset_session): '
        'every POST /api/sessions/{id}/reset is an AttributeError -> HTTP 500, so the workbench Soft/Hard '
        'reset buttons can never work. (The CLI `adare dev reset-*` calls the same missing methods.)'
    ),
)
@pytest.mark.parametrize('reset_type', ['soft', 'hard'])
def test_reset_works_through_the_real_facade(real_client, real_service, reset_type):
    _seed_session(real_service, status='running')

    response = TestClient(main.app, raise_server_exceptions=False).post(
        f'/api/sessions/{SESSION_ID}/reset', params={'reset_type': reset_type}
    )

    assert response.status_code == 200


# --- checkpoints ------------------------------------------------------------------------


def test_create_checkpoint_passes_name_and_description_and_broadcasts(client, devmode, ws):
    devmode.create_checkpoint.return_value = Result.ok(True)

    body = client.post(
        f'/api/sessions/{SESSION_ID}/checkpoints', json={'name': 'before-install', 'description': 'clean'}
    ).json()

    assert body['success'] is True
    devmode.create_checkpoint.assert_called_once_with(
        DevCheckpointCreateRequest(session_id=SESSION_ID, name='before-install', description='clean')
    )
    ws.send_checkpoint_created.assert_awaited_once_with(SESSION_ID, 'before-install')


def test_create_checkpoint_description_is_optional(client, devmode):
    """checkpoints-panel.tsx sends ``description: undefined`` (dropped from the JSON) when blank."""
    devmode.create_checkpoint.return_value = Result.ok(True)

    client.post(f'/api/sessions/{SESSION_ID}/checkpoints', json={'name': 'cp'})

    assert devmode.create_checkpoint.call_args.args[0].description == ''


def test_create_checkpoint_failure_does_not_broadcast(client, devmode, ws):
    devmode.create_checkpoint.return_value = _fail('CHECKPOINT_ERROR', 'exists')

    body = client.post(f'/api/sessions/{SESSION_ID}/checkpoints', json={'name': 'cp'}).json()

    assert body['success'] is False
    ws.send_checkpoint_created.assert_not_awaited()


def test_create_checkpoint_requires_name(client, devmode):
    assert client.post(f'/api/sessions/{SESSION_ID}/checkpoints', json={}).status_code == 422


def _seed_checkpoint(service, name='cp1', description='before'):
    service._db_api.save_checkpoint(
        DevCheckpoint(
            session_id=SESSION_ID,
            name=name,
            description=description,
            memory_file_path='',
            disk_file_path='',
            snapshot_name=f'snap-{name}',
            variable_state={'a': 1, 'b': 2},
        )
    )


def test_list_checkpoints_has_the_fields_the_checkpoints_panel_reads(real_client, real_service):
    """checkpoints-panel.tsx reads cp.name, cp.description and cp.created_at for every row."""
    _seed_session(real_service)
    _seed_checkpoint(real_service)

    body = real_client.get(f'/api/sessions/{SESSION_ID}/checkpoints').json()

    assert body['success'] is True
    (cp,) = body['data']
    assert cp['name'] == 'cp1'
    assert cp['description'] == 'before'
    assert isinstance(cp['created_at'], str)
    datetime.fromisoformat(cp['created_at'])
    assert cp['variable_count'] == 2


@pytest.mark.xfail(
    strict=True,
    reason=(
        'checkpoints-panel.tsx prints `{cp.memory_size_mb}MB mem · {cp.disk_size_mb}MB disk` (types/session.ts '
        'CheckpointInfo) but DevCheckpointInfo sends a single file_size_mb, so the row reads '
        '"undefinedMB mem · undefinedMB disk"'
    ),
)
def test_list_checkpoints_sends_memory_and_disk_sizes(real_client, real_service):
    _seed_session(real_service)
    _seed_checkpoint(real_service)

    (cp,) = real_client.get(f'/api/sessions/{SESSION_ID}/checkpoints').json()['data']

    assert 'memory_size_mb' in cp
    assert 'disk_size_mb' in cp


def test_list_checkpoints_empty_is_an_empty_list(real_client, real_service):
    _seed_session(real_service)

    assert real_client.get(f'/api/sessions/{SESSION_ID}/checkpoints').json() == {'success': True, 'data': []}


def test_restore_checkpoint_passes_name(client, devmode):
    devmode.restore_checkpoint.return_value = Result.ok(True)

    body = client.post(f'/api/sessions/{SESSION_ID}/checkpoints/my%20cp/restore').json()

    assert body == {'success': True, 'data': True}
    devmode.restore_checkpoint.assert_called_once_with(DevCheckpointRestoreRequest(session_id=SESSION_ID, name='my cp'))


def test_delete_checkpoint_passes_name(client, devmode):
    devmode.delete_checkpoint.return_value = Result.ok(True)

    body = client.delete(f'/api/sessions/{SESSION_ID}/checkpoints/cp1').json()

    assert body == {'success': True, 'data': True}
    devmode.delete_checkpoint.assert_called_once_with(DevCheckpointDeleteRequest(session_id=SESSION_ID, name='cp1'))


@pytest.mark.parametrize('method', ['post', 'delete'])
def test_restore_and_delete_failures_are_http_200_envelopes(client, devmode, method):
    devmode.restore_checkpoint.return_value = _fail('CHECKPOINT_NOT_FOUND', "Checkpoint 'nope' not found")
    devmode.delete_checkpoint.return_value = _fail('CHECKPOINT_NOT_FOUND', "Checkpoint 'nope' not found")
    url = f'/api/sessions/{SESSION_ID}/checkpoints/nope' + ('/restore' if method == 'post' else '')

    response = getattr(client, method)(url)

    assert response.status_code == 200
    assert response.json()['success'] is False
    assert response.json()['error']['code'] == 'CHECKPOINT_NOT_FOUND'


@pytest.mark.xfail(
    strict=True,
    reason=(
        'create_checkpoint accepts any name, but a name containing "/" can never be restored or deleted: '
        'the path parameter {checkpoint_name} does not match slashes, so the request falls through to the '
        'SPA catch-all (api/endpoints.ts does not encode the name either)'
    ),
)
def test_checkpoint_with_slash_in_name_can_be_restored(client, devmode):
    devmode.restore_checkpoint.return_value = Result.ok(True)

    client.post(f'/api/sessions/{SESSION_ID}/checkpoints/a%2Fb/restore')

    devmode.restore_checkpoint.assert_called_once()


# --- unknown session: every session route answers the same envelope ---------------------

UNKNOWN_SESSION_ROUTES = [
    ('get', '/api/sessions/nope/state', None),
    ('post', '/api/sessions/nope/stop', None),
    ('post', '/api/sessions/nope/actions/execute', {'action_yaml': 'idle:\n  duration: 1\n'}),
    ('post', '/api/sessions/nope/playbooks/execute', {'actions': [{'idle': {'duration': 1}}]}),
    ('post', '/api/sessions/nope/checkpoints', {'name': 'cp'}),
    ('get', '/api/sessions/nope/checkpoints', None),
    ('post', '/api/sessions/nope/checkpoints/cp/restore', None),
    ('delete', '/api/sessions/nope/checkpoints/cp', None),
]


@pytest.mark.parametrize(
    ('method', 'url', 'body'), UNKNOWN_SESSION_ROUTES, ids=[f'{m.upper()} {u}' for m, u, _ in UNKNOWN_SESSION_ROUTES]
)
def test_unknown_session_gets_a_session_not_found_envelope_with_http_200(real_client, ws, method, url, body):
    """Real service + empty DB: not a 404 -- ``{success: false, error: {code: SESSION_NOT_FOUND, ...}}`` / HTTP 200."""
    response = getattr(real_client, method)(url, **({'json': body} if body is not None else {}))

    assert response.status_code == 200
    payload = response.json()
    assert payload['success'] is False
    assert 'data' not in payload
    assert set(payload['error']) == {'code', 'message', 'solutions'}
    assert payload['error']['code'] == 'SESSION_NOT_FOUND'
    assert 'nope' in payload['error']['message']
    assert payload['error']['solutions']
    # nothing is announced for a session that does not exist
    ws.send_session_state.assert_not_awaited()
    ws.send_checkpoint_created.assert_not_awaited()
    ws.send_action_complete.assert_not_awaited()


@pytest.mark.parametrize('reset_type', ['soft', 'hard'])
def test_unknown_session_reset_envelope_when_reaching_the_service(real_service_client, reset_type):
    """Reset on an unknown session (service reached directly; the facade lacks the method, see xfail above)."""
    payload = real_service_client.post('/api/sessions/nope/reset', params={'reset_type': reset_type}).json()

    assert payload['success'] is False
    assert payload['error']['code'] == 'SESSION_NOT_FOUND'
    assert 'nope' in payload['error']['message']
