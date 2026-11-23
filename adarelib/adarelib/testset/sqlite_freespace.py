"""Locating the free space of an SQLite database file, where deleted records can survive.

Follows the database file format of https://www.sqlite.org/fileformat2.html, without SQLite.
Deleting a row does not erase its bytes (unless ``PRAGMA secure_delete`` is on); they stay in

* **freelist** pages: pages no longer in use, chained from the header (trunk pages listing
  leaf pages). A freed page keeps its old content: a whole leaf page, the bytes of a trunk
  page after its list of leaf page numbers. Overflow pages of a deleted large row end up here;
* **freeblocks**: the chain of freed cells inside a b-tree page's cell content area (each
  starts with a 4-byte header: offset of the next freeblock, size);
* **unallocated** space of a b-tree page: the gap between the end of the cell pointer array
  and the start of the cell content area.

Fragments of fewer than 4 bytes inside a page are not reported. The reserved bytes at the
end of each page (header offset 20) are never part of a region.

Regions are ``(page, start, end, kind)`` with ``start`` / ``end`` **absolute offsets in the
file** (``end`` exclusive), ``page`` 1-based and ``kind`` one of :data:`REGION_KINDS`.

Which pages are b-tree pages is decided by their page type byte (0x02, 0x05, 0x0a, 0x0d at
offset 0, offset 100 on page 1), not by walking the b-trees from their roots; freelist
pages, pointer-map pages (auto-vacuum databases) and the lock-byte page are skipped.
Overflow pages start with the 4-byte number of the next overflow page, whose first byte is
0 in any database below 2**25 pages, so they are not taken for b-tree pages.

The parser never trusts the file: every pointer is range-checked and every chain is
cycle-guarded. A file that is not an SQLite database, a header that cannot be right or a
broken chain raises :class:`SqliteFreeSpaceError`; nothing else (no ``IndexError`` or
``struct.error``) escapes for malformed input.

Entry points: :func:`parse_free_space` (bytes), :func:`read_free_space` (an open binary
file) and :func:`free_space_of_file` (a path).

Ships with the agent's adarelib wheel. Standard library only, importable on Python 3.10.
"""

import io
import os
from dataclasses import dataclass
from typing import BinaryIO

HEADER_MAGIC = b'SQLite format 3\x00'
HEADER_SIZE = 100
MIN_PAGE_SIZE = 512
MAX_PAGE_SIZE = 65536
MIN_USABLE_SIZE = 480
# the page holding the byte at offset 2**30 is never used by SQLite (file locking)
LOCK_BYTE_OFFSET = 1 << 30

# b-tree page types: interior index, interior table, leaf index, leaf table
INTERIOR_PAGE_TYPES = (0x02, 0x05)
LEAF_PAGE_TYPES = (0x0A, 0x0D)
BTREE_PAGE_TYPES = INTERIOR_PAGE_TYPES + LEAF_PAGE_TYPES

REGION_KINDS = ('freelist', 'freeblock', 'unallocated')


class SqliteFreeSpaceError(ValueError):
    """Not an SQLite database, an impossible header, or a broken freelist / freeblock chain."""


@dataclass(frozen=True)
class FreeRegion:
    """One stretch of free space: bytes ``[start, end)`` of the file, inside page ``page``."""

    page: int
    start: int
    end: int
    kind: str

    @property
    def size(self) -> int:
        return self.end - self.start


@dataclass(frozen=True)
class FreeSpace:
    """The free space of one database file."""

    page_size: int
    usable_size: int  # page size minus the reserved bytes per page
    page_count: int  # complete pages in the file
    freelist_pages: int  # trunk + leaf pages on the freelist (= header offset 36)
    regions: tuple[FreeRegion, ...]  # in file order of their pages; empty regions are left out

    def of_kind(self, *kinds: str) -> list[FreeRegion]:
        """The regions of the given kinds (all regions when none are given)."""
        return [r for r in self.regions if not kinds or r.kind in kinds]

    def total(self, kind: str) -> int:
        """Bytes in the regions of ``kind``."""
        return sum(r.size for r in self.regions if r.kind == kind)


class _Pages:
    """Bounds-checked reads from the database file."""

    def __init__(self, handle: BinaryIO, size: int):
        self.handle = handle
        self.size = size

    def read(self, offset: int, length: int, what: str) -> bytes:
        if offset < 0 or length < 0 or offset + length > self.size:
            raise SqliteFreeSpaceError(f'{what} at offset {offset} ({length} bytes) is outside the file')
        self.handle.seek(offset)
        data = self.handle.read(length)
        if len(data) != length:  # the file shrank while it was read
            raise SqliteFreeSpaceError(f'{what} at offset {offset}: only {len(data)} of {length} bytes could be read')
        return data


