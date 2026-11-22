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
import copy
import difflib
import hashlib
import logging
import math
import re
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

_NO_DEFAULT = object()

# Words a user/agent may use for the same assertion. Each query token is expanded
# to its whole group before matching, so "verify the file is gone" finds
# ``file_does_not_exist``.
_SYNONYM_GROUPS = (
    {'deleted', 'delete', 'removed', 'remove', 'gone', 'absent', 'absence', 'missing', 'not', 'lacks', 'wiped'}
    | {'erased', 'stripped', 'cleared', 'purged'},
    {'exists', 'exist', 'present', 'created', 'there', 'appears'},
    {'contains', 'contain', 'includes', 'include', 'has', 'with'},
    {'equals', 'equal', 'matches', 'match', 'same', 'identical', 'value', 'compare', 'compares'},
    {'screen', 'visible', 'shown', 'displayed', 'icon', 'ui', 'visual', 'window'},
    {'registry', 'regkey', 'hive'},
    {'sqlite', 'database', 'db', 'query', 'sql', 'table', 'records'},
    {'excel', 'xlsx', 'spreadsheet', 'sheet', 'cell', 'workbook'},
    {'hash', 'sha256', 'md5', 'checksum', 'integrity'},
    {'timestamp', 'timestamps', 'mtime', 'ctime', 'atime', 'modified', 'time', 'macb', 'epoch'},
    {'permission', 'permissions', 'mode', 'chmod', 'owner'},
    {'directory', 'dir', 'folder'},
    {'regex', 'pattern', 'regexp'},
    {'xml', 'xpath', 'element', 'attribute', 'docx', 'odt', 'pptx', 'office'},
    {'csv', 'row', 'rows', 'record', 'line'},
    {'process', 'running', 'service', 'daemon'},
    {'user', 'account'},
    {'log', 'logs', 'journal'},
    {'keepass', 'kdbx', 'password', 'vault'},
    {'ini', 'config', 'setting', 'settings', 'preference', 'preferences'},
    {'empty', 'size', 'bytes', 'kb', 'mb', 'large', 'big', 'small', 'grew', 'shrank'},
    {'count', 'counts', 'counting', 'number', 'many', 'times', 'occurrences', 'occurrence', 'occurs', 'often'},
    {'archive', 'zip', 'tar', 'compressed', 'lz4', 'jsonlz4', 'snappy', 'gzip', 'gz', 'xz', 'bzip2'},
    {'string', 'word', 'text', 'substring', 'marker'},
    {'exif', 'photo', 'photos', 'jpeg', 'jpg', 'camera', 'gps', 'metadata'},
    {'binary', 'encoding', 'encodings', 'utf', 'utf8', 'utf16', 'cache', 'dump'},
)
_NEGATIVE_WORDS = _SYNONYM_GROUPS[0] | {'no', 'longer', 'never', 'without'}
_COUNT_WORDS = next(group for group in _SYNONYM_GROUPS if 'count' in group)
_NEGATIVE_NAME_MARKERS = ('not_', '_not', 'absent', 'lacks', 'missing')
# A count with ``expected_count: 0`` asserts absence too, so negative goals favour it
# over a plain presence test (``json.value_count`` for "json key is absent").
_COUNT_NAME_MARKERS = ('count',)

# Glue words carry no intent; as name tokens (``value_in_any_line``) they caused
# incidental top hits.
_STOPWORDS = frozenset(
    {
        'a',
        'an',
        'the',
        'is',
        'are',
        'was',
        'were',
        'be',
        'been',
        'of',
        'in',
        'on',
        'at',
        'to',
        'for',
        'from',
        'by',
        'and',
        'or',
        'it',
        'its',
        'this',
        'that',
        'any',
        'all',
        'how',
        'what',
        'which',
        's',
        'n',
    }
)

_RELATIVE_CUTOFF = 0.45
_SYNONYM_FACTOR = 0.6
_EXTRA_FIELD_FACTOR = 0.25
_IDF_STRENGTH = 0.5

