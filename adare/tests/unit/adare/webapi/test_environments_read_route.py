"""Read / check-url / delete / verify endpoints of ``/api/environments``.

The React frontend (``adare-web/src/api/hooks/use-environments.ts``,
``pages/environments-list.tsx``, ``pages/environment-detail.tsx``) reads specific
keys off these responses. These tests run the *real* service layer against a
seeded temp global database so the real DTO -> JSON shape is asserted, instead of
a mocked dict that would hide a field the page reads but the backend never sends.

Boundaries that are mocked, and only these: the HTTP HEAD in ``check-url``, the
experiment service's ``ensure_verify_setup`` / ``run`` (they start VMs) and the
backend deletion routine in the ``force`` pass-through test.

Frontend reads that the backend does not satisfy are ``xfail(strict=True)`` so the
gap is visible, and the test starts failing loudly when someone closes it.
"""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import requests
import ulid
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adare.backend.environment.exceptions import EnvironmentDeletionError
from adare.core.result import Result
from adare.database.api.base import GlobalDatabaseApi, ProjectDatabaseApi
from adare.database.models.global_models import Environment, OsInfo, Project, SyncMetadata, Vm
from adare.database.models.project_models import Experiment, ExperimentRun
from adare.services.experiment_service import ExperimentRunStartedInfo, ExperimentService
from adare.webapi.routes.environments import router as environments_router
from adare.webapi.routes.experiments import router as experiments_router
from adare.webapi.routes.runs import router as runs_router

pytestmark = pytest.mark.unit

SHA = 'a' * 64
DISK_URL = 'https://cloud.example/share/disk.qcow2'
UBUNTU_ISO = 'https://releases.ubuntu.com/24.04/ubuntu-24.04-live-server-amd64.iso'

BAKED_YAML = f"""\
vm: {DISK_URL}
vm_type: url
vm_sha256: {SHA}
vm_format: qcow2
source_profile: ubuntu2404
source_iso_sha256: {'b' * 64}
os:
  platform: linux
  os: Ubuntu
  distribution: '24.04'
"""

RECIPE_YAML = f"""\
vm_type: recipe
os:
  platform: linux
  os: Ubuntu
  distribution: '24.04'
recipe:
  profile: ubuntu2404
  iso: {UBUNTU_ISO}
  iso_sha256: {SHA}
  params:
    disk_size: 40G
    ram_mb: 4096
    cpus: 2
"""

# What a failing Result must look like on the wire (the frontend's `assertOk` /
# `unwrap` switch on `success` and read `error.message`).
ENVELOPE_ERROR_KEYS = {'code', 'message', 'solutions'}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def global_db(tmp_path):
    """Point the whole process at a throwaway global database."""
    with patch('adare.config.database.get_global_database_location', return_value=tmp_path / 'global.db'):
        yield tmp_path


@pytest.fixture
def client(global_db):
    app = FastAPI()
    app.include_router(environments_router)
    return TestClient(app)


@pytest.fixture
def seed_env(global_db):
    """Insert a *current* environment row (plus VM / OS / sync rows) and return its ULID."""

    def _seed(
        name='env1',
        yaml_text=BAKED_YAML,
        disk='present',
        synced=None,
        os_name='Ubuntu',
        distribution='24.04',
        superseded=False,
    ) -> str:
        env_file = global_db / f'{name}-{ulid.ULID()}.yml'
        if yaml_text is not None:
            env_file.write_text(yaml_text)
        disk_path = {
            'present': str(global_db / f'{name}.qcow2'),
            'missing': str(global_db / 'nope' / f'{name}.qcow2'),
            'url': DISK_URL,
        }[disk]
        if disk == 'present':
            Path(disk_path).write_bytes(b'qcow2')
        with GlobalDatabaseApi() as db:
            session = db._session
            osinfo = OsInfo(
                id=str(ulid.ULID()),
                platform='linux',
                os=os_name,
                distribution=distribution,
                version='',
                language='en-US',
            )
            vm = Vm(id=str(ulid.ULID()), name=f'vm-{name}', file=disk_path, hash='h' * 8, osinfo_id=osinfo.id)
            sync = None
            if synced is not None:
                sync = SyncMetadata(id=str(ulid.ULID()), sync_status='synced' if synced else 'pending')
                session.add(sync)
            env = Environment(
                id=str(ulid.ULID()),
                name=name,
                description='desc',
                vm_id=vm.id,
                file=str(env_file),
                sync_metadata_id=sync.id if sync else None,
            )
            if superseded:
                from datetime import datetime

                env.superseded_at = datetime(2020, 1, 1)
            session.add_all([osinfo, vm])
            session.flush()
            session.add(env)
            return env.id

    return _seed


