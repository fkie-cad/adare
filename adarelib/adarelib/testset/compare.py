"""
Comparison helpers shared by the built-in testfunction collections.

Collections are uploaded to the guest fresh for every run, while this module
ships with the agent's adarelib wheel; since agent wheels are versioned by
content hash, a run that uploads collections using these helpers also
installs the adarelib that has them. Keep it standard-library only and
importable on Python 3.10 (the guest's floor).
"""

import logging
from typing import Any

from adarelib.event.event import TestResult
from adarelib.testset.basictest import PlaceholderError

log = logging.getLogger(__name__)

# What a placeholder comparison raises for a value it cannot interpret (an
# unparsable timestamp, a malformed interval, a non-string value). It is a
# problem of the test definition, so the helpers below turn it into a
# PlaceholderError, which the @testfunction decorator reports as ERROR.
PLACEHOLDER_ERRORS = (KeyError, ValueError, TypeError)


def compare_placeholder(ctx: Any, placeholder_name: str, actual: str) -> tuple[bool, str]:
    """``ctx.compare_with_placeholder`` with every evaluation problem raised as ``PlaceholderError``."""
    try:
        return ctx.compare_with_placeholder(placeholder_name, actual)
    except PLACEHOLDER_ERRORS as e:
        raise PlaceholderError(f"cannot evaluate '{{{{ {placeholder_name} }}}}': {e}") from e


def compare_with_single_placeholder(ctx: Any, expected_str: str, actual: str) -> tuple[bool, str]:
    """Compare ``actual`` against an expected string that must contain exactly one placeholder.

    Raises ``PlaceholderError`` (an ERROR result) when ``expected_str`` has more than one
    placeholder, names an unknown one or holds an invalid regular expression.
    """
    placeholder_names = ctx.get_placeholders(expected_str)
    if len(placeholder_names) != 1:
        raise PlaceholderError(
            f"expected exactly one placeholder in {expected_str!r}, got {len(placeholder_names)}: "
            "a value is compared against a single !re or !timestamp"
        )
    return compare_placeholder(ctx, placeholder_names[0], actual)


def parse_key_path(key_path: str) -> list[tuple[str, Any]]:
    """Split a key path into steps ``('key', name)``, ``('values',)``, ``('all',)`` or ``('index', n)``.

    Syntax: dot-separated keys (``user.profile.name``); ``*`` as a key = all values of an
    object; ``[*]`` = all elements of an array; ``[n]`` = element ``n`` (negative counts from
    the end); ``['a.b']`` / ``["a.b"]`` = a key that contains dots or brackets. A path may
    start with a bracket to address a top-level array (``[0].name``, ``[*].id``). A ``[``
    that starts none of these is part of the key name. When resolving, an object key equal
    to a whole dot segment (``files[0]``) wins over the bracket syntax, as before brackets
    were supported.
    """
    return [step for _, steps in _segments(key_path) for step in steps]


def _segments(key_path: str) -> list[tuple[str, list[tuple[str, Any]]]]:
    """The dot segments of ``key_path`` as ``(raw text, steps)``; dots inside quotes do not split."""
    segments = []
    start = 0
    i = 0
    while i <= len(key_path):
        if i == len(key_path) or key_path[i] == '.':
            raw = key_path[start:i]
            segments.append((raw, _segment_steps(raw)))
            start = i + 1
            i += 1
            continue
        if key_path[i] == '[':
            bracket = _parse_bracket(key_path, i)
            if bracket is not None:
                i = bracket[1]
                continue
        i += 1
    return segments


def _segment_steps(segment: str) -> list[tuple[str, Any]]:
    """Steps of one dot segment: an optional key, then any number of brackets."""
    steps: list[tuple[str, Any]] = []
    buf: list[str] = []
    i = 0
    after_bracket = False
    while i < len(segment):
        if segment[i] == '[':
            bracket = _parse_bracket(segment, i)
            if bracket is not None:
                if buf:
                    steps.append(_key_step(''.join(buf)))
                    buf = []
                steps.append(bracket[0])
                i = bracket[1]
                after_bracket = True
                continue
        buf.append(segment[i])
        i += 1
    if buf or not after_bracket:
        steps.append(_key_step(''.join(buf)))
    return steps


