"""Archive paths for file testfunctions: syntax, format detection, safe extraction."""

import bz2
import gzip
import io
import lzma
import os
import tarfile
import zipfile

import pytest

from adarelib.testset.archive import (
    DEFAULT_MAX_BYTES,
    MAX_BYTES_ENV,
    ArchiveError,
    detect_format,
    has_archive_separator,
    join_archive_path,
    mapping_errors,
    max_bytes_from_env,
    normalize_dst,
    normalize_test_parameters,
    resolve_archive_path,
    split_archive_path,
)

pytestmark = pytest.mark.unit

CONFIG = b'{"name": "app", "port": 8080}\n'


# --- helpers ---------------------------------------------------------------


def _tar(path, members, mode='w'):
    """members: {name: bytes}; written with tarfile so names are exactly as given."""
    with tarfile.open(path, mode) as tar:
        for name, data in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return str(path)


def _zip(path, members):
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return str(path)


def _resolve(dst, workdir, **kwargs):
    archive, members = split_archive_path(dst)
    return resolve_archive_path(archive, members, str(workdir), **kwargs)


def _read(path):
    with open(path, 'rb') as f:
        return f.read()


@pytest.fixture
def work(tmp_path):
    d = tmp_path / 'work'
    d.mkdir()
    return d


# --- syntax ----------------------------------------------------------------


@pytest.mark.parametrize(
    ('dst', 'expected'),
    [
        ('/h/b.tar.gz!/etc/app/config.json', ('/h/b.tar.gz', ['etc/app/config.json'])),
        ('/var/log/syslog.2.gz!', ('/var/log/syslog.2.gz', [''])),
        ('/h/outer.zip!/inner.tar.gz!/data.json', ('/h/outer.zip', ['inner.tar.gz', 'data.json'])),
        ('/h/backup-*.zip!/logs/app-*.log', ('/h/backup-*.zip', ['logs/app-*.log'])),
        ('C:\\b.zip!/x.json', ('C:\\b.zip', ['x.json'])),
        ('/h/a.zip!/', ('/h/a.zip', [''])),
        ('/h/plain.txt', ('/h/plain.txt', [])),
        ('/h/wow!.txt', ('/h/wow!.txt', [])),  # '!' not followed by '/' is part of the name
        ('/h/log[!a].zip!/x', ('/h/log[!a].zip', ['x'])),  # '!' in a glob bracket is not a separator
        ('/h/[!/]x', ('/h/[!/]x', [])),
    ],
)
def test_split_archive_path(dst, expected):
    assert split_archive_path(dst) == expected
    assert has_archive_separator(dst) == bool(expected[1])


def test_join_is_inverse_of_split():
    for dst in ('/a.tar!/x/y', '/s.gz!', '/o.zip!/i.gz!'):
        assert join_archive_path(*split_archive_path(dst)) == dst


def test_normalize_dst_mapping():
    assert normalize_dst({'archive': '/b.tar.gz', 'member': 'etc/x.json'}) == '/b.tar.gz!/etc/x.json'
    assert normalize_dst({'archive': '/b.tar.gz', 'member': '/etc/x.json'}) == '/b.tar.gz!/etc/x.json'
    assert normalize_dst({'archive': '/s.gz'}) == '/s.gz!'
    assert normalize_dst('/plain') == '/plain'


@pytest.mark.parametrize(
    'value',
    [{'member': 'x'}, {'archive': ''}, {'archive': '/a.zip', 'format': 'zip'}, {'archive': '/a.zip', 'member': 3}],
)
def test_malformed_mapping(value):
    assert mapping_errors(value)
    with pytest.raises(ValueError):
        normalize_dst(value)


def test_normalize_test_parameters():
    test = {'name': 't', 'parameter': {'dst': {'archive': '/a.zip', 'member': 'x'}, 'k': 1}}
    assert normalize_test_parameters(test)['parameter'] == {'dst': '/a.zip!/x', 'k': 1}
    plain = {'name': 't', 'parameter': {'dst': '/x'}}
    assert normalize_test_parameters(plain) is plain


def test_max_bytes_from_env(monkeypatch):
    monkeypatch.delenv(MAX_BYTES_ENV, raising=False)
    assert max_bytes_from_env() == DEFAULT_MAX_BYTES
    monkeypatch.setenv(MAX_BYTES_ENV, '1024')
    assert max_bytes_from_env() == 1024
    monkeypatch.setenv(MAX_BYTES_ENV, 'lots')
    assert max_bytes_from_env() == DEFAULT_MAX_BYTES


# --- format detection and members --------------------------------------------

TAR_MODES = {'b.tar': ('w', 'tar'), 'b.tar.gz': ('w:gz', 'tar.gzip'), 'b.tgz': ('w:gz', 'tar.gzip'),
             'b.tar.bz2': ('w:bz2', 'tar.bzip2'), 'b.tar.xz': ('w:xz', 'tar.xz')}  # fmt: skip


