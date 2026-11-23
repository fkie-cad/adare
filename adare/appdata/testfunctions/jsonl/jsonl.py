# external imports
from pathlib import Path
import json
import os
from typing import Optional

# internal imports
from adarelib.testset.api import testfunction, TestContext
from adarelib.testset.basictest import HostModeCategory
from adarelib.event.event import TestResult
from adarelib.testset.compare import get_nested_value
from adarelib.testset.content import open_text
from adarelib.testset.structured import compare_count, compare_value, count_parameter_errors
from adarelib.testset.ordering import OrderingError
from adarelib.testset.valuecompare import ordered_setup

# configure logging
import logging

log = logging.getLogger(__name__)


def _compare_values(test_instance, actual_value, expected_value, regex_match=False, ordered=None):
    """Compare one value like structured.compare_value; with ``regex_match`` the value ``"*"`` means "key exists".

    ``ordered`` (an ordered comparison, see adarelib.testset.valuecompare) replaces both.
    """
    if ordered is not None:
        return ordered.compare(actual_value, expected_value)
    if regex_match and expected_value == "*":
        return True, f'field exists with value "{actual_value}"'
    return compare_value(test_instance, actual_value, expected_value, regex_match=regex_match)


def _count_range(expected_count) -> tuple[int, float] | None:
    """``(min, max)`` of a ``{min, max}`` expected_count, or None when it is not a valid range."""
    if not isinstance(expected_count, dict) or not expected_count or set(expected_count) - {'min', 'max'}:
        return None
    bounds = [expected_count.get('min', 0), expected_count.get('max', 0)]
    if any(isinstance(b, bool) or not isinstance(b, int) or b < 0 for b in bounds):
        return None
    low, high = expected_count.get('min', 0), expected_count.get('max', float('inf'))
    return (low, high) if low <= high else None


_ENCODING_ERRORS = (LookupError, UnicodeDecodeError)


def _encoding_error(e: Exception, dst: str, encoding: str | None) -> TestResult:
    if isinstance(e, UnicodeDecodeError):
        return TestResult.execution_error(e, f'Cannot decode JSONL file {dst} as {encoding or "UTF-8/UTF-16"}')
    return TestResult.error([f'unknown encoding {encoding!r}: {e}'])


