"""
Centralized executable path resolution for hypervisors.
"""
import os
import platform
import shutil

from adare.hypervisor.exceptions import HypervisorException


class ExecutableManager:
    """
    Manages executable path resolution for hypervisor tools.

    Resolution order:
    1. Environment variables (e.g., QEMU_IMG_BIN)
    2. HYPERVISOR_CONFIGS
    3. Platform-specific defaults

    All paths are validated at initialization time.
    """

    def __init__(self, hypervisor_type: str, config: dict):
        """
        Args:
            hypervisor_type: 'qemu' or 'virtualbox'
            config: Config dict from HYPERVISOR_CONFIGS[hypervisor_type]
        """
        self.hypervisor_type = hypervisor_type
        self.config = config
        self.host_os = platform.system().lower()
        self._cache = {}  # Cache resolved paths

        # Validate at init time
        self._resolve_all()

    def _resolve_all(self):
        """Resolve and validate all executables for this hypervisor."""
        if self.hypervisor_type == 'qemu':
            self._cache['qemu_img'] = self._resolve_qemu_img()
            self._cache['qemu_system'] = self._resolve_qemu_system()
        elif self.hypervisor_type == 'virtualbox':
            self._cache['vboxmanage'] = self._resolve_vboxmanage()

    def _resolve_qemu_img(self) -> str:
        """Resolve qemu-img executable path."""
        # 1. Check environment variable override
        if env_path := os.getenv('QEMU_IMG_BIN'):
            return self._validate_executable(env_path, 'qemu-img')

        # 2. Check config
        config_path = self.config.get('qemu_img_exe', 'qemu-img')
        return self._validate_executable(config_path, 'qemu-img')

    def _resolve_qemu_system(self) -> str:
        """Resolve qemu-system executable path."""
        # 1. Check environment variable override
        if env_path := os.getenv('QEMU_SYSTEM_BIN'):
            return self._validate_executable(env_path, 'qemu-system')

        # 2. Check config (supports architecture override)
        arch = self.config.get('architecture', 'x86_64')
        default = f'qemu-system-{arch}'
        config_path = self.config.get('qemu_system_exe', default)
        return self._validate_executable(config_path, 'qemu-system')

    def _resolve_vboxmanage(self) -> str:
        """Resolve VBoxManage executable path."""
        # 1. Check environment variable override
        if env_path := os.getenv('VBOXMANAGE_BIN'):
            return self._validate_executable(env_path, 'VBoxManage')

        # 2. Check config
        config_path = self.config.get('vboxmanage_exe')

        # 3. Platform-specific default
        if not config_path:
            config_path = 'VBoxManage.exe' if self.host_os == 'windows' else 'VBoxManage'

        return self._validate_executable(config_path, 'VBoxManage')

    def _validate_executable(self, path: str, name: str) -> str:
        """
        Validate executable exists in PATH.

        Args:
            path: Executable name or absolute path
            name: Display name for error messages

        Returns:
            Validated executable path

        Raises:
            HypervisorException: If executable not found in PATH
        """
        if not shutil.which(path):
            raise HypervisorException(
                f"{name} executable '{path}' not found in PATH. "
                f"Please install required tools or set environment variable."
            )
        return path

    @property
    def qemu_img(self) -> str:
        """Get qemu-img executable path."""
        if self.hypervisor_type != 'qemu':
            raise HypervisorException("qemu_img only available for QEMU hypervisor")
        return self._cache['qemu_img']

    @property
    def qemu_system(self) -> str:
        """Get qemu-system executable path."""
        if self.hypervisor_type != 'qemu':
            raise HypervisorException("qemu_system only available for QEMU hypervisor")
        return self._cache['qemu_system']

    @property
    def vboxmanage(self) -> str:
        """Get VBoxManage executable path."""
        if self.hypervisor_type != 'virtualbox':
            raise HypervisorException("vboxmanage only available for VirtualBox hypervisor")
        return self._cache['vboxmanage']
