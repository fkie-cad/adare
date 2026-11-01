"""GuestFS: read-only view of a guest filesystem from the host.

Ground-truth test functions need ``open / read / exists / stat / listdir`` on
guest paths. In the agent backend those run inside the guest; host-side they run
against a ``GuestFS``. Implementations differ only in *where the bytes come from
and how consistent they are*, stated by :attr:`GuestFS.consistency`:

``OfflineDiskGuestFS``
    The guest's disk image (qcow2 chain -> partition -> LVM -> ext4, via dissect),
    for a *quiesced* image only: VM stopped, or a snapshot/copy. No guest
    involvement at all. Sees what reached the disk, which after a clean shutdown
    is everything.
``PatchedGuestFS``
    A base ``GuestFS`` plus the offline file operations that were staged into the
    overlay before first boot. Reconstructs the *initial* state (base image +
    injections) without copying an image.
``LiveGuestFS``
    Extension point for a RAM-first extractor (qemufile ``vmi_file_extract`` /
    the Rust core: page cache + disk fallback) that can answer while the VM runs
    and sees data not yet flushed. Not implemented: see the class docstring for
    the contract.
"""

from __future__ import annotations

import contextlib
import fnmatch
import logging
import posixpath
import shutil
from abc import ABC, abstractmethod
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, BinaryIO, cast

from adare.backend.hostside import disk

log = logging.getLogger(__name__)

S_IFMT = 0o170000
S_IFDIR = 0o040000
S_IFREG = 0o100000
S_IFLNK = 0o120000
_MAX_SYMLINKS = 40


class GuestFSError(RuntimeError):
    """Base class of GuestFS errors."""


class GuestFileNotFound(GuestFSError, FileNotFoundError):
    """The guest path does not exist."""


class GuestFSUnsupported(GuestFSError):
    """This GuestFS cannot answer (e.g. live process state from an offline image)."""


@dataclass(frozen=True)
class GuestStat:
    path: str
    size: int
    mode: int  # st_mode incl. file type bits
    uid: int
    gid: int
    atime: float  # epoch seconds (UTC), like os.stat
    mtime: float
    ctime: float
    crtime: float | None = None
    inode: int | None = None
    link_target: str | None = None

    @property
    def is_dir(self) -> bool:
        return (self.mode & S_IFMT) == S_IFDIR

    @property
    def is_file(self) -> bool:
        return (self.mode & S_IFMT) == S_IFREG

    @property
    def is_symlink(self) -> bool:
        return (self.mode & S_IFMT) == S_IFLNK

    @property
    def permissions(self) -> int:
        return self.mode & 0o7777


def normalize(path: str) -> str:
    """Absolute, normalized POSIX guest path ('..' cannot climb above '/')."""
    if not path.startswith('/'):
        path = '/' + path
    return posixpath.normpath(path) if path != '/' else '/'


