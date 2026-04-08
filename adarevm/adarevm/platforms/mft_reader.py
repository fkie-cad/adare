"""
Windows MFT (Master File Table) reader for forensic filesystem snapshots.

Reads MFT entries directly from the NTFS volume using Win32 API (ctypes),
eliminating the broken PowerShell extraction approach. Parses all 4 NTFS
timestamps (Created, Modified, Accessed, MFT Modified) along with file
paths and sizes.

Uses CreateFileW/ReadFile to open \\.\C: and stream MFT records directly,
handling MFT fragmentation via data run parsing.
"""

import sys
import struct
import logging
import platform
from typing import Dict, Optional, Tuple, Any

log = logging.getLogger(__name__)

# NTFS Constants
MFT_RECORD_SIZE = 1024  # Standard MFT entry size
FILE_SIGNATURE = b'FILE'  # MFT entry signature

# Attribute types
ATTR_STANDARD_INFORMATION = 0x10  # Contains 4 timestamps
ATTR_FILE_NAME = 0x30  # Contains filename and parent reference
ATTR_DATA = 0x80  # Data attribute (contains data runs for non-resident)
ATTR_END = 0xFFFFFFFF  # End of attributes marker

# Windows FILETIME epoch (1601-01-01) to Unix epoch (1970-01-01)
FILETIME_TO_UNIX_OFFSET = 11644473600

# MFT flags
MFT_RECORD_IN_USE = 0x0001
MFT_RECORD_IS_DIRECTORY = 0x0002

# Root directory MFT record number
MFT_ROOT_RECORD = 5

# Filename namespace priority: Win32 > Win32+DOS > POSIX > DOS
# Win32 (1) = long name, DOS (2) = 8.3 short name, Win32+DOS (3) = both,
# POSIX (0) = case-sensitive
NAMESPACE_PRIORITY = {1: 4, 3: 3, 0: 2, 2: 1}

# Read buffer size for streaming MFT parsing (1MB = ~1024 MFT entries)
READ_BUFFER_SIZE = 1024 * 1024


class MFTReaderException(Exception):
    """Base exception for MFT reading errors."""
    pass


class PrivilegeError(MFTReaderException):
    """Administrator privileges missing."""
    pass


class MFTExtractionError(MFTReaderException):
    """MFT volume reading failed."""
    pass


class MFTParsingError(MFTReaderException):
    """MFT parsing failed."""
    pass


class NTFSVolumeReader:
    """Read raw data from an NTFS volume via Win32 API (ctypes).

    Opens the volume device (e.g. \\\\.\\C:) using CreateFileW with
    GENERIC_READ access, then provides seek+read via SetFilePointerEx
    and ReadFile. Must be used as a context manager.

    Requires Administrator privileges.
    """

    def __init__(self, volume: str = "C:"):
        import ctypes
        import ctypes.wintypes

        self._ctypes = ctypes
        self._kernel32 = ctypes.windll.kernel32
        self._handle = None

        device_path = f"\\\\.\\{volume}"
        log.info(f"CLAUDE: Opening volume device: {device_path}")

        GENERIC_READ = 0x80000000
        FILE_SHARE_READ = 0x00000001
        FILE_SHARE_WRITE = 0x00000002
        OPEN_EXISTING = 3
        INVALID_HANDLE_VALUE = ctypes.wintypes.HANDLE(-1).value

        handle = self._kernel32.CreateFileW(
            device_path,
            GENERIC_READ,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            0,
            None,
        )

        if handle == INVALID_HANDLE_VALUE:
            error_code = self._kernel32.GetLastError()
            raise MFTExtractionError(
                f"Failed to open volume {device_path}: "
                f"Win32 error {error_code}"
            )

        self._handle = handle

    def read_at(self, offset: int, size: int) -> bytes:
        """Read `size` bytes from the volume at `offset`."""
        ctypes = self._ctypes

        # Seek to offset
        new_pos = ctypes.c_longlong(0)
        success = self._kernel32.SetFilePointerEx(
            self._handle,
            ctypes.c_longlong(offset),
            ctypes.byref(new_pos),
            0,  # FILE_BEGIN
        )
        if not success:
            error_code = self._kernel32.GetLastError()
            raise MFTExtractionError(
                f"SetFilePointerEx failed at offset {offset}: "
                f"Win32 error {error_code}"
            )

        # Read data
        buf = ctypes.create_string_buffer(size)
        bytes_read = ctypes.wintypes.DWORD(0)
        success = self._kernel32.ReadFile(
            self._handle,
            buf,
            size,
            ctypes.byref(bytes_read),
            None,
        )
        if not success:
            error_code = self._kernel32.GetLastError()
            raise MFTExtractionError(
                f"ReadFile failed at offset {offset}: "
                f"Win32 error {error_code}"
            )

        return buf.raw[:bytes_read.value]

    def close(self):
        """Close the volume handle."""
        if self._handle is not None:
            self._kernel32.CloseHandle(self._handle)
            self._handle = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False


