# external imports
from pathlib import Path
import pandas as pd
from typing import Optional, List, Tuple, Union
import re

# internal imports
from adarelib.testset.api import testfunction, TestContext
from adarelib.testset.basictest import HostModeCategory
from adarelib.event.event import TestResult
from adarelib.constants import StatusEnum

# configure logging
import logging
log = logging.getLogger(__name__)


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _normalize_cell_value(value) -> str:
    """
    Convert Excel cell values to strings for comparison.

    - NaN/None → empty string
    - Dates → ISO format string
    - Numbers → string representation
    - Everything else → string
    """
    if pd.isna(value) or value is None:
        return ""

    # Handle datetime objects
    if isinstance(value, pd.Timestamp):
        return value.isoformat()

    # Convert to string
    return str(value)


def _get_sheet_names(filepath: str) -> list[str]:
    """Get list of all sheet names in Excel file."""
    try:
        excel_file = pd.ExcelFile(filepath, engine='openpyxl')
        return excel_file.sheet_names
    except FileNotFoundError:
        raise
    except PermissionError:
        raise
    except Exception as e:
        log.error(f"Error reading Excel file '{filepath}': {e}")
        raise


def _resolve_sheet_identifier(filepath: str, sheet: str | int) -> str:
    """
    Resolve sheet identifier (name or index) to sheet name.

    Args:
        filepath: Path to Excel file
        sheet: Sheet name (str) or index (int)

    Returns:
        Sheet name as string

    Raises:
        ValueError: If sheet not found
    """
    sheet_names = _get_sheet_names(filepath)

    if isinstance(sheet, int):
        # Resolve by index
        if sheet < 0 or sheet >= len(sheet_names):
            raise ValueError(f"Sheet index {sheet} out of range (file has {len(sheet_names)} sheets: {sheet_names})")
        return sheet_names[sheet]
    # Resolve by name
    if sheet not in sheet_names:
        raise ValueError(f"Sheet '{sheet}' not found (available sheets: {sheet_names})")
    return sheet


def _read_excel_sheet(
    filepath: str,
    sheet: str | int = 0,
    header_row: int | None = None
) -> list[list[str]]:
    """
    Read Excel sheet and return as list of string lists.

    Args:
        filepath: Path to Excel file
        sheet: Sheet name or index (default 0)
        header_row: If specified, skip this many rows from the top

    Returns:
        List of rows, where each row is a list of strings
    """
    # Resolve sheet identifier to name
    sheet_name = _resolve_sheet_identifier(filepath, sheet)

    # Read the sheet
    df = pd.read_excel(
        filepath,
        sheet_name=sheet_name,
        header=None,  # Don't use first row as header
        engine='openpyxl'
    )

    # Skip header rows if specified
    if header_row is not None and header_row > 0:
        df = df.iloc[header_row:]

    # Convert to list of lists with normalized values
    rows = []
    for _, row in df.iterrows():
        normalized_row = [_normalize_cell_value(cell) for cell in row]
        rows.append(normalized_row)

    return rows


def _extract_columns(row: list[str], columns: list[int] | None) -> list[str]:
    """Extract selected columns from row, or return all if columns is None."""
    if columns is None:
        return row
    return [row[i] for i in columns if i < len(row)]


def _row_matches_pattern(test_instance, row, entry_pattern):
    """
    Check if a row matches the expected pattern using placeholder system.

    Returns:
        tuple: (is_match: bool, failed_columns: list, column_count_match: bool)
    """
    column_count_match = len(row) == len(entry_pattern)
    if not column_count_match:
        log.info(f"Row column count mismatch: got {len(row)} columns {row}, expected {len(entry_pattern)} columns {entry_pattern}")
        return False, [f"column_count({len(row)} != {len(entry_pattern)})"], False

    failed_columns = []

    # Check each column individually
    for i, (actual_value, expected_pattern) in enumerate(zip(row, entry_pattern)):
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
                except Exception as e:
                    log.error(f"Error in placeholder comparison for column {i}: {e}")
                    failed_columns.append(f"col{i}(placeholder_error: {e})")
            else:
                failed_columns.append(f"col{i}(invalid_placeholder: expected 1 placeholder, got {len(placeholder_names)})")
        else:
            # Direct string comparison
            if actual_value != expected_str:
                failed_columns.append(f"col{i}('{actual_value}' != '{expected_str}')")

    is_match = len(failed_columns) == 0

    # Log failures only if there were any
    if failed_columns:
        log.info(f"Row {row} failed pattern match: {', '.join(failed_columns)}")

    return is_match, failed_columns, column_count_match


