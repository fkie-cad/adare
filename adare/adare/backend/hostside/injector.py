"""Offline injection: apply :class:`StagedOp` file operations to the run overlay before first boot.

Class (c) of the host-side backend's "cannot be host-side" inventory. The guest
is not running and has no agent, so the overlay's filesystem is edited from the
host. Two engines, chosen by availability:

``GuestfishInjector``
    libguestfs (``guestfish``). The straightforward route on Linux hosts, the
    same tool ADARE's libguestfs file-transfer strategy uses. Not available on
    macOS, so it is **untested in this repository's macOS environment**.
``DebugfsInjector``
    e2fsprogs ``debugfs -w`` on a raw copy of the disk, then only the changed
    64 KiB clusters are written back into the qcow2 overlay with ``qemu-io``.
    Works wherever e2fsprogs and QEMU's tools exist (macOS: ``brew install
    e2fsprogs``, keg-only; found at ``/opt/homebrew/opt/e2fsprogs/sbin``). Costs
    roughly 30-60 s per run (a full ``qemu-img convert`` to raw and a scan), which
    is the price of editing ext4 without a mounting facility.

Both verify the result by re-reading the overlay through :class:`OfflineDiskGuestFS`.
"""

from __future__ import annotations

import logging
import os
import posixpath
import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod
from datetime import UTC
from pathlib import Path

from adare.backend.hostside import disk
from adare.backend.hostside.guestfs import GuestFS, GuestFSError, OfflineDiskGuestFS, StagedOp, normalize

log = logging.getLogger(__name__)

CLUSTER = 64 * 1024
SCAN_CHUNK = 1024 * 1024


class InjectionError(RuntimeError):
    """The staged operations could not be applied."""


def _which(name: str, extra: list[str]) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for candidate in extra:
        if os.access(candidate, os.X_OK):
            return candidate
    return None


class OverlayInjector(ABC):
    name = 'injector'

    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    def apply(self, overlay: Path, ops: list[StagedOp], base_fs: GuestFS) -> dict:
        """Apply ``ops`` to the overlay's root filesystem; return a report dict."""


def _expand_dirs(ops: list[StagedOp], fs: GuestFS) -> list[StagedOp]:
    """Insert the ``mkdir`` operations needed for parents that do not exist yet (owned like the file)."""
    out: list[StagedOp] = []
    made: set[str] = set()
    for op in ops:
        if op.kind in ('write', 'mkdir'):
            parents = posixpath.dirname(op.path)
            cur = ''
            for part in [p for p in parents.split('/') if p]:
                cur = f'{cur}/{part}'
                if cur in made or fs.is_dir(cur):
                    continue
                out.append(StagedOp('mkdir', cur, mode=0o755, uid=op.uid, gid=op.gid, source=op.source))
                made.add(cur)
        if op.kind == 'mkdir':
            if op.path in made or fs.is_dir(op.path):  # mkdir -p of an existing directory is a no-op
                continue
            made.add(op.path)
        out.append(op)
    return out


class GuestfishInjector(OverlayInjector):
    name = 'guestfish'

    def __init__(self):
        self._guestfish = _which('guestfish', [])

    def available(self) -> bool:
        return self._guestfish is not None

    def apply(self, overlay: Path, ops: list[StagedOp], base_fs: GuestFS) -> dict:
        if not self._guestfish:
            raise InjectionError('guestfish (libguestfs) is not installed')
        lines = []
        with tempfile.TemporaryDirectory(prefix='adare_inject_') as tmp:
            for i, op in enumerate(_expand_dirs(ops, base_fs)):
                if op.kind == 'mkdir':
                    lines += [
                        f'mkdir-p {op.path}',
                        f'chown {op.uid} {op.gid} {op.path}',
                        f'chmod 0{op.mode or 0o755:o} {op.path}',
                    ]
                elif op.kind == 'write':
                    src = Path(tmp) / f'f{i}'
                    src.write_bytes(op.content or b'')
                    lines += [
                        f'upload {src} {op.path}',
                        f'chown {op.uid} {op.gid} {op.path}',
                        f'chmod 0{op.mode or 0o644:o} {op.path}',
                    ]
                elif op.kind == 'remove':
                    lines.append(f'rm-rf {op.path}')
                elif op.kind == 'chmod':
                    lines.append(f'chmod 0{op.mode:o} {op.path}')
                elif op.kind == 'set_time':
                    st = base_fs.stat(op.path) if base_fs.exists(op.path) else None
                    at = op.atime if op.atime is not None else (st.atime if st else 0)
                    mt = op.mtime if op.mtime is not None else (st.mtime if st else 0)
                    lines.append(f'utimens {op.path} {int(at)} 0 {int(mt)} 0')
            script = '\n'.join(lines) + '\n'
            proc = subprocess.run(
                [self._guestfish, '--rw', '-a', str(overlay), '-i'],
                input=script,
                capture_output=True,
                text=True,
                timeout=300,
            )
        if proc.returncode != 0:
            raise InjectionError(f'guestfish failed: {proc.stderr.strip()[:500]}')
        return {'engine': self.name, 'ops': len(ops)}


