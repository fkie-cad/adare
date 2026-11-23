"""Read files inside archives for file testfunctions (``dst: backup.tar.gz!/etc/app.json``).

A ``!`` followed by ``/`` (or at the end of the path) separates an archive from the member
path inside it::

    /home/u/backup.tar.gz!/etc/app/config.json     member of a tar/zip
    /var/log/syslog.2.gz!                          decompressed content of a gz/bz2/xz/lz4/sz file
    /home/u/store.jsonlz4!                         decompressed content of an LZ4 file
    /home/u/outer.zip!/inner.tar.gz!/data.json     nested archives

The format comes from the file's magic bytes, never from its extension. Only the requested
member is extracted (streamed, size-capped) into a work directory under a sanitized name;
nothing is ever extracted by the name stored in the archive, so there is no path traversal.

LZ4 is read in both its frame format and as a block with an 8-byte magic and size header
(:mod:`adarelib.testset.lz4`, pure Python). Snappy is read in its framing format (``.sz``,
:mod:`adarelib.testset.snappy`, pure Python); raw Snappy blocks have no magic bytes and are
never detected.

Standard library only (the guest agent runs on Python 3.10). A new format is one entry in
``_MAGIC`` plus one entry in ``_STREAMS`` (single-file compressors) or ``_CONTAINERS``
(multi-member archives); a third-party format imports its library inside its handler.
"""

# external imports
import bz2
import fnmatch
import gzip
import hashlib
import io
import logging
import lzma
import os
import re
import tarfile
import zipfile
import zlib
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import IO, Any

import attrs

from adarelib.testset import lz4, snappy

log = logging.getLogger(__name__)

ARCHIVE_SEPARATOR = '!'
MAX_BYTES_ENV = 'ADARE_ARCHIVE_MAX_BYTES'
DEFAULT_MAX_BYTES = 1 << 30  # 1 GiB per extracted member
_CHUNK = 1 << 20
_GLOB_CHARS = ('*', '?', '[')
MAPPING_KEYS = frozenset({'archive', 'member'})


class ArchiveError(Exception):
    """The archive cannot be used: missing, unreadable, unsupported, unsafe or too large.

    Always an ERROR result, never a FAILED or a pass: nothing can be said about the member.
    """


# ---------------------------------------------------------------------------
# Path syntax
# ---------------------------------------------------------------------------


def split_archive_path(dst: str) -> tuple[str, list[str]]:
    """Split ``dst`` at each archive separator.

    ``'a.tar!/x/y.json'`` -> ``('a.tar', ['x/y.json'])``; ``'s.gz!'`` -> ``('s.gz', [''])``;
    a path without a separator -> ``(dst, [])``. A ``!`` inside a glob bracket (``[!a]``)
    or followed by anything but ``/`` is part of the name. An empty member means "the
    decompressed content" of a single-file compressor.
    """
    parts: list[str] = []
    start = 0
    i = 0
    while i < len(dst):
        ch = dst[i]
        if ch == '[':
            close = _bracket_end(dst, i)
            if close is not None:
                i = close + 1
                continue
        elif ch == ARCHIVE_SEPARATOR and dst[i + 1 : i + 2] in ('', '/'):
            parts.append(dst[start:i])
            start = i + 1
        i += 1
    if not parts:
        return dst, []
    parts.append(dst[start:])
    return parts[0], [p.lstrip('/') for p in parts[1:]]


def _bracket_end(text: str, start: int) -> int | None:
    """Index of the ``]`` closing the glob bracket opened at ``start``, or None (literal ``[``).

    Follows fnmatch: a leading ``!`` negates, and a ``]`` right after the opening (or after
    the ``!``) is a literal member of the set.
    """
    j = start + 1
    if j < len(text) and text[j] == '!':
        j += 1
    if j < len(text) and text[j] == ']':
        j += 1
    close = text.find(']', j)
    return close if close != -1 else None


