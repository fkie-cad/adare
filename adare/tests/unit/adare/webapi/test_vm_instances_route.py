"""The /api/vm-instances endpoints against a real, seeded global database.

``vm-detail.tsx`` lists a VM's instances, removes them and manages their snapshots;
``vms-list.tsx`` bulk-removes stopped instances. The tests go through the real
service layer and assert the JSON those pages receive. Only the hypervisor boundary
(domain state, domain teardown, VirtualBox snapshot calls) is faked; no VM is
started and libvirt is never called.

Frontend expectations the backend does not meet are strict xfails: when the
backend (or the frontend contract) is fixed they flip to XPASS and fail the suite
until the marker is removed. (None are open at the moment.)
"""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adare.backend.vm.instance_manager import VmInstanceManager
from adare.backend.vm.snapshot_manager import SnapshotManager
from adare.database.api.vm import VmApi
from adare.database.models.global_models import Vm, VmInstance
from adare.database.reference_manager import reference_manager
from adare.webapi.routes.vm_instances import router

pytestmark = pytest.mark.unit

UNKNOWN_ID = '01ZZZZZZZZZZZZZZZZZZZZZZZZ'


# ---- fixtures ----


@pytest.fixture
def global_db(tmp_path):
    with (
        patch('adare.config.database.get_global_database_location', return_value=tmp_path / 'global.db'),
        patch.object(reference_manager, '_global_api', None),
        patch.object(reference_manager, '_cache', {}),
        patch.object(reference_manager, '_cache_timestamps', {}),
    ):
        yield


@pytest.fixture
def hypervisor_states():
    """instance_name -> hypervisor state; anything unlisted is stopped. The only fake in the removal path."""
    states: dict[str, str] = {}

    def state_of(_manager, instance):
        return states.get(instance.instance_name, 'poweroff')

    with (
        patch.object(VmInstanceManager, '_get_hypervisor_vm_state', autospec=True, side_effect=state_of),
        patch.object(VmInstanceManager, '_cleanup_hypervisor_instance', new_callable=AsyncMock) as teardown,
    ):
        states['_teardown'] = teardown  # exposed for call assertions; never matches an instance name
        yield states


@pytest.fixture
def client(global_db, hypervisor_states):
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _add_vm(name: str, hypervisor: str = 'qemu') -> str:
    with VmApi() as api:
        vm = Vm(name=name, file=f'/disks/{name}.qcow2', hash=name.ljust(64, '0'), hypervisor=hypervisor)
        api._session.add(vm)
        api._session.commit()
        return vm.id


def _add_instance(
    vm_id: str,
    name: str,
    status: str = 'available',
    port: int | None = None,
    vbox_uuid: str | None = None,
    base_snapshot: str | None = None,
    run_id: str | None = None,
) -> str:
    with VmApi() as api:
        instance = VmInstance(
            vm_id=vm_id,
            instance_name=name,
            status=status,
            websocket_port=port,
            vbox_uuid=vbox_uuid,
            base_snapshot_name=base_snapshot,
            current_experiment_run_id=run_id,
        )
        api._session.add(instance)
        api._session.commit()
        return instance.id


def _add_snapshot(instance_id: str, name: str, kind: str = 'experiment', description: str | None = None) -> None:
    with VmApi() as api:
        api.create_instance_snapshot_record(instance_id, name, kind, description=description)


def _instance_ids(client) -> set[str]:
    return {row['id'] for row in client.get('/api/vm-instances').json()['data']}


def _error(body: dict) -> dict:
    assert body['success'] is False
    assert 'data' not in body
    assert set(body['error']) == {'code', 'message', 'solutions'}
    assert isinstance(body['error']['solutions'], list)
    return body['error']


@pytest.fixture
def ubuntu(global_db):
    return _add_vm('ubuntu2404')


@pytest.fixture
def debian(global_db):
    return _add_vm('debian12')


# ---- GET /api/vm-instances ----


