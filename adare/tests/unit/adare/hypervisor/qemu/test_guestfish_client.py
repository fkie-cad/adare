"""Tests for GuestfishClient - guestfish CLI abstraction."""

import subprocess
from unittest.mock import patch, MagicMock, call

import pytest

from adare.hypervisor.qemu.guestfish_client import GuestfishClient
from adare.hypervisor.exceptions import HypervisorException


class TestRunCommand:
    """Tests for GuestfishClient.run_command()."""

    @patch('adare.hypervisor.qemu.guestfish_client.get_experiment_log_file', return_value=None)
    @patch('adare.hypervisor.qemu.guestfish_client.LibvirtStderrRedirect')
    @patch('adare.hypervisor.qemu.guestfish_client.subprocess.run')
    def test_run_command_basic_args(self, mock_run, mock_redirect, mock_log_file):
        """run_command() calls subprocess with correct guestfish CLI args."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout='output', stderr=''
        )
        client = GuestfishClient()

        # auto_mount=False to avoid detect_root_filesystem subprocess call
        client.run_command('/disk.qcow2', ['ls', '/'], auto_mount=False)

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[:5] == ['guestfish', '--rw', '--format=qcow2', '-a', '/disk.qcow2']
        assert cmd[5:8] == [':', 'ls', '/']

    @patch('adare.hypervisor.qemu.guestfish_client.get_experiment_log_file', return_value=None)
    @patch('adare.hypervisor.qemu.guestfish_client.LibvirtStderrRedirect')
    @patch('adare.hypervisor.qemu.guestfish_client.subprocess.run')
    def test_run_command_readonly_adds_ro_flag(self, mock_run, mock_redirect, mock_log_file):
        """run_command() with readonly=True adds --ro flag."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout='', stderr=''
        )
        client = GuestfishClient()

        client.run_command('/disk.qcow2', ['ls', '/'], readonly=True, auto_mount=False)

        cmd = mock_run.call_args[0][0]
        assert '--ro' in cmd
        assert '--rw' not in cmd

    @patch('adare.hypervisor.qemu.guestfish_client.get_experiment_log_file', return_value=None)
    @patch('adare.hypervisor.qemu.guestfish_client.LibvirtStderrRedirect')
    @patch('adare.hypervisor.qemu.guestfish_client.subprocess.run')
    def test_run_command_returns_tuple(self, mock_run, mock_redirect, mock_log_file):
        """run_command() returns (returncode, stdout, stderr) tuple."""
        mock_run.return_value = MagicMock(
            returncode=1, stdout='some output', stderr='some error'
        )
        client = GuestfishClient()

        result = client.run_command('/disk.qcow2', ['ls', '/'], auto_mount=False)

        assert result == (1, 'some output', 'some error')

    @patch('adare.hypervisor.qemu.guestfish_client.get_experiment_log_file', return_value=None)
    @patch('adare.hypervisor.qemu.guestfish_client.LibvirtStderrRedirect')
    @patch('adare.hypervisor.qemu.guestfish_client.subprocess.run')
    def test_run_command_auto_mount_adds_mount_commands(self, mock_run, mock_redirect, mock_log_file):
        """run_command() with auto_mount=True detects and mounts root fs."""
        # First call: detect_root_filesystem -> list-filesystems
        # Second call: the actual guestfish command with mount
        mock_run.side_effect = [
            # detect_root_filesystem call
            MagicMock(returncode=0, stdout='/dev/sda1: ext4\n', stderr=''),
            # actual run_command with auto_mount
            MagicMock(returncode=0, stdout='dir contents', stderr=''),
        ]
        client = GuestfishClient()

        rc, stdout, stderr = client.run_command(
            '/disk.qcow2', ['ls', '/'], auto_mount=True
        )

        assert rc == 0
        # The second call should have run/mount commands
        final_cmd = mock_run.call_args_list[1][0][0]
        assert 'run' in final_cmd
        assert 'mount' in final_cmd
        assert '/dev/sda1' in final_cmd