def has_archive_separator(dst: Any) -> bool:
    return isinstance(dst, str) and bool(split_archive_path(dst)[1])


def join_archive_path(archive: str, members: list[str]) -> str:
    """Inverse of :func:`split_archive_path`."""
    return archive + ''.join(f'{ARCHIVE_SEPARATOR}/{m}' if m else ARCHIVE_SEPARATOR for m in members)


def mapping_errors(value: Any) -> list[str]:
    """Problems with a ``dst`` mapping (``{archive: ..., member: ...}``); empty when it is valid."""
    if not isinstance(value, dict):
        return []
    errors = []
    unknown = sorted(str(k) for k in value if k not in MAPPING_KEYS)
    if unknown:
        errors.append(f"unknown key(s) {', '.join(unknown)} in dst mapping (allowed: archive, member)")
    archive = value.get('archive')
    if not isinstance(archive, str) or not archive:
        errors.append("dst mapping needs 'archive': the path of the archive file")
    member = value.get('member', '')
    if member is not None and not isinstance(member, str):
        errors.append("'member' in a dst mapping must be a string (a path inside the archive)")
    return errors


def normalize_dst(value: Any) -> Any:
    """Turn the mapping form of ``dst`` into the string form; other values pass unchanged.

    ``{archive: /b.tar.gz, member: etc/x.json}`` -> ``'/b.tar.gz!/etc/x.json'``. A missing or
    empty member means the decompressed content (``'/s.gz!'``).

    :raises ValueError: for a malformed mapping
    """
    if not isinstance(value, dict):
        return value
    errors = mapping_errors(value)
    if errors:
        raise ValueError('; '.join(errors))
    member = (value.get('member') or '').lstrip('/')
    return join_archive_path(value['archive'], [member])


# Test parameters that hold a guest file path and take the archive mapping form like dst.
PATH_PARAMETERS = ('dst', 'other_dst')


def normalize_test_parameters(test: dict) -> dict:
    """Return ``test`` with a mapping ``parameter.dst`` (or ``other_dst``) turned into its string form."""
    parameter = test.get('parameter')
    if not isinstance(parameter, dict):
        return test
    mappings = {
        name: normalize_dst(parameter[name]) for name in PATH_PARAMETERS if isinstance(parameter.get(name), dict)
    }
    if mappings:
        test = {**test, 'parameter': {**parameter, **mappings}}
    return test


def max_bytes_from_env() -> int:
    raw = os.environ.get(MAX_BYTES_ENV, '').strip()
    if not raw:
        return DEFAULT_MAX_BYTES
    try:
        value = int(raw)
    except ValueError:
        log.warning(f'{MAX_BYTES_ENV}={raw!r} is not an integer; using {DEFAULT_MAX_BYTES}')
        return DEFAULT_MAX_BYTES
    return value if value > 0 else DEFAULT_MAX_BYTES


# ---------------------------------------------------------------------------
# Formats
# ---------------------------------------------------------------------------

# (offset, magic bytes, format); checked in order
_MAGIC: list[tuple[int, bytes, str]] = [
    (0, b'\x1f\x8b', 'gzip'),
    (0, b'BZh', 'bzip2'),
    (0, b'\xfd7zXZ\x00', 'xz'),
    (0, b'PK\x03\x04', 'zip'),
    (0, b'PK\x05\x06', 'zip'),  # empty zip
    (0, lz4.BLOCK_HEADER_MAGIC, 'lz4_block'),
    (0, lz4.FRAME_MAGIC, 'lz4_frame'),
    (0, lz4.LEGACY_FRAME_MAGIC, 'lz4_frame'),  # reported as unsupported when read
    *((0, magic, 'lz4_frame') for magic in lz4.SKIPPABLE_MAGICS),
    (0, snappy.STREAM_IDENTIFIER, 'snappy_framed'),
]


