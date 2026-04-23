"""Tests for VMOperationProxy base class and subclass inheritance."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.unit

from adare.backend.experiment.host_services.guest_command_proxy import GuestCommandProxy
from adare.backend.experiment.host_services.guest_file_proxy import GuestFileProxy
from adare.backend.experiment.host_services.vm_operation_proxy import VMOperationProxy


class TestVMOperationProxy:
    """Tests for the VMOperationProxy base class."""

    def test_init_sets_vm(self):
        vm = MagicMock()
        proxy = VMOperationProxy(vm, 'Ubuntu 24.04')
        assert proxy.vm is vm

    def test_init_detects_windows(self):
        proxy = VMOperationProxy(MagicMock(), 'Windows 11')
        assert proxy.is_windows is True

    def test_init_detects_linux(self):
        proxy = VMOperationProxy(MagicMock(), 'Ubuntu 24.04')
        assert proxy.is_windows is False

    def test_init_detects_windows_case_insensitive(self):
        proxy = VMOperationProxy(MagicMock(), 'WINDOWS 10 Pro')
        assert proxy.is_windows is True

    def test_init_stores_guest_os(self):
        proxy = VMOperationProxy(MagicMock(), 'Windows 10')
        assert proxy.guest_os == 'Windows 10'

    def test_init_stores_guest_os_linux(self):
        proxy = VMOperationProxy(MagicMock(), 'Fedora 40')
        assert proxy.guest_os == 'Fedora 40'

    @pytest.mark.asyncio
    async def test_context_manager_returns_self(self):
        proxy = VMOperationProxy(MagicMock(), 'linux')
        async with proxy as p:
            assert p is proxy

    @pytest.mark.asyncio
    async def test_context_manager_calls_cleanup_on_exit(self):
        proxy = VMOperationProxy(MagicMock(), 'linux')
        proxy.cleanup = MagicMock()
        async with proxy:
            pass
        proxy.cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager_calls_cleanup_on_exception(self):
        proxy = VMOperationProxy(MagicMock(), 'linux')
        proxy.cleanup = MagicMock()
        with pytest.raises(ValueError):
            async with proxy:
                raise ValueError("test error")
        proxy.cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_manager_does_not_suppress_exceptions(self):
        proxy = VMOperationProxy(MagicMock(), 'linux')
        with pytest.raises(RuntimeError, match="should propagate"):
            async with proxy:
                raise RuntimeError("should propagate")

    def test_default_cleanup_does_nothing(self):
        proxy = VMOperationProxy(MagicMock(), 'linux')
        proxy.cleanup()  # Should not raise


class TestGuestCommandProxyInheritance:
    """Tests that GuestCommandProxy correctly inherits from VMOperationProxy."""

    def test_inherits_from_vm_operation_proxy(self):
        assert issubclass(GuestCommandProxy, VMOperationProxy)

    def test_isinstance_of_vm_operation_proxy(self):
        proxy = GuestCommandProxy(MagicMock(), 'Ubuntu 24.04')
        assert isinstance(proxy, VMOperationProxy)

    def test_init_sets_vm_and_guest_os(self):
        vm = MagicMock()
        proxy = GuestCommandProxy(vm, 'Ubuntu 24.04')
        assert proxy.vm is vm
        assert proxy.guest_os == 'Ubuntu 24.04'
        assert proxy.is_windows is False

    def test_init_detects_windows(self):
        proxy = GuestCommandProxy(MagicMock(), 'Windows 11')
        assert proxy.is_windows is True

    @pytest.mark.asyncio
    async def test_context_manager_available(self):
        proxy = GuestCommandProxy(MagicMock(), 'linux')
        proxy.cleanup = MagicMock()
        async with proxy as p:
            assert p is proxy
        proxy.cleanup.assert_called_once()


class TestGuestFileProxyInheritance:
    """Tests that GuestFileProxy correctly inherits from VMOperationProxy."""

    def test_inherits_from_vm_operation_proxy(self):
        assert issubclass(GuestFileProxy, VMOperationProxy)

    def test_isinstance_of_vm_operation_proxy(self):
        proxy = GuestFileProxy(MagicMock(), 'Ubuntu 24.04')
        try:
            assert isinstance(proxy, VMOperationProxy)
        finally:
            proxy.cleanup()

    def test_init_sets_vm_and_guest_os(self):
        vm = MagicMock()
        proxy = GuestFileProxy(vm, 'Fedora 40')
        try:
            assert proxy.vm is vm
            assert proxy.guest_os == 'Fedora 40'
            assert proxy.is_windows is False
        finally:
            proxy.cleanup()

    def test_creates_temp_directory(self):
        proxy = GuestFileProxy(MagicMock(), 'linux')
        try:
            assert proxy._temp_root.exists()
            assert proxy._temp_root.is_dir()
            assert 'adare_host_test_' in str(proxy._temp_root)
        finally:
            proxy.cleanup()

    def test_init_creates_empty_caches(self):
        proxy = GuestFileProxy(MagicMock(), 'linux')
        try:
            assert proxy._cache == {}
            assert proxy._metadata_cache == {}
        finally:
            proxy.cleanup()

    def test_cleanup_removes_temp_directory(self):
        proxy = GuestFileProxy(MagicMock(), 'linux')
        temp_root = proxy._temp_root
        assert temp_root.exists()
        proxy.cleanup()
        assert not temp_root.exists()

    def test_cleanup_clears_caches(self):
        proxy = GuestFileProxy(MagicMock(), 'linux')
        # Populate caches manually
        proxy._cache['/some/path'] = Path('/tmp/fake')
        proxy._metadata_cache['/some/path'] = MagicMock()
        proxy.cleanup()
        assert proxy._cache == {}
        assert proxy._metadata_cache == {}

    @pytest.mark.asyncio
    async def test_context_manager_cleans_up_temp_dir(self):
        async with GuestFileProxy(MagicMock(), 'linux') as proxy:
            temp_root = proxy._temp_root
            assert temp_root.exists()
        assert not temp_root.exists()

    @pytest.mark.asyncio
    async def test_context_manager_cleans_up_on_exception(self):
        temp_root = None
        with pytest.raises(ValueError):
            async with GuestFileProxy(MagicMock(), 'linux') as proxy:
                temp_root = proxy._temp_root
                assert temp_root.exists()
                raise ValueError("test error")
        assert temp_root is not None
        assert not temp_root.exists()
