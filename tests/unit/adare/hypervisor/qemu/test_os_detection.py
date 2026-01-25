"""
Unit tests for adare.hypervisor.qemu.os_detection module.
"""
import pytest
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch
from adare.hypervisor.qemu.os_detection import detect_os_from_filename, detect_os_from_disk


class TestOSDetectionFromFilename:
    """Tests for detect_os_from_filename."""

    @pytest.mark.parametrize("filename,expected", [
        ("Win11-Pro.qcow2", "windows"),
        ("windows-server-2019.vmdk", "windows"),
        ("win10.img", "windows"),
        ("ubuntu-22.04.qcow2", "linux"),
        ("debian-11.raw", "linux"),
        ("arch-linux.vdi", "linux"),
        ("unknown-vm.qcow2", None),
        ("backup-image.img", None),
    ])
    def test_detection_cases(self, filename, expected):
        """Test various filename patterns."""
        assert detect_os_from_filename(filename) == expected


class TestOSDetectionFromDisk:
    """Tests for detect_os_from_disk using guestfish mock."""

    @patch("subprocess.run")
    def test_detect_windows_success(self, mock_run):
        """Test successful detection of Windows OS."""
        # Setup mock responses for sequence of guestfish calls
        
        # 1. inspect-os
        mock_inspect_os = MagicMock()
        mock_inspect_os.returncode = 0
        mock_inspect_os.stdout = "/dev/sda2\n"
        
        # 2. inspect-get-type
        mock_get_type = MagicMock()
        mock_get_type.returncode = 0
        mock_get_type.stdout = "windows\n"
        
        # 3. inspect-get-distro
        mock_get_distro = MagicMock()
        mock_get_distro.returncode = 0
        mock_get_distro.stdout = "windows\n"
        
        # 4. inspect-get-major-version
        mock_get_version = MagicMock()
        mock_get_version.returncode = 0
        mock_get_version.stdout = "11\n"
        
        mock_run.side_effect = [
            mock_inspect_os,
            mock_get_type,
            mock_get_distro,
            mock_get_version
        ]
        
        platform, details = detect_os_from_disk(Path("/tmp/win11.qcow2"))
        
        assert platform == "windows"
        assert details["distribution"] == "windows"
        assert details["version"] == "11"
        assert details["architecture"] == "x86_64"

    @patch("subprocess.run")
    def test_detect_linux_success(self, mock_run):
        """Test successful detection of Linux OS."""
        # 1. inspect-os
        mock_inspect_os = MagicMock()
        mock_inspect_os.returncode = 0
        mock_inspect_os.stdout = "/dev/sda1\n"
        
        # 2. inspect-get-type
        mock_get_type = MagicMock()
        mock_get_type.returncode = 0
        mock_get_type.stdout = "linux\n"
        
        # 3. inspect-get-distro
        mock_get_distro = MagicMock()
        mock_get_distro.returncode = 0
        mock_get_distro.stdout = "ubuntu\n"
        
        # 4. inspect-get-major-version
        mock_get_version = MagicMock()
        mock_get_version.returncode = 0
        mock_get_version.stdout = "22.04\n"
        
        mock_run.side_effect = [
            mock_inspect_os,
            mock_get_type,
            mock_get_distro,
            mock_get_version
        ]
        
        platform, details = detect_os_from_disk(Path("/tmp/ubuntu.qcow2"))
        
        assert platform == "linux"
        assert details["distribution"] == "ubuntu"
        
    @patch("subprocess.run")
    def test_detect_failure_no_os(self, mock_run):
        """Test safely handling case where no OS is found."""
        # 1. inspect-os returns empty string (no root)
        mock_inspect_os = MagicMock()
        mock_inspect_os.returncode = 0
        mock_inspect_os.stdout = ""
        
        mock_run.side_effect = [mock_inspect_os]
        
        platform, details = detect_os_from_disk(Path("/tmp/empty.qcow2"))
        
        assert platform == "linux" # Default fallback
        assert details == {}

    @patch("subprocess.run")
    def test_detect_failure_guestfish_error(self, mock_run):
        """Test safely handling guestfish errors."""
        # 1. inspect-os fails
        mock_inspect_os = MagicMock()
        mock_inspect_os.returncode = 1
        mock_inspect_os.stderr = "guestfish: error"
        
        mock_run.side_effect = [mock_inspect_os]
        
        platform, details = detect_os_from_disk(Path("/tmp/error.qcow2"))
        
        assert platform == "linux"
        assert details == {}

    @patch("subprocess.run")
    def test_detect_timeout(self, mock_run):
        """Test handling timeout exception."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="guestfish", timeout=30)
        
        platform, details = detect_os_from_disk(Path("/tmp/timeout.qcow2"))
        
        assert platform == "linux"
        assert details == {}

    @patch("subprocess.run")
    def test_detect_filenotfound(self, mock_run):
        """Test handling missing guestfish executable."""
        mock_run.side_effect = FileNotFoundError()
        
        platform, details = detect_os_from_disk(Path("/tmp/missing.qcow2"))
        
        assert platform == "linux"
        assert details == {}
