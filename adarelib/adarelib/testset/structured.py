"""Shared bodies of key-path testfunctions for structured file formats (JSON, plist, YAML, TOML).

A collection describes its format once (:class:`StructuredFormat`: a label, a ``load(path)``
callable and the exceptions that mean "not valid <format>") and delegates to
:func:`contains_key`, :func:`value_matches` and :func:`value_count`, which do glob
resolution, the error mapping, key-path resolution, wildcard any/all and value comparison.

Result rules (the same for every format):

* missing file (``... does not exist``), glob matching 0 or several files, unreadable or
  invalid file, bad parameters -> ERROR
* the file was read and the key path / value / count does not hold -> FAILED

Key paths use :func:`adarelib.testset.compare.parse_key_path`. Loaded data is normalized
before comparison: dates and times become ISO 8601 strings, binary data a hex string, tuples
lists and non-string keys their ``str()``.

Ships with the agent's adarelib wheel; standard library only, importable on Python 3.10.
"""

import datetime
import logging
import re
import reprlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from adarelib.event.event import TestResult
from adarelib.testset.compare import compare_with_single_placeholder, resolve_key_path
from adarelib.testset.ordering import OrderingError

log = logging.getLogger(__name__)

COMPARISON_TYPES = ('equals', 'greater', 'less', 'greater_equal', 'less_equal')
WILDCARD_MODES = ('any', 'all')


@dataclass(frozen=True)
class StructuredFormat:
    """How a collection reads its format."""

    label: str  # 'JSON', 'plist', ... used in messages
    load: Callable[[str], Any]  # path -> data (dicts, lists, scalars)
    errors: tuple[type[BaseException], ...]  # raised by load for content that is not valid


# ---------------------------------------------------------------------------
# Value helpers
# ---------------------------------------------------------------------------


def normalize(value: Any, _memo: dict[int, Any] | None = None) -> Any:
    """Make loaded data comparable: ISO strings for dates, hex for bytes, str keys, lists.

    Containers shared by reference (YAML aliases) stay shared and cycles stay cycles, so
    an alias bomb or a self-referencing document costs no more than its size on disk.
    """
    memo: dict[int, Any] = {} if _memo is None else _memo
    if isinstance(value, dict):
        if id(value) in memo:
            return memo[id(value)]
        out: dict[str, Any] = {}
        memo[id(value)] = out
        for k, v in value.items():
            out[k if isinstance(k, str) else str(k)] = normalize(v, memo)
        return out
    if isinstance(value, (list, tuple)):
        if id(value) in memo:
            return memo[id(value)]
        items: list[Any] = []
        memo[id(value)] = items
        items.extend(normalize(v, memo) for v in value)
        return items
    if isinstance(value, (datetime.datetime, datetime.date, datetime.time)):
        return value.isoformat()
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).hex()
    return value


_REPR = reprlib.Repr()
_REPR.maxlevel = 3
_REPR.maxdict = _REPR.maxlist = _REPR.maxtuple = 10
_REPR.maxstring = _REPR.maxother = 200
_MAX_TEXT = 2000


def text(value: Any) -> str:
    """``str(value)`` for scalars; a bounded repr for containers.

    ``str()`` of a container expands every shared reference, so a small YAML file with nested
    aliases would turn into gigabytes of text in a regex search or a result message.
    """
    shown = _REPR.repr(value) if isinstance(value, (dict, list)) else str(value)
    return shown if len(shown) <= _MAX_TEXT else shown[:_MAX_TEXT] + '...'


