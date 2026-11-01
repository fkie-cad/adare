"""The /api/web endpoints (login / logout / status / sync) against the real service layer.

Sessions live in a real (temporary) global database. Nothing leaves the machine: the OAuth browser
flow (``start_oauth_flow``), the token HTTP exchange (``refresh_gitea_token`` /
``exchange_gitea_for_django``) and the sync uploads are stubbed at the network boundary, and the
tokens seeded are made-up strings; no keyring or real credential is read.

``adare-web/src/api/endpoints.ts`` registers ``webLogin``/``webLogout``/``webStatus``/``webSync`` but no
page consumes them yet, so the asserted shapes are the service DTOs (``WebStatusResult`` etc.).
Failures are HTTP 200 ``{success: false, error: {code, message, solutions}}``.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adare.database.api.usersession import UserSessionApi
from adare.web.exceptions import LoginFailedError
from adare.webapi.routes.web_sync import router

pytestmark = pytest.mark.unit

CACHE_BUSTER = {'_t': '1700000000000'}


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A client whose global database (and so the user sessions) lives under ``tmp_path``."""
    import adare.config.database as config_database

    monkeypatch.setattr(config_database, 'STATE_DIR', tmp_path / 'state')
    app = FastAPI()
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


def _naive_utc(delta: timedelta) -> datetime:
    return (datetime.now(UTC) + delta).replace(tzinfo=None)


def _add_session(username='alice', gitea_in=timedelta(hours=1), django_in=timedelta(hours=1), refresh_token=''):
    with UserSessionApi() as db:
        db.add_user_session(
            username=username,
            gitea_token='gitea-fake',
            gitea_token_expiration=_naive_utc(gitea_in),
            gitea_refresh_token=refresh_token,
            django_token='django-fake',
            django_token_expiration=_naive_utc(django_in),
        )


def _assert_failure(payload, code):
    assert payload['success'] is False
    assert 'data' not in payload
    assert payload['error']['code'] == code
    assert isinstance(payload['error']['message'], str) and payload['error']['message']
    assert isinstance(payload['error']['solutions'], list)


# --- GET /api/web/status ---


def test_status_when_nobody_is_logged_in(client):
    response = client.get('/api/web/status', params=CACHE_BUSTER)

    assert response.status_code == 200
    assert response.json() == {'success': True, 'data': {'logged_in': False, 'username': None}}


def test_status_reports_the_logged_in_user(client):
    _add_session('alice')

    data = client.get('/api/web/status').json()['data']

    assert data == {'logged_in': True, 'username': 'alice'}


def test_status_prunes_an_expired_session_without_a_refresh_token(client):
    _add_session('alice', gitea_in=timedelta(hours=-1))

    data = client.get('/api/web/status').json()['data']

    assert data == {'logged_in': False, 'username': None}


def test_status_renews_an_expired_session_that_has_a_refresh_token(client):
    """The access token is expired but refreshable: the user must stay logged in (HTTP stubbed)."""
    _add_session('alice', gitea_in=timedelta(hours=-1), refresh_token='refresh-fake')
    fresh = {'access_token': 'gitea-new', 'expires_in': 3600, 'refresh_token': 'refresh-new'}

    with (
        patch('adare.web.login.refresh_gitea_token', return_value=fresh) as refresh,
        patch(
            'adare.web.login.exchange_gitea_for_django',
            return_value=('alice', 'django-new', datetime.now(UTC).replace(tzinfo=None) + timedelta(hours=1)),
        ),
    ):
        data = client.get('/api/web/status').json()['data']

    refresh.assert_called_once_with('refresh-fake')
    assert data == {'logged_in': True, 'username': 'alice'}


def test_status_failure_is_reported_in_the_envelope(client):
    with patch('adare.web.login.refresh_session_if_needed', side_effect=OSError('db locked')):
        response = client.get('/api/web/status')

    assert response.status_code == 200
    _assert_failure(response.json(), 'StatusError')
    assert 'db locked' in response.json()['error']['message']


# --- POST /api/web/login ---


