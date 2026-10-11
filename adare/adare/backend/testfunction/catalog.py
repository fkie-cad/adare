"""Static testfunction catalog for discovery (CLI, MCP tools, agents).

Built from the collection sources with ``ast`` — no database, no project and no
import of the collections — so it is

* complete: includes host-native collections (``visual``) that ``test sync``
  deliberately keeps out of the database, and bundled collections not yet synced;
* exact: per-function annotation, default and required-ness, which the shared
  ``test_parameter`` table (unique by name across all functions) cannot hold.

Parameter docs come from a Google-style ``Args:`` section in the function docstring.
"""

import ast
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

_NO_DEFAULT = object()

# Words a user/agent may use for the same assertion. Each query token is expanded
# to its whole group before matching, so "verify the file is gone" finds
# ``file_does_not_exist``.
_SYNONYM_GROUPS = (
    {'deleted', 'delete', 'removed', 'remove', 'gone', 'absent', 'missing', 'not', 'lacks', 'wiped', 'erased'},
    {'exists', 'exist', 'present', 'created', 'there'},
    {'contains', 'contain', 'includes', 'include', 'has', 'with'},
    {'equals', 'equal', 'matches', 'match', 'same', 'identical', 'value', 'compare', 'compares'},
    {'screen', 'visible', 'shown', 'displayed', 'icon', 'image', 'ui', 'visual', 'window'},
    {'registry', 'regkey', 'hive'},
    {'sqlite', 'database', 'db', 'query', 'sql', 'table'},
    {'excel', 'xlsx', 'spreadsheet', 'sheet', 'cell', 'workbook'},
    {'hash', 'sha256', 'md5', 'checksum', 'integrity'},
    {'timestamp', 'timestamps', 'mtime', 'ctime', 'atime', 'modified', 'time', 'macb'},
    {'permission', 'permissions', 'mode', 'chmod', 'owner'},
    {'directory', 'dir', 'folder'},
    {'regex', 'pattern', 'regexp'},
    {'json', 'key'},
    {'xml', 'xpath', 'element', 'attribute'},
    {'csv', 'row', 'rows', 'line'},
    {'process', 'running', 'service', 'daemon'},
    {'user', 'account'},
    {'log', 'logs', 'journal'},
    {'keepass', 'kdbx', 'password', 'vault'},
    {'ini', 'config', 'setting', 'settings'},
)
_NEGATIVE_WORDS = _SYNONYM_GROUPS[0] | {'no', 'longer', 'never', 'without'}
_NEGATIVE_NAME_MARKERS = ('not_', '_not', 'absent', 'lacks', 'missing')

_FIELD_WEIGHTS = (('name', 4.0), ('collection', 2.0), ('summary', 2.0), ('params', 1.0), ('doc', 1.0))


@dataclass(frozen=True)
class ParamSpec:
    name: str
    type: str
    required: bool
    default: Any = None
    doc: str = ''


@dataclass(frozen=True)
class CatalogEntry:
    dotnotation: str
    collection: str
    name: str
    summary: str
    category: str
    os: str
    installed: bool
    path: str
    execute_on_host: bool = False
    doc: str = ''
    params: tuple[ParamSpec, ...] = field(default_factory=tuple)

    def example(self) -> dict:
        """A ready-to-paste ``tests:`` list item (required params get a placeholder)."""
        parameter = {}
        for p in self.params:
            if p.required:
                parameter[p.name] = f'<{p.type or "value"}>'
            elif p.default not in (None, '', [], {}):
                parameter[p.name] = p.default
        item = {'name': f'check_{self.name.split(".")[-1]}', 'function': self.dotnotation}
        if parameter:
            item['parameter'] = parameter
        return item

    def example_yaml(self) -> str:
        return yaml.safe_dump({'tests': [self.example()]}, sort_keys=False, default_flow_style=False)

    def signature(self) -> str:
        parts = []
        for p in self.params:
            text = f'{p.name}: {p.type}' if p.type else p.name
            if not p.required:
                text += f' = {p.default!r}'
            parts.append(text)
        return f'{self.dotnotation}({", ".join(parts)})'

    def to_dict(self, compact: bool = False) -> dict:
        """``compact`` is the token-cheap form for listings: what to call and why."""
        if compact:
            return {'dotnotation': self.dotnotation, 'summary': self.summary,
                    'signature': self.signature(), 'os': self.os, 'installed': self.installed}
        data = asdict(self)
        data['signature'] = self.signature()
        data['example'] = self.example()
        return data


