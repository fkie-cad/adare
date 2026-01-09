"""
Unit tests for ExecutableManager class.

Tests the centralized executable path resolution for hypervisors including:
- Constructor initialization
- Path resolution for QEMU executables (qemu-img, qemu-system)
- Path resolution for VirtualBox executables (VBoxManage)
- Resolution precedence (env var > config > default)
- Platform-specific defaults
- Architecture-aware resolution
- Executable validation
- Error handling for missing executables
"""
import pytest
from unittest.mock import patch, MagicMock

from adare.hypervisor.executable_manager import ExecutableManager
from adare.hypervisor.exceptions import HypervisorException


class TestExecutableManagerConstructor:
    """Tests for ExecutableManager constructor."""

    def test_constructor_stores_hypervisor_type(self):
        """Test that constructor stores hypervisor_type correctly."""
        with patch.object(ExecutableManager, '_resolve_all'):
            manager = ExecutableManager('qemu', {'qemu_img_exe': 'qemu-img'})
            assert manager.hypervisor_type == 'qemu'

    def test_constructor_stores_config(self):
        """Test that constructor stores config correctly."""
        config = {'qemu_img_exe': 'qemu-img', 'architecture': 'x86_64'}
        with patch.object(ExecutableManager, '_resolve_all'):
            manager = ExecutableManager('qemu', config)
            assert manager.config == config

    def test_constructor_initializes_cache(self):
        """Test that constructor initializes empty cache."""
        with patch.object(ExecutableManager, '_resolve_all'):
            manager = ExecutableManager('qemu', {})
            assert manager._cache == {}

    def test_constructor_sets_host_os(self):
        """Test that constructor sets host_os from platform."""
        with patch.object(ExecutableManager, '_resolve_all'):
            with patch('platform.system', return_value='Linux'):
                manager = ExecutableManager('qemu', {})
                assert manager.host_os == 'linux'

    def test_constructor_calls_resolve_all(self):
        """Test that constructor calls _resolve_all for validation."""
        with patch.object(ExecutableManager, '_resolve_all') as mock_resolve:
            ExecutableManager('qemu', {})
            mock_resolve.assert_called_once()


class TestResolveAll:
    """Tests for _resolve_all method."""

    def test_resolve_all_qemu_resolves_qemu_executables(self):
        """Test that _resolve_all resolves qemu-img and qemu-system for QEMU."""
        with patch('shutil.which', return_value='/usr/bin/qemu-img'):
            manager = ExecutableManager('qemu', {})
            assert 'qemu_img' in manager._cache
            assert 'qemu_system' in manager._cache

    def test_resolve_all_virtualbox_resolves_vboxmanage(self):
        """Test that _resolve_all resolves VBoxManage for VirtualBox."""
        with patch('shutil.which', return_value='/usr/bin/VBoxManage'):
            manager = ExecutableManager('virtualbox', {})
            assert 'vboxmanage' in manager._cache

    def test_resolve_all_unknown_hypervisor_does_nothing(self):
        """Test that _resolve_all does nothing for unknown hypervisor types."""
        with patch.object(ExecutableManager, '_resolve_all'):
            manager = ExecutableManager('unknown', {})
        # Manually call _resolve_all to test behavior
        manager._resolve_all()
        assert manager._cache == {}


class TestResolveQemuImg:
    """Tests for _resolve_qemu_img method."""

    def test_env_var_takes_precedence(self):
        """Test that QEMU_IMG_BIN environment variable has highest priority."""
        with patch.dict('os.environ', {'QEMU_IMG_BIN': '/custom/qemu-img'}):
            with patch('shutil.which', return_value='/custom/qemu-img'):
                manager = ExecutableManager('qemu', {'qemu_img_exe': '/config/qemu-img'})
                assert manager._cache['qemu_img'] == '/custom/qemu-img'

    def test_config_used_when_no_env_var(self):
        """Test that config value is used when no environment variable is set."""
        with patch.dict('os.environ', {}, clear=True):
            with patch('shutil.which', return_value='/config/qemu-img'):
                manager = ExecutableManager('qemu', {'qemu_img_exe': '/config/qemu-img'})
                assert manager._cache['qemu_img'] == '/config/qemu-img'

    def test_default_used_when_no_env_or_config(self):
        """Test that default 'qemu-img' is used when no env var or config."""
        with patch.dict('os.environ', {}, clear=True):
            with patch('shutil.which', return_value='qemu-img'):
                manager = ExecutableManager('qemu', {})
                assert manager._cache['qemu_img'] == 'qemu-img'

    def test_env_var_not_set_uses_config(self):
        """Test that empty environment doesn't override config."""
        env_without_qemu_bin = {k: v for k, v in {}.items() if k != 'QEMU_IMG_BIN'}
        with patch.dict('os.environ', env_without_qemu_bin, clear=True):
            with patch('shutil.which', return_value='/path/to/custom-qemu-img'):
                manager = ExecutableManager('qemu', {'qemu_img_exe': '/path/to/custom-qemu-img'})
                assert manager._cache['qemu_img'] == '/path/to/custom-qemu-img'


