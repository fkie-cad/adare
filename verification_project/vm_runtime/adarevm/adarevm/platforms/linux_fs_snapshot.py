"""
Linux filesystem snapshot collection using find command.

This module provides snapshot capabilities for Linux filesystems, paralleling
the Windows MFT reader. It uses the find command to collect file metadata
including all 3 Linux timestamps (mtime, atime, ctime).
"""

import json
import logging
import subprocess
from typing import Dict, Any

log = logging.getLogger(__name__)


class LinuxFSSnapshotException(Exception):
    """Base exception for Linux filesystem snapshot errors."""
    pass


class LinuxFSSnapshot:
    """
    Linux filesystem snapshot collector.

    Collects file metadata using the find command, excluding virtual filesystems
    that aren't relevant for forensic analysis.
    """

    # Virtual/kernel filesystems to exclude
    EXCLUDED_PATHS = ['/proc', '/sys', '/dev', '/run']

    @staticmethod
    def get_snapshot(root_path: str = '/') -> Dict[str, Dict[str, Any]]:
        """
        Get filesystem snapshot using find command.

        Args:
            root_path: Root directory to scan (default: '/')

        Returns:
            Dict mapping file paths to metadata in common format:
            {
              "/path/to/file": {
                "size": 1024,
                "mtime": 1234567890.0,
                "timestamps": {
                  "modified": 1234567890.0,
                  "accessed": 1234567890.0,
                  "changed": 1234567890.0
                }
              }
            }

        Raises:
            LinuxFSSnapshotException: If snapshot collection fails
        """
        log.info(f"CLAUDE: Starting Linux filesystem snapshot from {root_path}")

        try:
            cmd = LinuxFSSnapshot._build_find_command(root_path)
            log.debug(f"CLAUDE: Executing command: {cmd}")

            # Execute find command
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=600  # 10 minute timeout
            )

            if result.returncode != 0 and result.returncode != 1:
                # Return code 1 is normal (some permission denied errors)
                log.warning(f"CLAUDE: Find command returned code {result.returncode}")

            # Parse output
            files = {}
            line_count = 0
            error_count = 0

            for line in result.stdout.strip().split('\n'):
                if not line:
                    continue

                line_count += 1

                try:
                    path, mtime, atime, ctime, size = LinuxFSSnapshot._parse_line(line)

                    files[path] = {
                        'size': size,
                        'mtime': mtime,
                        'timestamps': {
                            'modified': mtime,
                            'accessed': atime,
                            'changed': ctime
                        }
                    }

                    # Progress logging for large scans
                    if line_count % 100000 == 0:
                        log.info(f"CLAUDE: Processed {line_count} files...")

                except ValueError as e:
                    error_count += 1
                    if error_count <= 10:  # Only log first 10 errors
                        log.warning(f"CLAUDE: Failed to parse line: {e}")
                    continue

            log.info(f"CLAUDE: Linux snapshot complete: {len(files)} files collected")
            if error_count > 0:
                log.warning(f"CLAUDE: Skipped {error_count} files due to parsing errors")

            return files

        except subprocess.TimeoutExpired as e:
            msg = f"Snapshot collection timed out after {e.timeout} seconds"
            log.error(f"CLAUDE: {msg}")
            raise LinuxFSSnapshotException(msg)

        except subprocess.SubprocessError as e:
            msg = f"Failed to execute find command: {e}"
            log.error(f"CLAUDE: {msg}")
            raise LinuxFSSnapshotException(msg)

        except Exception as e:
            msg = f"Unexpected error during snapshot collection: {e}"
            log.error(f"CLAUDE: {msg}")
            raise LinuxFSSnapshotException(msg)

    @staticmethod
    def _build_find_command(root_path: str = '/') -> str:
        """
        Build find command with proper exclusions for virtual filesystems.

        Args:
            root_path: Root directory to scan

        Returns:
            Complete find command string
        """
        # Build exclusion pattern: \( -path /proc -o -path /sys ... \) -prune -o
        excludes = ' -o '.join([f'-path {p}' for p in LinuxFSSnapshot.EXCLUDED_PATHS])

        # Find all regular files, excluding virtual filesystems
        # Output format: path|mtime|atime|ctime|size
        cmd = (
            f'find {root_path} '
            f'\\( {excludes} \\) -prune -o '
            f'-type f -printf "%p|%T@|%A@|%C@|%s\\n" '
            f'2>/dev/null'
        )

        return cmd

    @staticmethod
    def _parse_line(line: str) -> tuple:
        """
        Parse single line of find output.

        Args:
            line: Output line in format: path|mtime|atime|ctime|size

        Returns:
            Tuple of (path, mtime, atime, ctime, size)

        Raises:
            ValueError: If line format is invalid
        """
        parts = line.strip().split('|')

        if len(parts) != 5:
            raise ValueError(f"Expected 5 fields, got {len(parts)}: {line[:100]}")

        path, mtime_str, atime_str, ctime_str, size_str = parts

        try:
            mtime = float(mtime_str)
            atime = float(atime_str)
            ctime = float(ctime_str)
            size = int(size_str)
        except ValueError as e:
            raise ValueError(f"Failed to parse numeric fields: {e}")

        return (path, mtime, atime, ctime, size)


# Convenience function for command-line execution
def main():
    """Command-line interface for testing."""
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    try:
        result = LinuxFSSnapshot.get_snapshot()
        print(json.dumps(result, indent=None))
    except LinuxFSSnapshotException as e:
        log.error(f"Snapshot failed: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
