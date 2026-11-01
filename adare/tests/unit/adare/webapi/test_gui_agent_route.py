"""``/api/sessions/{id}/agent/run`` and ``/agent/steps/{index}.png``.

Consumers: ``adare-web/src/api/hooks/use-gui-agent.ts`` (reads ``data.started``),
``components/workbench/run-agent-panel.tsx`` (reduces ``agent_step`` /
``agent_status`` websocket frames and loads ``/api/sessions/{id}/agent/steps/{index}.png``
into an ``<img>``), and the frame types in ``adare-web/src/types/api.ts``.

The agent itself drives a VM with a vision LLM, so ``run_gui_agent`` (the service
boundary) is replaced by a plain function that feeds the real progress ``sink`` the
way ``GuiAgent`` does. Everything else is real: the route, the sink, the
``DevGuiAgentRequest`` it builds, and ``ws_manager`` (a fake websocket client is
connected to it, so the asserted frames are exactly what the browser would receive).
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adare.core.dto.devmode import DevGuiAgentRequest, DevGuiAgentResult
from adare.core.result import Result
from adare.webapi.routes import gui_agent
from adare.webapi.routes.gui_agent import _step_frame, router
from adare.webapi.websocket_manager import ws_manager

pytestmark = pytest.mark.unit

PNG = b'\x89PNG\r\n\x1a\n' + b'fake-png-body'

# `AgentStepMessage['data']` in adare-web/src/types/api.ts: every key the reducer reads.
FRONTEND_STEP_KEYS = {
    'phase',
    'index',
    'kind',
    'describe',
    'reasoning',
    'coords',
    'grounded',
    'status',
    'screenshot',
}


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def app():
    application = FastAPI()
    application.include_router(router)
    return application


@pytest.fixture(autouse=True)
def _isolated_run_dirs():
    """`_RUN_DIRS` is module state shared across sessions: snapshot and restore it."""
    saved = dict(gui_agent._RUN_DIRS)
    gui_agent._RUN_DIRS.clear()
    yield
    gui_agent._RUN_DIRS.clear()
    gui_agent._RUN_DIRS.update(saved)


class _FakeBrowser:
    """A connected websocket client: records every frame ``ws_manager`` pushes to it."""

    def __init__(self):
        self.accept = AsyncMock()
        self.send_json = AsyncMock()

    @property
    def frames(self) -> list[dict]:
        return [call.args[0] for call in self.send_json.await_args_list]


@pytest.fixture
def session_id(request):
    return f'sess-{request.node.name[:40]}'


def _event_loop_client(app):
    """Async client on the *test's* loop, so the route's background task is observable."""
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test')


def _agent_result(**overrides) -> Result:
    fields = {'success': True, 'reason': 'goal achieved', 'steps': 2, 'summary': 'Opened Writer'}
    fields.update(overrides)
    return Result.ok(DevGuiAgentResult(**fields))


def _fake_api(run_gui_agent) -> MagicMock:
    api = MagicMock()
    api.devmode.run_gui_agent = run_gui_agent
    return api


async def _wait_until(predicate, timeout=5.0):
    """Poll on the loop until ``predicate()``; fail loudly instead of hanging the suite."""

    async def _poll():
        while not predicate():
            await asyncio.sleep(0.005)

    await asyncio.wait_for(_poll(), timeout)


async def _run(app, session_id, run_gui_agent, body=None, *, until_frames):
    """POST agent/run with ``run_gui_agent`` standing in for the service; wait for the frames."""
    browser = _FakeBrowser()
    await ws_manager.connect(browser, session_id)
    try:
        with patch('adare.api.AdareAPI', return_value=_fake_api(run_gui_agent)):
            async with _event_loop_client(app) as http:
                response = await http.post(
                    f'/api/sessions/{session_id}/agent/run', json=body or {'goal': 'open writer'}
                )
            await _wait_until(lambda: len(browser.frames) >= until_frames)
        return response, browser
    finally:
        await ws_manager.disconnect(browser, session_id)


# ---------------------------------------------------------------------------
# _step_frame: progress event -> `agent_step` payload
# ---------------------------------------------------------------------------


def test_step_frame_has_exactly_the_keys_the_frontend_reducer_reads():
    frame = _step_frame(
        {
            'type': 'decided',
            'index': 3,
            'kind': 'click',
            'describe': 'Click File menu',
            'coords': (10, 20),
            'grounded': True,
            'reasoning': 'need the menu',
        }
    )
    assert set(frame) == FRONTEND_STEP_KEYS
    assert frame['phase'] == 'decided'
    assert frame['index'] == 3
    assert frame['coords'] == [10, 20]  # a JSON array (TS: [number, number]), not a tuple
    assert frame['grounded'] is True


def test_step_frame_for_an_executed_event_carries_status_and_the_screenshot_name():
    frame = _step_frame({'type': 'executed', 'index': 3, 'status': 'success', 'screenshot': 'step_003.png'})
    assert set(frame) == FRONTEND_STEP_KEYS
    assert frame['phase'] == 'executed'
    assert frame['status'] == 'success'
    assert frame['screenshot'] == 'step_003.png'
    assert frame['coords'] is None
    # The reducer merges with `d.kind || existing.kind`: absent text must be null/empty, never missing.
    assert frame['kind'] is None


@pytest.mark.parametrize('phase', ['pause', 'resume'])
def test_step_frame_forwards_pause_and_resume_for_the_reducer_to_ignore(phase):
    frame = _step_frame({'type': phase})
    assert frame['phase'] == phase


@pytest.mark.parametrize('event', [{'type': 'run_dir', 'path': '/x'}, {'type': 'mystery'}, {}])
def test_step_frame_drops_non_loop_events(event):
    assert _step_frame(event) is None


# ---------------------------------------------------------------------------
# POST /api/sessions/{id}/agent/run
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_answers_started_true_without_the_result_envelope(app, session_id):
    """use-gui-agent.ts returns `data` as-is and reads `.started`: no `{success, data}` wrapper."""

    def agent(dto, sink):
        return _agent_result()

    response, _ = await _run(app, session_id, agent, until_frames=2)

    assert response.status_code == 200
    assert response.json() == {'started': True}


@pytest.mark.asyncio
async def test_run_builds_a_non_interactive_headless_request_from_the_body(app, session_id):
    seen = []

    def agent(dto, sink):
        seen.append(dto)
        return _agent_result()

    await _run(
        app,
        session_id,
        agent,
        body={
            'goal': 'save the file',
            'max_steps': 7,
            'stall_limit': 3,
            'planning': True,
            'grounding': False,
            'video': True,
        },
        until_frames=2,
    )

    (dto,) = seen
    assert isinstance(dto, DevGuiAgentRequest)
    assert dto.session_id == session_id  # the path id, not something from the body
    assert dto.goal == 'save the file'
    assert (dto.max_steps, dto.stall_limit) == (7, 3)
    assert (dto.planning, dto.grounding, dto.video) == (True, False, True)
    assert dto.interactive is False, 'no stdin gate inside the server'
    assert dto.progress is False, 'no rich Live display headless'


@pytest.mark.asyncio
async def test_run_leaves_optional_settings_unset_so_config_defaults_apply(app, session_id):
    seen = []

    def agent(dto, sink):
        seen.append(dto)
        return _agent_result()

    await _run(app, session_id, agent, until_frames=2)

    (dto,) = seen
    assert (dto.max_steps, dto.stall_limit, dto.planning, dto.grounding, dto.video) == (None,) * 5


@pytest.mark.asyncio
async def test_run_streams_running_then_steps_then_finished_in_the_frames_the_panel_reads(app, session_id):
    def agent(dto, sink):
        sink({'type': 'decided', 'index': 0, 'kind': 'click', 'describe': 'Click Start', 'coords': (5, 6)})
        sink({'type': 'executed', 'index': 0, 'status': 'success', 'screenshot': 'step_000.png'})
        return _agent_result(summary='All done')

    _, browser = await _run(app, session_id, agent, until_frames=4)

    frames = browser.frames
    assert [f['type'] for f in frames] == ['agent_status', 'agent_step', 'agent_step', 'agent_status']
    assert all(f['session_id'] == session_id for f in frames)

    # AgentStatusMessage: data.state + data.summary
    assert frames[0]['data'] == {'state': 'running', 'summary': ''}
    assert frames[-1]['data'] == {'state': 'finished', 'summary': 'All done'}

    # AgentStepMessage: data has every key, and index is the one the image URL is built from
    decided, executed = frames[1]['data'], frames[2]['data']
    assert set(decided) == set(executed) == FRONTEND_STEP_KEYS
    assert (decided['phase'], decided['index'], decided['coords']) == ('decided', 0, [5, 6])
    assert (executed['phase'], executed['index'], executed['screenshot']) == ('executed', 0, 'step_000.png')
    json.dumps(frames)  # everything on the wire is plain JSON


@pytest.mark.asyncio
async def test_run_skips_internal_and_unknown_events_and_survives_a_malformed_one(app, session_id, tmp_path):
    def agent(dto, sink):
        sink({'type': 'run_dir', 'path': str(tmp_path)})
        sink({'type': 'run_dir'})  # malformed: no 'path' -> KeyError inside the sink, must be swallowed
        sink({'type': 'telemetry', 'index': 1})
        sink({'type': 'executed', 'index': 1, 'status': 'success'})
        return _agent_result()

    _, browser = await _run(app, session_id, agent, until_frames=3)

    assert [f['type'] for f in browser.frames] == ['agent_status', 'agent_step', 'agent_status']
    assert browser.frames[-1]['data']['state'] == 'finished', 'a bad event must not abort the run'


@pytest.mark.asyncio
async def test_run_reports_an_unsuccessful_agent_as_failed_with_its_summary(app, session_id):
    def agent(dto, sink):
        return _agent_result(success=False, reason='stalled', summary='Gave up at the login dialog')

    _, browser = await _run(app, session_id, agent, until_frames=2)

    assert browser.frames[-1]['data'] == {'state': 'failed', 'summary': 'Gave up at the login dialog'}


@pytest.mark.asyncio
async def test_run_falls_back_to_the_reason_when_the_agent_gave_no_summary(app, session_id):
    def agent(dto, sink):
        return _agent_result(success=False, reason='step budget exhausted', summary='')

    _, browser = await _run(app, session_id, agent, until_frames=2)

    assert browser.frames[-1]['data'] == {'state': 'failed', 'summary': 'step budget exhausted'}


@pytest.mark.asyncio
async def test_run_reports_a_service_error_result_as_failed_with_the_error_message(app, session_id):
    """An unknown/stopped session is a Result.fail inside the run: the HTTP call is still `started`."""

    def agent(dto, sink):
        return Result.fail('SESSION_NOT_FOUND', f"Dev session '{dto.session_id}' not found", ['adare dev list'])

    response, browser = await _run(app, session_id, agent, until_frames=2)

    assert response.json() == {'started': True}
    assert browser.frames[-1]['type'] == 'agent_status'
    assert browser.frames[-1]['data']['state'] == 'failed'
    assert session_id in browser.frames[-1]['data']['summary']


@pytest.mark.asyncio
async def test_run_reports_a_crashing_run_as_failed_instead_of_leaving_the_panel_running(app, session_id):
    def agent(dto, sink):
        raise RuntimeError('qmp socket closed')

    _, browser = await _run(app, session_id, agent, until_frames=2)

    assert browser.frames[0]['data']['state'] == 'running'
    assert browser.frames[-1]['data'] == {'state': 'failed', 'summary': 'qmp socket closed'}


@pytest.mark.asyncio
async def test_run_runs_the_agent_off_the_event_loop(app, session_id):
    """`run_gui_agent` calls asyncio.run internally; on the server loop it would raise."""
    seen = {}

    def agent(dto, sink):
        try:
            asyncio.get_running_loop()
            seen['on_loop'] = True
        except RuntimeError:
            seen['on_loop'] = False
        return _agent_result()

    await _run(app, session_id, agent, until_frames=2)

    assert seen == {'on_loop': False}


@pytest.mark.asyncio
async def test_run_frames_only_reach_the_session_that_started_the_run(app, session_id):
    other = _FakeBrowser()
    await ws_manager.connect(other, 'someone-elses-session')
    try:

        def agent(dto, sink):
            sink({'type': 'executed', 'index': 0, 'status': 'success'})
            return _agent_result()

        _, mine = await _run(app, session_id, agent, until_frames=3)

        assert other.send_json.await_count == 0
        assert len(mine.frames) == 3
    finally:
        await ws_manager.disconnect(other, 'someone-elses-session')


def test_run_rejects_a_body_without_a_goal(app):
    with patch('adare.api.AdareAPI') as api:
        response = TestClient(app).post('/api/sessions/s1/agent/run', json={'max_steps': 3})
    assert response.status_code == 422
    api.assert_not_called()


@pytest.mark.parametrize('field', ['max_steps', 'stall_limit'])
def test_run_rejects_non_integer_limits(app, field):
    with patch('adare.api.AdareAPI') as api:
        response = TestClient(app).post('/api/sessions/s1/agent/run', json={'goal': 'x', field: 'lots'})
    assert response.status_code == 422
    api.assert_not_called()


# ---------------------------------------------------------------------------
# GET /api/sessions/{id}/agent/steps/{index}.png
# ---------------------------------------------------------------------------


@pytest.fixture
def run_dir(tmp_path):
    """A run directory shaped like the agent's: ``<run>/steps/step_NNN.png`` + a secret outside it."""
    root = tmp_path / 'agent_run'
    steps = root / 'steps'
    steps.mkdir(parents=True)
    (steps / 'step_000.png').write_bytes(PNG + b'-0')
    (steps / 'step_003.png').write_bytes(PNG + b'-3')
    (tmp_path / 'secret.png').write_bytes(b'TOP-SECRET')
    (root / 'step_001.png').write_bytes(b'TOP-SECRET')  # right name, wrong directory
    return root


