"""Run-time disk integrity: full hash once, then only when the disk changed."""

import hashlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from adare.backend.experiment.exceptions import ExperimentIntegrityError
from adare.backend.vm import commands

pytestmark = pytest.mark.unit


@pytest.fixture
def disk(tmp_path, monkeypatch):
    user_dir = tmp_path / 'evidence'
    user_dir.mkdir()
    disk = user_dir / 'ubuntu.qcow2'
    disk.write_bytes(b'disk bytes')
    monkeypatch.setattr('adare.config.configdirectory.STATE_DIR', tmp_path / 'state')
    record = SimpleNamespace(name='ubuntu', file=str(disk), hash=hashlib.sha256(b'disk bytes').hexdigest())
    monkeypatch.setattr(commands.vm_database, 'get_vm_by_id', lambda vm_id: record)
    return disk


def _hasher():
    async def full_hash(path, silent=True, interrupt_event=None):
        return hashlib.sha256(path.read_bytes()).hexdigest()

    return AsyncMock(side_effect=full_hash)


@pytest.mark.asyncio
async def test_unchanged_disk_is_hashed_once(disk):
    hasher = _hasher()
    with patch.object(commands.VMFileManager, 'calculate_file_hash_async', hasher):
        await commands.verify_vm_integrity('vm1')
        await commands.verify_vm_integrity('vm1')

    assert hasher.await_count == 1
    assert sorted(p.name for p in disk.parent.iterdir()) == ['ubuntu.qcow2']  # nothing written beside it


@pytest.mark.asyncio
async def test_modified_disk_is_rehashed_and_rejected(disk):
    hasher = _hasher()
    with patch.object(commands.VMFileManager, 'calculate_file_hash_async', hasher):
        await commands.verify_vm_integrity('vm1')
        disk.write_bytes(b'tampered disk bytes')
        with pytest.raises(ExperimentIntegrityError):
            await commands.verify_vm_integrity('vm1')

    assert hasher.await_count == 2
