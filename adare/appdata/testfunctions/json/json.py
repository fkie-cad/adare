# external imports
import json

# internal imports
from adarelib.testset.api import testfunction
from adarelib.testset.basictest import HostModeCategory
from adarelib.event.event import TestResult
from adarelib.testset.compare import get_nested_value
from adarelib.testset.content import decode_text
from adarelib.testset.structured import StructuredFormat, compare_value, load_data
from adarelib.testset.structured import value_count as _structured_value_count

# configure logging
import logging

log = logging.getLogger(__name__)


def _load_json(path: str, encoding: str | None = None):
    """Parse JSON file ``path``. Without ``encoding`` the parser gets the bytes and detects
    UTF-8/16/32 (with or without BOM); with one, a BOM still wins."""
    with open(path, 'rb') as f:
        raw = f.read()
    return json.loads(raw if encoding is None else decode_text(raw, encoding))


def _json_format(encoding: str | None) -> StructuredFormat:
    return StructuredFormat(label='JSON', load=lambda path: _load_json(path, encoding), errors=(json.JSONDecodeError,))


def _handle_wildcard_matching(ctx, values, expected_value, wildcard_mode, key_path, regex_match=False):
    """Handle matching logic for wildcard results with 'any' or 'all' modes"""
    if not values:
        return TestResult.failed([f'no values found for wildcard path "{key_path}"'])

    # Validate wildcard_mode
    if wildcard_mode not in ['any', 'all']:
        return TestResult.execution_error(None, f"Invalid wildcard_mode: {wildcard_mode}. Must be 'any' or 'all'")

    matches = []
    non_matches = []

    # Check each value against expected using unified comparison method
    for i, value in enumerate(values):
        is_match, message = compare_value(ctx, value, expected_value, regex_match=regex_match)
        if is_match:
            matches.append((i, value, message))
        else:
            non_matches.append((i, value, message))

    # Apply wildcard mode logic
    if wildcard_mode == 'any':
        if matches:
            match_details = [f"element[{i}]: {val}" for i, val, _ in matches[:3]]  # Show first 3 matches
            if len(matches) > 3:
                match_details.append(f"... and {len(matches) - 3} more matches")
            return TestResult.success(
                [
                    f'wildcard path "{key_path}" matched {len(matches)}/{len(values)} values (mode: any)',
                    f'matching values: {", ".join(match_details)}',
                ]
            )
        return TestResult.failed(
            [
                f'wildcard path "{key_path}" matched 0/{len(values)} values (mode: any)',
                f'expected: "{expected_value}"',
                f'got values: {[val for _, val, _ in non_matches[:5]]}',  # Show first 5 non-matches
            ]
        )
    # wildcard_mode == 'all'
    if not non_matches:
        return TestResult.success(
            [
                f'wildcard path "{key_path}" matched all {len(values)} values (mode: all)',
                f'all values equal: "{expected_value}"',
            ]
        )
    non_match_details = [f"element[{i}]: {val}" for i, val, _ in non_matches[:3]]  # Show first 3 non-matches
    if len(non_matches) > 3:
        non_match_details.append(f"... and {len(non_matches) - 3} more non-matches")
    return TestResult.failed(
        [
            f'wildcard path "{key_path}" matched {len(matches)}/{len(values)} values (mode: all)',
            f'expected: "{expected_value}"',
            f'non-matching values: {", ".join(non_match_details)}',
        ]
    )


@testfunction(
    name='contains_key',
    description='tests if JSON file contains specified key path (supports dot notation like "user.profile.name")',
    category=HostModeCategory.FILE_CONTENT,
)
def contains_key(ctx, dst: str, key_path: str, encoding: str | None = None):
    """Pass when ``key_path`` resolves to at least one value in JSON file ``dst`` (``null`` counts).

    Use for: checking a settings/config file gained a key. To also check the value use
    json.value_matches. Absence of a key: ``expect_to_fail: true`` here, or json.value_count
    with ``expected_count: 0``.

    Args:
        dst: Guest path to the JSON file; a glob must match exactly one path. A missing file
            or invalid JSON is an error. LZ4-compressed JSON is read through the archive
            separator (``/home/user/data/store.jsonlz4!``).
        key_path: Dot path from the root, e.g. ``user.profile.name``. ``*`` expands all
            values of an object (``config.*.enabled``), ``[*]`` all elements of an array
            (``users[*].email``), ``[n]`` one element (``items[0]``; ``items[-1]`` = last).
            A leading bracket addresses a top-level array (``[0].name``, ``[*].id``);
            ``['a.b']`` quotes a key that contains dots or brackets.
        encoding: ``None`` (default) detects UTF-8/16/32 with or without BOM; a name
            (``latin-1``) decodes BOM-less files with it. Unknown names are an error.

    Example:
        function: json.contains_key
        parameter:
          dst: /home/user/data/settings.json
          key_path: display.fontSize
    """
    data, error = load_data(ctx, dst, _json_format(encoding))
    if error is not None:
        return error
    value, exists = get_nested_value(data, key_path)
    if exists:
        return TestResult.success([f'key path "{key_path}" exists with value: {value}'])
    return TestResult.failed([f'key path "{key_path}" does not exist'])