def _assert_error_envelope(response, code=None):
    """A rejection is HTTP 200 + `{success: false, error: {code, message, solutions}}`."""
    assert response.status_code == 200
    body = response.json()
    assert body['success'] is False
    assert 'data' not in body
    assert set(body['error']) == ENVELOPE_ERROR_KEYS
    assert isinstance(body['error']['message'], str) and body['error']['message']
    assert isinstance(body['error']['solutions'], list)
    if code is not None:
        assert body['error']['code'] == code
    return body['error']


# ---------------------------------------------------------------------------
# GET /api/environments  (list)
# ---------------------------------------------------------------------------


def test_list_with_no_environments_is_an_empty_list_not_an_error(client):
    body = client.get('/api/environments').json()
    assert body == {'success': True, 'data': []}


def test_list_returns_the_keys_the_frontend_reads_for_a_baked_url_environment(client, seed_env):
    seed_env('baked', disk='url')

    body = client.get('/api/environments').json()

    assert body['success'] is True
    (item,) = body['data']
    # environments-list.tsx / use-environments.ts `Environment`
    assert item['name'] == 'baked'
    assert item['vm'] == DISK_URL  # rendered as a link by VmCell
    assert item['vm_type'] == 'url'  # EnvironmentTypeBadge -> "Baked"
    assert item['vm_sha256'] == SHA
    # ids the other pages link / delete with
    assert len(item['ulid']) == 26
    assert item['display_name'] == 'baked'
    assert item['description'] == 'desc'


def test_list_serialises_every_value_as_json_scalars(client, seed_env):
    """Paths/datetimes/enums must have been converted: a leaked object is a FastAPI 500."""
    seed_env('e', synced=True)
    response = client.get('/api/environments')
    assert response.status_code == 200
    item = response.json()['data'][0]
    assert isinstance(item['created_at'], str)
    assert isinstance(item['published'], bool)
    assert isinstance(item['in_request'], bool)


def test_list_hides_superseded_versions_and_keeps_current_ones(client, seed_env):
    seed_env('old', superseded=True)
    seed_env('current')

    names = [e['name'] for e in client.get('/api/environments').json()['data']]

    assert names == ['current']


def test_list_exposes_the_os_the_registered_vm_reports(client, seed_env):
    seed_env('e', os_name='Ubuntu', distribution='24.04')
    item = client.get('/api/environments').json()['data'][0]
    assert item['osinfo_os'] == 'Ubuntu'
    assert item['osinfo_distribution'] == '24.04'
    assert item['os_info'] == 'linux 24.04'  # str(OsInfo): platform distribution version


@pytest.mark.parametrize(
    ('disk', 'expected'),
    [('present', True), ('missing', False), ('url', None)],
)
def test_list_reports_whether_the_backing_disk_exists(client, seed_env, disk, expected):
    seed_env('e', disk=disk)
    item = client.get('/api/environments').json()['data'][0]
    assert item['disk_present'] is expected
    assert item['disk_path']


@pytest.mark.xfail(
    strict=True,
    reason=(
        'show_service._parse_env_source promises "a single malformed file must never break the whole list" but '
        'catches only (OSError, ValueError, DataStructuringError); a YAML syntax error is a yaml.YAMLError, '
        'which escapes, so one bad environment file turns GET /api/environments into an HTTP 500 and the list '
        'page shows nothing. (services/show_service.py:56)'
    ),
)
def test_list_survives_an_unparseable_environment_file(global_db, seed_env):
    app = FastAPI()
    app.include_router(environments_router)
    http = TestClient(app, raise_server_exceptions=False)
    seed_env('broken', yaml_text='vm: [unclosed')
    seed_env('fine')

    response = http.get('/api/environments')

    assert response.status_code == 200
    body = response.json()
    assert body['success'] is True
    by_name = {e['name']: e for e in body['data']}
    assert by_name['broken']['vm'] == ''
    assert by_name['fine']['vm'] == DISK_URL


