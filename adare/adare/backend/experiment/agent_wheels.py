"""
Guest agent wheels (adarelib, adarevm) versioned by source content.

Both packages keep a static ``version`` in their pyproject that is rarely bumped,
so comparing it with what a guest has installed cannot tell whether the guest
runs current code. Wheels are therefore built with a PEP 440 local version that
embeds a hash of the package sources (``0.1.1+g1a2b3c4d5e6f``): any source
change yields a new version, the installed-version check in ``agent_installer``
sees the mismatch, and the guest reinstalls.
"""

import hashlib
import logging
import os
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

log = logging.getLogger(__name__)

AGENT_PACKAGES = ('adarelib', 'adarevm')

HASH_LENGTH = 12

# Build output, caches and editor droppings never change what gets installed.
_IGNORED_DIRS = frozenset(
    {'__pycache__', '.venv', 'venv', 'dist', 'build', '.pytest_cache', '.mypy_cache', '.ruff_cache', '.git'}
)
_IGNORED_SUFFIXES = ('.pyc', '.pyo', '.egg-info')
_IGNORED_FILES = frozenset({'.DS_Store'})

# adarevm resolves adarelib from the uv workspace; the guest has no workspace,
# so the source entry is dropped for the build (the dependency itself stays).
_WORKSPACE_SOURCE = re.compile(r'adarelib\s*=\s*\{\s*workspace\s*=\s*true\s*\}')
_VERSION_LINE = re.compile(r'^(version\s*=\s*)"([^"]+)"', re.MULTILINE)


def _is_ignored(name: str) -> bool:
    return name in _IGNORED_DIRS or name in _IGNORED_FILES or name.endswith(_IGNORED_SUFFIXES)


def source_hash(pkg_dir: Path) -> str:
    """Hex SHA-256 over the relative paths and contents of a package's source files."""
    digest = hashlib.sha256()
    files: list[Path] = []
    for root, dirs, names in os.walk(pkg_dir):
        dirs[:] = [d for d in dirs if not _is_ignored(d)]
        files.extend(Path(root) / name for name in names if not _is_ignored(name))
    for path in sorted(files, key=lambda p: p.relative_to(pkg_dir).as_posix()):
        digest.update(path.relative_to(pkg_dir).as_posix().encode())
        digest.update(b'\0')
        digest.update(path.read_bytes())
        digest.update(b'\0')
    return digest.hexdigest()


def base_version(pkg_dir: Path) -> str:
    """The static ``[project] version`` from the package's pyproject.toml."""
    with (pkg_dir / 'pyproject.toml').open('rb') as fh:
        return str(tomllib.load(fh)['project']['version'])


def expected_version(pkg_dir: Path) -> str:
    """Version a wheel built from ``pkg_dir`` carries: ``<base>+g<hash12>``."""
    return f'{base_version(pkg_dir)}+g{source_hash(pkg_dir)[:HASH_LENGTH]}'


def wheel_versions(wheels_dir: Path) -> dict[str, str]:
    """Map package name to the version of its wheel in ``wheels_dir``."""
    versions: dict[str, str] = {}
    if not wheels_dir.is_dir():
        return versions
    for wheel in sorted(wheels_dir.glob('*.whl')):
        name, version = wheel.name.split('-')[:2]
        versions[name] = version
    return versions


def wheels_up_to_date(package_dirs: dict[str, Path], wheels_dir: Path) -> bool:
    """True if every package has a wheel whose version matches its current sources."""
    built = wheel_versions(wheels_dir)
    return all(built.get(name) == expected_version(pkg_dir) for name, pkg_dir in package_dirs.items())


