"""Install ADARE's workflow skills for AI coding agents (``adare agent setup/status``).

The tracked ``skills/adare-*`` directories are the single source. They are
symlinked (or copied) into each agent's skill directory. Existing entries are
never clobbered silently: a real directory is left alone, and a symlink
pointing elsewhere is only re-pointed with ``force``.
"""

import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

SKILL_PREFIX = 'adare-'

# (client, scope) -> skills directory; project scope is relative to the CWD.
_TARGETS = {
    ('claude', 'user'): lambda cwd: Path.home() / '.claude' / 'skills',
    ('claude', 'project'): lambda cwd: cwd / '.claude' / 'skills',
    ('opencode', 'user'): lambda cwd: Path.home() / '.config' / 'opencode' / 'skills',
    ('opencode', 'project'): lambda cwd: cwd / '.opencode' / 'skills',
}
CLIENTS = ('claude', 'opencode')
SCOPES = ('user', 'project')


@dataclass(frozen=True)
class SkillLink:
    client: str
    scope: str
    skill: str
    target: Path
    status: str  # linked | copied | ok | updated | missing | conflict | foreign-link | stale
    detail: str = ''


def skills_source() -> Path | None:
    """The ``skills/`` dir of the source checkout, else of the appdata copy."""
    from adare.config.configdirectory import APPDATA_DIR

    for candidate in (Path(__file__).resolve().parents[3] / 'skills', APPDATA_DIR / 'adare' / 'skills'):
        if candidate.is_dir() and any(candidate.glob(f'{SKILL_PREFIX}*/SKILL.md')):
            return candidate
    return None


def available_skills(source: Path) -> list[Path]:
    return sorted(p.parent for p in source.glob(f'{SKILL_PREFIX}*/SKILL.md'))


def target_dir(client: str, scope: str, cwd: Path | None = None) -> Path:
    return _TARGETS[(client, scope)](cwd or Path.cwd())


def _classify(skill_dir: Path, target: Path) -> tuple[str, str]:
    if target.is_symlink():
        pointee = Path(target.readlink())
        if not pointee.is_absolute():
            pointee = target.parent / pointee
        if not pointee.exists():
            return 'stale', f'broken link -> {pointee}'
        if pointee.resolve() == skill_dir.resolve():
            return 'ok', ''
        return 'foreign-link', f'links to {pointee.resolve()}'
    if target.exists():
        if (target / 'SKILL.md').is_file() and (skill_dir / 'SKILL.md').is_file() and \
                (target / 'SKILL.md').read_bytes() == (skill_dir / 'SKILL.md').read_bytes():
            return 'ok', 'copy (up to date)'
        return 'conflict', 'a real directory/file is in the way (left untouched)'
    return 'missing', ''


def status(source: Path, clients=CLIENTS, scopes=SCOPES, cwd: Path | None = None) -> list[SkillLink]:
    links = []
    for client in clients:
        for scope in scopes:
            directory = target_dir(client, scope, cwd)
            for skill_dir in available_skills(source):
                state, detail = _classify(skill_dir, directory / skill_dir.name)
                links.append(SkillLink(client, scope, skill_dir.name, directory / skill_dir.name, state, detail))
    return links


def setup(source: Path, clients=CLIENTS, scopes=('user',), *, copy: bool = False, force: bool = False,
          dry_run: bool = False, cwd: Path | None = None) -> list[SkillLink]:
    """Install every skill for every (client, scope); returns what happened per skill."""
    results = []
    for link in status(source, clients, scopes, cwd):
        skill_dir = source / link.skill
        action = None
        if link.status == 'missing':
            action = 'copied' if copy else 'linked'
        elif link.status == 'stale' or (link.status == 'foreign-link' and force):
            action = 'updated'
        elif link.status == 'ok' and copy and link.target.is_symlink():
            action = 'copied'  # explicit --copy replaces our own symlink with a copy
        if action is None:
            results.append(link)
            continue
        if not dry_run:
            link.target.parent.mkdir(parents=True, exist_ok=True)
            if link.target.is_symlink():
                link.target.unlink()
            if copy:
                shutil.copytree(skill_dir, link.target)
            else:
                link.target.symlink_to(skill_dir.resolve(), target_is_directory=True)
        results.append(SkillLink(link.client, link.scope, link.skill, link.target, action,
                                 'dry run' if dry_run else link.detail))
    return results