@pytest.fixture
def known_session(run_dir):
    gui_agent._RUN_DIRS['s1'] = run_dir
    return 's1'


def _get(app, path):
    return TestClient(app).get(path)


def test_step_image_is_served_as_png(app, known_session):
    response = _get(app, '/api/sessions/s1/agent/steps/3.png')

    assert response.status_code == 200
    assert response.headers['content-type'] == 'image/png'
    assert response.content == PNG + b'-3'


def test_step_image_index_is_zero_padded_to_the_agents_file_names(app, known_session):
    """The frontend uses the event's integer `index`; the agent writes `step_{index:03d}.png`."""
    response = _get(app, '/api/sessions/s1/agent/steps/0.png')
    assert response.status_code == 200
    assert response.content == PNG + b'-0'


def test_step_image_missing_index_is_404(app, known_session):
    response = _get(app, '/api/sessions/s1/agent/steps/2.png')
    assert response.status_code == 404
    assert response.json()['detail'] == 'screenshot not available yet'


def test_step_image_for_a_session_with_no_run_is_404(app):
    response = _get(app, '/api/sessions/never-ran/agent/steps/0.png')
    assert response.status_code == 404
    assert 'no known agent run' in response.json()['detail']


def test_step_image_404_when_the_run_has_no_steps_directory(app, tmp_path):
    gui_agent._RUN_DIRS['s1'] = tmp_path / 'no-such-run'
    assert _get(app, '/api/sessions/s1/agent/steps/0.png').status_code == 404