# ---------------------------------------------------------------------------
# Source parsing
# ---------------------------------------------------------------------------

def _decorator_call(node: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.Call | None:
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        func = decorator.func
        if (isinstance(func, ast.Name) and func.id == 'testfunction') or \
                (isinstance(func, ast.Attribute) and func.attr == 'testfunction'):
            return decorator
    return None


def _kwarg(call: ast.Call, key: str, default: Any = None) -> Any:
    for kw in call.keywords:
        if kw.arg != key:
            continue
        if isinstance(kw.value, ast.Constant):
            return kw.value.value
        if isinstance(kw.value, ast.Attribute):  # e.g. HostModeCategory.FILE_BASED
            return kw.value.attr
        return ast.unparse(kw.value)
    return default


def _default_value(node: ast.expr) -> Any:
    try:
        return ast.literal_eval(node)
    except ValueError:
        return ast.unparse(node)


def parse_args_section(doc: str) -> dict[str, str]:
    """Parse a Google-style ``Args:`` section into ``{param: description}``."""
    params: dict[str, str] = {}
    in_args = False
    current = None
    for raw in doc.splitlines():
        line = raw.rstrip()
        stripped = line.strip()
        if stripped in ('Args:', 'Arguments:', 'Parameters:'):
            in_args = True
            continue
        if not in_args:
            continue
        if stripped and not raw.startswith((' ', '\t')):
            break  # next top-level section (Returns:, Example:, ...)
        match = re.match(r'^\s+(\w+)(?:\s*\([^)]*\))?:\s*(.*)$', line)
        if match and (current is None or len(line) - len(line.lstrip()) <= params.get('__indent__', 99)):
            current = match.group(1)
            params['__indent__'] = len(line) - len(line.lstrip())
            params[current] = match.group(2).strip()
        elif current and stripped:
            params[current] = f'{params[current]} {stripped}'.strip()
    params.pop('__indent__', None)
    return params


def _params(node: ast.FunctionDef | ast.AsyncFunctionDef, arg_docs: dict[str, str]) -> tuple[ParamSpec, ...]:
    args = node.args.args
    defaults = [_NO_DEFAULT] * (len(args) - len(node.args.defaults)) + list(node.args.defaults)
    specs = []
    for arg, default in zip(args, defaults, strict=True):
        if arg.arg in ('ctx', 'self'):
            continue
        has_default = default is not _NO_DEFAULT
        specs.append(ParamSpec(
            name=arg.arg,
            type=ast.unparse(arg.annotation) if arg.annotation else '',
            required=not has_default,
            default=_default_value(default) if has_default else None,
            doc=arg_docs.get(arg.arg, ''),
        ))
    return tuple(specs)


def _infer_os(collection: str, summary: str) -> str:
    text = f'{collection} {summary}'.lower()
    if 'windows' in text:
        return 'windows'
    if 'linux' in text:
        return 'linux'
    return 'any'


def parse_collection(path: Path, installed: bool) -> list[CatalogEntry]:
    """Parse one collection file; a broken file is logged and yields no entries."""
    try:
        module = ast.parse(path.read_text(encoding='utf-8'), filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError) as e:
        log.warning(f'Skipping testfunction collection {path}: {e}')
        return []
    collection = path.stem
    entries = []
    for node in module.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        call = _decorator_call(node)
        if call is None:
            continue
        testname = _kwarg(call, 'name', node.name)
        summary = _kwarg(call, 'description', '') or ''
        doc = ast.get_docstring(node) or ''
        entries.append(CatalogEntry(
            # Host-native tests carry their full dotnotation in the name (``visual.exists``).
            dotnotation=testname if '.' in testname else f'{collection}.{testname}',
            collection=collection,
            name=testname,
            summary=summary,
            category=_kwarg(call, 'category', 'AGENT_ONLY'),
            os=_infer_os(collection, summary),
            installed=installed,
            path=path.as_posix(),
            execute_on_host=bool(_kwarg(call, 'execute_on_host', False)),
            doc=doc,
            params=_params(node, parse_args_section(doc)),
        ))
    return entries


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

def default_sources() -> list[tuple[Path, bool]]:
    """``(root, installed)`` pairs, installed first so it wins on duplicates."""
    from adare.config.configdirectory import APPDATA_DIR, STATE_DIR

    package_appdata = Path(__file__).resolve().parents[3] / 'appdata' / 'testfunctions'
    return [
        (STATE_DIR / 'testfunctions', True),
        (APPDATA_DIR / 'adare' / 'adare' / 'appdata' / 'testfunctions', False),
        (package_appdata, False),
    ]


def load_catalog(sources: list[tuple[Path, bool]] | None = None) -> list[CatalogEntry]:
    """All testfunctions from ``sources`` (default: installed + bundled), deduplicated by dotnotation.

    A host-native collection (``visual``) is never synced into the installed dir, so
    its bundled copy is reported as installed: it is always available at run time.
    """
    from adare.backend.testfunction.commands import testfunction_sync_all

    always_available = testfunction_sync_all.__defaults__[0]
    seen: dict[str, CatalogEntry] = {}
    for root, installed in sources if sources is not None else default_sources():
        if not root.is_dir():
            continue
        for path in sorted(root.glob('*/*.py')):
            if path.stem != path.parent.name:  # collection file must be named after its dir
                continue
            available = installed or path.stem in always_available
            for entry in parse_collection(path, available):
                seen.setdefault(entry.dotnotation, entry)
    return sorted(seen.values(), key=lambda e: e.dotnotation)


def find(entries: list[CatalogEntry], dotnotation: str) -> CatalogEntry | None:
    """Exact lookup; also accepts the legacy 3-part ``project.file.function`` form."""
    by_name = {e.dotnotation: e for e in entries}
    if dotnotation in by_name:
        return by_name[dotnotation]
    parts = dotnotation.split('.')
    return by_name.get('.'.join(parts[-2:])) if len(parts) == 3 else None


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r'[^a-z0-9]+', text.lower()) if t]


