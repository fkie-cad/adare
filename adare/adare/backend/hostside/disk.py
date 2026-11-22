"""Offline guest-disk access: qcow2 chain -> partitions -> (LVM) -> ext4.

Reads a *quiesced* guest disk from the host, with no guest involvement. The
layering mirrors the qemufile project's ``vmi_disk_qcow2`` / ``vmi_disk_partitions``
/ ``vmi_disk_fs`` (re-implemented here so ADARE does not depend on research
scripts), plus LVM, because Ubuntu server installs put the root filesystem on
``ubuntu-vg/ubuntu-lv`` and the qemufile images do not.

SAFETY: QEMU does not stop another process from opening a running VM's qcow2,
and reading a live-written qcow2 risks torn cluster and L2 reads. Callers must
only open an image whose VM is stopped, or a snapshot or copy of it (see
:mod:`adare.backend.hostside.session`, which only opens images after the guest
has shut down cleanly, and the initial state, which is the immutable base image).

The ``dissect.*`` packages are imported lazily so importing this module costs
nothing when the host-side backend is not used. Install them with
``uv pip install 'adare[hostside]'`` (``dissect.hypervisor``, ``dissect.extfs``,
``dissect.volume``, ``backports.zstd`` on Python < 3.14).
"""

from __future__ import annotations

import io
import logging
import os
import struct
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

#: A seekable binary stream (a file, a qcow2 stream, a partition or LVM slice)
type Stream = Any

SECTOR = 512
QCOW2_MAGIC = b'QFI\xfb'
EXT_MAGIC_OFFSET = 1024 + 56
EXT_MAGIC = b'\x53\xef'


class DiskError(RuntimeError):
    """The image cannot be read as a layered guest disk."""


def _need(module: str, package: str):
    try:
        return __import__(module, fromlist=['_'])
    except ImportError as e:
        raise DiskError(
            f"{package} is required for host-side disk access: uv pip install 'adare[hostside]' (missing {module})"
        ) from e


def open_disk_stream(path: str | Path) -> Stream:
    """Open an image (qcow2 with backing chain, or raw) as one seekable byte stream.

    The backing chain is resolved here, not by dissect: an absolute or
    directory-qualified backing path makes dissect's own resolution raise. A
    missing backing file is an error (an overlay without its base reads as a
    disk with holes where the base data should be).
    """
    path = Path(path)
    with path.open('rb') as fh:
        magic = fh.read(4)
    if magic != QCOW2_MAGIC:
        return path.open('rb')

    qcow2 = _need('dissect.hypervisor.disk.qcow2', 'dissect.hypervisor')
    with path.open('rb') as probe:
        recorded = qcow2.QCow2(probe, allow_no_backing_file=True).auto_backing_file
    if not recorded:
        return qcow2.QCow2(path).open()
    backing_path = Path(recorded)
    if not backing_path.is_absolute():
        backing_path = path.parent / backing_path
    if not backing_path.exists():
        raise DiskError(f"{path} records backing file {recorded!r}, which does not exist ({backing_path})")
    return qcow2.QCow2(path, backing_file=open_disk_stream(backing_path)).open()


class PartitionStream(io.RawIOBase):
    """``[offset, offset+size)`` of a stream as its own zero-based seekable stream."""

    def __init__(self, base: Stream, offset: int, size: int):
        super().__init__()
        self._base = base
        self._offset = offset
        self._size = size
        self._pos = 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._pos

    def seek(self, pos: int, whence: int = os.SEEK_SET) -> int:
        if whence == os.SEEK_SET:
            self._pos = pos
        elif whence == os.SEEK_CUR:
            self._pos += pos
        elif whence == os.SEEK_END:
            self._pos = self._size + pos
        else:
            raise ValueError(f"unsupported whence {whence!r}")
        return self._pos

    def readinto(self, b) -> int:
        n = min(len(b), self._size - self._pos)
        if n <= 0:
            return 0
        self._base.seek(self._offset + self._pos)
        data = self._base.read(n)
        b[: len(data)] = data
        self._pos += len(data)
        return len(data)