@testfunction(
    name='value_matches',
    description='tests if JSON value at key path matches expected value using placeholders (supports wildcards [*] and * with any/all modes)',
    category=HostModeCategory.FILE_CONTENT,
)
def value_matches(
    ctx,
    dst: str,
    key_path: str,
    expected_value: str | int | float | bool | None,
    regex_match: bool = False,
    wildcard_mode: str = "any",
    encoding: str | None = None,
):
    """Pass when the JSON value at ``key_path`` in ``dst`` equals (or matches) ``expected_value``.

    Use for: asserting a setting/field value. If the path yields several values (a wildcard,
    or a JSON array value, whose elements are then compared one by one) ``wildcard_mode``
    decides; a one-element array is unwrapped. Whole arrays cannot be compared. To assert
    that no value matches use json.value_count with ``expected_count: 0``.

    Args:
        dst: Guest path to the JSON file; a glob must match exactly one path. A missing file or
            invalid JSON is an error; an unresolvable key path fails. ``x.jsonlz4!`` reads
            LZ4-compressed JSON.
        key_path: Dot path from the root, e.g. ``user.profile.name``. ``*`` expands all
            values of an object (``config.*.enabled``), ``[*]`` all elements of an array
            (``users[*].email``), ``[n]`` one element (``items[0]``; ``items[-1]`` = last).
            A leading bracket addresses a top-level array (``[0].name``, ``[*].id``);
            ``['a.b']`` quotes a key that contains dots or brackets.
        expected_value: Required. Compared with Python ``==``, which is type-sensitive (``5`` != ``"5"``;
            a JSON ``null`` needs ``expected_value: null``). A ``!re``/``!timestamp`` tag compares
            ``str(value)`` by type; an invalid regex or unknown placeholder is an error.
        regex_match: Treat a string ``expected_value`` as a regex searched (``re.search``,
            unanchored) in ``str(value)``.
        wildcard_mode: ``any`` (default): one value must match; ``all``: every value must
            match. Other values are an error.
        encoding: ``None`` (default) detects UTF-8/16/32 with or without BOM; a name
            (``latin-1``) decodes BOM-less files with it. Unknown names are an error.

    Example:
        function: json.value_matches
        parameter:
          dst: /home/user/data/settings.json
          key_path: groups[*].items[*].title
          expected_value: Example Entry
    """
    if wildcard_mode not in ('any', 'all'):
        return TestResult.error([f"Invalid wildcard_mode: {wildcard_mode}. Must be 'any' or 'all'"])
    data, error = load_data(ctx, dst, _json_format(encoding))
    if error is not None:
        return error

    value, exists = get_nested_value(data, key_path)
    if not exists:
        return TestResult.failed([f'key path "{key_path}" does not exist'])

    if isinstance(value, list) and len(value) > 1:
        # several values (a wildcard or an array value): wildcard_mode decides
        return _handle_wildcard_matching(ctx, value, expected_value, wildcard_mode, key_path, regex_match=regex_match)
    if isinstance(value, list) and len(value) == 1:
        value = value[0]

    is_match, message = compare_value(ctx, value, expected_value, regex_match=regex_match)
    return TestResult.success([message]) if is_match else TestResult.failed([message])