def _open_lz4(path: str, max_bytes: int, head: int | None) -> IO[bytes]:
    """Decode a whole LZ4 file into memory (``head``: only its first bytes, for sniffing)."""
    if os.path.getsize(path) > max_bytes:
        raise lz4.Lz4SizeError(f'LZ4 file {path} is larger than the size cap of {max_bytes} bytes')
    with open(path, 'rb') as f:
        data = f.read()
    return io.BytesIO(lz4.decompress(data, max_bytes, stop_at=head))


def _open_snappy(path: str, max_bytes: int, head: int | None) -> IO[bytes]:
    """Decode a whole Snappy framed file into memory (``head``: only its first bytes, for sniffing)."""
    if os.path.getsize(path) > max_bytes:
        raise snappy.SnappySizeError(f'Snappy file {path} is larger than the size cap of {max_bytes} bytes')
    with open(path, 'rb') as f:
        data = f.read()
    return io.BytesIO(snappy.decompress_framed(data, max_bytes, stop_at=head))


# single-file compressors: format -> opener(path, max_bytes, head) returning a binary file
# object; ``max_bytes`` and ``head`` (bytes needed for sniffing, None = all) matter only to
# openers that decode into memory
_STREAMS: dict[str, Callable[[str, int, int | None], IO[bytes]]] = {
    'gzip': lambda path, _max, _head: gzip.open(path, 'rb'),  # noqa: SIM115 - caller closes
    'bzip2': lambda path, _max, _head: bz2.open(path, 'rb'),  # noqa: SIM115
    'xz': lambda path, _max, _head: lzma.open(path, 'rb'),  # noqa: SIM115
    'lz4_block': _open_lz4,
    'lz4_frame': _open_lz4,
    'snappy_framed': _open_snappy,
}

# Errors that mean "this archive cannot be read": truncated or corrupt data, encrypted or
# unsupported zip entries (RuntimeError / NotImplementedError from zipfile).
_READ_ERRORS = (
    OSError,
    EOFError,
    tarfile.TarError,
    zipfile.BadZipFile,
    zipfile.LargeZipFile,
    lzma.LZMAError,
    zlib.error,
    RuntimeError,
    NotImplementedError,
    lz4.Lz4Error,
    snappy.SnappyError,
)


def detect_format(path: str, max_bytes: int | None = None) -> str:
    """Format of the file at ``path`` from its content.

    ``max_bytes`` caps the decoding of an LZ4/Snappy stream that is checked for a tar
    inside (default: the cap from the environment).

    :return: ``'tar'``, ``'zip'``, ``'gzip'``, ``'bzip2'``, ``'xz'``, ``'lz4_frame'``,
             ``'lz4_block'``, ``'snappy_framed'``, or ``'tar.<compressor>'``
             for a compressed tar (e.g. ``'tar.gzip'``)
    :raises ArchiveError: missing, unreadable or unsupported file
    """
    if not os.path.lexists(path):
        raise ArchiveError(f'archive {path} does not exist')
    if os.path.isdir(path):
        raise ArchiveError(f'archive {path} is a directory, not an archive')
    try:
        with open(path, 'rb') as f:
            head = f.read(512)
    except OSError as e:
        raise ArchiveError(f'cannot read archive {path}: {e}') from e

    for offset, magic, fmt in _MAGIC:
        if head[offset : offset + len(magic)] == magic:
            if fmt in _STREAMS and _stream_holds_tar(path, fmt, max_bytes):
                return f'tar.{fmt}'
            return fmt
    if _is_tar_header(head):
        return 'tar'
    raise ArchiveError(
        f'{path} is not a supported archive (supported: tar, tar.gz/bz2/xz/lz4/sz, zip, gzip, bzip2, xz, lz4, snappy; '
        f'detected from content, not extension)'
    )


def _is_tar_header(block: bytes) -> bool:
    if len(block) < 512:
        return False
    if block[257:262] == b'ustar':
        return True
    try:
        tarfile.TarInfo.frombuf(block, tarfile.ENCODING, 'surrogateescape')
    except tarfile.HeaderError:
        return False
    return True