@pytest.mark.parametrize('name', sorted(TAR_MODES))
def test_tar_member(tmp_path, work, name):
    mode, fmt = TAR_MODES[name]
    archive = _tar(tmp_path / name, {'./etc/app/config.json': CONFIG, 'etc/other': b'x'}, mode)
    assert detect_format(archive) == fmt

    res = _resolve(f'{archive}!/etc/app/config.json', work)

    assert not res.status
    assert [_read(p) for p in res.paths] == [CONFIG]
    assert res.details[0].startswith(f'archive member: etc/app/config.json from {archive} sha256=')
    assert res.details[0].endswith(f', {len(CONFIG)} bytes')
    assert res.display == {res.paths[0]: f'{archive}!/etc/app/config.json'}


def test_zip_member(tmp_path, work):
    archive = _zip(tmp_path / 'b.zip', {'etc/app/config.json': CONFIG})
    assert detect_format(archive) == 'zip'
    assert _read(_resolve(f'{archive}!/etc/app/config.json', work).paths[0]) == CONFIG


def test_format_comes_from_content_not_extension(tmp_path, work):
    archive = _tar(tmp_path / 'evidence.bin', {'config.json': CONFIG}, 'w:gz')
    assert detect_format(archive) == 'tar.gzip'
    assert _read(_resolve(f'{archive}!/config.json', work).paths[0]) == CONFIG


@pytest.mark.parametrize(('ext', 'opener', 'fmt'), [('gz', gzip.open, 'gzip'), ('bz2', bz2.open, 'bzip2'),
                                                    ('xz', lzma.open, 'xz')])  # fmt: skip
def test_single_file_compressed(tmp_path, work, ext, opener, fmt):
    path = tmp_path / f'syslog.2.{ext}'
    with opener(path, 'wb') as f:
        f.write(b'line one\nline two\n')
    assert detect_format(str(path)) == fmt

    res = _resolve(f'{path}!', work)

    assert _read(res.paths[0]) == b'line one\nline two\n'
    assert os.path.basename(res.paths[0]) == 'syslog.2'
    assert 'decompressed content' in res.details[0]


def test_trailing_separator_on_tar_gz_gives_the_tar(tmp_path, work):
    archive = _tar(tmp_path / 'b.tar.gz', {'x': b'1'}, 'w:gz')
    res = _resolve(f'{archive}!', work)
    assert detect_format(res.paths[0]) == 'tar'


def test_nested_archives(tmp_path, work):
    inner = _tar(tmp_path / 'inner.tar.gz', {'data.json': CONFIG}, 'w:gz')
    outer = _zip(tmp_path / 'outer.zip', {'inner.tar.gz': _read(inner)})

    res = _resolve(f'{outer}!/inner.tar.gz!/data.json', work)

    assert _read(res.paths[0]) == CONFIG
    assert res.display[res.paths[0]] == f'{outer}!/inner.tar.gz!/data.json'
    assert f'({outer} sha256=' in res.details[0]


def test_nested_archive_missing_is_error(tmp_path, work):
    outer = _zip(tmp_path / 'outer.zip', {'a': b'1'})
    with pytest.raises(ArchiveError, match='not found'):
        _resolve(f'{outer}!/inner.tar.gz!/data.json', work)


# --- globs and absent members --------------------------------------------------


@pytest.fixture
def logs_zip(tmp_path):
    return _zip(tmp_path / 'logs.zip', {'logs/app-1.log': b'one', 'logs/app-2.log': b'two',
                                        'logs/sub/app-3.log': b'three', 'other.txt': b'x'})  # fmt: skip


def test_glob_single_match(logs_zip, work):
    res = _resolve(f'{logs_zip}!/logs/app-1.*', work)
    assert [_read(p) for p in res.paths] == [b'one']


def test_glob_ambiguous_is_status(logs_zip, work):
    res = _resolve(f'{logs_zip}!/logs/app-*.log', work)
    assert res.paths == []
    assert '2 members' in res.status  # '*' does not cross '/': sub/app-3.log is not a match


def test_glob_any_returns_all(logs_zip, work):
    res = _resolve(f'{logs_zip}!/logs/app-*.log', work, match_mode='any')
    assert sorted(_read(p) for p in res.paths) == [b'one', b'two']
    assert len(res.details) == 2


def test_glob_no_match(logs_zip, work):
    assert _resolve(f'{logs_zip}!/nope/*', work).status
    res = _resolve(f'{logs_zip}!/nope/*', work, match_mode='any')
    assert (res.paths, res.status) == ([], '')
    assert 'matched nothing' in res.details[0]


def test_missing_member_is_an_absent_path(logs_zip, work):
    res = _resolve(f'{logs_zip}!/etc/missing.json', work)
    assert not res.status
    assert len(res.paths) == 1 and not os.path.exists(res.paths[0])
    assert 'not found in' in res.details[0]


def test_later_duplicate_wins(tmp_path, work):
    path = tmp_path / 'dup.tar'
    _tar(path, {'x': b'old'})
    with tarfile.open(path, 'a') as tar:
        info = tarfile.TarInfo('x')
        info.size = 3
        tar.addfile(info, io.BytesIO(b'new'))
    assert _read(_resolve(f'{path}!/x', work).paths[0]) == b'new'


