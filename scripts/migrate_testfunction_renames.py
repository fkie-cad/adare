#!/usr/bin/env python3
"""Rewrite playbooks to the current testfunction and parameter names.

Uses the rename table in ``adarelib/adarelib/testset/renames.py``. Edits the YAML text in
place (comments, tags and layout are kept): renames ``function:`` values and the renamed keys
directly under a test's ``parameter:``. Without ``--write`` it only lists what it would change.

    python scripts/migrate_testfunction_renames.py PATH [PATH ...] [--write]

PATH is a playbook or a directory (searched for *.yml / *.yaml). Review the diff afterwards:
some renames also changed behaviour (see CHANGELOG, "Breaking").
"""

import argparse
import importlib.util
import re
import sys
from pathlib import Path

# loaded by path: renames.py is standard library only, so this runs with any python3
_SPEC = importlib.util.spec_from_file_location(
    'renames', Path(__file__).resolve().parents[1] / 'adarelib' / 'adarelib' / 'testset' / 'renames.py'
)
_RENAMES = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_RENAMES)
RENAMED_FUNCTIONS: dict[str, str] = _RENAMES.RENAMED_FUNCTIONS
RENAMED_PARAMETERS: dict[str, dict[str, str]] = _RENAMES.RENAMED_PARAMETERS

_FUNCTION = re.compile(r'^(?P<indent>\s*)(?P<dash>-\s+)?function:\s*(?P<quote>["\']?)(?P<name>[\w.]+)(?P=quote)')
_SKIP_DIRS = {'.git', 'node_modules', '.venv', '__pycache__'}


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(' '))


def _item_bounds(lines: list[str], at: int, key_indent: int) -> tuple[int, int]:
    """First and last+1 line of the list item (test) whose key sits at ``key_indent``."""
    start = at
    if not lines[at].lstrip().startswith('-'):
        for i in range(at - 1, -1, -1):
            text = lines[i]
            if not text.strip() or text.lstrip().startswith('#'):
                continue
            if _indent(text) < key_indent:
                start = i
                break
    end = len(lines)
    for i in range(at + 1, len(lines)):
        text = lines[i]
        if text.strip() and not text.lstrip().startswith('#') and _indent(text) < key_indent:
            end = i
            break
    return start, end


def migrate_text(text: str) -> tuple[str, list[str]]:
    """The migrated YAML text and one message per change."""
    lines = text.split('\n')
    changes: list[str] = []
    for i, line in enumerate(lines):
        m = _FUNCTION.match(line)
        if not m:
            continue
        name = m.group('name')
        qualified = name if '.' in name else f'standard.{name}'
        if qualified in RENAMED_FUNCTIONS:
            new = RENAMED_FUNCTIONS[qualified]
            lines[i] = line[: m.start('name')] + new + line[m.end('name') :]
            changes.append(f'line {i + 1}: function {name} -> {new}')
            qualified = new
        renamed = RENAMED_PARAMETERS.get(qualified)
        if not renamed:
            continue
        key_indent = len(m.group('indent')) + len(m.group('dash') or '')
        start, end = _item_bounds(lines, i, key_indent)
        for j in range(start, end):
            pm = re.match(r'^(\s*)(-\s+)?parameter:\s*$', lines[j])
            if not pm or len(pm.group(1)) + len(pm.group(2) or '') != key_indent:
                continue
            child_indent = None
            for k in range(j + 1, end):
                text = lines[k]
                if not text.strip() or text.lstrip().startswith('#'):
                    continue
                if _indent(text) <= key_indent:
                    break
                child_indent = child_indent or _indent(text)
                if _indent(text) != child_indent:
                    continue
                km = re.match(r'^(\s*)([\w]+)(\s*:)', text)
                if km and km.group(2) in renamed:
                    lines[k] = km.group(1) + renamed[km.group(2)] + text[km.end(2) :]
                    changes.append(f'line {k + 1}: {qualified} parameter {km.group(2)} -> {renamed[km.group(2)]}')
    return '\n'.join(lines), changes


def _playbooks(paths: list[str]):
    for raw in paths:
        path = Path(raw)
        if path.is_file():
            yield path
            continue
        for candidate in sorted(path.rglob('*')):
            if candidate.suffix in ('.yml', '.yaml') and not _SKIP_DIRS & set(candidate.parts):
                yield candidate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('paths', nargs='+')
    parser.add_argument('--write', action='store_true', help='change the files (default: only list changes)')
    args = parser.parse_args()
    total = 0
    for path in _playbooks(args.paths):
        try:
            text = path.read_text(encoding='utf-8')
        except (OSError, UnicodeDecodeError) as e:
            print(f'{path}: skipped ({e})', file=sys.stderr)
            continue
        new_text, changes = migrate_text(text)
        if not changes:
            continue
        total += len(changes)
        for change in changes:
            print(f'{path}: {change}')
        if args.write:
            path.write_text(new_text, encoding='utf-8')
    print(f'{total} change(s){"" if args.write else " (dry run; --write to apply)"}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
