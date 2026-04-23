"""
Tests for the file transfer strategy factory.

Verifies that detect_file_transfer_mode() and get_file_transfer_strategy()
select the correct strategy based on tool availability and platform.
"""
import pytest

pytestmark = pytest.mark.unit

from unittest.mock import MagicMock, patch

from adare.hypervisor.qemu.file_transfer import (
    LibguestfsStrategy,
    QGAStrategy,
    VirtioFSStrategy,
    detect_file_transfer_mode,
    get_file_transfer_strategy,
)


class TestDetectFileTransferMode:
    """Tests for detect_file_transfer_mode()."""

    def test_returns_virtiofs_when_virtiofsd_available(self):
        """virtiofsd on PATH -> virtiofs mode."""
        with (
            patch('adare.hypervisor.qemu.file_transfer.shutil.which') as mock_which,
            patch.dict('os.environ', {}, clear=False),
        ):
            mock_which.return_value = '/usr/bin/virtiofsd'
            # Remove QEMU_LIBGUESTFS if set
            with patch.dict('os.environ', {'QEMU_LIBGUESTFS': ''}, clear=False):
                result = detect_file_transfer_mode()
            assert result == 'virtiofs'

    def test_returns_libguestfs_when_env_var_set(self):
        """QEMU_LIBGUESTFS=true overrides everything."""
        with patch.dict('os.environ', {'QEMU_LIBGUESTFS': 'true'}, clear=False):
            result = detect_file_transfer_mode()
        assert result == 'libguestfs'

    def test_returns_libguestfs_when_env_var_yes(self):
        """QEMU_LIBGUESTFS=yes also forces libguestfs."""
        with patch.dict('os.environ', {'QEMU_LIBGUESTFS': 'yes'}, clear=False):
            result = detect_file_transfer_mode()
        assert result == 'libguestfs'

    def test_returns_libguestfs_when_env_var_1(self):
        """QEMU_LIBGUESTFS=1 also forces libguestfs."""
        with patch.dict('os.environ', {'QEMU_LIBGUESTFS': '1'}, clear=False):
            result = detect_file_transfer_mode()
        assert result == 'libguestfs'

    def test_returns_libguestfs_on_linux_without_virtiofsd(self):
        """Linux without virtiofsd -> libguestfs fallback."""
        with (
            patch('adare.hypervisor.qemu.file_transfer.shutil.which', return_value=None),
            patch('adare.hypervisor.qemu.file_transfer.platform.system', return_value='Linux'),
            patch.dict('os.environ', {'QEMU_LIBGUESTFS': ''}, clear=False),
        ):
            result = detect_file_transfer_mode()
        assert result == 'libguestfs'

    def test_returns_libguestfs_on_macos_with_guestfish(self):
        """macOS without virtiofsd but with guestfish -> libguestfs."""
        def which_side_effect(name):
            if name == 'virtiofsd':
                return None
            if name == 'guestfish':
                return '/usr/local/bin/guestfish'
            return None

        mock_subprocess_result = MagicMock()
        mock_subprocess_result.returncode = 0

        with (
            patch('adare.hypervisor.qemu.file_transfer.shutil.which', side_effect=which_side_effect),
            patch('adare.hypervisor.qemu.file_transfer.platform.system', return_value='Darwin'),
            patch('adare.hypervisor.qemu.file_transfer.subprocess.run', return_value=mock_subprocess_result),
            patch('adare.hypervisor.qemu.file_transfer.os.path.isdir', return_value=True),
            patch('adare.hypervisor.qemu.file_transfer.os.listdir', return_value=['appliance']),
            patch.dict('os.environ', {'QEMU_LIBGUESTFS': ''}, clear=False),
        ):
            result = detect_file_transfer_mode()
        assert result == 'libguestfs'

    def test_returns_qga_on_macos_without_tools(self):
        """macOS without virtiofsd and guestfish -> QGA fallback."""
        with (
            patch('adare.hypervisor.qemu.file_transfer.shutil.which', return_value=None),
            patch('adare.hypervisor.qemu.file_transfer.platform.system', return_value='Darwin'),
            patch.dict('os.environ', {'QEMU_LIBGUESTFS': ''}, clear=False),
        ):
            result = detect_file_transfer_mode()
        assert result == 'qga'


class TestGetFileTransferStrategy:
    """Tests for get_file_transfer_strategy()."""

    def test_returns_virtiofs_strategy(self):
        """VirtioFSStrategy selected when virtiofsd available."""
        with (
            patch('adare.hypervisor.qemu.file_transfer.shutil.which') as mock_which,
            patch.dict('os.environ', {'QEMU_LIBGUESTFS': ''}, clear=False),
        ):
            mock_which.return_value = '/usr/bin/virtiofsd'
            strategy = get_file_transfer_strategy()
        assert isinstance(strategy, VirtioFSStrategy)

    def test_returns_libguestfs_strategy(self):
        """LibguestfsStrategy selected when QEMU_LIBGUESTFS env var set."""
        with patch.dict('os.environ', {'QEMU_LIBGUESTFS': 'true'}, clear=False):
            strategy = get_file_transfer_strategy()
        assert isinstance(strategy, LibguestfsStrategy)

    def test_returns_qga_strategy(self):
        """QGAStrategy selected on macOS without tools."""
        with (
            patch('adare.hypervisor.qemu.file_transfer.shutil.which', return_value=None),
            patch('adare.hypervisor.qemu.file_transfer.platform.system', return_value='Darwin'),
            patch.dict('os.environ', {'QEMU_LIBGUESTFS': ''}, clear=False),
        ):
            strategy = get_file_transfer_strategy()
        assert isinstance(strategy, QGAStrategy)

    def test_libguestfs_uses_provided_client(self):
        """LibguestfsStrategy uses the provided GuestfishClient."""
        from unittest.mock import MagicMock

        mock_client = MagicMock()
        with patch.dict('os.environ', {'QEMU_LIBGUESTFS': 'true'}, clear=False):
            strategy = get_file_transfer_strategy(guestfish_client=mock_client)
        assert isinstance(strategy, LibguestfsStrategy)
        assert strategy.guestfish is mock_client

    def test_libguestfs_creates_default_client_when_none(self):
        """LibguestfsStrategy creates a GuestfishClient if none provided."""
        from adare.hypervisor.qemu.guestfish_client import GuestfishClient

        with patch.dict('os.environ', {'QEMU_LIBGUESTFS': 'true'}, clear=False):
            strategy = get_file_transfer_strategy(guestfish_client=None)
        assert isinstance(strategy, LibguestfsStrategy)
        assert isinstance(strategy.guestfish, GuestfishClient)