class NTFSBootSector:
    """Parse the NTFS boot sector (first 512 bytes of the volume).

    Extracts:
    - bytes_per_sector (offset 0x0B, 2 bytes)
    - sectors_per_cluster (offset 0x0D, 1 byte)
    - mft_cluster_number (offset 0x30, 8 bytes) — MFT start cluster
    - mft_record_size — decoded from offset 0x40
    """

    def __init__(self, boot_data: bytes):
        if len(boot_data) < 512:
            raise MFTParsingError(
                f"Boot sector too short: {len(boot_data)} bytes"
            )

        # Verify NTFS signature at offset 0x03
        oem_id = boot_data[0x03:0x0B]
        if b'NTFS' not in oem_id:
            raise MFTParsingError(
                f"Not an NTFS volume (OEM ID: {oem_id!r})"
            )

        self.bytes_per_sector = struct.unpack('<H', boot_data[0x0B:0x0D])[0]
        self.sectors_per_cluster = struct.unpack('<B', boot_data[0x0D:0x0E])[0]
        self.mft_cluster_number = struct.unpack('<Q', boot_data[0x30:0x38])[0]

        # MFT record size: offset 0x40, 1 signed byte
        # If positive: size in clusters. If negative: size is 2^|value| bytes.
        raw = struct.unpack('<b', boot_data[0x40:0x41])[0]
        if raw > 0:
            self.mft_record_size = (
                raw * self.sectors_per_cluster * self.bytes_per_sector
            )
        else:
            self.mft_record_size = 1 << (-raw)

        self.cluster_size = self.bytes_per_sector * self.sectors_per_cluster
        self.mft_offset = self.mft_cluster_number * self.cluster_size

        log.info(
            f"CLAUDE: NTFS boot sector parsed — "
            f"bytes/sector={self.bytes_per_sector}, "
            f"sectors/cluster={self.sectors_per_cluster}, "
            f"cluster_size={self.cluster_size}, "
            f"MFT cluster={self.mft_cluster_number}, "
            f"MFT offset={self.mft_offset}, "
            f"record_size={self.mft_record_size}"
        )


def parse_data_runs(run_data: bytes) -> list:
    """Parse NTFS data runs from a non-resident $DATA attribute.

    Each data run is encoded as:
    - 1 byte header: low nibble = length field size, high nibble = offset field size
    - N bytes: run length in clusters (unsigned)
    - M bytes: run offset delta in clusters (signed, relative to previous)

    A header byte of 0x00 terminates the list.

    Returns:
        List of (absolute_cluster_offset, cluster_count) tuples.
    """
    runs = []
    pos = 0
    prev_offset = 0

    while pos < len(run_data):
        header = run_data[pos]
        if header == 0x00:
            break
        pos += 1

        length_size = header & 0x0F
        offset_size = (header >> 4) & 0x0F

        if length_size == 0 or pos + length_size + offset_size > len(run_data):
            break

        # Parse run length (unsigned)
        length_bytes = run_data[pos:pos + length_size]
        run_length = int.from_bytes(length_bytes, byteorder='little', signed=False)
        pos += length_size

        # Parse run offset delta (signed)
        if offset_size > 0:
            offset_bytes = run_data[pos:pos + offset_size]
            offset_delta = int.from_bytes(offset_bytes, byteorder='little', signed=True)
            pos += offset_size
        else:
            # Sparse run (no physical clusters)
            offset_delta = 0

        absolute_offset = prev_offset + offset_delta
        prev_offset = absolute_offset

        if run_length > 0 and offset_size > 0:
            runs.append((absolute_offset, run_length))

    return runs