# ``use_for`` is the docstring's "Use for:" paragraph: intent phrasing ("asserting a
# value was wiped"), worth more than the rest of the prose, which mentions many
# neighbouring functions ("for X use ...") and would otherwise add noise.
_FIELD_WEIGHTS = (
    ('name', 4.0),
    ('collection', 2.0),
    ('summary', 2.0),
    ('use_for', 2.0),
    ('params', 0.75),
    ('doc', 0.5),
)


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
    code_sha: str = field(default='', compare=False, repr=False)  # docstring-free code hash

    @classmethod
    def from_dict(cls, data: dict) -> 'CatalogEntry':
        """Inverse of :meth:`to_dict` (full form); tolerates the legacy DB-shaped keys."""
        params = tuple(
            ParamSpec(
                name=p['name'],
                type=p.get('type', p.get('data_type', '')) or '',
                required=bool(p.get('required', True)),
                default=p.get('default'),
                doc=p.get('doc', p.get('description', '')) or '',
            )
            for p in data.get('params', data.get('parameters', ())) or ()
        )
        dotnotation = data['dotnotation']
        return cls(
            dotnotation=dotnotation,
            collection=data.get('collection', dotnotation.split('.')[0]),
            name=data.get('name', dotnotation.split('.')[-1]),
            summary=data.get('summary', data.get('description', '')) or '',
            category=data.get('category', ''),
            os=data.get('os', 'any'),
            installed=data.get('installed', True),
            path=data.get('path', ''),
            execute_on_host=data.get('execute_on_host', False),
            doc=data.get('doc', ''),
            params=params,
        )

    def example(self) -> dict:
        """A ready-to-paste ``tests:`` list item: placeholders for what must be filled in.

        Optional parameters are left out (their defaults apply); an empty-string
        default (``dst: str = ''``) is required in practice, so it gets a placeholder.
        """
        parameter = {p.name: f'<{p.type or "value"}>' for p in self.params if p.required or p.default == ''}
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
            return {
                'dotnotation': self.dotnotation,
                'summary': self.summary,
                'signature': self.signature(),
                'os': self.os,
                'installed': self.installed,
            }
        data = asdict(self)
        data.pop('code_sha')
        data['signature'] = self.signature()
        data['example'] = self.example()
        return data


# ---------------------------------------------------------------------------
# Source parsing
# ---------------------------------------------------------------------------


