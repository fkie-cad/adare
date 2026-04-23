"""Tests for DiskDiffComparator - disk image comparison."""

from unittest.mock import MagicMock, patch

import pytest

from adare.hypervisor.qemu.disk_diff import DiskDiffComparator


@pytest.fixture
def mock_guestfish():
    """Create a mock GuestfishClient."""
    return MagicMock()


@pytest.fixture
def comparator(mock_guestfish):
    """Create a DiskDiffComparator with mocked guestfish."""
    return DiskDiffComparator(mock_guestfish)


class TestCompare:
    """Tests for DiskDiffComparator.compare()."""

    @patch('adare.hypervisor.qemu.disk_diff.subprocess.run')
    def test_compare_returns_diff_dict_structure(
        self, mock_run, comparator, mock_guestfish
    ):
        """compare() returns dict with added/removed/modified keys."""
        mock_guestfish.detect_root_filesystem.return_value = (
            '/dev/sda4', 'ntfs'
        )

        # virt-ls returns CSV: type,perms,size,atime,mtime,ctime,path
        base_csv = '-,0100644,100,1700000000,1700000000,1700000000,/file1.txt\n'
        overlay_csv = (
            '-,0100644,100,1700000000,1700000000,1700000000,/file1.txt\n'
            '-,0100644,200,1700000001,1700000001,1700000001,/file2.txt\n'
        )

        # First call = base scan, second call = overlay scan
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=base_csv, stderr=''),
            MagicMock(returncode=0, stdout=overlay_csv, stderr=''),
        ]

        result = comparator.compare('/base.qcow2', '/overlay.qcow2')

        assert result is not None
        assert 'added' in result
        assert 'removed' in result
        assert 'modified' in result
        # file2.txt is added (only in overlay)
        assert len(result['added']) == 1
        assert result['added'][0]['path'] == '/file2.txt'
        # file1.txt is unchanged
        assert len(result['modified']) == 0
        assert len(result['removed']) == 0

    @patch('adare.hypervisor.qemu.disk_diff.subprocess.run')
    def test_compare_returns_none_when_scan_fails(
        self, mock_run, comparator, mock_guestfish
    ):
        """compare() returns None when virt-ls scan fails."""
        mock_guestfish.detect_root_filesystem.return_value = (
            '/dev/sda1', 'ext4'
        )

        # Both scans fail
        mock_run.return_value = MagicMock(
            returncode=1, stdout='', stderr='error'
        )

        result = comparator.compare('/base.qcow2', '/overlay.qcow2')

        assert result is None

    @patch('adare.hypervisor.qemu.disk_diff.subprocess.run')
    def test_compare_identical_disks_returns_empty_diff(
        self, mock_run, comparator, mock_guestfish
    ):
        """compare() returns empty diff when disks are identical."""
        mock_guestfish.detect_root_filesystem.return_value = (
            '/dev/sda1', 'ext4'
        )

        identical_csv = (
            '-,0100644,100,1700000000,1700000000,1700000000,/file1.txt\n'
            '-,0100644,200,1700000000,1700000000,1700000000,/file2.txt\n'
        )

        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=identical_csv, stderr=''),
            MagicMock(returncode=0, stdout=identical_csv, stderr=''),
        ]

        result = comparator.compare('/base.qcow2', '/overlay.qcow2')

        assert result is not None
        assert len(result['added']) == 0
        assert len(result['removed']) == 0
        assert len(result['modified']) == 0

    @patch('adare.hypervisor.qemu.disk_diff.subprocess.run')
    def test_compare_detects_modifications(
        self, mock_run, comparator, mock_guestfish
    ):
        """compare() detects modified files by size or mtime change."""
        mock_guestfish.detect_root_filesystem.return_value = (
            '/dev/sda2', 'ext4'
        )

        base_csv = (
            '-,0100644,100,1700000000,1700000000,1700000000,/config.txt\n'
        )
        overlay_csv = (
            '-,0100644,150,1700000000,1700000099,1700000000,/config.txt\n'
        )

        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=base_csv, stderr=''),
            MagicMock(returncode=0, stdout=overlay_csv, stderr=''),
        ]

        result = comparator.compare('/base.qcow2', '/overlay.qcow2')

        assert result is not None
        assert len(result['modified']) == 1
        mod = result['modified'][0]
        assert mod['path'] == '/config.txt'
        assert mod['size_before'] == 100
        assert mod['size_after'] == 150

    @patch('adare.hypervisor.qemu.disk_diff.subprocess.run')
    def test_compare_detects_removals(
        self, mock_run, comparator, mock_guestfish
    ):
        """compare() detects files present in base but missing from overlay."""
        mock_guestfish.detect_root_filesystem.return_value = (
            '/dev/sda1', 'ext4'
        )

        base_csv = (
            '-,0100644,100,1700000000,1700000000,1700000000,/removed.txt\n'
            '-,0100644,200,1700000000,1700000000,1700000000,/kept.txt\n'
        )
        overlay_csv = (
            '-,0100644,200,1700000000,1700000000,1700000000,/kept.txt\n'
        )

        mock_run.side_effect = [
            MagicMock(returncode=0, stdout=base_csv, stderr=''),
            MagicMock(returncode=0, stdout=overlay_csv, stderr=''),
        ]

        result = comparator.compare('/base.qcow2', '/overlay.qcow2')

        assert result is not None
        assert len(result['removed']) == 1
        assert result['removed'][0]['path'] == '/removed.txt'


