"""Testfunction contracts: what a function can and cannot do, in a form agents can query.

A collection's ``contract.yaml`` sits next to its ``.py`` file and states, per function,
what kind of assertion it makes, which formats and shared features it supports, which
goals it is *not* for (and what to use instead), when it returns passed / failed / error,
its limits, the allowed values of its parameters, use cases and examples. The examples
run in the unit suite, so the documentation cannot drift from the behaviour.

``library.yaml`` (in the collections root) holds what is shared by all collections: the
vocabulary of assertion kinds and formats, the cross-cutting features (archives in
``dst``, globs, ``!re``, ``!timestamp``, ordered comparison, ...) and the known gaps
(goals no testfunction covers), so a search can say "nothing does this" instead of
returning a near miss.

One source, several renderings: ``adare test search/info/feature``, the agent tools,
the skill's Markdown references and the Sphinx reference pages all read these files.
The docstring still carries the summary, "Use for:" and the ``Args:`` of each function.
"""

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

CONTRACT_FILE = 'contract.yaml'
LIBRARY_FILE = 'library.yaml'
OUTCOMES = ('passed', 'failed', 'error')


class ContractError(ValueError):
    """A contract or library file that does not follow the schema."""


@dataclass(frozen=True)
class Redirect:
    """``not_for`` (a goal this function does not cover) or ``related`` (a neighbour)."""

    use: str  # dotnotation of the function to use instead
    text: str  # the goal (not_for) or why the neighbour fits (related)


@dataclass(frozen=True)
class UseCase:
    title: str
    text: str = ''


@dataclass(frozen=True)
class Example:
    """One ``tests:`` item plus the files it reads; runnable unless ``run`` is false."""

    title: str
    parameter: dict
    expect: str = 'passed'
    files: dict = field(default_factory=dict)
    text: str = ''
    run: bool = True
    why_not_run: str = ''
    variables: dict = field(default_factory=dict)
    parameter_yaml: str = ''  # the parameter block as written (tags and flow style kept)
    parameter_display: dict = field(default_factory=dict)  # JSON-safe: tags as their YAML text


@dataclass(frozen=True)
class Contract:
    asserts: tuple[str, ...] = ()
    formats: tuple[str, ...] = ()
    features: tuple[str, ...] = ()
    unsupported: dict[str, str] = field(default_factory=dict)  # feature id -> why / what instead
    not_for: tuple[Redirect, ...] = ()
    related: tuple[Redirect, ...] = ()
    outcomes: dict[str, tuple[str, ...]] = field(default_factory=dict)  # passed/failed/error -> conditions
    limits: tuple[str, ...] = ()
    choices: dict[str, tuple] = field(default_factory=dict)  # parameter -> allowed values
    use_cases: tuple[UseCase, ...] = ()
    examples: tuple[Example, ...] = ()

    def to_dict(self) -> dict:
        return {
            'asserts': list(self.asserts),
            'formats': list(self.formats),
            'features': list(self.features),
            'unsupported': dict(self.unsupported),
            'not_for': [{'goal': r.text, 'use': r.use} for r in self.not_for],
            'related': [{'use': r.use, 'why': r.text} for r in self.related],
            'outcomes': {k: list(v) for k, v in self.outcomes.items()},
            'limits': list(self.limits),
            'choices': {k: list(v) for k, v in self.choices.items()},
            'use_cases': [{'title': u.title, 'text': u.text} for u in self.use_cases],
            'examples': [example_dict(e) for e in self.examples],
        }


@dataclass(frozen=True)
class CollectionInfo:
    title: str = ''
    summary: str = ''


@dataclass(frozen=True)
class Feature:
    id: str
    title: str
    summary: str
    syntax: str = ''
    example: str = ''
    doc: str = ''  # Sphinx document with the full story (``/guide/archives``)
    keywords: tuple[str, ...] = ()


