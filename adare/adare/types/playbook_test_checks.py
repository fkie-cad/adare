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


def _check_controls(tests: list[dict], names: list, refs: list[str]) -> list[str]:
    """``controls:`` must name defined tests, not form a cycle, and run before the test they control."""
    errors = []
    graph: dict[str, list[str]] = {}
    position = {ref: i for i, ref in reversed(list(enumerate(refs)))}  # first `- test:` of each name
    for test in tests:
        name, controls = test.get('name'), test.get('controls')
        if controls is None or not isinstance(name, str):
            continue
        if not isinstance(controls, list) or not all(isinstance(c, str) for c in controls):
            errors.append(f'test "{name}": `controls:` must be a list of test names')
            continue
        graph[name] = controls
        for control in controls:
            if control == name:
                errors.append(f'test "{name}": cannot be its own control')
            elif control not in names:
                errors.append(f'test "{name}": control "{control}" is not in `tests:`{_suggest(control, names)}')
            elif control not in position:
                errors.append(f'test "{name}": control "{control}" never runs (no `- test: {control}` action)')
            elif name in position and position[control] > position[name]:
                errors.append(f'test "{name}": control "{control}" runs after the test it controls')
    errors += _control_cycles(graph)
    return errors


def _control_cycles(graph: dict[str, list[str]]) -> list[str]:
    """One error per ``controls:`` cycle (a -> b -> a)."""
    errors, done = [], set()

    def visit(node: str, path: list[str]) -> None:
        if node in path:
            cycle = path[path.index(node) :] + [node]
            errors.append(f'`controls:` cycle: {" -> ".join(cycle)}')
            return
        if node in done:
            return
        for control in graph.get(node, []):
            if control != node:
                visit(control, path + [node])
        done.add(node)

    for node in graph:
        visit(node, [])
    return errors


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
    refs = _test_refs(data.get('actions'))
    for ref in dict.fromkeys(refs):
        if ref not in names:
            errors.append(f'`- test: {ref}` refers to no entry in `tests:`{_suggest(ref, names)}')
    errors += _check_controls(tests, names, refs)

    if not tests:
        return errors, []
    if entries is None:
        from adare.backend.testfunction.catalog import load_catalog

        entries = load_catalog()
    warnings = [w for t in tests for w in _check_against_catalog(t, entries)]
    return errors, warnings
