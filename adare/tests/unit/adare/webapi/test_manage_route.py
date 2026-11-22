"""The /api/manage/db-status endpoint against the real service and a real (temporary) global database.

The route is registered in ``adare-web/src/api/endpoints.ts`` as ``manageDbStatus`` but no page reads
it yet, so the shape asserted here is the ``DbStatusResult`` the CLI and a future status widget share.
Failures are HTTP 200 ``{success: false, error: {code, message, solutions}}``.
"""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adare.webapi.routes.manage import router

pytestmark = pytest.mark.unit

STATUS_FIELDS = {
    'global_db_exists',
    'global_db_accessible',
    'global_db_location',
    'valid',
    'pending_migrations',
    'errors',
}


@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    import adare.config.database as config_database

    directory = tmp_path / 'state'
    monkeypatch.setattr(config_database, 'STATE_DIR', directory)
    return directory


@pytest.fixture
def client(state_dir):
    app = FastAPI()
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


def test_status_reports_a_missing_database_in_the_data_not_as_a_failure(client, state_dir):
    response = client.get('/api/manage/db-status')

    assert response.status_code == 200
    payload = response.json()
    assert payload['success'] is True
    data = payload['data']
    assert set(data) == STATUS_FIELDS
    assert data['global_db_exists'] is False
    assert data['global_db_accessible'] is False
    assert data['valid'] is False
    assert data['global_db_location'] == str(state_dir / 'global.db.sqlite3')
    assert any('does not exist' in error for error in data['errors'])


def test_status_of_an_initialised_database_is_valid(client, state_dir):
    from adare.database.api.project import ProjectDbApi

    with ProjectDbApi():
        pass  # opening the global database creates and migrates it

    response = client.get('/api/manage/db-status', params={'_t': '1700000000000'})

    data = response.json()['data']
    assert response.json()['success'] is True
    assert data['global_db_exists'] is True
    assert data['global_db_accessible'] is True
    assert data['valid'] is True
    assert data['errors'] == []
    assert data['pending_migrations'] == []
    assert data['global_db_location'] == str(state_dir / 'global.db.sqlite3')
    assert (state_dir / 'global.db.sqlite3').is_file()


def test_status_field_types_are_json_friendly(client):
    data = client.get('/api/manage/db-status').json()['data']

    assert isinstance(data['global_db_location'], str)
    assert isinstance(data['pending_migrations'], list)
    assert isinstance(data['errors'], list)
    assert all(isinstance(data[key], bool) for key in ('global_db_exists', 'global_db_accessible', 'valid'))


def test_status_failure_is_reported_in_the_envelope(client):
    with patch('adare.services.manage_service.validate_database_integrity', side_effect=OSError('disk unreadable')):
        response = client.get('/api/manage/db-status')

    assert response.status_code == 200
    payload = response.json()
    assert payload['success'] is False
    assert 'data' not in payload
    assert payload['error']['code'] == 'DbStatusError'
    assert 'disk unreadable' in payload['error']['message']
    assert payload['error']['solutions']