def _key_step(name: str) -> tuple[str, Any]:
    return ('values',) if name == '*' else ('key', name)


def _parse_bracket(path: str, start: int) -> tuple[tuple[str, Any], int] | None:
    """Parse the bracket at ``start``; return (step, index after it) or None if it is no syntax."""
    if path[start + 1 : start + 2] in ("'", '"'):
        quote = path[start + 1]
        close = path.find(quote + ']', start + 2)
        if close == -1:
            return None
        return ('key', path[start + 2 : close]), close + 2
    close = path.find(']', start + 1)
    if close == -1:
        return None
    inner = path[start + 1 : close]
    if inner == '*':
        return ('all',), close + 1
    digits = inner[1:] if inner.startswith('-') else inner
    if digits.isdigit() and digits.isascii():
        return ('index', int(inner)), close + 1
    return None


def _apply_step(value: Any, step: tuple[str, Any], out: list[Any]) -> None:
    kind = step[0]
    if kind == 'key':
        if isinstance(value, dict) and step[1] in value:
            out.append(value[step[1]])
    elif kind == 'values':
        if isinstance(value, dict):
            out.extend(value.values())
    elif kind == 'all':
        if isinstance(value, list):
            out.extend(value)
    elif isinstance(value, list) and -len(value) <= step[1] < len(value):
        out.append(value[step[1]])


def resolve_key_path(data: Any, key_path: str) -> list[Any]:
    """All values ``key_path`` (syntax: :func:`parse_key_path`) selects in ``data``; empty if none."""
    current = [data]
    for raw, steps in _segments(key_path):
        nxt: list[Any] = []
        for value in current:
            if '[' in raw and isinstance(value, dict) and raw in value:
                nxt.append(value[raw])  # a literal key such as 'files[0]'
                continue
            selected = [value]
            for step in steps:
                stepped: list[Any] = []
                for item in selected:
                    _apply_step(item, step, stepped)
                selected = stepped
            nxt.extend(selected)
        if not nxt:
            return []
        current = nxt
    return current


def get_nested_value(data, key_path):
    """Navigate nested data with a key path (syntax: :func:`parse_key_path`).

    Supports:
    - [*] for all array elements (e.g., "users[*].name")
    - * for all object keys (e.g., "config.*.enabled")
    - [n] for one array element, a leading [..] for a top-level array, ['a.b'] for keys with dots

    Returns:
    - For exact paths: (value, True) or ([], False)
    - For wildcard paths: (list_of_values, True) or ([], False)
    """
    values = resolve_key_path(data, key_path)
    if not values:
        return [], False
    if len(values) > 1:
        return values, True
    return values[0], True


def extract_columns(row: list[str], columns: list[int] | None) -> list[str]:
    """Extract selected columns from row, or return all if columns is None."""
    if columns is None:
        return row
    return [row[i] for i in columns if i < len(row)]


def row_matches_pattern(test_instance, row, entry_pattern):
    """Check if a row matches the expected pattern using placeholder system.

    Returns:
        tuple: (is_match: bool, failed_columns: list, column_count_match: bool)
    """
    column_count_match = len(row) == len(entry_pattern)
    if not column_count_match:
        log.info(
            f"Row column count mismatch: got {len(row)} columns {row}, expected {len(entry_pattern)} columns {entry_pattern}"
        )
        return False, [f"column_count({len(row)} != {len(entry_pattern)})"], False

    failed_columns = []

    # Check each column individually
    for i, (actual_value, expected_pattern) in enumerate(zip(row, entry_pattern, strict=False)):
        expected_str = str(expected_pattern)

        if test_instance.has_placeholders(expected_str):
            success, message = compare_with_single_placeholder(test_instance, expected_str, actual_value)
            if not success:
                failed_columns.append(f"col{i}({message})")
        else:
            # Direct string comparison
            if actual_value != expected_str:
                failed_columns.append(f"col{i}('{actual_value}' != '{expected_str}')")

    is_match = len(failed_columns) == 0

    # Log failures only if there were any
    if failed_columns:
        log.info(f"Row {row} failed pattern match: {', '.join(failed_columns)}")

    return is_match, failed_columns, column_count_match


