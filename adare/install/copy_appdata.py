"""
Install the parts of the workspace that ADARE reads at runtime into the appdata directory.

``<appdata>/adare`` receives an allow-listed copy of the workspace (guest agent
sources, shared library, appdata, skills and the uv workspace metadata that
``uv run --package adarevm`` needs); everything else there is pruned, so stale
files and build trees never accumulate. ``adare/appdata/*`` (except
testfunctions, which are loaded from that copy) is additionally copied to the
appdata root. Stdlib only: this runs with the system ``python3`` before the
workspace environment exists.
"""

import os
import platform
import shutil
import sys
from pathlib import Path

# Workspace root: this file lives at <root>/adare/install/copy_appdata.py.
# Resolved from the file, not the cwd, because install.ps1 runs it from adare/.
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]

# Directories / files of the workspace copied to <appdata>/adare (relative paths).
WORKSPACE_DIRS = ('adarevm', 'adarelib', 'adare/appdata', 'skills')
WORKSPACE_FILES = (
    'pyproject.toml',
    'uv.lock',
    'README.md',
    'adare/pyproject.toml',
    'adare-cv-server/pyproject.toml',
)

IGNORE_PATTERNS = (
    '.venv',
    'venv',
    'build',
    'dist',
    'node_modules',
    '.idea',
    '.git',
    '*.egg-info',
    '__pycache__',
    '*.pyc',
    '.pytest_cache',
    '.mypy_cache',
    '.ruff_cache',
    '.DS_Store',
)


def appdata_directory(program_name: str = 'adare') -> Path:
    """Same resolution as ``adare.config.configdirectory`` (``$ADARE_HOME`` first)."""
    override = os.getenv('ADARE_HOME')
    if override:
        return Path(override).expanduser()
    if platform.system() == 'Windows':
        appdata = os.getenv('APPDATA')
        if appdata:
            return Path(appdata) / program_name
    return Path.home() / f'.{program_name}'


def _remove(path: Path) -> None:
    if path.is_dir() and not path.is_symlink():
        shutil.rmtree(path)
    else:
        path.unlink()


def _prune(directory: Path, prefix: Path, allowed: set[Path], ancestors: set[Path]) -> None:
    """Delete every entry below ``directory`` that is neither allowed nor on the way to one."""
    for entry in directory.iterdir():
        rel = prefix / entry.name
        if rel in allowed:
            continue
        if rel in ancestors and entry.is_dir() and not entry.is_symlink():
            _prune(entry, rel, allowed, ancestors)
        else:
            _remove(entry)


def sync_workspace(src: Path, dst: Path) -> None:
    """Make ``dst`` an allow-listed copy of the workspace at ``src``.

    Allowed directories are deleted and copied fresh (so files removed upstream
    disappear), allowed files are overwritten, and anything else in ``dst`` is
    removed.
    """
    allowed = {Path(p) for p in (*WORKSPACE_DIRS, *WORKSPACE_FILES)}
    ancestors = {parent for path in allowed for parent in path.parents if parent != Path('.')}
    dst.mkdir(parents=True, exist_ok=True)
    _prune(dst, Path(), allowed, ancestors)

    ignore = shutil.ignore_patterns(*IGNORE_PATTERNS)
    for rel in WORKSPACE_DIRS:
        source, target = src / rel, dst / rel
        if target.exists():
            _remove(target)
        if source.is_dir():
            shutil.copytree(source, target, ignore=ignore)
    for rel in WORKSPACE_FILES:
        source, target = src / rel, dst / rel
        if source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)


def install_appdata(src: Path, appdata_dir: Path) -> None:
    """Copy ``src/adare/appdata/*`` (except testfunctions) to the appdata root."""
    ignore = shutil.ignore_patterns(*IGNORE_PATTERNS)
    for entry in (src / 'adare' / 'appdata').iterdir():
        if entry.name == 'testfunctions':  # loaded from <appdata>/adare/adare/appdata
            continue
        if entry.is_dir():
            shutil.copytree(entry, appdata_dir / entry.name, dirs_exist_ok=True, ignore=ignore)
        else:
            shutil.copy2(entry, appdata_dir / entry.name)


def main() -> int:
    appdata_dir = appdata_directory()
    appdata_dir.mkdir(parents=True, exist_ok=True)
    sync_workspace(WORKSPACE_ROOT, appdata_dir / 'adare')
    install_appdata(WORKSPACE_ROOT, appdata_dir)
    print(f'Installed ADARE appdata into {appdata_dir}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