def test_list_empty(client):
    response = client.get('/api/vm-instances')

    assert response.status_code == 200
    assert response.json() == {'success': True, 'data': []}


def test_list_row_shape(client, ubuntu):
    instance_id = _add_instance(ubuntu, 'ubuntu2404_run_1', status='active', port=5901)

    body = client.get('/api/vm-instances').json()

    assert body['success'] is True
    assert body['data'] == [
        {
            'id': instance_id,
            'vm_name': 'ubuntu2404',
            'instance_name': 'ubuntu2404_run_1',
            'status': 'active',
            'websocket_port': 5901,
            'hypervisor': 'qemu',
            'vm_id': ubuntu,
            'current_experiment_run_id': None,
        }
    ]


def test_list_row_carries_the_run_live_links_to(client, ubuntu):
    _add_instance(ubuntu, 'ubuntu2404_run_1', status='active', port=5901, run_id='01RUNRUNRUNRUNRUNRUNRUNRUN')

    (row,) = client.get('/api/vm-instances').json()['data']

    assert row['current_experiment_run_id'] == '01RUNRUNRUNRUNRUNRUNRUNRUN'


def test_list_filters_by_the_vm_id_vm_detail_passes(client, ubuntu, debian):
    """vm-detail.tsx calls GET /api/vm-instances?vm_id=<the VM id from its URL>."""
    wanted = _add_instance(ubuntu, 'ubuntu2404_run_1')
    _add_instance(debian, 'debian12_run_1')

    rows = client.get(f'/api/vm-instances?vm_id={ubuntu}').json()['data']

    assert [row['id'] for row in rows] == [wanted]
    assert rows[0]['vm_name'] == 'ubuntu2404'


def test_list_filter_matches_nothing_for_an_instance_id(client, ubuntu):
    """What vm-detail shows after following the System page link: an instance id is no vm_id."""
    instance_id = _add_instance(ubuntu, 'ubuntu2404_run_1')

    assert client.get(f'/api/vm-instances?vm_id={instance_id}').json() == {'success': True, 'data': []}


def test_list_filter_for_unknown_vm_is_empty_not_an_error(client, ubuntu):
    _add_instance(ubuntu, 'ubuntu2404_run_1')

    assert client.get(f'/api/vm-instances?vm_id={UNKNOWN_ID}').json() == {'success': True, 'data': []}


def test_list_ids_are_ids_the_remove_and_snapshot_routes_resolve(client, ubuntu):
    """vm-detail.tsx uses instance.id for DELETE and for the snapshots panel."""
    instance_id = _add_instance(ubuntu, 'ubuntu2404_run_1')
    _add_snapshot(instance_id, 'checkpoint')

    row = client.get('/api/vm-instances').json()['data'][0]

    assert client.get(f'/api/vm-instances/{row["id"]}').json()['data']['instance_name'] == 'ubuntu2404_run_1'
    assert [s['name'] for s in client.get(f'/api/vm-instances/{row["id"]}/snapshots').json()['data']] == ['checkpoint']


def test_list_rows_carry_the_name_vm_detail_shows_and_watches(client, ubuntu):
    """vm-detail.tsx labels each row, and asks /api/vm-watch-url for the live view, by `instance_name`.

    Rewritten from a `name` expectation: the page was wrong to read `instance.name`. The
    instance name is the hypervisor domain name vm-watch-url resolves, and `vm_id` ties
    the row back to the VM (image) page it is listed on.
    """
    _add_instance(ubuntu, 'ubuntu2404_run_1')

    row = client.get('/api/vm-instances').json()['data'][0]

    assert row['instance_name'] == 'ubuntu2404_run_1'
    assert row['vm_id'] == ubuntu


# ---- GET /api/vm-instances/usage ----


def test_usage_empty(client):
    assert client.get('/api/vm-instances/usage').json() == {
        'success': True,
        'data': {
            'total_instances': 0,
            'active_instances': 0,
            'available_instances': 0,
            'cleanup_pending_instances': 0,
            'instances_by_vm': {},
        },
    }


