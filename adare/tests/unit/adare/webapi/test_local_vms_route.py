"""The /api/local-vms endpoints against a real, seeded global database.

The React pages (``vms-list.tsx``, ``vm-detail.tsx``, ``system.tsx``) read ids and
fields straight off these responses, so the tests go through the real service layer
and assert the JSON the frontend actually receives. Only the hypervisor boundary
(domain state, domain deletion) is faked; no VM is started and libvirt is never
called.

Frontend expectations that the backend does not meet are encoded as strict xfails:
when the backend (or the frontend contract) is fixed they flip to XPASS and fail
the suite until the marker is removed.
"""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adare.backend.system.host import HostSnapshot, VmProcess
from adare.config import configdirectory
from adare.database.api.environment import EnvironmentDbApi
from adare.database.api.vm import VmApi
from adare.database.models.global_models import OsInfo, Vm, VmInstance
from adare.database.reference_manager import reference_manager
from adare.webapi.routes.local_vms import router as local_vms_router
from adare.webapi.routes.system import router as system_router

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
def vms_dir(tmp_path, global_db):
    managed = tmp_path / 'vms'
    managed.mkdir()
    # VMS_DIR is imported by name in several modules; patch each user of it
    with (
        patch.object(configdirectory, 'VMS_DIR', managed),
        patch('adare.database.api.vm.core.VMS_DIR', managed),
    ):
        yield managed


@pytest.fixture
def hypervisor():
    """No real hypervisor: instances are stopped, and delete_vm drops the row like the real one."""

    async def delete_vm(vm_id, force=False):
        with VmApi() as api:
            return api.delete_vm(vm_id)

    with (
        patch('adare.backend.vm.instance_manager.get_instance_hypervisor_state', return_value='not_found'),
        patch('adare.backend.vm.commands.delete_vm', side_effect=delete_vm) as fake_delete,
    ):
        yield fake_delete


@pytest.fixture
def client(vms_dir, hypervisor):
    app = FastAPI()
    app.include_router(local_vms_router)
    app.include_router(system_router)
    return TestClient(app)


def _add_vm(name: str, disk: Path, hypervisor: str = 'qemu', platform: str | None = 'linux') -> str:
    with VmApi() as api:
        osinfo_id = None
        if platform:
            osinfo = OsInfo(
                platform=platform,
                os='Linux',
                distribution='Ubuntu',
                version='24.04',
                language='en',
                architecture='arm64',
            )
            api._session.add(osinfo)
            api._session.flush()
            osinfo_id = osinfo.id
        vm = Vm(
            name=name,
            file=str(disk),
            hash=name.ljust(64, '0'),
            description=f'{name} image',
            hypervisor=hypervisor,
            osinfo_id=osinfo_id,
        )
        api._session.add(vm)
        api._session.commit()
        return vm.id


def _add_instance(vm_id: str, name: str, status: str = 'available', owner_pid: int | None = None, port=None) -> str:
    with VmApi() as api:
        instance = VmInstance(vm_id=vm_id, instance_name=name, status=status, owner_pid=owner_pid, websocket_port=port)
        api._session.add(instance)
        api._session.commit()
        return instance.id


def _add_env(name: str, vm_id: str) -> str:
    with EnvironmentDbApi() as db:
        return db.create_environment_version(
            name=name,
            description='',
            vm_id=vm_id,
            vm_hash=None,
            tags=[],
            installations=[],
            environment_file=Path(f'/envs/{name}.yml'),
            sha256hash='b' * 64,
            hypervisor='qemu',
        ).id


@pytest.fixture
def ubuntu(vms_dir):
    """A registered VM whose disk is in managed storage."""
    return _add_vm('ubuntu2404', vms_dir / 'ubuntu2404.qcow2')


def _error(body: dict) -> dict:
    assert body['success'] is False
    assert 'data' not in body
    assert set(body['error']) == {'code', 'message', 'solutions'}
    assert isinstance(body['error']['solutions'], list)
    return body['error']


# ---- GET /api/local-vms ----


def test_list_empty(client):
    response = client.get('/api/local-vms')

    assert response.status_code == 200
    assert response.json() == {'success': True, 'data': []}


def test_list_row_shape(client, vms_dir):
    vm_id = _add_vm('ubuntu2404', vms_dir / 'ubuntu2404.qcow2')
    _add_instance(vm_id, 'ubuntu2404_run_1')
    _add_instance(vm_id, 'ubuntu2404_run_2', status='active', port=5901)

    body = client.get('/api/local-vms').json()

    assert body['success'] is True
    assert body['data'] == [
        {
            'id': vm_id,
            'name': 'ubuntu2404',
            'description': 'ubuntu2404 image',
            'file_hash': 'ubuntu2404000000' + '...',
            'hypervisor': 'qemu',
            'os_platform': 'linux',
            'instance_count': 2,
        }
    ]


