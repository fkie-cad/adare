"""The installer copies only the allow-listed workspace parts and prunes the rest."""

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SCRIPT = Path(__file__).resolve().parents[4] / 'install' / 'copy_appdata.py'


@pytest.fixture(scope='module')
def copy_appdata():
    spec = importlib.util.spec_from_file_location('copy_appdata', SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(path: Path, text: str = 'x') -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture
def workspace(tmp_path):
    src = tmp_path / 'src'
    for rel in (
        'pyproject.toml',
        'uv.lock',
        'README.md',
        'adare/pyproject.toml',
        'adare/adare/run.py',  # host package: not consumed from appdata
        'adare/appdata/os-profiles/ubuntu.yml',
        'adare/appdata/testfunctions/standard/standard.py',
        'adare/appdata/icon-library.yml',
        'adare-cv-server/pyproject.toml',
        'adare-cv-server/adare_cv_server/server.py',
        'adarevm/pyproject.toml',
        'adarevm/adarevm/main.py',
        'adarevm/.venv/lib/site.py',
        'adarevm/adarevm/__pycache__/main.cpython-313.pyc',
        'adarelib/adarelib/__init__.py',
        'adarelib/dist/adarelib-0.1.1-py3-none-any.whl',
        'skills/adare-overview/SKILL.md',
        'paper/huge.mp4',
        'adare-web/node_modules/x/index.js',
        '.venv/bin/python',
    ):
        _write(src / rel)
    return src


def _files(root: Path) -> set[str]:
    return {p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file()}


def test_sync_copies_only_allow_list(copy_appdata, workspace, tmp_path):
    dst = tmp_path / 'appdata' / 'adare'
    copy_appdata.sync_workspace(workspace, dst)

    assert _files(dst) == {
        'pyproject.toml',
        'uv.lock',
        'README.md',
        'adare/pyproject.toml',
        'adare/appdata/os-profiles/ubuntu.yml',
        'adare/appdata/testfunctions/standard/standard.py',
        'adare/appdata/icon-library.yml',
        'adare-cv-server/pyproject.toml',
        'adarevm/pyproject.toml',
        'adarevm/adarevm/main.py',
        'adarelib/adarelib/__init__.py',
        'skills/adare-overview/SKILL.md',
    }


def test_sync_prunes_stale_entries_and_removed_files(copy_appdata, workspace, tmp_path):
    dst = tmp_path / 'appdata' / 'adare'
    for stale in ('paper/old.mp4', 'adare/adare/run.py', 'adarevm/adarevm/removed.py', '.venv/bin/python', 'NOTES.md'):
        _write(dst / stale)

    copy_appdata.sync_workspace(workspace, dst)

    for stale in ('paper', 'adare/adare', 'adarevm/adarevm/removed.py', '.venv', 'NOTES.md'):
        assert not (dst / stale).exists(), stale


def test_install_appdata_skips_testfunctions(copy_appdata, workspace, tmp_path):
    appdata = tmp_path / 'appdata'
    appdata.mkdir()
    copy_appdata.install_appdata(workspace, appdata)

    assert (appdata / 'os-profiles' / 'ubuntu.yml').is_file()
    assert (appdata / 'icon-library.yml').is_file()
    assert not (appdata / 'testfunctions').exists()


def test_main_honors_adare_home(copy_appdata, workspace, tmp_path, monkeypatch):
    home = tmp_path / 'home'
    monkeypatch.setenv('ADARE_HOME', str(home))
    monkeypatch.setattr(copy_appdata, 'WORKSPACE_ROOT', workspace)

    assert copy_appdata.main() == 0
    assert (home / 'adare' / 'adarevm' / 'adarevm' / 'main.py').is_file()
    assert (home / 'os-profiles' / 'ubuntu.yml').is_file()


def test_workspace_root_is_repo_root(copy_appdata):
    assert (copy_appdata.WORKSPACE_ROOT / 'adarevm' / 'pyproject.toml').is_file()
    for rel in (*copy_appdata.WORKSPACE_DIRS, *copy_appdata.WORKSPACE_FILES):
        assert (copy_appdata.WORKSPACE_ROOT / rel).exists(), rel


def test_main_reports_unremovable_files_instead_of_crashing(copy_appdata, tmp_path, monkeypatch, capsys):
    """Root-owned guest leftovers (a venv a VM wrote through a share) fail with the fix, not a traceback."""
    monkeypatch.setenv('ADARE_HOME', str(tmp_path / 'home'))

    def denied(src, dst):
        raise PermissionError(13, 'Permission denied', str(dst / '.venv'))

    monkeypatch.setattr(copy_appdata, 'sync_workspace', denied)

    assert copy_appdata.main() == 1
    err = capsys.readouterr().err
    assert 'Cannot replace' in err and '.venv' in err
