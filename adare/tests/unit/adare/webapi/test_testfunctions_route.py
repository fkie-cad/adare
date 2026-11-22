"""The /api/testfunctions endpoints against the real service layer and a seeded global database.

``adare-web/src/api/hooks/use-testfunctions.ts`` types a testfunction as
``{dotnotation, name?, file_name?, description?}``, filters the list with ``?file_name=<file_name>``
and fetches one with ``/testfunctions/${dotnotation}``. The rows are inserted the way registration
stores them (file name = module stem, dotnotation = ``<file>.<name>``) so the real DB -> DTO -> JSON
path is what is asserted, and the ids the frontend passes round-trip.

Failures are HTTP 200 ``{success: false, error: {code, message, solutions}}``.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adare.database.api.testfunction import TestfunctionDbApi
from adare.database.models.global_models import TestFunction, TestFunctionFile, TestParameter
from adare.webapi.routes.testfunctions import router

pytestmark = pytest.mark.unit

CACHE_BUSTER = {'_t': '1700000000000'}


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A client whose global database lives under ``tmp_path``."""
    import adare.config.database as config_database

    monkeypatch.setattr(config_database, 'STATE_DIR', tmp_path / 'state')
    app = FastAPI()
    app.include_router(router)
    return TestClient(app, raise_server_exceptions=False)


def _seed(api, file_name, functions):
    """Register a testfunction collection. ``functions`` maps name -> (description, [(param, dtype, optional)])."""
    tf_file = TestFunctionFile(
        name=file_name,
        path=f'/adare/testfunctions/{file_name}.py',
        requirements_path=f'/adare/testfunctions/{file_name}.txt',
        sha256hash='f' * 64,
        description=f'{file_name} collection',
    )
    api._session.add(tf_file)
    api._session.flush()
    for name, (description, params) in functions.items():
        parameters = []
        for param_name, dtype, optional in params:
            parameter = TestParameter(name=f'{file_name}.{name}.{param_name}', dtype=dtype, optional=optional)
            parameter.description = f'the {param_name}'
            parameters.append(parameter)
        api._session.add(
            TestFunction(
                type=f'{name.title()}Test',
                name=name,
                description=description,
                sha256hash='a' * 64,
                file_id=tf_file.id,
                parameters=parameters,
            )
        )
    return tf_file


@pytest.fixture
def seeded(client):
    """Two collections: ``files`` (two functions) and ``json`` (one)."""
    with TestfunctionDbApi() as api:
        _seed(
            api,
            'files',
            {
                'file_exists': ('Check that a file exists', [('path', 'str', False), ('follow', 'bool', True)]),
                'file_size': ('Check a file size', [('path', 'str', False)]),
            },
        )
        _seed(api, 'json', {'key_equals': ('Check a JSON key', [])})


def _assert_failure(payload, code):
    assert payload['success'] is False
    assert 'data' not in payload
    assert payload['error']['code'] == code
    assert isinstance(payload['error']['message'], str) and payload['error']['message']
    assert isinstance(payload['error']['solutions'], list)


# --- GET /api/testfunctions ---


def test_list_is_empty_without_registered_testfunctions(client):
    response = client.get('/api/testfunctions')

    assert response.status_code == 200
    assert response.json() == {'success': True, 'data': []}


def test_list_returns_the_fields_the_frontend_reads(client, seeded):
    response = client.get('/api/testfunctions', params=CACHE_BUSTER)

    assert response.status_code == 200
    data = response.json()['data']
    by_dotnotation = {tf['dotnotation']: tf for tf in data}
    assert sorted(by_dotnotation) == ['files.file_exists', 'files.file_size', 'json.key_equals']
    exists = by_dotnotation['files.file_exists']
    # use-testfunctions.ts: dotnotation, name, file_name, description
    assert exists['name'] == 'file_exists'
    assert exists['file_name'] == 'files'
    assert exists['description'] == 'Check that a file exists'
    assert isinstance(exists['id'], str) and exists['id']
    assert exists['file_description'] == 'files collection'


def test_list_dotnotation_is_the_file_name_dot_function_name(client, seeded):
    for tf in client.get('/api/testfunctions').json()['data']:
        assert tf['dotnotation'] == f'{tf["file_name"]}.{tf["name"]}'


