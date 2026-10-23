"""Static checks of a playbook's ``tests:`` block against its actions and the testfunction catalog.

Used by ``adare exp playbook validate`` / ``playbook_validate`` (not by the run-time
parser). Errors are structural mistakes that cannot work (a ``- test:`` naming an
undefined test, duplicate test names). Catalog findings are warnings: the catalog
reflects this machine's collections, which may differ from where the playbook runs.
"""

import difflib
from typing import Any

import yaml


def _test_refs(node: Any) -> list[str]:
    """Names referenced by ``- test:`` actions anywhere in an actions tree (blocks, loops)."""
    refs: list[str] = []
    if isinstance(node, list):
        for item in node:
            refs += _test_refs(item)
    elif isinstance(node, dict):
        for key, value in node.items():
            if key == 'test' and isinstance(value, str):
                refs.append(value)
            elif key == 'test' and isinstance(value, dict) and isinstance(value.get('name'), str):
                refs.append(value['name'])
            else:
                refs += _test_refs(value)
    return refs


def _suggest(name: str, choices: list[str]) -> str:
    close = difflib.get_close_matches(name, choices, n=3, cutoff=0.6)
    return f' (did you mean: {", ".join(close)}?)' if close else ''


def _check_against_catalog(test: dict, entries: list) -> list[str]:
    from adare.backend.testfunction.catalog import close_matches, find

    name, function = test.get('name', '?'), test.get('function')
    if not isinstance(function, str):
        return [f'test "{name}": missing `function:` (find one with `adare test search "<goal>"`)']
    entry = find(entries, function)
    if entry is None:
        candidates = ', '.join(e.dotnotation for e in close_matches(entries, function))
        hint = f' (did you mean: {candidates}?)' if candidates else ' (see `adare test search`)'
        return [f'test "{name}": unknown testfunction "{function}"{hint}']

    warnings = []
    given = test.get('parameter') or {}
    known = [p.name for p in entry.params]
    if isinstance(given, dict):
        for param in given:
            if param not in known:
                warnings.append(
                    f'test "{name}": {function} has no parameter "{param}"{_suggest(param, known)}'
                    f' — signature: {entry.signature()}'
                )
        for p in entry.params:
            if p.required and p.name not in given:
                warnings.append(f'test "{name}": missing required parameter "{p.name}" for {function}')
    return warnings


def check_playbook_tests(playbook_yaml: str, entries: list | None = None) -> tuple[list[str], list[str]]:
    """Return ``(errors, warnings)`` for the playbook's tests; unparsable YAML yields none."""
    try:
        data = yaml.safe_load(playbook_yaml)
    except yaml.YAMLError:
        return [], []  # the schema validator reports parse errors
    if not isinstance(data, dict):
        return [], []

    tests = [t for t in (data.get('tests') or []) if isinstance(t, dict)]
    names = [t.get('name') for t in tests if isinstance(t.get('name'), str)]
    errors = [f'duplicate test name "{n}" in `tests:`' for n in sorted({n for n in names if names.count(n) > 1})]
    for ref in dict.fromkeys(_test_refs(data.get('actions'))):
        if ref not in names:
            errors.append(f'`- test: {ref}` refers to no entry in `tests:`{_suggest(ref, names)}')

    if not tests:
        return errors, []
    if entries is None:
        from adare.backend.testfunction.catalog import load_catalog

        entries = load_catalog()
    warnings = [w for t in tests for w in _check_against_catalog(t, entries)]
    return errors, warnings