class DebugfsInjector(OverlayInjector):
    name = 'debugfs'

    _EXTRA_DEBUGFS = [
        '/opt/homebrew/opt/e2fsprogs/sbin/debugfs',
        '/usr/local/opt/e2fsprogs/sbin/debugfs',
        '/opt/local/sbin/debugfs',
        '/sbin/debugfs',
        '/usr/sbin/debugfs',
    ]

    def __init__(self, qemu_img: str | None = None, qemu_io: str | None = None):
        self.debugfs = os.environ.get('ADARE_DEBUGFS') or _which('debugfs', self._EXTRA_DEBUGFS)
        self.qemu_img = qemu_img or _which('qemu-img', ['/opt/local/bin/qemu-img', '/opt/homebrew/bin/qemu-img'])
        self.qemu_io = qemu_io or _which('qemu-io', ['/opt/local/bin/qemu-io', '/opt/homebrew/bin/qemu-io'])

    def available(self) -> bool:
        return bool(self.debugfs and self.qemu_img and self.qemu_io)

    def _tools(self) -> tuple[str, str, str]:
        """``(debugfs, qemu-img, qemu-io)``; raises InjectionError when one is missing."""
        if not (self.debugfs and self.qemu_img and self.qemu_io):
            raise InjectionError(
                'debugfs injection needs e2fsprogs (debugfs) and QEMU tools (qemu-img, qemu-io); '
                'on macOS: brew install e2fsprogs (keg-only, found automatically) or set ADARE_DEBUGFS'
            )
        return self.debugfs, self.qemu_img, self.qemu_io

    # -- volume location ----------------------------------------------------------

    @staticmethod
    def locate_root_volume(raw: Path) -> int:
        """Byte offset of the root ext filesystem inside the raw disk (partition or single linear LV)."""
        stream = disk.open_disk_stream(raw)
        try:
            for part in disk.read_partitions(stream):
                ps = disk.PartitionStream(stream, part.offset, part.size)
                if disk._is_ext(ps):  # noqa: SLF001 - same package
                    root_marker = _has_os_release(ps)
                    if root_marker:
                        return part.offset
            # LVM: single physical volume, one linear segment
            lvm = disk._need('dissect.volume.lvm', 'dissect.volume')  # noqa: SLF001
            pvs = []
            for part in disk.read_partitions(stream):
                ps = disk.PartitionStream(stream, part.offset, part.size)
                ps.seek(0)
                head = ps.read(4 * disk.SECTOR)
                if b'LABELONE' in head and b'LVM2' in head:
                    pvs.append((part, disk.PartitionStream(stream, part.offset, part.size)))
            if len(pvs) != 1:
                raise InjectionError('debugfs injection supports exactly one LVM physical volume')
            volume = lvm.LVM2([pvs[0][1]])
            pv = next(iter(volume.vg.physical_volumes.values()))
            for lv in volume.vg.logical_volumes.values():
                segments = list(lv.segments)
                if len(segments) != 1 or segments[0].stripe_count != 1 or segments[0].type != 'striped':
                    continue
                seg = segments[0]
                _, start_extent = seg.stripes[0]
                offset = pvs[0][0].offset + (pv.pe_start + start_extent * volume.vg.extent_size) * disk.SECTOR
                lvs = disk.PartitionStream(stream, offset, 0)
                lvs._size = lv.open().size  # noqa: SLF001
                if disk._is_ext(lvs) and _has_os_release(lvs):  # noqa: SLF001
                    return int(offset)
            raise InjectionError('no linear ext4 root logical volume found')
        finally:
            stream.close()

    # -- apply ----------------------------------------------------------------------

    def apply(self, overlay: Path, ops: list[StagedOp], base_fs: GuestFS) -> dict:
        debugfs, qemu_img, qemu_io = self._tools()
        full_ops = _expand_dirs(ops, base_fs)
        with tempfile.TemporaryDirectory(prefix='adare_inject_', dir=overlay.parent) as tmp:
            tmpdir = Path(tmp)
            raw, pre = tmpdir / 'disk.raw', tmpdir / 'pre.raw'
            self._run([qemu_img, 'convert', '-f', 'qcow2', '-O', 'raw', str(overlay), str(raw)], 'qemu-img convert')
            self._clone(raw, pre)
            offset = self.locate_root_volume(raw)
            script = tmpdir / 'cmds.txt'
            script.write_text(self._script(full_ops, tmpdir, base_fs))
            proc = subprocess.run(
                [debugfs, '-w', '-f', str(script), f'{raw}?offset={offset}'],
                capture_output=True,
                text=True,
                timeout=300,
            )
            errors = [
                ln
                for ln in proc.stdout.splitlines() + proc.stderr.splitlines()
                if not ln.startswith('debugfs') and _is_debugfs_error(ln)
            ]
            if proc.returncode != 0 or errors:
                raise InjectionError(f'debugfs reported errors: {errors[:5] or proc.stderr.strip()[:300]}')
            changed = self._changed_clusters(pre, raw)
            self._write_back(qemu_io, overlay, raw, changed, tmpdir)
        self._verify(overlay, full_ops)
        return {'engine': self.name, 'ops': len(ops), 'clusters_written': len(changed), 'fs_offset': offset}

    @staticmethod
    def _run(cmd: list[str], what: str) -> None:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if proc.returncode != 0:
            raise InjectionError(f'{what} failed: {proc.stderr.strip()[:400]}')

    @staticmethod
    def _clone(src: Path, dst: Path) -> None:
        """Copy-on-write clone (APFS / reflink) when possible: the pre-image is only for diffing."""
        for cmd in (['cp', '-c', str(src), str(dst)], ['cp', '--reflink=auto', str(src), str(dst)]):
            if subprocess.run(cmd, capture_output=True).returncode == 0:
                return
        shutil.copyfile(src, dst)

    def _script(self, ops: list[StagedOp], tmpdir: Path, base_fs: GuestFS) -> str:
        lines = []
        for i, op in enumerate(ops):
            if op.kind == 'mkdir':
                lines += [
                    f'mkdir {op.path}',
                    f'sif {op.path} uid {op.uid}',
                    f'sif {op.path} gid {op.gid}',
                    f'sif {op.path} mode 040{op.mode or 0o755:o}',
                ]
            elif op.kind == 'write':
                src = tmpdir / f'f{i}'
                src.write_bytes(op.content or b'')
                if base_fs.exists(op.path):
                    lines.append(f'rm {op.path}')
                lines += [
                    f'write {src} {op.path}',
                    f'sif {op.path} uid {op.uid}',
                    f'sif {op.path} gid {op.gid}',
                    f'sif {op.path} mode 0100{op.mode or 0o644:o}',
                ]
                if op.mtime is not None:
                    stamp = _debugfs_time(op.mtime)
                    lines += [f'sif {op.path} mtime {stamp}', f'sif {op.path} atime {stamp}']
            elif op.kind == 'remove':
                if base_fs.lexists(op.path):  # rm -f of an absent file is a no-op
                    lines.append(f'rm {op.path}')
            elif op.kind == 'chmod':
                lines.append(f'sif {op.path} mode {_type_bits(base_fs, op.path)}{op.mode:o}')
            elif op.kind == 'set_time':
                if op.atime is not None:
                    lines.append(f'sif {op.path} atime {_debugfs_time(op.atime)}')
                if op.mtime is not None:
                    lines.append(f'sif {op.path} mtime {_debugfs_time(op.mtime)}')
        return '\n'.join(lines) + '\n'

    @staticmethod
    def _changed_clusters(pre: Path, post: Path) -> list[tuple[int, int]]:
        """Merged ``(offset, length)`` ranges of 64 KiB clusters that differ between two raw images."""
        ranges: list[list[int]] = []
        with pre.open('rb') as a, post.open('rb') as b:
            size = post.stat().st_size
            pos = 0
            while pos < size:
                try:
                    start = os.lseek(b.fileno(), pos, os.SEEK_DATA)
                except OSError:  # no more data (ENXIO)
                    break
                end = os.lseek(b.fileno(), start, os.SEEK_HOLE)
                start -= start % CLUSTER
                cur = start
                while cur < end:
                    n = min(SCAN_CHUNK, size - cur)
                    a.seek(cur)
                    b.seek(cur)
                    da, db = a.read(n), b.read(n)
                    if da != db:
                        for off in range(0, len(db), CLUSTER):
                            if da[off : off + CLUSTER] != db[off : off + CLUSTER]:
                                at = cur + off
                                ln = min(CLUSTER, size - at)
                                if ranges and ranges[-1][0] + ranges[-1][1] == at:
                                    ranges[-1][1] += ln
                                else:
                                    ranges.append([at, ln])
                    cur += n
                pos = end
        return [(o, n) for o, n in ranges]

    @staticmethod
    def _write_back(qemu_io: str, overlay: Path, raw: Path, changed: list[tuple[int, int]], tmpdir: Path) -> None:
        if not changed:
            raise InjectionError('debugfs changed nothing on the disk')
        cmds: list[str] = []
        with raw.open('rb') as fh:
            for i, (off, ln) in enumerate(changed):
                fh.seek(off)
                chunk = tmpdir / f'chunk{i}'
                chunk.write_bytes(fh.read(ln))
                cmds += ['-c', f'write -s {chunk} {off} {ln}']
        for start in range(0, len(cmds), 400):
            DebugfsInjector._run([qemu_io, '-f', 'qcow2', *cmds[start : start + 400], str(overlay)], 'qemu-io write')

    @staticmethod
    def _verify(overlay: Path, ops: list[StagedOp]) -> None:
        fs = OfflineDiskGuestFS(overlay)
        try:
            for op in ops:
                try:
                    if op.kind == 'write':
                        got = fs.read_bytes(op.path)
                        if got != (op.content or b''):
                            raise InjectionError(f'verification: {op.path} content differs after injection')
                    elif op.kind == 'remove' and fs.lexists(op.path):
                        raise InjectionError(f'verification: {op.path} still exists after injection')
                    elif op.kind == 'mkdir' and not fs.is_dir(op.path):
                        raise InjectionError(f'verification: {op.path} missing after injection')
                except GuestFSError as e:
                    raise InjectionError(f'verification failed for {op.path}: {e}') from e
        finally:
            fs.close()