class GuestFS(ABC):
    """Read-only guest filesystem. Paths are absolute POSIX paths inside the guest."""

    #: What the answers are consistent with; recorded as marker/provenance data.
    consistency: str = 'unknown'
    #: Human-readable origin (image path, 'base+staged', ...).
    origin: str = ''

    @abstractmethod
    def stat(self, path: str, follow: bool = True) -> GuestStat:
        """Metadata of ``path`` (raises :class:`GuestFileNotFound`)."""

    @abstractmethod
    def listdir(self, path: str) -> list[str]:
        """Names in a directory (no '.' / '..')."""

    @abstractmethod
    def open(self, path: str) -> BinaryIO:
        """Open a regular file for binary reading."""

    def close(self) -> None:
        """Release resources (idempotent)."""
        self._closed = True

    def __enter__(self) -> GuestFS:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # -- derived operations -------------------------------------------------

    def exists(self, path: str) -> bool:
        try:
            self.stat(path)
        except GuestFileNotFound:
            return False
        return True

    def lexists(self, path: str) -> bool:
        try:
            self.stat(path, follow=False)
        except GuestFileNotFound:
            return False
        return True

    def is_file(self, path: str) -> bool:
        try:
            return self.stat(path).is_file
        except GuestFileNotFound:
            return False

    def is_dir(self, path: str) -> bool:
        try:
            return self.stat(path).is_dir
        except GuestFileNotFound:
            return False

    def read_bytes(self, path: str) -> bytes:
        with self.open(path) as fh:
            return fh.read()

    def read_text(self, path: str, encoding: str = 'utf-8', errors: str = 'replace') -> str:
        return self.read_bytes(path).decode(encoding, errors)

    def iter_tree(self, top: str = '/') -> Iterator[GuestStat]:
        """Depth-first walk yielding every entry's lstat (symlinks are not followed)."""
        stack = [normalize(top)]
        while stack:
            directory = stack.pop()
            try:
                names = self.listdir(directory)
            except (GuestFSError, OSError, ValueError) as e:
                log.debug(f"iter_tree: cannot list {directory}: {e}")
                continue
            for name in sorted(names, reverse=True):
                child = posixpath.join(directory, name)
                try:
                    st = self.stat(child, follow=False)
                except (GuestFSError, OSError, ValueError) as e:
                    log.debug(f"iter_tree: cannot stat {child}: {e}")
                    continue
                yield st
                if st.is_dir:
                    stack.append(child)

    def glob(self, pattern: str) -> list[str]:
        """Shell-style glob over guest paths ('*', '?', '[..]'; no '**')."""
        pattern = normalize(pattern)
        if not any(c in pattern for c in '*?['):
            return [pattern] if self.lexists(pattern) else []
        matches = ['/']
        for part in pattern.strip('/').split('/'):
            nxt = []
            for base in matches:
                if not any(c in part for c in '*?['):
                    cand = posixpath.join(base, part)
                    if self.lexists(cand):
                        nxt.append(cand)
                    continue
                try:
                    names = self.listdir(base)
                except GuestFSError:
                    continue
                nxt.extend(posixpath.join(base, n) for n in sorted(names) if fnmatch.fnmatchcase(n, part))
            matches = nxt
        return matches

    def extract(self, path: str, dest: Path) -> Path:
        """Copy a guest file (or directory tree) to ``dest`` on the host."""
        st = self.stat(path)
        dest = Path(dest)
        if st.is_dir:
            dest.mkdir(parents=True, exist_ok=True)
            for name in self.listdir(path):
                child = posixpath.join(path, name)
                if self.stat(child, follow=False).is_symlink:
                    continue
                self.extract(child, dest / name)
            return dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        with self.open(path) as src, dest.open('wb') as out:
            shutil.copyfileobj(src, out)
        return dest

    def name_of_uid(self, uid: int) -> str:
        return self._passwd_name('/etc/passwd', uid)

    def name_of_gid(self, gid: int) -> str:
        return self._passwd_name('/etc/group', gid)

    def _passwd_name(self, path: str, ident: int) -> str:
        try:
            for line in self.read_text(path).splitlines():
                fields = line.split(':')
                if len(fields) > 2 and fields[2] == str(ident):
                    return fields[0]
        except GuestFSError:
            pass
        return str(ident)