def _stream_holds_tar(path: str, fmt: str, max_bytes: int | None) -> bool:
    cap = max_bytes_from_env() if max_bytes is None else max_bytes
    try:
        with _STREAMS[fmt](path, cap, 512) as stream:
            return _is_tar_header(stream.read(512))
    except (lz4.Lz4SizeError, snappy.SnappySizeError) as e:
        # over the cap: neither as a tar nor as one stream can it be read
        raise ArchiveError(f'{e} (set {MAX_BYTES_ENV} to raise it)') from e
    except _READ_ERRORS:
        # corrupt stream: reported when the content is actually read
        return False


# ---------------------------------------------------------------------------
# Containers
# ---------------------------------------------------------------------------


@attrs.frozen
class Entry:
    name: str  # as stored in the archive
    kind: str  # 'file', 'dir', 'link' or 'other'
    size: int | None


class _TarContainer:
    def __init__(self, path: str, max_bytes: int):
        self._tar = tarfile.open(path, 'r:*')  # noqa: SIM115 - closed by close()
        self._infos: dict[str, tarfile.TarInfo] = {}

    def entries(self) -> list[Entry]:
        result = []
        for info in self._tar.getmembers():
            self._infos[info.name] = info  # a later duplicate wins, as on extraction
            if info.isreg():
                kind = 'file'
            elif info.isdir():
                kind = 'dir'
            elif info.issym() or info.islnk():
                kind = 'link'
            else:
                kind = 'other'
            result.append(Entry(info.name, kind, info.size))
        return result

    def open(self, name: str) -> IO[bytes]:
        stream = self._tar.extractfile(self._infos[name])
        if stream is None:
            raise ArchiveError(f'member {name} has no readable content')
        return stream

    def close(self) -> None:
        self._tar.close()


class _LZ4TarContainer(_TarContainer):
    """A tar inside LZ4 (tarfile cannot decompress LZ4 itself)."""

    def __init__(self, path: str, max_bytes: int):
        self._tar = tarfile.open(fileobj=_open_lz4(path, max_bytes, None))  # noqa: SIM115
        self._infos = {}


class _SnappyTarContainer(_TarContainer):
    """A tar inside Snappy framing (tarfile cannot decompress Snappy itself)."""

    def __init__(self, path: str, max_bytes: int):
        self._tar = tarfile.open(fileobj=_open_snappy(path, max_bytes, None))  # noqa: SIM115
        self._infos = {}


class _ZipContainer:
    def __init__(self, path: str, max_bytes: int):
        self._zip = zipfile.ZipFile(path)
        self._infos: dict[str, zipfile.ZipInfo] = {}

    def entries(self) -> list[Entry]:
        result = []
        for info in self._zip.infolist():
            self._infos[info.filename] = info
            if info.is_dir():
                kind = 'dir'
            elif (info.external_attr >> 16) & 0o170000 == 0o120000:  # unix symlink
                kind = 'link'
            else:
                kind = 'file'
            result.append(Entry(info.filename, kind, info.file_size))
        return result

    def open(self, name: str) -> IO[bytes]:
        return self._zip.open(self._infos[name])

    def close(self) -> None:
        self._zip.close()


# container format -> class with entries() / open(name) / close()
_CONTAINERS: dict[str, Callable[[str], Any]] = {
    'tar': _TarContainer,
    'tar.gzip': _TarContainer,
    'tar.bzip2': _TarContainer,
    'tar.xz': _TarContainer,
    'tar.lz4_block': _LZ4TarContainer,
    'tar.lz4_frame': _LZ4TarContainer,
    'tar.snappy_framed': _SnappyTarContainer,
    'zip': _ZipContainer,
}


