"""The /api/projects endpoints against the real service layer and a real (temporary) registry.

The React frontend (``adare-web/src/api/hooks/use-projects.ts``, ``pages/projects-list.tsx``) reads
``name``, ``path`` and ``description`` from each project and uses the *path* as the project's id
everywhere else (``project_path`` in other requests, ``GET /projects/{path}``,
``DELETE /projects/{name}?path=``). Mocking the service would hide a field the frontend reads but the
backend never sends, so these tests create projects through the route and read them back.

Failures are HTTP 200 ``{success: false, error: {code, message, solutions}}`` (the frontend's axios
interceptor only sees 4xx/5xx), so the envelope is asserted explicitly.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adare.webapi.routes.projects import router

pytestmark = pytest.mark.unit

# axios adds a cache-busting `_t` query parameter to every request (adare-web/src/api/client.ts)
CACHE_BUSTER = {'_t': '1700000000000'}


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A client whose global project registry lives under ``tmp_path`` (never the shared test home)."""
    import adare.config.database as config_database

    monkeypatch.setattr(config_database, 'STATE_DIR', tmp_path / 'state')
    app = FastAPI()
    app.include_router(router)
    # Unhandled server errors surface as HTTP 500 instead of raising into the test.
    return TestClient(app, raise_server_exceptions=False)


def _create(client, tmp_path, name, description='') -> dict:
    """Create a project through the route and return the ``data`` of the response."""
    body = {'name': name, 'path': str(tmp_path / name)}
    if description:
        body['description'] = description
    response = client.post('/api/projects', json=body)
    assert response.status_code == 200
    payload = response.json()
    assert payload['success'] is True, payload
    return payload['data']


def _assert_failure(payload, code):
    assert payload['success'] is False
    assert 'data' not in payload
    assert payload['error']['code'] == code
    assert isinstance(payload['error']['message'], str) and payload['error']['message']
    assert isinstance(payload['error']['solutions'], list)


# --- GET /api/projects ---


def test_list_is_empty_on_a_fresh_registry(client):
    response = client.get('/api/projects')

    assert response.status_code == 200
    assert response.json() == {'success': True, 'data': []}


def test_list_returns_the_fields_the_frontend_reads(client, tmp_path):
    created = _create(client, tmp_path, 'alpha', description='first project')

    data = client.get('/api/projects', params=CACHE_BUSTER).json()['data']

    assert len(data) == 1
    project = data[0]
    # projects-list.tsx: name, path (also the React key), description
    assert project['name'] == 'alpha'
    assert project['path'] == str(tmp_path / 'alpha')
    assert project['description'] == 'first project'
    # the id created is the id listed
    assert project['id'] == created['id']
    assert isinstance(project['id'], str) and project['id']
    assert isinstance(project['path'], str)


def test_list_path_is_absolute_and_usable_as_a_project_path(client, tmp_path):
    """Other frontend requests send ``project.path`` back as ``project_path``; it must name the directory."""
    _create(client, tmp_path, 'alpha')

    project = client.get('/api/projects').json()['data'][0]

    assert Path(project['path']).is_absolute()
    assert Path(project['path']).is_dir()


def test_list_has_one_unique_path_per_project(client, tmp_path):
    """``path`` is the React ``key`` in projects-list.tsx and must be unique."""
    for name in ('alpha', 'beta', 'gamma'):
        _create(client, tmp_path, name)

    data = client.get('/api/projects').json()['data']

    assert sorted(p['name'] for p in data) == ['alpha', 'beta', 'gamma']
    assert len({p['path'] for p in data}) == 3
    assert len({p['id'] for p in data}) == 3


def test_list_description_defaults_to_empty_string(client, tmp_path):
    _create(client, tmp_path, 'alpha')

    project = client.get('/api/projects').json()['data'][0]

    assert project['description'] == ''


@pytest.mark.xfail(
    strict=True,
    reason="projects-list.tsx renders a 'Created' column from `created_at`, but ProjectListItem / the project "
    'table carry no timestamp, so the column is always blank (adare/core/dto/project.py:ProjectListItem)',
)
def test_list_includes_created_at_for_the_created_column(client, tmp_path):
    _create(client, tmp_path, 'alpha')

    project = client.get('/api/projects').json()['data'][0]

    assert project.get('created_at')


# --- POST /api/projects ---


def test_create_returns_the_new_project(client, tmp_path):
    response = client.post(
        '/api/projects',
        json={'name': 'alpha', 'path': str(tmp_path / 'alpha'), 'description': 'first project'},
    )

    payload = response.json()
    assert response.status_code == 200
    assert payload['success'] is True
    data = payload['data']
    assert data['name'] == 'alpha'
    assert data['path'] == str(tmp_path / 'alpha')
    assert data['description'] == 'first project'
    assert isinstance(data['id'], str) and data['id']
    assert data['next_steps'] and all(isinstance(step, str) for step in data['next_steps'])
    assert (tmp_path / 'alpha').is_dir()


def test_create_description_is_optional(client, tmp_path):
    """create-project-dialog.tsx sends ``description: undefined`` when the field is empty."""
    response = client.post('/api/projects', json={'name': 'alpha', 'path': str(tmp_path / 'alpha')})

    assert response.json()['data']['description'] == ''


