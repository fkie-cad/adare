"""``/api/experiments`` routes.

Part 1: GET /api/experiments/{name} accepts a short name or a ``Project.experiment``
dotnotation. Links built from run rows (Runs list, Environment page) carry the
dotnotation; the Experiments list links with the short name. Both must resolve.

Part 2 (from "Real service layer" on): every endpoint through FastAPI's TestClient.
The read endpoints run against a real seeded project database (``seeded_projects.py``)
and assert the fields ``experiments-list.tsx`` / ``experiment-detail.tsx`` read; the
mutation endpoints mock ``AdareAPI().experiment`` at its boundary (no VM, libvirt or
network) and assert the request DTO the route builds. Failures are HTTP 200
``{success: false, error: {code, message, solutions}}``. ``xfail(strict=True)`` tests
encode known contract bugs and flip to XPASS (a failure) once fixed.
"""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adare.core.dto.experiment import (
    ExperimentCloneRequest,
    ExperimentCreateRequest,
    ExperimentEnvModifyRequest,
    ExperimentEnvModifyResult,
    ExperimentInfo,
    ExperimentRemoveRequest,
    ExperimentRemoveResult,
    ExperimentValidateRequest,
    ExperimentValidateResult,
    ValidationCheckResult,
)
from adare.core.result import Result
from adare.services.experiment_service import ExperimentRunStartedInfo
from adare.webapi.routes.experiments import get_experiment, router

from .seeded_projects import seeded_fixture  # noqa: F401  (pytest fixture, registered as `seeded`)

pytestmark = pytest.mark.unit

NOT_FOUND = Result.fail(code='ExperimentNotFoundError', message='not found', solutions=[])


def _show(by_dotnotation: Result, by_name: Result) -> MagicMock:
    show = MagicMock()
    show.get_experiment.side_effect = lambda name=None, ulid=None, dotnotation=None: (
        by_dotnotation if dotnotation is not None else by_name
    )
    return show


def _call(name: str, show: MagicMock) -> dict:
    api = MagicMock()
    api.show = show
    with patch('adare.webapi.routes.experiments._api', return_value=api):
        return get_experiment(name)


def test_dotnotation_is_resolved_by_dotnotation():
    show = _show(Result.ok({'name': 'exp'}), NOT_FOUND)
    resp = _call('Proj.exp', show)
    assert resp['success'] is True
    show.get_experiment.assert_called_once_with(dotnotation='Proj.exp')


def test_short_name_is_resolved_by_name():
    show = _show(NOT_FOUND, Result.ok({'name': 'exp'}))
    resp = _call('exp', show)
    assert resp['success'] is True
    show.get_experiment.assert_called_once_with(name='exp')


def test_dotted_short_name_falls_back_to_name_lookup():
    show = _show(NOT_FOUND, Result.ok({'name': 'v1.2'}))
    resp = _call('v1.2', show)
    assert resp['success'] is True
    assert show.get_experiment.call_count == 2


def test_unknown_experiment_reports_not_found():
    resp = _call('Proj.missing', _show(NOT_FOUND, NOT_FOUND))
    assert resp['success'] is False
    assert resp['error']['code'] == 'ExperimentNotFoundError'


# ====================================================================================
# Real service layer: read endpoints against a seeded project database
# ====================================================================================

# What experiments-list.tsx / experiment-detail.tsx / the dialogs read from an experiment.
FRONTEND_EXPERIMENT_FIELDS = {'ulid', 'name', 'project', 'dotnotation', 'tags', 'description'}


@pytest.fixture
def client(seeded):
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _assert_failure_envelope(body: dict, code: str) -> None:
    assert body['success'] is False
    assert body['error']['code'] == code
    assert isinstance(body['error']['message'], str)
    assert isinstance(body['error']['solutions'], list)
    assert 'data' not in body


def _list(client: TestClient, query: str = '') -> dict[str, dict]:
    """Experiment rows keyed by dotnotation."""
    body = client.get(f'/api/experiments{query}').json()
    assert body['success'] is True
    return {row['dotnotation']: row for row in body['data']}


# ------------------------------------------------------------- GET /api/experiments


def test_list_experiments_spans_every_project(client):
    assert set(_list(client)) == {'Alpha.exp', 'Alpha.other', 'Beta.exp'}