class TestScanDisksViaGuestfish:
    """Tests for DiskDiffComparator._scan_disks_via_guestfish()."""

    @patch('adare.hypervisor.qemu.disk_diff.subprocess.run')
    def test_scan_returns_file_dicts(self, mock_run, comparator):
        """_scan_disks_via_guestfish() returns file metadata dicts."""
        csv_data = (
            '-,0100644,1024,1700000000,1700000010,1700000000,/etc/hosts\n'
            '-,0100644,2048,1700000000,1700000020,1700000000,/etc/passwd\n'
        )
        mock_run.return_value = MagicMock(
            returncode=0, stdout=csv_data, stderr=''
        )

        base_files, overlay_files = comparator._scan_disks_via_guestfish(
            '/base.qcow2', '/overlay.qcow2', '1'
        )

        assert base_files is not None
        assert overlay_files is not None
        assert '/etc/hosts' in base_files
        assert base_files['/etc/hosts']['size'] == 1024
        assert base_files['/etc/hosts']['mtime'] == 1700000010

    @patch('adare.hypervisor.qemu.disk_diff.subprocess.run')
    def test_scan_uses_correct_mount_device(self, mock_run, comparator):
        """_scan_disks_via_guestfish() constructs /dev/sda{suffix} mount."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout='', stderr=''
        )

        comparator._scan_disks_via_guestfish(
            '/base.qcow2', '/overlay.qcow2', '4'
        )

        # Both calls should use /dev/sda4
        assert mock_run.call_count == 2
        for c in mock_run.call_args_list:
            cmd = c[0][0]
            assert '-m' in cmd
            idx = cmd.index('-m')
            assert cmd[idx + 1] == '/dev/sda4'

    @patch('adare.hypervisor.qemu.disk_diff.subprocess.run')
    def test_scan_returns_none_pair_on_failure(self, mock_run, comparator):
        """_scan_disks_via_guestfish() returns (None, None) on scan failure."""
        mock_run.return_value = MagicMock(
            returncode=1, stdout='', stderr='disk error'
        )

        base, overlay = comparator._scan_disks_via_guestfish(
            '/base.qcow2', '/overlay.qcow2', '1'
        )

        assert base is None
        assert overlay is None

    @patch('adare.hypervisor.qemu.disk_diff.subprocess.run')
    def test_scan_skips_malformed_rows(self, mock_run, comparator):
        """_scan_disks_via_guestfish() skips rows with fewer than 7 columns."""
        csv_data = (
            '-,0100644,1024,1700000000,1700000010,1700000000,/good.txt\n'
            'bad,row,only\n'
            '\n'
        )
        mock_run.return_value = MagicMock(
            returncode=0, stdout=csv_data, stderr=''
        )

        base_files, _ = comparator._scan_disks_via_guestfish(
            '/base.qcow2', '/overlay.qcow2', '1'
        )

        assert base_files is not None
        assert len(base_files) == 1
        assert '/good.txt' in base_files


class TestParseVirtDiffOutput:
    """Tests for DiskDiffComparator.parse_virt_diff_output()."""

    def test_parses_added_files(self, comparator):
        """parse_virt_diff_output() parses 'added' change type."""
        csv_input = (
            'Change,Path,Old Size,New Size,Old Time,New Time\n'
            'added,/new_file.txt,,1024,,2024-01-15 10:30:45\n'
        )

        result = comparator.parse_virt_diff_output(csv_input)

        assert len(result['added']) == 1
        assert result['added'][0]['path'] == '/new_file.txt'
        assert result['added'][0]['size'] == 1024

    def test_parses_removed_files(self, comparator):
        """parse_virt_diff_output() parses 'removed' change type."""
        csv_input = (
            'Change,Path,Old Size,New Size,Old Time,New Time\n'
            'removed,/old_file.txt,512,,2024-01-10 08:00:00,\n'
        )

        result = comparator.parse_virt_diff_output(csv_input)

        assert len(result['removed']) == 1
        assert result['removed'][0]['path'] == '/old_file.txt'
        assert result['removed'][0]['size'] == 512

    def test_parses_changed_files(self, comparator):
        """parse_virt_diff_output() parses 'changed' change type as modified."""
        csv_input = (
            'Change,Path,Old Size,New Size,Old Time,New Time\n'
            'changed,/config.txt,100,200,2024-01-10 08:00:00,'
            '2024-01-15 10:30:45\n'
        )

        result = comparator.parse_virt_diff_output(csv_input)

        assert len(result['modified']) == 1
        mod = result['modified'][0]
        assert mod['path'] == '/config.txt'
        assert mod['size_before'] == 100
        assert mod['size_after'] == 200

    def test_parses_multiple_entries(self, comparator):
        """parse_virt_diff_output() handles mixed change types."""
        csv_input = (
            'Change,Path,Old Size,New Size,Old Time,New Time\n'
            'added,/new1.txt,,100,,2024-01-15 10:30:45\n'
            'added,/new2.txt,,200,,2024-01-15 10:30:46\n'
            'removed,/old.txt,50,,2024-01-10 08:00:00,\n'
            'changed,/mod.txt,100,150,2024-01-10 08:00:00,'
            '2024-01-15 10:30:45\n'
        )

        result = comparator.parse_virt_diff_output(csv_input)

        assert len(result['added']) == 2
        assert len(result['removed']) == 1
        assert len(result['modified']) == 1

    def test_returns_empty_diff_for_empty_input(self, comparator):
        """parse_virt_diff_output() returns empty diff for empty CSV."""
        result = comparator.parse_virt_diff_output(
            'Change,Path,Old Size,New Size,Old Time,New Time\n'
        )

        assert result == {'added': [], 'removed': [], 'modified': []}

    def test_handles_missing_size_gracefully(self, comparator):
        """parse_virt_diff_output() treats empty size fields as 0."""
        csv_input = (
            'Change,Path,Old Size,New Size,Old Time,New Time\n'
            'added,/empty.txt,,,,,\n'
        )

        result = comparator.parse_virt_diff_output(csv_input)

        assert len(result['added']) == 1
        assert result['added'][0]['size'] == 0


class TestExtractDiffFiles:
    """Tests for DiskDiffComparator._extract_diff_files()."""

    def test_creates_directory_structure(
        self, comparator, mock_guestfish, tmp_path
    ):
        """_extract_diff_files() creates added/removed/modified dirs."""
        diff = {'added': [], 'removed': [], 'modified': []}
        extract_dir = tmp_path / 'extract'

        comparator._extract_diff_files(
            '/base.qcow2', '/overlay.qcow2',
            '/dev/sda4', diff, extract_dir
        )

        assert (extract_dir / 'added').is_dir()
        assert (extract_dir / 'removed').is_dir()
        assert (extract_dir / 'modified' / 'base').is_dir()
        assert (extract_dir / 'modified' / 'overlay').is_dir()

    def test_extracts_added_files_from_overlay(
        self, comparator, mock_guestfish, tmp_path
    ):
        """_extract_diff_files() downloads added files from overlay disk."""
        diff = {
            'added': [
                {'path': '/new_file.txt', 'size': 100,
                 'mtime': 1700000000, 'mtime_readable': '2023-11-14'}
            ],
            'removed': [],
            'modified': [],
        }
        extract_dir = tmp_path / 'extract'

        comparator._extract_diff_files(
            '/base.qcow2', '/overlay.qcow2',
            '/dev/sda4', diff, extract_dir
        )

        # run_script should be called once for overlay
        mock_guestfish.run_script.assert_called_once()
        call_args = mock_guestfish.run_script.call_args
        # First arg is disk path (overlay for added files)
        assert call_args[0][0] == '/overlay.qcow2'
        # Script lines include mount and download
        script = call_args[0][1]
        assert 'run' in script
        assert 'mount /dev/sda4 /' in script

    def test_extracts_removed_files_from_base(
        self, comparator, mock_guestfish, tmp_path
    ):
        """_extract_diff_files() downloads removed files from base disk."""
        diff = {
            'added': [],
            'removed': [
                {'path': '/old_file.txt', 'size': 50,
                 'mtime': 1700000000, 'mtime_readable': '2023-11-14'}
            ],
            'modified': [],
        }
        extract_dir = tmp_path / 'extract'

        comparator._extract_diff_files(
            '/base.qcow2', '/overlay.qcow2',
            '/dev/sda4', diff, extract_dir
        )

        mock_guestfish.run_script.assert_called_once()
        call_args = mock_guestfish.run_script.call_args
        # First arg is base disk for removed files
        assert call_args[0][0] == '/base.qcow2'

    def test_extracts_modified_files_from_both_disks(
        self, comparator, mock_guestfish, tmp_path
    ):
        """_extract_diff_files() downloads modified files from both disks."""
        diff = {
            'added': [],
            'removed': [],
            'modified': [
                {'path': '/config.txt', 'size_before': 100,
                 'size_after': 150, 'mtime_before': 1700000000,
                 'mtime_after': 1700000099,
                 'mtime_before_readable': '2023-11-14',
                 'mtime_after_readable': '2023-11-14'}
            ],
        }
        extract_dir = tmp_path / 'extract'

        comparator._extract_diff_files(
            '/base.qcow2', '/overlay.qcow2',
            '/dev/sda4', diff, extract_dir
        )

        # run_script called twice: once for base, once for overlay
        assert mock_guestfish.run_script.call_count == 2

    def test_skips_extraction_when_no_files(
        self, comparator, mock_guestfish, tmp_path
    ):
        """_extract_diff_files() does nothing when diff has no files."""
        diff = {'added': [], 'removed': [], 'modified': []}
        extract_dir = tmp_path / 'extract'

        comparator._extract_diff_files(
            '/base.qcow2', '/overlay.qcow2',
            '/dev/sda4', diff, extract_dir
        )

        mock_guestfish.run_script.assert_not_called()


class TestParseVirtDiffTime:
    """Tests for DiskDiffComparator._parse_virt_diff_time()."""

    def test_parses_datetime_string(self, comparator):
        """_parse_virt_diff_time() parses 'YYYY-MM-DD HH:MM:SS' format."""
        result = comparator._parse_virt_diff_time('2024-01-15 10:30:45')
        assert result > 0

    def test_parses_unix_timestamp(self, comparator):
        """_parse_virt_diff_time() parses raw unix timestamp string."""
        result = comparator._parse_virt_diff_time('1700000000')
        assert result == 1700000000.0

    def test_returns_zero_for_empty_string(self, comparator):
        """_parse_virt_diff_time() returns 0.0 for empty input."""
        assert comparator._parse_virt_diff_time('') == 0.0

    def test_returns_zero_for_unparseable_string(self, comparator):
        """_parse_virt_diff_time() returns 0.0 for garbage input."""
        assert comparator._parse_virt_diff_time('not-a-date') == 0.0


class TestAddScannedFile:
    """Tests for DiskDiffComparator._add_scanned_file()."""

    def test_adds_standard_file_record(self, comparator):
        """_add_scanned_file() adds file with standard path/size/mtime."""
        file_map = {}
        comparator._add_scanned_file(file_map, {
            'path': '/etc/hosts',
            'size': '1024',
            'mtime': '1700000000',
        })

        assert '/etc/hosts' in file_map
        assert file_map['/etc/hosts']['size'] == 1024
        assert file_map['/etc/hosts']['mtime'] == 1700000000

    def test_adds_tsk_style_record(self, comparator):
        """_add_scanned_file() handles TSK-style field names."""
        file_map = {}
        comparator._add_scanned_file(file_map, {
            'tsk_name': '/Windows/System32/config',
            'tsk_size': '2048',
            'tsk_mtime_sec': '1700000000',
        })

        assert '/Windows/System32/config' in file_map
        assert file_map['/Windows/System32/config']['size'] == 2048

    def test_skips_record_without_path(self, comparator):
        """_add_scanned_file() ignores records with no path."""
        file_map = {}
        comparator._add_scanned_file(file_map, {
            'size': '100',
            'mtime': '1700000000',
        })

        assert len(file_map) == 0

    def test_strips_quotes_from_path(self, comparator):
        """_add_scanned_file() removes quotes from paths."""
        file_map = {}
        comparator._add_scanned_file(file_map, {
            'path': '"/some/path"',
            'size': '100',
            'mtime': '1700000000',
        })

        assert '/some/path' in file_map
