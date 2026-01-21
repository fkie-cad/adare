"""
Windows MFT (Master File Table) reader for forensic filesystem snapshots.

Provides direct NTFS MFT parsing to efficiently capture all 4 NTFS timestamps
(Created, Modified, Accessed, MFT Modified) along with file paths and sizes.

This module uses custom minimal NTFS parsing without external dependencies,
reading MFT entries directly from the filesystem for maximum performance.
"""

import struct
import logging
import subprocess
import platform
import tempfile
import json
from pathlib import Path
from typing import Dict, Optional, Tuple, Any

log = logging.getLogger(__name__)

# NTFS Constants
MFT_RECORD_SIZE = 1024  # Standard MFT entry size
FILE_SIGNATURE = b'FILE'  # MFT entry signature

# Attribute types
ATTR_STANDARD_INFORMATION = 0x10  # Contains 4 timestamps
ATTR_FILE_NAME = 0x30  # Contains filename and parent reference
ATTR_END = 0xFFFFFFFF  # End of attributes marker

# Windows FILETIME epoch (1601-01-01) to Unix epoch (1970-01-01)
# Difference in seconds
FILETIME_TO_UNIX_OFFSET = 11644473600

# MFT flags
MFT_RECORD_IN_USE = 0x0001
MFT_RECORD_IS_DIRECTORY = 0x0002

# Root directory MFT record number
MFT_ROOT_RECORD = 5


class MFTReaderException(Exception):
    """Base exception for MFT reading errors."""
    pass


class PrivilegeError(MFTReaderException):
    """Administrator privileges missing."""
    pass


class MFTExtractionError(MFTReaderException):
    """MFT file extraction failed."""
    pass