def test_usage_counts_by_status_and_vm(client, ubuntu, debian):
    _add_instance(ubuntu, 'u1', status='active', port=5901)
    _add_instance(ubuntu, 'u2', status='available')
    _add_instance(debian, 'd1', status='available')
    _add_instance(debian, 'd2', status='cleanup_pending')

    data = client.get('/api/vm-instances/usage').json()['data']

    assert data['total_instances'] == 4
    assert data['active_instances'] == 1
    assert data['available_instances'] == 2
    assert data['cleanup_pending_instances'] == 1
    assert 'stopped_instances' not in data
    assert data['instances_by_vm'] == {'ubuntu2404': 2, 'debian12': 2}


def test_usage_is_not_captured_by_the_instance_id_route(client):
    """The literal path must win over /{instance_id} (a capture would report VmInstanceNotFoundError)."""
    assert client.get('/api/vm-instances/usage').json()['success'] is True


# ---- GET /api/vm-instances/{instance_id} ----


def test_get_returns_the_detail_shape(client, ubuntu):
    instance_id = _add_instance(
        ubuntu,
        'ubuntu2404_run_1',
        status='active',
        port=5901,
        vbox_uuid='uuid-1',
        base_snapshot='base',
        run_id='RUN1',
    )

    body = client.get(f'/api/vm-instances/{instance_id}').json()

    assert body['success'] is True
    data = body['data']
    assert datetime.fromisoformat(data.pop('created_at'))
    assert datetime.fromisoformat(data.pop('last_used_at'))
    assert data == {
        'id': instance_id,
        'vm_id': ubuntu,
        'vm_name': 'ubuntu2404',
        'instance_name': 'ubuntu2404_run_1',
        'status': 'active',
        'websocket_port': 5901,
        'vbox_uuid': 'uuid-1',
        'base_snapshot_name': 'base',
        'current_experiment_run_id': 'RUN1',
        'hypervisor': 'qemu',
    }


def test_get_exposes_the_vm_id_the_local_vm_route_resolves(client, ubuntu):
    """The detail row carries vm_id, so a link from an instance to its VM is possible."""
    instance_id = _add_instance(ubuntu, 'ubuntu2404_run_1')

    vm_id = client.get(f'/api/vm-instances/{instance_id}').json()['data']['vm_id']

    assert vm_id == ubuntu


def test_get_unknown_id_is_an_error_envelope_with_http_200(client):
    response = client.get(f'/api/vm-instances/{UNKNOWN_ID}')

    assert response.status_code == 200
    error = _error(response.json())
    assert error['code'] == 'VmInstanceNotFoundError'
    assert UNKNOWN_ID in error['message']
    assert error['solutions']


def test_get_rejects_a_vm_id(client, ubuntu):
    assert _error(client.get(f'/api/vm-instances/{ubuntu}').json())['code'] == 'VmInstanceNotFoundError'


# ---- DELETE /api/vm-instances/{instance_id} ----


def test_remove_a_stopped_instance(client, ubuntu, hypervisor_states):
    instance_id = _add_instance(ubuntu, 'ubuntu2404_run_1')
    keep = _add_instance(ubuntu, 'ubuntu2404_run_2')

    response = client.delete(f'/api/vm-instances/{instance_id}')

    assert response.status_code == 200
    assert response.json() == {'success': True, 'data': None}
    hypervisor_states['_teardown'].assert_awaited_once()
    assert _instance_ids(client) == {keep}


def test_remove_cascades_to_the_instance_snapshots(client, ubuntu):
    instance_id = _add_instance(ubuntu, 'ubuntu2404_run_1')
    _add_snapshot(instance_id, 'checkpoint')

    assert client.delete(f'/api/vm-instances/{instance_id}').json()['success'] is True

    with VmApi() as api:
        assert api.get_snapshots_for_instance(instance_id) == []