def test_list_survives_a_structurally_invalid_environment_file(client, seed_env):
    """Valid YAML that is not a valid environment (no vm / recipe) is skipped, not fatal."""
    seed_env('broken', yaml_text='name: nothing-else\n')
    seed_env('fine')

    body = client.get('/api/environments').json()

    assert body['success'] is True
    by_name = {e['name']: e for e in body['data']}
    assert by_name['broken']['vm'] == ''
    assert by_name['fine']['vm'] == DISK_URL


def test_list_failure_is_a_200_error_envelope(client):
    from sqlalchemy.exc import OperationalError

    with patch(
        'adare.database.api.structured_data.StructuredDataApi.get_environments_structured',
        side_effect=OperationalError('select', {}, Exception('db locked')),
    ):
        error = _assert_error_envelope(client.get('/api/environments'), 'EnvironmentListError')
    assert 'db locked' in error['message']


# --- frontend reads that the backend does not satisfy ------------------------


@pytest.mark.xfail(
    strict=True,
    reason=(
        'environments-list.tsx / environment-detail.tsx render `(env as any).os` ("OS" column) but '
        'ShowService.list_environments sends only osinfo_os / osinfo_distribution / os_info, never `os`: '
        'the OS column is always "—".'
    ),
)
@pytest.mark.parametrize('route', ['/api/environments', '/api/environments/e'])
def test_environment_carries_the_os_label_the_pages_render(client, seed_env, route):
    seed_env('e', os_name='Ubuntu', distribution='24.04')
    data = client.get(route).json()['data']
    item = data[0] if isinstance(data, list) else data
    assert item.get('os'), f'no `os` key; backend sent {sorted(item)}'


@pytest.mark.xfail(
    strict=True,
    reason=(
        'the Sync badge reads a boolean `synced` (env.synced === true/false) but the backend sends '
        '`published` / `in_request` only: the badge is always "—".'
    ),
)
@pytest.mark.parametrize('route', ['/api/environments', '/api/environments/e'])
@pytest.mark.parametrize('synced', [True, False])
def test_environment_carries_the_boolean_sync_flag_the_badge_reads(client, seed_env, route, synced):
    seed_env('e', synced=synced)
    data = client.get(route).json()['data']
    item = data[0] if isinstance(data, list) else data
    assert item.get('synced') is synced, f'no `synced` key; backend sent {sorted(item)}'


@pytest.mark.xfail(
    strict=True,
    reason=(
        'the frontend decides recipe-vs-baked from `env.recipe` ({profile, disk_size, ram_mb, cpus, ...}: '
        'type badge on the list, "Recipe" row on the detail page) but the backend never sends `recipe`. '
        'A recipe environment has no `vm`, so it is labelled "Legacy" in the list and the Recipe row never shows.'
    ),
)
@pytest.mark.parametrize('route', ['/api/environments', '/api/environments/recipe-env'])
def test_recipe_environment_carries_the_recipe_block_the_pages_render(client, seed_env, route):
    seed_env('recipe-env', yaml_text=RECIPE_YAML, disk='missing')
    data = client.get(route).json()['data']
    item = data[0] if isinstance(data, list) else data
    recipe = item.get('recipe')
    assert recipe, f'no `recipe` key; backend sent {sorted(item)}'
    assert recipe['profile'] == 'ubuntu2404'
    assert recipe['disk_size'] == '40G'
    assert recipe['ram_mb'] == 4096
    assert recipe['cpus'] == 2


@pytest.mark.xfail(
    strict=True,
    reason=(
        'environment-detail.tsx enables the Verify button only when `env.project_path` is set and posts it as '
        'the verify body; the backend sends `project: "Global"` and no `project_path` (environments are global), '
        'so Verify is permanently disabled and the Project cell is always "—". The fix may belong in the frontend '
        '(pass the active project) rather than here.'
    ),
)
@pytest.mark.parametrize('route', ['/api/environments', '/api/environments/e'])
def test_environment_carries_the_project_path_the_verify_button_needs(client, seed_env, route):
    seed_env('e')
    data = client.get(route).json()['data']
    item = data[0] if isinstance(data, list) else data
    assert item.get('project_path'), f'no `project_path` key; backend sent {sorted(item)}'


# ---------------------------------------------------------------------------
# GET /api/environments/os-profiles
# ---------------------------------------------------------------------------

