#!/usr/bin/env python3
"""Repository hygiene checks for CI (``make ci-hygiene``). Standard library only.

The pre-commit hooks guard the same things, but only for what is being committed
(``check-added-large-files`` and ``check-merge-conflict`` do nothing under
``--all-files`` outside a commit or merge), and nobody is forced to install them. So
CI checks the tracked tree here:

- **pins**: ruff and mypy are pinned exactly in the workspace ``lint`` group
  (``pyproject.toml``), mirrored in ``adare/pyproject.toml``; ruff is pinned twice more
  in ``.pre-commit-config.yaml`` (the ``ruff-pre-commit`` rev and the ratchet hook's
  ``additional_dependencies``). A Dependabot bump moves only one of them.
- **large files**: no tracked file over ``MAX_KB`` (the pre-commit limit), except the
  ones listed in ``LARGE_FILE_ALLOWLIST``.
- **conflict markers**: no ``<<<<<<< `` / ``>>>>>>> `` line (``=======`` alone is an
  RST heading, so it is not a marker here).
- **private keys**: no PEM/PuTTY/OpenVPN private-key header (the
  ``detect-private-key`` patterns).

gitleaks runs separately (``make ci-hygiene``), pinned to the pre-commit rev.
"""

import re
import subprocess
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ('ruff', 'mypy')
MAX_KB = 2048  # same as check-added-large-files --maxkb in .pre-commit-config.yaml
# Committed before the limit applied in CI. Do not add to this: large media belongs
# in a release asset or an external download.
LARGE_FILE_ALLOWLIST = frozenset(
    {
        'adare/appdata/examples/experiments/test_windows_admin/shared/tools/RBCmd.exe',
        'adare/appdata/examples/experiments/win_deletefile/shared/tools/RBCmd.exe',
        'docsrc/source/_static/img/structure.png',
        'paper/demo/ubuntu2204.mp4',
        'paper/demo/windows11.mp4',
    }
)
CONFLICT_MARKER = re.compile(rb'^(<<<<<<<|>>>>>>>) ', re.MULTILINE)
PRIVATE_KEY_HEADERS = (
    b'BEGIN RSA PRIVATE KEY',
    b'BEGIN DSA PRIVATE KEY',
    b'BEGIN EC PRIVATE KEY',
    b'BEGIN OPENSSH PRIVATE KEY',
    b'BEGIN PRIVATE KEY',
    b'PuTTY-User-Key-File-2',
    b'BEGIN SSH2 ENCRYPTED PRIVATE KEY',
    b'BEGIN PGP PRIVATE KEY BLOCK',
    b'BEGIN ENCRYPTED PRIVATE KEY',
    b'BEGIN OpenVPN Static key V1',
)
# Holds the key headers above as patterns (its tests build them at runtime).
CONTENT_ALLOWLIST = frozenset({'scripts/ci_hygiene.py'})


def lint_pins(pyproject: Path) -> dict[str, str]:
    """``{tool: version}`` for the exact ``tool==version`` pins in the ``lint`` group."""
    with pyproject.open('rb') as fh:
        group = tomllib.load(fh).get('dependency-groups', {}).get('lint', [])
    pins = {}
    for spec in group:
        if isinstance(spec, str) and (m := re.fullmatch(r'([A-Za-z0-9_.-]+)==([^\s;]+)', spec.strip())):
            pins[m[1].lower()] = m[2]
    return pins


def precommit_ruff_pins(config: str) -> list[tuple[str, str]]:
    """``(where, version)`` for every ruff pin in the pre-commit config."""
    pins = []
    rev = re.search(r'repo:\s*https://github\.com/astral-sh/ruff-pre-commit\s*\n\s*rev:\s*[\'"]?v?([^\s\'"#]+)', config)
    if rev:
        pins.append(('.pre-commit-config.yaml ruff-pre-commit rev', rev[1]))
    for m in re.finditer(r'[\'"]ruff==([^\'"\s]+)[\'"]', config):
        pins.append(('.pre-commit-config.yaml additional_dependencies', m[1]))
    return pins


def pin_drift(root: Path) -> list[str]:
    workspace = lint_pins(root / 'pyproject.toml')
    problems = [f'pyproject.toml lint group does not pin {tool} exactly' for tool in TOOLS if tool not in workspace]
    mirror = lint_pins(root / 'adare' / 'pyproject.toml')
    for tool in TOOLS:
        if tool in workspace and mirror.get(tool) != workspace[tool]:
            problems.append(
                f'adare/pyproject.toml lint group: {tool}=={mirror.get(tool)}, workspace: {workspace[tool]}'
            )
    ruff_pins = precommit_ruff_pins((root / '.pre-commit-config.yaml').read_text(encoding='utf-8'))
    if not ruff_pins:
        problems.append('.pre-commit-config.yaml: no ruff pin found (ruff-pre-commit rev)')
    for where, version in ruff_pins:
        if 'ruff' in workspace and version != workspace['ruff']:
            problems.append(f'{where}: ruff {version}, workspace: {workspace["ruff"]}')
    if problems:
        problems.append('set every pin to the pyproject.toml lint group (then `make lint-baseline` if counts moved)')
    return problems


def tracked_files(root: Path) -> list[str]:
    out = subprocess.run(['git', 'ls-files', '-z'], cwd=root, capture_output=True, check=True).stdout
    return [name for name in out.decode('utf-8', 'surrogateescape').split('\0') if name]


def large_files(root: Path, files: list[str]) -> list[str]:
    problems = []
    for rel in files:
        path = root / rel
        if rel in LARGE_FILE_ALLOWLIST or path.is_symlink() or not path.is_file():
            continue
        size_kb = path.stat().st_size // 1024
        if size_kb > MAX_KB:
            problems.append(f'{rel}: {size_kb} KB is over {MAX_KB} KB')
    return problems


def content_problems(root: Path, files: list[str]) -> list[str]:
    problems = []
    for rel in files:
        path = root / rel
        if rel in CONTENT_ALLOWLIST or path.is_symlink() or not path.is_file():
            continue
        data = path.read_bytes()
        if b'\0' in data[:8192]:  # binary
            continue
        if m := CONFLICT_MARKER.search(data):
            line = data.count(b'\n', 0, m.start()) + 1
            problems.append(f'{rel}:{line}: merge conflict marker')
        problems.extend(f'{rel}: private key ({header.decode()})' for header in PRIVATE_KEY_HEADERS if header in data)
    return problems


def run_checks(root: Path) -> dict[str, list[str]]:
    files = tracked_files(root)
    checks: dict[str, Callable[[], list[str]]] = {
        'lint-tool pins': lambda: pin_drift(root),
        'large files': lambda: large_files(root, files),
        'file contents': lambda: content_problems(root, files),
    }
    return {name: check() for name, check in checks.items()}


def main() -> int:
    failed = False
    for name, problems in run_checks(ROOT).items():
        if problems:
            failed = True
            print(f'{name}: FAILED', file=sys.stderr)
            for problem in problems:
                print(f'  - {problem}', file=sys.stderr)
        else:
            print(f'{name}: ok')
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
