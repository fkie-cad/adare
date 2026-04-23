"""
Filesystem snapshot and diff utilities for forensic analysis.

Provides OS-specific commands to capture filesystem state (file paths + timestamps)
and calculate differences between snapshots.
"""

import csv
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class FilesystemSnapshot:
    """Represents a filesystem snapshot with file metadata."""

    def __init__(self, files: dict[str, dict[str, Any]], timestamp: str, os_type: str):
        """
        Initialize snapshot.

        Args:
            files: Dict mapping file path -> {mtime: float, size: int}
            timestamp: ISO timestamp when snapshot was captured
            os_type: 'Windows' or 'Linux'
        """
        self.files = files
        self.timestamp = timestamp
        self.os_type = os_type

    def to_dict(self) -> dict:
        """Serialize snapshot to dict."""
        return {
            'timestamp': self.timestamp,
            'os_type': self.os_type,
            'file_count': len(self.files),
            'files': self.files
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'FilesystemSnapshot':
        """Deserialize snapshot from dict."""
        return cls(
            files=data['files'],
            timestamp=data['timestamp'],
            os_type=data['os_type']
        )


def get_snapshot_command(os_type: str, root_path: str | None = None) -> str:
    """
    Get OS-specific command to capture filesystem snapshot.

    Args:
        os_type: 'Windows' or 'Linux'
        root_path: Root path to scan (default: / or C:\\)

    Returns:
        Shell command string
    """
    if os_type == 'linux':
        # Linux: use LinuxFSSnapshot module (parallels Windows MFT approach)
        return (
            "python -c \""
            "from adarevm.platforms.linux_fs_snapshot import LinuxFSSnapshot; "
            "import json; "
            "result = LinuxFSSnapshot.get_snapshot(); "
            "print(json.dumps(result, indent=None))"
            "\""
        )

    if os_type == 'windows':
        # Windows: use MFT reader for efficient snapshot with all 4 NTFS timestamps
        scan_root = root_path or 'C:\\'
        # Escape single quotes for Python inline command
        scan_root_escaped = scan_root.replace("'", "\\'")

        # Python command to run MFT reader
        return (
            f"python -c \""
            f"from adarevm.platforms.mft_reader import MFTReader; "
            f"import json; "
            f"result = MFTReader.get_mft_snapshot(volume='C:', root_path='{scan_root_escaped}'); "
            f"print(json.dumps(result, indent=None))"
            f"\""
        )

    raise ValueError(f"Unsupported OS type: {os_type}")


def parse_snapshot_output(output: str, os_type: str) -> dict[str, dict[str, Any]]:
    """
    Parse command output into file metadata dict.
    Both Windows and Linux now return JSON in common format.

    Args:
        output: Raw command stdout (JSON)
        os_type: 'Windows' or 'Linux'

    Returns:
        Dict mapping file path -> {mtime: float, size: int, timestamps: {...}}

    Raises:
        ValueError: If parsing fails
    """
    files = {}

    try:
        # Both platforms now return JSON
        data = json.loads(output)

        if not isinstance(data, dict):
            raise ValueError(f"Expected dict, got {type(data)}")

        # Process each file entry
        for path, metadata in data.items():
            # Backward compatibility: migrate old format to new format
            if 'timestamps' not in metadata:
                # Old format - migrate to new format
                log.debug(f"Migrating old format for {path}")
                metadata['timestamps'] = {}

                # Copy timestamp fields to nested object
                for ts_field in ['created', 'modified', 'accessed', 'mft_modified', 'changed']:
                    if ts_field in metadata:
                        metadata['timestamps'][ts_field] = metadata[ts_field]

                # Ensure mtime is set (primary timestamp for diff)
                if 'mtime' not in metadata:
                    metadata['mtime'] = metadata.get('modified', 0.0)

            # Validate required fields
            if 'mtime' not in metadata or 'size' not in metadata:
                log.warning(f"Missing required fields (mtime, size) for {path}, skipping")
                continue

            files[path] = metadata

        log.info(f"Parsed {len(files)} files from {os_type} snapshot")
        return files

    except json.JSONDecodeError as e:
        log.error(f"Failed to parse JSON output: {e}")
        raise ValueError(f"Invalid JSON output from snapshot command: {e}") from e


def _get_timestamp_fields(snapshot: FilesystemSnapshot) -> list[str]:
    """Get the relevant timestamp field names based on OS type.

    Windows (NTFS/MFT): created, modified, accessed, mft_modified
    Linux: modified, accessed, changed
    """
    if snapshot.os_type == 'Windows':
        return ['created', 'modified', 'accessed', 'mft_modified']
    return ['modified', 'accessed', 'changed']


def _get_all_timestamps(file_meta: dict[str, Any]) -> dict[str, float]:
    """Extract all timestamps from file metadata, checking nested 'timestamps' dict."""
    timestamps = {}
    ts_dict = file_meta.get('timestamps', {})
    for key in ['created', 'modified', 'accessed', 'mft_modified', 'changed']:
        if key in ts_dict:
            timestamps[key] = ts_dict[key]
        elif key in file_meta:
            timestamps[key] = file_meta[key]
    return timestamps


def calculate_diff(before: FilesystemSnapshot, after: FilesystemSnapshot) -> dict[str, list[dict]]:
    """
    Calculate differences between two snapshots.

    Compares ALL available timestamps (not just mtime) to detect modifications.
    A file is considered "modified" if ANY timestamp differs between snapshots.

    Args:
        before: Snapshot taken before changes
        after: Snapshot taken after changes

    Returns:
        Dict with keys: added, removed, modified (each is list of file info dicts)
    """
    before_paths = set(before.files.keys())
    after_paths = set(after.files.keys())
    ts_fields = _get_timestamp_fields(after)

    # Files added (in after but not in before)
    added_paths = after_paths - before_paths
    added = []
    for path in sorted(added_paths):
        entry = {
            'path': path,
            'size': after.files[path]['size'],
            'mtime': after.files[path]['mtime'],
            'mtime_readable': datetime.fromtimestamp(after.files[path]['mtime']).isoformat(),
            'timestamps': _get_all_timestamps(after.files[path]),
        }
        added.append(entry)

    # Files removed (in before but not in after)
    removed_paths = before_paths - after_paths
    removed = []
    for path in sorted(removed_paths):
        entry = {
            'path': path,
            'size': before.files[path]['size'],
            'mtime': before.files[path]['mtime'],
            'mtime_readable': datetime.fromtimestamp(before.files[path]['mtime']).isoformat(),
            'timestamps': _get_all_timestamps(before.files[path]),
        }
        removed.append(entry)

    # Files modified (in both but ANY timestamp changed)
    common_paths = before_paths & after_paths
    modified = []
    # Timestamp comparison tolerance to avoid floating-point rounding errors
    # NTFS timestamps (100ns precision) converted to Unix epoch may have precision loss
    TIMESTAMP_EPSILON = 0.0001  # 0.1ms tolerance
    for path in sorted(common_paths):
        before_ts = _get_all_timestamps(before.files[path])
        after_ts = _get_all_timestamps(after.files[path])

        # Check all relevant timestamp fields for changes
        timestamp_changes = {}
        for field in ts_fields:
            bval = before_ts.get(field, 0.0)
            aval = after_ts.get(field, 0.0)
            if abs(bval - aval) > TIMESTAMP_EPSILON:
                timestamp_changes[field] = {
                    'before': bval,
                    'after': aval,
                    'before_readable': datetime.fromtimestamp(bval).isoformat(),
                    'after_readable': datetime.fromtimestamp(aval).isoformat(),
                }

        if timestamp_changes:
            before_mtime = before.files[path]['mtime']
            after_mtime = after.files[path]['mtime']
            modified.append({
                'path': path,
                'size_before': before.files[path]['size'],
                'size_after': after.files[path]['size'],
                'mtime_before': before_mtime,
                'mtime_after': after_mtime,
                'mtime_before_readable': datetime.fromtimestamp(before_mtime).isoformat(),
                'mtime_after_readable': datetime.fromtimestamp(after_mtime).isoformat(),
                'timestamps_before': before_ts,
                'timestamps_after': after_ts,
                'timestamp_changes': timestamp_changes,
            })

    return {
        'added': added,
        'removed': removed,
        'modified': modified
    }


def export_diff_json(diff: dict, output_path: Path, metadata: dict | None = None):
    """
    Export diff to JSON file.

    Args:
        diff: Diff dict from calculate_diff()
        output_path: Path to output JSON file
        metadata: Optional metadata to include (experiment name, timestamps, etc.)
    """
    output_data = {
        'metadata': metadata or {},
        'summary': {
            'added_count': len(diff['added']),
            'removed_count': len(diff['removed']),
            'modified_count': len(diff['modified'])
        },
        'changes': diff
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2)

    log.info(f"Exported filesystem diff JSON to {output_path}")


def export_diff_csv(diff: dict, output_path: Path):
    """
    Export diff to CSV file with all available timestamps.

    Args:
        diff: Diff dict from calculate_diff()
        output_path: Path to output CSV file
    """
    # All possible timestamp columns (superset of Windows + Linux)
    ts_names = ['created', 'modified', 'accessed', 'mft_modified', 'changed']

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)

        # Build header with before/after columns for every timestamp
        header = ['Change Type', 'Path', 'Size Before', 'Size After']
        for ts in ts_names:
            header.append(f'{ts} Before')
            header.append(f'{ts} After')
        header.append('Changed Timestamps')
        writer.writerow(header)

        def _ts_readable(epoch: float | None) -> str:
            if epoch is None or epoch == 0.0:
                return ''
            return datetime.fromtimestamp(epoch).isoformat()

        # Added files
        for file_info in diff['added']:
            row = ['ADDED', file_info['path'], '', file_info['size']]
            timestamps = file_info.get('timestamps', {})
            for ts in ts_names:
                row.append('')  # no "before" for added
                row.append(_ts_readable(timestamps.get(ts)))
            row.append('')  # no changed-timestamps indicator
            writer.writerow(row)

        # Removed files
        for file_info in diff['removed']:
            row = ['REMOVED', file_info['path'], file_info['size'], '']
            timestamps = file_info.get('timestamps', {})
            for ts in ts_names:
                row.append(_ts_readable(timestamps.get(ts)))
                row.append('')  # no "after" for removed
            row.append('')
            writer.writerow(row)

        # Modified files
        for file_info in diff['modified']:
            row = ['MODIFIED', file_info['path'], file_info['size_before'], file_info['size_after']]
            ts_before = file_info.get('timestamps_before', {})
            ts_after = file_info.get('timestamps_after', {})
            for ts in ts_names:
                row.append(_ts_readable(ts_before.get(ts)))
                row.append(_ts_readable(ts_after.get(ts)))
            changed = file_info.get('timestamp_changes', {})
            row.append(';'.join(sorted(changed.keys())) if changed else '')
            writer.writerow(row)

    log.info(f"Exported filesystem diff CSV to {output_path}")