@dataclass(frozen=True)
class Partition:
    index: int
    scheme: str
    offset: int
    size: int


def read_partitions(disk: Stream) -> list[Partition]:
    """GPT first (a protective MBR must not be mistaken for the layout), MBR as fallback."""
    disk.seek(SECTOR)
    hdr = disk.read(92)
    if hdr[:8] == b'EFI PART':
        (entries_lba,) = struct.unpack_from('<Q', hdr, 72)
        count, entry_size = struct.unpack_from('<II', hdr, 80)
        disk.seek(entries_lba * SECTOR)
        raw = disk.read(count * entry_size)
        parts = []
        for i in range(count):
            e = raw[i * entry_size : (i + 1) * entry_size]
            if len(e) < 48 or e[:16] == b'\x00' * 16:
                continue
            first, last = struct.unpack_from('<QQ', e, 32)
            parts.append(Partition(i, 'gpt', first * SECTOR, (last - first + 1) * SECTOR))
        return parts

    disk.seek(0)
    boot = disk.read(SECTOR)
    if boot[510:512] != b'\x55\xaa':
        raise DiskError('neither a GPT header nor an MBR signature found: not a partitioned disk image')
    parts = []
    for i in range(4):
        e = boot[0x1BE + i * 16 : 0x1BE + (i + 1) * 16]
        ptype = e[4]
        start, sectors = struct.unpack_from('<II', e, 8)
        if ptype and sectors:
            parts.append(Partition(i, 'mbr', start * SECTOR, sectors * SECTOR))
    return parts


def _is_ext(stream: Stream) -> bool:
    stream.seek(EXT_MAGIC_OFFSET)
    return bool(stream.read(2) == EXT_MAGIC)


def iter_ext_volumes(disk: Stream) -> Iterator[tuple[str, Stream]]:
    """Yield ``(description, stream)`` for every ext2/3/4 volume: plain partitions and LVM logical volumes."""
    pvs: list[tuple[Partition, Stream]] = []
    try:
        partitions = read_partitions(disk)
    except DiskError:
        if _is_ext(disk):  # a bare filesystem image without a partition table
            yield 'whole disk', disk
            return
        raise
    for part in partitions:
        stream = PartitionStream(disk, part.offset, part.size)
        if _is_ext(stream):
            yield f'partition {part.index}', PartitionStream(disk, part.offset, part.size)
            continue
        # LVM2 label: "LABELONE" in one of the first four sectors, "LVM2 001" type id.
        stream.seek(0)
        head = stream.read(4 * SECTOR)
        if b'LABELONE' in head and b'LVM2' in head:
            pvs.append((part, PartitionStream(disk, part.offset, part.size)))

    if not pvs:
        return
    lvm = _need('dissect.volume.lvm', 'dissect.volume')
    volume_errors = _need('dissect.volume.exceptions', 'dissect.volume')
    try:
        volume = lvm.LVM2([stream for _, stream in pvs])
    except (volume_errors.Error, ValueError, OSError) as e:
        log.warning(f"LVM metadata unreadable: {e}")
        return
    for name, lv in volume.vg.logical_volumes.items():
        stream = lv.open()
        if _is_ext(stream):
            yield f'lvm {volume.vg.name}/{name}', lv.open()


def open_ext_filesystems(disk: Stream) -> list[tuple[str, Any]]:
    """Open every ext volume as a ``dissect.extfs.ExtFS``."""
    extfs = _need('dissect.extfs', 'dissect.extfs')
    out = []
    for desc, stream in iter_ext_volumes(disk):
        try:
            out.append((desc, extfs.ExtFS(stream)))
        except (extfs.Error, ValueError, OSError) as e:
            log.warning(f"{desc}: not a readable ext filesystem ({e})")
    return out