def test_list_experiments_row_carries_the_fields_the_frontend_reads(client, seeded):
    row = _list(client)['Alpha.exp']

    assert set(row) >= FRONTEND_EXPERIMENT_FIELDS
    assert row['ulid'] == seeded.exp_id
    assert row['name'] == 'exp'
    assert row['project'] == 'Alpha'
    assert row['description'] == 'exp description'
    assert row['tags'] == ['forensics']


def test_list_experiments_environment_names_are_what_the_table_renders(client, seeded):
    """experiments-list.tsx renders ``exp.environment_names`` and links each to /environments/$name."""
    row = _list(client)['Alpha.exp']

    assert row['environment_names'] == ['ubuntu-env']
    assert row['environment_ids'] == [seeded.env_id]
    assert row['environments'] == ['ubuntu-env']
    assert row['environment'] == 'ubuntu-env'


def test_list_experiments_tags_filter_with_an_unknown_tag_is_empty(client):
    assert client.get('/api/experiments?tags=no-such-tag').json() == {'success': True, 'data': []}


def test_list_experiments_tags_filter_returns_the_tagged_experiment(client):
    assert set(_list(client, '?tags=forensics')) == {'Alpha.exp'}


def test_list_experiments_run_count_and_last_run_reflect_the_runs(client):
    rows = _list(client)

    assert rows['Alpha.exp']['run_count'] == 1
    assert rows['Alpha.exp']['last_run'] == '2026-01-02T03:04:05'
    assert rows['Alpha.other']['run_count'] == 0


def test_list_experiments_row_exposes_the_project_path_mutations_need(client, seeded):
    row = _list(client)['Alpha.exp']

    project_path = row.get('project_path') or row['project']  # experiments-list.tsx projectPathOf()
    assert Path(project_path) == seeded.alpha


def test_list_experiments_tags_filter_needs_every_requested_tag(client):
    assert set(_list(client, '?tags=forensics,forensics')) == {'Alpha.exp'}
    assert _list(client, '?tags=forensics,no-such-tag') == {}


def test_list_experiments_tags_filter_ignores_empty_entries(client):
    assert set(_list(client, '?tags=forensics,')) == {'Alpha.exp'}


def test_list_experiments_run_count_is_per_experiment_across_projects(client):
    rows = _list(client)

    assert rows['Beta.exp']['run_count'] == 1
    assert rows['Beta.exp']['last_run'] == '2026-01-02T03:04:05'
    assert rows['Alpha.other']['last_run'] is None


def test_list_experiments_project_path_is_the_experiments_own_project(client, seeded):
    rows = _list(client)

    assert Path(rows['Alpha.other']['project_path']) == seeded.alpha
    assert Path(rows['Beta.exp']['project_path']) == seeded.beta


def test_list_experiments_database_failure_is_reported_in_the_envelope(client):
    with patch(
        'adare.services.show_service.ShowService._query_across_projects', side_effect=OSError('disk unavailable')
    ):
        response = client.get('/api/experiments')

    assert response.status_code == 200
    _assert_failure_envelope(response.json(), 'ExperimentListError')


# -------------------------------------------------------- GET /api/experiments/{name}


def test_get_experiment_by_dotnotation_picks_the_right_project(client, seeded):
    alpha = client.get('/api/experiments/Alpha.exp').json()['data']
    beta = client.get('/api/experiments/Beta.exp').json()['data']

    assert (alpha['ulid'], alpha['project']) == (seeded.exp_id, 'Alpha')
    assert (beta['ulid'], beta['project']) == (seeded.beta_exp_id, 'Beta')


def test_get_experiment_by_unique_short_name(client, seeded):
    body = client.get('/api/experiments/other').json()

    assert body['success'] is True
    assert body['data']['ulid'] == seeded.other_exp_id
    assert body['data']['dotnotation'] == 'Alpha.other'


def test_get_experiment_detail_carries_the_fields_the_page_reads(client, seeded):
    """experiment-detail.tsx reads name, project, tags and ``environments`` (the detail payload)."""
    data = client.get('/api/experiments/Alpha.exp').json()['data']

    assert set(data) >= FRONTEND_EXPERIMENT_FIELDS
    assert data['name'] == 'exp'
    assert data['project'] == 'Alpha'
    assert data['tags'] == ['forensics']
    # The page reads environment_names ?? environments; the detail payload sends `environments`.
    assert data['environments'] == ['ubuntu-env']
    names = data.get('environment_names') or data['environments']
    assert names == ['ubuntu-env']


