"""Tests for disk_helpers module -- shared qcow2 disk creation logic."""

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

from adare.hypervisor.qemu.vm_creator.disk_helpers import (
    DiskCreationError,
    create_qcow2_disk,
)


class TestCreateQcow2Disk:

    @patch('adare.hypervisor.qemu.vm_creator.disk_helpers.print_step')
    @patch('adare.hypervisor.qemu.vm_creator.disk_helpers.subprocess.run')
    @patch('adare.hypervisor.qemu.vm_creator.disk_helpers.HYPERVISOR_CONFIGS', {
        'qemu': {'qemu_img_exe': '/usr/bin/qemu-img'},
    })
    def test_calls_qemu_img_with_correct_args(self, mock_run, mock_print, tmp_path):
        """create_qcow2_disk invokes qemu-img create with the right parameters."""
        mock_run.return_value = MagicMock(returncode=0)
        disk_path = tmp_path / 'test.qcow2'

        create_qcow2_disk(disk_path, '60G')

        mock_run.assert_called_once()
        args = mock_run.call_args
        cmd = args[0][0]
        assert cmd == ['/usr/bin/qemu-img', 'create', '-f', 'qcow2', str(disk_path), '60G']

    @patch('adare.hypervisor.qemu.vm_creator.disk_helpers.print_step')
    @patch('adare.hypervisor.qemu.vm_creator.disk_helpers.subprocess.run')
    @patch('adare.hypervisor.qemu.vm_creator.disk_helpers.HYPERVISOR_CONFIGS', {
        'qemu': {'qemu_img_exe': 'qemu-img'},
    })
    def test_raises_on_failure(self, mock_run, mock_print, tmp_path):
        """create_qcow2_disk raises DiskCreationError when qemu-img fails."""
        mock_run.return_value = MagicMock(returncode=1, stderr='disk full')
        disk_path = tmp_path / 'test.qcow2'

        with pytest.raises(DiskCreationError, match='qemu-img create failed'):
            create_qcow2_disk(disk_path, '60G')

    @patch('adare.hypervisor.qemu.vm_creator.disk_helpers.print_step')
    @patch('adare.hypervisor.qemu.vm_creator.disk_helpers.subprocess.run')
    @patch('adare.hypervisor.qemu.vm_creator.disk_helpers.HYPERVISOR_CONFIGS', {
        'qemu': {'qemu_img_exe': 'qemu-img'},
    })
    def test_prints_success_step(self, mock_run, mock_print, tmp_path):
        """create_qcow2_disk prints a success step after creating the disk."""
        mock_run.return_value = MagicMock(returncode=0)
        disk_path = tmp_path / 'test.qcow2'

        create_qcow2_disk(disk_path, '80G')

        mock_print.assert_called_once()
        msg = mock_print.call_args[0][0]
        assert '80G' in msg

    @patch('adare.hypervisor.qemu.vm_creator.disk_helpers.print_step')
    @patch('adare.hypervisor.qemu.vm_creator.disk_helpers.subprocess.run')
    @patch('adare.hypervisor.qemu.vm_creator.disk_helpers.HYPERVISOR_CONFIGS', {
        'qemu': {'qemu_img_exe': 'qemu-img'},
    })
    def test_uses_capture_output(self, mock_run, mock_print, tmp_path):
        """create_qcow2_disk uses capture_output=True and text=True."""
        mock_run.return_value = MagicMock(returncode=0)
        disk_path = tmp_path / 'test.qcow2'

        create_qcow2_disk(disk_path, '60G')

        kwargs = mock_run.call_args[1]
        assert kwargs['capture_output'] is True
        assert kwargs['text'] is True


class TestDiskCreationError:

    def test_is_hypervisor_exception(self):
        """DiskCreationError inherits from HypervisorException."""
        from adare.hypervisor.exceptions import HypervisorException
        err = DiskCreationError('oops')
        assert isinstance(err, HypervisorException)

    def test_message_contains_detail(self):
        """DiskCreationError message includes the detail string."""
        err = DiskCreationError('no space left')
        assert 'no space left' in str(err)
