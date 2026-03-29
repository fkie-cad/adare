"""
Disk image comparison for detecting filesystem changes.

This module compares a base disk image (pristine state) with an overlay
disk image (modified state) to identify added, removed, and modified files.

Comparison strategy:
1. Detect the root partition on the overlay disk
2. Scan both disks with virt-ls to build full file listings
3. Diff the listings by path, size, and mtime
4. Optionally extract changed file content via guestfish scripts

Extracted from QEMULifecycleStrategy to separate concerns and enable testing.
"""

import csv
import logging
import re
import subprocess
from datetime import datetime
from io import StringIO
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from adare.hypervisor.qemu.guestfish_client import GuestfishClient

log = logging.getLogger(__name__)


class DiskDiffComparator:
    """Compare base and overlay disk images to detect filesystem changes."""

    def __init__(self, guestfish_client: GuestfishClient):
        self.guestfish = guestfish_client

    def compare(
        self,
        base_disk_path: str,
        overlay_disk_path: str,
        extract_dir: Optional[Path] = None,
    ) -> Optional[Dict[str, List[Dict]]]:
        """Compare two disk images and return diff results.

        Uses manual virt-ls scanning (avoids virt-diff's unreliable
        auto-detection of operating systems).

        Args:
            base_disk_path: Path to immutable base disk (pristine state)
            overlay_disk_path: Path to overlay disk (modified state)
            extract_dir: Optional path where changed file content is extracted

        Returns:
            Diff dict: {added: [...], removed: [...], modified: [...]}
            None on failure
        """
        log.info("Comparing base disk vs overlay using manual virt-ls diff")
        log.debug(f"Base: {base_disk_path}")
        log.debug(f"Overlay: {overlay_disk_path}")

        return self._compare_disks_manual(
            base_disk_path, overlay_disk_path, extract_dir
        )

    def _compare_disks_manual(
        self,
        base_disk_path: str,
        overlay_disk_path: str,
        extract_dir: Optional[Path] = None,
    ) -> Optional[Dict[str, List[Dict]]]:
        """Manually compare disks using optimized guestfish single-boot scan.

        Args:
            base_disk_path: Path to base disk image
            overlay_disk_path: Path to overlay disk image
            extract_dir: Optional directory for extracting changed files

        Returns:
            Diff dict or None on failure
        """
        log.info(
            "Starting manual disk comparison using optimized guestfish scan"
        )

        # Detect root partition on the overlay
        # We assume the layout is identical on base.
        root_device, _ = self.guestfish.detect_root_filesystem(overlay_disk_path)
        log.debug(f"Detected root partition: {root_device}")

        # Parse partition number to map to sda/sdb in the combined session
        # We assume simple partitioning (sdaX). If LVM, this optimization
        # might fail but is valid for the Windows use case.
        part_match = re.search(r'(\d+)$', root_device)
        if not part_match:
            log.warning(
                f"Could not extract partition number from "
                f"{root_device}. Assuming LVM or complex layout - "
                f"optimization logic might require adjustment."
            )
            part_suffix = ""
        else:
            part_suffix = part_match.group(1)

        # Scan both disks
        base_files, overlay_files = self._scan_disks_via_guestfish(
            base_disk_path, overlay_disk_path, part_suffix
        )

        if base_files is None or overlay_files is None:
            log.error("Failed to scan disks")
            return None

        # Compute diff
        diff: Dict[str, List[Dict]] = {
            'added': [],
            'removed': [],
            'modified': [],
        }

        # Check for additions and modifications
        for path, meta in overlay_files.items():
            if path not in base_files:
                diff['added'].append({
                    'path': path,
                    'size': meta['size'],
                    'mtime': meta['mtime'],
                    'mtime_readable': meta['mtime_readable'],
                })
            else:
                base_meta = base_files[path]
                if (
                    meta['size'] != base_meta['size']
                    or meta['mtime'] != base_meta['mtime']
                ):
                    diff['modified'].append({
                        'path': path,
                        'size_before': base_meta['size'],
                        'size_after': meta['size'],
                        'mtime_before': base_meta['mtime'],
                        'mtime_after': meta['mtime'],
                        'mtime_before_readable': base_meta['mtime_readable'],
                        'mtime_after_readable': meta['mtime_readable'],
                    })

        # Check for removals
        for path, meta in base_files.items():
            if path not in overlay_files:
                diff['removed'].append({
                    'path': path,
                    'size': meta['size'],
                    'mtime': meta['mtime'],
                    'mtime_readable': meta['mtime_readable'],
                })

        log.info(
            f"Manual Diff complete: {len(diff['added'])} added, "
            f"{len(diff['removed'])} removed, "
            f"{len(diff['modified'])} modified"
        )

        # Extract file content if requested
        # This starts a NEW guestfish session (2nd boot), acceptable for stability.
        if extract_dir:
            self._extract_diff_files(
                base_disk_path, overlay_disk_path,
                root_device, diff, extract_dir
            )

        return diff

    def _scan_disks_via_guestfish(
        self,
        base_disk: str,
        overlay_disk: str,
        part_suffix: str,
    ) -> Tuple[Optional[Dict], Optional[Dict]]:
        """Scan both disks using separate virt-ls calls.

        Args:
            base_disk: Path to base disk image
            overlay_disk: Path to overlay disk image
            part_suffix: Partition number suffix (e.g. "4" for /dev/sda4)

        Returns:
            Tuple of (base_files, overlay_files) dicts mapping path to metadata.
            Returns (None, None) if either scan fails.
        """
        # Scan Base
        log.info("Scanning base disk with virt-ls...")
        base_files = self._scan_single_disk(base_disk, part_suffix)

        # Scan Overlay
        log.info("Scanning overlay disk with virt-ls...")
        overlay_files = self._scan_single_disk(overlay_disk, part_suffix)

        if base_files is None or overlay_files is None:
            return None, None

        log.info(
            f"Scanned {len(base_files)} base files, "
            f"{len(overlay_files)} overlay files"
        )
        return base_files, overlay_files

    def _scan_single_disk(
        self, disk_path: str, part_suffix: str
    ) -> Optional[Dict]:
        """Scan a single disk using virt-ls.

        Args:
            disk_path: Path to disk image
            part_suffix: Partition number suffix

        Returns:
            Dict mapping file paths to metadata, or None on failure
        """
        # virt-ls -a disk.img -m /dev/sda{suffix} --csv --time-t -l -R /
        # Note: We always use /dev/sda because we are mounting a single disk
        mount_dev = f"/dev/sda{part_suffix}"

        cmd = [
            'virt-ls',
            '-a', disk_path,
            '-m', mount_dev,
            '--csv',
            '--time-t',
            '-l',
            '-R',
            '/',
        ]

        log.debug(
            f"Running virt-ls on {disk_path} (mount: {mount_dev})"
        )

        result = subprocess.run(
            cmd, capture_output=True, text=True, check=False
        )

        if result.returncode != 0:
            log.error(
                f"virt-ls failed for {disk_path}: {result.stderr}"
            )
            return None

        files: Dict = {}

        # virt-ls output has no header
        # Columns: type, perms, size, atime, mtime, ctime, path
        reader = csv.reader(StringIO(result.stdout))
        for row in reader:
            if not row or len(row) < 7:
                continue

            size = int(row[2])
            mtime = int(row[4])
            path = row[6]

            files[path] = {
                'size': size,
                'mtime': mtime,
                'mtime_readable': datetime.fromtimestamp(mtime).isoformat(),
            }

        return files

    def _extract_diff_files(
        self,
        base_disk_path: str,
        overlay_disk_path: str,
        partition: str,
        diff_results: Dict[str, List[Dict]],
        extract_dir: Path,
    ) -> None:
        """Extract content of changed files from disks using batched guestfish.

        Args:
            base_disk_path: Path to base disk image
            overlay_disk_path: Path to overlay disk image
            partition: Partition device path (e.g. '/dev/sda4')
            diff_results: Diff dict with added/removed/modified lists
            extract_dir: Target directory for extracted files
        """
        log.info(f"Extracting diff content to {extract_dir}")
        extract_dir.mkdir(parents=True, exist_ok=True)

        # Create structure
        added_dir = extract_dir / 'added'
        removed_dir = extract_dir / 'removed'
        mod_base_dir = extract_dir / 'modified' / 'base'
        mod_overlay_dir = extract_dir / 'modified' / 'overlay'

        for d in [added_dir, removed_dir, mod_base_dir, mod_overlay_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # Prepare batch specs: (source, guest_path, host_path)
        specs: List[Tuple[str, str, Path]] = []

        # 1. Added files -> from Overlay
        for item in diff_results['added']:
            guest_path = item['path']
            rel_path = guest_path.lstrip('/')
            host_path = added_dir / rel_path
            specs.append(('overlay', guest_path, host_path))

        # 2. Removed files -> from Base
        for item in diff_results['removed']:
            guest_path = item['path']
            rel_path = guest_path.lstrip('/')
            host_path = removed_dir / rel_path
            specs.append(('base', guest_path, host_path))

        # 3. Modified files -> from Both
        for item in diff_results['modified']:
            guest_path = item['path']
            rel_path = guest_path.lstrip('/')
            specs.append(('base', guest_path, mod_base_dir / rel_path))
            specs.append(('overlay', guest_path, mod_overlay_dir / rel_path))

        if not specs:
            log.info("No files to extract.")
            return

        # Group by disk source to minimize guestfish invocations
        base_specs = [s for s in specs if s[0] == 'base']
        overlay_specs = [s for s in specs if s[0] == 'overlay']

        for name, disk_path, current_specs in [
            ('Base', base_disk_path, base_specs),
            ('Overlay', overlay_disk_path, overlay_specs),
        ]:
            if not current_specs:
                continue

            log.info(
                f"Extracting {len(current_specs)} files from "
                f"{name} disk"
            )

            # Create parent directories for all targets
            for _, _, target_path in current_specs:
                target_path.parent.mkdir(parents=True, exist_ok=True)

            # Build guestfish script
            script_lines = [
                'run',
                f'mount {partition} /',
            ]

            for _, guest_path, host_path in current_specs:
                script_lines.append(f"download {guest_path} {host_path}")

            # Execute batch
            self.guestfish.run_script(disk_path, script_lines)

    def _add_scanned_file(self, file_map: Dict, file_data: Dict) -> None:
        """Process and add a file record from filesystem_walk.

        Handles both standard and TSK-style output formats.

        Args:
            file_map: Dict to add the file record to
            file_data: Raw file data dict with path/size/mtime fields
        """
        path = file_data.get('path') or file_data.get('tsk_name')
        if not path:
            return

        # Clean path formatting
        path = path.strip().replace('"', '')

        try:
            # Handle size
            if 'size' in file_data:
                size = int(file_data['size'])
            elif 'tsk_size' in file_data:
                size = int(file_data['tsk_size'])
            else:
                size = 0

            # Handle mtime (seconds since epoch)
            if 'mtime' in file_data:
                mtime = int(file_data['mtime'])
            elif 'tsk_mtime_sec' in file_data:
                mtime = int(file_data['tsk_mtime_sec'])
            else:
                mtime = 0

            file_map[path] = {
                'size': size,
                'mtime': mtime,
                'mtime_readable': datetime.fromtimestamp(mtime).isoformat(),
            }
        except ValueError:
            pass  # Skip malformed records

    def parse_virt_diff_output(
        self, csv_output: str
    ) -> Dict[str, List[Dict]]:
        """Parse virt-diff CSV output into standard diff format.

        virt-diff CSV columns: Change,Path,Old Size,New Size,Old Time,New Time
        Change types: added, removed, changed

        Args:
            csv_output: CSV output from virt-diff

        Returns:
            Dict with keys: added, removed, modified
            (each containing list of file dicts)
        """
        diff: Dict[str, List[Dict]] = {
            'added': [],
            'removed': [],
            'modified': [],
        }

        reader = csv.DictReader(StringIO(csv_output))

        for row in reader:
            change_type = row.get('Change', '').strip()
            path = row.get('Path', '').strip()

            if change_type == 'added':
                diff['added'].append({
                    'path': path,
                    'size': int(row.get('New Size', 0) or 0),
                    'mtime': self._parse_virt_diff_time(
                        row.get('New Time', '')
                    ),
                    'mtime_readable': row.get('New Time', ''),
                })

            elif change_type == 'removed':
                diff['removed'].append({
                    'path': path,
                    'size': int(row.get('Old Size', 0) or 0),
                    'mtime': self._parse_virt_diff_time(
                        row.get('Old Time', '')
                    ),
                    'mtime_readable': row.get('Old Time', ''),
                })

            elif change_type == 'changed':
                diff['modified'].append({
                    'path': path,
                    'size_before': int(row.get('Old Size', 0) or 0),
                    'size_after': int(row.get('New Size', 0) or 0),
                    'mtime_before': self._parse_virt_diff_time(
                        row.get('Old Time', '')
                    ),
                    'mtime_after': self._parse_virt_diff_time(
                        row.get('New Time', '')
                    ),
                    'mtime_before_readable': row.get('Old Time', ''),
                    'mtime_after_readable': row.get('New Time', ''),
                })

        return diff

    def _parse_virt_diff_time(self, time_str: str) -> float:
        """Parse virt-diff timestamp to Unix epoch.

        Handles ISO-like format ("2024-01-15 10:30:45") and raw timestamps.

        Args:
            time_str: Timestamp string from virt-diff output

        Returns:
            Unix epoch float, or 0.0 if parsing fails
        """
        if not time_str:
            return 0.0

        try:
            dt = datetime.strptime(
                time_str.split('.')[0], '%Y-%m-%d %H:%M:%S'
            )
            return dt.timestamp()
        except (ValueError, AttributeError):
            try:
                return float(time_str)
            except (ValueError, TypeError):
                log.debug(f"Could not parse timestamp: {time_str}")
                return 0.0
