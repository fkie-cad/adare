import pytest

pytestmark = pytest.mark.unit

from adare.config.configdirectory import (
    ADARE_DIR,
    ADAREVM_DIR,
    APPDATA_DIR,
    ENVIRONMENTS_DIR,
    OS_PROFILES_DIR,
    STATE_DIR,
    VMS_DIR,
    ensure_directories,
)


def test_adarevm_dir_consistency():
    """ADAREVM_DIR should be derived from ADARE_DIR, not constructed independently."""
    assert ADAREVM_DIR == ADARE_DIR / 'adarevm'


def test_ensure_directories_creates_required_dirs():
    """ensure_directories() should create the appdata directory structure."""
    ensure_directories()

    assert APPDATA_DIR.exists()
    assert STATE_DIR.exists()
    assert VMS_DIR.exists()
    assert ENVIRONMENTS_DIR.exists()
    assert OS_PROFILES_DIR.exists()


def test_ensure_directories_is_idempotent():
    """Calling ensure_directories() multiple times should not raise errors."""
    ensure_directories()
    ensure_directories()

    # All directories still exist after second call
    assert APPDATA_DIR.exists()
    assert STATE_DIR.exists()
