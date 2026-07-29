"""An install-phase QMP socket path must fit the AF_UNIX limit.

``sockaddr_un.sun_path`` is 104 bytes on macOS including the NUL, and macOS sets
``TMPDIR`` to a 48-character per-user folder. A recipe base disk is named
``<profile>-recipebase-<hash>.partial``, so ``gettempdir() /
f'adare-qemu-install-{stem}.qmp'`` came to 116 characters and every Stage 1 Windows
recipe build died with ``OSError: AF_UNIX path too long`` before QEMU was launched —
with the failure reported as a bare non-zero QEMU exit.
"""

import tempfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

from adare.hypervisor.qemu.vm_creator.qmp_utils import AF_UNIX_PATH_MAX, install_qmp_socket_path

# The name that triggered the bug.
RECIPE_BASE_STEM = 'windows11arm64-recipebase-03ded856fcd8.partial'


def _set_tmpdir(monkeypatch, directory: Path) -> None:
    """Point tempfile at *directory*.

    `tempfile.gettempdir()` memoises its answer in `tempfile.tempdir` on first use,
    so setting TMPDIR alone has no effect once anything has already asked. Clearing
    the cache is what makes the env var take.
    """
    monkeypatch.setenv('TMPDIR', str(directory))
    monkeypatch.setattr(tempfile, 'tempdir', None)


class TestInstallQmpSocketPath:

    @pytest.mark.parametrize('stem', [
        'win11arm',
        RECIPE_BASE_STEM,
        'windows11arm64-recipebase-' + 'f' * 12 + '.partial',
        'x' * 200,
    ])
    def test_always_within_the_af_unix_limit(self, stem):
        assert len(str(install_qmp_socket_path(stem))) <= AF_UNIX_PATH_MAX

    def test_within_limit_under_a_long_tmpdir(self, tmp_path, monkeypatch):
        """macOS-shaped TMPDIR: long, but still short enough to be usable."""
        long_tmp = tmp_path / ('d' * 40)
        long_tmp.mkdir()
        _set_tmpdir(monkeypatch, long_tmp)
        assert len(str(install_qmp_socket_path(RECIPE_BASE_STEM))) <= AF_UNIX_PATH_MAX

    def test_falls_back_to_tmp_when_tmpdir_is_hopeless(self, tmp_path, monkeypatch):
        """With a TMPDIR too long for even the shortest name, /tmp is used."""
        hopeless = tmp_path / ('d' * 90)
        hopeless.mkdir(parents=True, exist_ok=True)
        _set_tmpdir(monkeypatch, hopeless)
        path = install_qmp_socket_path(RECIPE_BASE_STEM)
        assert len(str(path)) <= AF_UNIX_PATH_MAX
        assert path.parent == Path('/tmp')

    def test_keeps_the_readable_name_when_it_fits(self, tmp_path, monkeypatch):
        _set_tmpdir(monkeypatch, tmp_path)
        path = install_qmp_socket_path('win11arm')
        assert path.name == 'adare-qemu-install-win11arm.qmp'

    def test_distinct_disks_get_distinct_sockets(self):
        """Two concurrent builds must not share one socket."""
        a = install_qmp_socket_path('windows11arm64-recipebase-aaaaaaaaaaaa.partial')
        b = install_qmp_socket_path('windows11arm64-recipebase-bbbbbbbbbbbb.partial')
        assert a != b

    def test_same_disk_gets_a_stable_socket(self):
        """The path is recomputed for cleanup, so it must not drift per call."""
        assert install_qmp_socket_path(RECIPE_BASE_STEM) == install_qmp_socket_path(RECIPE_BASE_STEM)

    def test_always_a_qmp_suffix(self):
        # `find_stale_sockets` globs '*.qmp' and reads the VM name off the stem.
        assert install_qmp_socket_path(RECIPE_BASE_STEM).suffix == '.qmp'