class TestResolveQemuSystem:
    """Tests for _resolve_qemu_system method."""

    def test_env_var_takes_precedence(self):
        """Test that QEMU_SYSTEM_BIN environment variable has highest priority."""
        with patch.dict('os.environ', {'QEMU_SYSTEM_BIN': '/custom/qemu-system-x86_64'}):
            with patch('shutil.which', return_value='/custom/qemu-system-x86_64'):
                manager = ExecutableManager('qemu', {'qemu_system_exe': '/config/qemu-system'})
                assert manager._cache['qemu_system'] == '/custom/qemu-system-x86_64'

    def test_config_used_when_no_env_var(self):
        """Test that config value is used when no environment variable is set."""
        with patch.dict('os.environ', {}, clear=True):
            with patch('shutil.which', return_value='/config/qemu-system'):
                manager = ExecutableManager('qemu', {'qemu_system_exe': '/config/qemu-system'})
                assert manager._cache['qemu_system'] == '/config/qemu-system'

    def test_default_x86_64_architecture(self):
        """Test default qemu-system-x86_64 when no architecture specified."""
        with patch.dict('os.environ', {}, clear=True):
            with patch('shutil.which', return_value='qemu-system-x86_64'):
                manager = ExecutableManager('qemu', {})
                assert manager._cache['qemu_system'] == 'qemu-system-x86_64'

    def test_architecture_from_config_x86_64(self):
        """Test qemu-system-x86_64 when architecture is x86_64."""
        with patch.dict('os.environ', {}, clear=True):
            with patch('shutil.which', return_value='qemu-system-x86_64'):
                manager = ExecutableManager('qemu', {'architecture': 'x86_64'})
                assert manager._cache['qemu_system'] == 'qemu-system-x86_64'

    def test_architecture_from_config_arm64(self):
        """Test qemu-system-aarch64 when architecture is aarch64."""
        with patch.dict('os.environ', {}, clear=True):
            with patch('shutil.which', return_value='qemu-system-aarch64'):
                manager = ExecutableManager('qemu', {'architecture': 'aarch64'})
                assert manager._cache['qemu_system'] == 'qemu-system-aarch64'

    def test_architecture_arm(self):
        """Test qemu-system-arm when architecture is arm."""
        with patch.dict('os.environ', {}, clear=True):
            with patch('shutil.which', return_value='qemu-system-arm'):
                manager = ExecutableManager('qemu', {'architecture': 'arm'})
                assert manager._cache['qemu_system'] == 'qemu-system-arm'

    def test_config_exe_overrides_architecture_default(self):
        """Test that explicit qemu_system_exe in config overrides architecture default."""
        with patch.dict('os.environ', {}, clear=True):
            with patch('shutil.which', return_value='/custom/my-qemu'):
                manager = ExecutableManager('qemu', {
                    'architecture': 'x86_64',
                    'qemu_system_exe': '/custom/my-qemu'
                })
                assert manager._cache['qemu_system'] == '/custom/my-qemu'


