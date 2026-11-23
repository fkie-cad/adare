"""Archive paths for file testfunctions: syntax, format detection, safe extraction."""

import bz2
import gzip
import io
import lzma
import os
import struct
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
    archive = _zip(tmp_path / 'app-data.zip', {'records.db': b'db', 'records.db-wal': b'wal'})
    res = _resolve(f'{archive}!/records.db', work, companions=('-wal', '-journal'))
    assert _read(res.paths[0] + '-wal') == b'wal'
    assert not os.path.exists(res.paths[0] + '-journal')


# --- LZ4 -------------------------------------------------------------------


def _lz4_frame(data: bytes) -> bytes:
    """An LZ4 frame holding ``data`` as one uncompressed block (independent blocks, 4 MiB)."""
    from adarelib.testset import lz4

    descriptor = b'\x60\x70'
    hc = (lz4.xxh32(descriptor) >> 8) & 0xFF
    return (
        lz4.FRAME_MAGIC
        + descriptor
        + bytes([hc])
        + (0x80000000 | len(data)).to_bytes(4, 'little')
        + data
        + b'\x00\x00\x00\x00'
    )


def _block_with_header(data: bytes) -> bytes:
    """The block-with-header format: magic, u32 size, one LZ4 block of literals only."""
    from adarelib.testset import lz4

    n = len(data)
    if n < 15:
        block = bytes([n << 4]) + data
    else:
        rest, ext = n - 15, b''
        while rest >= 255:
            ext += b'\xff'
            rest -= 255
        block = b'\xf0' + ext + bytes([rest]) + data
    return lz4.BLOCK_HEADER_MAGIC + n.to_bytes(4, 'little') + block


def test_jsonlz4_block_with_header(tmp_path, work):
    path = tmp_path / 'store.jsonlz4'
    path.write_bytes(_block_with_header(CONFIG))
    assert detect_format(str(path)) == 'lz4_block'

    res = _resolve(f'{path}!', work)

    assert _read(res.paths[0]) == CONFIG
    assert os.path.basename(res.paths[0]) == 'store.json'
    assert 'decompressed content' in res.details[0]


def test_lz4_frame(tmp_path, work):
    path = tmp_path / 'data.json.lz4'
    path.write_bytes(_lz4_frame(CONFIG))
    assert detect_format(str(path)) == 'lz4_frame'

    res = _resolve(f'{path}!', work)

    assert _read(res.paths[0]) == CONFIG
    assert os.path.basename(res.paths[0]) == 'data.json'


def test_tar_inside_lz4(tmp_path, work):
    tar = _tar(tmp_path / 'b.tar', {'etc/config.json': CONFIG})
    path = tmp_path / 'b.tar.lz4'
    path.write_bytes(_lz4_frame(_read(tar)))
    assert detect_format(str(path)) == 'tar.lz4_frame'

    assert _read(_resolve(f'{path}!/etc/config.json', work).paths[0]) == CONFIG


def test_jsonlz4_inside_zip(tmp_path, work):
    archive = _zip(tmp_path / 'profile.zip', {'p/store.jsonlz4': _block_with_header(CONFIG)})
    assert _read(_resolve(f'{archive}!/p/store.jsonlz4!', work).paths[0]) == CONFIG


@pytest.mark.parametrize(
    'content',
    [
        b'mozLz40\x00\x20\x00\x00\x00\x50hel',  # truncated block
        b'mozLz40\x00\x09\x00\x00\x00\x50hello',  # size header does not match
        b'\x04\x22\x4d\x18\x64\x40\x00',  # bad header checksum
        b'\x02\x21\x4c\x18' + b'\x00' * 8,  # legacy frame: unsupported
    ],
)
def test_corrupt_lz4_is_an_archive_error(tmp_path, work, content):
    path = tmp_path / 'bad.jsonlz4'
    path.write_bytes(content)
    with pytest.raises(ArchiveError, match='cannot read'):
        _resolve(f'{path}!', work)


def test_lz4_size_cap(tmp_path, work):
    path = tmp_path / 'big.jsonlz4'
    path.write_bytes(_block_with_header(b'x' * 5000))
    with pytest.raises(ArchiveError, match='size cap'):
        _resolve(f'{path}!', work, max_bytes=1000)


# --- Snappy ------------------------------------------------------------------


def _snappy_framed(data: bytes) -> bytes:
    """A Snappy framed stream holding ``data`` as uncompressed chunks of at most 64 KiB."""
    from adarelib.testset import snappy

    out = snappy.STREAM_IDENTIFIER
    for start in range(0, len(data), 65536):
        piece = data[start : start + 65536]
        body = snappy.masked_crc32c(piece).to_bytes(4, 'little') + piece
        out += b'\x01' + len(body).to_bytes(3, 'little') + body
    return out


def test_snappy_framed(tmp_path, work):
    path = tmp_path / 'data.json.sz'
    path.write_bytes(_snappy_framed(CONFIG))
    assert detect_format(str(path)) == 'snappy_framed'

    res = _resolve(f'{path}!', work)

    assert _read(res.paths[0]) == CONFIG
    assert os.path.basename(res.paths[0]) == 'data.json'
    assert 'decompressed content' in res.details[0]