def test_remove_refuses_a_running_instance(client, ubuntu, hypervisor_states):
    """The frontend never sends force: a running instance must stay."""
    instance_id = _add_instance(ubuntu, 'ubuntu2404_run_1', status='active', port=5901)
    hypervisor_states['ubuntu2404_run_1'] = 'running'

    error = _error(client.delete(f'/api/vm-instances/{instance_id}').json())

    assert error['code'] == 'InstanceStateException'
    assert 'running' in error['message']
    assert _instance_ids(client) == {instance_id}


def test_remove_unknown_id_is_an_error_envelope(client):
    response = client.delete(f'/api/vm-instances/{UNKNOWN_ID}')

    assert response.status_code == 200
    error = _error(response.json())
    assert error['code'] == 'InstanceNotFoundException'
    assert UNKNOWN_ID in error['message']


# ---- DELETE /api/vm-instances ----


def test_remove_all_with_nothing_to_remove(client):
    assert client.delete('/api/vm-instances').json() == {
        'success': True,
        'data': {'removed_count': 0, 'removed_instances': [], 'failed_count': 0, 'failed_instances': []},
    }


def test_remove_all_removes_stopped_and_skips_running(client, ubuntu, debian, hypervisor_states):
    stopped_a = _add_instance(ubuntu, 'u1')
    stopped_b = _add_instance(debian, 'd1', status='cleanup_pending')
    running = _add_instance(ubuntu, 'u2', status='active', port=5901)
    hypervisor_states['u2'] = 'running'

    body = client.delete('/api/vm-instances').json()

    assert body['success'] is True
    assert body['data']['removed_count'] == 2
    assert set(body['data']['removed_instances']) == {stopped_a, stopped_b}
    assert body['data']['failed_count'] == 0
    assert _instance_ids(client) == {running}


def test_remove_all_is_not_captured_by_the_instance_id_route(client):
    """DELETE '' and DELETE '/{id}' are distinct routes."""
    assert client.delete('/api/vm-instances').json()['success'] is True


def test_remove_all_data_carries_the_removed_count_the_toast_prints(client, ubuntu):
    """use-vms.ts types the data as a VmInstanceCleanupResult and vms-list.tsx toasts `removed_count`.

    Rewritten from `data == 1`: the frontend was wrong to treat the object as a number.
    """
    instance_id = _add_instance(ubuntu, 'u1')

    data = client.delete('/api/vm-instances').json()['data']

    assert data == {
        'removed_count': 1,
        'removed_instances': [instance_id],
        'failed_count': 0,
        'failed_instances': [],
    }


# ---- GET /api/vm-instances/{instance_id}/snapshots ----


def test_snapshots_row_shape(client, ubuntu):
    instance_id = _add_instance(ubuntu, 'ubuntu2404_run_1', vbox_uuid='uuid-1')
    _add_snapshot(instance_id, 'checkpoint', kind='backup', description='before install')

    body = client.get(f'/api/vm-instances/{instance_id}/snapshots').json()

    assert body['success'] is True
    [snapshot] = body['data']
    assert datetime.fromisoformat(snapshot.pop('created_at'))
    assert snapshot.pop('id')
    assert snapshot == {
        'name': 'checkpoint',
        'snapshot_type': 'backup',
        'description': 'before install',
        'vm_id': None,
        'vm_instance_id': instance_id,
        'vbox_uuid': None,
    }


def test_snapshots_are_scoped_to_the_instance(client, ubuntu):
    first = _add_instance(ubuntu, 'ubuntu2404_run_1')
    second = _add_instance(ubuntu, 'ubuntu2404_run_2')
    _add_snapshot(first, 'a')
    _add_snapshot(first, 'b')
    _add_snapshot(second, 'c')

    names = [s['name'] for s in client.get(f'/api/vm-instances/{first}/snapshots').json()['data']]

    assert sorted(names) == ['a', 'b']


def test_snapshots_of_an_instance_without_any_are_empty(client, ubuntu):
    instance_id = _add_instance(ubuntu, 'ubuntu2404_run_1')

    assert client.get(f'/api/vm-instances/{instance_id}/snapshots').json() == {'success': True, 'data': []}


