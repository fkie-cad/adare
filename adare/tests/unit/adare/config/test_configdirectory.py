import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

from adare.config.configdirectory import (
    ADARE_DIR,
    ADAREVM_DIR,
    APPDATA_DIR,
    ENVIRONMENTS_DIR,
    OS_PROFILES_DIR,
    QEMU_STATE_DIR,
    STATE_DIR,
    VMS_DIR,
    ensure_directories,
)


def test_suite_runs_against_temp_adare_home():
    """The root conftest points ADARE_HOME at a temp dir; nothing may resolve to ~/.adare."""
    assert Path(os.environ['ADARE_HOME']) == APPDATA_DIR
    assert Path.home() / '.adare' != APPDATA_DIR
    assert APPDATA_DIR / 'qemu' == QEMU_STATE_DIR


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


def test_import_creates_nothing(tmp_path):
    """Importing the module only resolves paths; directories are created by ensure_directories()."""
    home = tmp_path / 'nested' / 'adare-home'
    code = (
        'from adare.config.configdirectory import APPDATA_DIR, QEMU_STATE_DIR; '
        'print(APPDATA_DIR); print(QEMU_STATE_DIR)'
    )
    proc = subprocess.run(
        [sys.executable, '-c', code],
        env={**os.environ, 'ADARE_HOME': str(home)},
        capture_output=True,
        text=True,
        check=True,
    )

    assert proc.stdout.split() == [str(home), str(home / 'qemu')]
    assert not (tmp_path / 'nested').exists()