@testfunction(
    name='line_matches',
    description='tests if lines in JSONL file match specified conditions (supports any/all modes)',
    category=HostModeCategory.FILE_CONTENT,
)
def line_matches(
    ctx: TestContext,
    dst: str = '',
    conditions: dict[str, str | int | float | bool | None] = None,
    wildcard_mode: str = "any",
    regex_match: bool = False,
    skip_malformed: bool = True,
    encoding: str | None = None,
):
    """Pass when one line (``any``) or every valid line (``all``) of JSONL file ``dst`` meets all ``conditions``.

    Use for: event logs / NDJSON exports (e.g. "a line with type=login and user=alice exists").
    To count matches use jsonl.line_count.

    Args:
        dst: Guest path to the JSONL file (one JSON document per line; blank lines are
            skipped). A glob must match exactly one path; a missing file is an error, a 0-byte file fails.
        conditions: Required mapping ``key_path -> expected value``; a line matches when every
            condition holds. If a path yields several values (wildcard or JSON array), one
            matching element suffices. Missing keys fail the line.
        wildcard_mode: ``any`` (default) or ``all`` (every valid line must match; no valid lines
            fails). Other values are an error.
        regex_match: Treat string expected values as regexes searched (``re.search``) in
            ``str(value)``; the value ``"*"`` then means "key exists". Without it, values
            are compared with type-sensitive ``==``; ``!re``/``!timestamp`` tags always work.
        skip_malformed: ``True`` (default) ignores lines that are not valid JSON; ``False``
            makes the first malformed line an error.
        encoding: ``None`` (default) detects a BOM (UTF-8/16/32) and BOM-less UTF-16, else
            reads UTF-8; a name reads BOM-less files with it. Unknown names or undecodable
            content are an error.

    Example:
        function: jsonl.line_matches
        parameter:
          dst: /var/log/app/events.jsonl
          conditions:
            event: login
            user.name: alice
    """
    dst_param = dst
    dst, status = ctx.resolve_globfilepath(dst)
    if not dst:
        return TestResult.error([f'JSONL file {dst_param} not found ({status})'])

    log.debug(f'dst file {dst} will be used for test line_matches')

    wildcard_mode = wildcard_mode or "any"
    regex_match = regex_match or False

    if wildcard_mode not in ['any', 'all']:
        return TestResult.error([f"Invalid wildcard_mode: {wildcard_mode}. Must be 'any' or 'all'"])
    if not isinstance(conditions, dict) or not conditions:
        return TestResult.error(
            [f'conditions must be a non-empty mapping key_path -> expected value, got {conditions!r}']
        )

    try:
        # Check if file is empty (edge case handling)
        if os.path.getsize(dst) == 0:
            return TestResult.failed(['JSONL file is empty (0 bytes)'])
        matching_lines = []
        non_matching_lines = []
        malformed_lines = []
        line_num = 0

        with open_text(dst, encoding) as f:
            for line in f:
                line_num += 1
                line = line.strip()

                # Skip blank lines
                if not line:
                    continue

                # Try to parse JSON
                try:
                    data = json.loads(line)
                except json.JSONDecodeError as e:
                    malformed_lines.append((line_num, line[:100]))
                    if not skip_malformed:
                        return TestResult.execution_error(
                            e, f'Malformed JSON on line {line_num} (content: {line[:200]})'
                        )
                    continue

                # Check all conditions for this line
                all_conditions_met = True
                failed_conditions = []

                for key_path, expected_value in conditions.items():
                    value, exists = get_nested_value(data, key_path)

                    if not exists:
                        all_conditions_met = False
                        failed_conditions.append(f"{key_path} (not found)")
                        continue

                    # Handle multiple values from wildcards
                    if isinstance(value, list):
                        # Check if any value matches (for wildcards)
                        any_match = False
                        for v in value:
                            is_match, msg = _compare_values(ctx, v, expected_value, regex_match)
                            if is_match:
                                any_match = True
                                break
                        if not any_match:
                            all_conditions_met = False
                            failed_conditions.append(f"{key_path} (no wildcard matches)")
                    else:
                        # Single value comparison
                        is_match, msg = _compare_values(ctx, value, expected_value, regex_match)
                        if not is_match:
                            all_conditions_met = False
                            failed_conditions.append(f"{key_path} ({msg})")

                if all_conditions_met:
                    matching_lines.append((line_num, data))
                else:
                    non_matching_lines.append((line_num, data, failed_conditions))

        # Log malformed lines if any
        if malformed_lines:
            log.warning(f"Skipped {len(malformed_lines)} malformed JSON lines in {dst}")

        # Determine success based on wildcard_mode
        if wildcard_mode == "any":
            if matching_lines:
                messages = [
                    f'Found {len(matching_lines)} matching line(s) out of {line_num} total lines (mode: any)',
                    f'First matching line: {matching_lines[0][0]}',
                ]
                if len(matching_lines) > 1:
                    messages.append(f'Additional matches on lines: {[ln for ln, _ in matching_lines[1:4]]}')
                return TestResult.success(messages)
            messages = [
                'No lines matched all conditions (mode: any)',
                f'Analyzed {line_num} lines',
                f'Conditions: {conditions}',
            ]
            if non_matching_lines[:3]:
                messages.append('Sample non-matching lines:')
                for ln, _data, failed in non_matching_lines[:3]:
                    messages.append(f'  Line {ln}: failed {failed}')
            return TestResult.failed(messages)
        # wildcard_mode == "all"
        total_valid_lines = len(matching_lines) + len(non_matching_lines)
        if total_valid_lines == 0:
            return TestResult.failed(['No valid JSON lines found in file'])

        if len(matching_lines) == total_valid_lines:
            return TestResult.success(
                [f'All {total_valid_lines} lines matched conditions (mode: all)', f'Conditions: {conditions}']
            )
        messages = [
            f'Only {len(matching_lines)}/{total_valid_lines} lines matched (mode: all)',
            f'Conditions: {conditions}',
        ]
        if non_matching_lines[:3]:
            messages.append('Sample non-matching lines:')
            for ln, _data, failed in non_matching_lines[:3]:
                messages.append(f'  Line {ln}: failed {failed}')
        return TestResult.failed(messages)

    except FileNotFoundError:
        return TestResult.error([f'JSONL file {dst} does not exist'])
    except _ENCODING_ERRORS as e:
        return _encoding_error(e, dst, encoding)
    except (PermissionError, OSError) as e:
        return TestResult.execution_error(e, f"Cannot read JSONL file {dst}")