def test_snapshots_of_an_unknown_instance_are_not_found(client):
    error = _error(client.get(f'/api/vm-instances/{UNKNOWN_ID}/snapshots').json())

    assert error['code'] == 'VmInstanceNotFoundError'
    assert UNKNOWN_ID in error['message']


# ---- DELETE /api/vm-instances/{instance_id}/snapshots/{snapshot_name} ----


class _VirtualBoxVmStub:
    """The VirtualBox VM object (the hypervisor boundary): records the snapshot it was asked to delete."""

    def __init__(self, succeeds: bool = True):
        self.succeeds = succeeds
        self.deleted: list[str] = []

    def delete_snapshot(self, snapshot_name: str, silent: bool = False) -> bool:
        self.deleted.append(snapshot_name)
        return self.succeeds


@pytest.fixture
def vbox_tools():
    """SnapshotManager() builds a VirtualBoxManager, which needs VBoxManage on PATH: stand in for it."""
    with patch('adare.backend.vm.snapshot_manager.VirtualBoxManager', return_value=object()):
        yield


@pytest.fixture
def virtualbox(global_db, vbox_tools):
    return _add_vm('win11', hypervisor='virtualbox')


def _snapshot_names(client, instance_id: str) -> list[str]:
    return [s['name'] for s in client.get(f'/api/vm-instances/{instance_id}/snapshots').json()['data']]


def test_delete_snapshot(client, virtualbox):
    instance_id = _add_instance(virtualbox, 'win11_run_1', vbox_uuid='uuid-1', base_snapshot='base')
    _add_snapshot(instance_id, 'base', kind='base')
    _add_snapshot(instance_id, 'checkpoint')
    vm_stub = _VirtualBoxVmStub()

    with patch.object(SnapshotManager, '_get_vm_object', return_value=vm_stub):
        response = client.delete(f'/api/vm-instances/{instance_id}/snapshots/checkpoint')

    assert response.status_code == 200
    assert response.json() == {'success': True, 'data': None}
    assert vm_stub.deleted == ['checkpoint']
    assert _snapshot_names(client, instance_id) == ['base']


def test_delete_snapshot_decodes_a_percent_encoded_name(client, virtualbox):
    """endpoints.ts sends encodeURIComponent(name)."""
    instance_id = _add_instance(virtualbox, 'win11_run_1', vbox_uuid='uuid-1')
    _add_snapshot(instance_id, 'before install v2')
    vm_stub = _VirtualBoxVmStub()

    with patch.object(SnapshotManager, '_get_vm_object', return_value=vm_stub):
        body = client.delete(f'/api/vm-instances/{instance_id}/snapshots/before%20install%20v2').json()

    assert body['success'] is True
    assert vm_stub.deleted == ['before install v2']
    assert _snapshot_names(client, instance_id) == []


def test_delete_snapshot_protects_the_base_snapshot(client, virtualbox):
    instance_id = _add_instance(virtualbox, 'win11_run_1', vbox_uuid='uuid-1', base_snapshot='base')
    _add_snapshot(instance_id, 'base', kind='base')

    error = _error(client.delete(f'/api/vm-instances/{instance_id}/snapshots/base').json())

    assert error['code'] == 'VMError'
    assert 'protected' in error['message']
    assert _snapshot_names(client, instance_id) == ['base']


def test_delete_snapshot_reports_a_hypervisor_failure(client, virtualbox):
    instance_id = _add_instance(virtualbox, 'win11_run_1', vbox_uuid='uuid-1')
    _add_snapshot(instance_id, 'checkpoint')

    with patch.object(SnapshotManager, '_get_vm_object', return_value=_VirtualBoxVmStub(succeeds=False)):
        error = _error(client.delete(f'/api/vm-instances/{instance_id}/snapshots/checkpoint').json())

    assert error['code'] == 'SnapshotDeleteError'
    assert 'checkpoint' in error['message']
    assert error['solutions']
    assert _snapshot_names(client, instance_id) == ['checkpoint']


