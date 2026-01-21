"""
Filesystem snapshot and diff utilities for forensic analysis.

Provides OS-specific commands to capture filesystem state (file paths + timestamps)
and calculate differences between snapshots.
"""

import logging
import json
import csv
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

log = logging.getLogger(__name__)


class FilesystemSnapshot:
    """Represents a filesystem snapshot with file metadata."""

    def __init__(self, files: Dict[str, Dict[str, Any]], timestamp: str, os_type: str):
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

    def to_dict(self) -> Dict:
        """Serialize snapshot to dict."""
        return {
            'timestamp': self.timestamp,
            'os_type': self.os_type,
            'file_count': len(self.files),
            'files': self.files
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'FilesystemSnapshot':
        """Deserialize snapshot from dict."""
        return cls(
            files=data['files'],
            timestamp=data['timestamp'],
            os_type=data['os_type']
        )


def get_snapshot_command(os_type: str, root_path: Optional[str] = None) -> str:
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
        python_cmd = (
            f"python -c \""
            f"from adarevm.platforms.linux_fs_snapshot import LinuxFSSnapshot; "
            f"import json; "
            f"result = LinuxFSSnapshot.get_snapshot(); "
            f"print(json.dumps(result, indent=None))"
            f"\""
        )
        return python_cmd

    elif os_type == 'windows':
        # Windows: use MFT reader for efficient snapshot with all 4 NTFS timestamps
        scan_root = root_path or 'C:\\'
        # Escape single quotes for Python inline command
        scan_root_escaped = scan_root.replace("'", "\\'")

        # Python command to run MFT reader
        python_cmd = (
            f"python -c \""
            f"from adarevm.platforms.mft_reader import MFTReader; "
            f"import json; "
            f"result = MFTReader.get_mft_snapshot(volume='C:', root_path='{scan_root_escaped}'); "
            f"print(json.dumps(result, indent=None))"
            f"\""
        )
        return python_cmd

    else:
        raise ValueError(f"Unsupported OS type: {os_type}")


def parse_snapshot_output(output: str, os_type: str) -> Dict[str, Dict[str, Any]]:
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
        raise ValueError(f"Invalid JSON output from snapshot command: {e}")


def calculate_diff(before: FilesystemSnapshot, after: FilesystemSnapshot) -> Dict[str, List[Dict]]:
    """
    Calculate differences between two snapshots.

    Args:
        before: Snapshot taken before changes
        after: Snapshot taken after changes

    Returns:
        Dict with keys: added, removed, modified (each is list of file info dicts)
    """
    before_paths = set(before.files.keys())
    after_paths = set(after.files.keys())

    # Files added (in after but not in before)
    added_paths = after_paths - before_paths
    added = [
        {
            'path': path,
            'size': after.files[path]['size'],
            'mtime': after.files[path]['mtime'],
            'mtime_readable': datetime.fromtimestamp(after.files[path]['mtime']).isoformat()
        }
        for path in sorted(added_paths)
    ]

    # Files removed (in before but not in after)
    removed_paths = before_paths - after_paths
    removed = [
        {
            'path': path,
            'size': before.files[path]['size'],
            'mtime': before.files[path]['mtime'],
            'mtime_readable': datetime.fromtimestamp(before.files[path]['mtime']).isoformat()
        }
        for path in sorted(removed_paths)
    ]

    # Files modified (in both but mtime changed)
    common_paths = before_paths & after_paths
    modified = []
    # Timestamp comparison tolerance to avoid floating-point rounding errors
    # NTFS timestamps (100ns precision) converted to Unix epoch may have precision loss
    TIMESTAMP_EPSILON = 0.0001  # 0.1ms tolerance
    for path in sorted(common_paths):
        before_mtime = before.files[path]['mtime']
        after_mtime = after.files[path]['mtime']

        # Consider modified if mtime differs beyond epsilon threshold
        # Use epsilon comparison to avoid false positives from float rounding
        if abs(before_mtime - after_mtime) > TIMESTAMP_EPSILON:
            modified.append({
                'path': path,
                'size_before': before.files[path]['size'],
                'size_after': after.files[path]['size'],
                'mtime_before': before_mtime,
                'mtime_after': after_mtime,
                'mtime_before_readable': datetime.fromtimestamp(before_mtime).isoformat(),
                'mtime_after_readable': datetime.fromtimestamp(after_mtime).isoformat()
            })

    return {
        'added': added,
        'removed': removed,
        'modified': modified
    }


def export_diff_json(diff: Dict, output_path: Path, metadata: Optional[Dict] = None):
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


def export_diff_csv(diff: Dict, output_path: Path):
    """
    Export diff to CSV file (human-readable format).

    Args:
        diff: Diff dict from calculate_diff()
        output_path: Path to output CSV file
    """
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)

        # Header
        writer.writerow(['Change Type', 'Path', 'Size Before', 'Size After', 'Modified Time Before', 'Modified Time After'])

        # Added files
        for file_info in diff['added']:
            writer.writerow([
                'ADDED',
                file_info['path'],
                '',
                file_info['size'],
                '',
                file_info['mtime_readable']
            ])

        # Removed files
        for file_info in diff['removed']:
            writer.writerow([
                'REMOVED',
                file_info['path'],
                file_info['size'],
                '',
                file_info['mtime_readable'],
                ''
            ])

        # Modified files
        for file_info in diff['modified']:
            writer.writerow([
                'MODIFIED',
                file_info['path'],
                file_info['size_before'],
                file_info['size_after'],
                file_info['mtime_before_readable'],
                file_info['mtime_after_readable']
            ])

    log.info(f"Exported filesystem diff CSV to {output_path}")
