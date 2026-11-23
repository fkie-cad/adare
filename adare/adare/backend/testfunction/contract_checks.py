"""Consistency checks of testfunction contracts against the code and ``library.yaml``.

Used by ``adare test validate`` (advisory, for any collection) and by the unit suite (strict,
for the bundled collections). A contract that says something the code or the vocabulary does
not know is worse than none: an agent trusts it.
"""

from pathlib import Path
from typing import Any

from adare.backend.testfunction.catalog import CatalogEntry, find, parse_collection
from adare.backend.testfunction.contract import (
    CONTRACT_FILE,
    Contract,
    ContractError,
    Library,
    load_library,
    read_contract_file,
)

# A file test (one that reads ``dst``) must say whether it reads archive members and globs.
_FILE_CATEGORIES = ('FILE_BASED', 'FILE_CONTENT')
_DECLARE_FOR_DST = ('archive_dst', 'glob_dst')
# A parameter that is the feature itself: the function must list that feature.
_FEATURE_PARAMS = (('expected_count', 'count_comparison'), ('value_decode', 'value_decode'), ('other_dst', 'other_dst'))


def _literal(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool)) and not (isinstance(value, str) and '{{' in value)


def _vocabulary_problems(where: str, contract: Contract, library: Library) -> list[str]:
    problems = []
    for kind, values, vocabulary in (
        ('asserts', contract.asserts, library.asserts),
        ('formats', contract.formats, library.formats),
        ('features', contract.features, library.features),
        ('unsupported', tuple(contract.unsupported), library.features),
    ):
        unknown = [v for v in values if v not in vocabulary]
        if unknown:
            problems.append(f'{where}: unknown {kind} {", ".join(unknown)} (see library.yaml)')
    if not contract.asserts:
        problems.append(f'{where}: no `asserts:`')
    both = set(contract.features) & set(contract.unsupported)
    if both:
        problems.append(f'{where}: {", ".join(sorted(both))} both supported and unsupported')
    return problems


def _declaration_problems(entry: CatalogEntry, contract: Contract) -> list[str]:
    """Features a function's signature implies must be declared (supported or not)."""
    problems = []
    params = {p.name for p in entry.params}
    if 'dst' in params and entry.category in _FILE_CATEGORIES:
        for feature in _DECLARE_FOR_DST:
            if feature not in contract.features and feature not in contract.unsupported:
                problems.append(
                    f'{entry.dotnotation}: reads dst but does not declare `{feature}` (features or unsupported)'
                )
    for param, feature in _FEATURE_PARAMS:
        if param in params and feature not in contract.features:
            problems.append(f'{entry.dotnotation}: has {param} but not the `{feature}` feature')
    return problems


def _redirect_problems(entry: CatalogEntry, contract: Contract, entries: list[CatalogEntry]) -> list[str]:
    problems = []
    for redirect in (*contract.not_for, *contract.related):
        target = find(entries, redirect.use)
        if target is None:
            problems.append(f'{entry.dotnotation}: `use: {redirect.use}` is no known testfunction')
        elif target.dotnotation == entry.dotnotation:
            problems.append(f'{entry.dotnotation}: `use: {redirect.use}` points at itself')
    return problems


def _choice_problems(entry: CatalogEntry, contract: Contract) -> list[str]:
    problems = []
    params = {p.name: p for p in entry.params}
    for name, allowed in contract.choices.items():
        param = params.get(name)
        if param is None:
            problems.append(f'{entry.dotnotation}: choices for unknown parameter "{name}"')
        elif not param.required and param.default is not None and param.default not in allowed:
            problems.append(f'{entry.dotnotation}: default {param.default!r} of "{name}" is not in its choices')
    return problems


def _example_problems(entry: CatalogEntry, contract: Contract) -> list[str]:
    problems = []
    if not any(e.expect == 'passed' for e in contract.examples):
        problems.append(f'{entry.dotnotation}: no example with `expect: passed`')
    params = {p.name for p in entry.params}
    required = [p.name for p in entry.params if p.required or p.default == '']
    for example in contract.examples:
        label = f'{entry.dotnotation} example "{example.title}"'
        for name, value in example.parameter.items():
            if name not in params:
                problems.append(f'{label}: unknown parameter "{name}"')
            elif (
                example.expect != 'error'  # an error example may show a refused value
                and name in contract.choices
                and _literal(value)
                and value not in contract.choices[name]
            ):
                problems.append(f'{label}: {name}={value!r} is not one of {list(contract.choices[name])}')
        missing = [name for name in required if name not in example.parameter]
        if missing:
            problems.append(f'{label}: missing required parameter(s) {", ".join(missing)}')
    return problems


def entry_problems(entry: CatalogEntry, contract: Contract, library: Library, entries: list[CatalogEntry]) -> list[str]:
    """Problems of one function's contract (empty when it is consistent)."""
    return [
        *_vocabulary_problems(entry.dotnotation, contract, library),
        *_declaration_problems(entry, contract),
        *_redirect_problems(entry, contract, entries),
        *_choice_problems(entry, contract),
        *_example_problems(entry, contract),
    ]


def collection_problems(
    collection_py: Path, entries: list[CatalogEntry] | None = None, library: Library | None = None
) -> list[str]:
    """Problems of the ``contract.yaml`` next to a collection file (none without one)."""
    path = collection_py.parent / CONTRACT_FILE
    if not path.is_file():
        return []
    try:
        _, contracts = read_contract_file(path)
    except (OSError, ContractError) as e:
        return [str(e)]
    own = parse_collection(collection_py, installed=False)
    if entries is None:
        from adare.backend.testfunction.catalog import load_catalog

        entries = load_catalog()
    known = {e.dotnotation: e for e in entries} | {e.dotnotation: e for e in own}
    library = library or load_library()
    problems = []
    by_name = {e.name.split('.')[-1]: e for e in own}
    for name in contracts:
        if name not in by_name:
            problems.append(f'{path.name}: "{name}" is no testfunction of {collection_py.stem}')
    for name, contract in contracts.items():
        if name in by_name:
            problems += entry_problems(by_name[name], contract, library, list(known.values()))
    return problems