OS_PROFILE_KEYS = {
    'name',
    'display_name',
    'platform',
    'distribution',
    'version',
    'architecture',
    'default_disk_size',
    'default_ram_mb',
    'default_cpus',
    'iso_url',
    'iso_sha256',
    'iso_notes',
}


def test_os_profiles_is_not_captured_by_the_name_route(client):
    """`/os-profiles` is a literal; if `/{name}` won it would answer EnvironmentNotFoundError."""
    body = client.get('/api/environments/os-profiles').json()
    assert body['success'] is True
    assert isinstance(body['data'], list)
    assert body['data']


def test_os_profiles_carry_every_field_the_recipe_dialog_reads(client):
    profiles = client.get('/api/environments/os-profiles').json()['data']
    for profile in profiles:
        assert set(profile) >= OS_PROFILE_KEYS, profile['name']
        assert profile['name'] and profile['display_name']
        assert isinstance(profile['default_ram_mb'], int)
        assert isinstance(profile['default_cpus'], int)
    names = [p['name'] for p in profiles]
    assert len(names) == len(set(names)), 'the dialog selects a profile by `name`, so it must be unique'


def test_os_profiles_platform_uses_the_lowercase_values_the_dialog_compares(client):
    """create-environment-dialog.tsx: `selectedProfile?.platform === 'windows'` gates the BYO ISO flow."""
    platforms = {p['platform'] for p in client.get('/api/environments/os-profiles').json()['data']}
    assert platforms <= {'windows', 'linux'}
    assert 'windows' in platforms


def test_os_profiles_split_windows_byo_from_published_linux_isos(client):
    """The dialog prefills Linux from iso_url + iso_sha256 and shows iso_notes for Windows."""
    profiles = client.get('/api/environments/os-profiles').json()['data']
    windows = [p for p in profiles if p['platform'] == 'windows']
    linux = [p for p in profiles if p['platform'] == 'linux']

    assert windows
    for profile in windows:
        assert not profile['iso_url'], f'{profile["name"]}: a Windows ISO cannot be rehosted'
        assert profile['iso_notes'], f'{profile["name"]}: a BYO ISO needs a download pointer'
    prefilled = [p for p in linux if p['iso_url']]
    assert prefilled, 'at least one Linux profile must prefill a published ISO'
    for profile in linux:
        # Either both halves of the integrity pair are present or neither (the dialog prefills the pair).
        assert bool(profile['iso_url']) == bool(profile['iso_sha256']), profile['name']
    for profile in prefilled:
        assert profile['iso_url'].startswith(('http://', 'https://')), profile['name']
        assert len(profile['iso_sha256']) == 64, profile['name']


# ---------------------------------------------------------------------------
# GET /api/environments/{name}
# ---------------------------------------------------------------------------


def test_get_environment_returns_the_detail_the_page_reads(client, seed_env):
    ulid_ = seed_env('baked', disk='url', synced=True)

    body = client.get('/api/environments/baked').json()

    assert body['success'] is True
    env = body['data']
    assert env['name'] == 'baked'
    assert env['ulid'] == ulid_
    assert env['vm'] == DISK_URL
    assert env['vm_type'] == 'url'
    assert env['vm_sha256'] == SHA
    # "Source profile (provenance only)" row of environment-detail.tsx
    assert env['source_profile'] == 'ubuntu2404'
    assert env['source_iso_sha256'] == 'b' * 64
    assert env['published'] is True


def test_get_environment_agrees_with_the_list_row_for_the_shared_fields(client, seed_env):
    seed_env('e', disk='url')
    listed = client.get('/api/environments').json()['data'][0]
    detail = client.get('/api/environments/e').json()['data']
    for key in listed:
        assert detail[key] == listed[key], key


def test_get_environment_only_matches_the_requested_name(client, seed_env):
    seed_env('alpha')
    seed_env('beta')
    assert client.get('/api/environments/beta').json()['data']['name'] == 'beta'


def test_get_environment_ignores_superseded_versions(client, seed_env):
    seed_env('gone', superseded=True)
    _assert_error_envelope(client.get('/api/environments/gone'), 'EnvironmentNotFoundError')


def test_get_unknown_environment_is_a_200_error_envelope(client, seed_env):
    seed_env('other')

    error = _assert_error_envelope(client.get('/api/environments/missing'), 'EnvironmentNotFoundError')

    assert 'missing' in error['message']
    assert error['solutions']