class MFTRecord:
    """Represents a parsed MFT record with timestamps and metadata."""

    def __init__(self, record_number: int):
        self.record_number = record_number
        self.parent_ref = None
        self.filename = None
        self.is_directory = False
        self.file_size = 0

        # Four NTFS timestamps from $STANDARD_INFORMATION
        self.created = None
        self.modified = None
        self.accessed = None
        self.mft_modified = None

    def __repr__(self):
        return (f"MFTRecord(#{self.record_number}, filename={self.filename}, "
                f"parent={self.parent_ref}, size={self.file_size})")


class MFTParser:
    """Custom minimal NTFS MFT parser."""

    @staticmethod
    def filetime_to_unix(filetime: int) -> float:
        """Convert Windows FILETIME to Unix epoch.

        FILETIME: 100-nanosecond intervals since 1601-01-01 00:00:00
        Unix epoch: seconds since 1970-01-01 00:00:00
        """
        if filetime == 0:
            return 0.0
        seconds = filetime / 10000000.0
        return seconds - FILETIME_TO_UNIX_OFFSET

    @staticmethod
    def parse_standard_information(attr_data: bytes) -> Dict[str, float]:
        """Parse $STANDARD_INFORMATION attribute (0x10).

        Offset  Size  Description
        0       8     Created timestamp (FILETIME)
        8       8     Modified timestamp (FILETIME)
        16      8     MFT modified timestamp (FILETIME)
        24      8     Accessed timestamp (FILETIME)
        """
        if len(attr_data) < 32:
            log.warning("$STANDARD_INFORMATION too short, skipping")
            return {}

        try:
            created_ft = struct.unpack('<Q', attr_data[0:8])[0]
            modified_ft = struct.unpack('<Q', attr_data[8:16])[0]
            mft_modified_ft = struct.unpack('<Q', attr_data[16:24])[0]
            accessed_ft = struct.unpack('<Q', attr_data[24:32])[0]

            return {
                'created': MFTParser.filetime_to_unix(created_ft),
                'modified': MFTParser.filetime_to_unix(modified_ft),
                'accessed': MFTParser.filetime_to_unix(accessed_ft),
                'mft_modified': MFTParser.filetime_to_unix(mft_modified_ft),
            }
        except struct.error as e:
            log.warning(f"Failed to parse $STANDARD_INFORMATION: {e}")
            return {}

    @staticmethod
    def parse_file_name(attr_data: bytes) -> Tuple[Optional[int], Optional[str], bool]:
        """Parse $FILE_NAME attribute (0x30).

        Returns:
            (parent_ref, filename, is_directory)
        """
        if len(attr_data) < 66:
            log.warning("$FILE_NAME too short, skipping")
            return (None, None, False)

        try:
            parent_ref_bytes = attr_data[0:6] + b'\x00\x00'
            parent_ref = struct.unpack('<Q', parent_ref_bytes)[0]

            file_size = struct.unpack('<Q', attr_data[48:56])[0]

            flags = struct.unpack('<I', attr_data[56:60])[0]
            is_directory = (flags & 0x10000000) != 0

            filename_length = struct.unpack('<B', attr_data[64:65])[0]
            namespace = struct.unpack('<B', attr_data[65:66])[0]

            if len(attr_data) < 66 + (filename_length * 2):
                log.warning("Filename truncated in $FILE_NAME")
                return (parent_ref, None, is_directory)

            filename_bytes = attr_data[66:66 + (filename_length * 2)]
            filename = filename_bytes.decode('utf-16le', errors='replace')

            return (parent_ref, filename, is_directory)

        except (struct.error, UnicodeDecodeError) as e:
            log.warning(f"Failed to parse $FILE_NAME: {e}")
            return (None, None, False)

    @staticmethod
    def apply_fixup(data: bytes, update_seq_offset: int,
                    update_seq_size: int) -> bytes:
        """Apply NTFS update sequence (fixup array) to restore original data.

        The last 2 bytes of each 512-byte sector are replaced with an update
        sequence number by NTFS. This restores the original bytes.
        """
        if update_seq_size < 2:
            return data

        try:
            update_seq_num = data[update_seq_offset:update_seq_offset + 2]

            update_seq_array = []
            for i in range(1, update_seq_size):
                offset = update_seq_offset + (i * 2)
                update_seq_array.append(data[offset:offset + 2])

            data_bytearray = bytearray(data)
            for i, fixup_value in enumerate(update_seq_array):
                sector_offset = (i + 1) * 512 - 2

                if sector_offset + 2 <= len(data_bytearray):
                    if data_bytearray[sector_offset:sector_offset + 2] != update_seq_num:
                        log.warning(f"Update sequence mismatch at sector {i}")
                    data_bytearray[sector_offset:sector_offset + 2] = fixup_value

            return bytes(data_bytearray)

        except (struct.error, IndexError) as e:
            log.warning(f"Failed to apply fixup: {e}")
            return data

    @staticmethod
    def parse_mft_entry(data: bytes, record_number: int) -> Optional[MFTRecord]:
        """Parse a single 1024-byte MFT entry.

        Returns MFTRecord or None if invalid/deleted.
        """
        if len(data) < MFT_RECORD_SIZE:
            return None

        try:
            signature = data[0:4]
            if signature != FILE_SIGNATURE:
                return None

            update_seq_offset = struct.unpack('<H', data[4:6])[0]
            update_seq_size = struct.unpack('<H', data[6:8])[0]
            flags = struct.unpack('<H', data[22:24])[0]
            used_size = struct.unpack('<I', data[24:28])[0]
            first_attr_offset = struct.unpack('<H', data[20:22])[0]

            if not (flags & MFT_RECORD_IN_USE):
                return None

            data = MFTParser.apply_fixup(data, update_seq_offset, update_seq_size)

            record = MFTRecord(record_number)
            record.is_directory = (flags & MFT_RECORD_IS_DIRECTORY) != 0

            attr_offset = first_attr_offset
            timestamps_found = False
            filename_found = False
            current_namespace_priority = -1

            while attr_offset + 16 <= used_size:
                attr_type = struct.unpack('<I', data[attr_offset:attr_offset + 4])[0]

                if attr_type == ATTR_END:
                    break

                attr_length = struct.unpack('<I', data[attr_offset + 4:attr_offset + 8])[0]

                if attr_length == 0 or attr_offset + attr_length > used_size:
                    break

                non_resident = struct.unpack('<B', data[attr_offset + 8:attr_offset + 9])[0]

                if non_resident == 0:  # Resident attribute
                    content_length = struct.unpack(
                        '<I', data[attr_offset + 16:attr_offset + 20]
                    )[0]
                    content_offset = struct.unpack(
                        '<H', data[attr_offset + 20:attr_offset + 22]
                    )[0]

                    content_start = attr_offset + content_offset
                    content_end = content_start + content_length

                    if content_end <= used_size:
                        attr_content = data[content_start:content_end]

                        if (attr_type == ATTR_STANDARD_INFORMATION
                                and not timestamps_found):
                            timestamps = MFTParser.parse_standard_information(
                                attr_content
                            )
                            if timestamps:
                                record.created = timestamps.get('created')
                                record.modified = timestamps.get('modified')
                                record.accessed = timestamps.get('accessed')
                                record.mft_modified = timestamps.get('mft_modified')
                                timestamps_found = True

                        elif attr_type == ATTR_FILE_NAME:
                            parent_ref, filename, is_dir = (
                                MFTParser.parse_file_name(attr_content)
                            )

                            if len(attr_content) >= 56:
                                file_size = struct.unpack(
                                    '<Q', attr_content[48:56]
                                )[0]
                            else:
                                file_size = 0

                            if parent_ref is not None and filename:
                                namespace = (
                                    attr_content[65]
                                    if len(attr_content) > 65
                                    else 0
                                )
                                new_priority = NAMESPACE_PRIORITY.get(
                                    namespace, 0
                                )

                                if new_priority > current_namespace_priority:
                                    record.parent_ref = parent_ref
                                    record.filename = filename
                                    record.is_directory = is_dir
                                    record.file_size = file_size
                                    current_namespace_priority = new_priority
                                    filename_found = True

                attr_offset += attr_length

            if timestamps_found and filename_found:
                return record
            return None

        except (struct.error, IndexError, ValueError) as e:
            log.debug(f"Failed to parse MFT entry {record_number}: {e}")
            return None

    @staticmethod
    def parse_mft_entry_data_runs(data: bytes) -> list:
        """Parse MFT entry 0 to extract the $DATA attribute's data runs.

        MFT entry 0 is the $MFT file's own record. Its $DATA attribute
        is non-resident and contains data runs describing where the MFT
        is stored on disk (potentially fragmented).

        Returns:
            List of (cluster_offset, cluster_count) tuples.
        """
        if len(data) < MFT_RECORD_SIZE:
            raise MFTParsingError("MFT entry 0 too short")

        signature = data[0:4]
        if signature != FILE_SIGNATURE:
            raise MFTParsingError(
                f"MFT entry 0 has invalid signature: {signature!r}"
            )

        update_seq_offset = struct.unpack('<H', data[4:6])[0]
        update_seq_size = struct.unpack('<H', data[6:8])[0]
        used_size = struct.unpack('<I', data[24:28])[0]
        first_attr_offset = struct.unpack('<H', data[20:22])[0]

        data = MFTParser.apply_fixup(data, update_seq_offset, update_seq_size)

        attr_offset = first_attr_offset
        while attr_offset + 16 <= used_size:
            attr_type = struct.unpack('<I', data[attr_offset:attr_offset + 4])[0]

            if attr_type == ATTR_END:
                break

            attr_length = struct.unpack(
                '<I', data[attr_offset + 4:attr_offset + 8]
            )[0]
            if attr_length == 0 or attr_offset + attr_length > used_size:
                break

            non_resident = struct.unpack(
                '<B', data[attr_offset + 8:attr_offset + 9]
            )[0]

            if attr_type == ATTR_DATA and non_resident == 1:
                # Non-resident $DATA attribute
                # Data runs offset is at attribute offset + 0x20
                run_offset_in_attr = struct.unpack(
                    '<H', data[attr_offset + 0x20:attr_offset + 0x22]
                )[0]
                run_data_start = attr_offset + run_offset_in_attr
                run_data_end = attr_offset + attr_length
                run_data = data[run_data_start:run_data_end]

                runs = parse_data_runs(run_data)
                if runs:
                    log.info(
                        f"CLAUDE: Parsed {len(runs)} data run(s) from "
                        f"MFT entry 0"
                    )
                    return runs

            attr_offset += attr_length

        raise MFTParsingError(
            "No non-resident $DATA attribute found in MFT entry 0"
        )

    @staticmethod
    def parse_mft_from_volume(
        volume_reader: 'NTFSVolumeReader',
        boot_sector: 'NTFSBootSector',
    ) -> Dict[int, MFTRecord]:
        """Stream-parse all MFT entries directly from the volume.

        1. Read MFT entry 0 at the boot sector offset
        2. Parse its $DATA data runs (handles MFT fragmentation)
        3. Iterate through all data runs, reading in 1MB chunks
        4. Parse each 1024-byte entry

        Returns:
            Dict of record_number -> MFTRecord
        """
        record_size = boot_sector.mft_record_size
        cluster_size = boot_sector.cluster_size
        mft_offset = boot_sector.mft_offset

        # Step 1: Read MFT entry 0 to get data runs
        entry0_data = volume_reader.read_at(mft_offset, record_size)
        data_runs = MFTParser.parse_mft_entry_data_runs(entry0_data)

        # Calculate total MFT size from data runs
        total_clusters = sum(count for _, count in data_runs)
        total_bytes = total_clusters * cluster_size
        total_entries = total_bytes // record_size
        log.info(
            f"CLAUDE: MFT spans {total_clusters} clusters "
            f"({total_bytes / (1024*1024):.1f} MB), "
            f"~{total_entries} entries across {len(data_runs)} run(s)"
        )

        # Step 2: Stream through data runs, parsing entries
        records = {}
        record_number = 0
        entries_per_buffer = READ_BUFFER_SIZE // record_size

        for run_idx, (cluster_offset, cluster_count) in enumerate(data_runs):
            run_byte_offset = cluster_offset * cluster_size
            run_byte_length = cluster_count * cluster_size
            bytes_read_in_run = 0

            while bytes_read_in_run < run_byte_length:
                # Read up to 1MB at a time
                remaining = run_byte_length - bytes_read_in_run
                chunk_size = min(READ_BUFFER_SIZE, remaining)
                # Align to record size
                chunk_size = (chunk_size // record_size) * record_size
                if chunk_size == 0:
                    break

                read_offset = run_byte_offset + bytes_read_in_run
                chunk = volume_reader.read_at(read_offset, chunk_size)

                if len(chunk) < record_size:
                    break

                # Parse each entry in the chunk
                entries_in_chunk = len(chunk) // record_size
                for i in range(entries_in_chunk):
                    entry_data = chunk[i * record_size:(i + 1) * record_size]
                    record = MFTParser.parse_mft_entry(entry_data, record_number)
                    if record:
                        records[record_number] = record
                    record_number += 1

                bytes_read_in_run += len(chunk)

            if record_number % 50000 > 0 and run_idx == len(data_runs) - 1:
                log.info(
                    f"CLAUDE: Processed {record_number} MFT records, "
                    f"{len(records)} valid"
                )

            # Progress logging after each run
            if len(data_runs) > 1:
                log.info(
                    f"CLAUDE: Completed data run {run_idx + 1}/{len(data_runs)}"
                )

        log.info(
            f"CLAUDE: MFT parsing complete. Total records: {record_number}, "
            f"Valid: {len(records)}"
        )
        return records


def reconstruct_paths_memoized(
    records: Dict[int, MFTRecord],
    root_path_filter: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """Reconstruct full file paths from parent references with memoization.

    Uses a path cache so each record's path is computed at most once,
    giving O(N) total work instead of O(N*D) where D is average depth.

    Args:
        records: Dict of record_number -> MFTRecord
        root_path_filter: Optional filter (e.g., C:\\Windows)

    Returns:
        Dict mapping full paths to metadata
    """
    path_cache: Dict[int, Optional[str]] = {}

    # Guard against very deep directory trees
    old_limit = sys.getrecursionlimit()
    sys.setrecursionlimit(max(old_limit, 10000))

    def get_path(record_num: int, depth: int = 0) -> Optional[str]:
        if record_num in path_cache:
            return path_cache[record_num]

        if record_num not in records:
            path_cache[record_num] = None
            return None

        record = records[record_num]

        # Root directory
        if record.record_number == MFT_ROOT_RECORD:
            path_cache[record_num] = "C:"
            return "C:"

        # Iterative fallback for very deep paths
        if depth > 5000:
            return _get_path_iterative(record_num, records, path_cache)

        parent_ref = record.parent_ref
        if parent_ref is None:
            full_path = f"C:\\{record.filename}"
            path_cache[record_num] = full_path
            return full_path

        parent_path = get_path(parent_ref, depth + 1)
        if parent_path is None:
            full_path = f"C:\\{record.filename}"
        else:
            full_path = f"{parent_path}\\{record.filename}"

        path_cache[record_num] = full_path
        return full_path

    # Normalize filter
    filter_normalized = None
    if root_path_filter:
        filter_normalized = root_path_filter.replace('/', '\\')
        if not filter_normalized.endswith('\\'):
            filter_normalized += '\\'

    result = {}
    for record_num, record in records.items():
        if not record.filename:
            continue

        # Skip root directory itself
        if record.record_number == MFT_ROOT_RECORD:
            continue

        full_path = get_path(record_num)
        if full_path is None:
            continue

        # Apply path filter
        if filter_normalized:
            if not full_path.upper().startswith(filter_normalized.upper()):
                continue

        result[full_path] = {
            'size': record.file_size,
            'mtime': record.modified or 0.0,
            'timestamps': {
                'modified': record.modified or 0.0,
                'accessed': record.accessed or 0.0,
                'created': record.created or 0.0,
                'mft_modified': record.mft_modified or 0.0,
            },
        }

    # Restore recursion limit
    sys.setrecursionlimit(old_limit)

    log.info(f"CLAUDE: Path reconstruction complete. Total files: {len(result)}")
    return result


def _get_path_iterative(
    record_num: int,
    records: Dict[int, MFTRecord],
    path_cache: Dict[int, Optional[str]],
) -> Optional[str]:
    """Iterative fallback for very deep directory trees."""
    chain = []
    current = record_num
    visited = set()

    while current is not None and current not in path_cache:
        if current in visited:
            log.warning(f"Circular parent ref detected at record {current}")
            break
        visited.add(current)

        if current not in records:
            break

        rec = records[current]
        chain.append(current)

        if rec.record_number == MFT_ROOT_RECORD:
            break

        current = rec.parent_ref

    # Build paths from deepest known point
    base_path = path_cache.get(current) if current is not None else None

    for rec_num in reversed(chain):
        rec = records[rec_num]
        if rec.record_number == MFT_ROOT_RECORD:
            path_cache[rec_num] = "C:"
        elif base_path is None:
            base_path = f"C:\\{rec.filename}"
            path_cache[rec_num] = base_path
        else:
            base_path = f"{base_path}\\{rec.filename}"
            path_cache[rec_num] = base_path

    return path_cache.get(record_num)


class MFTReader:
    """High-level MFT reader with privilege checking."""

    @staticmethod
    def check_admin_privileges() -> Tuple[bool, str]:
        """Check if running with Administrator privileges on Windows.

        Returns:
            (is_admin: bool, error_message: str)
        """
        if platform.system().lower() != 'windows':
            return (True, "")

        try:
            import ctypes
            is_admin = ctypes.windll.shell32.IsUserAnAdmin()

            if not is_admin:
                error_msg = (
                    "Administrator privileges required for MFT reading. "
                    "Please run adarevm as Administrator."
                )
                return (False, error_msg)

            log.info(
                "CLAUDE: Running with Administrator privileges — "
                "MFT access enabled"
            )
            return (True, "")

        except (AttributeError, OSError) as e:
            error_msg = f"Failed to check admin privileges: {e}"
            log.error(f"CLAUDE: {error_msg}")
            return (False, error_msg)

    @staticmethod
    def get_mft_snapshot(
        volume: str = "C:",
        root_path: Optional[str] = None,
    ) -> Dict[str, Dict[str, Any]]:
        """Get filesystem snapshot by parsing MFT directly from the volume.

        Reads MFT entries by opening the raw volume device via Win32 API,
        parsing the NTFS boot sector to locate the MFT, then streaming
        through all MFT records following data runs.

        Args:
            volume: Volume to scan (default: C:)
            root_path: Optional path filter (e.g., C:\\Windows)

        Returns:
            Dict mapping file paths to metadata with enhanced format
        """
        log.info(f"CLAUDE: Starting MFT snapshot for volume {volume}")
        if root_path:
            log.info(f"CLAUDE: Path filter: {root_path}")

        # Step 1: Check admin privileges
        is_admin, error_msg = MFTReader.check_admin_privileges()
        if not is_admin:
            raise PrivilegeError(error_msg)

        # Step 2: Open volume and parse boot sector
        with NTFSVolumeReader(volume) as reader:
            boot_data = reader.read_at(0, 512)
            boot_sector = NTFSBootSector(boot_data)

            # Step 3: Stream-parse all MFT entries
            records = MFTParser.parse_mft_from_volume(reader, boot_sector)

        # Step 4: Reconstruct paths with memoization
        log.info("CLAUDE: Reconstructing file paths...")
        result = reconstruct_paths_memoized(records, root_path)

        log.info(f"CLAUDE: MFT snapshot complete. Total files: {len(result)}")
        return result
