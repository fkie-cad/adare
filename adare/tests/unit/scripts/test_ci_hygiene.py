"""scripts/ci_hygiene.py: lint-tool pin drift, large files, conflict markers, private keys."""

from pathlib import Path

import pytest

from .conftest import load_script

pytestmark = pytest.mark.unit

hygiene = load_script('ci_hygiene')

PRECOMMIT = """repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v{rev}  # keep in sync
    hooks:
      - id: ruff-format
  - repo: local
    hooks:
      - id: quality-ratchet
        additional_dependencies: ["ruff=={dep}"]
"""


def _pyproject(path: Path, ruff: str, mypy: str = '2.4.0') -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'[project]\nname = "x"\n\n[dependency-groups]\nlint = ["ruff=={ruff}", "mypy=={mypy}"]\n')


@pytest.fixture
def workspace(tmp_path):
    def make(ruff='0.15.11', mirror_ruff='0.15.11', mirror_mypy='2.4.0', rev='0.15.11', dep='0.15.11'):
        _pyproject(tmp_path / 'pyproject.toml', ruff)
        _pyproject(tmp_path / 'adare' / 'pyproject.toml', mirror_ruff, mirror_mypy)
        (tmp_path / '.pre-commit-config.yaml').write_text(PRECOMMIT.format(rev=rev, dep=dep))
        return tmp_path

    return make


def test_pins_in_sync(workspace):
    assert hygiene.pin_drift(workspace()) == []


def test_pins_in_this_repo_are_in_sync():
    assert hygiene.pin_drift(hygiene.ROOT) == []


def test_precommit_rev_drift(workspace):
    problems = hygiene.pin_drift(workspace(rev='0.16.0'))
    assert problems[0] == '.pre-commit-config.yaml ruff-pre-commit rev: ruff 0.16.0, workspace: 0.15.11'
    assert len(problems) == 2  # plus the how-to-fix line


def test_every_drifted_pin_is_named(workspace):
    problems = hygiene.pin_drift(workspace(ruff='0.16.0', mirror_mypy='2.5.0'))
    text = '\n'.join(problems)
    assert 'adare/pyproject.toml lint group: ruff==0.15.11, workspace: 0.16.0' in text
    assert 'adare/pyproject.toml lint group: mypy==2.5.0, workspace: 2.4.0' in text
    assert 'ruff-pre-commit rev: ruff 0.15.11, workspace: 0.16.0' in text
    assert 'additional_dependencies: ruff 0.15.11, workspace: 0.16.0' in text


def test_missing_precommit_ruff_is_a_problem(workspace):
    root = workspace()
    (root / '.pre-commit-config.yaml').write_text('repos: []\n')
    assert '.pre-commit-config.yaml: no ruff pin found' in hygiene.pin_drift(root)[0]


def test_large_files(tmp_path, monkeypatch):
    monkeypatch.setattr(hygiene, 'MAX_KB', 1)
    monkeypatch.setattr(hygiene, 'LARGE_FILE_ALLOWLIST', frozenset({'old.bin'}))
    for name in ('big.bin', 'old.bin'):
        (tmp_path / name).write_bytes(b'x' * 4096)
    (tmp_path / 'small.txt').write_bytes(b'x' * 100)
    files = ['big.bin', 'old.bin', 'small.txt', 'deleted.txt']
    assert hygiene.large_files(tmp_path, files) == ['big.bin: 4 KB is over 1 KB']


def test_conflict_markers_and_private_keys(tmp_path):
    marker = '<' * 7
    key = '-----BEGIN ' + 'OPENSSH PRIVATE KEY-----'
    (tmp_path / 'conflict.py').write_text(f'a = 1\n{marker} HEAD\nb = 2\n')
    (tmp_path / 'heading.rst').write_text('Title\n=======\n\ntext with <<< and >>>\n')
    (tmp_path / 'id_ed25519').write_text(f'{key}\nabc\n')
    (tmp_path / 'blob.bin').write_bytes(b'\0' + key.encode())  # binary: skipped
    files = ['conflict.py', 'heading.rst', 'id_ed25519', 'blob.bin']
    assert hygiene.content_problems(tmp_path, files) == [
        'conflict.py:2: merge conflict marker',
        'id_ed25519: private key (BEGIN OPENSSH PRIVATE KEY)',
    ]