@contextmanager
def _open_container(path: str, fmt: str, max_bytes: int) -> Iterator[Any]:
    """Open an archive; ``max_bytes`` caps the decompressed stream of a tar inside LZ4/Snappy."""
    try:
        container = _CONTAINERS[fmt](path, max_bytes)
    except _READ_ERRORS as e:
        raise ArchiveError(f'cannot read {fmt} archive {path}: {e}') from e
    try:
        yield container
    finally:
        container.close()


# ---------------------------------------------------------------------------
# Member matching and extraction
# ---------------------------------------------------------------------------


def _norm(name: str) -> str:
    """Member name as compared: no leading ``./`` or ``/``, no trailing ``/``."""
    while name.startswith('./'):
        name = name[2:]
    return name.strip('/')


def _has_glob(member: str) -> bool:
    return any(c in member for c in _GLOB_CHARS)


def _glob_match(name: str, pattern: str) -> bool:
    """Per-component match, so ``*`` does not cross ``/`` (like ``glob``, unlike ``fnmatch``)."""
    names = name.split('/')
    patterns = pattern.split('/')
    return len(names) == len(patterns) and all(fnmatch.fnmatchcase(n, p) for n, p in zip(names, patterns, strict=True))


def _check_safe_request(member: str) -> None:
    if '..' in member.split('/'):
        raise ArchiveError(f"member path {member!r} contains '..'; name the member by its path inside the archive")


def _check_safe_entry(entry: Entry, archive_display: str) -> None:
    norm = _norm(entry.name)
    if '..' in norm.split('/'):
        raise ArchiveError(f"member {entry.name!r} in {archive_display} has '..' in its path; not read")
    if entry.kind == 'link':
        raise ArchiveError(f'member {entry.name!r} in {archive_display} is a link; links are not followed')
    if entry.kind == 'dir':
        raise ArchiveError(f'member {entry.name!r} in {archive_display} is a directory; only files can be read')
    if entry.kind != 'file':
        raise ArchiveError(f'member {entry.name!r} in {archive_display} is not a regular file')


def _find(entries: list[Entry], member: str) -> list[Entry]:
    """Entries matching ``member`` (exact or glob); a later duplicate name replaces an earlier one."""
    want = _norm(member)
    by_name: dict[str, Entry] = {}
    if _has_glob(want):
        for e in entries:
            if e.kind != 'dir' and _glob_match(_norm(e.name), want):
                by_name[_norm(e.name)] = e
    else:
        for e in entries:
            if _norm(e.name) == want:
                by_name[want] = e
    return list(by_name.values())


_SAFE_CHARS = re.compile(r'[^A-Za-z0-9._-]')


def _safe_basename(name: str) -> str:
    base = _SAFE_CHARS.sub('_', _norm(name).rsplit('/', 1)[-1])
    return base if base.strip('.') else 'member'


def _copy_capped(src: IO[bytes], out_path: str, max_bytes: int, what: str) -> int:
    written = 0
    try:
        with open(out_path, 'wb') as out:
            for chunk in iter(lambda: src.read(_CHUNK), b''):
                written += len(chunk)
                if written > max_bytes:
                    raise ArchiveError(
                        f'{what} is larger than the size cap of {max_bytes} bytes (set {MAX_BYTES_ENV} to raise it)'
                    )
                out.write(chunk)
    except ArchiveError:
        os.unlink(out_path)
        raise
    except _READ_ERRORS as e:
        if os.path.exists(out_path):
            os.unlink(out_path)
        raise ArchiveError(f'cannot read {what}: {e}') from e
    return written


class _Workdir:
    """Hands out fresh numbered subdirectories, so extracted files never collide."""

    def __init__(self, root: str):
        self.root = root
        self._count = 0

    def new_path(self, basename: str) -> str:
        self._count += 1
        sub = os.path.join(self.root, str(self._count))
        os.makedirs(sub, exist_ok=True)
        return os.path.join(sub, basename)