def _expand(token: str) -> set[str]:
    for group in _SYNONYM_GROUPS:
        if token in group:
            return group | {token}
    return {token}


def _matches(query_token: str, field_tokens: set[str]) -> bool:
    if query_token in field_tokens:
        return True
    # cheap stemming: "deletes"/"deleting" vs "delete", "files" vs "file"
    return len(query_token) >= 4 and any(
        t.startswith(query_token) or query_token.startswith(t) for t in field_tokens if len(t) >= 4)


def _fields(entry: CatalogEntry) -> dict[str, set[str]]:
    return {
        'name': set(_tokens(entry.name)),
        'collection': set(_tokens(entry.collection)),
        'summary': set(_tokens(entry.summary)),
        'params': {t for p in entry.params for t in _tokens(f'{p.name} {p.doc}')},
        'doc': set(_tokens(entry.doc)),
    }


def search(entries: list[CatalogEntry], query: str = '', *, collection: str | None = None,
           category: str | None = None, os: str | None = None, limit: int | None = None) -> list[CatalogEntry]:
    """Rank entries for a natural-language ``query``; filters are exact (case-insensitive)."""
    pool = [
        e for e in entries
        if (not collection or e.collection.lower() == collection.lower())
        and (not category or e.category.lower() == category.lower())
        and (not os or e.os in (os.lower(), 'any'))
    ]
    query_tokens = _tokens(query)
    if not query_tokens:
        return pool[:limit] if limit else pool

    wants_negative = any(t in _NEGATIVE_WORDS for t in query_tokens)
    scored = []
    for entry in pool:
        fields = _fields(entry)
        score = 0.0
        for qt in query_tokens:
            exact = {qt}
            synonyms = _expand(qt) - exact
            for field_name, weight in _FIELD_WEIGHTS:
                if any(_matches(t, fields[field_name]) for t in exact):
                    score += weight
                elif any(t in fields[field_name] for t in synonyms):
                    score += weight * 0.6
        if score <= 0:
            continue
        is_negative = any(marker in entry.name for marker in _NEGATIVE_NAME_MARKERS)
        if wants_negative:
            score += 3.0 if is_negative else -1.5
        elif is_negative:
            score -= 1.0
        scored.append((score, entry))
    scored.sort(key=lambda pair: (-pair[0], pair[1].dotnotation))
    ranked = [entry for _, entry in scored]
    return ranked[:limit] if limit else ranked