class MFTParsingError(MFTReaderException):
    """MFT file parsing failed."""
    pass


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

        Args:
            filetime: Windows FILETIME value

        Returns:
            Unix epoch timestamp as float
        """
        if filetime == 0:
            return 0.0

        seconds = filetime / 10000000.0  # Convert to seconds
        return seconds - FILETIME_TO_UNIX_OFFSET  # Adjust epoch

    @staticmethod
    def parse_standard_information(attr_data: bytes) -> Dict[str, float]:
        """Parse $STANDARD_INFORMATION attribute (0x10).

        Structure (resident attribute):
        Offset  Size  Description
        0       8     Created timestamp (FILETIME)
        8       8     Modified timestamp (FILETIME)
        16      8     MFT modified timestamp (FILETIME)
        24      8     Accessed timestamp (FILETIME)
        32      4     File attributes (flags)

        Args:
            attr_data: Attribute content bytes

        Returns:
            Dict with 'created', 'modified', 'accessed', 'mft_modified' as Unix epoch
        """
        if len(attr_data) < 32:
            log.warning("$STANDARD_INFORMATION too short, skipping")
            return {}

        try:
            # Parse 4 FILETIME timestamps (8 bytes each, little-endian)
            created_ft = struct.unpack('<Q', attr_data[0:8])[0]
            modified_ft = struct.unpack('<Q', attr_data[8:16])[0]
            mft_modified_ft = struct.unpack('<Q', attr_data[16:24])[0]
            accessed_ft = struct.unpack('<Q', attr_data[24:32])[0]

            return {
                'created': MFTParser.filetime_to_unix(created_ft),
                'modified': MFTParser.filetime_to_unix(modified_ft),
                'accessed': MFTParser.filetime_to_unix(accessed_ft),
                'mft_modified': MFTParser.filetime_to_unix(mft_modified_ft)
            }
        except struct.error as e:
            log.warning(f"Failed to parse $STANDARD_INFORMATION: {e}")
            return {}

    @staticmethod
    def parse_file_name(attr_data: bytes) -> Tuple[Optional[int], Optional[str], bool]:
        """Parse $FILE_NAME attribute (0x30).

        Structure (resident attribute):
        Offset  Size  Description
        0       6     Parent directory reference (MFT record number in first 48 bits)
        6       2     Sequence number
        8       8     Created time
        16      8     Modified time
        24      8     MFT modified time
        32      8     Accessed time
        40      8     Allocated size
        48      8     Real size
        56      4     Flags
        60      4     Reparse value
        64      1     Filename length (Unicode characters)
        65      1     Namespace (0=POSIX, 1=Win32, 2=DOS, 3=Win32+DOS)
        66      2*N   Filename (UTF-16LE)

        Args:
            attr_data: Attribute content bytes

        Returns:
            (parent_ref, filename, is_directory)
        """
        if len(attr_data) < 66:
            log.warning("$FILE_NAME too short, skipping")
            return (None, None, False)

        try:
            # Parse parent directory reference (6 bytes = 48 bits)
            # MFT record number is in lower 48 bits
            parent_ref_bytes = attr_data[0:6] + b'\x00\x00'  # Pad to 8 bytes
            parent_ref = struct.unpack('<Q', parent_ref_bytes)[0]

            # Parse file size (real size)
            file_size = struct.unpack('<Q', attr_data[48:56])[0]

            # Parse flags to detect directory
            flags = struct.unpack('<I', attr_data[56:60])[0]
            is_directory = (flags & 0x10000000) != 0  # FILE_ATTRIBUTE_DIRECTORY

            # Parse filename length (in Unicode characters)
            filename_length = struct.unpack('<B', attr_data[64:65])[0]

            # Parse namespace
            namespace = struct.unpack('<B', attr_data[65:66])[0]

            # Parse filename (UTF-16LE)
            if len(attr_data) < 66 + (filename_length * 2):
                log.warning("Filename truncated in $FILE_NAME")
                return (parent_ref, None, is_directory)

            filename_bytes = attr_data[66:66 + (filename_length * 2)]
            filename = filename_bytes.decode('utf-16le', errors='replace')

            # Prefer Win32 namespace (1) over DOS (2) or POSIX (0)
            # DOS names are short 8.3 names like "PROGRA~1"
            # We'll return all but let caller filter

            return (parent_ref, filename, is_directory)

        except (struct.error, UnicodeDecodeError) as e:
            log.warning(f"Failed to parse $FILE_NAME: {e}")
            return (None, None, False)

    @staticmethod
    def apply_fixup(data: bytes, update_seq_offset: int, update_seq_size: int) -> bytes:
        """Apply NTFS update sequence (fixup array) to restore original data.

        NTFS stores a fixup array to detect corruption. The last 2 bytes of each
        512-byte sector are replaced with an update sequence number. This function
        restores the original bytes.

        Args:
            data: MFT entry data (1024 bytes)
            update_seq_offset: Offset to update sequence array
            update_seq_size: Size of update sequence array (in 16-bit words)

        Returns:
            Fixed data with original bytes restored
        """
        if update_seq_size < 2:
            return data  # No fixup needed

        try:
            # Read update sequence number (2 bytes)
            update_seq_num = data[update_seq_offset:update_seq_offset + 2]

            # Read update sequence array (update_seq_size-1 entries, each 2 bytes)
            update_seq_array = []
            for i in range(1, update_seq_size):
                offset = update_seq_offset + (i * 2)
                update_seq_array.append(data[offset:offset + 2])

            # Apply fixup to each 512-byte sector
            data_bytearray = bytearray(data)
            for i, fixup_value in enumerate(update_seq_array):
                # Replace last 2 bytes of each sector (at offset 510, 1022)
                sector_offset = (i + 1) * 512 - 2

                if sector_offset + 2 <= len(data_bytearray):
                    # Verify update sequence number matches
                    if data_bytearray[sector_offset:sector_offset + 2] != update_seq_num:
                        log.warning(f"Update sequence mismatch at sector {i}")

                    # Replace with original bytes
                    data_bytearray[sector_offset:sector_offset + 2] = fixup_value

            return bytes(data_bytearray)

        except (struct.error, IndexError) as e:
            log.warning(f"Failed to apply fixup: {e}")
            return data  # Return original data if fixup fails

    @staticmethod
    def parse_mft_entry(data: bytes, record_number: int) -> Optional[MFTRecord]:
        """Parse a single MFT entry (1024 bytes).

        Steps:
        1. Validate FILE signature
        2. Parse fixup array (update sequence)
        3. Iterate through attributes
        4. Extract $STANDARD_INFORMATION timestamps
        5. Extract $FILE_NAME (filename + parent reference)

        Args:
            data: 1024 bytes of MFT entry
            record_number: MFT record number

        Returns:
            MFTRecord or None if invalid/deleted
        """
        if len(data) < MFT_RECORD_SIZE:
            return None

        try:
            # Validate signature
            signature = data[0:4]
            if signature != FILE_SIGNATURE:
                return None  # Not a valid MFT entry

            # Parse MFT entry header
            update_seq_offset = struct.unpack('<H', data[4:6])[0]
            update_seq_size = struct.unpack('<H', data[6:8])[0]
            flags = struct.unpack('<H', data[22:24])[0]
            used_size = struct.unpack('<I', data[24:28])[0]
            first_attr_offset = struct.unpack('<H', data[20:22])[0]

            # Check if entry is in use
            if not (flags & MFT_RECORD_IN_USE):
                return None  # Deleted entry, skip

            # Apply fixup array
            data = MFTParser.apply_fixup(data, update_seq_offset, update_seq_size)

            # Create record object
            record = MFTRecord(record_number)
            record.is_directory = (flags & MFT_RECORD_IS_DIRECTORY) != 0

            # Parse attributes
            attr_offset = first_attr_offset
            timestamps_found = False
            filename_found = False
            file_size = 0

            while attr_offset + 16 <= used_size:  # Need at least 16 bytes for header
                # Parse attribute header
                attr_type = struct.unpack('<I', data[attr_offset:attr_offset + 4])[0]

                if attr_type == ATTR_END:
                    break  # End of attributes

                attr_length = struct.unpack('<I', data[attr_offset + 4:attr_offset + 8])[0]

                if attr_length == 0 or attr_offset + attr_length > used_size:
                    break  # Invalid attribute length

                non_resident = struct.unpack('<B', data[attr_offset + 8:attr_offset + 9])[0]

                if non_resident == 0:  # Resident attribute
                    content_length = struct.unpack('<I', data[attr_offset + 16:attr_offset + 20])[0]
                    content_offset = struct.unpack('<H', data[attr_offset + 20:attr_offset + 22])[0]

                    content_start = attr_offset + content_offset
                    content_end = content_start + content_length

                    if content_end <= used_size:
                        attr_content = data[content_start:content_end]

                        if attr_type == ATTR_STANDARD_INFORMATION and not timestamps_found:
                            timestamps = MFTParser.parse_standard_information(attr_content)
                            if timestamps:
                                record.created = timestamps.get('created')
                                record.modified = timestamps.get('modified')
                                record.accessed = timestamps.get('accessed')
                                record.mft_modified = timestamps.get('mft_modified')
                                timestamps_found = True

                        elif attr_type == ATTR_FILE_NAME:
                            parent_ref, filename, is_dir = MFTParser.parse_file_name(attr_content)

                            # Parse file size from $FILE_NAME
                            if len(attr_content) >= 56:
                                file_size = struct.unpack('<Q', attr_content[48:56])[0]

                            if parent_ref is not None and filename:
                                # Prefer Win32 namespace (namespace byte at offset 65)
                                namespace = attr_content[65] if len(attr_content) > 65 else 0

                                # Only use this filename if we haven't found a better one
                                # Prefer Win32 (1) over DOS (2) or POSIX (0)
                                if not filename_found or namespace == 1:
                                    record.parent_ref = parent_ref
                                    record.filename = filename
                                    record.is_directory = is_dir
                                    record.file_size = file_size
                                    filename_found = True

                # Move to next attribute
                attr_offset += attr_length

            # Return record only if we found essential data
            if timestamps_found and filename_found:
                return record
            else:
                return None  # Incomplete record

        except (struct.error, IndexError, ValueError) as e:
            log.debug(f"Failed to parse MFT entry {record_number}: {e}")
            return None

    @staticmethod
    def reconstruct_paths(records: Dict[int, MFTRecord],
                         root_path_filter: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """Reconstruct full file paths from parent references.

        Algorithm:
        1. For each record, walk parent chain to root (record 5)
        2. Build path string: C:\\parent\\child\\file.txt
        3. Apply path filter if specified
        4. Format into output dict

        Args:
            records: Dict of record_number -> MFTRecord
            root_path_filter: Optional filter (e.g., C:\\Windows)

        Returns:
            Dict mapping full paths to metadata
        """
        result = {}

        for record_num, record in records.items():
            if not record.filename:
                continue

            # Build path by walking parent chain
            path_components = []
            current_record = record
            visited = set()

            while current_record:
                # Prevent infinite loops
                if current_record.record_number in visited:
                    log.warning(f"Circular parent reference detected for record {record_num}")
                    break

                visited.add(current_record.record_number)

                # Add filename to path
                path_components.insert(0, current_record.filename)

                # Stop at root
                if current_record.record_number == MFT_ROOT_RECORD:
                    break

                # Move to parent
                parent_ref = current_record.parent_ref
                if parent_ref is None or parent_ref not in records:
                    break

                current_record = records[parent_ref]

            # Build full path
            if not path_components:
                continue

            # Skip root directory itself (record 5 with filename ".")
            if len(path_components) == 1 and path_components[0] == '.':
                continue

            # Build Windows path
            if path_components[0] == '.':
                path_components[0] = 'C:'

            full_path = '\\'.join(path_components)

            # Ensure path starts with C:
            if not full_path.startswith('C:'):
                full_path = f"C:\\{full_path}"

            # Apply path filter
            if root_path_filter:
                # Normalize filter path
                filter_normalized = root_path_filter.replace('/', '\\')
                if not filter_normalized.endswith('\\'):
                    filter_normalized += '\\'

                # Check if path starts with filter
                if not full_path.upper().startswith(filter_normalized.upper()):
                    continue

            # Add to result (common format with nested timestamps)
            result[full_path] = {
                'size': record.file_size,
                'mtime': record.modified or 0.0,
                'timestamps': {
                    'modified': record.modified or 0.0,
                    'accessed': record.accessed or 0.0,
                    'created': record.created or 0.0,
                    'mft_modified': record.mft_modified or 0.0
                }
            }

        return result

    @staticmethod
    def parse_mft_file(mft_file_path: Path,
                      root_path_filter: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """Parse MFT file and return file metadata dict.

        Two-pass algorithm:
        1. First pass: Build record_number -> MFTRecord mapping
        2. Second pass: Reconstruct full paths from parent references

        Args:
            mft_file_path: Path to extracted MFT file
            root_path_filter: Optional path filter (e.g., C:\\Windows)

        Returns:
            Dict mapping full paths to file metadata
        """
        log.info(f"CLAUDE: Parsing MFT file: {mft_file_path}")
        records = {}

        try:
            with open(mft_file_path, 'rb') as f:
                record_number = 0

                while True:
                    data = f.read(MFT_RECORD_SIZE)
                    if len(data) < MFT_RECORD_SIZE:
                        break

                    record = MFTParser.parse_mft_entry(data, record_number)
                    if record:
                        records[record_number] = record

                    record_number += 1

                    # Progress logging every 50k records
                    if record_number % 50000 == 0:
                        log.info(f"CLAUDE: Processed {record_number} MFT records, "
                                f"{len(records)} valid")

            log.info(f"CLAUDE: MFT parsing complete. Total records: {record_number}, "
                    f"Valid: {len(records)}")

            # Second pass: Reconstruct paths
            log.info("CLAUDE: Reconstructing file paths...")
            result = MFTParser.reconstruct_paths(records, root_path_filter)
            log.info(f"CLAUDE: Path reconstruction complete. Total files: {len(result)}")

            return result

        except OSError as e:
            raise MFTParsingError(f"Failed to read MFT file: {e}")


class MFTReader:
    """High-level MFT reader with privilege checking."""

    @staticmethod
    def check_admin_privileges() -> Tuple[bool, str]:
        """Check if running with Administrator privileges on Windows.

        Returns:
            (is_admin: bool, error_message: str)
        """
        if platform.system().lower() != 'windows':
            return (True, "")  # Not Windows, privilege check not applicable

        try:
            import ctypes
            is_admin = ctypes.windll.shell32.IsUserAnAdmin()

            if not is_admin:
                error_msg = (
                    "Administrator privileges required for MFT reading. "
                    "Please run adarevm as Administrator."
                )
                return (False, error_msg)

            log.info("CLAUDE: Running with Administrator privileges - MFT access enabled")
            return (True, "")

        except Exception as e:
            error_msg = f"Failed to check admin privileges: {e}"
            log.error(f"CLAUDE: {error_msg}")
            return (False, error_msg)

    @staticmethod
    def extract_mft_to_file(output_path: Path, volume: str = "C:") -> Path:
        """Extract raw MFT file from volume to disk.

        Uses PowerShell command to copy $MFT file.

        Args:
            volume: Volume letter (default: C:)
            output_path: Where to save extracted MFT

        Returns:
            Path to extracted MFT file
        """
        log.info(f"CLAUDE: Extracting MFT from volume {volume}...")

        # PowerShell command to read raw MFT file
        # Note: Device path format is \\.\C:$MFT (no backslash before $MFT)
        ps_cmd = f"""