class TestDetectRootFilesystem:
    """Tests for GuestfishClient.detect_root_filesystem()."""

    @patch('adare.hypervisor.qemu.guestfish_client.subprocess.run')
    def test_detect_linux_ext4(self, mock_run):
        """detect_root_filesystem() parses guestfish output for Linux ext4."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='/dev/sda1: ext4\n',
            stderr='',
        )
        client = GuestfishClient()

        device, fs_type = client.detect_root_filesystem('/disk.qcow2')

        assert device == '/dev/sda1'
        assert fs_type == 'ext4'

    @patch('adare.hypervisor.qemu.guestfish_client.subprocess.run')
    def test_detect_largest_ntfs_partition_for_windows(self, mock_run):
        """detect_root_filesystem() identifies largest NTFS partition for Windows."""
        # First call: list-filesystems
        # Second call: size of sda1 (small recovery)
        # Third call: size of sda4 (main OS)
        mock_run.side_effect = [
            MagicMock(
                returncode=0,
                stdout='/dev/sda1: ntfs\n/dev/sda2: unknown\n/dev/sda3: unknown\n/dev/sda4: ntfs\n',
                stderr='',
            ),
            # size of /dev/sda1 (500 MB recovery)
            MagicMock(returncode=0, stdout='524288000\n', stderr=''),
            # size of /dev/sda4 (100 GB OS)
            MagicMock(returncode=0, stdout='107374182400\n', stderr=''),
        ]
        client = GuestfishClient()

        device, fs_type = client.detect_root_filesystem('/disk.qcow2')

        assert device == '/dev/sda4'
        assert fs_type == 'ntfs'

    @patch('adare.hypervisor.qemu.guestfish_client.subprocess.run')
    def test_detect_raises_when_no_os_filesystem(self, mock_run):
        """detect_root_filesystem() raises when no OS filesystem found."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='/dev/sda1: swap\n/dev/sda2: unknown\n',
            stderr='',
        )
        client = GuestfishClient()

        with pytest.raises(HypervisorException, match="No suitable OS filesystem"):
            client.detect_root_filesystem('/disk.qcow2')

    @patch('adare.hypervisor.qemu.guestfish_client.subprocess.run')
    def test_detect_raises_on_guestfish_failure(self, mock_run):
        """detect_root_filesystem() raises on guestfish command failure."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout='',
            stderr='guestfish error: disk not found',
        )
        client = GuestfishClient()

        with pytest.raises(HypervisorException, match="Failed to detect filesystems"):
            client.detect_root_filesystem('/disk.qcow2')


class TestParseFilesystemsOutput:
    """Tests for GuestfishClient._parse_filesystems_output()."""

    def test_multi_partition_output(self):
        """_parse_filesystems_output() parses multi-partition output correctly."""
        stdout = (
            '/dev/sda1: ntfs\n'
            '/dev/sda2: unknown\n'
            '/dev/sda3: ext4\n'
            '/dev/sda4: swap\n'
            '/dev/sda5: xfs\n'
        )
        client = GuestfishClient()

        result = client._parse_filesystems_output(stdout)

        assert result == [
            ('/dev/sda1', 'ntfs'),
            ('/dev/sda3', 'ext4'),
            ('/dev/sda5', 'xfs'),
        ]

    def test_filters_unsupported_filesystems(self):
        """_parse_filesystems_output() filters out swap, unknown, etc."""
        stdout = '/dev/sda1: swap\n/dev/sda2: unknown\n/dev/sda3: vfat\n'
        client = GuestfishClient()

        result = client._parse_filesystems_output(stdout)

        assert result == []

    def test_handles_ext3(self):
        """_parse_filesystems_output() includes ext3 as supported."""
        stdout = '/dev/sda1: ext3\n'
        client = GuestfishClient()

        result = client._parse_filesystems_output(stdout)

        assert result == [('/dev/sda1', 'ext3')]

    def test_handles_empty_output(self):
        """_parse_filesystems_output() returns empty list for empty output."""
        client = GuestfishClient()

        result = client._parse_filesystems_output('')

        assert result == []


class TestIsNtfsHibernated:
    """Tests for GuestfishClient.is_ntfs_hibernated()."""

    @patch('adare.hypervisor.qemu.guestfish_client.subprocess.run')
    def test_returns_true_when_hiberfil_found(self, mock_run):
        """is_ntfs_hibernated() returns (True, 'ntfs') when hiberfil.sys found."""
        mock_run.side_effect = [
            # list-filesystems call
            MagicMock(returncode=0, stdout='/dev/sda4: ntfs\n', stderr=''),
            # is-file /hiberfil.sys call -> "true"
            MagicMock(returncode=0, stdout='true\n', stderr=''),
        ]
        client = GuestfishClient()

        is_hibernated, fs_type = client.is_ntfs_hibernated('/disk.qcow2', '/dev/sda4')

        assert is_hibernated is True
        assert fs_type == 'ntfs'

    @patch('adare.hypervisor.qemu.guestfish_client.subprocess.run')
    def test_returns_false_for_clean_ntfs(self, mock_run):
        """is_ntfs_hibernated() returns (False, 'ntfs') for clean NTFS."""
        mock_run.side_effect = [
            # list-filesystems call
            MagicMock(returncode=0, stdout='/dev/sda4: ntfs\n', stderr=''),
            # is-file /hiberfil.sys call -> "false" with no hibernation warnings
            MagicMock(returncode=0, stdout='false\n', stderr=''),
        ]
        client = GuestfishClient()

        is_hibernated, fs_type = client.is_ntfs_hibernated('/disk.qcow2', '/dev/sda4')

        assert is_hibernated is False
        assert fs_type == 'ntfs'

    @patch('adare.hypervisor.qemu.guestfish_client.subprocess.run')
    def test_returns_true_when_stderr_has_hibernation_warning(self, mock_run):
        """is_ntfs_hibernated() detects hibernation from stderr warnings."""
        mock_run.side_effect = [
            MagicMock(returncode=0, stdout='/dev/sda4: ntfs\n', stderr=''),
            MagicMock(
                returncode=1,
                stdout='',
                stderr='ntfs: volume is hibernated, refuse to mount',
            ),
        ]
        client = GuestfishClient()

        is_hibernated, fs_type = client.is_ntfs_hibernated('/disk.qcow2', '/dev/sda4')

        assert is_hibernated is True

    @patch('adare.hypervisor.qemu.guestfish_client.subprocess.run')
    def test_returns_false_for_non_ntfs(self, mock_run):
        """is_ntfs_hibernated() returns (False, fs_type) for non-NTFS filesystems."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout='/dev/sda1: ext4\n', stderr=''
        )
        client = GuestfishClient()

        is_hibernated, fs_type = client.is_ntfs_hibernated('/disk.qcow2', '/dev/sda1')

        assert is_hibernated is False
        assert fs_type == 'ext4'
        # Only one subprocess call (list-filesystems), no is-file check
        assert mock_run.call_count == 1


