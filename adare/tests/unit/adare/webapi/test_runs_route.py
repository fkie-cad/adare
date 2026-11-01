"""``/api/runs`` against a real seeded project database.

The React frontend repeatedly broke by reading ids/fields the backend never sends, so
the read endpoints go through the real ``ShowService`` and SQLite (see
``seeded_projects.py``) and assert the JSON the pages read (``runs-list.tsx``,
``run-detail.tsx``, ``experiment-detail.tsx``). Only the mutation boundary
(``AdareAPI().show.remove_run``) is mocked where a real delete is not the point.

Failures are HTTP 200 ``{success: false, error: {code, message, solutions}}``.
Tests marked ``xfail(strict=True)`` encode known backend/frontend contract bugs: when one
is fixed the test flips to XPASS and fails, forcing the marker to be removed.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adare.core.dto.show import RunRemoveRequest, RunRemoveResult
from adare.core.result import Result
from adare.webapi.routes.experiments import router as experiments_router
from adare.webapi.routes.runs import _classify_artifact, router

from .seeded_projects import seeded_fixture  # noqa: F401  (pytest fixture, registered as `seeded`)

pytestmark = pytest.mark.unit

UNKNOWN_ULID = '01ARZ3NDEKTSV4RRFFQ69G5FAV'

# Every field runs-list.tsx / run-detail.tsx / experiment-detail.tsx read from a run row.
FRONTEND_RUN_FIELDS = {
    'ulid',
    'experiment_name',
    'environment_name',
    'project_name',
    'start_time',
    'end_time',
    'duration_seconds',
    'status',
    'result_status',
    'published',
}


@pytest.fixture
def client(seeded):
    app = FastAPI()
    app.include_router(router)
    app.include_router(experiments_router)
    return TestClient(app)


def _assert_failure_envelope(body: dict, code: str) -> None:
    assert body['success'] is False
    assert body['error']['code'] == code
    assert isinstance(body['error']['message'], str)
    assert isinstance(body['error']['solutions'], list)
    assert 'data' not in body


def _rows_by_ulid(client: TestClient, query: str = '') -> dict[str, dict]:
    body = client.get(f'/api/runs{query}').json()
    assert body['success'] is True
    return {row['ulid']: row for row in body['data']}


# ---------------------------------------------------------------- GET /api/runs


def test_list_runs_row_carries_every_field_the_frontend_reads(client, seeded):
    rows = _rows_by_ulid(client)

    assert set(rows) == {seeded.run_id, seeded.beta_run_id}
    row = rows[seeded.run_id]
    assert set(row) >= FRONTEND_RUN_FIELDS
    assert row['project_name'] == 'Alpha'
    assert row['environment_name'] == 'ubuntu-env'
    assert row['status'] == 'FINISHED'
    assert row['published'] is True
    assert row['fake'] is False
    assert row['duration_seconds'] == 120.0
    assert row['start_time'] == '2026-01-02T03:04:05'
    assert row['end_time'] == '2026-01-02T03:06:05'


def test_list_runs_ids_point_at_the_seeded_experiment_and_environment(client, seeded):
    row = _rows_by_ulid(client)[seeded.run_id]

    assert row['experiment_ulid'] == seeded.exp_id
    assert row['environment_ulid'] == seeded.env_id


def test_list_runs_experiment_name_is_the_project_dotnotation(client, seeded):
    """Run rows carry ``Project.experiment``: the frontend links it to /experiments/$name."""
    rows = _rows_by_ulid(client)

    assert rows[seeded.run_id]['experiment_name'] == 'Alpha.exp'
    assert rows[seeded.beta_run_id]['experiment_name'] == 'Beta.exp'


def test_list_runs_result_status_comes_from_the_test_results(client, seeded):
    """The run has one passing and one failing TestEvent, so its verdict is FAILED."""
    assert _rows_by_ulid(client)[seeded.run_id]['result_status'] == 'FAILED'


@pytest.mark.xfail(
    strict=True,
    reason=(
        'runs-list.tsx and experiment-detail.tsx render run.overall_result, but the backend '
        'sends the verdict as result_status (RunListItem), so the Result column is always "—"'
    ),
)
def test_list_runs_row_has_overall_result_the_tables_render(client, seeded):
    assert _rows_by_ulid(client)[seeded.run_id].get('overall_result') == 'FAILED'


@pytest.mark.xfail(
    strict=True,
    reason=(
        'runs-list.tsx deletes with projectPath = row.project_path, but run rows only carry '
        'project_name, so the delete request never has a project_path'
    ),
)
def test_list_runs_row_has_project_path_the_delete_button_sends(client, seeded):
    assert _rows_by_ulid(client)[seeded.run_id].get('project_path') == str(seeded.alpha)


def test_list_runs_filter_by_project(client, seeded):
    assert set(_rows_by_ulid(client, '?project=Beta')) == {seeded.beta_run_id}
    assert set(_rows_by_ulid(client, '?project=Alpha')) == {seeded.run_id}


def test_list_runs_filter_by_unknown_project_is_an_empty_success(client):
    body = client.get('/api/runs?project=Nope').json()

    assert body == {'success': True, 'data': []}


def test_list_runs_filter_by_experiment_short_name_spans_projects(client, seeded):
    """Short names repeat across projects, which is why the experiment page adds ``project``."""
    assert set(_rows_by_ulid(client, '?experiment=exp')) == {seeded.run_id, seeded.beta_run_id}
    assert _rows_by_ulid(client, '?experiment=other') == {}


def test_list_runs_filter_by_project_and_experiment_as_the_experiment_page_sends_it(client, seeded):
    """experiment-detail.tsx: ``useRuns({project: exp.project, experiment: exp.name})``."""
    exp = client.get('/api/experiments/Beta.exp').json()['data']

    rows = _rows_by_ulid(client, f'?project={exp["project"]}&experiment={exp["name"]}')

    assert set(rows) == {seeded.beta_run_id}
    assert rows[seeded.beta_run_id]['experiment_ulid'] == exp['ulid']


def test_list_runs_filter_by_environment(client, seeded):
    assert set(_rows_by_ulid(client, '?environment=ubuntu-env')) == {seeded.run_id, seeded.beta_run_id}
    assert _rows_by_ulid(client, '?environment=other-env') == {}


def test_list_runs_filters_combine(client, seeded):
    rows = _rows_by_ulid(client, '?project=Alpha&experiment=exp&environment=ubuntu-env')

    assert set(rows) == {seeded.run_id}
    assert _rows_by_ulid(client, '?project=Alpha&experiment=exp&environment=other-env') == {}


def test_list_runs_database_failure_is_reported_in_the_envelope(client):
    with patch(
        'adare.services.show_service.ShowService._query_across_projects', side_effect=OSError('disk unavailable')
    ):
        response = client.get('/api/runs')

    assert response.status_code == 200
    _assert_failure_envelope(response.json(), 'RunListError')
    assert 'disk unavailable' in response.json()['error']['message']


# ------------------------------------------------------------ GET /api/runs/{ulid}


def test_get_run_carries_every_field_the_frontend_reads(client, seeded):
    body = client.get(f'/api/runs/{seeded.run_id}').json()

    assert body['success'] is True
    run = body['data']
    assert set(run) >= FRONTEND_RUN_FIELDS
    assert run['ulid'] == seeded.run_id
    assert run['experiment_name'] == 'Alpha.exp'
    assert run['experiment_ulid'] == seeded.exp_id
    assert run['environment_name'] == 'ubuntu-env'
    assert run['environment_ulid'] == seeded.env_id
    assert run['project_name'] == 'Alpha'
    assert run['status'] == 'FINISHED'
    assert run['result_status'] == 'FAILED'
    assert run['published'] is True
    assert run['duration_seconds'] == 120.0


def test_get_run_is_the_same_run_as_its_list_row(client, seeded):
    row = _rows_by_ulid(client)[seeded.run_id]
    detail = client.get(f'/api/runs/{seeded.run_id}').json()['data']

    assert {key: detail[key] for key in row} == row


def test_get_run_of_another_project_is_found_by_ulid_alone(client, seeded):
    detail = client.get(f'/api/runs/{seeded.beta_run_id}').json()['data']

    assert detail['project_name'] == 'Beta'
    assert detail['experiment_ulid'] == seeded.beta_exp_id


def test_get_run_experiment_link_resolves_to_the_runs_own_experiment(client, seeded):
    """run-detail.tsx links ``run.experiment_name`` (a dotnotation) to /experiments/$name.

    Both runs belong to an experiment called ``exp`` in different projects; following
    each run's link must land on that run's experiment, not the first ``exp`` found.
    """
    for run_id, exp_id in ((seeded.run_id, seeded.exp_id), (seeded.beta_run_id, seeded.beta_exp_id)):
        run = client.get(f'/api/runs/{run_id}').json()['data']
        linked = client.get(f'/api/experiments/{run["experiment_name"]}').json()

        assert linked['success'] is True
        assert linked['data']['ulid'] == exp_id == run['experiment_ulid']


def test_get_run_unknown_ulid_is_reported_in_the_envelope(client):
    response = client.get(f'/api/runs/{UNKNOWN_ULID}')

    assert response.status_code == 200
    _assert_failure_envelope(response.json(), 'RunNotFoundError')
    assert UNKNOWN_ULID in response.json()['error']['message']
    assert response.json()['error']['solutions']


@pytest.mark.xfail(
    strict=True,
    reason=(
        'ShowService.get_run (show_service.py ~L218) builds RunDetail without test_results although the '
        'run has TestEvents with Results, so the Test Results tab always says "No test results"'
    ),
)
def test_get_run_fills_test_results_from_the_runs_test_events(client, seeded):
    run = client.get(f'/api/runs/{seeded.run_id}').json()['data']

    results = run['test_results']
    assert len(results) == 2
    dumped = repr(results)  # run-detail.tsx only JSON-dumps each entry
    assert 'file_exists' in dumped
    assert 'file_hash' in dumped
    assert 'file_hash details' in dumped


@pytest.mark.xfail(
    strict=True,
    reason=(
        'ShowService.get_run never sets os_info / vm_box on RunDetail, so the run page Overview '
        'shows "—" for OS and VM box although the run environment has a Vm with OsInfo'
    ),
)
def test_get_run_fills_os_info_and_vm_box_from_the_runs_environment(client, seeded):
    run = client.get(f'/api/runs/{seeded.run_id}').json()['data']

    assert 'Ubuntu' in run['os_info'] or 'Jammy' in run['os_info']
    assert run['vm_box'] == 'ubuntu-env-disk'


# ------------------------------------------------- GET /api/runs/{ulid}/artifacts


def _write_artifacts(run_dir: Path) -> None:
    (run_dir / 'steps').mkdir(exist_ok=True)
    (run_dir / 'logs').mkdir(exist_ok=True)
    (run_dir / 'steps' / '001.png').write_bytes(b'png-bytes')
    (run_dir / 'run.mp4').write_bytes(b'v' * 10)
    (run_dir / 'report.html').write_text('<html></html>')
    (run_dir / 'logs' / 'adare.log').write_text('log line')
    (run_dir / 'results.json').write_text('{}')


def test_list_run_artifacts_reports_path_kind_and_size_the_page_reads(client, seeded):
    _write_artifacts(seeded.run_dir)

    body = client.get(f'/api/runs/{seeded.run_id}/artifacts').json()

    assert body['success'] is True
    assert body['data'] == [
        {'path': 'logs/adare.log', 'kind': 'log', 'size': 8},
        {'path': 'report.html', 'kind': 'report', 'size': 13},
        {'path': 'results.json', 'kind': 'other', 'size': 2},
        {'path': 'run.mp4', 'kind': 'video', 'size': 10},
        {'path': 'steps/001.png', 'kind': 'screenshot', 'size': 9},
    ]
    # run-detail.tsx's tabs only know these kinds
    assert {a['kind'] for a in body['data']} <= {'screenshot', 'video', 'report', 'log', 'other'}


def test_list_run_artifacts_of_an_empty_run_folder_is_an_empty_list(client, seeded):
    assert client.get(f'/api/runs/{seeded.run_id}/artifacts').json() == {'success': True, 'data': []}


def test_list_run_artifacts_when_the_folder_is_gone_is_an_empty_list(client, seeded):
    import shutil

    shutil.rmtree(seeded.run_dir)

    assert client.get(f'/api/runs/{seeded.run_id}/artifacts').json() == {'success': True, 'data': []}


def test_list_run_artifacts_of_an_unknown_run_is_an_empty_list(client):
    """Current behaviour: an unknown ULID is indistinguishable from a run without artifacts."""
    assert client.get(f'/api/runs/{UNKNOWN_ULID}/artifacts').json() == {'success': True, 'data': []}


@pytest.mark.parametrize(
    ('rel_path', 'kind'),
    [
        ('steps/001.png', 'screenshot'),
        ('steps/001.JPG', 'screenshot'),
        ('steps/sub/002.jpeg', 'screenshot'),
        ('run.mp4', 'video'),
        ('video/session.mp4', 'video'),
        ('report.html', 'report'),
        ('Report-final.pdf', 'report'),
        ('logs/adare.log', 'log'),
        ('adarevm.log', 'log'),
        ('logs/adarevm.txt', 'other'),
        ('results.json', 'other'),
        ('screenshots/001.png', 'other'),
        ('archive.zip', 'other'),
        pytest.param(
            'screenshots/dialog.png',
            'other',
            marks=pytest.mark.xfail(
                strict=True,
                reason='_classify_artifact treats any name containing "log" as a log, so dialog.png lands on the Logs tab',
            ),
        ),
        pytest.param(
            'catalog.json',
            'other',
            marks=pytest.mark.xfail(
                strict=True,
                reason='_classify_artifact treats any name containing "log" as a log, so catalog.json lands on the Logs tab',
            ),
        ),
    ],
)
def test_classify_artifact(rel_path, kind):
    assert _classify_artifact(rel_path) == kind


# ----------------------------------- GET /api/runs/{ulid}/artifacts/{artifact_path}


def test_get_run_artifact_streams_the_file(client, seeded):
    _write_artifacts(seeded.run_dir)

    response = client.get(f'/api/runs/{seeded.run_id}/artifacts/steps/001.png')

    assert response.status_code == 200
    assert response.content == b'png-bytes'
    assert response.headers['content-type'] == 'image/png'


def test_get_run_artifact_path_from_the_listing_is_fetchable(client, seeded):
    """The frontend builds the URL from each listed ``path`` (endpoints.runArtifact)."""
    _write_artifacts(seeded.run_dir)

    for artifact in client.get(f'/api/runs/{seeded.run_id}/artifacts').json()['data']:
        response = client.get(f'/api/runs/{seeded.run_id}/artifacts/{artifact["path"]}')
        assert response.status_code == 200, artifact['path']
        assert len(response.content) == artifact['size']


def test_get_run_artifact_missing_file_is_404(client, seeded):
    assert client.get(f'/api/runs/{seeded.run_id}/artifacts/steps/nope.png').status_code == 404


def test_get_run_artifact_directory_is_404(client, seeded):
    _write_artifacts(seeded.run_dir)

    assert client.get(f'/api/runs/{seeded.run_id}/artifacts/steps').status_code == 404


def test_get_run_artifact_unknown_run_is_404(client):
    assert client.get(f'/api/runs/{UNKNOWN_ULID}/artifacts/steps/001.png').status_code == 404


@pytest.mark.parametrize(
    'url_path',
    [
        '%2e%2e/%2e%2e/%2e%2e/%2e%2e/%2e%2e/etc/passwd',
        '..%2f..%2f..%2f..%2f..%2fetc/passwd',
    ],
)
def test_get_run_artifact_traversal_out_of_the_run_folder_is_404(client, seeded, url_path):
    assert client.get(f'/api/runs/{seeded.run_id}/artifacts/{url_path}').status_code == 404


def test_get_run_artifact_traversal_to_a_parent_file_is_404(client, seeded):
    (seeded.run_dir.parent / 'secret.txt').write_text('SECRET')

    response = client.get(f'/api/runs/{seeded.run_id}/artifacts/%2e%2e/secret.txt')

    assert response.status_code == 404
    assert b'SECRET' not in response.content


@pytest.mark.xfail(
    strict=True,
    reason=(
        'get_run_artifact guards traversal with str(target).startswith(str(run_dir)) and no path separator, '
        'so ../<run_dir name>-x/secret.txt (a sibling folder sharing the name prefix) is served'
    ),
)
def test_get_run_artifact_traversal_to_a_sibling_with_the_same_name_prefix_is_404(client, seeded):
    sibling = seeded.run_dir.parent / f'{seeded.run_dir.name}-evil'
    sibling.mkdir()
    (sibling / 'secret.txt').write_text('SECRET')

    response = client.get(f'/api/runs/{seeded.run_id}/artifacts/%2e%2e/{sibling.name}/secret.txt')

    assert response.status_code == 404
    assert b'SECRET' not in response.content


# ------------------------------------------------------- DELETE /api/runs/{ulid}


def _mocked_show(result: Result) -> tuple[MagicMock, MagicMock]:
    api = MagicMock()
    api.show.remove_run.return_value = result
    return api, api.show.remove_run


def test_remove_run_forwards_ulid_project_path_and_keep_files(client):
    removed = RunRemoveResult(removed=True, ulid=UNKNOWN_ULID, folder='/p/run/exp/x', folder_removed=True)
    api, remove_run = _mocked_show(Result.ok(removed))

    with patch('adare.webapi.routes.runs._api', return_value=api):
        body = client.delete(f'/api/runs/{UNKNOWN_ULID}', params={'project_path': '/p', 'keep_files': 'true'}).json()

    assert remove_run.call_args.args[0] == RunRemoveRequest(ulid=UNKNOWN_ULID, project_path=Path('/p'), keep_files=True)
    assert body['success'] is True
    assert body['data']['removed'] is True
    assert body['data']['folder_removed'] is True


def test_remove_run_defaults_to_deleting_files_without_a_project_path(client):
    api, remove_run = _mocked_show(Result.ok(RunRemoveResult(removed=True, ulid=UNKNOWN_ULID)))

    with patch('adare.webapi.routes.runs._api', return_value=api):
        client.delete(f'/api/runs/{UNKNOWN_ULID}')

    assert remove_run.call_args.args[0] == RunRemoveRequest(ulid=UNKNOWN_ULID, project_path=None, keep_files=False)


def test_remove_run_failure_is_reported_in_the_envelope(client):
    api, _ = _mocked_show(Result.fail(code='RunNotFoundError', message='gone', solutions=['list runs']))

    with patch('adare.webapi.routes.runs._api', return_value=api):
        response = client.delete(f'/api/runs/{UNKNOWN_ULID}')

    assert response.status_code == 200
    assert response.json() == {
        'success': False,
        'error': {'code': 'RunNotFoundError', 'message': 'gone', 'solutions': ['list runs']},
    }


def test_remove_run_with_project_path_deletes_row_and_folder(client, seeded):
    response = client.delete(f'/api/runs/{seeded.run_id}', params={'project_path': str(seeded.alpha)})

    assert response.json()['success'] is True
    assert not seeded.run_dir.exists()
    assert seeded.run_id not in _rows_by_ulid(client)
    assert seeded.beta_run_id in _rows_by_ulid(client)


def test_remove_run_keep_files_keeps_the_folder(client, seeded):
    response = client.delete(
        f'/api/runs/{seeded.run_id}', params={'project_path': str(seeded.alpha), 'keep_files': 'true'}
    )

    assert response.json()['success'] is True
    assert seeded.run_dir.exists()
    assert seeded.run_id not in _rows_by_ulid(client)


def test_remove_run_unknown_ulid_is_reported_in_the_envelope(client, seeded):
    response = client.delete(f'/api/runs/{UNKNOWN_ULID}', params={'project_path': str(seeded.alpha)})

    assert response.status_code == 200
    assert response.json()['success'] is False
    assert response.json()['error']['code']


@pytest.mark.xfail(
    strict=True,
    reason=(
        'runs-list.tsx calls DELETE /api/runs/{ulid} with no project_path (run rows have none) and the server '
        'then looks for a project in its own working directory (NoProjectFoundError), so the UI delete button '
        'fails; useRemoveRun also ignores success:false, so it reports "Run removed" anyway'
    ),
)
def test_remove_run_by_ulid_alone_as_the_frontend_calls_it(client, seeded):
    response = client.delete(f'/api/runs/{seeded.run_id}')

    assert response.json()['success'] is True
    assert seeded.run_id not in _rows_by_ulid(client)