class OfflineDiskGuestFS(GuestFS):
    """ext4 root filesystem of a quiesced disk image, read via dissect."""

    consistency = 'quiesced-image'

    def __init__(self, image: str | Path, root_marker: str = '/etc/os-release'):
        self.image = Path(image)
        self.origin = str(self.image)
        self._disk = disk.open_disk_stream(self.image)
        self._volumes = disk.open_ext_filesystems(self._disk)
        if not self._volumes:
            raise disk.DiskError(f'{self.image}: no ext2/3/4 filesystem found (partitions or LVM)')
        self.volume_name, self._fs = self._pick_root(root_marker)
        self._dir_cache: dict[int, dict[str, Any]] = {}

    def _pick_root(self, marker: str):
        """The volume holding the OS (``marker``); the last volume when none does."""
        import dissect.extfs as extfs_module

        for name, fs in self._volumes:
            try:
                fs.get(marker)
                return name, fs
            except (extfs_module.Error, OSError, ValueError) as e:
                log.debug(f"{name}: no {marker} ({e})")
        return self._volumes[-1]

    # -- internals -----------------------------------------------------------

    def _children(self, inode) -> dict[str, Any]:
        cached = self._dir_cache.get(inode.inum)
        if cached is None:
            cached = {k: v for k, v in inode.listdir().items() if k not in ('.', '..')}
            if len(self._dir_cache) > 4096:
                self._dir_cache.clear()
            self._dir_cache[inode.inum] = cached
        return cached

    def _lookup(self, path: str, follow: bool):
        """Resolve a path to an INode, following symlinks (the last one only if ``follow``)."""
        todo = [p for p in normalize(path).split('/') if p]
        cur = self._fs.root
        trail: list[Any] = []  # inode stack for '..' after symlinks (rare; resolved lexically)
        links = 0
        while todo:
            part = todo.pop(0)
            if part == '.':
                continue
            if part == '..':
                if trail:
                    cur = trail.pop()
                continue
            if (cur.filetype & S_IFMT) != S_IFDIR:
                raise GuestFileNotFound(path)
            child = self._children(cur).get(part)
            if child is None:
                raise GuestFileNotFound(path)
            if (child.filetype & S_IFMT) == S_IFLNK and (todo or follow):
                links += 1
                if links > _MAX_SYMLINKS:
                    raise GuestFSError(f'too many symlinks resolving {path}')
                target = child.link
                if target.startswith('/'):
                    cur, trail = self._fs.root, []
                todo = [p for p in target.split('/') if p] + todo
                continue
            trail.append(cur)
            cur = child
        return cur

    def _stat_inode(self, inode, path: str) -> GuestStat:
        raw = inode.inode
        mode = raw.i_mode
        uid = raw.i_uid | (getattr(raw, 'l_i_uid_high', 0) << 16)
        gid = raw.i_gid | (getattr(raw, 'l_i_gid_high', 0) << 16)
        crtime = None
        try:
            crtime = inode.crtime.timestamp()
        except (AttributeError, OSError, ValueError, OverflowError):
            crtime = None
        link = inode.link if (mode & S_IFMT) == S_IFLNK else None
        return GuestStat(
            path=path,
            size=inode.size,
            mode=mode,
            uid=uid,
            gid=gid,
            atime=_ts(inode.atime),
            mtime=_ts(inode.mtime),
            ctime=_ts(inode.ctime),
            crtime=crtime,
            inode=inode.inum,
            link_target=link,
        )

    # -- GuestFS ---------------------------------------------------------------

    def stat(self, path: str, follow: bool = True) -> GuestStat:
        path = normalize(path)
        return self._stat_inode(self._lookup(path, follow), path)

    def listdir(self, path: str) -> list[str]:
        inode = self._lookup(path, True)
        if (inode.filetype & S_IFMT) != S_IFDIR:
            raise GuestFSError(f'{path}: not a directory')
        return list(self._children(inode))

    def open(self, path: str) -> BinaryIO:
        inode = self._lookup(path, True)
        if (inode.filetype & S_IFMT) != S_IFREG:
            raise GuestFSError(f'{path}: not a regular file')
        return cast(BinaryIO, inode.open())

    def close(self) -> None:
        self._dir_cache.clear()
        with contextlib.suppress(OSError, ValueError, AttributeError):
            self._disk.close()


def _ts(value: Any) -> float:
    return value.timestamp() if isinstance(value, datetime) else float(value)


# ---------------------------------------------------------------------------
# Staged offline operations and the patched (initial-state) view
# ---------------------------------------------------------------------------


@dataclass
class StagedOp:
    """One offline file operation applied to the overlay before first boot."""

    kind: str  # 'write' | 'remove' | 'mkdir' | 'set_time' | 'chmod'
    path: str
    content: bytes | None = None
    mode: int | None = None
    uid: int = 1000
    gid: int = 1000
    atime: float | None = None
    mtime: float | None = None
    source: str = ''  # the playbook command / file this came from


@dataclass
class _Entry:
    stat: GuestStat | None  # None = removed
    content: bytes | None = None