@attrs.define
class Resolution:
    """Result of resolving an archive path.

    ``paths`` are local files (an absent member's path does not exist, like a plain path that
    is not there); a non-empty ``status`` means the test must ERROR (``paths`` is then empty).
    ``details`` are provenance lines for the test result; ``display`` maps each local path to
    the ``archive!/member`` path it stands for.
    """

    paths: list[str] = attrs.Factory(list)
    status: str = ''
    details: list[str] = attrs.Factory(list)
    display: dict[str, str] = attrs.Factory(dict)


def sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(_CHUNK), b''):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_archive_path(
    archive: str,
    members: list[str],
    workdir: str,
    match_mode: str = 'single',
    max_bytes: int = DEFAULT_MAX_BYTES,
    companions: tuple[str, ...] = (),
) -> Resolution:
    """Extract ``members`` (one per nesting level) of the local file ``archive`` into ``workdir``.

    Intermediate members (nested archives) must match exactly one file. The last member
    follows ``match_mode`` like ``BasicTest.resolve_globfilepath``: ``single`` -> a glob must
    match exactly one member, ``any`` -> zero or more.

    ``companions`` are suffixes of files that belong to the member (SQLite ``-wal``); those
    present in the same archive are extracted next to it.

    :raises ArchiveError: the archive or a nested archive cannot be used
    """
    work = _Workdir(workdir)
    fmt = detect_format(archive, max_bytes)
    try:
        outer_hash = sha256_file(archive)
    except OSError as e:
        raise ArchiveError(f'cannot read archive {archive}: {e}') from e

    if not members:
        raise ArchiveError(f'no member given for archive {archive}')
    if '' in members[:-1]:
        raise ArchiveError(f"'{ARCHIVE_SEPARATOR}' without a member is only allowed at the end of the path")

    current, current_fmt, chain = archive, fmt, archive
    # nested archives: every member but the last must be exactly one file
    for member in members[:-1]:
        _check_safe_request(member)
        _require_container(current_fmt, chain)
        with _open_container(current, current_fmt, max_bytes) as container:
            found = _find(_entries(container, chain), member)
            if len(found) != 1:
                what = 'not found' if not found else f'matches {len(found)} members (must be one)'
                raise ArchiveError(f'nested archive {member} {what} in {chain}')
            entry = found[0]
            _check_safe_entry(entry, chain)
            out = work.new_path(_safe_basename(entry.name))
            _extract_entry(container, entry, out, max_bytes, chain)
        current, chain = out, f'{chain}{ARCHIVE_SEPARATOR}/{_norm(entry.name)}'
        current_fmt = detect_format(current, max_bytes)

    member = members[-1]
    if member == '':
        out = _decompress(current, current_fmt, chain, work, max_bytes)
        return Resolution(
            paths=[out],
            details=[
                f'archive member: decompressed content of {_provenance(chain, archive, outer_hash)}, '
                f'{os.path.getsize(out)} bytes'
            ],
            display={out: f'{chain}{ARCHIVE_SEPARATOR}'},
        )
    _check_safe_request(member)
    _require_container(current_fmt, chain)
    return _extract_last(
        current,
        current_fmt,
        chain,
        member,
        work,
        match_mode,
        max_bytes,
        companions,
        _provenance(chain, archive, outer_hash),
    )


def _provenance(chain: str, archive: str, outer_hash: str) -> str:
    """``<archive> sha256=<hash>``; for a nested archive the hash is the outer file's."""
    if chain == archive:
        return f'{archive} sha256={outer_hash}'
    return f'{chain} ({archive} sha256={outer_hash})'


def _require_container(fmt: str, chain: str) -> None:
    if fmt not in _CONTAINERS:
        raise ArchiveError(
            f"{chain} is a single-file {fmt} stream, not an archive with members; "
            f"write '{chain}{ARCHIVE_SEPARATOR}' to read its decompressed content"
        )


def _entries(container: Any, chain: str) -> list[Entry]:
    try:
        return container.entries()
    except _READ_ERRORS as e:
        raise ArchiveError(f'cannot list members of {chain}: {e}') from e