def test_list_includes_parameters_with_their_meaning(client, seeded):
    data = {tf['dotnotation']: tf for tf in client.get('/api/testfunctions').json()['data']}

    exists = data['files.file_exists']
    assert exists['parameter_count'] == 2
    parameters = {p['name'].rsplit('.', 1)[-1]: p for p in exists['parameters']}
    assert parameters['path']['data_type'] == 'str'
    assert parameters['path']['optional'] is False
    assert parameters['path']['required'] is True
    assert parameters['follow']['data_type'] == 'bool'
    assert parameters['follow']['optional'] is True
    assert parameters['follow']['required'] is False
    assert data['json.key_equals']['parameter_count'] == 0
    assert data['json.key_equals']['parameters'] == []


def test_list_filters_by_file_name(client, seeded):
    response = client.get('/api/testfunctions', params={'file_name': 'files', **CACHE_BUSTER})

    data = response.json()['data']
    assert sorted(tf['dotnotation'] for tf in data) == ['files.file_exists', 'files.file_size']
    assert {tf['file_name'] for tf in data} == {'files'}


def test_list_filter_round_trips_the_file_name_the_list_returned(client, seeded):
    """``file_name`` from a listed item is what the frontend passes back as ``?file_name=``."""
    everything = client.get('/api/testfunctions').json()['data']

    for item in everything:
        filtered = client.get('/api/testfunctions', params={'file_name': item['file_name']}).json()['data']
        assert item['dotnotation'] in {tf['dotnotation'] for tf in filtered}
        assert {tf['file_name'] for tf in filtered} == {item['file_name']}


def test_list_filter_for_an_unknown_file_is_empty_not_an_error(client, seeded):
    response = client.get('/api/testfunctions', params={'file_name': 'nope'})

    assert response.json() == {'success': True, 'data': []}


def test_list_hides_testfunctions_no_longer_in_the_source(client, seeded):
    with TestfunctionDbApi() as api:
        vanished = api._session.query(TestFunction).filter_by(name='file_size').one()
        vanished.is_current = False

    dotnotations = {tf['dotnotation'] for tf in client.get('/api/testfunctions').json()['data']}

    assert 'files.file_size' not in dotnotations
    assert 'files.file_exists' in dotnotations


# --- GET /api/testfunctions/{dotnotation:path} ---


def test_get_returns_the_detail_for_a_dotnotation(client, seeded):
    response = client.get('/api/testfunctions/files.file_exists', params=CACHE_BUSTER)

    assert response.status_code == 200
    payload = response.json()
    assert payload['success'] is True
    data = payload['data']
    assert data['dotnotation'] == 'files.file_exists'
    assert data['name'] == 'file_exists'
    assert data['file_name'] == 'files'
    assert data['description'] == 'Check that a file exists'
    assert data['parameter_count'] == 2
    assert {p['name'].rsplit('.', 1)[-1] for p in data['parameters']} == {'path', 'follow'}


def test_every_listed_dotnotation_can_be_fetched(client, seeded):
    """The list's ``dotnotation`` is the id the frontend puts in ``/testfunctions/${dotnotation}``."""
    listed = client.get('/api/testfunctions').json()['data']
    assert listed

    for item in listed:
        payload = client.get(f'/api/testfunctions/{item["dotnotation"]}', params=CACHE_BUSTER).json()
        assert payload['success'] is True, item['dotnotation']
        assert payload['data']['id'] == item['id']
        assert payload['data']['dotnotation'] == item['dotnotation']


def test_get_unknown_dotnotation_is_a_not_found_envelope(client, seeded):
    response = client.get('/api/testfunctions/files.nope')

    assert response.status_code == 200
    _assert_failure(response.json(), 'TestfunctionNotFoundError')
    assert 'files.nope' in response.json()['error']['message']
    assert response.json()['error']['solutions']


def test_get_on_an_empty_registry_is_a_not_found_envelope(client):
    _assert_failure(client.get('/api/testfunctions/files.file_exists').json(), 'TestfunctionNotFoundError')


def test_get_dotnotation_with_slashes_is_a_not_found_envelope_not_a_404(client, seeded):
    """The ``:path`` converter accepts slashes; a bogus value must not escape the envelope."""
    response = client.get('/api/testfunctions/files/file_exists')

    assert response.status_code == 200
    _assert_failure(response.json(), 'TestfunctionNotFoundError')


def test_get_is_case_sensitive(client, seeded):
    _assert_failure(client.get('/api/testfunctions/Files.File_Exists').json(), 'TestfunctionNotFoundError')


def test_get_hides_a_testfunction_that_vanished_from_its_source(client, seeded):
    """Detail follows the list: a vanished testfunction (kept only for experiment references) is not found."""
    with TestfunctionDbApi() as api:
        api._session.query(TestFunction).filter_by(name='file_size').one().is_current = False

    payload = client.get('/api/testfunctions/files.file_size').json()

    _assert_failure(payload, 'TestfunctionNotFoundError')