class TestRemoveNtfsHibernation:
    """Tests for GuestfishClient.remove_ntfs_hibernation()."""

    @patch('adare.hypervisor.qemu.guestfish_client.subprocess.run')
    def test_calls_ntfsfix_command(self, mock_run):
        """remove_ntfs_hibernation() calls guestfish with ntfsfix command."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout='ntfsfix output', stderr=''
        )
        client = GuestfishClient()

        client.remove_ntfs_hibernation('/disk.qcow2', '/dev/sda4')

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert 'guestfish' == cmd[0]
        assert '--rw' in cmd
        assert 'ntfsfix -d /dev/sda4' in cmd

    @patch('adare.hypervisor.qemu.guestfish_client.subprocess.run')
    def test_raises_when_ntfsfix_unavailable(self, mock_run):
        """remove_ntfs_hibernation() raises when ntfsfix is not available."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout='',
            stderr='unknown command: ntfsfix',
        )
        client = GuestfishClient()

        with pytest.raises(HypervisorException, match="ntfsfix utility not available"):
            client.remove_ntfs_hibernation('/disk.qcow2', '/dev/sda4')

    @patch('adare.hypervisor.qemu.guestfish_client.subprocess.run')
    def test_raises_on_other_failure(self, mock_run):
        """remove_ntfs_hibernation() raises with troubleshooting on other failures."""
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout='',
            stderr='disk corruption detected',
        )
        client = GuestfishClient()

        with pytest.raises(HypervisorException, match="Failed to remove NTFS hibernation"):
            client.remove_ntfs_hibernation('/disk.qcow2', '/dev/sda4')