def compare_value(ctx: Any, actual: Any, expected: Any, regex_match: bool = False) -> tuple[bool, str]:
    """Compare one value: ``!re`` tag (``re.match``), ``{{placeholder}}``, regex search or ``==``.

    :raises re.error: invalid regex in ``expected``
    """
    try:
        from adarelib.testset.yaml.customtags import YamlRegexString
    except ImportError:  # YAML support not installed: no !re tags can occur
        YamlRegexString = None  # noqa: N806

    if YamlRegexString is not None and isinstance(expected, YamlRegexString):
        try:
            pattern = re.compile(expected.string)
        except re.error as e:
            raise re.error(f'invalid regex pattern {expected.string!r}: {e}') from e
        if pattern.match(text(actual)):
            return True, f'value "{text(actual)}" matches regex "{expected.string}"'
        return False, f'value "{text(actual)}" does not match regex "{expected.string}"'

    expected_str = str(expected)
    if ctx.has_placeholders(expected_str):
        return compare_with_single_placeholder(ctx, expected_str, text(actual))
    if regex_match and isinstance(expected, str):
        try:
            pattern = re.compile(expected)
        except re.error as e:
            raise re.error(f'invalid regex pattern {expected!r}: {e}') from e
        if pattern.search(text(actual)):
            return True, f'value "{text(actual)}" matches regex "{expected}"'
        return False, f'value "{text(actual)}" does not match regex "{expected}"'
    if actual == expected:
        return True, f'value matches expected: {text(actual)}'
    return False, f'expected "{expected}", got "{text(actual)}"'


def compare_count(actual: int, expected: int, comparison_type: str) -> tuple[bool, str]:
    """Compare a count; ``comparison_type`` is one of :data:`COMPARISON_TYPES`.

    :raises ValueError: unknown ``comparison_type``
    """
    checks = {
        'equals': (actual == expected, '=='),
        'greater': (actual > expected, '>'),
        'less': (actual < expected, '<'),
        'greater_equal': (actual >= expected, '>='),
        'less_equal': (actual <= expected, '<='),
    }
    if comparison_type not in checks:
        raise ValueError(f"invalid comparison_type {comparison_type!r} (allowed: {', '.join(COMPARISON_TYPES)})")
    ok, op = checks[comparison_type]
    verdict = 'holds' if ok else 'does not hold'
    return ok, f'count {actual} {op} {expected} {verdict}'


def count_parameter_errors(expected_count: Any, comparison_type: str) -> list[str]:
    """Problems with ``expected_count`` / ``comparison_type``; empty when both are valid."""
    errors = []
    if isinstance(expected_count, bool) or not isinstance(expected_count, int) or expected_count < 0:
        errors.append(f'expected_count must be a non-negative integer, got {expected_count!r}')
    if comparison_type not in COMPARISON_TYPES:
        errors.append(f"invalid comparison_type {comparison_type!r} (allowed: {', '.join(COMPARISON_TYPES)})")
    return errors


def _candidates(values: list[Any]) -> list[Any]:
    """Values to compare: a path that selects exactly one array compares its elements."""
    if len(values) == 1 and isinstance(values[0], list):
        return values[0]
    return values


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def load_data(ctx: Any, dst: str, fmt: StructuredFormat) -> tuple[Any, TestResult | None]:
    """Resolve ``dst`` and load it; return ``(data, None)`` or ``(None, error_result)``."""
    path, status = ctx.resolve_globfilepath(dst)
    if not path:
        return None, TestResult.error([f'{fmt.label} file {dst} not found ({status})'])
    log.debug(f'dst file {path} will be used for this {fmt.label} test')
    try:
        data = fmt.load(path)
    except FileNotFoundError:
        return None, TestResult.error([f'{fmt.label} file {path} does not exist'])
    except IsADirectoryError:
        return None, TestResult.error([f'{fmt.label} file {path} is a directory'])
    except UnicodeDecodeError as e:
        return None, TestResult.execution_error(e, f'Cannot decode {fmt.label} file {path}')
    except LookupError as e:
        return None, TestResult.error([f'unknown encoding for {fmt.label} file {path}: {e}'])
    except fmt.errors as e:
        return None, TestResult.execution_error(e, f'Invalid {fmt.label} in file {path}')
    except OSError as e:
        return None, TestResult.execution_error(e, f'Cannot read {fmt.label} file {path}')
    return normalize(data), None


# ---------------------------------------------------------------------------
# Testfunction bodies
# ---------------------------------------------------------------------------