def compare_row_sets(
    test_instance,
    actual_rows: list[list[str]],
    reference_rows: list[list[str]],
    columns: list[int] | None,
    allow_extra: bool,
    allow_missing: bool,
    label: str = 'CSV',
) -> TestResult:
    """
    Compare rows as sets (ignore_order=True).

    Algorithm:
    1. Extract selected columns from all rows
    2. Build sets of actual and reference rows (handling placeholders)
    3. Find missing rows (in reference but not in actual)
    4. Find extra rows (in actual but not in reference)
    5. Generate detailed diff report
    """
    # Extract selected columns from all rows
    actual_extracted = [extract_columns(row, columns) for row in actual_rows]
    reference_extracted = [extract_columns(row, columns) for row in reference_rows]

    # Find matches using placeholder-aware comparison
    matched_actual_indices = set()
    matched_reference_indices = set()

    for ref_idx, ref_row in enumerate(reference_extracted):
        # Check if reference row has placeholders
        has_placeholders = any(test_instance.has_placeholders(str(col)) for col in ref_row)

        for act_idx, act_row in enumerate(actual_extracted):
            if act_idx in matched_actual_indices:
                continue

            if has_placeholders:
                # Use placeholder comparison
                is_match, _, _ = row_matches_pattern(test_instance, act_row, ref_row)
                if is_match:
                    matched_actual_indices.add(act_idx)
                    matched_reference_indices.add(ref_idx)
                    break
            else:
                # Direct comparison
                if act_row == ref_row:
                    matched_actual_indices.add(act_idx)
                    matched_reference_indices.add(ref_idx)
                    break

    # Find missing and extra rows
    missing_rows = [
        (i, reference_extracted[i]) for i in range(len(reference_extracted)) if i not in matched_reference_indices
    ]
    extra_rows = [(i, actual_extracted[i]) for i in range(len(actual_extracted)) if i not in matched_actual_indices]

    # Check if comparison passes
    has_failures = False
    if missing_rows and not allow_missing:
        has_failures = True
    if extra_rows and not allow_extra:
        has_failures = True

    if not has_failures:
        return TestResult.success()

    # Generate detailed diff report
    details = format_diff_report(
        missing_rows=missing_rows,
        extra_rows=extra_rows,
        mismatched_rows=[],
        actual_count=len(actual_rows),
        reference_count=len(reference_rows),
        columns=columns,
        label=label,
    )

    return TestResult.failed(details)