def _has_os_release(stream) -> bool:
    import dissect.extfs as extfs

    try:
        extfs.ExtFS(stream).get('/etc')
        return True
    except (extfs.Error, OSError, ValueError):
        return False


def _is_debugfs_error(line: str) -> bool:
    low = line.lower()
    return any(m in low for m in ('not found', 'error', 'cannot', 'no such', 'invalid', 'bad ', 'exist'))


def _debugfs_time(epoch: float) -> str:
    from datetime import datetime

    return datetime.fromtimestamp(epoch, UTC).strftime('%Y%m%d%H%M%S')


def _type_bits(fs: GuestFS, path: str) -> str:
    try:
        return '040' if fs.is_dir(path) else '0100'
    except GuestFSError:
        return '0100'


def select_injector() -> OverlayInjector:
    """libguestfs when present, else debugfs; raises InjectionError when neither can run."""
    gf = GuestfishInjector()
    if gf.available():
        return gf
    dbg = DebugfsInjector()
    if dbg.available():
        return dbg
    raise InjectionError(
        'no offline injector available: install libguestfs (guestfish) or e2fsprogs (debugfs) plus the QEMU tools'
    )


__all__ = ['DebugfsInjector', 'GuestfishInjector', 'InjectionError', 'OverlayInjector', 'normalize', 'select_injector']
