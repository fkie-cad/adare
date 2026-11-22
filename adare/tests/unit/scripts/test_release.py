"""scripts/release.py: release-tag parsing, version and CHANGELOG checks, the main check."""

import subprocess
from pathlib import Path

import pytest

from .conftest import load_script

pytestmark = pytest.mark.unit

release = load_script('release')

CHANGELOG = """# Changelog

## [Unreleased]

### Added
- next thing

## [adarelib 0.3.0] - 2026-11-22

### Changed
- the contract

## [adare 0.1.1] - 2026-11-01

### Fixed
- a bug
"""


@pytest.mark.parametrize(
    ('tag', 'package', 'version'),
    [
        ('adare-v0.1.1', 'adare', '0.1.1'),
        ('adarelib-v0.3.0', 'adarelib', '0.3.0'),
        ('adare-cv-server-v1.2.3', 'adare-cv-server', '1.2.3'),
        ('adarevm-v0.2.0rc1', 'adarevm', '0.2.0rc1'),
    ],
)
def test_parse_tag(tag, package, version):
    assert release.parse_tag(tag) == release.Tag(package, version)


@pytest.mark.parametrize('tag', ['v0.1.1', 'adare-0.1.1', 'adare-v1.2', 'adare-vfoo', 'Adare-v0.1.1'])
def test_parse_tag_rejects_bad_format(tag):
    with pytest.raises(release.ReleaseError, match='is not <package>-v'):
        release.parse_tag(tag)


def test_parse_tag_rejects_unknown_package():
    with pytest.raises(release.ReleaseError, match="unknown package 'adareweb'"):
        release.parse_tag('adareweb-v0.1.0')


def test_changelog_notes_extracts_the_section_body():
    assert release.changelog_notes(CHANGELOG, 'adarelib', '0.3.0') == '### Changed\n- the contract\n'
    assert release.changelog_notes(CHANGELOG, 'adare', '0.1.1') == '### Fixed\n- a bug\n'


def test_changelog_notes_needs_the_exact_section():
    with pytest.raises(release.ReleaseError, match=r'no "## \[adare 0.1.2\]'):
        release.changelog_notes(CHANGELOG, 'adare', '0.1.2')
    # "adare 0.1.1" must not match "adare 0.1.10" or another package's section
    with pytest.raises(release.ReleaseError):
        release.changelog_notes(CHANGELOG.replace('[adare 0.1.1]', '[adare 0.1.10]'), 'adare', '0.1.1')


def test_changelog_notes_rejects_an_empty_section():
    text = CHANGELOG.replace('### Changed\n- the contract\n', '')
    with pytest.raises(release.ReleaseError, match='is empty'):
        release.changelog_notes(text, 'adarelib', '0.3.0')


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(['git', *args], cwd=repo, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    """A workspace with adare 0.1.1, a main branch and a dev commit ahead of it."""
    repo = tmp_path / 'repo'
    (repo / 'adare').mkdir(parents=True)
    (repo / 'adare' / 'pyproject.toml').write_text('[project]\nname = "adare"\nversion = "0.1.1"\n')
    (repo / 'CHANGELOG.md').write_text(CHANGELOG)
    _git(repo, 'init', '-q', '-b', 'main')
    _git(repo, 'add', '.')
    _git(repo, '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', 'commit', '-qm', 'release')
    return repo


def _commit_on_dev(repo: Path) -> None:
    _git(repo, 'checkout', '-qb', 'dev')
    (repo / 'x').write_text('x')
    _git(repo, 'add', 'x')
    _git(repo, '-c', 'user.name=t', '-c', 'user.email=t@example.invalid', 'commit', '-qm', 'dev work')


def test_check_passes_for_a_tag_on_main(repo):
    _git(repo, 'tag', 'adare-v0.1.1')
    _commit_on_dev(repo)  # HEAD moved on; the tag's commit is what counts
    tag, notes, errors = release.check(repo, 'adare-v0.1.1', 'main')
    assert errors == []
    assert tag == release.Tag('adare', '0.1.1')
    assert notes == '### Fixed\n- a bug\n'


def test_check_before_tagging_uses_head(repo):
    assert release.check(repo, 'adare-v0.1.1', 'main')[2] == []
    _commit_on_dev(repo)
    errors = release.check(repo, 'adare-v0.1.1', 'main')[2]
    assert len(errors) == 1
    assert 'HEAD (tag not created yet)' in errors[0]
    assert 'is not on main' in errors[0]


def test_check_reports_every_problem(repo):
    _commit_on_dev(repo)
    _git(repo, 'tag', 'adare-v9.9.9')
    _, notes, errors = release.check(repo, 'adare-v9.9.9', 'main')
    assert notes == ''
    assert len(errors) == 3
    assert 'has version 0.1.1, the tag says 9.9.9' in errors[0]
    assert 'no "## [adare 9.9.9]' in errors[1]
    assert 'tag adare-v9.9.9' in errors[2]
    assert 'is not on main' in errors[2]


def test_check_needs_the_main_branch(repo):
    errors = release.check(repo, 'adare-v0.1.1', 'origin/main')[2]
    assert errors == ['origin/main not found (fetch it, or check out with fetch-depth: 0)']


def test_main_writes_notes_and_github_output(repo, tmp_path, monkeypatch):
    output = tmp_path / 'github_output'
    notes = tmp_path / 'notes.md'
    monkeypatch.setattr(release, 'ROOT', repo)
    monkeypatch.setenv('GITHUB_OUTPUT', str(output))
    assert release.main(['check', 'adare-v0.1.1', '--main', 'main', '--notes', str(notes)]) == 0
    assert notes.read_text() == '### Fixed\n- a bug\n'
    assert output.read_text() == 'package=adare\nversion=0.1.1\n'


def test_main_fails_without_writing_notes(repo, tmp_path, monkeypatch, capsys):
    notes = tmp_path / 'notes.md'
    monkeypatch.setattr(release, 'ROOT', repo)
    monkeypatch.delenv('GITHUB_OUTPUT', raising=False)
    assert release.main(['check', 'adare-v0.1.2', '--main', 'main', '--notes', str(notes)]) == 1
    assert not notes.exists()
    assert 'has version 0.1.1, the tag says 0.1.2' in capsys.readouterr().err
    assert release.main(['check', 'nonsense', '--main', 'main', '--notes', str(notes)]) == 1