def test_delete_snapshot_of_a_qemu_instance_is_refused(client, ubuntu, vbox_tools):
    """Snapshots are VirtualBox-only: a QEMU run keeps none."""
    instance_id = _add_instance(ubuntu, 'ubuntu2404_run_1')
    _add_snapshot(instance_id, 'checkpoint')

    error = _error(client.delete(f'/api/vm-instances/{instance_id}/snapshots/checkpoint').json())

    assert error['code'] == 'SnapshotNotSupported'
    assert 'VirtualBox-only' in error['message']
    assert 'qemu' in error['message']
    assert error['solutions']
    assert _snapshot_names(client, instance_id) == ['checkpoint']


def test_delete_snapshot_of_an_unknown_instance_is_an_error_envelope(client):
    response = client.delete(f'/api/vm-instances/{UNKNOWN_ID}/snapshots/checkpoint')

    assert response.status_code == 200
    error = _error(response.json())
    assert error['code'] == 'VmInstanceNotFoundError'
    assert UNKNOWN_ID in error['message']


def test_delete_snapshot_without_virtualbox_installed_is_an_error_envelope(global_db, ubuntu):
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)
    instance_id = _add_instance(ubuntu, 'ubuntu2404_run_1')

    with patch('adare.hypervisor.executable_manager.shutil.which', return_value=None):
        response = client.delete(f'/api/vm-instances/{instance_id}/snapshots/checkpoint')

    assert response.status_code == 200
    assert response.json()['success'] is False


def test_delete_snapshot_of_a_virtualbox_instance_without_vboxmanage_is_an_error_envelope(global_db):
    """A VirtualBox instance on a host that lost VBoxManage: the HypervisorException becomes the envelope, not a 500."""
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app, raise_server_exceptions=False)
    instance_id = _add_instance(_add_vm('win11', hypervisor='virtualbox'), 'win11_run_1', vbox_uuid='uuid-1')

    with patch('adare.hypervisor.executable_manager.shutil.which', return_value=None):
        response = client.delete(f'/api/vm-instances/{instance_id}/snapshots/checkpoint')

    assert response.status_code == 200
    error = _error(response.json())
    assert error['code']
    assert 'VBoxManage' in error['message'] or 'VirtualBox' in error['message']


# ---- GET /api/vm-instances/{id}/logs[/{source}] (live.tsx log tail) ----

RUN_ID = '01RUNRUNRUNRUNRUNRUNRUNRUN'


@pytest.fixture
def run_logs(tmp_path):
    """A run directory with a logs/ folder the instance's run resolves to; no libvirt log."""
    run_dir = tmp_path / 'run'
    (run_dir / 'logs').mkdir(parents=True)
    run_dirs = {RUN_ID: run_dir}
    with (
        patch('adare.webapi.routes.runs._resolve_run_dir', side_effect=run_dirs.get),
        patch(
            'adare.webapi.routes.vm_instances._libvirt_log_candidates',
            return_value=[tmp_path / 'libvirt' / 'domain.log'],
        ),
    ):
        yield run_dir / 'logs'


@pytest.fixture
def running(client, ubuntu, run_logs):
    return _add_instance(ubuntu, 'ubuntu2404_run_1', status='active', port=5901, run_id=RUN_ID)


def test_logs_lists_the_run_logs(client, running, run_logs):
    (run_logs / 'adare.log').write_text('hello\n')
    (run_logs / 'adarevm.log').write_text('')
    (run_logs / 'notes.txt').write_text('not a log')

    body = client.get(f'/api/vm-instances/{running}/logs').json()

    assert body == {
        'success': True,
        'data': [
            {'key': 'run/adare.log', 'name': 'adare.log', 'size': 6},
            {'key': 'run/adarevm.log', 'name': 'adarevm.log', 'size': 0},
        ],
    }