def contains_key(ctx: Any, dst: str, key_path: str, fmt: StructuredFormat) -> TestResult:
    """Pass when ``key_path`` selects at least one value (a null value counts)."""
    data, error = load_data(ctx, dst, fmt)
    if error is not None:
        return error
    values = resolve_key_path(data, key_path)
    if not values:
        return TestResult.failed([f'key path "{key_path}" does not exist'])
    shown = values[0] if len(values) == 1 else values
    return TestResult.success([f'key path "{key_path}" exists with value: {text(shown)}'])


def value_matches(
    ctx: Any,
    dst: str,
    key_path: str,
    expected_value: Any,
    fmt: StructuredFormat,
    regex_match: bool = False,
    wildcard_mode: str = 'any',
    **ordered_parameters: Any,
) -> TestResult:
    """Pass when the value(s) at ``key_path`` match ``expected_value`` (``wildcard_mode``: any/all).

    ``ordered_parameters`` (``comparison_type``, ``value_type``, ``tolerance``, time parameters;
    see :mod:`adarelib.testset.valuecompare`) switch to an ordered comparison when one is set.
    """
    if wildcard_mode not in WILDCARD_MODES:
        return TestResult.error([f"Invalid wildcard_mode: {wildcard_mode}. Must be 'any' or 'all'"])
    from adarelib.testset.valuecompare import ordered_setup  # imports this module

    ordered, problem = ordered_setup(ctx, expected_value, regex_match, **ordered_parameters)
    if problem is not None:
        return problem
    data, error = load_data(ctx, dst, fmt)
    if error is not None:
        return error
    values = resolve_key_path(data, key_path)
    if not values:
        return TestResult.failed([f'key path "{key_path}" does not exist'])
    candidates = _candidates(values)
    expected = normalize(expected_value)
    try:
        if ordered is not None:
            results = [(v, *ordered.compare(v, expected)) for v in candidates]
        else:
            results = [(v, *compare_value(ctx, v, expected, regex_match)) for v in candidates]
    except (re.error, OrderingError) as e:
        return TestResult.error([str(e)])
    if not results:
        return TestResult.failed([f'key path "{key_path}" selects an empty array'])
    if len(results) == 1:
        _, ok, message = results[0]
        return TestResult.success([message]) if ok else TestResult.failed([message])

    matching = [i for i, (_, ok, _) in enumerate(results) if ok]
    head = f'path "{key_path}" matched {len(matching)}/{len(results)} values (mode: {wildcard_mode})'
    passed = bool(matching) if wildcard_mode == 'any' else len(matching) == len(results)
    if passed:
        shown = [f'element[{i}]: {text(results[i][0])}' for i in matching[:3]]
        return TestResult.success([head, f'matching values: {", ".join(shown)}'])
    misses = [f'element[{i}]: {text(v)}' for i, (v, ok, _) in enumerate(results) if not ok][:5]
    return TestResult.failed([head, f'expected: "{expected_value}"', f'non-matching values: {", ".join(misses)}'])


def value_count(
    ctx: Any,
    dst: str,
    key_path: str,
    expected_count: int,
    fmt: StructuredFormat,
    expected_value: Any = None,
    regex_match: bool = False,
    comparison_type: str = 'equals',
) -> TestResult:
    """Pass when the number of values at ``key_path`` (matching ``expected_value``, if given)
    satisfies ``comparison_type`` against ``expected_count``. ``0`` = the key / value is absent."""
    problems = count_parameter_errors(expected_count, comparison_type)
    if problems:
        return TestResult.error(problems)
    data, error = load_data(ctx, dst, fmt)
    if error is not None:
        return error
    values = resolve_key_path(data, key_path)
    if expected_value is None:
        actual = len(values)
        what = f'{actual} value(s) at "{key_path}"'
    else:
        expected = normalize(expected_value)
        try:
            actual = sum(1 for v in _candidates(values) if compare_value(ctx, v, expected, regex_match)[0])
        except re.error as e:
            return TestResult.error([str(e)])
        what = f'{actual} value(s) at "{key_path}" match "{expected_value}"'
    ok, message = compare_count(actual, expected_count, comparison_type)
    details = [what, message]
    return TestResult.success(details) if ok else TestResult.failed(details)