def test_get_experiment_detail_agrees_with_its_list_row(client):
    row = _list(client)['Alpha.exp']
    detail = client.get('/api/experiments/Alpha.exp').json()['data']

    for key in ('ulid', 'name', 'display_name', 'dotnotation', 'project', 'environments', 'tags', 'description'):
        assert detail[key] == row[key], key


def test_every_list_row_opens_itself_through_its_dotnotation(client):
    """experiments-list.tsx links each row by dotnotation: short names repeat across projects."""
    for row in _list(client).values():
        opened = client.get(f'/api/experiments/{row["dotnotation"]}').json()['data']

        assert opened['ulid'] == row['ulid']


def test_get_experiment_not_found_is_reported_in_the_envelope(client):
    for name in ('missing', 'Alpha.missing'):
        response = client.get(f'/api/experiments/{name}')

        assert response.status_code == 200
        _assert_failure_envelope(response.json(), 'ExperimentNotFoundError')
        assert name in response.json()['error']['message']
        assert response.json()['error']['solutions']


def test_get_experiment_detail_run_count_reflects_the_runs(client):
    assert client.get('/api/experiments/Alpha.exp').json()['data']['run_count'] == 1


def test_get_experiment_detail_exposes_the_project_path_run_and_link_need(client, seeded):
    data = client.get('/api/experiments/Alpha.exp').json()['data']

    assert Path(data.get('project_path') or data['project']) == seeded.alpha


# ====================================================================================
# Mutation endpoints: AdareAPI().experiment mocked at its boundary
# ====================================================================================


def _mock_api(**methods) -> MagicMock:
    api = MagicMock()
    for name, result in methods.items():
        getattr(api.experiment, name).return_value = result
    return api


def _request(client: TestClient, api: MagicMock, method: str, url: str, **kwargs):
    with patch('adare.webapi.routes.experiments._api', return_value=api):
        response = client.request(method, url, **kwargs)
    assert response.status_code == 200
    return response.json()


def _info(name: str, **overrides) -> ExperimentInfo:
    fields = dict(
        id='',
        name=name,
        description='',
        file_path=Path('/p/experiments') / name,
        sha256='',
        environment_names=[],
    )
    return ExperimentInfo(**{**fields, **overrides})


FAIL = Result.fail(code='SomethingFailed', message='nope', solutions=['try again'])
FAIL_BODY = {'success': False, 'error': {'code': 'SomethingFailed', 'message': 'nope', 'solutions': ['try again']}}


def test_create_experiment_builds_the_request_and_returns_the_experiment(client):
    api = _mock_api(create=Result.ok(_info('new')))

    body = _request(client, api, 'POST', '/api/experiments', json={'project_path': '/p', 'name': 'new'})

    api.experiment.create.assert_called_once_with(ExperimentCreateRequest(project_path=Path('/p'), name='new'))
    assert body['success'] is True
    assert body['data']['name'] == 'new'  # useCreateExperiment returns data.data as an Experiment
    assert body['data']['file_path'] == '/p/experiments/new'


def test_create_experiment_failure_is_reported_in_the_envelope(client):
    assert (
        _request(client, _mock_api(create=FAIL), 'POST', '/api/experiments', json={'project_path': '/p', 'name': 'x'})
        == FAIL_BODY
    )


@pytest.mark.parametrize('payload', [{}, {'project_path': '/p'}, {'name': 'x'}])
def test_create_experiment_requires_project_path_and_name(client, payload):
    assert client.post('/api/experiments', json=payload).status_code == 422


def test_run_experiment_returns_the_run_ulid_the_dialog_navigates_to(client):
    api = MagicMock()
    api.experiment.run = AsyncMock(
        return_value=Result.ok(ExperimentRunStartedInfo(run_ulid='01RUN', experiment_name='exp'))
    )

    body = _request(
        client, api, 'POST', '/api/experiments/exp/run', json={'project_path': '/p', 'environment_name': 'ubuntu-env'}
    )

    api.experiment.run.assert_awaited_once_with(Path('/p'), 'exp', 'ubuntu-env')
    # experiment-detail.tsx reads data.run_ulid and data.experiment_name
    assert body == {'success': True, 'data': {'run_ulid': '01RUN', 'experiment_name': 'exp'}}


def test_run_experiment_failure_is_reported_in_the_envelope(client):
    api = MagicMock()
    api.experiment.run = AsyncMock(return_value=FAIL)

    body = _request(
        client, api, 'POST', '/api/experiments/exp/run', json={'project_path': '/p', 'environment_name': 'e'}
    )

    assert body == FAIL_BODY


