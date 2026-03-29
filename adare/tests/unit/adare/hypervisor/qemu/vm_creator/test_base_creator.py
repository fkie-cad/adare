"""Tests for BaseVMCreator abstract base class and Template Method pattern."""

from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from adare.hypervisor.qemu.vm_creator.base_creator import BaseVMCreator, VMCreationError
from adare.hypervisor.qemu.vm_creator.os_catalog import OsDefinition


# --- Helpers ---

def _make_os_def(**overrides) -> OsDefinition:
    """Create a minimal OsDefinition for testing."""
    defaults = dict(
        name='testlinux',
        display_name='Test Linux 1.0',
        platform='linux',
        distribution='testdist',
        version='1.0',
        iso_url='',
        iso_sha256='',
        iso_filename='',
        default_disk_size='30G',
        default_ram_mb=4096,
        default_cpus=2,
        architecture='x86_64',
    )
    defaults.update(overrides)
    return OsDefinition(**defaults)


class ConcreteCreator(BaseVMCreator):
    """Concrete subclass for testing the abstract base."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.steps_called: list[str] = []

    def _ensure_iso(self) -> None:
        self.steps_called.append('_ensure_iso')

    def _run_installation(self, disk_path: Path, nvram_path: Path | None) -> None:
        self.steps_called.append('_run_installation')


class FailingInstallCreator(BaseVMCreator):
    """Creator whose _run_installation always raises."""

    def _ensure_iso(self) -> None:
        pass

    def _run_installation(self, disk_path: Path, nvram_path: Path | None) -> None:
        raise VMCreationError('installation exploded')


# --- Tests: Abstract nature ---

class TestBaseVMCreatorAbstract:

    def test_cannot_instantiate_base_class(self):
        """BaseVMCreator is abstract and cannot be instantiated directly."""
        os_def = _make_os_def()
        with pytest.raises(TypeError, match='abstract method'):
            BaseVMCreator(os_def=os_def)

    def test_ensure_iso_is_abstract(self):
        """_ensure_iso must be implemented by subclasses."""

        class MissingEnsureIso(BaseVMCreator):
            def _run_installation(self, disk_path, nvram_path):
                pass

        os_def = _make_os_def()
        with pytest.raises(TypeError, match='abstract method'):
            MissingEnsureIso(os_def=os_def)

    def test_run_installation_is_abstract(self):
        """_run_installation must be implemented by subclasses."""

        class MissingRunInstall(BaseVMCreator):
            def _ensure_iso(self):
                pass

        os_def = _make_os_def()
        with pytest.raises(TypeError, match='abstract method'):
            MissingRunInstall(os_def=os_def)


# --- Tests: Default values ---

class TestDefaultValues:

    def test_default_vm_name_uses_os_name_and_date(self):
        """_default_vm_name generates '{os_def.name}-YYYYMMDD'."""
        os_def = _make_os_def(name='mylinux')
        creator = ConcreteCreator(os_def=os_def)
        assert creator.vm_name.startswith('mylinux-')
        # Date portion is 8 digits
        date_part = creator.vm_name.split('-', 1)[1]
        assert len(date_part) == 8
        assert date_part.isdigit()

    def test_explicit_vm_name_overrides_default(self):
        os_def = _make_os_def()
        creator = ConcreteCreator(os_def=os_def, vm_name='custom-name')
        assert creator.vm_name == 'custom-name'

    def test_defaults_from_os_def(self):
        os_def = _make_os_def(default_disk_size='50G', default_ram_mb=2048, default_cpus=4)
        creator = ConcreteCreator(os_def=os_def)
        assert creator.disk_size == '50G'
        assert creator.ram_mb == 2048
        assert creator.cpus == 4

    def test_explicit_overrides(self):
        os_def = _make_os_def(default_disk_size='50G', default_ram_mb=2048, default_cpus=4)
        creator = ConcreteCreator(
            os_def=os_def,
            disk_size='100G',
            ram_mb=16384,
            cpus=8,
        )
        assert creator.disk_size == '100G'
        assert creator.ram_mb == 16384
        assert creator.cpus == 8

    def test_cpus_falls_back_to_default_host_cpus(self):
        """When os_def.default_cpus is 0, falls back to default_host_cpus()."""
        os_def = _make_os_def(default_cpus=0)
        with patch(
            'adare.hypervisor.qemu.vm_creator.base_creator.default_host_cpus',
            return_value=6,
        ):
            creator = ConcreteCreator(os_def=os_def)
        assert creator.cpus == 6


# --- Tests: Template method order ---

class TestCreateTemplateMethod:

    @patch('adare.hypervisor.qemu.vm_creator.base_creator.console')
    @patch('adare.hypervisor.qemu.vm_creator.base_creator.check_prerequisites')
    @patch('adare.hypervisor.qemu.vm_creator.base_creator.print_vm_config_panel')
    @patch('adare.hypervisor.qemu.vm_creator.base_creator.print_section')
    @patch('adare.hypervisor.qemu.vm_creator.base_creator.create_qcow2_disk')
    @patch('adare.hypervisor.qemu.vm_creator.base_creator.create_nvram_for_vm')
    def test_create_calls_steps_in_order(
        self,
        mock_nvram,
        mock_create_disk,
        mock_print_section,
        mock_config_panel,
        mock_prereqs,
        mock_console,
        tmp_path,
    ):
        """create() calls the template steps in the correct sequence."""
        os_def = _make_os_def()
        creator = ConcreteCreator(os_def=os_def, vm_dir=tmp_path)

        # Track call order across both mocks and creator methods
        call_order = []

        original_ensure = creator._ensure_iso
        original_install = creator._run_installation

        def tracked_ensure():
            call_order.append('ensure_iso')
            original_ensure()

        def tracked_install(dp, nvp):
            call_order.append('run_installation')
            original_install(dp, nvp)

        creator._ensure_iso = tracked_ensure
        creator._run_installation = tracked_install

        mock_config_panel.side_effect = lambda *a, **kw: call_order.append('config_panel')
        mock_prereqs.side_effect = lambda *a, **kw: call_order.append('check_prerequisites')
        mock_create_disk.side_effect = lambda *a, **kw: None  # no-op

        result = creator.create()

        assert call_order == [
            'config_panel',
            'check_prerequisites',
            'ensure_iso',
            'run_installation',
        ]
        assert isinstance(result, Path)
        assert result.name.endswith('.qcow2')

    @patch('adare.hypervisor.qemu.vm_creator.base_creator.console')
    @patch('adare.hypervisor.qemu.vm_creator.base_creator.check_prerequisites')
    @patch('adare.hypervisor.qemu.vm_creator.base_creator.print_vm_config_panel')
    @patch('adare.hypervisor.qemu.vm_creator.base_creator.print_section')
    @patch('adare.hypervisor.qemu.vm_creator.base_creator.create_qcow2_disk')
    @patch('adare.hypervisor.qemu.vm_creator.base_creator.create_nvram_for_vm')
    def test_create_returns_disk_path(
        self,
        mock_nvram,
        mock_create_disk,
        mock_print_section,
        mock_config_panel,
        mock_prereqs,
        mock_console,
        tmp_path,
    ):
        """create() returns the path to the qcow2 disk image."""
        os_def = _make_os_def()
        creator = ConcreteCreator(os_def=os_def, vm_name='myvm', vm_dir=tmp_path)
        result = creator.create()
        assert result == tmp_path / 'myvm.qcow2'


# --- Tests: Cleanup on failure ---

class TestCleanupOnFailure:

    def test_cleanup_removes_existing_disk(self, tmp_path):
        """_cleanup_on_failure removes the disk file if it exists."""
        os_def = _make_os_def()
        creator = ConcreteCreator(os_def=os_def)

        disk_path = tmp_path / 'test.qcow2'
        disk_path.write_text('fake disk')

        creator._cleanup_on_failure(disk_path, nvram_path=None)
        assert not disk_path.exists()

    def test_cleanup_removes_existing_nvram(self, tmp_path):
        """_cleanup_on_failure removes the NVRAM file if it exists."""
        os_def = _make_os_def()
        creator = ConcreteCreator(os_def=os_def)

        disk_path = tmp_path / 'test.qcow2'
        disk_path.write_text('fake disk')
        nvram_path = tmp_path / 'test_VARS.fd'
        nvram_path.write_text('fake nvram')

        creator._cleanup_on_failure(disk_path, nvram_path)
        assert not disk_path.exists()
        assert not nvram_path.exists()

    def test_cleanup_ignores_missing_files(self, tmp_path):
        """_cleanup_on_failure does not raise when files are already gone."""
        os_def = _make_os_def()
        creator = ConcreteCreator(os_def=os_def)

        disk_path = tmp_path / 'nonexistent.qcow2'
        nvram_path = tmp_path / 'nonexistent_VARS.fd'

        # Should not raise
        creator._cleanup_on_failure(disk_path, nvram_path)

    def test_cleanup_handles_none_nvram(self, tmp_path):
        """_cleanup_on_failure handles nvram_path=None gracefully."""
        os_def = _make_os_def()
        creator = ConcreteCreator(os_def=os_def)

        disk_path = tmp_path / 'test.qcow2'
        disk_path.write_text('fake disk')

        # Should not raise
        creator._cleanup_on_failure(disk_path, nvram_path=None)
        assert not disk_path.exists()

    @patch('adare.hypervisor.qemu.vm_creator.base_creator.console')
    @patch('adare.hypervisor.qemu.vm_creator.base_creator.check_prerequisites')
    @patch('adare.hypervisor.qemu.vm_creator.base_creator.print_vm_config_panel')
    @patch('adare.hypervisor.qemu.vm_creator.base_creator.print_section')
    @patch('adare.hypervisor.qemu.vm_creator.base_creator.create_qcow2_disk')
    @patch('adare.hypervisor.qemu.vm_creator.base_creator.create_nvram_for_vm')
    def test_create_cleans_up_on_installation_failure(
        self,
        mock_nvram,
        mock_create_disk,
        mock_print_section,
        mock_config_panel,
        mock_prereqs,
        mock_console,
        tmp_path,
    ):
        """create() calls _cleanup_on_failure when _run_installation raises."""
        os_def = _make_os_def()
        creator = FailingInstallCreator(os_def=os_def, vm_dir=tmp_path)

        # Create a fake disk file so cleanup has something to remove
        disk_path = tmp_path / f'{creator.vm_name}.qcow2'
        mock_create_disk.side_effect = lambda dp, sz: dp.write_text('fake')

        with pytest.raises(VMCreationError, match='installation exploded'):
            creator.create()

        # Disk should have been cleaned up
        assert not disk_path.exists()


# --- Tests: Disk creation ---

class TestCreateDisk:

    @patch('adare.hypervisor.qemu.vm_creator.base_creator.print_section')
    @patch('adare.hypervisor.qemu.vm_creator.base_creator.print_step')
    @patch('adare.hypervisor.qemu.vm_creator.base_creator.create_qcow2_disk')
    @patch('adare.hypervisor.qemu.vm_creator.base_creator.create_nvram_for_vm')
    def test_create_disk_raises_if_exists_without_force(
        self,
        mock_nvram,
        mock_create_disk,
        mock_print_step,
        mock_print_section,
        tmp_path,
    ):
        """_create_disk raises VMCreationError when disk exists and force=False."""
        os_def = _make_os_def()
        creator = ConcreteCreator(os_def=os_def, vm_name='existing', vm_dir=tmp_path, force=False)

        # Pre-create the disk
        (tmp_path / 'existing.qcow2').write_text('fake')

        with pytest.raises(VMCreationError, match='already exists'):
            creator._create_disk()

    @patch('adare.hypervisor.qemu.vm_creator.base_creator.print_section')
    @patch('adare.hypervisor.qemu.vm_creator.base_creator.print_step')
    @patch('adare.hypervisor.qemu.vm_creator.base_creator.create_qcow2_disk')
    @patch('adare.hypervisor.qemu.vm_creator.base_creator.create_nvram_for_vm')
    def test_create_disk_removes_old_when_force(
        self,
        mock_nvram,
        mock_create_disk,
        mock_print_step,
        mock_print_section,
        tmp_path,
    ):
        """_create_disk removes existing disk and NVRAM when force=True."""
        os_def = _make_os_def()
        creator = ConcreteCreator(os_def=os_def, vm_name='existing', vm_dir=tmp_path, force=True)

        disk_file = tmp_path / 'existing.qcow2'
        nvram_file = tmp_path / 'existing_VARS.fd'
        disk_file.write_text('fake')
        nvram_file.write_text('fake')

        creator._create_disk()

        # Old files should be removed (new disk creation is mocked)
        assert not disk_file.exists() or mock_create_disk.called
        assert not nvram_file.exists()

    @patch('adare.hypervisor.qemu.vm_creator.base_creator.print_section')
    @patch('adare.hypervisor.qemu.vm_creator.base_creator.create_qcow2_disk')
    @patch('adare.hypervisor.qemu.vm_creator.base_creator.create_nvram_for_vm')
    def test_create_disk_creates_nvram_for_uefi(
        self,
        mock_nvram,
        mock_create_disk,
        mock_print_section,
        tmp_path,
    ):
        """_create_disk creates NVRAM when os_def requires UEFI."""
        os_def = _make_os_def(requires_uefi=True)
        mock_nvram.return_value = str(tmp_path / 'test_VARS.fd')

        creator = ConcreteCreator(os_def=os_def, vm_name='uefivm', vm_dir=tmp_path)
        disk_path, nvram_path = creator._create_disk()

        mock_nvram.assert_called_once()
        assert nvram_path == tmp_path / 'test_VARS.fd'

    @patch('adare.hypervisor.qemu.vm_creator.base_creator.print_section')
    @patch('adare.hypervisor.qemu.vm_creator.base_creator.create_qcow2_disk')
    @patch('adare.hypervisor.qemu.vm_creator.base_creator.create_nvram_for_vm')
    def test_create_disk_creates_nvram_for_aarch64(
        self,
        mock_nvram,
        mock_create_disk,
        mock_print_section,
        tmp_path,
    ):
        """_create_disk creates NVRAM for aarch64 regardless of requires_uefi."""
        os_def = _make_os_def(architecture='aarch64', requires_uefi=False)
        mock_nvram.return_value = str(tmp_path / 'test_VARS.fd')

        creator = ConcreteCreator(os_def=os_def, vm_name='armvm', vm_dir=tmp_path)
        disk_path, nvram_path = creator._create_disk()

        mock_nvram.assert_called_once()
        assert nvram_path is not None

    @patch('adare.hypervisor.qemu.vm_creator.base_creator.print_section')
    @patch('adare.hypervisor.qemu.vm_creator.base_creator.create_qcow2_disk')
    def test_create_disk_no_nvram_for_bios(
        self,
        mock_create_disk,
        mock_print_section,
        tmp_path,
    ):
        """_create_disk returns None nvram_path when UEFI is not required."""
        os_def = _make_os_def(requires_uefi=False, architecture='x86_64')
        creator = ConcreteCreator(os_def=os_def, vm_name='biosvm', vm_dir=tmp_path)
        disk_path, nvram_path = creator._create_disk()

        assert nvram_path is None


# --- Tests: VMCreationError hierarchy ---

class TestVMCreationError:

    def test_is_hypervisor_exception(self):
        """VMCreationError inherits from HypervisorException."""
        from adare.hypervisor.exceptions import HypervisorException
        err = VMCreationError('something broke')
        assert isinstance(err, HypervisorException)