def test_get_environment_failure_is_a_200_error_envelope(client):
    from sqlalchemy.exc import OperationalError

    with patch(
        'adare.database.api.structured_data.StructuredDataApi.get_environments_structured',
        side_effect=OperationalError('select', {}, Exception('db locked')),
    ):
        _assert_error_envelope(client.get('/api/environments/e'), 'EnvironmentRetrievalError')


# ---------------------------------------------------------------------------
# POST /api/environments/check-url   (HTTP HEAD mocked at the `requests` boundary)
# ---------------------------------------------------------------------------

CHECK_KEYS = {'valid', 'reachable', 'status', 'reason'}


def _head_response(status_code):
    return MagicMock(spec=requests.Response, status_code=status_code)


def _check(client, **body):
    payload = {'url': DISK_URL, 'sha256': SHA, 'kind': 'vm'}
    payload.update(body)
    return client.post('/api/environments/check-url', json=payload)


def test_check_url_reachable_host(client):
    with patch('adare.webapi.routes.environments.requests.head', return_value=_head_response(200)) as head:
        body = _check(client).json()

    assert body['success'] is True
    assert set(body['data']) == CHECK_KEYS
    assert body['data'] == {'valid': True, 'reachable': True, 'status': 200, 'reason': None}
    args, kwargs = head.call_args
    assert args == (DISK_URL,)
    assert kwargs['allow_redirects'] is True
    assert kwargs['timeout'] > 0, 'a HEAD without a timeout can hang the worker forever'


@pytest.mark.parametrize(('status', 'reachable'), [(204, True), (399, True), (400, False), (404, False), (503, False)])
def test_check_url_status_threshold(client, status, reachable):
    with patch('adare.webapi.routes.environments.requests.head', return_value=_head_response(status)):
        data = _check(client).json()['data']

    assert data['valid'] is True
    assert data['reachable'] is reachable
    assert data['status'] == status
    if reachable:
        assert data['reason'] is None
    else:
        assert data['reason'] == f'Host returned HTTP {status}.'


@pytest.mark.parametrize(
    'exc',
    [requests.ConnectionError('refused'), requests.Timeout('slow'), requests.exceptions.SSLError('bad cert')],
)
def test_check_url_network_failure_is_a_result_not_a_rejection(client, exc):
    """use-environments.ts reads `data.data!` unwrapped: it must never see `success: false` here."""
    with patch('adare.webapi.routes.environments.requests.head', side_effect=exc):
        body = _check(client).json()

    assert body['success'] is True
    assert body['data']['valid'] is True
    assert body['data']['reachable'] is False
    assert body['data']['status'] is None
    assert body['data']['reason'].startswith('URL is not reachable: ')
    assert str(exc) in body['data']['reason']


@pytest.mark.parametrize(
    ('overrides', 'reason_fragment'),
    [
        ({'url': 'ftp://x.example/d.qcow2'}, 'http or https'),
        ({'url': '/local/d.qcow2'}, 'http or https'),
        ({'url': 'https:///d.qcow2'}, 'missing a host'),
        ({'sha256': None}, 'vm_sha256 is required'),
        ({'sha256': 'A' * 64}, '64 lowercase hex'),
        ({'kind': 'iso', 'url': UBUNTU_ISO, 'sha256': None}, 'iso_sha256 is required'),
        # a share link has no disk extension: the format hint is mandatory for a baked VM
        ({'url': 'https://cloud.example/s/TOKEN/download'}, 'vm_format is required'),
        ({'vm_format': 'iso'}, 'vm_format must be one of'),
    ],
)
def test_check_url_format_violation_never_touches_the_network(client, overrides, reason_fragment):
    with patch('adare.webapi.routes.environments.requests.head') as head:
        body = _check(client, **overrides).json()

    head.assert_not_called()
    assert body['success'] is True
    assert body['data']['valid'] is False
    assert body['data']['reachable'] is False
    assert body['data']['status'] is None
    assert reason_fragment in body['data']['reason']


def test_check_url_accepts_an_extensionless_share_link_when_a_vm_format_is_given(client):
    with patch('adare.webapi.routes.environments.requests.head', return_value=_head_response(200)):
        data = _check(client, url='https://cloud.example/s/TOKEN/download', vm_format='qcow2').json()['data']
    assert data['valid'] is True
    assert data['reachable'] is True


