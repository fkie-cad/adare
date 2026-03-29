"""
Tests for file transfer strategy classes.

Verifies the ABC cannot be instantiated, the requires_vm_stop_for_retrieval()
contract for each strategy, and basic setup/retrieve behaviour with mocks.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from adare.hypervisor.qemu.file_transfer.base import FileTransferStrategy
from adare.hypervisor.qemu.file_transfer.virtiofs_strategy import VirtioFSStrategy
from adare.hypervisor.qemu.file_transfer.libguestfs_strategy import LibguestfsStrategy
from adare.hypervisor.qemu.file_transfer.qga_strategy import QGAStrategy


class TestFileTransferStrategyABC:
    """Tests for the abstract base class."""

    def test_cannot_instantiate_abc(self):
        """FileTransferStrategy cannot be instantiated directly."""
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            FileTransferStrategy()

    def test_defines_required_methods(self):
        """ABC requires all four methods to be implemented."""
        abstract_methods = FileTransferStrategy.__abstractmethods__
        assert 'setup' in abstract_methods
        assert 'post_boot_transfer' in abstract_methods
        assert 'retrieve_artifacts' in abstract_methods
        assert 'requires_vm_stop_for_retrieval' in abstract_methods


class TestRequiresVMStopForRetrieval:
    """Tests for the requires_vm_stop_for_retrieval() contract."""

    def test_virtiofs_does_not_require_stop(self):
        """VirtioFS can retrieve artifacts while VM is running."""
        strategy = VirtioFSStrategy()
        assert strategy.requires_vm_stop_for_retrieval() is False

    def test_libguestfs_requires_stop(self):
        """Libguestfs requires VM to be stopped for disk access."""
        strategy = LibguestfsStrategy()
        assert strategy.requires_vm_stop_for_retrieval() is True

    def test_qga_does_not_require_stop(self):
        """QGA retrieves artifacts from running VM."""
        strategy = QGAStrategy()
        assert strategy.requires_vm_stop_for_retrieval() is False


class TestVirtioFSStrategy:
    """Tests for VirtioFSStrategy."""

    @pytest.mark.asyncio
    async def test_setup_configures_virtiofs_shares(self):
        """setup() should enable virtiofs and configure shares in VM config."""
        strategy = VirtioFSStrategy()

        # Create mock context
        context = MagicMock()
        context.guest_platform = 'ubuntu-22.04'
        context.config.installation_mode = 'wheel'

        # Mock experiment_run_directory
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / 'run'
            run_dir.mkdir()

            context.experiment_run_directory.path = run_dir
            context.experiment_run_directory.log_directory = run_dir / 'logs'

            # Mock experiment_directory
            context.experiment_directory = MagicMock()
            context.experiment_directory.playbookfile = Path(tmpdir) / 'playbook.yml'
            context.experiment_directory.playbookfile.write_text('test: true')
            context.experiment_directory.path = Path(tmpdir) / 'experiment'
            context.experiment_directory.shared = Path(tmpdir) / 'shared'
            # shared does not exist -> should be skipped

            # Mock project_directory
            context.project_directory.vm_runtime = Path(tmpdir) / 'vm_runtime'
            context.project_directory.vm_runtime.mkdir()
            context.project_directory.shared = Path(tmpdir) / 'project_shared'
            # shared does not exist -> should be skipped

            context.config.shared_directories = None

            # Mock VM config
            context.vm.config = MagicMock()
            context.vm._save_vm_config = MagicMock()

            await strategy.setup(context)

            # Verify virtiofs was enabled
            assert context.vm.config.virtiofs_enabled is True
            assert len(context.vm.config.virtiofs_shares) >= 2  # run + vm at minimum
            context.vm._save_vm_config.assert_called_once()

    @pytest.mark.asyncio
    async def test_retrieve_artifacts_checks_run_dir(self):
        """retrieve_artifacts() should check for artifacts in run dir."""
        strategy = VirtioFSStrategy()
        context = MagicMock()

        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            run_dir = Path(tmpdir) / 'run'
            artifacts_dir = run_dir / 'artifacts'
            logs_dir = run_dir / 'logs'
            artifacts_dir.mkdir(parents=True)
            logs_dir.mkdir(parents=True)

            context.experiment_run_directory.path = run_dir
            context.experiment_run_directory.log_directory = logs_dir

            # No artifacts produced
            await strategy.retrieve_artifacts(context)
            # Should not raise


class TestLibguestfsStrategy:
    """Tests for LibguestfsStrategy."""

    def test_init_with_custom_client(self):
        """Can provide a custom GuestfishClient."""
        mock_client = MagicMock()
        strategy = LibguestfsStrategy(guestfish_client=mock_client)
        assert strategy.guestfish is mock_client

    def test_init_creates_default_client(self):
        """Creates GuestfishClient if none provided."""
        from adare.hypervisor.qemu.guestfish_client import GuestfishClient

        strategy = LibguestfsStrategy()
        assert isinstance(strategy.guestfish, GuestfishClient)

    @pytest.mark.asyncio
    async def test_post_boot_transfer_is_noop(self):
        """post_boot_transfer() should do nothing for libguestfs."""
        strategy = LibguestfsStrategy()
        context = MagicMock()
        # Should not raise or do anything
        await strategy.post_boot_transfer(context)

    def test_generate_retrieval_script_empty_specs(self):
        """Empty retrieval specs should produce empty script."""
        strategy = LibguestfsStrategy()
        result = strategy._generate_retrieval_script('/dev/sda1', [])
        assert result == ""

    def test_generate_retrieval_script_with_file(self):
        """Script should contain download command for files."""
        from pathlib import Path

        strategy = LibguestfsStrategy()
        specs = [
            {
                'guest_path': '/adare/run/logs/adarevm.log',
                'host_path': Path('/tmp/adarevm.log'),
                'type': 'file',
                'optional': True,
                'name': 'adarevm.log',
            }
        ]
        result = strategy._generate_retrieval_script('/dev/sda1', specs)
        assert 'run' in result
        assert 'mount /dev/sda1 /' in result
        assert '-download /adare/run/logs/adarevm.log' in result

    def test_generate_retrieval_script_with_directory(self):
        """Script should contain copy-out command for directories."""
        from pathlib import Path

        strategy = LibguestfsStrategy()
        specs = [
            {
                'guest_path': '/adare/run/artifacts',
                'host_path': Path('/tmp/artifacts'),
                'type': 'directory',
                'optional': True,
                'name': 'artifacts',
            }
        ]
        result = strategy._generate_retrieval_script('/dev/sda1', specs)
        assert '-copy-out /adare/run/artifacts /tmp' in result


class TestQGAStrategy:
    """Tests for QGAStrategy."""

    @pytest.mark.asyncio
    async def test_setup_builds_manifest_and_disables_virtiofs(self):
        """setup() should disable virtiofs and build file manifest."""
        strategy = QGAStrategy()

        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            context = MagicMock()
            context.guest_platform = 'ubuntu-22.04'

            run_dir = Path(tmpdir) / 'run'
            run_dir.mkdir()
            context.experiment_run_directory.path = run_dir

            # Mock experiment_directory
            context.experiment_directory = MagicMock()
            context.experiment_directory.playbookfile = Path(tmpdir) / 'playbook.yml'
            context.experiment_directory.playbookfile.write_text('test: true')
            context.experiment_directory.shared = Path(tmpdir) / 'shared'

            # Mock project_directory
            context.project_directory.vm_runtime = Path(tmpdir) / 'vm_runtime'
            context.project_directory.vm_runtime.mkdir()
            wheels_dir = context.project_directory.vm_runtime / 'wheels'
            wheels_dir.mkdir()
            # Create dummy wheels
            (wheels_dir / 'adarelib-1.0.whl').write_text('dummy')
            (wheels_dir / 'adarevm-1.0.whl').write_text('dummy')
            context.project_directory.shared = Path(tmpdir) / 'project_shared'

            context.config.shared_directories = None

            # Mock VM config
            context.vm.config = MagicMock()
            context.vm._save_vm_config = MagicMock()

            await strategy.setup(context)

            # Verify virtiofs was disabled
            assert context.vm.config.virtiofs_enabled is False
            assert context.vm.config.virtiofs_shares == []
            context.vm._save_vm_config.assert_called_once()

            # Verify manifest was built and stored on context
            assert hasattr(context, '_qga_file_manifest')
            manifest = context._qga_file_manifest
            assert len(manifest) >= 1  # At least playbook.yml