def test_run_experiment_requires_an_environment(client):
    assert client.post('/api/experiments/exp/run', json={'project_path': '/p'}).status_code == 422


def test_clone_experiment_builds_the_request(client):
    api = _mock_api(clone=Result.ok(_info('copy', environment_names=['ubuntu-env'])))

    body = _request(
        client,
        api,
        'POST',
        '/api/experiments/exp/clone',
        json={'project_path': '/p', 'target_experiment': 'copy', 'environments': ['ubuntu-env']},
    )

    api.experiment.clone.assert_called_once_with(
        ExperimentCloneRequest(
            project_path=Path('/p'),
            source_experiment='exp',
            target_experiment='copy',
            environments=['ubuntu-env'],
        )
    )
    assert body['success'] is True
    assert body['data']['name'] == 'copy'
    assert body['data']['environment_names'] == ['ubuntu-env']


def test_clone_experiment_environments_are_optional(client):
    api = _mock_api(clone=Result.ok(_info('copy')))

    _request(
        client, api, 'POST', '/api/experiments/exp/clone', json={'project_path': '/p', 'target_experiment': 'copy'}
    )

    assert api.experiment.clone.call_args.args[0].environments is None


def test_clone_experiment_failure_is_reported_in_the_envelope(client):
    body = _request(
        client,
        _mock_api(clone=FAIL),
        'POST',
        '/api/experiments/exp/clone',
        json={'project_path': '/p', 'target_experiment': 'c'},
    )

    assert body == FAIL_BODY


def test_remove_experiment_takes_its_options_from_the_delete_body(client):
    """useRemoveExperiment sends the options as a JSON body on DELETE /experiments/{name}."""
    api = _mock_api(
        remove=Result.ok(ExperimentRemoveResult(removed_from_db=True, files_deleted=False, experiment_name='exp'))
    )

    body = _request(
        client,
        api,
        'DELETE',
        '/api/experiments/exp',
        json={'project_path': '/p', 'force': True, 'keep_files': True},
    )

    api.experiment.remove.assert_called_once_with(
        ExperimentRemoveRequest(project_path=Path('/p'), name='exp', force=True, keep_files=True)
    )
    assert body == {
        'success': True,
        'data': {'removed_from_db': True, 'files_deleted': False, 'experiment_name': 'exp'},
    }


def test_remove_experiment_flags_default_to_false(client):
    api = _mock_api(
        remove=Result.ok(ExperimentRemoveResult(removed_from_db=True, files_deleted=True, experiment_name='exp'))
    )

    _request(client, api, 'DELETE', '/api/experiments/exp', json={'project_path': '/p'})

    request = api.experiment.remove.call_args.args[0]
    assert (request.force, request.keep_files) == (False, False)


def test_remove_experiment_failure_is_reported_in_the_envelope(client):
    assert (
        _request(client, _mock_api(remove=FAIL), 'DELETE', '/api/experiments/exp', json={'project_path': '/p'})
        == FAIL_BODY
    )


def test_remove_experiment_without_a_body_is_rejected(client):
    assert client.delete('/api/experiments/exp').status_code == 422


def test_validate_experiment_builds_the_request_and_returns_the_checks(client):
    checks = [
        ValidationCheckResult(name='playbook', passed=True, message='ok'),
        ValidationCheckResult(name='tests', passed=False, message='missing test'),
    ]
    api = _mock_api(validate=Result.ok(ExperimentValidateResult(name='exp', checks=checks)))

    body = _request(
        client,
        api,
        'POST',
        '/api/experiments/exp/validate',
        json={'project_path': '/p', 'environment': 'ubuntu-env'},
    )

    api.experiment.validate.assert_called_once_with(
        ExperimentValidateRequest(project_path=Path('/p'), name='exp', environment='ubuntu-env')
    )
    assert body['success'] is True
    assert body['data']['name'] == 'exp'
    assert [(c['name'], c['passed'], c['message']) for c in body['data']['checks']] == [
        ('playbook', True, 'ok'),
        ('tests', False, 'missing test'),
    ]


def test_validate_experiment_environment_is_optional(client):
    api = _mock_api(validate=Result.ok(ExperimentValidateResult(name='exp')))

    _request(client, api, 'POST', '/api/experiments/exp/validate', json={'project_path': '/p'})

    assert api.experiment.validate.call_args.args[0].environment is None