@dataclass
class PatchedGuestFS(GuestFS):
    """``base`` + staged operations = the guest's state at first boot.

    Used to evaluate pre-interaction tests: the base image is immutable, the
    staged operations are known, so the initial state needs no image copy.
    """

    base: GuestFS
    ops: list[StagedOp]
    now: float = 0.0
    consistency: str = 'initial-state(base+staged)'
    _entries: dict[str, _Entry] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.origin = f'{self.base.origin} + {len(self.ops)} staged op(s)'
        for op in self.ops:
            self._apply(op)

    def _apply(self, op: StagedOp) -> None:
        path = normalize(op.path)
        if op.kind == 'remove':
            for known in [p for p in self._entries if p == path or p.startswith(path + '/')]:
                self._entries[known] = _Entry(None)
            self._entries[path] = _Entry(None)
            return
        if op.kind == 'mkdir':
            self._ensure_dirs(path, op.uid, op.gid, op.mode if op.mode is not None else 0o755, include_last=True)
            return
        parent = posixpath.dirname(path)
        self._ensure_dirs(parent, op.uid, op.gid, 0o755, include_last=True)
        if op.kind == 'write':
            data = op.content or b''
            t = op.mtime if op.mtime is not None else self.now
            st = GuestStat(
                path,
                len(data),
                S_IFREG | (op.mode if op.mode is not None else 0o644),
                op.uid,
                op.gid,
                op.atime if op.atime is not None else t,
                t,
                t,
                t,
            )
            self._entries[path] = _Entry(st, data)
            return
        # set_time / chmod modify an existing entry (staged or base)
        entry = self._entries.get(path)
        try:
            st = entry.stat if entry and entry.stat else self._base_stat(path)
        except GuestFileNotFound:  # touch creates a missing file
            t = op.mtime if op.mtime is not None else self.now
            st = GuestStat(path, 0, S_IFREG | 0o644, op.uid, op.gid, t, t, t, t)
            entry = _Entry(st, b'')
        content = entry.content if entry else None
        changes: dict[str, Any] = {}
        if op.kind == 'set_time':
            if op.atime is not None:
                changes['atime'] = op.atime
            if op.mtime is not None:
                changes['mtime'] = op.mtime
        elif op.kind == 'chmod' and op.mode is not None:
            changes['mode'] = (st.mode & S_IFMT) | op.mode
        self._entries[path] = _Entry(GuestStat(**{**st.__dict__, **changes}), content)

    def _base_stat(self, path: str) -> GuestStat:
        return self.base.stat(path)

    def _ensure_dirs(self, path: str, uid: int, gid: int, mode: int, include_last: bool) -> None:
        parts = [p for p in path.split('/') if p]
        cur = ''
        for i, part in enumerate(parts):
            cur = f'{cur}/{part}'
            if i == len(parts) - 1 and not include_last:
                break
            entry = self._entries.get(cur)
            if entry is not None and entry.stat is not None:
                continue
            if entry is None and self.base.is_dir(cur):
                continue
            self._entries[cur] = _Entry(
                GuestStat(cur, 4096, S_IFDIR | mode, uid, gid, self.now, self.now, self.now, self.now)
            )

    def stat(self, path: str, follow: bool = True) -> GuestStat:
        path = normalize(path)
        entry = self._entries.get(path)
        if entry is not None:
            if entry.stat is None:
                raise GuestFileNotFound(path)
            return entry.stat
        # a removed ancestor hides everything below it
        parent = posixpath.dirname(path)
        while parent != '/':
            pe = self._entries.get(parent)
            if pe is not None and pe.stat is None:
                raise GuestFileNotFound(path)
            parent = posixpath.dirname(parent)
        return self.base.stat(path, follow)

    def listdir(self, path: str) -> list[str]:
        path = normalize(path)
        names: set[str] = set()
        try:
            names.update(self.base.listdir(path))
        except GuestFSError:
            if not any(p.startswith(path.rstrip('/') + '/') for p in self._entries):
                raise
        prefix = path.rstrip('/') + '/'
        for known, entry in self._entries.items():
            if known.startswith(prefix):
                head = known[len(prefix) :].split('/', 1)[0]
                direct = '/' not in known[len(prefix) :]
                if direct and entry.stat is None:
                    names.discard(head)
                else:
                    names.add(head)
        return sorted(names)

    def open(self, path: str) -> BinaryIO:
        import io

        path = normalize(path)
        entry = self._entries.get(path)
        if entry is not None:
            if entry.stat is None:
                raise GuestFileNotFound(path)
            if entry.content is not None:
                return io.BytesIO(entry.content)
        return self.base.open(path)

    def close(self) -> None:
        return None


class LiveGuestFS(GuestFS):
    """Extension point: file access to a *running* guest, RAM first.

    Contract for a future implementation (qemufile ``vmi_file_extract.py`` /
    the Rust ``qfm-guest`` core): ``open(path)`` resolves the path through the
    guest's VFS in RAM (dentry -> inode), returns the page-cache-resident bytes
    and falls back to the disk image for non-resident pages (qemufile's
    ``--disk-fallback``), reporting per read how it was obtained. Because it can
    see data that has not reached the disk it is what mid-run test points need;
    ``consistency`` would be ``'ram-first(paused|mmap)'`` with the paused window
    recorded as provenance. Until it exists, host-side test points are
    evaluated after the guest has quiesced (see docs/guide/hostside-backend).
    """

    consistency = 'live-ram'

    def __init__(self, *args, **kwargs):
        raise GuestFSUnsupported(
            'LiveGuestFS is an extension point; the RAM-first extractor (qemufile vmi_file_extract) is not wired in yet'
        )

    def stat(self, path: str, follow: bool = True) -> GuestStat:  # pragma: no cover - never constructed
        raise GuestFSUnsupported('live')

    def listdir(self, path: str) -> list[str]:  # pragma: no cover
        raise GuestFSUnsupported('live')

    def open(self, path: str) -> BinaryIO:  # pragma: no cover
        raise GuestFSUnsupported('live')
