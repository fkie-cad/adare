"""Tests for VM database getter deduplication (_get_vm helper)."""

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit

# We patch VmApi and field_extractor at the module level where they're imported
MODULE = "adare.backend.vm.database"


@pytest.fixture
def mock_vm():
    """Create a mock VM object with typical attributes."""
    vm = MagicMock()
    vm.id = "vm-001"
    vm.name = "Ubuntu20"
    vm.file = "/vms/ubuntu20.qcow2"
    vm.hash = "abc123"
    vm.description = "Test VM"
    vm.osinfo = MagicMock()
    return vm


@pytest.fixture
def mock_api(mock_vm):
    """Create a mock VmApi context manager that returns mock_vm for lookups."""
    api_instance = MagicMock()
    api_instance.get_vm_by_hash.return_value = mock_vm
    api_instance.get_vm_by_name.return_value = mock_vm
    api_instance.get_vm_by_id.return_value = mock_vm

    api_cls = MagicMock()
    api_cls.return_value.__enter__ = MagicMock(return_value=api_instance)
    api_cls.return_value.__exit__ = MagicMock(return_value=False)
    return api_cls, api_instance


class TestGetVmHelper:
    """Tests for the _get_vm internal helper."""

    def test_calls_correct_api_method(self, mock_api, mock_vm):
        api_cls, api_instance = mock_api

        with patch(f"{MODULE}.VmApi", api_cls):
            from adare.backend.vm.database import _get_vm

            result = _get_vm("get_vm_by_hash", "abc123")

        api_instance.get_vm_by_hash.assert_called_once_with("abc123")
        assert result is mock_vm

    def test_returns_none_when_vm_not_found(self, mock_api):
        api_cls, api_instance = mock_api
        api_instance.get_vm_by_name.return_value = None

        with patch(f"{MODULE}.VmApi", api_cls):
            from adare.backend.vm.database import _get_vm

            result = _get_vm("get_vm_by_name", "nonexistent")

        assert result is None

    def test_extracts_fields_when_specified(self, mock_api, mock_vm):
        api_cls, api_instance = mock_api

        with patch(f"{MODULE}.VmApi", api_cls):
            from adare.backend.vm.database import _get_vm

            result = _get_vm("get_vm_by_id", "vm-001", fields=["id", "name"])

        assert isinstance(result, dict)
        assert result["id"] == "vm-001"
        assert result["name"] == "Ubuntu20"

    def test_returns_full_object_when_no_fields(self, mock_api, mock_vm):
        api_cls, api_instance = mock_api

        with patch(f"{MODULE}.VmApi", api_cls):
            from adare.backend.vm.database import _get_vm

            result = _get_vm("get_vm_by_hash", "abc123", fields=None)

        # Without fields, extract_fields returns the original object
        assert result is mock_vm


class TestGetVmByHash:
    """Tests for get_vm_by_hash delegating to _get_vm."""

    def test_returns_extracted_fields_when_vm_found(self, mock_api, mock_vm):
        api_cls, api_instance = mock_api

        with patch(f"{MODULE}.VmApi", api_cls):
            from adare.backend.vm.database import get_vm_by_hash

            result = get_vm_by_hash("abc123", fields=["id", "name", "hash"])

        api_instance.get_vm_by_hash.assert_called_once_with("abc123")
        assert isinstance(result, dict)
        assert result["id"] == "vm-001"
        assert result["name"] == "Ubuntu20"
        assert result["hash"] == "abc123"

    def test_returns_full_object_without_fields(self, mock_api, mock_vm):
        api_cls, api_instance = mock_api

        with patch(f"{MODULE}.VmApi", api_cls):
            from adare.backend.vm.database import get_vm_by_hash

            result = get_vm_by_hash("abc123")

        assert result is mock_vm


class TestGetVmByName:
    """Tests for get_vm_by_name delegating to _get_vm."""

    def test_returns_none_when_vm_not_found(self, mock_api):
        api_cls, api_instance = mock_api
        api_instance.get_vm_by_name.return_value = None

        with patch(f"{MODULE}.VmApi", api_cls):
            from adare.backend.vm.database import get_vm_by_name

            result = get_vm_by_name("nonexistent")

        api_instance.get_vm_by_name.assert_called_once_with("nonexistent")
        assert result is None

    def test_returns_full_object_when_found(self, mock_api, mock_vm):
        api_cls, api_instance = mock_api

        with patch(f"{MODULE}.VmApi", api_cls):
            from adare.backend.vm.database import get_vm_by_name

            result = get_vm_by_name("Ubuntu20")

        assert result is mock_vm


class TestGetVmById:
    """Tests for get_vm_by_id delegating to _get_vm."""

    def test_returns_specific_fields(self, mock_api, mock_vm):
        api_cls, api_instance = mock_api

        with patch(f"{MODULE}.VmApi", api_cls):
            from adare.backend.vm.database import get_vm_by_id

            result = get_vm_by_id("vm-001", fields=["id", "file"])

        api_instance.get_vm_by_id.assert_called_once_with("vm-001")
        assert isinstance(result, dict)
        assert result["id"] == "vm-001"
        assert result["file"] == "/vms/ubuntu20.qcow2"
        assert "name" not in result

    def test_returns_none_when_not_found(self, mock_api):
        api_cls, api_instance = mock_api
        api_instance.get_vm_by_id.return_value = None

        with patch(f"{MODULE}.VmApi", api_cls):
            from adare.backend.vm.database import get_vm_by_id

            result = get_vm_by_id("no-such-id")

        assert result is None