def test_list_defaults_without_osinfo(client, vms_dir):
    _add_vm('bare', vms_dir / 'bare.qcow2', platform=None)

    row = client.get('/api/local-vms').json()['data'][0]

    assert row['os_platform'] is None
    assert row['instance_count'] == 0


def test_list_ids_are_vm_ids_the_detail_route_resolves(client, vms_dir):
    """vms-list.tsx links each row to /vms/$instanceId with vm.id; vm-detail feeds it to /api/local-vms/{id}."""
    first = _add_vm('first', vms_dir / 'first.qcow2')
    second = _add_vm('second', vms_dir / 'second.qcow2')

    rows = client.get('/api/local-vms').json()['data']

    assert {row['id'] for row in rows} == {first, second}
    for row in rows:
        detail = client.get(f'/api/local-vms/{row["id"]}').json()
        assert detail['success'] is True
        assert detail['data']['name'] == row['name']


@pytest.mark.xfail(
    strict=True,
    reason='vms-list.tsx renders vm.path in its "Path" column, but VmListItem has no `path` '
    '(only file_hash), so the column is always an em dash',
)
def test_list_rows_carry_the_path_vms_list_renders(client, vms_dir):
    _add_vm('ubuntu2404', vms_dir / 'ubuntu2404.qcow2')

    row = client.get('/api/local-vms').json()['data'][0]

    assert row['path'] == str(vms_dir / 'ubuntu2404.qcow2')


# ---- GET /api/local-vms/{vm_id} ----


def test_get_returns_the_detail_shape(client, vms_dir):
    disk = vms_dir / 'ubuntu2404.qcow2'
    vm_id = _add_vm('ubuntu2404', disk)
    _add_instance(vm_id, 'ubuntu2404_run_1')

    body = client.get(f'/api/local-vms/{vm_id}').json()

    assert body['success'] is True
    assert body['data'] == {
        'id': vm_id,
        'name': 'ubuntu2404',
        'file_path': str(disk),
        'file_hash': 'ubuntu2404'.ljust(64, '0'),
        'description': 'ubuntu2404 image',
        'hypervisor': 'qemu',
        'use_snapshots': True,
        'os_platform': 'linux',
        'os_type': 'Linux',
        'os_distribution': 'Ubuntu',
        'os_version': '24.04',
        'os_language': 'en',
        'os_architecture': 'arm64',
        'instance_count': 1,
        'is_external': False,
        'next_steps': [],
        'tip': None,
    }


def test_get_flags_a_disk_outside_managed_storage_as_external(client, tmp_path):
    vm_id = _add_vm('external', tmp_path / 'elsewhere' / 'disk.qcow2')

    assert client.get(f'/api/local-vms/{vm_id}').json()['data']['is_external'] is True


def test_get_unknown_id_is_an_error_envelope_with_http_200(client):
    response = client.get(f'/api/local-vms/{UNKNOWN_ID}')

    assert response.status_code == 200
    error = _error(response.json())
    assert error['code'] == 'VMNotFoundError'
    assert UNKNOWN_ID in error['message']
    assert error['solutions']


def test_get_by_vm_name_is_not_found(client, ubuntu):
    """The detail route takes a ULID; vm-detail never passes a name."""
    assert _error(client.get('/api/local-vms/ubuntu2404').json())['code'] == 'VMNotFoundError'


def test_get_rejects_an_instance_id(client, ubuntu):
    """Root of the System page bug: a VMInstance id is not a VM id."""
    instance_id = _add_instance(ubuntu, 'ubuntu2404_run_1')

    assert _error(client.get(f'/api/local-vms/{instance_id}').json())['code'] == 'VMNotFoundError'


@pytest.mark.xfail(
    strict=True,
    reason='vm-detail.tsx reads vmQuery.data.path for the page description, but VmInfo only has `file_path`',
)
def test_get_carries_the_path_vm_detail_renders(client, vms_dir):
    disk = vms_dir / 'ubuntu2404.qcow2'
    vm_id = _add_vm('ubuntu2404', disk)

    assert client.get(f'/api/local-vms/{vm_id}').json()['data']['path'] == str(disk)


# ---- the System page link (system.tsx:65 -> vm-detail.tsx) ----