def test_login_starts_the_oauth_flow_on_a_free_localhost_port(client):
    with (
        patch('adare.web.login.is_localhost_port_free', return_value=True),
        patch('adare.web.login.start_oauth_flow') as flow,
    ):
        response = client.post('/api/web/login')

    assert response.status_code == 200
    payload = response.json()
    assert payload['success'] is True
    assert payload['data']['logged_in'] is True
    assert payload['data']['message']
    (redirect_uri, port), _ = flow.call_args
    assert redirect_uri == f'http://localhost:{port}/oauth/callback'


def test_login_when_already_logged_in_is_a_login_error(client):
    _add_session('alice')

    with patch('adare.web.login.start_oauth_flow') as flow:
        response = client.post('/api/web/login')

    assert response.status_code == 200
    _assert_failure(response.json(), 'LoginError')
    assert 'alice' in response.json()['error']['message']
    flow.assert_not_called()


def test_login_failure_is_reported_in_the_envelope(client):
    import logging

    failure = LoginFailedError(logging.getLogger(__name__), 'State mismatch')

    with (
        patch('adare.web.login.is_localhost_port_free', return_value=True),
        patch('adare.web.login.start_oauth_flow', side_effect=failure),
    ):
        response = client.post('/api/web/login')

    assert response.status_code == 200
    _assert_failure(response.json(), 'LoginError')
    assert 'State mismatch' in response.json()['error']['message']
    assert response.json()['error']['solutions']


def test_login_without_a_free_redirect_port_is_a_login_error(client):
    with (
        patch('adare.web.login.is_localhost_port_free', return_value=False),
        patch('adare.web.login.start_oauth_flow') as flow,
    ):
        response = client.post('/api/web/login')

    assert response.status_code == 200
    _assert_failure(response.json(), 'LoginError')
    assert 'No free port' in response.json()['error']['message']
    flow.assert_not_called()


# --- POST /api/web/logout ---


def test_logout_ends_the_session(client):
    _add_session('alice')

    response = client.post('/api/web/logout')

    assert response.status_code == 200
    payload = response.json()
    assert payload['success'] is True
    assert payload['data']['logged_out'] is True
    assert payload['data']['message']
    assert client.get('/api/web/status').json()['data'] == {'logged_in': False, 'username': None}


def test_logout_when_nobody_is_logged_in_is_a_logout_error(client):
    response = client.post('/api/web/logout')

    assert response.status_code == 200
    _assert_failure(response.json(), 'LogoutError')
    assert 'No user is currently logged in' in response.json()['error']['message']
    assert response.json()['error']['solutions']


# --- POST /api/web/sync ---


@pytest.fixture
def uploads():
    """The three per-resource sync functions, replaced so nothing can reach the server."""
    with (
        patch('adare.backend.sync.sync_environments_all') as environments,
        patch('adare.backend.sync.sync_experiments_all') as experiments,
        patch('adare.backend.sync.sync_testfunctions_all') as testfunctions,
    ):
        yield environments, experiments, testfunctions


def test_sync_when_logged_in_syncs_every_resource_kind(client, uploads):
    _add_session('alice')

    response = client.post('/api/web/sync')

    assert response.status_code == 200
    payload = response.json()
    assert payload['success'] is True
    assert payload['data']['synced'] is True
    assert payload['data']['message']
    for sync_function in uploads:
        sync_function.assert_called_once_with(None)


def test_sync_failure_is_reported_in_the_envelope(client, uploads):
    _add_session('alice')
    uploads[0].side_effect = ConnectionError('server unreachable')

    response = client.post('/api/web/sync')

    assert response.status_code == 200
    _assert_failure(response.json(), 'SyncError')
    assert 'server unreachable' in response.json()['error']['message']
    assert response.json()['error']['solutions']


@pytest.mark.xfail(
    strict=True,
    reason='backend.sync.sync() just logs "You need to be logged in to sync" and returns when nobody is logged in, '
    'and WebService.sync() then reports {success: true, data: {synced: true, message: "Sync completed '
    'successfully"}} although nothing was synced (adare/services/web_service.py:328)',
)
def test_sync_when_logged_out_does_not_claim_success(client, uploads):
    response = client.post('/api/web/sync')

    payload = response.json()
    assert response.status_code == 200
    assert payload['success'] is False or payload['data']['synced'] is False
    for sync_function in uploads:
        sync_function.assert_not_called()
