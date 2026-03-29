"""Tests for FilesystemDiffManager."""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from adare.backend.experiment.filesystem_diff_manager import FilesystemDiffManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_manager(
    vm=None,
    execution_context=None,
    experiment_run_directory=None,
    action_executor=None,
):
    """Create a FilesystemDiffManager with sensible defaults."""
    return FilesystemDiffManager(
        vm=vm,
        execution_context=execution_context or {},
        experiment_run_directory=experiment_run_directory,
        action_executor=action_executor or MagicMock(),
    )


def _make_qemu_vm():
    """Create a mock that looks like a QEMU VM."""
    vm = MagicMock()
    vm.__class__ = type('QEMUVM', (), {})
    return vm


def _make_vbox_vm():
    """Create a mock that looks like a VirtualBox VM."""
    vm = MagicMock()
    vm.__class__ = type('VirtualBoxVM', (), {})
    return vm


# ---------------------------------------------------------------------------
# determine_diff_enabled
# ---------------------------------------------------------------------------

class TestDetermineEnabled:
    """Test determine_diff_enabled precedence logic."""

    def test_cli_override_true(self):
        config = MagicMock()
        config.enable_diff = True
        mgr = _make_manager(execution_context={'config': config})

        playbook = MagicMock()
        playbook.settings.enable_filesystem_diff = False

        assert mgr.determine_diff_enabled(playbook) is True

    def test_cli_override_false(self):
        config = MagicMock()
        config.enable_diff = False
        mgr = _make_manager(execution_context={'config': config})

        playbook = MagicMock()
        playbook.settings.enable_filesystem_diff = True

        assert mgr.determine_diff_enabled(playbook) is False

    def test_falls_back_to_playbook_enabled(self):
        mgr = _make_manager()
        playbook = MagicMock()
        playbook.settings.enable_filesystem_diff = True
        assert mgr.determine_diff_enabled(playbook) is True

    def test_falls_back_to_playbook_disabled(self):
        mgr = _make_manager()
        playbook = MagicMock()
        playbook.settings.enable_filesystem_diff = False
        assert mgr.determine_diff_enabled(playbook) is False

    def test_defaults_false_when_no_config_or_settings(self):
        mgr = _make_manager()
        playbook = MagicMock(spec=[])  # no 'settings' attribute
        assert mgr.determine_diff_enabled(playbook) is False

    def test_cli_config_none_falls_back_to_playbook(self):
        config = MagicMock()
        config.enable_diff = None  # explicit None -> not set
        mgr = _make_manager(execution_context={'config': config})

        playbook = MagicMock()
        playbook.settings.enable_filesystem_diff = True
        assert mgr.determine_diff_enabled(playbook) is True


# ---------------------------------------------------------------------------
# resolve_diff_mode
# ---------------------------------------------------------------------------

class TestResolveDiffMode:
    """Test diff mode auto-resolution logic."""

    def test_explicit_guest_mode(self):
        config = MagicMock()
        config.diff_mode = 'guest'
        mgr = _make_manager(execution_context={'config': config})
        assert mgr.resolve_diff_mode() == 'guest'

    def test_explicit_host_mode(self):
        config = MagicMock()
        config.diff_mode = 'host'
        mgr = _make_manager(execution_context={'config': config})
        assert mgr.resolve_diff_mode() == 'host'

    def test_auto_with_qemu_and_virt_diff(self):
        config = MagicMock()
        config.diff_mode = 'auto'
        mgr = _make_manager(vm=_make_qemu_vm(), execution_context={'config': config})

        with patch.object(mgr, '_is_virt_diff_available', return_value=True):
            assert mgr.resolve_diff_mode() == 'host'

    def test_auto_with_qemu_no_virt_diff(self):
        config = MagicMock()
        config.diff_mode = 'auto'
        mgr = _make_manager(vm=_make_qemu_vm(), execution_context={'config': config})

        with patch.object(mgr, '_is_virt_diff_available', return_value=False):
            assert mgr.resolve_diff_mode() == 'guest'

    def test_auto_with_virtualbox(self):
        config = MagicMock()
        config.diff_mode = 'auto'
        mgr = _make_manager(vm=_make_vbox_vm(), execution_context={'config': config})
        assert mgr.resolve_diff_mode() == 'guest'

    def test_auto_with_no_vm(self):
        config = MagicMock()
        config.diff_mode = 'auto'
        mgr = _make_manager(vm=None, execution_context={'config': config})
        assert mgr.resolve_diff_mode() == 'guest'

    def test_defaults_to_auto_when_no_config(self):
        mgr = _make_manager(vm=_make_vbox_vm())
        # No config in context -> defaults to 'auto' -> guest for non-QEMU
        assert mgr.resolve_diff_mode() == 'guest'


# ---------------------------------------------------------------------------
# _is_qemu_vm
# ---------------------------------------------------------------------------

class TestIsQemuVM:
    """Test QEMU VM detection."""

    def test_qemu_vm_detected(self):
        mgr = _make_manager(vm=_make_qemu_vm())
        assert mgr._is_qemu_vm() is True

    def test_virtualbox_vm_not_detected(self):
        mgr = _make_manager(vm=_make_vbox_vm())
        assert mgr._is_qemu_vm() is False

    def test_none_vm(self):
        mgr = _make_manager(vm=None)
        assert mgr._is_qemu_vm() is False


# ---------------------------------------------------------------------------
# validate_host_mode_support
# ---------------------------------------------------------------------------

class TestValidateHostModeSupport:
    """Test host mode validation raises on bad config."""

    def test_raises_for_non_qemu(self):
        mgr = _make_manager(vm=_make_vbox_vm())
        with pytest.raises(Exception, match="requires QEMU"):
            mgr.validate_host_mode_support()

    def test_raises_when_virt_diff_missing(self):
        mgr = _make_manager(vm=_make_qemu_vm())
        with patch.object(mgr, '_is_virt_diff_available', return_value=False):
            with pytest.raises(Exception, match="guestfish not found"):
                mgr.validate_host_mode_support()

    def test_passes_when_qemu_and_virt_diff(self):
        mgr = _make_manager(vm=_make_qemu_vm())
        with patch.object(mgr, '_is_virt_diff_available', return_value=True):
            # Should not raise
            mgr.validate_host_mode_support()
