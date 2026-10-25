"""Physical sizes and grouping of run disks by owner."""

import os

import pytest

from adare.backend.system.storage import StorageReport, _uncounted, group_disk_owners, physical_size

pytestmark = pytest.mark.unit


def _write(path, size):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(os.urandom(size))


def test_physical_size_of_file_tree_and_missing_path(tmp_path):
    _write(tmp_path / 'a' / 'one.bin', 10_000)
    _write(tmp_path / 'a' / 'b' / 'two.bin', 20_000)

    size, files = physical_size(tmp_path / 'a')

    assert files == 2
    assert size >= 30_000
    assert physical_size(tmp_path / 'missing') == (0, 0)


def test_sparse_file_counts_allocated_bytes_only(tmp_path):
    sparse = tmp_path / 'disk.qcow2'
    with open(sparse, 'wb') as f:
        f.truncate(1024**3)  # 1 GiB apparent, nothing written

    size, _ = physical_size(sparse)

    assert size < 1024**2


def test_disk_owners_are_grouped_and_classified(tmp_path):
    for name in (
        'ubuntu_exp_A-base.qcow2',
        'ubuntu_exp_A-nvram.fd',
        'ubuntu_exp_A-overlay-01XYZ.qcow2',
        'win_exp_B-base.qcow2',
        'gone_exp_C-base.qcow2',
        'gone_exp_C-nvram.fd',
    ):
        _write(tmp_path / name, 4096)
    _write(tmp_path / 'ubuntu_exp_A-overlay-01DEV' / 'snapshots' / 'cp1.qcow2', 4096)

    owners = {
        o.name: o
        for o in group_disk_owners(
            tmp_path, running={'ubuntu_exp_A'}, registered={'win_exp_B': 'available', 'ubuntu': None}
        )
    }

    assert set(owners) == {'ubuntu_exp_A', 'win_exp_B', 'gone_exp_C'}
    assert (owners['ubuntu_exp_A'].state, owners['ubuntu_exp_A'].files) == ('running', 4)
    assert (owners['win_exp_B'].state, owners['win_exp_B'].instance_status) == ('registered', 'available')
    assert (owners['gone_exp_C'].state, owners['gone_exp_C'].files) == ('orphaned', 2)

    report = StorageReport(computed_at=0, disk_owners=list(owners.values()))
    assert report.reclaimable_bytes == owners['gone_exp_C'].bytes


def test_uncounted_skips_directories_already_counted(tmp_path):
    _write(tmp_path / 'state' / 'vms' / 'env.qcow2', 50_000)
    _write(tmp_path / 'state' / 'global.db', 4096)
    _write(tmp_path / 'logs' / 'x.log', 4096)

    size, files = _uncounted(tmp_path, {(tmp_path / 'state' / 'vms').resolve()})

    assert files == 2
    assert size < 50_000