def test_tar_inside_snappy(tmp_path, work):
    tar = _tar(tmp_path / 'b.tar', {'etc/config.json': CONFIG, 'big.bin': os.urandom(100_000)})
    path = tmp_path / 'b.tar.sz'
    path.write_bytes(_snappy_framed(_read(tar)))
    assert detect_format(str(path)) == 'tar.snappy_framed'

    assert _read(_resolve(f'{path}!/etc/config.json', work).paths[0]) == CONFIG


def test_snappy_inside_zip(tmp_path, work):
    archive = _zip(tmp_path / 'bundle.zip', {'d/data.json.sz': _snappy_framed(CONFIG)})
    assert _read(_resolve(f'{archive}!/d/data.json.sz!', work).paths[0]) == CONFIG


@pytest.mark.parametrize(
    'content',
    [
        _snappy_framed(CONFIG)[:-3],  # truncated chunk
        _snappy_framed(CONFIG)[:14] + b'\x00' + _snappy_framed(CONFIG)[15:],  # checksum mismatch
        _snappy_framed(CONFIG) + b'\x02\x01\x00\x00x',  # reserved chunk type
        b'\xff\x06\x00\x00sNaPpY\x00\x05\x00\x00\x00\x00\x00\x00\x05',  # corrupt block
    ],
)
def test_corrupt_snappy_is_an_archive_error(tmp_path, work, content):
    path = tmp_path / 'bad.json.sz'
    path.write_bytes(content)
    with pytest.raises(ArchiveError, match='cannot read'):
        _resolve(f'{path}!', work)


def test_snappy_size_cap(tmp_path, work):
    path = tmp_path / 'big.sz'
    path.write_bytes(_snappy_framed(b'x' * 5000))
    with pytest.raises(ArchiveError, match='size cap'):
        _resolve(f'{path}!', work, max_bytes=1000)


# --- max_bytes reaches the tar-in-stream containers ---------------------------


@pytest.mark.parametrize('compress', ['lz4', 'snappy'])
def test_tar_inside_stream_honours_the_max_bytes_argument(tmp_path, work, monkeypatch, compress):
    """The cap passed to resolve_archive_path applies, not only the one from the environment."""
    monkeypatch.delenv(MAX_BYTES_ENV, raising=False)  # environment: the 1 GiB default
    tar = _tar(tmp_path / 'b.tar', {'etc/big.bin': b'x' * 50_000})
    path = tmp_path / f'b.tar.{compress}'
    path.write_bytes(_lz4_frame(_read(tar)) if compress == 'lz4' else _snappy_framed(_read(tar)))

    assert _read(_resolve(f'{path}!/etc/big.bin', work).paths[0]) == b'x' * 50_000
    with pytest.raises(ArchiveError) as caught:
        _resolve(f'{path}!/etc/big.bin', work, max_bytes=20_000)
    assert 'single-file' not in str(caught.value)  # still read as a tar, refused by the cap
    assert 'cap' in str(caught.value) or 'limit' in str(caught.value) or 'max' in str(caught.value)


# --- corrupt zip member names (found by test_parser_fuzz.py) -----------------


def _resolve_bytes(tmp_path, data: bytes, member: str):
    path = tmp_path / 'input.zip'
    path.write_bytes(data)
    work = tmp_path / 'work'
    work.mkdir()
    return resolve_archive_path(str(path), [member], str(work))


def _zip_with_bad_utf8_name(local: bool, central: bool) -> bytes:
    """A one-member zip whose name is flagged UTF-8 (bit 11) but starts with byte 0xa3."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr('data.json', b'{}')
    data = bytearray(buf.getvalue())
    central_start = data.find(b'PK\x01\x02')
    if local:
        data[7] |= 0x08  # local header: general purpose flags at 6
        data[30] = 0xA3  # first byte of the local name
    if central:
        data[central_start + 9] |= 0x08  # central header: general purpose flags at 8
        data[central_start + 46] = 0xA3  # first byte of the central name
    return bytes(data)


@pytest.mark.parametrize(('local', 'central'), [(True, False), (False, True)], ids=['local-name', 'central-name'])
def test_zip_member_name_flagged_utf8_but_not_utf8_is_an_archive_error(tmp_path, local, central):
    # zipfile raised UnicodeDecodeError, which escaped resolve_archive_path
    with pytest.raises(ArchiveError, match='utf-8'):
        _resolve_bytes(tmp_path, _zip_with_bad_utf8_name(local, central), 'data.json')


def _zip_with_empty_central_name() -> bytes:
    """A one-member zip whose central directory entry has a 0-byte name (the local header keeps 'x')."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr('x', b'{}')
    data = bytearray(buf.getvalue())
    central = data.find(b'PK\x01\x02')
    data[central + 28 : central + 30] = b'\x00\x00'  # file name length
    del data[central + 46]  # the name 'x'
    eocd = data.find(b'PK\x05\x06')
    size = struct.unpack_from('<I', data, eocd + 12)[0]
    struct.pack_into('<I', data, eocd + 12, size - 1)  # central directory size
    return bytes(data)


def test_zip_member_with_empty_name_is_an_archive_error_or_absent(tmp_path):
    # ZipInfo.is_dir() raised IndexError for an empty name on Python 3.10
    try:
        resolution = _resolve_bytes(tmp_path, _zip_with_empty_central_name(), 'data.json')
    except ArchiveError:
        return
    assert not os.path.exists(resolution.paths[0])  # the member is simply not there
