"""Tests for the ``<file>.sha256`` sidecar digest cache."""

import hashlib
import json
import os

import pytest

from adare.helperfunctions import digest_cache
from adare.helperfunctions.digest_cache import cached_file_sha256, record_file_sha256, sidecar_path

pytestmark = pytest.mark.unit


class _CountingHash:
    def __init__(self):
        self.calls = 0

    def __call__(self, path):
        self.calls += 1
        return hashlib.sha256(path.read_bytes()).hexdigest()


def test_second_call_is_served_from_sidecar(tmp_path):
    iso = tmp_path / 'os.iso'
    iso.write_bytes(b'installer bytes')
    compute = _CountingHash()

    first = cached_file_sha256(iso, compute=compute)
    second = cached_file_sha256(iso, compute=compute)

    assert first == second == hashlib.sha256(b'installer bytes').hexdigest()
    assert compute.calls == 1
    entry = json.loads(sidecar_path(iso).read_text())
    st = iso.stat()
    assert (entry['size'], entry['mtime_ns'], entry['inode']) == (st.st_size, st.st_mtime_ns, st.st_ino)


def test_mtime_change_invalidates(tmp_path):
    iso = tmp_path / 'os.iso'
    iso.write_bytes(b'aaaa')
    compute = _CountingHash()
    cached_file_sha256(iso, compute=compute)

    # Same size, different content: only the mtime gives it away.
    iso.write_bytes(b'bbbb')
    st = iso.stat()
    os.utime(iso, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))

    assert cached_file_sha256(iso, compute=compute) == hashlib.sha256(b'bbbb').hexdigest()
    assert compute.calls == 2


def test_size_change_invalidates(tmp_path):
    iso = tmp_path / 'os.iso'
    iso.write_bytes(b'aaaa')
    compute = _CountingHash()
    cached_file_sha256(iso, compute=compute)
    st = iso.stat()

    iso.write_bytes(b'aaaaaaaa')
    # Restore the old mtime so only the size differs.
    os.utime(iso, ns=(st.st_atime_ns, st.st_mtime_ns))

    assert cached_file_sha256(iso, compute=compute) == hashlib.sha256(b'aaaaaaaa').hexdigest()
    assert compute.calls == 2


def test_replaced_file_invalidates_via_inode(tmp_path):
    iso = tmp_path / 'os.iso'
    iso.write_bytes(b'aaaa')
    compute = _CountingHash()
    cached_file_sha256(iso, compute=compute)
    st = iso.stat()

    replacement = tmp_path / 'new.iso'
    replacement.write_bytes(b'cccc')
    os.utime(replacement, ns=(st.st_atime_ns, st.st_mtime_ns))
    os.replace(replacement, iso)

    assert cached_file_sha256(iso, compute=compute) == hashlib.sha256(b'cccc').hexdigest()
    assert compute.calls == 2


def test_record_seeds_the_cache(tmp_path):
    iso = tmp_path / 'os.iso'
    iso.write_bytes(b'downloaded')
    digest = hashlib.sha256(b'downloaded').hexdigest()
    record_file_sha256(iso, digest.upper())
    compute = _CountingHash()

    assert cached_file_sha256(iso, compute=compute) == digest
    assert compute.calls == 0


def test_foreign_checksum_file_is_neither_trusted_nor_overwritten(tmp_path):
    iso = tmp_path / 'os.iso'
    iso.write_bytes(b'installer')
    foreign = sidecar_path(iso)
    foreign.write_text(f'{"0" * 64}  os.iso\n')
    compute = _CountingHash()

    assert cached_file_sha256(iso, compute=compute) == hashlib.sha256(b'installer').hexdigest()
    assert cached_file_sha256(iso, compute=compute) == hashlib.sha256(b'installer').hexdigest()
    assert compute.calls == 2
    assert foreign.read_text() == f'{"0" * 64}  os.iso\n'


def test_unwritable_sidecar_is_not_fatal(tmp_path, monkeypatch):
    iso = tmp_path / 'os.iso'
    iso.write_bytes(b'installer')

    def _fail(*_args, **_kwargs):
        raise PermissionError('read-only directory')

    monkeypatch.setattr(digest_cache.os, 'replace', _fail)

    assert cached_file_sha256(iso) == hashlib.sha256(b'installer').hexdigest()
    assert not sidecar_path(iso).exists()
    assert not (tmp_path / 'os.iso.sha256.tmp').exists()


def test_ctime_change_alone_invalidates(tmp_path):
    """An in-place edit can restore size and mtime (utime), but not ctime."""
    disk = tmp_path / 'disk.qcow2'
    disk.write_bytes(b'original')
    compute = _CountingHash()
    cached_file_sha256(disk, compute=compute)
    sidecar = sidecar_path(disk)
    entry = json.loads(sidecar.read_text())
    entry['ctime_ns'] -= 1_000_000_000  # the file's ctime moved on since it was cached
    sidecar.write_text(json.dumps(entry))

    cached_file_sha256(disk, compute=compute)

    assert compute.calls == 2


def test_external_cache_file_leaves_the_files_directory_alone(tmp_path):
    user_dir = tmp_path / 'evidence'
    user_dir.mkdir()
    disk = user_dir / 'disk.qcow2'
    disk.write_bytes(b'bytes')
    cache_file = tmp_path / 'state' / 'digests' / 'disk.json'

    digest = cached_file_sha256(disk, cache_file=cache_file)

    assert sorted(p.name for p in user_dir.iterdir()) == ['disk.qcow2']
    assert digest_cache.fresh_cached_sha256(disk, cache_file) == digest
    disk.write_bytes(b'changed')
    assert digest_cache.fresh_cached_sha256(disk, cache_file) is None


def test_record_with_pre_hash_stat_does_not_bless_a_concurrent_change(tmp_path):
    disk = tmp_path / 'disk.qcow2'
    disk.write_bytes(b'v1')
    stat_before = disk.stat()
    disk.write_bytes(b'v2, longer')  # changed while "hashing"

    record_file_sha256(disk, hashlib.sha256(b'v1').hexdigest(), st=stat_before)

    assert digest_cache.fresh_cached_sha256(disk) is None