$bytes = [System.IO.File]::ReadAllBytes("\\\\.\\{volume}$MFT")
[System.IO.File]::WriteAllBytes("{output_path}", $bytes)
"""

        try:
            result = subprocess.run(
                ['powershell', '-NoProfile', '-NonInteractive', '-Command', ps_cmd],
                capture_output=True,
                text=True,
                timeout=300  # 5 minutes timeout
            )

            if result.returncode != 0:
                stderr = result.stderr.strip()
                raise MFTExtractionError(
                    f"PowerShell MFT extraction failed (exit code {result.returncode}): {stderr}"
                )

            if not output_path.exists():
                raise MFTExtractionError(f"MFT file was not created at {output_path}")

            file_size_mb = output_path.stat().st_size / (1024 * 1024)
            log.info(f"CLAUDE: MFT extracted successfully ({file_size_mb:.2f} MB)")

            return output_path

        except subprocess.TimeoutExpired:
            raise MFTExtractionError("MFT extraction timed out after 5 minutes")
        except OSError as e:
            raise MFTExtractionError(f"Failed to execute PowerShell: {e}")

    @staticmethod
    def get_mft_snapshot(volume: str = "C:",
                        root_path: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """Get filesystem snapshot by parsing MFT.

        Main entry point for MFT-based filesystem snapshots.

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

        # Step 2: Extract MFT to temp file
        temp_mft = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mft') as f:
                temp_mft = Path(f.name)

            MFTReader.extract_mft_to_file(temp_mft, volume)

            # Step 3: Parse MFT file
            result = MFTParser.parse_mft_file(temp_mft, root_path)

            log.info(f"CLAUDE: MFT snapshot complete. Total files: {len(result)}")
            return result

        finally:
            # Step 4: Clean up temp file
            if temp_mft and temp_mft.exists():
                try:
                    temp_mft.unlink()
                    log.info("CLAUDE: Cleaned up temporary MFT file")
                except OSError as e:
                    log.warning(f"CLAUDE: Failed to delete temp MFT file: {e}")