def export_diff_bodyfile(
    diff: dict,
    output_path: Path,
    snapshot_before: FilesystemSnapshot | None = None,
    snapshot_after: FilesystemSnapshot | None = None,
):
    """
    Export diff in mactime bodyfile format (pipe-delimited).

    Compatible with Plaso/log2timeline/mactime for forensic timeline analysis.
    Format: MD5|name|inode|mode_as_string|UID|GID|size|atime|mtime|ctime|crtime

    Args:
        diff: Diff dict from calculate_diff()
        output_path: Path to output bodyfile
        snapshot_before: Optional before-snapshot for metadata header
        snapshot_after: Optional after-snapshot for metadata header
    """

    def _epoch_int(ts_dict: dict[str, float], key: str) -> int:
        """Get timestamp as integer epoch, defaulting to 0."""
        val = ts_dict.get(key, 0.0)
        return int(val) if val else 0

    def _write_bodyfile_line(f, path: str, size: int, timestamps: dict[str, float], os_type: str, comment: str = ''):
        """Write a single bodyfile line.

        Mapping to bodyfile columns:
          atime = accessed
          mtime = modified
          ctime = changed (Linux) or mft_modified (Windows)
          crtime = created (Windows only, 0 on Linux)
        """
        atime = _epoch_int(timestamps, 'accessed')
        mtime = _epoch_int(timestamps, 'modified')
        if os_type == 'Windows':
            ctime = _epoch_int(timestamps, 'mft_modified')
            crtime = _epoch_int(timestamps, 'created')
        else:
            ctime = _epoch_int(timestamps, 'changed')
            crtime = 0

        name = f"{path} ({comment})" if comment else path
        # MD5|name|inode|mode_as_string|UID|GID|size|atime|mtime|ctime|crtime
        f.write(f"0|{name}|0||0|0|{size}|{atime}|{mtime}|{ctime}|{crtime}\n")

    # Determine OS type from snapshots or infer from diff content
    os_type = 'Windows'
    if snapshot_after:
        os_type = snapshot_after.os_type
    elif snapshot_before:
        os_type = snapshot_before.os_type

    with open(output_path, 'w', encoding='utf-8') as f:
        # Comment header
        f.write("# ADARE filesystem diff bodyfile (mactime format)\n")
        f.write(f"# OS type: {os_type}\n")
        if snapshot_before:
            f.write(f"# Snapshot before: {snapshot_before.timestamp}\n")
        if snapshot_after:
            f.write(f"# Snapshot after: {snapshot_after.timestamp}\n")
        f.write(f"# Generated: {datetime.now().isoformat()}\n")
        f.write("#\n")

        # Added files — use after timestamps
        for entry in diff.get('added', []):
            timestamps = entry.get('timestamps', {})
            _write_bodyfile_line(f, entry['path'], entry['size'], timestamps, os_type, comment='ADDED')

        # Removed files — use before timestamps
        for entry in diff.get('removed', []):
            timestamps = entry.get('timestamps', {})
            _write_bodyfile_line(f, entry['path'], entry['size'], timestamps, os_type, comment='REMOVED')

        # Modified files — use after timestamps
        for entry in diff.get('modified', []):
            timestamps = entry.get('timestamps_after', entry.get('timestamps', {}))
            size = entry.get('size_after', entry.get('size', 0))
            _write_bodyfile_line(f, entry['path'], size, timestamps, os_type, comment='MODIFIED')

    log.info(f"Exported filesystem diff bodyfile to {output_path}")
