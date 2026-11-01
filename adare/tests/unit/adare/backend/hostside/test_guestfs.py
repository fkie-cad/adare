"""GuestFS over a real (small) ext4 image, the patched initial-state view, and the offline diff."""

import os
import shutil
import subprocess

import pytest

pytest.importorskip('dissect.extfs')

from adare.backend.hostside import fsdiff  # noqa: E402
from adare.backend.hostside.guestfs import (  # noqa: E402
    GuestFileNotFound,
    OfflineDiskGuestFS,
    PatchedGuestFS,
    StagedOp,
)

pytestmark = pytest.mark.unit

_MKE2FS = shutil.which('mke2fs') or next(
    (
        p
        for p in ('/opt/homebrew/opt/e2fsprogs/sbin/mke2fs', '/usr/local/opt/e2fsprogs/sbin/mke2fs', '/sbin/mke2fs')
        if os.access(p, os.X_OK)
    ),
    None,
)
needs_mke2fs = pytest.mark.skipif(_MKE2FS is None, reason='mke2fs (e2fsprogs) not installed')


def _make_image(tmp_path, name, files):
    src = tmp_path / f'{name}-src'
    for rel, content in files.items():
        path = src / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    (src / 'etc').mkdir(exist_ok=True)
    (src / 'etc' / 'os-release').write_text('NAME="Test"\n')
    os.symlink('/etc/os-release', src / 'os-link')
    image = tmp_path / f'{name}.img'
    subprocess.run(
        [_MKE2FS, '-q', '-t', 'ext4', '-O', '^has_journal', '-d', str(src), '-F', str(image), '4M'], check=True
    )
    return image


@pytest.fixture
def fs(tmp_path):
    image = _make_image(tmp_path, 'a', {'home/u/a.txt': b'hello\n', 'home/u/b.bin': b'\x00\x01'})
    with OfflineDiskGuestFS(image) as g:
        yield g


@needs_mke2fs
def test_read_stat_listdir(fs):
    assert fs.read_text('/home/u/a.txt') == 'hello\n'
    assert sorted(fs.listdir('/home/u')) == ['a.txt', 'b.bin']
    st = fs.stat('/home/u/a.txt')
    assert st.is_file and st.size == 6 and not st.is_dir
    assert fs.is_dir('/home/u') and fs.exists('/home/u/b.bin') and not fs.exists('/home/u/none')
    with pytest.raises(GuestFileNotFound):
        fs.stat('/nope')


@needs_mke2fs
def test_symlinks_are_followed_or_reported(fs):
    assert fs.read_text('/os-link') == 'NAME="Test"\n'
    lst = fs.stat('/os-link', follow=False)
    assert lst.is_symlink and lst.link_target == '/etc/os-release'


@needs_mke2fs
def test_glob_and_extract(fs, tmp_path):
    assert fs.glob('/home/*/a.txt') == ['/home/u/a.txt']
    out = fs.extract('/home/u', tmp_path / 'out')
    assert (out / 'a.txt').read_text() == 'hello\n'


@needs_mke2fs
def test_patched_view_applies_staged_operations(fs):
    ops = [
        StagedOp('write', '/home/u/new/doc.txt', content=b'x', uid=1000, gid=1000),
        StagedOp('remove', '/home/u/b.bin'),
        StagedOp('set_time', '/home/u/a.txt', atime=946684800.0),
    ]
    patched = PatchedGuestFS(fs, ops, now=1_700_000_000.0)
    assert patched.read_text('/home/u/new/doc.txt') == 'x'
    assert patched.is_dir('/home/u/new')
    assert not patched.exists('/home/u/b.bin')
    assert 'b.bin' not in patched.listdir('/home/u')
    assert patched.stat('/home/u/a.txt').atime == 946684800.0
    assert patched.read_text('/home/u/a.txt') == 'hello\n'  # base content untouched


@needs_mke2fs
def test_offline_diff_between_two_images(tmp_path):
    before = _make_image(tmp_path, 'before', {'home/u/a.txt': b'one', 'home/u/gone.txt': b'x'})
    after = _make_image(tmp_path, 'after', {'home/u/a.txt': b'two!', 'home/u/added.txt': b'y'})
    with OfflineDiskGuestFS(before) as b, OfflineDiskGuestFS(after) as a:
        result = fsdiff.diff(b, a)
    assert {e['path'] for e in result['added']} == {'/home/u/added.txt'}
    assert {e['path'] for e in result['removed']} == {'/home/u/gone.txt'}
    assert {e['path'] for e in result['modified']} >= {'/home/u/a.txt'}


def test_agent_footprint_classification():
    groups = fsdiff.classify_agent_footprint(
        ['/adare/run/adarevm.log', '/usr/lib/python3/dist-packages/adarevm/core.py', '/home/u/Documents/a.txt']
    )
    assert sum(len(v) for v in groups.values()) == 2