def test_check_url_iso_kind_needs_no_vm_format(client):
    with patch('adare.webapi.routes.environments.requests.head', return_value=_head_response(200)):
        data = _check(client, kind='iso', url='https://cloud.example/s/T/download').json()['data']
    assert data['valid'] is True


def test_check_url_rejects_an_unknown_kind_before_anything_runs(client):
    with patch('adare.webapi.routes.environments.requests.head') as head:
        response = _check(client, kind='floppy')
    assert response.status_code == 422
    head.assert_not_called()


# ---------------------------------------------------------------------------
# DELETE /api/environments/{name}
# ---------------------------------------------------------------------------


def test_delete_removes_the_environment_and_returns_a_null_payload(client, seed_env):
    seed_env('doomed')
    seed_env('kept')

    body = client.delete('/api/environments/doomed?force=false').json()

    # use-environments.ts only calls `assertOk` here, so `data` may be null but `success` must be true.
    assert body['success'] is True
    assert body['data'] is None
    assert [e['name'] for e in client.get('/api/environments').json()['data']] == ['kept']
    _assert_error_envelope(client.get('/api/environments/doomed'), 'EnvironmentNotFoundError')


def test_delete_accepts_a_ulid_as_well_as_a_name(client, seed_env):
    ulid_ = seed_env('doomed')
    assert client.delete(f'/api/environments/{ulid_}').json()['success'] is True
    assert client.get('/api/environments').json()['data'] == []


def test_delete_unknown_environment_is_a_200_error_envelope(client, seed_env):
    seed_env('kept')

    error = _assert_error_envelope(client.delete('/api/environments/missing'))

    assert 'missing' in error['message']
    assert [e['name'] for e in client.get('/api/environments').json()['data']] == ['kept']


def test_delete_defaults_to_not_forcing(client):
    with (
        patch('adare.services.environment_service.backend_environment_delete') as backend,
        patch(
            'adare.backend.environment.database.resolve_environment_identifier',
            return_value='01' * 13,
        ),
    ):
        client.delete('/api/environments/e')
    backend.assert_called_once_with('01' * 13, force=False)


def test_delete_passes_force_through_to_the_backend(client):
    with (
        patch('adare.services.environment_service.backend_environment_delete') as backend,
        patch(
            'adare.backend.environment.database.resolve_environment_identifier',
            return_value='01' * 13,
        ),
    ):
        assert client.delete('/api/environments/e?force=true').json()['success'] is True
    backend.assert_called_once_with('01' * 13, force=True)


def test_delete_refused_by_the_backend_is_an_error_envelope_with_the_reason(client):
    """The page toasts `error.message`; a refused delete must not look like success."""
    import logging

    refusal = EnvironmentDeletionError(
        logging.getLogger(__name__),
        'environment e has 2 experiment run(s), so it cannot be deleted',
        possible_solutions=['run with --force to delete all runs and the environment'],
    )
    with (
        patch('adare.services.environment_service.backend_environment_delete', side_effect=refusal),
        patch('adare.backend.environment.database.resolve_environment_identifier', return_value='01' * 13),
    ):
        error = _assert_error_envelope(client.delete('/api/environments/e'))

    assert 'cannot be deleted' in error['message']
    assert error['solutions'] == ['run with --force to delete all runs and the environment']


# ---------------------------------------------------------------------------
# POST /api/environments/{name}/verify   (service boundary mocked: it boots a VM)
# ---------------------------------------------------------------------------


@pytest.fixture
def verify_service():
    """Replace the two ExperimentService calls the route makes; nothing else is stubbed."""
    started = ExperimentRunStartedInfo(run_ulid=str(ulid.ULID()), experiment_name='verify_vm')
    setup = MagicMock(return_value=Result.ok('verify_vm'))
    run = AsyncMock(return_value=Result.ok(started))
    with (
        patch.object(ExperimentService, 'ensure_verify_setup', new=setup),
        patch.object(ExperimentService, 'run', new=run),
    ):
        yield MagicMock(setup=setup, run=run, started=started)


def test_verify_returns_the_run_ulid_the_dialog_navigates_to(client, verify_service):
    response = client.post('/api/environments/env1/verify', json={'project_path': '/work/proj'})

    body = response.json()
    assert response.status_code == 200
    assert body['success'] is True
    # verify-environment-dialog.tsx: navigate({to: '/runs', search: {focus: data.run_ulid}})
    assert body['data']['run_ulid'] == verify_service.started.run_ulid
    assert len(body['data']['run_ulid']) == 26
    assert body['data']['experiment_name'] == 'verify_vm'