def testfunction_code_without_docstring(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Source of a testfunction for hashing, docstring excluded.

    Documentation (the catalog's ``Args:`` section) must not bump the function's
    version: only code changes do.
    """
    body = func_node.body
    if (
        body
        and isinstance(body[0], ast.Expr)
        and isinstance(body[0].value, ast.Constant)
        and isinstance(body[0].value.value, str)
    ):
        body = body[1:] or [ast.Pass()]
    stripped = copy.copy(func_node)
    stripped.body = body
    return ast.unparse(stripped)


def _decorator_call(node: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.Call | None:
    for decorator in node.decorator_list:
        if not isinstance(decorator, ast.Call):
            continue
        func = decorator.func
        if (isinstance(func, ast.Name) and func.id == 'testfunction') or (
            isinstance(func, ast.Attribute) and func.attr == 'testfunction'
        ):
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
        specs.append(
            ParamSpec(
                name=arg.arg,
                type=ast.unparse(arg.annotation) if arg.annotation else '',
                required=not has_default,
                default=_default_value(default) if has_default else None,
                doc=arg_docs.get(arg.arg, ''),
            )
        )
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
        entries.append(
            CatalogEntry(
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
                code_sha=hashlib.sha256(testfunction_code_without_docstring(node).encode()).hexdigest(),
            )
        )
    return entries


def docstring_warnings(path: Path) -> list[str]:
    """Documentation gaps in one collection file, for ``adare test validate``.

    Reports testfunctions without a docstring and non-ctx parameters without an
    ``Args:`` entry. Advisory only: undocumented functions still load and run.
    """
    warnings = []
    for entry in parse_collection(path, installed=False):
        if not entry.doc.strip():
            warnings.append(f"{entry.dotnotation}: no docstring (add a summary line and an 'Args:' section)")
            continue
        documented = parse_args_section(entry.doc)
        missing = [p.name for p in entry.params if p.name not in documented]
        if missing:
            warnings.append(f"{entry.dotnotation}: no 'Args:' entry for parameter(s) {', '.join(missing)}")
    return warnings


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

PACKAGE_APPDATA = Path(__file__).resolve().parents[3] / 'appdata' / 'testfunctions'


def bundled_sources() -> list[tuple[Path, bool]]:
    """Only the collections shipped with this checkout: machine-independent (generated docs)."""
    return [(PACKAGE_APPDATA, False)]


def default_sources() -> list[tuple[Path, bool]]:
    """``(root, installed)`` pairs, installed first so it wins on duplicates."""
    from adare.config.configdirectory import APPDATA_DIR, STATE_DIR

    return [
        (STATE_DIR / 'testfunctions', True),
        (APPDATA_DIR / 'adare' / 'adare' / 'appdata' / 'testfunctions', False),
        *bundled_sources(),
    ]


# load_catalog() runs on every agent tool call (chat tools, MCP serving, playbook
# checks). Parsing and hashing every collection each time is wasted work while no
# source changed, so the result is kept per input, guarded by a fingerprint of the
# collection files that any edit, addition or removal invalidates.
_CATALOG_CACHE: dict[tuple, tuple[tuple, list[CatalogEntry]]] = {}


def _collection_files(sources: tuple[tuple[Path, bool], ...]) -> list[tuple[Path, bool]]:
    files = []
    for root, installed in sources:
        if not root.is_dir():
            continue
        for path in sorted(root.glob('*/*.py')):
            if path.stem == path.parent.name:  # collection file must be named after its dir
                files.append((path, installed))
    return files


def _fingerprint(files: list[tuple[Path, bool]]) -> tuple:
    stamps: list[tuple[str, int | None, int | None]] = []
    for path, _ in files:
        try:
            st = path.stat()
        except OSError:
            stamps.append((path.as_posix(), None, None))  # vanished mid-scan: parse_collection logs it
            continue
        stamps.append((path.as_posix(), st.st_mtime_ns, st.st_size))
    return tuple(stamps)


def load_catalog(sources: list[tuple[Path, bool]] | None = None) -> list[CatalogEntry]:
    """All testfunctions from ``sources`` (default: installed + bundled), deduplicated by dotnotation.

    A host-native collection (``visual``) is never synced into the installed dir, so
    its bundled copy is reported as installed: it is always available at run time.

    Cached per ``sources`` while the collection files' paths, mtimes and sizes are
    unchanged; each call still re-scans the directories (cheap) to check that.
    """
    from adare.backend.testfunction.commands import testfunction_sync_all

    always_available = testfunction_sync_all.__defaults__[0]
    resolved = tuple(
        (Path(root), installed) for root, installed in (sources if sources is not None else default_sources())
    )
    files = _collection_files(resolved)
    fingerprint = _fingerprint(files)
    key = (resolved, tuple(always_available))
    cached = _CATALOG_CACHE.get(key)
    if cached is not None and cached[0] == fingerprint:
        return list(cached[1])

    seen: dict[str, CatalogEntry] = {}
    for path, installed in files:
        available = installed or path.stem in always_available
        for entry in parse_collection(path, available):
            if entry.dotnotation not in seen:
                seen[entry.dotnotation] = entry
            else:
                seen[entry.dotnotation] = _borrow_docs(seen[entry.dotnotation], entry)
    entries = sorted(seen.values(), key=lambda e: e.dotnotation)
    _CATALOG_CACHE[key] = (fingerprint, entries)
    return list(entries)


def _borrow_docs(installed: CatalogEntry, bundled: CatalogEntry) -> CatalogEntry:
    """Give an undocumented installed function the docs of its *identical* bundled copy.

    Docstrings don't change a function's version, so ``test sync`` is not needed
    to see newly written docs; differing code keeps the installed entry as is.
    """
    if installed.doc or not bundled.doc or installed.code_sha != bundled.code_sha:
        return installed
    docs = {p.name: p.doc for p in bundled.params}
    params = tuple(replace(p, doc=p.doc or docs.get(p.name, '')) for p in installed.params)
    return replace(installed, doc=bundled.doc, params=params)


def close_matches(entries: list[CatalogEntry], dotnotation: str, n: int = 3) -> list[CatalogEntry]:
    """Typo-tolerant suggestions for an unknown dotnotation or bare name."""
    by_key = {e.dotnotation: e for e in entries} | {e.name: e for e in entries}
    keys = difflib.get_close_matches(dotnotation, list(by_key), n=n * 2, cutoff=0.6)
    unique = list(dict.fromkeys(by_key[k] for k in keys))
    return unique[:n]


def find(entries: list[CatalogEntry], dotnotation: str) -> CatalogEntry | None:
    """Resolve like the run-time loader does (``ExperimentDbApi`` test creation).

    A bare name means ``standard.<name>``; the legacy 3-part
    ``project.file.function`` form ignores the project (testfunctions are global).
    """
    by_name = {e.dotnotation: e for e in entries}
    if dotnotation in by_name:
        return by_name[dotnotation]
    parts = dotnotation.split('.')
    if len(parts) == 1:
        return by_name.get(f'standard.{dotnotation}')
    return by_name.get('.'.join(parts[-2:])) if len(parts) == 3 else None


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


def _tokens(text: str) -> list[str]:
    return [t for t in re.split(r'[^a-z0-9]+', text.lower()) if t and t not in _STOPWORDS]


_USE_FOR = re.compile(r'^\s*Use for:\s*(.*?)(?:\n\s*\n|\Z)', re.MULTILINE | re.DOTALL)


def use_for(doc: str) -> str:
    """The docstring's ``Use for:`` paragraph, joined to one line (``''`` without one)."""
    match = _USE_FOR.search(doc.split('\nArgs:')[0])
    return ' '.join(match.group(1).split()) if match else ''


def _expand(token: str) -> set[str]:
    for group in _SYNONYM_GROUPS:
        if token in group:
            return group | {token}
    return {token}


def _matches(query_token: str, field_tokens: set[str]) -> bool:
    if query_token in field_tokens:
        return True
    # cheap stemming: "deletes"/"deleting" vs "delete", "files" vs "file", "absent" vs
    # "absence" -- but not "times" vs "timestamps" (at most 3 letters differ in length)
    return len(query_token) >= 4 and any(_same_stem(query_token, t) for t in field_tokens if len(t) >= 4)


def _same_stem(a: str, b: str) -> bool:
    if abs(len(a) - len(b)) > 3:
        return False
    if a.startswith(b) or b.startswith(a):
        return True
    return len(a) >= 5 and len(b) >= 5 and a[:5] == b[:5]


def _fields(entry: CatalogEntry) -> dict[str, set[str]]:
    return {
        'name': set(_tokens(entry.name)),
        'collection': set(_tokens(entry.collection)),
        'summary': set(_tokens(entry.summary)),
        'use_for': set(_tokens(use_for(entry.doc))),
        'params': {t for p in entry.params for t in _tokens(f'{p.name} {p.doc}')},
        'doc': set(_tokens(entry.doc)),
    }


def _token_score(query_token: str, fields: dict[str, set[str]]) -> float:
    """Best field match of one query token, plus a little for every further field it hits.

    Taking the best field (instead of the sum over all fields) keeps a long docstring
    that mentions a word in passing from outranking a function named after it.
    """
    synonyms = _expand(query_token) - {query_token}
    hits = []
    for field_name, weight in _FIELD_WEIGHTS:
        if _matches(query_token, fields[field_name]):
            hits.append(weight)
        elif any(t in fields[field_name] for t in synonyms):
            hits.append(weight * _SYNONYM_FACTOR)
    if not hits:
        return 0.0
    hits.sort(reverse=True)
    return hits[0] + _EXTRA_FIELD_FACTOR * sum(hits[1:])


def search(
    entries: list[CatalogEntry],
    query: str = '',
    *,
    collection: str | None = None,
    category: str | None = None,
    os: str | None = None,
    limit: int | None = None,
) -> list[CatalogEntry]:
    """Rank entries for a natural-language ``query``; filters are exact (case-insensitive)."""
    pool = [
        e
        for e in entries
        if (not collection or e.collection.lower() == collection.lower())
        and (not category or e.category.lower() == category.lower())
        and (not os or e.os in (os.lower(), 'any'))
    ]
    query_tokens = _tokens(query)
    if not query_tokens:
        return pool[:limit] if limit else pool

    wants_negative = any(t in _NEGATIVE_WORDS for t in query_tokens)
    wants_count = any(t in _COUNT_WORDS for t in query_tokens)
    token_scores = [[_token_score(qt, fields) for qt in query_tokens] for fields in map(_fields, pool)]
    # Rare words decide more: "wiped" (2 functions) outweighs "value" (most of them).
    idf = [
        1.0 + _IDF_STRENGTH * math.log(len(pool) / max(1, sum(1 for scores in token_scores if scores[i] > 0)))
        for i in range(len(query_tokens))
    ]
    scored = []
    for entry, scores in zip(pool, token_scores, strict=True):
        score = sum(s * w for s, w in zip(scores, idf, strict=True))
        if score <= 0:
            continue
        is_negative = any(marker in entry.name for marker in _NEGATIVE_NAME_MARKERS)
        is_count = any(marker in entry.name for marker in _COUNT_NAME_MARKERS)
        if wants_negative:
            score += 3.0 if is_negative else 1.0 if is_count else -1.5
        elif is_negative:
            score -= 1.0
        if is_count:
            score += 1.0 if wants_count else -0.5
        scored.append((score, entry))
    scored.sort(key=lambda pair: (-pair[0], pair[1].dotnotation))
    # Drop the long tail of incidental matches ("file" alone matches half the catalog).
    cutoff = scored[0][0] * _RELATIVE_CUTOFF if scored else 0
    ranked = [entry for score, entry in scored if score >= cutoff]
    return ranked[:limit] if limit else ranked