def test_step_image_never_serves_a_neighbouring_runs_screenshot(app, run_dir):
    other = run_dir.parent / 'other_run'
    (other / 'steps').mkdir(parents=True)
    (other / 'steps' / 'step_000.png').write_bytes(b'OTHER-RUN')
    gui_agent._RUN_DIRS['s1'] = run_dir
    gui_agent._RUN_DIRS['s2'] = other

    assert _get(app, '/api/sessions/s1/agent/steps/0.png').content == PNG + b'-0'
    assert _get(app, '/api/sessions/s2/agent/steps/0.png').content == b'OTHER-RUN'


@pytest.mark.parametrize(
    'index',
    [
        '..%2Fsecret',
        '..%2F..%2Fsecret',
        '%2E%2E%2Fsecret',
        '..%5Csecret',
        '..\\secret',
        '../secret',
        '1.5',
        'abc',
        '',
        '0%00',
    ],
)
def test_step_image_index_cannot_be_used_to_escape_the_steps_directory(app, known_session, index):
    response = _get(app, f'/api/sessions/s1/agent/steps/{index}.png')

    assert response.status_code in (404, 422)
    assert b'TOP-SECRET' not in response.content


def test_step_image_negative_index_is_just_a_missing_file(app, known_session):
    response = _get(app, '/api/sessions/s1/agent/steps/-1.png')
    assert response.status_code == 404
    assert b'TOP-SECRET' not in response.content