@testfunction(
    name='line_count',
    description='counts lines in JSONL file matching conditions and validates against expected count (if None, requires at least 1 match)',
    category=HostModeCategory.FILE_CONTENT,
)
def line_count(
    ctx: TestContext,
    dst: str = '',
    conditions: dict[str, str | int | float | bool | None] | None = None,
    expected_count: int | dict[str, int] | None = None,
    regex_match: bool = False,
    skip_malformed: bool = True,
    comparison_type: str = 'equals',
    encoding: str | None = None,
):
    """Pass when the number of JSONL lines meeting all ``conditions`` is within ``expected_count``.

    Use for: asserting how many records/events were written (e.g. exactly 3 deletions);
    absence: ``expected_count: 0``. For CSV records use csv.row_count, for lines of a plain
    text file text.line_count.

    Args:
        dst: Guest path to the JSONL file (one JSON document per line; blank lines are
            skipped). A glob must match exactly one path; a missing file is an error, a 0-byte file
            has 0 lines (passes ``expected_count: 0``).
        conditions: Mapping ``key_path -> expected value`` (all must hold; for multi-value
            paths one matching element suffices). ``None``/empty counts every valid JSON line.
        expected_count: Non-negative ``int`` compared with ``comparison_type``, ``{min: N, max: M}``
            for a range (either bound optional: min defaults to 0, max to unbounded), or ``None``
            for "at least 1". Anything else (a negative number, a boolean, other keys,
            min > max) is an error.
        regex_match: Treat string expected values as regexes searched (``re.search``) in
            ``str(value)``; the value ``"*"`` then means "key exists". Without it, values
            are compared with type-sensitive ``==``; ``!re``/``!timestamp`` tags always work.
        skip_malformed: ``True`` (default) ignores lines that are not valid JSON; ``False``
            makes the first malformed line an error.
        encoding: ``None`` (default) detects a BOM (UTF-8/16/32) and BOM-less UTF-16, else
            reads UTF-8; a name reads BOM-less files with it. Unknown names or undecodable
            content are an error.
        comparison_type: ``equals`` (default), ``greater``, ``less``, ``greater_equal`` or
            ``less_equal``, applied to an ``int`` ``expected_count``. With the range form or
            ``None`` only ``equals`` is allowed; other values are an error.

    Example:
        function: jsonl.line_count
        parameter:
          dst: /var/log/app/events.jsonl
          conditions: {event: file_deleted}
          expected_count: {min: 1, max: 5}
    """
    if isinstance(expected_count, int) and not isinstance(expected_count, bool):
        problems = count_parameter_errors(expected_count, comparison_type)
    elif expected_count is not None and _count_range(expected_count) is None:
        problems = [
            f'expected_count must be a non-negative integer, {{min: N, max: M}} (only these keys, '
            f'non-negative integers, min <= max) or None; got {expected_count!r}'
        ]
    elif comparison_type != 'equals':
        problems = [
            f'comparison_type {comparison_type!r} needs an integer expected_count; '
            f'with {expected_count!r} only equals is allowed'
        ]
    else:
        problems = []
    if problems:
        return TestResult.error(problems)

    dst_param = dst
    dst, status = ctx.resolve_globfilepath(dst)
    if not dst:
        return TestResult.error([f'JSONL file {dst_param} not found ({status})'])

    log.debug(f'dst file {dst} will be used for test line_count')

    regex_match = regex_match or False

    # Parse expected_count
    if expected_count is None:
        # No expected_count specified - require at least 1 match
        min_count = 1
        max_count = float('inf')
    elif isinstance(expected_count, int) and not isinstance(expected_count, bool):
        min_count = expected_count
        max_count = expected_count
    else:
        min_count, max_count = _count_range(expected_count)

    try:
        # A 0-byte file is read like any other: it has 0 matching lines, which passes
        # expected_count 0 (or {max: 0}) and fails everything else.
        matching_count = 0
        total_lines = 0
        malformed_count = 0

        with open_text(dst, encoding) as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()

                # Skip blank lines
                if not line:
                    continue

                total_lines += 1

                # Try to parse JSON
                try:
                    data = json.loads(line)
                except json.JSONDecodeError as e:
                    malformed_count += 1
                    if not skip_malformed:
                        return TestResult.execution_error(
                            e, f'Malformed JSON on line {line_num} (content: {line[:200]})'
                        )
                    continue

                # If no conditions, count all valid JSON lines
                if not conditions:
                    matching_count += 1
                    continue

                # Check all conditions for this line
                all_conditions_met = True

                for key_path, expected_value in conditions.items():
                    value, exists = get_nested_value(data, key_path)

                    if not exists:
                        all_conditions_met = False
                        break

                    # Handle multiple values from wildcards
                    if isinstance(value, list):
                        any_match = False
                        for v in value:
                            is_match, msg = _compare_values(ctx, v, expected_value, regex_match)
                            if is_match:
                                any_match = True
                                break
                        if not any_match:
                            all_conditions_met = False
                            break
                    else:
                        is_match, msg = _compare_values(ctx, value, expected_value, regex_match)
                        if not is_match:
                            all_conditions_met = False
                            break

                if all_conditions_met:
                    matching_count += 1

        # Log malformed lines if any
        if malformed_count > 0:
            log.warning(f"Skipped {malformed_count} malformed JSON lines in {dst}")

        if isinstance(expected_count, int) and comparison_type != 'equals':
            ok, comparison = compare_count(matching_count, expected_count, comparison_type)
            messages = [f'Found {matching_count} matching lines', comparison]
            messages.append(f'Total valid lines: {total_lines - malformed_count}')
            if conditions:
                messages.append(f'Conditions: {conditions}')
            return TestResult.success(messages) if ok else TestResult.failed(messages)

        # Check if count is within expected range
        if min_count <= matching_count <= max_count:
            messages = [f'Found {matching_count} matching lines']
            if expected_count is None:
                messages[0] += ' (expected at least 1)'
            elif min_count == max_count:
                messages[0] += f' (expected exactly {min_count})'
            else:
                messages[0] += f' (expected {min_count}-{max_count if max_count != float("inf") else "∞"})'
            messages.append(f'Total valid lines: {total_lines - malformed_count}')
            if conditions:
                messages.append(f'Conditions: {conditions}')
            return TestResult.success(messages)
        messages = [
            f'Found {matching_count} matching lines',
        ]
        if expected_count is None:
            messages.append('Expected: at least 1')
        elif min_count == max_count:
            messages.append(f'Expected: {min_count}')
        else:
            messages.append(f'Expected: {min_count}-{max_count if max_count != float("inf") else "∞"}')
        messages.append(f'Total valid lines: {total_lines - malformed_count}')
        if conditions:
            messages.append(f'Conditions: {conditions}')
        return TestResult.failed(messages)

    except FileNotFoundError:
        return TestResult.error([f'JSONL file {dst} does not exist'])
    except _ENCODING_ERRORS as e:
        return _encoding_error(e, dst, encoding)
    except (PermissionError, OSError) as e:
        return TestResult.execution_error(e, f"Cannot read JSONL file {dst}")