def _build_wheel(pkg_dir: Path, wheels_dir: Path) -> None:
    """``uv build`` one package with its version rewritten to the content-hash version."""
    pyproject = pkg_dir / 'pyproject.toml'
    original = pyproject.read_text()
    version = expected_version(pkg_dir)  # hashed before the pyproject is touched
    rewritten, count = _VERSION_LINE.subn(rf'\g<1>"{version}"', original, count=1)
    if count != 1:
        raise ValueError(f'No static version found in {pyproject}')
    pyproject.write_text(_WORKSPACE_SOURCE.sub('', rewritten))
    try:
        subprocess.run(
            ['uv', 'build', '--wheel', '--out-dir', str(wheels_dir)],
            cwd=pkg_dir,
            check=True,
            capture_output=True,
        )
    finally:
        pyproject.write_text(original)


def build_agent_wheels(package_dirs: dict[str, Path], wheels_dir: Path) -> dict[str, Path]:
    """
    Build fresh wheels for the given packages into ``wheels_dir``.

    ``package_dirs`` maps package name to a *copy* of its sources (the project's
    ``vm_runtime``): the pyproject is rewritten for the duration of the build.
    Old wheels are removed first. Raises ``subprocess.CalledProcessError`` when
    ``uv build`` fails.

    Returns:
        Package name -> path of the built wheel.
    """
    wheels_dir.mkdir(parents=True, exist_ok=True)
    for old_wheel in wheels_dir.glob('*.whl'):
        old_wheel.unlink()
    # adarelib first: it has no path dependencies
    for name in sorted(package_dirs, key=AGENT_PACKAGES.index):
        log.info(f'Building {name} wheel...')
        _build_wheel(package_dirs[name], wheels_dir)
    built = {wheel.name.split('-')[0]: wheel for wheel in wheels_dir.glob('*.whl')}
    log.info(f'Wheels built in {wheels_dir}: {", ".join(sorted(p.name for p in built.values()))}')
    return built


def runtime_copy_stale(source: Path, target: Path) -> bool:
    """True if the cached copy's contents differ from the agent sources.

    Compared by content, not mtime: building a wheel rewrites the copy's
    pyproject.toml, which made the copy look newer than any later source edit.
    """
    return source_hash(source) != source_hash(target)


def ensure_vm_runtime(vm_runtime_dir: Path, sources: dict[str, Path]) -> None:
    """
    Make ``vm_runtime_dir`` hold current copies of the agent packages and their wheels.

    ``sources`` maps package name to its installed sources. The copies are
    refreshed when missing or stale, and the wheels rebuilt when their
    content-hash version no longer matches. A failed build is logged, not
    raised: without wheels the guest installs the agent from the copied sources.
    """
    targets = {name: vm_runtime_dir / name for name in sources}
    if not vm_runtime_dir.exists():
        log.info("Creating VM runtime directory for first time")
        needs_update = True
    elif not all(target.exists() for target in targets.values()):
        log.info("VM runtime directory incomplete, updating")
        needs_update = True
    else:
        needs_update = any(runtime_copy_stale(sources[name], targets[name]) for name in sources)
        if needs_update:
            log.info("Agent sources changed since the cached runtime was copied, updating")

    if needs_update:
        if vm_runtime_dir.exists():
            shutil.rmtree(vm_runtime_dir)
        vm_runtime_dir.mkdir(parents=True)
        for name, source in sources.items():
            log.info(f"Copying {name} from {source} to {targets[name]}")
            shutil.copytree(source, targets[name], dirs_exist_ok=True)
        log.info("VM runtime directory ready")

    # Wheels carry a content-hash version, so this also catches edits that
    # mtimes miss and tells the guest-side version check to reinstall.
    wheels_dir = vm_runtime_dir / 'wheels'
    if wheels_up_to_date(targets, wheels_dir):
        log.info("Wheels are up-to-date - skipping build")
        return
    try:
        build_agent_wheels(targets, wheels_dir)
    except subprocess.CalledProcessError as e:
        log.warning(f"Wheel build failed: {e.stderr.decode() if e.stderr else str(e)}")
        log.warning("Falling back to editable install mode (wheels will not be available)")
