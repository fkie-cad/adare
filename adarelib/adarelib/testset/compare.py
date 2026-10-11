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

log = logging.getLogger(__name__)

# What a placeholder comparison raises for a value it cannot interpret (an
# unparsable timestamp, an unknown placeholder, a non-string value). Anything
# else is a bug and must surface as an ERROR result.
PLACEHOLDER_ERRORS = (KeyError, ValueError, TypeError)


def compare_with_single_placeholder(ctx: Any, expected_str: str, actual: str) -> tuple[bool, str]:
    """Compare ``actual`` against an expected string that must contain exactly one placeholder."""
    placeholder_names = ctx.get_placeholders(expected_str)
    if len(placeholder_names) != 1:
        return False, f"expected 1 placeholder for single value comparison, got {len(placeholder_names)}"
    try:
        return ctx.compare_with_placeholder(placeholder_names[0], actual)
    except PLACEHOLDER_ERRORS as e:
        return False, f"placeholder comparison error: {e}"


def get_nested_value(data, key_path):
    """Navigate nested dictionary using dot notation with wildcard support

    Supports:
    - [*] for all array elements (e.g., "users[*].name")
    - * for all object keys (e.g., "config.*.enabled")

    Returns:
    - For exact paths: (value, True) or (None, False)
    - For wildcard paths: (list_of_values, True) or ([], False)
    """
    keys = key_path.split('.')
    current_values = [data]  # Start with data wrapped in list for consistent handling

    for key in keys:
        next_values = []

        for current in current_values:
            if key == '*':
                # Wildcard for all keys in dict
                if isinstance(current, dict):
                    next_values.extend(current.values())
            elif key.endswith('[*]'):
                # Array wildcard (e.g., "users[*]")
                base_key = key[:-3]  # Remove '[*]'
                if isinstance(current, dict) and base_key in current:
                    array_value = current[base_key]
                    if isinstance(array_value, list):
                        next_values.extend(array_value)
            elif isinstance(current, dict) and key in current:
                # Regular key access
                next_values.append(current[key])

        if not next_values:
            # No matching values found
            return [], False

        current_values = next_values

    # If we have multiple values, it was a wildcard match
    if len(current_values) > 1:
        return current_values, True
    if len(current_values) == 1:
        return current_values[0], True
    return None, False


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
            # Has placeholder - use tolerance comparison
            placeholder_names = test_instance.get_placeholders(expected_str)
            if len(placeholder_names) == 1:
                placeholder_name = placeholder_names[0]
                try:
                    success, message = test_instance.compare_with_placeholder(placeholder_name, actual_value)
                    if not success:
                        failed_columns.append(f"col{i}({message})")
                except PLACEHOLDER_ERRORS as e:
                    log.error(f"Error in placeholder comparison for column {i}: {e}")
                    failed_columns.append(f"col{i}(placeholder_error: {e})")
            else:
                failed_columns.append(
                    f"col{i}(invalid_placeholder: expected 1 placeholder, got {len(placeholder_names)})"
                )
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
