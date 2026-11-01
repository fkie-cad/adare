#!/usr/bin/env python3
"""Inventory of the places where playbooks, environments and test sets need a guest component.

For every playbook under the given roots it counts action types, classifies each ``command:``
action (and each environment installation) with the host-side backend's CommandPlanner, and
classifies every test function used by its host-mode category. Output is JSON on stdout
(``--markdown`` prints the tables used in docs/guide/hostside-backend.rst).

    python scripts/hostside_inventory.py --root paper/experiments --root ../projects/Tproj1/experiments \
        --env-dir ~/.adare/state/environments --markdown
"""

from __future__ import annotations

import argparse
import collections
import json
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'adare'))

from adare.backend.hostside.commands import CommandPlanner  # noqa: E402


def _function_categories() -> dict[str, str]:
    from adare.config.configdirectory import STATE_DIR
    from adarelib.testset.testfunction import import_basictest_subclasses

    out: dict[str, str] = {}
    path = STATE_DIR / 'testfunctions'
    if not path.exists():
        return out
    for collection, funcs in import_basictest_subclasses(directory=path).items():
        if isinstance(funcs, dict):
            for name, cls in funcs.items():
                cat = getattr(cls, 'host_mode_category', None)
                out[f'{collection}.{name}'] = getattr(cat, 'value', str(cat))
    return out


def _render(text: str, variables: dict[str, str]) -> str:
    """Render ``{{ var }}`` with the playbook's own variables and the automatic ``adare_*`` ones."""
    import jinja2

    env = jinja2.Environment(undefined=jinja2.ChainableUndefined)
    for _ in range(3):
        try:
            rendered = env.from_string(text).render(**variables)
        except jinja2.TemplateError:  # custom filters of the registry (e.g. ``| format``) are not available here
            return text
        if rendered == text:
            break
        text = rendered
    return text


def _variables(doc: dict) -> dict[str, str]:
    from adarelib.common.automatic_variables import AutomaticVariables

    auto = AutomaticVariables.get_automatic_variables('linux', 'adare')
    ctx = {k: str(v.value) for k, v in auto.variables.items()}
    for name, spec in (doc.get('variables') or {}).items():
        value = spec.get('value') if isinstance(spec, dict) else spec
        if value is not None:
            ctx[name] = str(value)
    return ctx


def _load(path: Path):
    try:
        return yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError):
        return None


def _scan_playbooks(roots: list[Path], planner: CommandPlanner, categories: dict[str, str]) -> dict:
    actions: collections.Counter = collections.Counter()
    commands: collections.Counter = collections.Counter()
    command_examples: dict[str, list[str]] = collections.defaultdict(list)
    functions: collections.Counter = collections.Counter()
    playbooks = with_commands = 0
    for root in roots:
        for path in sorted(root.rglob('playbook.yml')):
            if '/run/' in str(path):
                continue
            doc = _load(path)
            if not isinstance(doc, dict):
                continue
            playbooks += 1
            variables = _variables(doc)
            has_cmd = False
            for item in doc.get('actions') or []:
                if not isinstance(item, dict) or not item:
                    continue
                kind = next(iter(item))
                actions[kind] += 1
                if kind != 'command':
                    continue
                has_cmd = True
                body = item['command']
                text = _render(body if isinstance(body, str) else str(body.get('command', '')), variables)
                cls = _classify(planner, text, body if isinstance(body, dict) else {})
                commands[cls] += 1
                if len(command_examples[cls]) < 4 and text not in command_examples[cls]:
                    command_examples[cls].append(text[:110])
            with_commands += has_cmd
            for test in doc.get('tests') or []:
                if isinstance(test, dict) and test.get('function'):
                    functions[test['function']] += 1
    by_category: collections.Counter = collections.Counter()
    for fn, n in functions.items():
        by_category[categories.get(fn, 'unknown')] += n
    return {
        'playbooks': playbooks,
        'playbooks_with_commands': with_commands,
        'actions': dict(actions.most_common()),
        'pull_actions': actions['pull'],
        'command_classes': dict(commands),
        'command_examples': command_examples,
        'test_functions': dict(functions.most_common()),
        'test_functions_by_host_mode_category': dict(by_category),
        'unknown_test_functions': {fn: n for fn, n in functions.items() if fn not in categories},
    }


def _scan_environments(env_dirs: list[Path], planner: CommandPlanner) -> dict:
    installs: collections.Counter = collections.Counter()
    examples: dict[str, list[str]] = collections.defaultdict(list)
    for env_dir in env_dirs:
        for path in sorted(env_dir.glob('*.yml')):
            doc = _load(path)
            if not isinstance(doc, dict):
                continue
            for inst in doc.get('postsetupinstallations') or []:
                text = inst.get('command', '') if isinstance(inst, dict) else str(inst)
                cls = _classify(planner, text, {'shell': True, 'admin': True})
                installs[cls] += 1
                if len(examples[cls]) < 3 and text[:100] not in examples[cls]:
                    examples[cls].append(text[:100])
    return {'environment_installations_by_class': dict(installs), 'environment_installation_examples': examples}


def scan(roots: list[Path], env_dirs: list[Path]) -> dict:
    planner = CommandPlanner(users={'adare': (1000, 1000)}, now=1.0)
    return {**_scan_playbooks(roots, planner, _function_categories()), **_scan_environments(env_dirs, planner)}


_WINDOWS = re.compile(r'(Get-|New-Item|Copy-Item|Remove-Item|Start-Process|\$\w+\s*=|[cC]:[\\/]|^r\")')


def _classify(planner: CommandPlanner, text: str, body: dict) -> str:
    """``a``/``b``/``c``/``d``; ``d-windows`` for PowerShell / Windows-path commands (out of scope here)."""
    plan = planner.plan(text, shell=bool(body.get('shell')), admin=bool(body.get('admin')), cwd=body.get('cwd') or None)
    if plan.category == 'd' and _WINDOWS.search(text):
        return 'd-windows'
    return plan.category


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--root', action='append', type=Path, required=True)
    ap.add_argument('--env-dir', action='append', type=Path, default=[])
    ap.add_argument('--markdown', action='store_true')
    args = ap.parse_args()
    result = scan(args.root, args.env_dir)
    if not args.markdown:
        print(json.dumps(result, indent=2, default=dict))
        return
    print(f"playbooks scanned: {result['playbooks']} ({result['playbooks_with_commands']} use `command:`)")
    print('\nactions:', ', '.join(f'{k}={v}' for k, v in result['actions'].items()))
    print('\ncommand classes (a provision, b GUI, c offline-stageable, d needs guest):', result['command_classes'])
    for cls, ex in result['command_examples'].items():
        print(f'  [{cls}]', *ex, sep='\n      ')
    print('\ntest functions by host-mode category:', result['test_functions_by_host_mode_category'])
    print('environment installations by class:', result['environment_installations_by_class'])


if __name__ == '__main__':
    main()
