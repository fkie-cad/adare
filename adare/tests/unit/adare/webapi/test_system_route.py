"""The /api/system endpoints return the service's data in the standard envelope."""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from adare.backend.system.host import DiskUsage, HostSnapshot, VmProcess
from adare.webapi.routes.system import router

pytestmark = pytest.mark.unit

GIB = 1024**3


@pytest.fixture
def client(tmp_path):
    app = FastAPI()
    app.include_router(router)
    with patch('adare.config.database.get_global_database_location', return_value=tmp_path / 'global.db'):
        yield TestClient(app)


def _snapshot():
    return HostSnapshot(
        cpu_count=8,
        cpu_percent=12.5,
        load_average=(0.5, 0.4, 0.3),
        memory_total_bytes=32 * GIB,
        memory_available_bytes=20 * GIB,
        memory_used_bytes=12 * GIB,
        swap_total_bytes=0,
        swap_used_bytes=0,
        disks=[DiskUsage('/adare', 1000 * GIB, 400 * GIB, 600 * GIB)],
        vms=[VmProcess(42, 'ubuntu_exp_A', 3 * GIB, 55.0, 1_700_000_000.0, memory_mb=4096, cpus=4)],
    )


def test_resources(client):
    with patch('adare.services.system_service.host_snapshot', return_value=_snapshot()):
        body = client.get('/api/system/resources').json()

    assert body['success'] is True
    data = body['data']
    assert data['cpu'] == {'count': 8, 'percent': 12.5, 'load_average': [0.5, 0.4, 0.3]}
    assert data['disks'][0]['percent'] == 40.0
    assert data['vms'][0]['name'] == 'ubuntu_exp_A'
    assert data['vm_totals'] == {'count': 1, 'rss_bytes': 3 * GIB, 'cpu_percent': 55.0}


def test_capacity_without_environments(client):
    with patch('adare.services.system_service.host_snapshot', return_value=_snapshot()):
        body = client.get('/api/system/capacity').json()

    assert body['success'] is True
    assert body['data']['environments'] == []
    assert body['data']['headroom']['cpu_cores'] == 7.0


def test_history_and_run_usage_start_empty(client):
    assert client.get('/api/system/history?hours=6').json()['data'] == []
    assert client.get('/api/system/run-usage').json()['data'] == []


def test_history_rejects_out_of_range_hours(client):
    assert client.get('/api/system/history?hours=0').status_code == 422


def test_failure_is_reported_in_the_envelope(client):
    with patch('adare.services.system_service.host_snapshot', side_effect=OSError('no /proc')):
        body = client.get('/api/system/resources').json()

    assert body['success'] is False
    assert 'no /proc' in body['error']['message']