class TestRunScript:
    """Tests for GuestfishClient.run_script()."""

    @patch('adare.hypervisor.qemu.guestfish_client.subprocess.run')
    def test_creates_temp_file_runs_guestfish_cleans_up(self, mock_run):
        """run_script() creates temp file, runs guestfish, and cleans up."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout='', stderr=''
        )
        client = GuestfishClient()

        result = client.run_script('/disk.qcow2', ['run', 'mount /dev/sda1 /'])

        assert result is True
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == 'guestfish'
        assert '--ro' in cmd
        assert '-f' in cmd
        # Verify script file path was passed (temp file, should end with .guestfish)
        script_path_idx = cmd.index('-f') + 1
        assert cmd[script_path_idx].endswith('.guestfish')

    @patch('adare.hypervisor.qemu.guestfish_client.subprocess.run')
    def test_returns_false_on_failure(self, mock_run):
        """run_script() returns False when guestfish fails."""
        mock_run.return_value = MagicMock(
            returncode=1, stdout='', stderr='mount error'
        )
        client = GuestfishClient()

        result = client.run_script('/disk.qcow2', ['run', 'mount /dev/sda1 /'])

        assert result is False

    @patch('adare.hypervisor.qemu.guestfish_client.subprocess.run')
    def test_temp_file_cleaned_up_after_success(self, mock_run):
        """run_script() cleans up temp file after successful execution."""
        mock_run.return_value = MagicMock(
            returncode=0, stdout='', stderr=''
        )
        client = GuestfishClient()

        client.run_script('/disk.qcow2', ['run'])

        # After run_script returns, the temp file should be deleted
        cmd = mock_run.call_args[0][0]
        script_path_idx = cmd.index('-f') + 1
        script_path = cmd[script_path_idx]
        from pathlib import Path
        assert not Path(script_path).exists()

    @patch('adare.hypervisor.qemu.guestfish_client.subprocess.run')
    def test_temp_file_cleaned_up_after_failure(self, mock_run):
        """run_script() cleans up temp file even when guestfish fails."""
        mock_run.return_value = MagicMock(
            returncode=1, stdout='', stderr='error'
        )
        client = GuestfishClient()

        client.run_script('/disk.qcow2', ['run'])

        cmd = mock_run.call_args[0][0]
        script_path_idx = cmd.index('-f') + 1
        script_path = cmd[script_path_idx]
        from pathlib import Path
        assert not Path(script_path).exists()

    @patch('adare.hypervisor.qemu.guestfish_client.subprocess.run')
    def test_script_content_written_correctly(self, mock_run):
        """run_script() writes commands joined by newlines to the script file."""
        written_content = None

        def capture_run(cmd, **kwargs):
            nonlocal written_content
            script_idx = cmd.index('-f') + 1
            with open(cmd[script_idx], 'r') as f:
                written_content = f.read()
            return MagicMock(returncode=0, stdout='', stderr='')

        mock_run.side_effect = capture_run
        client = GuestfishClient()

        client.run_script('/disk.qcow2', ['run', 'mount /dev/sda1 /', 'ls /'])

        assert written_content == 'run\nmount /dev/sda1 /\nls /'