def test_verify_attaches_the_builtin_experiment_then_runs_it_against_the_named_environment(client, verify_service):
    client.post('/api/environments/env1/verify', json={'project_path': '/work/proj'})

    verify_service.setup.assert_called_once_with(Path('/work/proj'), 'env1')
    verify_service.run.assert_awaited_once_with(Path('/work/proj'), 'verify_vm', 'env1')


def test_verify_setup_failure_is_an_error_envelope_and_never_starts_a_run(client, verify_service):
    verify_service.setup.return_value = Result.fail(
        code='EnvironmentNotFoundError', message="Environment 'env1' not found", solutions=['create it first']
    )

    error = _assert_error_envelope(
        client.post('/api/environments/env1/verify', json={'project_path': '/work/proj'}),
        'EnvironmentNotFoundError',
    )

    assert error['solutions'] == ['create it first']
    verify_service.run.assert_not_awaited()


def test_verify_run_start_failure_is_an_error_envelope(client, verify_service):
    verify_service.run.return_value = Result.fail(
        code='ExperimentRunStartError', message='Failed to start experiment run: boom', solutions=[]
    )

    _assert_error_envelope(
        client.post('/api/environments/env1/verify', json={'project_path': '/work/proj'}),
        'ExperimentRunStartError',
    )


def test_verify_without_a_project_path_is_rejected_by_validation(client, verify_service):
    response = client.post('/api/environments/env1/verify', json={})
    assert response.status_code == 422
    verify_service.setup.assert_not_called()


def test_verify_does_not_block_the_event_loop_while_the_setup_runs(client, verify_service):
    """ensure_verify_setup is sync and slow (registers an experiment): it must run off the loop."""
    seen = {}

    def _setup(project_path, name):
        try:
            asyncio.get_running_loop()
            seen['on_loop'] = True
        except RuntimeError:
            seen['on_loop'] = False
        return Result.ok('verify_vm')

    verify_service.setup.side_effect = _setup
    client.post('/api/environments/env1/verify', json={'project_path': '/work/proj'})
    assert seen == {'on_loop': False}


# ---------------------------------------------------------------------------
# environment-detail.tsx "Run history": run.experiment_name -> /experiments/$name
# ---------------------------------------------------------------------------


@pytest.fixture
def project_with_run(global_db, seed_env, tmp_path):
    """A registered project whose database holds one experiment run on env ``E``."""
    env_ulid = seed_env('E')
    project_dir = tmp_path / 'proj'
    project_dir.mkdir()
    with GlobalDatabaseApi() as db:
        db._session.add(Project(id=str(ulid.ULID()), name='Proj', description='', path=str(project_dir)))
    with ProjectDatabaseApi(project_dir) as db:
        experiment = Experiment(id=str(ulid.ULID()), name='exp1', sha256='x', environment_ids=[env_ulid])
        db._session.add(experiment)
        db._session.flush()
        db._session.add(ExperimentRun(id=str(ulid.ULID()), experiment_id=experiment.id, environment_id=env_ulid))
    return project_dir


def test_run_history_experiment_links_resolve_through_the_experiments_route(global_db, project_with_run):
    app = FastAPI()
    app.include_router(runs_router)
    app.include_router(experiments_router)
    http = TestClient(app)

    runs = http.get('/api/runs', params={'environment': 'E'}).json()
    assert runs['success'] is True
    (run,) = runs['data']
    # Fields environment-detail.tsx reads from each run row.
    assert run['environment_name'] == 'E'
    assert len(run['ulid']) == 26
    for key in ('status', 'start_time', 'duration_seconds'):
        assert key in run
    # The link target is `Project.experiment` dotnotation ...
    assert run['experiment_name'] == 'Proj.exp1'
    # ... and the experiment page must resolve exactly that string.
    detail = http.get(f'/api/experiments/{run["experiment_name"]}').json()
    assert detail['success'] is True
    assert detail['data']['name'] == 'exp1'
    assert detail['data']['dotnotation'] == 'Proj.exp1'


def test_run_history_is_filtered_to_the_environment_in_the_url(global_db, project_with_run):
    app = FastAPI()
    app.include_router(runs_router)
    http = TestClient(app)

    assert http.get('/api/runs', params={'environment': 'someone-else'}).json() == {'success': True, 'data': []}