class TestResolveVboxmanage:
    """Tests for _resolve_vboxmanage method."""

    def test_env_var_takes_precedence(self):
        """Test that VBOXMANAGE_BIN environment variable has highest priority."""
        with patch.dict('os.environ', {'VBOXMANAGE_BIN': '/custom/VBoxManage'}):
            with patch('shutil.which', return_value='/custom/VBoxManage'):
                with patch('platform.system', return_value='Linux'):
                    manager = ExecutableManager('virtualbox', {'vboxmanage_exe': '/config/VBoxManage'})
                    assert manager._cache['vboxmanage'] == '/custom/VBoxManage'

    def test_config_used_when_no_env_var(self):
        """Test that config value is used when no environment variable is set."""
        with patch.dict('os.environ', {}, clear=True):
            with patch('shutil.which', return_value='/config/VBoxManage'):
                with patch('platform.system', return_value='Linux'):
                    manager = ExecutableManager('virtualbox', {'vboxmanage_exe': '/config/VBoxManage'})
                    assert manager._cache['vboxmanage'] == '/config/VBoxManage'

    def test_unix_default(self):
        """Test default 'VBoxManage' on Unix platforms."""
        with patch.dict('os.environ', {}, clear=True):
            with patch('shutil.which', return_value='VBoxManage'):
                with patch('platform.system', return_value='Linux'):
                    manager = ExecutableManager('virtualbox', {})
                    assert manager._cache['vboxmanage'] == 'VBoxManage'

    def test_windows_default(self):
        """Test default 'VBoxManage.exe' on Windows."""
        with patch.dict('os.environ', {}, clear=True):
            with patch('shutil.which', return_value='VBoxManage.exe'):
                with patch('platform.system', return_value='Windows'):
                    manager = ExecutableManager('virtualbox', {})
                    assert manager._cache['vboxmanage'] == 'VBoxManage.exe'

    def test_macos_uses_unix_default(self):
        """Test that macOS uses Unix default 'VBoxManage'."""
        with patch.dict('os.environ', {}, clear=True):
            with patch('shutil.which', return_value='VBoxManage'):
                with patch('platform.system', return_value='Darwin'):
                    manager = ExecutableManager('virtualbox', {})
                    assert manager._cache['vboxmanage'] == 'VBoxManage'


class TestValidateExecutable:
    """Tests for _validate_executable method."""

    def test_valid_executable_returns_path(self):
        """Test that valid executable path is returned."""
        with patch('shutil.which', return_value='/usr/bin/qemu-img'):
            manager = ExecutableManager('qemu', {})
            # The validation happens during init, so cache should have the path
            assert manager._cache['qemu_img'] == 'qemu-img'

    def test_missing_executable_raises_hypervisor_exception(self):
        """Test that missing executable raises HypervisorException."""
        with patch('shutil.which', return_value=None):
            with pytest.raises(HypervisorException) as exc_info:
                ExecutableManager('qemu', {})
            assert 'not found in PATH' in str(exc_info.value)

    def test_exception_message_contains_executable_name(self):
        """Test that exception message contains the executable name."""
        with patch('shutil.which', return_value=None):
            with pytest.raises(HypervisorException) as exc_info:
                ExecutableManager('qemu', {})
            assert 'qemu-img' in str(exc_info.value)

    def test_exception_message_contains_path(self):
        """Test that exception message contains the attempted path."""
        with patch('shutil.which', return_value=None):
            with pytest.raises(HypervisorException) as exc_info:
                ExecutableManager('qemu', {'qemu_img_exe': '/nonexistent/path/qemu-img'})
            assert '/nonexistent/path/qemu-img' in str(exc_info.value)


class TestPropertyQemuImg:
    """Tests for qemu_img property."""

    def test_returns_cached_path(self):
        """Test that qemu_img property returns cached path."""
        with patch('shutil.which', return_value='/usr/bin/qemu-img'):
            manager = ExecutableManager('qemu', {})
            assert manager.qemu_img == 'qemu-img'

    def test_raises_for_virtualbox_hypervisor(self):
        """Test that accessing qemu_img for VirtualBox raises exception."""
        with patch('shutil.which', return_value='/usr/bin/VBoxManage'):
            manager = ExecutableManager('virtualbox', {})
            with pytest.raises(HypervisorException) as exc_info:
                _ = manager.qemu_img
            assert 'only available for QEMU' in str(exc_info.value)


class TestPropertyQemuSystem:
    """Tests for qemu_system property."""

    def test_returns_cached_path(self):
        """Test that qemu_system property returns cached path."""
        with patch('shutil.which', return_value='/usr/bin/qemu-system-x86_64'):
            manager = ExecutableManager('qemu', {})
            assert manager.qemu_system == 'qemu-system-x86_64'

    def test_raises_for_virtualbox_hypervisor(self):
        """Test that accessing qemu_system for VirtualBox raises exception."""
        with patch('shutil.which', return_value='/usr/bin/VBoxManage'):
            manager = ExecutableManager('virtualbox', {})
            with pytest.raises(HypervisorException) as exc_info:
                _ = manager.qemu_system
            assert 'only available for QEMU' in str(exc_info.value)