def _u16(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 2], 'big')


def _u32(data: bytes, offset: int) -> int:
    return int.from_bytes(data[offset : offset + 4], 'big')


@dataclass(frozen=True)
class _Header:
    page_size: int
    usable_size: int
    page_count: int
    first_trunk: int
    freelist_count: int
    auto_vacuum: bool


def _parse_header(pages: _Pages) -> _Header:
    if pages.size < HEADER_SIZE:
        raise SqliteFreeSpaceError(f'not an SQLite database: {pages.size} bytes, shorter than the 100-byte header')
    header = pages.read(0, HEADER_SIZE, 'database header')
    if header[:16] != HEADER_MAGIC:
        raise SqliteFreeSpaceError('not an SQLite database: the header does not start with "SQLite format 3"')
    raw_page_size = _u16(header, 16)
    page_size = MAX_PAGE_SIZE if raw_page_size == 1 else raw_page_size
    if page_size < MIN_PAGE_SIZE or page_size > MAX_PAGE_SIZE or page_size & (page_size - 1):
        raise SqliteFreeSpaceError(f'invalid page size {raw_page_size} in the header (a power of two, 512 to 65536)')
    usable_size = page_size - header[20]
    if usable_size < MIN_USABLE_SIZE:
        raise SqliteFreeSpaceError(
            f'invalid header: {header[20]} reserved bytes leave {usable_size} usable bytes per page (at least 480)'
        )
    return _Header(
        page_size=page_size,
        usable_size=usable_size,
        page_count=pages.size // page_size,
        first_trunk=_u32(header, 32),
        freelist_count=_u32(header, 36),
        auto_vacuum=_u32(header, 52) != 0,
    )


def _page_offset(header: _Header, page: int) -> int:
    return (page - 1) * header.page_size


def _walk_freelist(pages: _Pages, header: _Header) -> tuple[set[int], list[FreeRegion]]:
    """The freelist pages and their regions.

    :raises SqliteFreeSpaceError: a page number out of range, a page listed twice (a cycle),
        a trunk listing more leaves than fit, or a count that differs from the header's
    """
    on_freelist: set[int] = set()
    regions = []
    max_leaves = header.usable_size // 4 - 2

    def claim(page: int, what: str) -> None:
        if page < 2 or page > header.page_count:
            raise SqliteFreeSpaceError(
                f'broken freelist: {what} page {page} is outside the database (pages 2 to {header.page_count})'
            )
        if page in on_freelist:
            raise SqliteFreeSpaceError(f'broken freelist: page {page} is listed twice (a cycle)')
        on_freelist.add(page)

    trunk = header.first_trunk
    while trunk:
        claim(trunk, 'trunk')
        start = _page_offset(header, trunk)
        head = pages.read(start, 8, f'freelist trunk page {trunk}')
        next_trunk, leaf_count = _u32(head, 0), _u32(head, 4)
        if leaf_count > max_leaves:
            raise SqliteFreeSpaceError(
                f'broken freelist: trunk page {trunk} lists {leaf_count} leaf pages (at most {max_leaves} fit)'
            )
        leaves = pages.read(start + 8, 4 * leaf_count, f'freelist trunk page {trunk}')
        regions.append(FreeRegion(trunk, start + 8 + 4 * leaf_count, start + header.usable_size, 'freelist'))
        for i in range(leaf_count):
            leaf = _u32(leaves, 4 * i)
            claim(leaf, f'leaf (listed on trunk {trunk})')
            leaf_start = _page_offset(header, leaf)
            regions.append(FreeRegion(leaf, leaf_start, leaf_start + header.usable_size, 'freelist'))
        if len(on_freelist) > header.freelist_count:
            break  # reported as a count mismatch below
        trunk = next_trunk

    if len(on_freelist) != header.freelist_count:
        raise SqliteFreeSpaceError(
            f'broken freelist: the header counts {header.freelist_count} freelist pages, '
            f'the trunk chain {"lists at least" if trunk else "lists"} {len(on_freelist)}'
        )
    return on_freelist, regions


def _is_pointer_map_page(header: _Header, page: int, lock_byte_page: int) -> bool:
    """Whether ``page`` is a pointer-map page of an auto-vacuum database (SQLite's ptrmapPageno)."""
    if not header.auto_vacuum or page < 2:
        return False
    per_map_page = header.usable_size // 5 + 1
    map_page = (page - 2) // per_map_page * per_map_page + 2
    if map_page == lock_byte_page:
        map_page += 1
    return map_page == page