def _extract_entry(container: Any, entry: Entry, out: str, max_bytes: int, chain: str) -> int:
    what = f'member {entry.name} of {chain}'
    if entry.size is not None and entry.size > max_bytes:
        raise ArchiveError(
            f'{what} is {entry.size} bytes, over the size cap of {max_bytes} bytes (set {MAX_BYTES_ENV} to raise it)'
        )
    try:
        src = container.open(entry.name)
    except _READ_ERRORS as e:
        raise ArchiveError(f'cannot read {what}: {e}') from e
    with src:
        return _copy_capped(src, out, max_bytes, what)


# suffix of a compressed file -> suffix of its decompressed content
_DECOMPRESSED_EXT = {
    '.gz': '',
    '.bz2': '',
    '.xz': '',
    '.lz4': '',
    '.jsonlz4': '.json',
    '.sz': '',
    '.tgz': '.tar',
    '.tbz2': '.tar',
    '.txz': '.tar',
}


def _decompress(path: str, fmt: str, chain: str, work: _Workdir, max_bytes: int) -> str:
    compressor = fmt.split('.', 1)[1] if fmt.startswith('tar.') else fmt
    if compressor not in _STREAMS:
        raise ArchiveError(
            f"{chain} is a {fmt} archive; name a member after '{ARCHIVE_SEPARATOR}/' "
            f"(e.g. {chain}{ARCHIVE_SEPARATOR}/path/in/archive)"
        )
    base = _safe_basename(chain.rsplit('/', 1)[-1] or 'content')
    stem, ext = os.path.splitext(base)
    if stem and ext.lower() in _DECOMPRESSED_EXT:
        base = stem + _DECOMPRESSED_EXT[ext.lower()]
    out = work.new_path(base)
    try:
        src = _STREAMS[compressor](path, max_bytes, None)
    except _READ_ERRORS as e:
        raise ArchiveError(f'cannot read {fmt} file {chain}: {e}') from e
    with src:
        _copy_capped(src, out, max_bytes, f'decompressed content of {chain}')
    return out


def _extract_last(
    current: str,
    fmt: str,
    chain: str,
    member: str,
    work: _Workdir,
    match_mode: str,
    max_bytes: int,
    companions: tuple[str, ...],
    provenance: str,
) -> Resolution:
    with _open_container(current, fmt, max_bytes) as container:
        entries = _entries(container, chain)
        found = _find(entries, member)
        is_glob = _has_glob(_norm(member))

        if not found:
            if is_glob:
                if match_mode == 'single':
                    return Resolution(status=f'no member of {chain} matches {member} (glob)')
                return Resolution(details=[f'archive member: {member} matched nothing in {provenance}'])
            absent = work.new_path(_safe_basename(member))
            return Resolution(
                paths=[absent],
                details=[f'archive member: {member} not found in {provenance}'],
                display={absent: f'{chain}{ARCHIVE_SEPARATOR}/{_norm(member)}'},
            )
        if is_glob and match_mode == 'single' and len(found) > 1:
            names = ', '.join(sorted(_norm(e.name) for e in found))
            return Resolution(status=f'{len(found)} members of {chain} match {member} (glob): {names}')

        result = Resolution()
        by_name = {_norm(e.name): e for e in entries if e.kind == 'file'}
        for entry in found:
            _check_safe_entry(entry, chain)
            out = work.new_path(_safe_basename(entry.name))
            size = _extract_entry(container, entry, out, max_bytes, chain)
            for suffix in companions:
                companion = by_name.get(_norm(entry.name) + suffix)
                if companion is not None:
                    _check_safe_entry(companion, chain)
                    _extract_entry(container, companion, out + suffix, max_bytes, chain)
            name = _norm(entry.name)
            result.paths.append(out)
            result.display[out] = f'{chain}{ARCHIVE_SEPARATOR}/{name}'
            result.details.append(f'archive member: {name} from {provenance}, {size} bytes')
        return result