class TestPropertyVboxmanage:
    """Tests for vboxmanage property."""

    def test_returns_cached_path(self):
        """Test that vboxmanage property returns cached path."""
        with patch('shutil.which', return_value='/usr/bin/VBoxManage'):
            with patch('platform.system', return_value='Linux'):
                manager = ExecutableManager('virtualbox', {})
                assert manager.vboxmanage == 'VBoxManage'

    def test_raises_for_qemu_hypervisor(self):
        """Test that accessing vboxmanage for QEMU raises exception."""
        with patch('shutil.which', return_value='/usr/bin/qemu-img'):
            manager = ExecutableManager('qemu', {})
            with pytest.raises(HypervisorException) as exc_info:
                _ = manager.vboxmanage
            assert 'only available for VirtualBox' in str(exc_info.value)


class TestResolutionPrecedence:
    """Tests for complete resolution precedence hierarchy."""

    def test_env_var_overrides_all_for_qemu_img(self):
        """Test that env var has highest precedence for qemu-img."""
        with patch.dict('os.environ', {'QEMU_IMG_BIN': '/env/qemu-img'}):
            with patch('shutil.which', return_value='/env/qemu-img'):
                manager = ExecutableManager('qemu', {'qemu_img_exe': '/config/qemu-img'})
                assert manager.qemu_img == '/env/qemu-img'

    def test_env_var_overrides_all_for_qemu_system(self):
        """Test that env var has highest precedence for qemu-system."""
        with patch.dict('os.environ', {'QEMU_SYSTEM_BIN': '/env/qemu-system'}):
            with patch('shutil.which', return_value='/env/qemu-system'):
                manager = ExecutableManager('qemu', {
                    'qemu_system_exe': '/config/qemu-system',
                    'architecture': 'arm64'
                })
                assert manager.qemu_system == '/env/qemu-system'

    def test_env_var_overrides_all_for_vboxmanage(self):
        """Test that env var has highest precedence for VBoxManage."""
        with patch.dict('os.environ', {'VBOXMANAGE_BIN': '/env/VBoxManage'}):
            with patch('shutil.which', return_value='/env/VBoxManage'):
                with patch('platform.system', return_value='Linux'):
                    manager = ExecutableManager('virtualbox', {'vboxmanage_exe': '/config/VBoxManage'})
                    assert manager.vboxmanage == '/env/VBoxManage'

    def test_config_overrides_default(self):
        """Test that config overrides default values."""
        with patch.dict('os.environ', {}, clear=True):
            with patch('shutil.which', return_value='/config/custom-qemu-img'):
                manager = ExecutableManager('qemu', {'qemu_img_exe': '/config/custom-qemu-img'})
                assert manager.qemu_img == '/config/custom-qemu-img'


class TestPlatformSpecificDefaults:
    """Tests for platform-specific default values."""

    def test_windows_vboxmanage_default(self):
        """Test VBoxManage.exe is default on Windows."""
        with patch.dict('os.environ', {}, clear=True):
            with patch('shutil.which', return_value='VBoxManage.exe'):
                with patch('platform.system', return_value='Windows'):
                    manager = ExecutableManager('virtualbox', {})
                    # Verify the cached value has .exe extension
                    assert manager._cache['vboxmanage'] == 'VBoxManage.exe'

    def test_linux_vboxmanage_default(self):
        """Test VBoxManage (no extension) is default on Linux."""
        with patch.dict('os.environ', {}, clear=True):
            with patch('shutil.which', return_value='VBoxManage'):
                with patch('platform.system', return_value='Linux'):
                    manager = ExecutableManager('virtualbox', {})
                    assert manager._cache['vboxmanage'] == 'VBoxManage'

    def test_darwin_vboxmanage_default(self):
        """Test VBoxManage (no extension) is default on macOS."""
        with patch.dict('os.environ', {}, clear=True):
            with patch('shutil.which', return_value='VBoxManage'):
                with patch('platform.system', return_value='Darwin'):
                    manager = ExecutableManager('virtualbox', {})
                    assert manager._cache['vboxmanage'] == 'VBoxManage'