@dataclass(frozen=True)
class Gap:
    """A goal no bundled testfunction covers (yet), with what to do instead."""

    id: str
    summary: str
    keywords: tuple[str, ...] = ()
    instead: str = ''


@dataclass(frozen=True)
class Library:
    asserts: dict[str, str] = field(default_factory=dict)
    formats: dict[str, str] = field(default_factory=dict)
    features: dict[str, Feature] = field(default_factory=dict)
    gaps: tuple[Gap, ...] = ()


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _yaml_loader():
    """The playbook loader, so examples may use ``!re`` / ``!timestamp`` like a real playbook."""
    from adarelib.testset.yaml.customloader import get_custom_loader

    return get_custom_loader()


def _strings(value: Any, where: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return tuple(value)
    raise ContractError(f'{where}: expected a string or a list of strings')


def _mapping(value: Any, where: str) -> dict:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ContractError(f'{where}: expected a mapping')
    return value


def _redirects(items: Any, text_key: str, where: str) -> tuple[Redirect, ...]:
    if items is None:
        return ()
    if not isinstance(items, list):
        raise ContractError(f'{where}: expected a list')
    out = []
    for i, item in enumerate(items):
        if not isinstance(item, dict) or not isinstance(item.get('use'), str) or not item.get(text_key):
            raise ContractError(f'{where}[{i}]: needs `use: <collection.function>` and `{text_key}:`')
        out.append(Redirect(use=item['use'], text=str(item[text_key]).strip()))
    return tuple(out)


def _child(node: yaml.Node | None, key: str | int) -> yaml.Node | None:
    """The value node under a mapping key or at a sequence index (``None`` when absent)."""
    if isinstance(node, yaml.MappingNode) and isinstance(key, str):
        return next((v for k, v in node.value if k.value == key), None)
    if isinstance(node, yaml.SequenceNode) and isinstance(key, int) and key < len(node.value):
        return node.value[key]
    return None


def _serialize(node: yaml.Node) -> str:
    """The node as YAML text; PyYAML writes an empty-string key as ``? ''``, a plain ``'':`` reads better."""
    return re.sub(r"\?\s+(''|\"\")\s*:", r"\1:", str(yaml.serialize(node, width=100)).strip())


def _display(node: yaml.Node) -> Any:
    """Plain data for a node; a custom-tagged node (``!re``, ``!timestamp``) becomes its YAML text."""
    if node.tag.startswith('!'):
        return yaml.serialize(node, width=1000).strip()
    if isinstance(node, yaml.MappingNode):
        return {k.value: _display(v) for k, v in node.value}
    if isinstance(node, yaml.SequenceNode):
        return [_display(v) for v in node.value]
    return yaml.safe_load(yaml.serialize(node))


def _example(item: Any, where: str, node: yaml.Node | None = None) -> Example:
    if not isinstance(item, dict) or not isinstance(item.get('title'), str):
        raise ContractError(f'{where}: an example needs a `title:`')
    expect = item.get('expect', 'passed')
    if expect not in OUTCOMES:
        raise ContractError(f'{where}: `expect: {expect}` is not one of {", ".join(OUTCOMES)}')
    run = item.get('run', True)
    if run is not True and not isinstance(run, str):
        raise ContractError(f'{where}: `run:` is omitted (runs) or a string saying why it cannot run offline')
    return Example(
        title=item['title'].strip(),
        parameter=_mapping(item.get('parameter'), f'{where}.parameter'),
        expect=expect,
        files=_mapping(item.get('files'), f'{where}.files'),
        text=str(item.get('text', '')).strip(),
        run=run is True,
        why_not_run='' if run is True else run.strip(),
        variables=_mapping(item.get('variables'), f'{where}.variables'),
        parameter_yaml=_serialize(node) if node is not None else '',
        parameter_display=_display(node) if node is not None else {},
    )


def parse_contract(data: Any, where: str, node: yaml.Node | None = None) -> Contract:
    data = _mapping(data, where)
    unknown = set(data) - {
        'asserts',
        'formats',
        'features',
        'unsupported',
        'not_for',
        'related',
        'outcomes',
        'limits',
        'choices',
        'use_cases',
        'examples',
    }
    if unknown:
        raise ContractError(f'{where}: unknown key(s) {", ".join(sorted(unknown))}')
    outcomes = _mapping(data.get('outcomes'), f'{where}.outcomes')
    if set(outcomes) - set(OUTCOMES):
        raise ContractError(f'{where}.outcomes: keys are {", ".join(OUTCOMES)}')
    choices = _mapping(data.get('choices'), f'{where}.choices')
    for name, values in choices.items():
        if not isinstance(values, list) or not values:
            raise ContractError(f'{where}.choices.{name}: expected a non-empty list of allowed values')
    use_cases = []
    for i, item in enumerate(data.get('use_cases') or []):
        if isinstance(item, str):
            use_cases.append(UseCase(title=item.strip()))
        elif isinstance(item, dict) and isinstance(item.get('title'), str):
            use_cases.append(UseCase(title=item['title'].strip(), text=str(item.get('text', '')).strip()))
        else:
            raise ContractError(f'{where}.use_cases[{i}]: a string or `title:` + `text:`')
    return Contract(
        asserts=_strings(data.get('asserts'), f'{where}.asserts'),
        formats=_strings(data.get('formats'), f'{where}.formats'),
        features=_strings(data.get('features'), f'{where}.features'),
        unsupported={str(k): str(v).strip() for k, v in _mapping(data.get('unsupported'), where).items()},
        not_for=_redirects(data.get('not_for'), 'goal', f'{where}.not_for'),
        related=_redirects(data.get('related'), 'why', f'{where}.related'),
        outcomes={k: _strings(v, f'{where}.outcomes.{k}') for k, v in outcomes.items()},
        limits=_strings(data.get('limits'), f'{where}.limits'),
        choices={k: tuple(v) for k, v in choices.items()},
        use_cases=tuple(use_cases),
        examples=tuple(
            _example(e, f'{where}.examples[{i}]', _child(_child(_child(node, 'examples'), i), 'parameter'))
            for i, e in enumerate(data.get('examples') or [])
        ),
    )


def read_contract_file(path: Path) -> tuple[CollectionInfo, dict[str, Contract]]:
    """Parse one ``contract.yaml``; raises :class:`ContractError` (or ``OSError``)."""
    text = path.read_text(encoding='utf-8')
    try:
        data = yaml.load(text, Loader=_yaml_loader())  # noqa: S506 - SafeLoader subclass
        root = yaml.compose(text, Loader=_yaml_loader())  # noqa: S506 - nodes, to keep examples as written
    except (yaml.YAMLError, ValueError) as e:  # an invalid !timestamp raises ValueError
        raise ContractError(f'{path}: {e}') from e
    data = _mapping(data, str(path))
    info = _mapping(data.get('collection'), f'{path}: collection')
    functions = _mapping(data.get('functions'), f'{path}: functions')
    function_nodes = _child(root, 'functions')
    return (
        CollectionInfo(title=str(info.get('title', '')), summary=str(info.get('summary', '')).strip()),
        {
            str(name): parse_contract(body, f'{path.name}: {name}', _child(function_nodes, name))
            for name, body in functions.items()
        },
    )


def load_contracts(collection_py: Path) -> tuple[CollectionInfo, dict[str, Contract]]:
    """The contracts next to a collection file; a broken or missing file yields none (logged)."""
    path = collection_py.parent / CONTRACT_FILE
    if not path.is_file():
        return CollectionInfo(), {}
    try:
        return read_contract_file(path)
    except (OSError, ContractError) as e:
        log.warning(f'Ignoring testfunction contract {path}: {e}')
        return CollectionInfo(), {}


def read_library(path: Path) -> Library:
    try:
        data = yaml.safe_load(path.read_text(encoding='utf-8'))
    except yaml.YAMLError as e:
        raise ContractError(f'{path}: {e}') from e
    data = _mapping(data, str(path))
    features = {}
    for fid, body in _mapping(data.get('features'), 'features').items():
        body = _mapping(body, f'features.{fid}')
        if not body.get('title') or not body.get('summary'):
            raise ContractError(f'{path}: feature {fid} needs `title:` and `summary:`')
        features[fid] = Feature(
            id=fid,
            title=str(body['title']),
            summary=str(body['summary']).strip(),
            syntax=str(body.get('syntax', '')).strip(),
            example=str(body.get('example', '')).rstrip(),
            doc=str(body.get('doc', '')),
            keywords=_strings(body.get('keywords'), f'features.{fid}.keywords'),
        )
    gaps = []
    for i, body in enumerate(data.get('gaps') or []):
        body = _mapping(body, f'gaps[{i}]')
        if not body.get('id') or not body.get('summary'):
            raise ContractError(f'{path}: gaps[{i}] needs `id:` and `summary:`')
        gaps.append(
            Gap(
                id=str(body['id']),
                summary=str(body['summary']).strip(),
                keywords=_strings(body.get('keywords'), f'gaps[{i}].keywords'),
                instead=str(body.get('instead', '')).strip(),
            )
        )
    return Library(
        asserts={str(k): str(v) for k, v in _mapping(data.get('asserts'), 'asserts').items()},
        formats={str(k): str(v) for k, v in _mapping(data.get('formats'), 'formats').items()},
        features=features,
        gaps=tuple(gaps),
    )


_LIBRARY_CACHE: dict[Path, tuple[tuple, Library]] = {}


def load_library(root: Path | None = None) -> Library:
    """``library.yaml`` of the bundled collections (cached while the file is unchanged)."""
    from adare.backend.testfunction.catalog import PACKAGE_APPDATA

    path = (root or PACKAGE_APPDATA) / LIBRARY_FILE
    try:
        st = path.stat()
    except OSError:
        return Library()
    stamp = (st.st_mtime_ns, st.st_size)
    cached = _LIBRARY_CACHE.get(path)
    if cached and cached[0] == stamp:
        return cached[1]
    try:
        library = read_library(path)
    except (OSError, ContractError) as e:
        log.warning(f'Ignoring testfunction library file {path}: {e}')
        library = Library()
    _LIBRARY_CACHE[path] = (stamp, library)
    return library


# ---------------------------------------------------------------------------
# Examples as playbook items
# ---------------------------------------------------------------------------


def example_item(dotnotation: str, example: Example) -> dict:
    """The example as a ``tests:`` list item."""
    name = '_'.join(w for w in ''.join(c if c.isalnum() else ' ' for c in example.title.lower()).split())[:48]
    return {'name': name or 'check', 'function': dotnotation, 'parameter': example.parameter}


def example_yaml(dotnotation: str, example: Example) -> str:
    """``tests:`` YAML for an example, with the parameter block exactly as written in the contract."""
    item = example_item(dotnotation, example)
    head = str(yaml.safe_dump({'tests': [{'name': item['name'], 'function': dotnotation}]}, sort_keys=False))
    if not example.parameter:
        return head
    body = example.parameter_yaml or str(yaml.safe_dump(example.parameter, sort_keys=False)).strip()
    return head + '  parameter:\n' + ''.join(f'    {line}\n' for line in body.splitlines())


def example_dict(example: Example) -> dict:
    """JSON-safe form (tags as their YAML text) for ``--json`` output and agent tools."""
    data: dict[str, Any] = {
        'title': example.title,
        'expect': example.expect,
        'parameter': example.parameter_display or example.parameter,
    }
    if example.text:
        data['text'] = example.text
    if not example.run:
        data['runs_offline'] = False
    return data