@pytest.mark.parametrize('sid', ['..', '..%2F..', '%2E%2E%2Fagent_run', '../agent_run'])
def test_step_image_session_id_cannot_be_used_to_reach_a_run_directory(app, known_session, sid):
    """The id is only a dict key into `_RUN_DIRS`, never part of a filesystem path."""
    response = _get(app, f'/api/sessions/{sid}/agent/steps/0.png')

    assert response.status_code == 404
    assert b'TOP-SECRET' not in response.content
    assert response.content != PNG + b'-0'


def test_step_image_symlink_pointing_outside_the_steps_directory_is_not_followed(app, run_dir):
    (run_dir / 'steps' / 'step_007.png').symlink_to(run_dir.parent / 'secret.png')
    gui_agent._RUN_DIRS['s1'] = run_dir

    response = _get(app, '/api/sessions/s1/agent/steps/7.png')

    assert response.status_code == 404
    assert b'TOP-SECRET' not in response.content


def test_step_image_directory_named_like_a_screenshot_is_404_not_a_500(app, run_dir):
    (run_dir / 'steps' / 'step_009.png').mkdir()
    gui_agent._RUN_DIRS['s1'] = run_dir
    assert _get(app, '/api/sessions/s1/agent/steps/9.png').status_code == 404


# ---------------------------------------------------------------------------
# run -> image: the event the panel receives must lead to a servable file
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_screenshot_named_in_an_executed_frame_is_served_at_the_index_url(app, session_id, tmp_path):
    """run-agent-panel.tsx: `<img src=/api/sessions/{id}/agent/steps/{frame.index}.png>`."""
    run = tmp_path / 'run'
    (run / 'steps').mkdir(parents=True)
    (run / 'steps' / 'step_004.png').write_bytes(PNG + b'-live')

    def agent(dto, sink):
        sink({'type': 'run_dir', 'path': str(run)})
        sink({'type': 'executed', 'index': 4, 'status': 'success', 'screenshot': 'step_004.png'})
        return _agent_result()

    _, browser = await _run(app, session_id, agent, until_frames=3)

    executed = next(f['data'] for f in browser.frames if f['type'] == 'agent_step')
    assert gui_agent._RUN_DIRS[session_id] == run
    async with _event_loop_client(app) as http:
        image = await http.get(f'/api/sessions/{session_id}/agent/steps/{executed["index"]}.png')
    assert image.status_code == 200
    assert image.headers['content-type'] == 'image/png'
    assert image.content == PNG + b'-live'
    assert executed['screenshot'] == 'step_004.png'