@testfunction(
    name='value_in_any_line',
    description='tests if specified key path with expected value exists in any line of JSONL file',
    category=HostModeCategory.FILE_CONTENT,
)
def value_in_any_line(
    ctx: TestContext,
    dst: str = '',
    key_path: str = '',
    expected_value: str | int | float | bool | None = None,
    regex_match: bool = False,
    skip_malformed: bool = True,
    encoding: str | None = None,
    comparison_type: str = 'equals',
    value_type: str = 'auto',
    tolerance: int | float | None = None,
    time_format: str | None = None,
    timestamp_epoch: int | None = None,
    timestamp_unit: str | None = None,
    utc_offset: str | None = None,
):
    """Pass when ``key_path`` has a value matching ``expected_value`` in at least one JSONL line.

    Use for: a single-field check across a log; for multi-field conditions use jsonl.line_matches.

    With ``comparison_type`` (``greater``, ``less``, ...), ``tolerance`` or the time
    parameters the value is compared as a number or timestamp.

    Args:
        dst: Guest path to the JSONL file (one JSON document per line; blank lines are
            skipped). A glob must match exactly one path; a missing file is an error, a 0-byte file fails.
        key_path: Dot path inside each line's object, e.g. ``event.type``; ``*`` expands
            object values, ``name[*]`` array elements. No numeric indexes.
            For multi-value paths one matching element suffices.
        expected_value: Value to find; see ``regex_match`` for how it is compared.
        regex_match: Treat string expected values as regexes searched (``re.search``) in
            ``str(value)``; the value ``"*"`` then means "key exists". Without it, values
            are compared with type-sensitive ``==``; ``!re``/``!timestamp`` tags always work.
        skip_malformed: ``True`` (default) ignores lines that are not valid JSON; ``False``
            makes the first malformed line an error.
        encoding: ``None`` (default) detects a BOM (UTF-8/16/32) and BOM-less UTF-16, else
            reads UTF-8; a name reads BOM-less files with it. Unknown names or undecodable
            content are an error.
        comparison_type: ``equals`` (default), ``not_equals``, ``greater``, ``less``,
            ``greater_equal`` or ``less_equal``. Anything but ``equals``, or any parameter
            below, compares the value with ``expected_value`` as a number or point in time
            (ordered mode; ``less`` = earlier); a ``!re`` tag, ``{{placeholder}}`` or
            ``regex_match`` is then an error, and so is a value that is no number or timestamp.
        value_type: ``auto`` (default; numbers if both sides are numbers, else timestamps),
            ``number`` or ``timestamp``.
        tolerance: Allowed difference for ``equals``/``not_equals`` (seconds for timestamps).
        time_format: ``strptime`` format of text timestamps on both sides; default ISO 8601 or RFC 2822.
        timestamp_epoch: Read numbers as a count since 1 January of ``1970``, ``1601`` or ``2001``.
        timestamp_unit: Unit of that count: ``s`` (default), ``ms``, ``us``, ``ns`` or ``100ns``.
        utc_offset: Zone of timestamps without one (``+02:00``); default UTC.

    Example:
        function: jsonl.value_in_any_line
        parameter:
          dst: /home/user/data/events.jsonl
          key_path: source
          expected_value: example
          regex_match: true
    """
    ordered, problem = ordered_setup(
        ctx,
        expected_value,
        regex_match,
        comparison_type,
        value_type,
        tolerance,
        time_format,
        timestamp_epoch,
        timestamp_unit,
        utc_offset,
    )
    if problem is not None:
        return problem
    dst_param = dst
    dst, status = ctx.resolve_globfilepath(dst)
    if not dst:
        return TestResult.error([f'JSONL file {dst_param} not found ({status})'])

    log.debug(f'dst file {dst} will be used for test value_in_any_line')

    regex_match = regex_match or False

    try:
        # Check if file is empty (edge case handling)
        if os.path.getsize(dst) == 0:
            return TestResult.failed(['JSONL file is empty (0 bytes)'])
        matching_lines = []
        total_lines = 0
        malformed_count = 0
        lines_with_key = 0

        with open_text(dst, encoding) as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()

                # Skip blank lines
                if not line:
                    continue

                total_lines += 1

                # Try to parse JSON
                try:
                    data = json.loads(line)
                except json.JSONDecodeError as e:
                    malformed_count += 1
                    if not skip_malformed:
                        return TestResult.execution_error(
                            e, f'Malformed JSON on line {line_num} (content: {line[:200]})'
                        )
                    continue

                # Get value at key path
                value, exists = get_nested_value(data, key_path)

                if not exists:
                    continue

                lines_with_key += 1

                # Handle multiple values from wildcards
                if isinstance(value, list):
                    for v in value:
                        is_match, msg = _compare_values(ctx, v, expected_value, regex_match, ordered)
                        if is_match:
                            matching_lines.append((line_num, v, msg))
                            break  # Only record once per line
                else:
                    is_match, msg = _compare_values(ctx, value, expected_value, regex_match, ordered)
                    if is_match:
                        matching_lines.append((line_num, value, msg))

        # Log malformed lines if any
        if malformed_count > 0:
            log.warning(f"Skipped {malformed_count} malformed JSON lines in {dst}")

        # Determine success
        if matching_lines:
            messages = [
                f'Found matching value in {len(matching_lines)} line(s)',
                f'First match: line {matching_lines[0][0]} with value "{matching_lines[0][1]}"',
            ]
            if len(matching_lines) > 1:
                messages.append(f'Additional matches on lines: {[ln for ln, _, _ in matching_lines[1:4]]}')
            return TestResult.success(messages)
        messages = [
            f'No lines found with key path "{key_path}" matching expected value "{expected_value}"',
            f'Analyzed {total_lines - malformed_count} valid JSON lines',
        ]
        if lines_with_key > 0:
            messages.append(f'Found {lines_with_key} lines with key "{key_path}" but none matched the expected value')
        else:
            messages.append(f'Key path "{key_path}" not found in any line')
        return TestResult.failed(messages)

    except OrderingError as e:
        return TestResult.error([f'line {line_num}: {e}'])
    except FileNotFoundError:
        return TestResult.error([f'JSONL file {dst} does not exist'])
    except _ENCODING_ERRORS as e:
        return _encoding_error(e, dst, encoding)
    except (PermissionError, OSError) as e:
        return TestResult.execution_error(e, f"Cannot read JSONL file {dst}")