def _compare_row_sets(
    test_instance,
    actual_rows: list[list[str]],
    reference_rows: list[list[str]],
    columns: list[int] | None,
    allow_extra: bool,
    allow_missing: bool
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
    actual_extracted = [_extract_columns(row, columns) for row in actual_rows]
    reference_extracted = [_extract_columns(row, columns) for row in reference_rows]

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
                is_match, _, _ = _row_matches_pattern(test_instance, act_row, ref_row)
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
    missing_rows = [(i, reference_extracted[i]) for i in range(len(reference_extracted)) if i not in matched_reference_indices]
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
    details = _format_diff_report(
        missing_rows=missing_rows,
        extra_rows=extra_rows,
        mismatched_rows=[],
        actual_count=len(actual_rows),
        reference_count=len(reference_rows),
        columns=columns
    )

    return TestResult.failed(details)


def _compare_row_sequences(
    test_instance,
    actual_rows: list[list[str]],
    reference_rows: list[list[str]],
    columns: list[int] | None,
    allow_extra: bool,
    allow_missing: bool
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
    actual_extracted = [_extract_columns(row, columns) for row in actual_rows]
    reference_extracted = [_extract_columns(row, columns) for row in reference_rows]

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
            is_match, failed_columns, _ = _row_matches_pattern(test_instance, act_row, ref_row)
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
    details = _format_diff_report(
        missing_rows=missing_rows,
        extra_rows=extra_rows,
        mismatched_rows=mismatched_rows,
        actual_count=len(actual_rows),
        reference_count=len(reference_rows),
        columns=columns
    )

    return TestResult.failed(details)


def _format_diff_report(
    missing_rows: list[tuple[int, list[str]]],
    extra_rows: list[tuple[int, list[str]]],
    mismatched_rows: list[tuple[int, list[str], list[str], list[str]]],
    actual_count: int,
    reference_count: int,
    columns: list[int] | None
) -> list[str]:
    """
    Format detailed comparison report for test failure.

    Returns list of detail strings:
    - Summary: "Excel comparison failed: X missing, Y extra, Z mismatched"
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

    summary = "Excel comparison failed: " + ", ".join(summary_parts)
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


def _match_sheets(
    actual_sheets: list[str],
    reference_sheets: list[str],
    mode: str,
    specific_sheets: list[str] | None = None
) -> list[tuple[str, str]]:
    """
    Match sheets between actual and reference files based on mode.

    Args:
        actual_sheets: List of sheet names in actual file
        reference_sheets: List of sheet names in reference file
        mode: "by_name", "by_index", or "specific"
        specific_sheets: List of specific sheet names (for mode="specific")

    Returns:
        List of (actual_sheet, reference_sheet) tuples to compare
    """
    if mode == "by_name":
        # Match sheets with same name
        matches = []
        for sheet_name in reference_sheets:
            if sheet_name in actual_sheets:
                matches.append((sheet_name, sheet_name))
        return matches

    if mode == "by_index":
        # Match sheets by position
        matches = []
        for i in range(min(len(actual_sheets), len(reference_sheets))):
            matches.append((actual_sheets[i], reference_sheets[i]))
        return matches

    if mode == "specific":
        # Match only specified sheets
        if not specific_sheets:
            return []
        matches = []
        for sheet_name in specific_sheets:
            if sheet_name in actual_sheets and sheet_name in reference_sheets:
                matches.append((sheet_name, sheet_name))
        return matches

    raise ValueError(f"Invalid sheet_mode '{mode}'. Must be 'by_name', 'by_index', or 'specific'")


def _format_sheet_diff_report(
    sheet_name: str,
    row_comparison_details: list[str]
) -> list[str]:
    """Format sheet comparison report with sheet name prefix."""
    details = [f"Sheet '{sheet_name}':"]
    for line in row_comparison_details:
        details.append(f"  {line}")
    return details


def _validate_columns(
    actual_columns: list[str],
    expected_columns: list[str],
    allow_extra: bool,
    allow_missing: bool,
    ignore_order: bool
) -> tuple[bool, list[str]]:
    """
    Validate column headers.

    Args:
        actual_columns: Column headers from actual sheet
        expected_columns: Expected column headers
        allow_extra: Allow extra columns in actual
        allow_missing: Allow missing columns in actual
        ignore_order: Ignore column order

    Returns:
        (success, error_details) tuple where error_details is a list of strings
    """
    # Normalize column names (strip whitespace)
    actual_normalized = [str(col).strip() for col in actual_columns]
    expected_normalized = [str(col).strip() for col in expected_columns]

    # Find missing columns (in expected but not in actual)
    missing_columns = [col for col in expected_normalized if col not in actual_normalized]

    # Find extra columns (in actual but not in expected)
    extra_columns = [col for col in actual_normalized if col not in expected_normalized]

    # Check order if ignore_order=False
    order_mismatch = False
    if not ignore_order and not missing_columns and not extra_columns:
        # Only check order if sets match
        if actual_normalized != expected_normalized:
            order_mismatch = True

    # Determine if validation passes
    has_failures = False
    if missing_columns and not allow_missing:
        has_failures = True
    if extra_columns and not allow_extra:
        has_failures = True
    if order_mismatch:
        has_failures = True

    if not has_failures:
        return True, []

    # Generate detailed error report
    error_details = []

    # Summary
    summary_parts = []
    if missing_columns and not allow_missing:
        summary_parts.append(f"{len(missing_columns)} missing column{'s' if len(missing_columns) != 1 else ''}")
    if extra_columns and not allow_extra:
        summary_parts.append(f"{len(extra_columns)} extra column{'s' if len(extra_columns) != 1 else ''}")
    if order_mismatch:
        summary_parts.append("column order mismatch")

    error_details.append("Column validation failed: " + ", ".join(summary_parts))
    error_details.append(f"Actual: {len(actual_columns)} columns, Expected: {len(expected_columns)} columns")

    # Missing columns section
    if missing_columns and not allow_missing:
        error_details.append("")
        error_details.append("Missing columns (in expected but not in actual):")
        for col in missing_columns:
            error_details.append(f"  - {col}")

    # Extra columns section
    if extra_columns and not allow_extra:
        error_details.append("")
        error_details.append("Extra columns (in actual but not in expected):")
        for col in extra_columns:
            error_details.append(f"  - {col}")

    # Order mismatch section
    if order_mismatch:
        error_details.append("")
        error_details.append("Column order mismatch:")
        error_details.append(f"  Actual:   {actual_normalized}")
        error_details.append(f"  Expected: {expected_normalized}")

    return False, error_details


# ============================================================================
# TESTFUNCTION 1: sheet_exists
# ============================================================================

@testfunction(
    name='sheet_exists',
    description='tests if a sheet exists in an Excel file',
    category=HostModeCategory.FILE_CONTENT,
)
def sheet_exists(ctx: TestContext, dst: str = '', sheet_name: str = '', regex_match: bool = False):
    try:
        # Resolve file path
        dst_resolved, status = ctx.resolve_globfilepath(dst)
        if not dst_resolved:
            try:
                search_path = Path(dst).parent if '/' in dst or '\\' in dst else Path('.')
                available_files = [str(p.name) for p in search_path.iterdir() if p.is_file()]
                files_info = f"Available files in directory: {available_files}" if available_files else "No files found in directory"
            except (OSError, PermissionError, FileNotFoundError) as e:
                files_info = f"Could not list directory contents: {e}"

            return TestResult.failed([f'file with path {dst} can\'t be used, because no unambiguous file could be identified (because {status}). {files_info}'])

        log.debug(f'dst file {dst_resolved} will be used for test sheet_exists')

        try:
            # Get all sheet names
            sheet_names = _get_sheet_names(dst_resolved)

            if not sheet_names:
                return TestResult.failed(['Excel file contains no sheets'])

            # Check if sheet exists
            if regex_match:
                # Regex matching
                pattern = re.compile(sheet_name)
                matching_sheets = [name for name in sheet_names if pattern.match(name)]

                if matching_sheets:
                    return TestResult.success()
                return TestResult.failed([
                    f'no sheet matches regex pattern: {sheet_name}',
                    f'available sheets: {sheet_names}'
                ])
            # Exact name matching
            if sheet_name in sheet_names:
                return TestResult.success()
            return TestResult.failed([
                f'sheet "{sheet_name}" not found',
                f'available sheets: {sheet_names}'
            ])

        except FileNotFoundError:
            return TestResult.failed([f'file with path {dst} does not exist'])
        except (PermissionError, OSError) as e:
            return TestResult.execution_error(e, f"Cannot read Excel file {dst_resolved}")
        except Exception as e:
            return TestResult.failed([f"Error reading Excel file {dst_resolved}: {e}"])

    except Exception as e:
        log.error(f"Unexpected error in sheet_exists test: {e}", exc_info=True)
        return TestResult.execution_error(e, "Unexpected error in sheet_exists test")


# ============================================================================
# TESTFUNCTION 2: cell_value_matches
# ============================================================================

@testfunction(
    name='cell_value_matches',
    description='validates specific cell value with placeholder support',
    category=HostModeCategory.FILE_CONTENT,
)
def cell_value_matches(ctx: TestContext, dst: str = '', row: int = 0, column: int = 0, expected_value: str | int | float | bool | None = None, sheet: str | int = 0, regex_match: bool = False):
    try:
        # Resolve file path
        dst_resolved, status = ctx.resolve_globfilepath(dst)
        if not dst_resolved:
            try:
                search_path = Path(dst).parent if '/' in dst or '\\' in dst else Path('.')
                available_files = [str(p.name) for p in search_path.iterdir() if p.is_file()]
                files_info = f"Available files in directory: {available_files}" if available_files else "No files found in directory"
            except (OSError, PermissionError, FileNotFoundError) as e:
                files_info = f"Could not list directory contents: {e}"

            return TestResult.failed([f'file with path {dst} can\'t be used, because no unambiguous file could be identified (because {status}). {files_info}'])

        log.debug(f'dst file {dst_resolved} will be used for test cell_value_matches')

        try:
            # Read sheet
            rows = _read_excel_sheet(dst_resolved, sheet=sheet)

            # Validate row and column indices
            if row < 0 or row >= len(rows):
                return TestResult.failed([
                    f'row index {row} out of bounds',
                    f'sheet has {len(rows)} rows (valid indices: 0-{len(rows)-1})'
                ])

            row_data = rows[row]

            if column < 0 or column >= len(row_data):
                return TestResult.failed([
                    f'column index {column} out of bounds',
                    f'row has {len(row_data)} columns (valid indices: 0-{len(row_data)-1})'
                ])

            # Get actual cell value
            actual_value = row_data[column]
            expected_str = str(expected_value) if expected_value is not None else ""

            # Check for placeholders in expected value
            if ctx.has_placeholders(expected_str):
                placeholder_names = ctx.get_placeholders(expected_str)
                if len(placeholder_names) == 1:
                    placeholder_name = placeholder_names[0]
                    success, message = ctx.compare_with_placeholder(placeholder_name, actual_value)
                    if success:
                        return TestResult.success()
                    return TestResult.failed([
                        f'cell value mismatch at row {row}, column {column}',
                        f'actual: "{actual_value}"',
                        f'placeholder: {{{{{placeholder_name}}}}}',
                        f'comparison: {message}'
                    ])
                return TestResult.failed([f'expected exactly one placeholder in expected_value, got {len(placeholder_names)}'])

            # Regex matching
            if regex_match:
                pattern = re.compile(expected_str)
                if pattern.match(actual_value):
                    return TestResult.success()
                return TestResult.failed([
                    f'cell value does not match regex at row {row}, column {column}',
                    f'actual: "{actual_value}"',
                    f'regex: {expected_str}'
                ])

            # Exact string comparison
            if actual_value == expected_str:
                return TestResult.success()
            return TestResult.failed([
                f'cell value mismatch at row {row}, column {column}',
                f'actual: "{actual_value}"',
                f'expected: "{expected_str}"'
            ])

        except FileNotFoundError:
            return TestResult.failed([f'file with path {dst} does not exist'])
        except ValueError as e:
            # Sheet resolution errors
            return TestResult.failed([str(e)])
        except (PermissionError, OSError) as e:
            return TestResult.execution_error(e, f"Cannot read Excel file {dst_resolved}")
        except Exception as e:
            return TestResult.failed([f"Error reading Excel file {dst_resolved}: {e}"])

    except Exception as e:
        log.error(f"Unexpected error in cell_value_matches test: {e}", exc_info=True)
        return TestResult.execution_error(e, "Unexpected error in cell_value_matches test")


# ============================================================================
# TESTFUNCTION 3: contains_row
# ============================================================================

@testfunction(
    name='contains_row',
    description='finds row matching pattern in Excel sheet',
    category=HostModeCategory.FILE_CONTENT,
)
def contains_row(ctx: TestContext, dst: str = '', entry: list[str] = None, sheet: str | int = 0, header_row: int | None = None):
    try:
        # Resolve file path
        dst_resolved, status = ctx.resolve_globfilepath(dst)
        if not dst_resolved:
            try:
                search_path = Path(dst).parent if '/' in dst or '\\' in dst else Path('.')
                available_files = [str(p.name) for p in search_path.iterdir() if p.is_file()]
                files_info = f"Available files in directory: {available_files}" if available_files else "No files found in directory"
            except (OSError, PermissionError, FileNotFoundError) as e:
                files_info = f"Could not list directory contents: {e}"

            return TestResult.failed([f'file with path {dst} can\'t be used, because no unambiguous file could be identified (because {status}). {files_info}'])

        log.debug(f'dst file {dst_resolved} will be used for test contains_row')

        try:
            # Read sheet
            rows = _read_excel_sheet(dst_resolved, sheet=sheet, header_row=header_row)

            # Track best matching rows for detailed error reporting
            match_results = []

            for i, row_item in enumerate(rows):
                is_match, failed_columns, column_count_match = _row_matches_pattern(ctx, row_item, entry)
                if is_match:
                    return TestResult.success()

                # Store match details for error reporting
                match_results.append({
                    'row_index': i,
                    'row': row_item,
                    'failed_columns': failed_columns,
                    'column_count_match': column_count_match,
                    'failure_count': len(failed_columns)
                })

            # Log sheet contents for debugging when test fails
            log.info("Excel sheet contents for failed test contains_row:")
            for i, row_item in enumerate(rows):
                log.info(f"  Row {i}: {row_item}")
            log.info(f"Expected entry pattern: {entry}")

            # Find the best matching rows
            if match_results:
                # Sort by failure count (ascending), then by whether column count matches
                best_matches = sorted(match_results, key=lambda x: (x['failure_count'], not x['column_count_match']))

                # Build structured failure details
                failure_details = [
                    f'no matching row found for pattern: {entry}',
                    f'analyzed {len(rows)} rows in Excel sheet'
                ]

                # Add up to 3 best matching rows with detailed failures
                failure_details.append('closest matches:')
                for i, match in enumerate(best_matches[:3]):
                    failure_details.append(f'  [{i+1}] row {match["row_index"]}: {match["row"]}')
                    failure_details.append(f'      failures: {", ".join(match["failed_columns"])}')

                return TestResult.failed(failure_details)
            return TestResult.failed([
                f'no matching row found for pattern: {entry}',
                'no rows found in Excel sheet to analyze'
            ])

        except FileNotFoundError:
            return TestResult.failed([f'file with path {dst} does not exist'])
        except ValueError as e:
            # Sheet resolution errors
            return TestResult.failed([str(e)])
        except (PermissionError, OSError) as e:
            return TestResult.execution_error(e, f"Cannot read Excel file {dst_resolved}")
        except Exception as e:
            return TestResult.failed([f"Error reading Excel file {dst_resolved}: {e}"])

    except Exception as e:
        log.error(f"Unexpected error in contains_row test: {e}", exc_info=True)
        return TestResult.execution_error(e, "Unexpected error in contains_row test")


# ============================================================================
# TESTFUNCTION 4: validate_columns
# ============================================================================

@testfunction(
    name='validate_columns',
    description='validates column headers in Excel sheet',
    category=HostModeCategory.FILE_CONTENT,
)
def validate_columns(ctx: TestContext, dst: str = '', expected_columns: list[str] = None, sheet: str | int = 0, column_row: int = 0, allow_extra_columns: bool = False, allow_missing_columns: bool = False, ignore_order: bool = False):
    try:
        # Resolve file path
        dst_resolved, status = ctx.resolve_globfilepath(dst)
        if not dst_resolved:
            try:
                search_path = Path(dst).parent if '/' in dst or '\\' in dst else Path('.')
                available_files = [str(p.name) for p in search_path.iterdir() if p.is_file()]
                files_info = f"Available files in directory: {available_files}" if available_files else "No files found in directory"
            except (OSError, PermissionError, FileNotFoundError) as e:
                files_info = f"Could not list directory contents: {e}"

            return TestResult.failed([f'file with path {dst} can\'t be used, because no unambiguous file could be identified (because {status}). {files_info}'])

        log.debug(f'dst file {dst_resolved} will be used for test validate_columns')

        # Validate expected_columns parameter
        if not isinstance(expected_columns, list):
            return TestResult.failed(['expected_columns must be a list'])

        if not expected_columns:
            return TestResult.failed(['expected_columns cannot be empty'])

        try:
            # Read sheet
            rows = _read_excel_sheet(dst_resolved, sheet=sheet)

            # Validate column_row index
            if column_row < 0 or column_row >= len(rows):
                return TestResult.failed([
                    f'column_row index {column_row} out of bounds',
                    f'sheet has {len(rows)} rows (valid indices: 0-{len(rows)-1})'
                ])

            # Get actual columns from specified row
            actual_columns = rows[column_row]

            # Check if row is empty
            if not actual_columns or all(col == "" for col in actual_columns):
                return TestResult.failed([
                    f'column_row {column_row} is empty',
                    'cannot validate columns from an empty row'
                ])

            # Validate columns
            success, error_details = _validate_columns(
                actual_columns=actual_columns,
                expected_columns=expected_columns,
                allow_extra=allow_extra_columns,
                allow_missing=allow_missing_columns,
                ignore_order=ignore_order
            )

            if success:
                return TestResult.success()
            return TestResult.failed(error_details)

        except FileNotFoundError:
            return TestResult.failed([f'file with path {dst} does not exist'])
        except ValueError as e:
            # Sheet resolution errors
            return TestResult.failed([str(e)])
        except (PermissionError, OSError) as e:
            return TestResult.execution_error(e, f"Cannot read Excel file {dst_resolved}")
        except Exception as e:
            return TestResult.failed([f"Error reading Excel file {dst_resolved}: {e}"])

    except Exception as e:
        log.error(f"Unexpected error in validate_columns test: {e}", exc_info=True)
        return TestResult.execution_error(e, "Unexpected error in validate_columns test")


# ============================================================================
# TESTFUNCTION 5: compare_rows
# ============================================================================

@testfunction(
    name='compare_rows',
    description='compares sheet rows against reference data (embedded or external file)',
    category=HostModeCategory.FILE_CONTENT,
)
def compare_rows(ctx: TestContext, dst: str = '', reference_rows: list[list[str]] | None = None, reference_file: str | None = None, reference_sheet: str | int = 0, reference_header_row: int | None = None, sheet: str | int = 0, columns: list[int] | None = None, ignore_order: bool = False, allow_extra_rows: bool = False, allow_missing_rows: bool = False, header_row: int | None = None):
    try:
        # Resolve file path
        dst_resolved, status = ctx.resolve_globfilepath(dst)
        if not dst_resolved:
            try:
                search_path = Path(dst).parent if '/' in dst or '\\' in dst else Path('.')
                available_files = [str(p.name) for p in search_path.iterdir() if p.is_file()]
                files_info = f"Available files in directory: {available_files}" if available_files else "No files found in directory"
            except (OSError, PermissionError, FileNotFoundError) as e:
                files_info = f"Could not list directory contents: {e}"

            return TestResult.failed([f'file with path {dst} can\'t be used, because no unambiguous file could be identified (because {status}). {files_info}'])

        log.debug(f'dst file {dst_resolved} will be used for test compare_rows')

        # Validate reference source (exactly one must be provided)
        has_embedded = reference_rows is not None
        has_file = reference_file is not None

        if not has_embedded and not has_file:
            return TestResult.failed(['Must provide either reference_rows or reference_file'])
        if has_embedded and has_file:
            return TestResult.failed(['Cannot provide both reference_rows and reference_file'])

        # Load reference data from file if specified
        if has_file:
            ref_file_path, ref_status = ctx.resolve_globfilepath(reference_file)
            if not ref_file_path:
                return TestResult.failed([f'reference_file {reference_file} not found (because {ref_status})'])

            try:
                ref_rows = _read_excel_sheet(
                    ref_file_path,
                    sheet=reference_sheet,
                    header_row=reference_header_row
                )
            except ValueError as e:
                return TestResult.failed([f'Error reading reference file: {e}'])
            except FileNotFoundError:
                return TestResult.failed([f'reference_file {reference_file} does not exist'])
            except (PermissionError, OSError) as e:
                return TestResult.execution_error(e, f"Cannot read reference Excel file {ref_file_path}")
        else:
            # Existing validation for embedded reference_rows
            ref_rows = reference_rows

            # Validate reference_rows structure
            if not isinstance(ref_rows, list):
                return TestResult.failed(['reference_rows must be a list of rows'])

            if not ref_rows:
                return TestResult.failed(['reference_rows cannot be empty'])

            for i, row_item in enumerate(ref_rows):
                if not isinstance(row_item, list):
                    return TestResult.failed([f'reference_rows[{i}] must be a list, got {type(row_item).__name__}'])

        try:
            # Read sheet
            actual_rows = _read_excel_sheet(dst_resolved, sheet=sheet, header_row=header_row)

            # Log contents for debugging
            log.debug(f"Excel sheet contains {len(actual_rows)} rows")
            log.debug(f"Reference data contains {len(ref_rows)} rows")

            # Choose comparison algorithm based on ignore_order
            if ignore_order:
                return _compare_row_sets(
                    test_instance=ctx,
                    actual_rows=actual_rows,
                    reference_rows=ref_rows,
                    columns=columns,
                    allow_extra=allow_extra_rows,
                    allow_missing=allow_missing_rows
                )
            return _compare_row_sequences(
                test_instance=ctx,
                actual_rows=actual_rows,
                reference_rows=ref_rows,
                columns=columns,
                allow_extra=allow_extra_rows,
                allow_missing=allow_missing_rows
            )

        except FileNotFoundError:
            return TestResult.failed([f'file with path {dst} does not exist'])
        except ValueError as e:
            # Sheet resolution errors
            return TestResult.failed([str(e)])
        except (PermissionError, OSError) as e:
            return TestResult.execution_error(e, f"Cannot read Excel file {dst_resolved}")
        except Exception as e:
            return TestResult.failed([f"Error reading Excel file {dst_resolved}: {e}"])

    except Exception as e:
        log.error(f"Unexpected error in compare_rows test: {e}", exc_info=True)
        return TestResult.execution_error(e, "Unexpected error in compare_rows test")


# ============================================================================
# TESTFUNCTION 6: compare_sheets
# ============================================================================

@testfunction(
    name='compare_sheets',
    description='compares two sheets from same or different files',
    category=HostModeCategory.FILE_CONTENT,
)
def compare_sheets(ctx: TestContext, actual: str = '', reference: str = '', actual_sheet: str | int = 0, reference_sheet: str | int = 0, columns: list[int] | None = None, ignore_order: bool = False, allow_extra_rows: bool = False, allow_missing_rows: bool = False, header_row: int | None = None):
    try:
        # Resolve actual file path
        actual_path, actual_status = ctx.resolve_globfilepath(actual)
        if not actual_path:
            try:
                search_path = Path(actual).parent if '/' in actual or '\\' in actual else Path('.')
                available_files = [str(p.name) for p in search_path.iterdir() if p.is_file()]
                files_info = f"Available files in directory: {available_files}" if available_files else "No files found in directory"
            except (OSError, PermissionError, FileNotFoundError) as e:
                files_info = f"Could not list directory contents: {e}"

            return TestResult.failed([f'actual file with path {actual} can\'t be used, because no unambiguous file could be identified (because {actual_status}). {files_info}'])

        # Resolve reference file path
        reference_path, reference_status = ctx.resolve_globfilepath(reference)
        if not reference_path:
            try:
                search_path = Path(reference).parent if '/' in reference or '\\' in reference else Path('.')
                available_files = [str(p.name) for p in search_path.iterdir() if p.is_file()]
                files_info = f"Available files in directory: {available_files}" if available_files else "No files found in directory"
            except (OSError, PermissionError, FileNotFoundError) as e:
                files_info = f"Could not list directory contents: {e}"

            return TestResult.failed([f'reference file with path {reference} can\'t be used, because no unambiguous file could be identified (because {reference_status}). {files_info}'])

        log.debug(f'actual file {actual_path} sheet {actual_sheet} will be compared against reference file {reference_path} sheet {reference_sheet} for test compare_sheets')

        try:
            # Read sheets
            actual_rows = _read_excel_sheet(actual_path, sheet=actual_sheet, header_row=header_row)
            reference_rows = _read_excel_sheet(reference_path, sheet=reference_sheet, header_row=header_row)

            # Log contents for debugging
            log.debug(f"Actual sheet contains {len(actual_rows)} rows")
            log.debug(f"Reference sheet contains {len(reference_rows)} rows")

            # Choose comparison algorithm based on ignore_order
            if ignore_order:
                return _compare_row_sets(
                    test_instance=ctx,
                    actual_rows=actual_rows,
                    reference_rows=reference_rows,
                    columns=columns,
                    allow_extra=allow_extra_rows,
                    allow_missing=allow_missing_rows
                )
            return _compare_row_sequences(
                test_instance=ctx,
                actual_rows=actual_rows,
                reference_rows=reference_rows,
                columns=columns,
                allow_extra=allow_extra_rows,
                allow_missing=allow_missing_rows
            )

        except FileNotFoundError as e:
            error_str = str(e)
            if actual_path in error_str or actual in error_str:
                return TestResult.failed([f'actual file with path {actual} does not exist'])
            return TestResult.failed([f'reference file with path {reference} does not exist'])
        except ValueError as e:
            # Sheet resolution errors
            return TestResult.failed([str(e)])
        except (PermissionError, OSError) as e:
            return TestResult.execution_error(e, "Cannot read Excel files")
        except Exception as e:
            return TestResult.failed([f"Error reading Excel files: {e}"])

    except Exception as e:
        log.error(f"Unexpected error in compare_sheets test: {e}", exc_info=True)
        return TestResult.execution_error(e, "Unexpected error in compare_sheets test")


# ============================================================================
# TESTFUNCTION 7: compare_files
# ============================================================================

@testfunction(
    name='compare_files',
    description='compares entire Excel files with multi-sheet awareness',
    category=HostModeCategory.FILE_CONTENT,
)
def compare_files(ctx: TestContext, actual: str = '', reference: str = '', sheet_mode: str = "by_name", specific_sheets: list[str] | None = None, columns: list[int] | None = None, ignore_order: bool = False, allow_extra_rows: bool = False, allow_missing_rows: bool = False, allow_extra_sheets: bool = False, allow_missing_sheets: bool = False, header_row: int | None = None):
    try:
        # Resolve actual file path
        actual_path, actual_status = ctx.resolve_globfilepath(actual)
        if not actual_path:
            try:
                search_path = Path(actual).parent if '/' in actual or '\\' in actual else Path('.')
                available_files = [str(p.name) for p in search_path.iterdir() if p.is_file()]
                files_info = f"Available files in directory: {available_files}" if available_files else "No files found in directory"
            except (OSError, PermissionError, FileNotFoundError) as e:
                files_info = f"Could not list directory contents: {e}"

            return TestResult.failed([f'actual file with path {actual} can\'t be used, because no unambiguous file could be identified (because {actual_status}). {files_info}'])

        # Resolve reference file path
        reference_path, reference_status = ctx.resolve_globfilepath(reference)
        if not reference_path:
            try:
                search_path = Path(reference).parent if '/' in reference or '\\' in reference else Path('.')
                available_files = [str(p.name) for p in search_path.iterdir() if p.is_file()]
                files_info = f"Available files in directory: {available_files}" if available_files else "No files found in directory"
            except (OSError, PermissionError, FileNotFoundError) as e:
                files_info = f"Could not list directory contents: {e}"

            return TestResult.failed([f'reference file with path {reference} can\'t be used, because no unambiguous file could be identified (because {reference_status}). {files_info}'])

        log.debug(f'comparing Excel files: {actual_path} vs {reference_path} for test compare_files')

        try:
            # Get sheet names
            actual_sheets = _get_sheet_names(actual_path)
            reference_sheets = _get_sheet_names(reference_path)

            log.debug(f"Actual file has {len(actual_sheets)} sheets: {actual_sheets}")
            log.debug(f"Reference file has {len(reference_sheets)} sheets: {reference_sheets}")

            # Match sheets based on mode
            try:
                sheet_matches = _match_sheets(
                    actual_sheets,
                    reference_sheets,
                    sheet_mode,
                    specific_sheets
                )
            except ValueError as e:
                return TestResult.failed([str(e)])

            # Check for missing/extra sheets
            if sheet_mode == "by_name":
                matched_names = set(s for s, _ in sheet_matches)
                missing_sheets_list = [s for s in reference_sheets if s not in matched_names]
                extra_sheets_list = [s for s in actual_sheets if s not in set(reference_sheets)]
            elif sheet_mode == "by_index":
                missing_sheets_list = reference_sheets[len(actual_sheets):] if len(reference_sheets) > len(actual_sheets) else []
                extra_sheets_list = actual_sheets[len(reference_sheets):] if len(actual_sheets) > len(reference_sheets) else []
            elif sheet_mode == "specific":
                if specific_sheets:
                    matched_names = set(s for s, _ in sheet_matches)
                    missing_sheets_list = [s for s in specific_sheets if s not in actual_sheets]
                    extra_sheets_list = []  # Don't count extra sheets in specific mode
                else:
                    missing_sheets_list = []
                    extra_sheets_list = []
            else:
                missing_sheets_list = []
                extra_sheets_list = []

            # Track failures
            sheet_failures = []
            has_sheet_structure_failures = False

            # Check missing sheets
            if missing_sheets_list and not allow_missing_sheets:
                has_sheet_structure_failures = True
                sheet_failures.append(f"Missing sheets (in reference but not in actual): {missing_sheets_list}")

            # Check extra sheets
            if extra_sheets_list and not allow_extra_sheets:
                has_sheet_structure_failures = True
                sheet_failures.append(f"Extra sheets (in actual but not in reference): {extra_sheets_list}")

            # Compare each matched sheet
            sheet_comparison_failures = []
            for act_sheet, ref_sheet in sheet_matches:
                try:
                    # Read sheets
                    actual_rows = _read_excel_sheet(actual_path, sheet=act_sheet, header_row=header_row)
                    reference_rows = _read_excel_sheet(reference_path, sheet=ref_sheet, header_row=header_row)

                    # Compare rows
                    if ignore_order:
                        result = _compare_row_sets(
                            test_instance=ctx,
                            actual_rows=actual_rows,
                            reference_rows=reference_rows,
                            columns=columns,
                            allow_extra=allow_extra_rows,
                            allow_missing=allow_missing_rows
                        )
                    else:
                        result = _compare_row_sequences(
                            test_instance=ctx,
                            actual_rows=actual_rows,
                            reference_rows=reference_rows,
                            columns=columns,
                            allow_extra=allow_extra_rows,
                            allow_missing=allow_missing_rows
                        )

                    # Track failures
                    if result.status != StatusEnum.SUCCESS:
                        sheet_comparison_failures.append({
                            'sheet': act_sheet,
                            'details': result.details
                        })

                except Exception as e:
                    sheet_comparison_failures.append({
                        'sheet': act_sheet,
                        'details': [f"Error comparing sheet: {e}"]
                    })

            # Build final result
            if not has_sheet_structure_failures and not sheet_comparison_failures:
                return TestResult.success()

            # Build failure report
            failure_details = []

            # Summary
            summary_parts = []
            if has_sheet_structure_failures:
                if missing_sheets_list and not allow_missing_sheets:
                    summary_parts.append(f"{len(missing_sheets_list)} missing sheet(s)")
                if extra_sheets_list and not allow_extra_sheets:
                    summary_parts.append(f"{len(extra_sheets_list)} extra sheet(s)")
            if sheet_comparison_failures:
                summary_parts.append(f"{len(sheet_comparison_failures)} sheet(s) with row differences")

            failure_details.append("Excel file comparison failed: " + ", ".join(summary_parts))
            failure_details.append(f"Actual: {len(actual_sheets)} sheets, Reference: {len(reference_sheets)} sheets")
            failure_details.append(f"Sheet matching mode: {sheet_mode}")

            # Add sheet structure failures
            if sheet_failures:
                failure_details.append("")
                failure_details.extend(sheet_failures)

            # Add sheet comparison failures
            if sheet_comparison_failures:
                failure_details.append("")
                failure_details.append("Sheet comparison failures:")
                for failure in sheet_comparison_failures:
                    failure_details.append("")
                    failure_details.extend(_format_sheet_diff_report(failure['sheet'], failure['details']))

            return TestResult.failed(failure_details)

        except FileNotFoundError as e:
            error_str = str(e)
            if actual_path in error_str or actual in error_str:
                return TestResult.failed([f'actual file with path {actual} does not exist'])
            return TestResult.failed([f'reference file with path {reference} does not exist'])
        except (PermissionError, OSError) as e:
            return TestResult.execution_error(e, "Cannot read Excel files")
        except Exception as e:
            return TestResult.failed([f"Error reading Excel files: {e}"])

    except Exception as e:
        log.error(f"Unexpected error in compare_files test: {e}", exc_info=True)
        return TestResult.execution_error(e, "Unexpected error in compare_files test")