def test_validate_experiment_payload_carries_a_verdict_for_failed_checks(client):
    failing = ExperimentValidateResult(
        name='exp', checks=[ValidationCheckResult(name='tests', passed=False, message='missing test')]
    )

    body = _request(
        client,
        _mock_api(validate=Result.ok(failing)),
        'POST',
        '/api/experiments/exp/validate',
        json={'project_path': '/p'},
    )

    assert body['data']['is_valid'] is False


def test_validate_experiment_payload_verdict_for_passing_and_warning_checks(client):
    ok = ExperimentValidateResult(
        name='exp',
        checks=[
            ValidationCheckResult(name='playbook', passed=True, message='ok'),
            ValidationCheckResult(name='style', passed=False, message='meh', is_warning=True),
        ],
    )

    data = _request(
        client, _mock_api(validate=Result.ok(ok)), 'POST', '/api/experiments/exp/validate', json={'project_path': '/p'}
    )['data']

    assert (data['is_valid'], data['failed_count'], data['passed_count'], data['warning_count']) == (True, 0, 1, 1)


def test_validate_experiment_payload_counts_failed_checks(client):
    failing = ExperimentValidateResult(
        name='exp', checks=[ValidationCheckResult(name='tests', passed=False, message='missing test')]
    )

    data = _request(
        client,
        _mock_api(validate=Result.ok(failing)),
        'POST',
        '/api/experiments/exp/validate',
        json={'project_path': '/p'},
    )['data']

    assert data['failed_count'] == 1


def test_validate_experiment_failure_is_reported_in_the_envelope(client):
    assert (
        _request(client, _mock_api(validate=FAIL), 'POST', '/api/experiments/exp/validate', json={'project_path': '/p'})
        == FAIL_BODY
    )


def test_add_environments_builds_the_request(client):
    result = ExperimentEnvModifyResult(affected_experiments=['exp'], environments_changed=['e1', 'e2'], operation='add')
    api = _mock_api(add_environments=Result.ok(result))

    body = _request(
        client,
        api,
        'POST',
        '/api/experiments/exp/environments',
        json={'project_path': '/p', 'environments': ['e1', 'e2'], 'force': True},
    )

    api.experiment.add_environments.assert_called_once_with(
        ExperimentEnvModifyRequest(
            project_path=Path('/p'), experiment_pattern='exp', environments=['e1', 'e2'], force=True
        )
    )
    assert body == {
        'success': True,
        'data': {'affected_experiments': ['exp'], 'environments_changed': ['e1', 'e2'], 'operation': 'add'},
    }


def test_add_environments_force_defaults_to_false(client):
    api = _mock_api(add_environments=Result.ok(ExperimentEnvModifyResult([], ['e1'], 'add')))

    _request(
        client, api, 'POST', '/api/experiments/exp/environments', json={'project_path': '/p', 'environments': ['e1']}
    )

    assert api.experiment.add_environments.call_args.args[0].force is False


def test_add_environments_failure_is_reported_in_the_envelope(client):
    body = _request(
        client,
        _mock_api(add_environments=FAIL),
        'POST',
        '/api/experiments/exp/environments',
        json={'project_path': '/p', 'environments': ['e1']},
    )

    assert body == FAIL_BODY


def test_remove_environments_takes_its_request_from_the_delete_body(client):
    """useRemoveExperimentEnvironments sends the same body as the add call, on DELETE."""
    result = ExperimentEnvModifyResult(affected_experiments=['exp'], environments_changed=['e1'], operation='remove')
    api = _mock_api(remove_environments=Result.ok(result))

    body = _request(
        client,
        api,
        'DELETE',
        '/api/experiments/exp/environments',
        json={'project_path': '/p', 'environments': ['e1'], 'force': True},
    )

    api.experiment.remove_environments.assert_called_once_with(
        ExperimentEnvModifyRequest(project_path=Path('/p'), experiment_pattern='exp', environments=['e1'], force=True)
    )
    api.experiment.add_environments.assert_not_called()
    assert body['data']['operation'] == 'remove'


def test_remove_environments_failure_is_reported_in_the_envelope(client):
    body = _request(
        client,
        _mock_api(remove_environments=FAIL),
        'DELETE',
        '/api/experiments/exp/environments',
        json={'project_path': '/p', 'environments': ['e1']},
    )

    assert body == FAIL_BODY


def test_environment_routes_require_the_environment_list(client):
    assert client.post('/api/experiments/exp/environments', json={'project_path': '/p'}).status_code == 422
    assert client.request('DELETE', '/api/experiments/exp/environments', json={'project_path': '/p'}).status_code == 422