def compare_row_sequences(
    test_instance,
    actual_rows: list[list[str]],
    reference_rows: list[list[str]],
    columns: list[int] | None,
    allow_extra: bool,
    allow_missing: bool,
    label: str = 'CSV',
) -> TestResult:
    """
    Compare rows as ordered sequences (ignore_order=False).

    Algorithm:
    1. Extract selected columns from all rows
    2. Compare row-by-row in order
    3. Track position mismatches
    4. Track missing rows (reference rows past end of actual)
    5. Track extra rows (actual rows past end of reference)
    6. Generate detailed diff report with row indices
    """
    # Extract selected columns from all rows
    actual_extracted = [extract_columns(row, columns) for row in actual_rows]
    reference_extracted = [extract_columns(row, columns) for row in reference_rows]

    mismatched_rows = []
    missing_rows = []
    extra_rows = []

    # Compare rows up to the minimum length
    min_length = min(len(actual_extracted), len(reference_extracted))

    for i in range(min_length):
        act_row = actual_extracted[i]
        ref_row = reference_extracted[i]

        # Check if reference row has placeholders
        has_placeholders = any(test_instance.has_placeholders(str(col)) for col in ref_row)

        if has_placeholders:
            # Use placeholder comparison
            is_match, failed_columns, _ = row_matches_pattern(test_instance, act_row, ref_row)
            if not is_match:
                mismatched_rows.append((i, act_row, ref_row, failed_columns))
        else:
            # Direct comparison
            if act_row != ref_row:
                # Find which columns differ
                failed_columns = []
                for col_idx in range(min(len(act_row), len(ref_row))):
                    if act_row[col_idx] != ref_row[col_idx]:
                        failed_columns.append(f"col{col_idx}('{act_row[col_idx]}' != '{ref_row[col_idx]}')")

                # Check for column count mismatch
                if len(act_row) != len(ref_row):
                    failed_columns.append(f"column_count({len(act_row)} != {len(ref_row)})")

                mismatched_rows.append((i, act_row, ref_row, failed_columns))

    # Handle missing rows (reference has more rows than actual)
    if len(reference_extracted) > len(actual_extracted):
        for i in range(len(actual_extracted), len(reference_extracted)):
            missing_rows.append((i, reference_extracted[i]))

    # Handle extra rows (actual has more rows than reference)
    if len(actual_extracted) > len(reference_extracted):
        for i in range(len(reference_extracted), len(actual_extracted)):
            extra_rows.append((i, actual_extracted[i]))

    # Check if comparison passes
    has_failures = False
    if mismatched_rows:
        has_failures = True
    if missing_rows and not allow_missing:
        has_failures = True
    if extra_rows and not allow_extra:
        has_failures = True

    if not has_failures:
        return TestResult.success()

    # Generate detailed diff report
    details = format_diff_report(
        missing_rows=missing_rows,
        extra_rows=extra_rows,
        mismatched_rows=mismatched_rows,
        actual_count=len(actual_rows),
        reference_count=len(reference_rows),
        columns=columns,
        label=label,
    )

    return TestResult.failed(details)


def format_diff_report(
    missing_rows: list[tuple[int, list[str]]],
    extra_rows: list[tuple[int, list[str]]],
    mismatched_rows: list[tuple[int, list[str], list[str], list[str]]],
    actual_count: int,
    reference_count: int,
    columns: list[int] | None,
    label: str = 'CSV',
) -> list[str]:
    """
    Format detailed comparison report for test failure.

    Returns list of detail strings:
    - Summary: "<label> comparison failed: X missing, Y extra, Z mismatched"
    - Row counts: "Actual: X rows, Reference: Y rows"
    - Column selection info if columns specified
    - Missing rows section with details
    - Extra rows section with details
    - Mismatched rows with column-by-column diff
    """
    details = []

    # Build summary line
    summary_parts = []
    if mismatched_rows:
        summary_parts.append(f"{len(mismatched_rows)} mismatched row{'s' if len(mismatched_rows) != 1 else ''}")
    if missing_rows:
        summary_parts.append(f"{len(missing_rows)} missing row{'s' if len(missing_rows) != 1 else ''}")
    if extra_rows:
        summary_parts.append(f"{len(extra_rows)} extra row{'s' if len(extra_rows) != 1 else ''}")

    summary = f"{label} comparison failed: " + ", ".join(summary_parts)
    details.append(summary)
    details.append(f"Actual: {actual_count} rows, Reference: {reference_count} rows")

    # Add column selection info
    if columns is not None:
        details.append(f"Checking columns: {columns} (indices)")
    else:
        details.append("Checking all columns")

    # Add mismatched rows section
    if mismatched_rows:
        details.append("")
        details.append("Mismatched rows:")
        for row_idx, act_row, ref_row, failed_columns in mismatched_rows:
            details.append(f"  Row {row_idx} mismatch:")
            details.append(f"    Actual:    {act_row}")
            details.append(f"    Reference: {ref_row}")
            details.append(f"    Failures: {', '.join(failed_columns)}")

    # Add missing rows section
    if missing_rows:
        details.append("")
        details.append("Missing rows (in reference but not in actual):")
        for row_idx, row in missing_rows:
            details.append(f"  [{row_idx}] {row}")

    # Add extra rows section
    if extra_rows:
        details.append("")
        details.append("Extra rows (in actual but not in reference):")
        for row_idx, row in extra_rows:
            details.append(f"  [{row_idx}] {row}")

    return details
