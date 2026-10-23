"""``adare skills install/status``: install skills without clobbering anything."""

from pathlib import Path

import pytest

from adare.backend import agent_setup
from adare.backend.agent_setup import setup, status

pytestmark = pytest.mark.unit


@pytest.fixture()
def env(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    home.mkdir()
    monkeypatch.setattr(Path, 'home', lambda: home)
    source = tmp_path / 'skills'
    for name in ('adare-a', 'adare-b'):
        (source / name).mkdir(parents=True)
        (source / name / 'SKILL.md').write_text(f'---\nname: {name}\n---\n')
    (source / 'not-adare').mkdir()
    (source / 'not-adare' / 'SKILL.md').write_text('x')
    return home, source


def _by_skill(links):
    return {link.skill: link.status for link in links}


def test_setup_links_every_adare_skill_and_is_idempotent(env):
    home, source = env
    assert _by_skill(setup(source, ('claude',))) == {'adare-a': 'linked', 'adare-b': 'linked'}
    target = home / '.claude' / 'skills' / 'adare-a'
    assert target.is_symlink() and target.resolve() == (source / 'adare-a').resolve()
    assert _by_skill(setup(source, ('claude',))) == {'adare-a': 'ok', 'adare-b': 'ok'}


def test_dry_run_changes_nothing(env):
    home, source = env
    assert _by_skill(setup(source, ('opencode',), dry_run=True)) == {'adare-a': 'linked', 'adare-b': 'linked'}
    assert not (home / '.config' / 'opencode' / 'skills').exists()


def test_foreign_links_and_real_dirs_are_left_alone_without_force(env, tmp_path):
    home, source = env
    skills = home / '.claude' / 'skills'
    skills.mkdir(parents=True)
    other = tmp_path / 'other-checkout' / 'adare-a'
    other.mkdir(parents=True)
    (skills / 'adare-a').symlink_to(other)
    (skills / 'adare-b').mkdir()  # a user's own directory
    assert _by_skill(setup(source, ('claude',))) == {'adare-a': 'foreign-link', 'adare-b': 'conflict'}
    assert (skills / 'adare-a').resolve() == other.resolve()
    assert _by_skill(setup(source, ('claude',), force=True)) == {'adare-a': 'updated', 'adare-b': 'conflict'}
    assert (skills / 'adare-a').resolve() == (source / 'adare-a').resolve()


def test_stale_links_are_repaired_and_copy_mode(env, tmp_path):
    home, source = env
    skills = home / '.claude' / 'skills'
    skills.mkdir(parents=True)
    (skills / 'adare-a').symlink_to(tmp_path / 'gone')
    links = setup(source, ('claude',), copy=True)
    assert _by_skill(links) == {'adare-a': 'updated', 'adare-b': 'copied'}
    assert (skills / 'adare-b' / 'SKILL.md').is_file() and not (skills / 'adare-b').is_symlink()
    assert _by_skill(status(source, ('claude',), ('user',))) == {'adare-a': 'ok', 'adare-b': 'ok'}


def test_project_scope_uses_cwd(env, tmp_path):
    _home, source = env
    project = tmp_path / 'proj'
    project.mkdir()
    setup(source, ('claude', 'opencode'), ('project',), cwd=project)
    assert (project / '.claude' / 'skills' / 'adare-a').is_symlink()
    assert (project / '.opencode' / 'skills' / 'adare-b').is_symlink()


def test_skills_source_finds_the_checkout():
    source = agent_setup.skills_source()
    assert source is not None and (source / 'adare-overview' / 'SKILL.md').is_file()