# --- errors -------------------------------------------------------------------


def test_missing_archive(tmp_path, work):
    with pytest.raises(ArchiveError, match='does not exist'):
        _resolve(f'{tmp_path}/none.zip!/x', work)


def test_corrupt_archive(tmp_path, work):
    path = tmp_path / 'bad.gz'
    path.write_bytes(b'\x1f\x8b' + b'garbage' * 100)
    with pytest.raises(ArchiveError):
        _resolve(f'{path}!', work)


def test_truncated_tar_gz(tmp_path, work):
    archive = _tar(tmp_path / 'b.tar.gz', {'a': os.urandom(200_000)}, 'w:gz')
    data = _read(archive)
    (tmp_path / 'cut.tar.gz').write_bytes(data[: len(data) // 2])
    with pytest.raises(ArchiveError):
        _resolve(f'{tmp_path}/cut.tar.gz!/a', work)


def test_unsupported_format(tmp_path, work):
    path = tmp_path / 'notes.txt'
    path.write_text('just text\n' * 100)
    with pytest.raises(ArchiveError, match='not a supported archive'):
        _resolve(f'{path}!/x', work)


def test_member_of_single_file_stream_is_error(tmp_path, work):
    path = tmp_path / 's.gz'
    with gzip.open(path, 'wb') as f:
        f.write(b'x' * 1000)
    with pytest.raises(ArchiveError, match='single-file gzip'):
        _resolve(f'{path}!/x', work)


def test_container_without_member_is_error(logs_zip, work):
    with pytest.raises(ArchiveError, match='name a member'):
        _resolve(f'{logs_zip}!', work)


def test_dotdot_request_is_error(logs_zip, work):
    with pytest.raises(ArchiveError, match=r"'\.\.'"):
        _resolve(f'{logs_zip}!/logs/../other.txt', work)


def test_dotdot_entry_is_error_and_never_written_outside(tmp_path, work):
    archive = _tar(tmp_path / 'evil.tar', {'../evil.txt': b'pwned'})
    with pytest.raises(ArchiveError, match=r"'\.\.'"):
        _resolve(f'{archive}!/*/evil.txt', work)
    assert not (tmp_path / 'evil.txt').exists()


def test_absolute_entry_is_read_under_a_safe_name(tmp_path, work):
    archive = _tar(tmp_path / 'abs.tar', {'/etc/passwd': b'root'})
    res = _resolve(f'{archive}!/etc/passwd', work)
    assert res.paths[0].startswith(str(work))
    assert _read(res.paths[0]) == b'root'


def test_tar_symlink_member_is_error(tmp_path, work):
    path = tmp_path / 'link.tar'
    with tarfile.open(path, 'w') as tar:
        info = tarfile.TarInfo('shadow')
        info.type = tarfile.SYMTYPE
        info.linkname = '/etc/shadow'
        tar.addfile(info)
    with pytest.raises(ArchiveError, match='link'):
        _resolve(f'{path}!/shadow', work)


def test_zip_symlink_member_is_error(tmp_path, work):
    path = tmp_path / 'link.zip'
    with zipfile.ZipFile(path, 'w') as zf:
        info = zipfile.ZipInfo('shadow')
        info.external_attr = 0o120777 << 16
        zf.writestr(info, '/etc/shadow')
    with pytest.raises(ArchiveError, match='link'):
        _resolve(f'{path}!/shadow', work)


def test_directory_member_is_error(tmp_path, work):
    path = tmp_path / 'd.zip'
    with zipfile.ZipFile(path, 'w') as zf:
        zf.writestr('etc/', b'')
        zf.writestr('etc/x', b'1')
    with pytest.raises(ArchiveError, match='directory'):
        _resolve(f'{path}!/etc', work)


def test_size_cap_declared(tmp_path, work):
    archive = _zip(tmp_path / 'big.zip', {'big': b'0' * 5000})
    with pytest.raises(ArchiveError, match='size cap'):
        _resolve(f'{archive}!/big', work, max_bytes=1000)


def test_size_cap_while_streaming(tmp_path, work):
    path = tmp_path / 'bomb.gz'
    with gzip.open(path, 'wb') as f:
        f.write(b'\0' * 50_000)
    with pytest.raises(ArchiveError, match='size cap'):
        _resolve(f'{path}!', work, max_bytes=10_000)
    assert not any(f for _, _, files in os.walk(work) for f in files)  # partial output removed


def test_companions_are_extracted_next_to_member(tmp_path, work):
    archive = _zip(tmp_path / 'profile.zip', {'places.sqlite': b'db', 'places.sqlite-wal': b'wal'})
    res = _resolve(f'{archive}!/places.sqlite', work, companions=('-wal', '-journal'))
    assert _read(res.paths[0] + '-wal') == b'wal'
    assert not os.path.exists(res.paths[0] + '-journal')