def test_logs_include_a_readable_libvirt_log(client, running, tmp_path):
    (tmp_path / 'libvirt').mkdir()
    (tmp_path / 'libvirt' / 'domain.log').write_text('qemu started\n')

    keys = [s['key'] for s in client.get(f'/api/vm-instances/{running}/logs').json()['data']]

    assert keys == ['libvirt']


def test_logs_of_an_instance_without_a_run_are_empty(client, ubuntu, run_logs):
    instance_id = _add_instance(ubuntu, 'ubuntu2404_run_2', status='active', port=5902)

    assert client.get(f'/api/vm-instances/{instance_id}/logs').json() == {'success': True, 'data': []}


def test_logs_of_an_unknown_instance_are_not_found(client, run_logs):
    assert client.get(f'/api/vm-instances/{UNKNOWN_ID}/logs').status_code == 404


def test_log_read_without_offset_returns_the_whole_small_file(client, running, run_logs):
    (run_logs / 'adare.log').write_text('one\ntwo\n')

    data = client.get(f'/api/vm-instances/{running}/logs/run/adare.log').json()['data']

    assert data == {'text': 'one\ntwo\n', 'offset': 0, 'next_offset': 8, 'size': 8, 'reset': False}


def test_log_read_from_offset_returns_only_what_was_appended(client, running, run_logs):
    log = run_logs / 'adare.log'
    log.write_text('one\n')
    first = client.get(f'/api/vm-instances/{running}/logs/run/adare.log').json()['data']
    with log.open('a') as fh:
        fh.write('two\n')

    data = client.get(
        f'/api/vm-instances/{running}/logs/run/adare.log', params={'offset': first['next_offset']}
    ).json()['data']

    assert data['text'] == 'two\n'
    assert data['next_offset'] == 8
    assert data['reset'] is False


def test_log_read_at_the_end_returns_nothing(client, running, run_logs):
    (run_logs / 'adare.log').write_text('one\n')

    data = client.get(f'/api/vm-instances/{running}/logs/run/adare.log', params={'offset': 4}).json()['data']

    assert data['text'] == ''
    assert data['next_offset'] == 4


def test_log_read_past_a_truncated_file_resets(client, running, run_logs):
    (run_logs / 'adare.log').write_text('new\n')

    data = client.get(f'/api/vm-instances/{running}/logs/run/adare.log', params={'offset': 100}).json()['data']

    assert data == {'text': 'new\n', 'offset': 0, 'next_offset': 4, 'size': 4, 'reset': True}


def test_log_tail_of_a_big_file_starts_at_a_line_boundary(client, running, run_logs):
    from adare.webapi.routes.vm_instances import _LOG_TAIL_BYTES

    line = b'x' * 99 + b'\n'
    (run_logs / 'adare.log').write_bytes(line * (2 * _LOG_TAIL_BYTES // len(line)))

    data = client.get(f'/api/vm-instances/{running}/logs/run/adare.log').json()['data']

    assert data['next_offset'] == data['size']
    assert len(data['text']) <= _LOG_TAIL_BYTES
    assert data['text'].startswith('x' * 99 + '\n')
    assert data['offset'] % len(line) == 0


def test_log_chunk_short_of_the_end_stops_at_a_newline(client, running, run_logs):
    with patch('adare.webapi.routes.vm_instances._LOG_CHUNK_MAX_BYTES', 10):
        (run_logs / 'adare.log').write_text('abcd\nefgh\nijkl\n')

        data = client.get(f'/api/vm-instances/{running}/logs/run/adare.log', params={'offset': 0}).json()['data']

    assert data['text'] == 'abcd\nefgh\n'
    assert data['next_offset'] == 10


def test_log_read_of_an_unlisted_path_is_not_found(client, running, run_logs):
    (run_logs / 'adare.log').write_text('x\n')

    assert client.get(f'/api/vm-instances/{running}/logs/run/../../etc/passwd').status_code == 404
    assert client.get(f'/api/vm-instances/{running}/logs/run/missing.log').status_code == 404