@pytest.mark.xfail(
    strict=True,
    reason='system.tsx links running VMs to /vms/$instanceId with vm.instance_id (a VmInstance id), but '
    'vm-detail.tsx resolves that param via GET /api/local-vms/{id}, which only knows VM ids, so the page '
    'shows VMNotFoundError. /api/system/resources exposes no vm_id to link with.',
)
def test_system_running_vm_link_id_resolves_to_a_vm(client, ubuntu):
    _add_instance(ubuntu, 'ubuntu2404_run_1', status='active', port=5901)
    host = HostSnapshot(
        cpu_count=8,
        cpu_percent=1.0,
        load_average=(0.1, 0.1, 0.1),
        memory_total_bytes=1,
        memory_available_bytes=1,
        memory_used_bytes=0,
        swap_total_bytes=0,
        swap_used_bytes=0,
        disks=[],
        vms=[VmProcess(4242, 'ubuntu2404_run_1', 2**30, 10.0, 1_700_000_000.0, memory_mb=4096, cpus=4)],
    )
    with patch('adare.services.system_service.host_snapshot', return_value=host):
        resources = client.get('/api/system/resources').json()

    running = resources['data']['vms'][0]
    # Sanity: the system page does get a registered-instance id for this process
    assert running['instance_id']
    # The id the page can link a VM detail with: prefer a VM id, else what it links with today
    link_id = running.get('vm_id') or running['instance_id']

    detail = client.get(f'/api/local-vms/{link_id}').json()

    assert detail['success'] is True
    assert detail['data']['id'] == ubuntu


# ---- DELETE /api/local-vms/{vm_id} ----


def test_delete_removes_the_vm_and_its_instances(client, ubuntu, hypervisor):
    _add_instance(ubuntu, 'ubuntu2404_run_1')
    other = _add_vm('other', Path('/elsewhere/other.qcow2'))

    response = client.delete(f'/api/local-vms/{ubuntu}')

    assert response.status_code == 200
    assert response.json() == {'success': True, 'data': None}
    hypervisor.assert_called_once_with(ubuntu, force=False)
    assert [row['id'] for row in client.get('/api/local-vms').json()['data']] == [other]
    with VmApi() as api:
        assert api.get_all_vm_instances() == []


def test_delete_passes_the_force_flag_the_frontend_always_sends(client, ubuntu, hypervisor):
    """vms-list.tsx and vm-detail.tsx both call DELETE ...?force=true."""
    body = client.delete(f'/api/local-vms/{ubuntu}?force=true').json()

    assert body == {'success': True, 'data': None}
    hypervisor.assert_called_once_with(ubuntu, force=True)


def test_delete_keeps_a_disk_outside_managed_storage(client, tmp_path):
    disk = tmp_path / 'external.qcow2'
    disk.write_bytes(b'disk')
    vm_id = _add_vm('external', disk)

    assert client.delete(f'/api/local-vms/{vm_id}').json()['success'] is True
    assert disk.exists()


def test_delete_removes_a_managed_disk(client, vms_dir):
    disk = vms_dir / 'managed.qcow2'
    disk.write_bytes(b'disk')
    vm_id = _add_vm('managed', disk)

    assert client.delete(f'/api/local-vms/{vm_id}').json()['success'] is True
    assert not disk.exists()


def test_delete_unknown_id_is_an_error_envelope(client):
    response = client.delete(f'/api/local-vms/{UNKNOWN_ID}')

    assert response.status_code == 200
    error = _error(response.json())
    assert error['code'] == 'VMNotFoundError'
    assert UNKNOWN_ID in error['message']


def test_delete_refuses_a_vm_an_environment_uses(client, ubuntu):
    _add_env('ubuntu', ubuntu)

    error = _error(client.delete(f'/api/local-vms/{ubuntu}?force=true').json())

    assert error['code'] == 'VMInUseByEnvironmentError'
    assert 'ubuntu' in error['message']
    assert error['solutions']
    # refusal changed nothing
    assert [row['id'] for row in client.get('/api/local-vms').json()['data']] == [ubuntu]


def test_delete_refuses_a_vm_with_a_live_instance_even_when_forced(client, ubuntu):
    _add_instance(ubuntu, 'ubuntu2404_run_1', status='active', owner_pid=os.getpid(), port=5901)

    error = _error(client.delete(f'/api/local-vms/{ubuntu}?force=true').json())

    assert error['code'] == 'VMRemovalError'
    assert 'ubuntu2404_run_1' in error['message']
    assert [row['id'] for row in client.get('/api/local-vms').json()['data']] == [ubuntu]


def test_delete_takes_a_stale_active_instance_along(client, ubuntu):
    """A crashed run leaves status=active with a dead owner pid: that is not live."""
    _add_instance(ubuntu, 'ubuntu2404_run_1', status='active', owner_pid=2**22 + 12345, port=5901)

    assert client.delete(f'/api/local-vms/{ubuntu}').json() == {'success': True, 'data': None}
