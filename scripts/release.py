#!/usr/bin/env python3
"""Release-tag checks: ``scripts/release.py check <package>-v<version>``.

A release tag is ``<package>-v<version>`` (e.g. ``adarelib-v0.2.0``) on a commit of
``main``. ``check`` verifies, and reports every problem at once:

- ``<package>`` is a workspace package (``PACKAGES``);
- ``<package>/pyproject.toml`` has exactly ``<version>``;
- ``CHANGELOG.md`` has a non-empty ``## [<package> <version>]`` section, whose body is
  written to ``--notes`` (the GitHub Release text);
- the tagged commit is on ``--main`` (default ``origin/main``). Before tagging, when
  the tag does not exist yet, HEAD is checked instead.

Run through ``make release-check TAG=...`` (CI: release.yml). In GitHub Actions the
package and version are also written to ``$GITHUB_OUTPUT``. Standard library only.
"""

import argparse
import os
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = ('adare', 'adarevm', 'adarelib', 'adare-cv-server')
TAG_RE = re.compile(r'^(?P<package>[a-z][a-z0-9-]*?)-v(?P<version>\d+\.\d+\.\d+\S*)$')


class ReleaseError(Exception):
    pass


@dataclass(frozen=True)
class Tag:
    package: str
    version: str


def parse_tag(tag: str) -> Tag:
    """Split ``<package>-v<version>``; the package must be a workspace package."""
    match = TAG_RE.match(tag)
    if not match:
        raise ReleaseError(f'tag {tag!r} is not <package>-v<major>.<minor>.<patch>')
    package = match['package']
    if package not in PACKAGES:
        raise ReleaseError(f'tag {tag!r}: unknown package {package!r} (one of {", ".join(PACKAGES)})')
    return Tag(package, match['version'])


def package_version(root: Path, package: str) -> str:
    with (root / package / 'pyproject.toml').open('rb') as fh:
        return tomllib.load(fh)['project']['version']


def changelog_notes(changelog: str, package: str, version: str) -> str:
    """Body of the ``## [<package> <version>]`` section, up to the next ``## `` heading."""
    heading = re.compile(rf'^## \[{re.escape(package)} {re.escape(version)}\](?:\s|$)')
    lines = changelog.splitlines()
    start = next((i for i, line in enumerate(lines) if heading.match(line)), None)
    if start is None:
        raise ReleaseError(f'CHANGELOG.md has no "## [{package} {version}] - <date>" section')
    body = []
    for line in lines[start + 1 :]:
        if line.startswith('## '):
            break
        body.append(line)
    notes = '\n'.join(body).strip()
    if not notes:
        raise ReleaseError(f'CHANGELOG.md section [{package} {version}] is empty')
    return notes + '\n'


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(['git', *args], cwd=root, capture_output=True, text=True, check=False)


def tagged_commit(root: Path, tag: str) -> tuple[str, str]:
    """``(sha, what)``: the tag's commit, or HEAD's when the tag does not exist yet."""
    proc = _git(root, 'rev-parse', '--verify', '--quiet', f'refs/tags/{tag}^{{commit}}')
    if proc.returncode == 0:
        return proc.stdout.strip(), f'tag {tag}'
    head = _git(root, 'rev-parse', '--verify', 'HEAD^{commit}')
    if head.returncode != 0:
        raise ReleaseError(f'cannot resolve HEAD: {head.stderr.strip()}')
    return head.stdout.strip(), 'HEAD (tag not created yet)'


def check_on_branch(root: Path, sha: str, what: str, branch: str) -> None:
    if _git(root, 'rev-parse', '--verify', '--quiet', branch).returncode != 0:
        raise ReleaseError(f'{branch} not found (fetch it, or check out with fetch-depth: 0)')
    proc = _git(root, 'merge-base', '--is-ancestor', sha, branch)
    if proc.returncode == 1:
        raise ReleaseError(f'{what} ({sha[:12]}) is not on {branch}: release from main only')
    if proc.returncode != 0:
        raise ReleaseError(f'git merge-base failed: {proc.stderr.strip()}')


def check(root: Path, tag: str, main: str) -> tuple[Tag, str, list[str]]:
    """``(tag, notes, errors)``; ``notes`` is empty when the changelog check failed."""
    parsed = parse_tag(tag)  # nothing else can be checked without it
    errors: list[str] = []
    notes = ''

    version = package_version(root, parsed.package)
    if version != parsed.version:
        errors.append(f'{parsed.package}/pyproject.toml has version {version}, the tag says {parsed.version}')
    try:
        notes = changelog_notes((root / 'CHANGELOG.md').read_text(encoding='utf-8'), parsed.package, parsed.version)
    except ReleaseError as exc:
        errors.append(str(exc))
    try:
        sha, what = tagged_commit(root, tag)
        check_on_branch(root, sha, what, main)
    except ReleaseError as exc:
        errors.append(str(exc))
    return parsed, notes, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest='command', required=True)
    p_check = sub.add_parser('check', help='verify a release tag and extract its notes')
    p_check.add_argument('tag', help='<package>-v<version>, e.g. adarelib-v0.2.0')
    p_check.add_argument('--notes', type=Path, default=ROOT / 'release-notes.md', help='where to write the notes')
    p_check.add_argument('--main', default='origin/main', help='branch the commit must be on')
    args = parser.parse_args(argv)

    try:
        parsed, notes, errors = check(ROOT, args.tag, args.main)
    except ReleaseError as exc:
        print(f'release check failed: {exc}', file=sys.stderr)
        return 1
    if errors:
        print(f'release check failed for {args.tag}:', file=sys.stderr)
        for error in errors:
            print(f'  - {error}', file=sys.stderr)
        return 1

    args.notes.write_text(notes, encoding='utf-8')
    if github_output := os.environ.get('GITHUB_OUTPUT'):
        with open(github_output, 'a', encoding='utf-8') as fh:
            fh.write(f'package={parsed.package}\nversion={parsed.version}\n')
    print(f'{args.tag}: {parsed.package} {parsed.version} is releasable; notes in {args.notes}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