@testfunction(
    name='array_contains',
    description='tests if JSON array at specified path contains expected element',
    category=HostModeCategory.FILE_CONTENT,
)
def array_contains(
    ctx,
    dst: str,
    array_path: str,
    expected_value: str | int | float | bool | dict | list | None,
    encoding: str | None = None,
):
    """Pass when the JSON array at ``array_path`` in ``dst`` contains ``expected_value``.

    Use for: checking that a list in a JSON file includes an entry. To count entries use
    json.value_count (``array_path[*]`` as key path).

    Args:
        dst: Guest path to the JSON file; a glob must match exactly one path. A missing file or
            invalid JSON is an error; an unresolvable path or non-array value fails.
            ``x.jsonlz4!`` reads LZ4-compressed JSON.
        array_path: Dot path to the array (same syntax as json.value_matches ``key_path``);
            a wildcard yielding several values is treated as the array of those values.
        expected_value: Required. An element equal to it (type-sensitive ``==``; dicts and lists
            must match exactly). A ``!re``/``!timestamp`` tag passes if any element's ``str()``
            matches; an invalid regex or unknown placeholder is an error.
        encoding: ``None`` (default) detects UTF-8/16/32 with or without BOM; a name
            (``latin-1``) decodes BOM-less files with it. Unknown names are an error.

    Example:
        function: json.array_contains
        parameter:
          dst: /home/user/.config/app/recent.json
          array_path: recent_files
          expected_value: /home/user/Documents/report.odt
    """
    data, error = load_data(ctx, dst, _json_format(encoding))
    if error is not None:
        return error

    array, exists = get_nested_value(data, array_path)
    if not exists:
        return TestResult.failed([f'array path "{array_path}" does not exist'])
    if not isinstance(array, list):
        return TestResult.failed([f'path "{array_path}" is not an array, got {type(array).__name__}'])

    for i, element in enumerate(array):
        is_match, message = compare_value(ctx, element, expected_value)
        if is_match:
            return TestResult.success([f'array element [{i}] matches: {message}'])
    return TestResult.failed(
        [f'array "{array_path}" ({len(array)} elements) has no element matching {expected_value!r}']
    )


@testfunction(
    name='value_count',
    description='tests the number of JSON values at a key path (optionally only those matching a value)',
    category=HostModeCategory.FILE_CONTENT,
)
def value_count(
    ctx,
    dst: str,
    key_path: str,
    expected_count: int,
    expected_value: str | int | float | bool | None = None,
    regex_match: bool = False,
    comparison_type: str = 'equals',
    encoding: str | None = None,
):
    """Pass when the number of values at ``key_path`` in JSON file ``dst`` satisfies ``comparison_type``.

    Use for: counting entries (e.g. exactly 3 bookmarks with a given tag) and asserting
    absence: ``expected_count: 0`` without ``expected_value`` passes when the key path selects
    nothing, with ``expected_value`` when no value matches.

    Args:
        dst: Guest path to the JSON file; a glob must match exactly one path. A missing file or
            invalid JSON is an error. ``x.jsonlz4!`` reads LZ4-compressed JSON.
        key_path: Dot path from the root, e.g. ``user.profile.name``. ``*`` expands all
            values of an object (``config.*.enabled``), ``[*]`` all elements of an array
            (``users[*].email``), ``[n]`` one element (``items[0]``; ``items[-1]`` = last).
            A leading bracket addresses a top-level array (``[0].name``, ``[*].id``);
            ``['a.b']`` quotes a key that contains dots or brackets.
        expected_count: Non-negative integer to compare against; anything else is an error.
        expected_value: ``None`` (default) counts the values the path selects (a ``null``
            value counts; an array is one value, ``items[*]`` counts its elements). Otherwise
            counts the values equal to it (type-sensitive ``==``; ``!re``/``!timestamp`` tags
            compare ``str(value)``; an invalid regex or unknown placeholder is an error); a path
            that selects exactly one array compares its elements one by one.
        regex_match: Treat a string ``expected_value`` as a regex searched (``re.search``,
            unanchored) in ``str(value)``; an invalid regex is an error.
        comparison_type: ``equals`` (default), ``greater``, ``less``, ``greater_equal`` or
            ``less_equal``; other values are an error.
        encoding: ``None`` (default) detects UTF-8/16/32 with or without BOM; a name
            (``latin-1``) decodes BOM-less files with it. Unknown names are an error.

    Example:
        function: json.value_count
        parameter:
          dst: /home/user/data/settings.json
          key_path: groups[*].items[*].tag
          expected_value: archived
          expected_count: 3
    """
    return _structured_value_count(
        ctx,
        dst,
        key_path,
        expected_count,
        _json_format(encoding),
        expected_value=expected_value,
        regex_match=regex_match,
        comparison_type=comparison_type,
    )