def test_create_rejects_a_duplicate_name_in_the_envelope(client, tmp_path):
    _create(client, tmp_path, 'alpha')

    response = client.post('/api/projects', json={'name': 'alpha', 'path': str(tmp_path / 'elsewhere')})

    assert response.status_code == 200
    _assert_failure(response.json(), 'DatabaseProjectCreationError')
    assert 'alpha' in response.json()['error']['message']
    # the half-created directory is cleaned up and the first project is untouched
    assert not (tmp_path / 'elsewhere').exists()
    assert [p['name'] for p in client.get('/api/projects').json()['data']] == ['alpha']


def test_create_rejects_an_existing_directory_in_the_envelope(client, tmp_path):
    (tmp_path / 'taken').mkdir()

    response = client.post('/api/projects', json={'name': 'taken', 'path': str(tmp_path / 'taken')})

    assert response.status_code == 200
    _assert_failure(response.json(), 'ProjectDirectoryCreationError')
    assert client.get('/api/projects').json()['data'] == []


@pytest.mark.parametrize('body', [{'path': '/x'}, {'name': 'x'}, {}])
def test_create_requires_name_and_path(client, body):
    assert client.post('/api/projects', json=body).status_code == 422


# --- GET /api/projects/{path:path} ---


def test_get_passes_an_absolute_path_through_verbatim(client, tmp_path):
    """The frontend builds ``/projects/${project.path}`` from an absolute path (a double slash after /projects).

    The ``{path:path}`` converter must hand the service the full absolute path, not strip the leading slash.
    """
    project_path = tmp_path / 'alpha'
    api = MagicMock()
    api.project.get_by_path.return_value = MagicMock(success=True, data=None, error=None)

    with patch('adare.webapi.routes.projects._api', return_value=api):
        client.get(f'/api/projects/{project_path}', params=CACHE_BUSTER)

    (received,), _ = api.project.get_by_path.call_args
    assert Path(received) == project_path


@pytest.mark.xfail(
    strict=True,
    reason='GET /api/projects/{path} answers HTTP 500: the route passes the raw str to ProjectService.get_by_path, '
    "which needs a Path (ProjectDbApi.get_project_by_path calls path.as_posix()) -> AttributeError: 'str' object "
    "has no attribute 'as_posix' (adare/webapi/routes/projects.py:46)",
)
def test_get_returns_the_project_the_list_returned(client, tmp_path):
    """A project from the list can be fetched with the id the frontend passes (its absolute path)."""
    _create(client, tmp_path, 'alpha', description='first project')
    listed = client.get('/api/projects').json()['data'][0]

    response = client.get(f'/api/projects/{listed["path"]}', params=CACHE_BUSTER)

    assert response.status_code == 200
    payload = response.json()
    assert payload['success'] is True
    assert payload['data']['id'] == listed['id']
    assert payload['data']['name'] == 'alpha'
    assert payload['data']['path'] == listed['path']
    assert payload['data']['description'] == 'first project'


@pytest.mark.xfail(
    strict=True,
    reason='an unknown project path should be the ProjectNotFoundError envelope, but the route crashes with HTTP 500 '
    '(str passed where the service needs a Path, adare/webapi/routes/projects.py:46)',
)
def test_get_unknown_path_is_a_not_found_envelope(client, tmp_path):
    response = client.get(f'/api/projects/{tmp_path / "nope"}')

    assert response.status_code == 200
    _assert_failure(response.json(), 'ProjectNotFoundError')


# --- DELETE /api/projects/{name} ---


def test_delete_with_path_removes_directory_and_registration(client, tmp_path):
    """projects-list.tsx always sends ``?path=<project.path>``."""
    project = _create(client, tmp_path, 'alpha')

    response = client.delete('/api/projects/alpha', params={'path': project['path'], **CACHE_BUSTER})

    assert response.status_code == 200
    assert response.json() == {'success': True, 'data': None}
    assert not (tmp_path / 'alpha').exists()
    assert client.get('/api/projects').json()['data'] == []


def test_delete_with_unknown_path_is_an_envelope_failure(client, tmp_path):
    response = client.delete('/api/projects/ghost', params={'path': str(tmp_path / 'ghost')})

    assert response.status_code == 200
    _assert_failure(response.json(), 'ProjectMissingInDatabaseError')
    assert response.json()['error']['solutions']


def test_delete_leaves_other_projects_alone(client, tmp_path):
    keep = _create(client, tmp_path, 'keep')
    drop = _create(client, tmp_path, 'drop')

    client.delete('/api/projects/drop', params={'path': drop['path']})

    assert [p['path'] for p in client.get('/api/projects').json()['data']] == [keep['path']]
    assert (tmp_path / 'keep').is_dir()


@pytest.mark.xfail(
    strict=True,
    reason='DELETE /api/projects/{name} without ?path= is documented to resolve the path from the name, but it calls '
    'get_by_path(name) with a str -> HTTP 500 AttributeError (and a name is not a path, so the lookup could '
    'never match anyway) (adare/webapi/routes/projects.py:75)',
)
def test_delete_by_name_alone_removes_the_project(client, tmp_path):
    _create(client, tmp_path, 'alpha')

    response = client.delete('/api/projects/alpha')

    assert response.status_code == 200
    assert response.json()['success'] is True
    assert client.get('/api/projects').json()['data'] == []


@pytest.mark.xfail(
    strict=True,
    reason='DELETE of an unknown project name without ?path= should be the documented HTTP 404, but the route '
    'crashes with HTTP 500 first (adare/webapi/routes/projects.py:75)',
)
def test_delete_unknown_name_alone_is_a_404(client):
    assert client.delete('/api/projects/ghost').status_code == 404
