"""
Unit tests for adare.hypervisor.qemu.lifecycle module.
"""
import pytest
import unittest
from unittest.mock import MagicMock, patch, call
from pathlib import Path
import tempfile
import os

from adare.hypervisor.qemu.lifecycle import QEMULifecycleStrategy
from adare.hypervisor.exceptions import HypervisorException

class TestQEMULifecycleStrategy:
    
    @pytest.fixture
    def strategy(self):
        with patch('adare.hypervisor.qemu.lifecycle.QEMUManager'):
             strategy = QEMULifecycleStrategy()
             return strategy

    def test_parse_filesystems_output(self, strategy):
        """Test parsing of guestfish list-filesystems output."""
        output = "/dev/sda1: ext4\n/dev/sda2: unknown\n/dev/sda3: ntfs\n"
        result = strategy._parse_filesystems_output(output)
        
        assert len(result) == 2
        assert ("/dev/sda1", "ext4") in result
        assert ("/dev/sda3", "ntfs") in result
        
    def test_parse_filesystems_output_empty(self, strategy):
        output = ""
        result = strategy._parse_filesystems_output(output)
        assert result == []

    def test_check_ntfs_hibernation_output_true(self, strategy):
        # Case 1: Stderr contains keywords
        assert strategy._check_ntfs_hibernation_output("some output", "Windows is hibernated, refused to mount") is True
        assert strategy._check_ntfs_hibernation_output("", "Mount is unsafe") is True
        
        # Case 2: Stdout contains true (from is-file check)
        assert strategy._check_ntfs_hibernation_output("true\n", "") is True
        
    def test_check_ntfs_hibernation_output_false(self, strategy):
        assert strategy._check_ntfs_hibernation_output("false\n", "") is False
        assert strategy._check_ntfs_hibernation_output("", "some other error") is False

    def test_generate_guestfish_retrieval_script(self, strategy):
        root_device = "/dev/sda1"
        specs = [
            {'guest_path': '/var/log/syslog', 'host_path': Path('/tmp/syslog'), 'type': 'file'},
            {'guest_path': '/home/user/data', 'host_path': Path('/tmp/data'), 'type': 'directory'}
        ]
        
        script = strategy._generate_guestfish_retrieval_script(root_device, specs)
        
        assert "mount /dev/sda1 /" in script
        assert "-download /var/log/syslog /tmp/syslog" in script
        # Check parent directory usage for copy-out
        parent = str(Path('/tmp/data').parent)
        assert f"-copy-out /home/user/data {parent}" in script

    def test_generate_guestfish_retrieval_script_empty(self, strategy):
        script = strategy._generate_guestfish_retrieval_script("/dev/sda1", [])
        assert script == ""

    @patch('subprocess.run')
    def test_detect_root_filesystem_success(self, mock_run, strategy):
        # Setup mock behavior
        # 1. list-filesystems call
        list_fs_mock = MagicMock()
        list_fs_mock.returncode = 0
        list_fs_mock.stdout = "/dev/sda1: ext4\n"
        
        # 2. blockdev-getsize64 call
        size_mock = MagicMock()
        size_mock.returncode = 0
        size_mock.stdout = "10737418240\n" # 10GB
        
        mock_run.side_effect = [list_fs_mock, size_mock]
        
        dev, fs = strategy._detect_root_filesystem("/tmp/disk.qcow2")
        
        assert dev == "/dev/sda1"
        assert fs == "ext4"
        
    @patch('subprocess.run')
    def test_copy_files_to_disk_via_libguestfs(self, mock_run, strategy):
        disk_path = "/tmp/disk.qcow2"
        files = [{'source': '/tmp/src', 'dest': 'dest/file'}]
        
        # Mock disk exists
        with patch('pathlib.Path.exists', return_value=True), \
             patch.object(strategy, '_detect_root_filesystem', return_value=('/dev/sda1', 'ext4')):
             
             # Mock subprocess for guestfish
             mock_run.return_value.returncode = 0
             
             strategy._copy_files_to_disk_via_libguestfs(disk_path, files)
             
             assert mock_run.called
             args = mock_run.call_args[0][0]
             assert 'guestfish' in args
             assert 'copy-in' in args