def _btree_regions(pages: _Pages, header: _Header, page: int) -> list[FreeRegion]:
    """Freeblocks and unallocated space of b-tree page ``page`` (empty when it is no b-tree page).

    :raises SqliteFreeSpaceError: page 1 is no b-tree page, or its pointers are impossible
    """
    start = _page_offset(header, page)
    hdr = HEADER_SIZE if page == 1 else 0
    page_type = pages.read(start + hdr, 1, f'page {page} type')[0]
    if page_type not in BTREE_PAGE_TYPES:
        if page == 1:
            raise SqliteFreeSpaceError(f'page 1 is not a b-tree page (type 0x{page_type:02x})')
        return []
    header_size = 12 if page_type in INTERIOR_PAGE_TYPES else 8
    btree_header = pages.read(start + hdr, header_size, f'page {page} b-tree header')
    first_freeblock = _u16(btree_header, 1)
    cell_count = _u16(btree_header, 3)
    content_start = _u16(btree_header, 5) or 65536
    pointers_end = hdr + header_size + 2 * cell_count
    if pointers_end > content_start or content_start > header.usable_size:
        raise SqliteFreeSpaceError(
            f'corrupt b-tree page {page}: cell pointer array ends at {pointers_end}, cell content starts at '
            f'{content_start}, usable page size {header.usable_size}'
        )
    regions = [FreeRegion(page, start + pointers_end, start + content_start, 'unallocated')]

    page_data = None
    block = first_freeblock
    if block and block < content_start:
        raise SqliteFreeSpaceError(
            f'broken freeblock chain on page {page}: freeblock at {block} is before the cell content ({content_start})'
        )
    while block:
        if block > header.usable_size - 4:
            raise SqliteFreeSpaceError(f'broken freeblock chain on page {page}: freeblock at {block} is off the page')
        if page_data is None:
            page_data = pages.read(start, header.usable_size, f'page {page}')
        next_block, size = _u16(page_data, block), _u16(page_data, block + 2)
        if block + size > header.usable_size:
            raise SqliteFreeSpaceError(
                f'broken freeblock chain on page {page}: freeblock at {block} ({size} bytes) extends past the page'
            )
        if next_block and next_block <= block + size + 3:
            # SQLite keeps freeblocks in ascending order with at least 4 bytes between them;
            # anything else (including a pointer back, a cycle) is corruption
            raise SqliteFreeSpaceError(
                f'broken freeblock chain on page {page}: next freeblock {next_block} after the one at {block} '
                f'({size} bytes) is not in ascending order'
            )
        regions.append(FreeRegion(page, start + block, start + block + size, 'freeblock'))
        block = next_block
    return regions


def read_free_space(handle: BinaryIO, size: int) -> FreeSpace:
    """The free space of the database read from ``handle`` (``size`` bytes, seekable).

    An empty (0-byte) file is an empty database: no regions. Bytes after the last complete
    page are not examined.

    :raises SqliteFreeSpaceError: not an SQLite database, an impossible header, a broken chain
    :raises OSError: the file cannot be read
    """
    if size == 0:
        return FreeSpace(page_size=0, usable_size=0, page_count=0, freelist_pages=0, regions=())
    pages = _Pages(handle, size)
    header = _parse_header(pages)
    if header.page_count < 1:
        raise SqliteFreeSpaceError(f'not an SQLite database: {size} bytes, less than one page of {header.page_size}')
    on_freelist, freelist_regions = _walk_freelist(pages, header)
    lock_byte_page = LOCK_BYTE_OFFSET // header.page_size + 1

    regions = list(freelist_regions)
    for page in range(1, header.page_count + 1):
        if page in on_freelist or page == lock_byte_page or _is_pointer_map_page(header, page, lock_byte_page):
            continue
        regions += _btree_regions(pages, header, page)
    regions.sort(key=lambda r: (r.start, r.end))
    return FreeSpace(
        page_size=header.page_size,
        usable_size=header.usable_size,
        page_count=header.page_count,
        freelist_pages=len(on_freelist),
        regions=tuple(r for r in regions if r.end > r.start),
    )


def parse_free_space(data: bytes) -> FreeSpace:
    """The free space of a database file given as bytes (see :func:`read_free_space`).

    :raises SqliteFreeSpaceError: not an SQLite database, an impossible header, a broken chain
    """
    return read_free_space(io.BytesIO(data), len(data))


def free_space_of_file(path: str) -> FreeSpace:
    """The free space of the database file at ``path`` (see :func:`read_free_space`).

    :raises SqliteFreeSpaceError: not an SQLite database, an impossible header, a broken chain
    :raises OSError: the file cannot be read
    """
    with open(path, 'rb') as handle:
        return read_free_space(handle, os.fstat(handle.fileno()).st_size)


def read_region(handle: BinaryIO, region: FreeRegion) -> bytes:
    """The bytes of ``region`` in the file ``handle`` was parsed from."""
    handle.seek(region.start)
    return handle.read(region.size)