class TestArchitectureSupport:
    """Tests for architecture-aware executable resolution."""

    def test_x86_64_architecture(self):
        """Test qemu-system-x86_64 for x86_64 architecture."""
        with patch.dict('os.environ', {}, clear=True):
            with patch('shutil.which', return_value='qemu-system-x86_64'):
                manager = ExecutableManager('qemu', {'architecture': 'x86_64'})
                assert manager.qemu_system == 'qemu-system-x86_64'

    def test_aarch64_architecture(self):
        """Test qemu-system-aarch64 for aarch64 architecture."""
        with patch.dict('os.environ', {}, clear=True):
            with patch('shutil.which', return_value='qemu-system-aarch64'):
                manager = ExecutableManager('qemu', {'architecture': 'aarch64'})
                assert manager.qemu_system == 'qemu-system-aarch64'

    def test_arm_architecture(self):
        """Test qemu-system-arm for arm architecture."""
        with patch.dict('os.environ', {}, clear=True):
            with patch('shutil.which', return_value='qemu-system-arm'):
                manager = ExecutableManager('qemu', {'architecture': 'arm'})
                assert manager.qemu_system == 'qemu-system-arm'

    def test_i386_architecture(self):
        """Test qemu-system-i386 for i386 architecture."""
        with patch.dict('os.environ', {}, clear=True):
            with patch('shutil.which', return_value='qemu-system-i386'):
                manager = ExecutableManager('qemu', {'architecture': 'i386'})
                assert manager.qemu_system == 'qemu-system-i386'

    def test_ppc64_architecture(self):
        """Test qemu-system-ppc64 for ppc64 architecture."""
        with patch.dict('os.environ', {}, clear=True):
            with patch('shutil.which', return_value='qemu-system-ppc64'):
                manager = ExecutableManager('qemu', {'architecture': 'ppc64'})
                assert manager.qemu_system == 'qemu-system-ppc64'


class TestErrorHandling:
    """Tests for error handling scenarios."""

    def test_missing_qemu_img_raises_exception(self):
        """Test that missing qemu-img raises HypervisorException."""
        with patch('shutil.which', return_value=None):
            with pytest.raises(HypervisorException) as exc_info:
                ExecutableManager('qemu', {})
            assert 'qemu-img' in str(exc_info.value)

    def test_missing_qemu_system_raises_exception(self):
        """Test that missing qemu-system raises HypervisorException."""
        def which_side_effect(path):
            if 'qemu-img' in path:
                return path
            return None

        with patch('shutil.which', side_effect=which_side_effect):
            with pytest.raises(HypervisorException) as exc_info:
                ExecutableManager('qemu', {})
            assert 'qemu-system' in str(exc_info.value)

    def test_missing_vboxmanage_raises_exception(self):
        """Test that missing VBoxManage raises HypervisorException."""
        with patch('shutil.which', return_value=None):
            with patch('platform.system', return_value='Linux'):
                with pytest.raises(HypervisorException) as exc_info:
                    ExecutableManager('virtualbox', {})
                assert 'VBoxManage' in str(exc_info.value)

    def test_exception_suggests_installing_tools(self):
        """Test that exception message suggests installing required tools."""
        with patch('shutil.which', return_value=None):
            with pytest.raises(HypervisorException) as exc_info:
                ExecutableManager('qemu', {})
            assert 'install' in str(exc_info.value).lower()

    def test_exception_suggests_environment_variable(self):
        """Test that exception message mentions environment variable option."""
        with patch('shutil.which', return_value=None):
            with pytest.raises(HypervisorException) as exc_info:
                ExecutableManager('qemu', {})
            assert 'environment variable' in str(exc_info.value).lower()


class TestCaching:
    """Tests for caching behavior."""

    def test_qemu_executables_cached_after_init(self):
        """Test that QEMU executables are cached after initialization."""
        with patch('shutil.which', return_value='/usr/bin/qemu-img'):
            manager = ExecutableManager('qemu', {})
            assert 'qemu_img' in manager._cache
            assert 'qemu_system' in manager._cache

    def test_vboxmanage_cached_after_init(self):
        """Test that VBoxManage is cached after initialization."""
        with patch('shutil.which', return_value='/usr/bin/VBoxManage'):
            with patch('platform.system', return_value='Linux'):
                manager = ExecutableManager('virtualbox', {})
                assert 'vboxmanage' in manager._cache

    def test_property_access_uses_cache(self):
        """Test that property access uses cached value without re-resolving."""
        with patch('shutil.which', return_value='/usr/bin/qemu-img') as mock_which:
            manager = ExecutableManager('qemu', {})
            initial_call_count = mock_which.call_count

            # Access properties multiple times
            _ = manager.qemu_img
            _ = manager.qemu_img
            _ = manager.qemu_system

            # which() should not be called again after init
            assert mock_which.call_count == initial_call_count
