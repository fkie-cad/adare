# external imports
from pathlib import Path
import csv
import sys
from typing import Optional

# internal imports
from adarelib.testset.api import testfunction, TestContext
from adarelib.testset.basictest import HostModeCategory
from adarelib.event.event import TestResult
from adarelib.testset.compare import compare_row_sequences, compare_row_sets, extract_columns, row_matches_pattern

# configure logging
import logging

log = logging.getLogger(__name__)


def _row_to_comparable(test_instance, row: list[str], columns: list[int] | None) -> tuple[bool, list[str], str]:
    """
    Convert row to comparable form, handling placeholders.

    Returns:
        tuple: (has_placeholders, processed_row, error_message)
            - has_placeholders: True if row contains placeholders that were processed
            - processed_row: The row with selected columns extracted
            - error_message: Empty string on success, error description on failure
    """
    extracted = extract_columns(row, columns)
    has_placeholders = False

    # Check if any column has placeholders
    for col_value in extracted:
        if test_instance.has_placeholders(str(col_value)):
            has_placeholders = True
            break

    return has_placeholders, extracted, ""


@testfunction(
    name='contains_line',
    description='tests if row in a csv file exists that matches the given entry layout',
    category=HostModeCategory.FILE_CONTENT,
)
def contains_line(ctx: TestContext, dst: str, entry: list = None):
    """Pass when at least one row of CSV file ``dst`` matches ``entry`` column by column.

    Use for: checking a tool's CSV output (e.g. a timeline) contains a specific record.

    Args:
        dst: Guest path to the CSV file. A glob must match exactly one path; no/ambiguous
            match or a missing file fails. Parsed with the default ``csv`` dialect (comma,
            double quotes) in the guest's default encoding; the header row is a normal row.
        entry: Expected row as a list, one item per column; a row must have exactly this many
            columns. Items are compared as exact, case-sensitive strings (``str(item)``), or by
            type for ``!re``/``!timestamp`` tags (``!re`` uses ``re.match``, anchored at the start).
            Required in practice: omitting it is an execution error unless the file is empty.

    Example:
        function: csv.contains_line
        parameter:
          dst: '{{ out_dir }}/timeline.csv'
          entry: [report.docx, !re '.*', Created]
    """
    dst_resolved, status = ctx.resolve_globfilepath(dst)
    if not dst_resolved:
        # List files in directory to help with debugging
        try:
            search_path = Path(dst).parent if '/' in dst or '\\' in dst else Path('.')
            available_files = [str(p.name) for p in search_path.iterdir() if p.is_file()]
            files_info = (
                f"Available files in directory: {available_files}" if available_files else "No files found in directory"
            )
        except (OSError, PermissionError, FileNotFoundError) as e:
            files_info = f"Could not list directory contents: {e}"

        return TestResult.failed(
            [
                f'file with path {dst} can\'t be used, because no unambiguous file could be identified (because {status}). {files_info}'
            ]
        )

    log.debug(f'dst file {dst_resolved} will be used for test contains_line')

    # The entry pattern will be used directly with the placeholder system
    entry_pattern = entry

    try:
        # Increase CSV field size limit to handle large fields (e.g., prefetch data)
        try:
            csv.field_size_limit(sys.maxsize)
        except OverflowError:
            # Fallback for systems where maxsize is too large
            csv.field_size_limit(10485760)  # 10MB

        with open(dst_resolved) as f:
            reader = csv.reader(f)
            rows = list(reader)

            # Track best matching rows for detailed error reporting
            match_results = []

            for i, row in enumerate(rows):
                is_match, failed_columns, column_count_match = row_matches_pattern(ctx, row, entry_pattern)
                if is_match:
                    return TestResult.success()

                # Store match details for error reporting
                match_results.append(
                    {
                        'row_index': i,
                        'row': row,
                        'failed_columns': failed_columns,
                        'column_count_match': column_count_match,
                        'failure_count': len(failed_columns),
                    }
                )

        # Log file contents for debugging when test fails
        log.info(f"CSV file '{dst_resolved}' contents for failed test 'contains_line':")
        for i, row in enumerate(rows):
            log.info(f"  Row {i}: {row}")
        log.info(f"Expected entry pattern: {entry_pattern}")

        # Find the best matching rows (least number of failed columns)
        if match_results:
            # Sort by failure count (ascending), then by whether column count matches
            best_matches = sorted(match_results, key=lambda x: (x['failure_count'], not x['column_count_match']))

            # Build structured failure details
            failure_details = [
                f'no matching row found for pattern: {entry_pattern}',
                f'analyzed {len(rows)} rows in CSV file',
            ]

            # Add up to 3 best matching rows with detailed failures
            failure_details.append('closest matches:')
            for i, match in enumerate(best_matches[:3]):
                failure_details.append(f'  [{i + 1}] row {match["row_index"]}: {match["row"]}')
                failure_details.append(f'      failures: {", ".join(match["failed_columns"])}')

            return TestResult.failed(failure_details)
        return TestResult.failed(
            [f'no matching row found for pattern: {entry_pattern}', 'no rows found in CSV file to analyze']
        )
    except FileNotFoundError:
        return TestResult.failed([f'file with path {dst} does not exist'])
    except (PermissionError, OSError) as e:
        return TestResult.execution_error(e, f"Cannot read CSV file {dst_resolved}")
    except csv.Error as e:
        return TestResult.failed([f"CSV parsing error in file {dst_resolved}: {e}"])


@testfunction(
    name='compare_rows',
    description='compares all rows in CSV against embedded reference data',
    category=HostModeCategory.FILE_CONTENT,
)
def compare_rows(
    ctx: TestContext,
    dst: str,
    reference_rows: list[list[str]] = None,
    columns: list[int] = None,
    ignore_order: bool = False,
    allow_extra_rows: bool = False,
    allow_missing_rows: bool = False,
):
    """Pass when the rows of CSV file ``dst`` match the embedded ``reference_rows``.

    Use for: asserting a whole (small) CSV export. To compare against a second CSV file use
    csv.compare_files.

    Args:
        dst: Guest path to the CSV file. A glob must match exactly one path; no/ambiguous
            match or a missing file fails. Default ``csv`` dialect; header row included.
        reference_rows: Expected rows, a non-empty list of lists of strings (quote numbers in
            YAML). ``!re``/``!timestamp`` tags are matched by type; other cells exactly.
        columns: 0-based column indices to compare (others ignored; out-of-range indices are
            silently dropped). ``None`` compares all columns.
        ignore_order: ``False`` (default) compares row N with row N; ``True`` matches rows as
            a multiset regardless of position.
        allow_extra_rows: Do not fail on actual rows without a reference counterpart (in
            ordered mode only trailing rows count as extra).
        allow_missing_rows: Do not fail on reference rows missing from the file (in ordered
            mode only trailing rows count as missing).

    Example:
        function: csv.compare_rows
        parameter:
          dst: /home/user/export.csv
          reference_rows:
            - [name, size]
            - [report.docx, '1024']
    """
    # Resolve file path
    dst_resolved, status = ctx.resolve_globfilepath(dst)
    if not dst_resolved:
        try:
            search_path = Path(dst).parent if '/' in dst or '\\' in dst else Path('.')
            available_files = [str(p.name) for p in search_path.iterdir() if p.is_file()]
            files_info = (
                f"Available files in directory: {available_files}" if available_files else "No files found in directory"
            )
        except (OSError, PermissionError, FileNotFoundError) as e:
            files_info = f"Could not list directory contents: {e}"

        return TestResult.failed(
            [
                f'file with path {dst} can\'t be used, because no unambiguous file could be identified (because {status}). {files_info}'
            ]
        )

    log.debug(f'dst file {dst_resolved} will be used for test compare_rows')

    # Validate reference_rows structure
    if not isinstance(reference_rows, list):
        return TestResult.failed(['reference_rows must be a list of rows'])

    if not reference_rows:
        return TestResult.failed(['reference_rows cannot be empty'])

    for i, row in enumerate(reference_rows):
        if not isinstance(row, list):
            return TestResult.failed([f'reference_rows[{i}] must be a list, got {type(row).__name__}'])

    try:
        # Increase CSV field size limit to handle large fields
        try:
            csv.field_size_limit(sys.maxsize)
        except OverflowError:
            csv.field_size_limit(10485760)  # 10MB

        # Read actual CSV
        with open(dst_resolved) as f:
            reader = csv.reader(f)
            actual_rows = list(reader)

        # Log file contents for debugging
        log.debug(f"CSV file '{dst_resolved}' contains {len(actual_rows)} rows")
        log.debug(f"Reference data contains {len(reference_rows)} rows")

        # Choose comparison algorithm based on ignore_order
        if ignore_order:
            return compare_row_sets(
                test_instance=ctx,
                actual_rows=actual_rows,
                reference_rows=reference_rows,
                columns=columns,
                allow_extra=allow_extra_rows,
                allow_missing=allow_missing_rows,
            )
        return compare_row_sequences(
            test_instance=ctx,
            actual_rows=actual_rows,
            reference_rows=reference_rows,
            columns=columns,
            allow_extra=allow_extra_rows,
            allow_missing=allow_missing_rows,
        )

    except FileNotFoundError:
        return TestResult.failed([f'file with path {dst} does not exist'])
    except (PermissionError, OSError) as e:
        return TestResult.execution_error(e, f"Cannot read CSV file {dst_resolved}")
    except csv.Error as e:
        return TestResult.failed([f"CSV parsing error in file {dst_resolved}: {e}"])


@testfunction(
    name='compare_files',
    description='compares two CSV files with full diff reporting',
    category=HostModeCategory.FILE_CONTENT,
)
def compare_files(
    ctx: TestContext,
    actual: str = '',
    reference: str = '',
    columns: list[int] = None,
    ignore_order: bool = False,
    allow_extra_rows: bool = False,
    allow_missing_rows: bool = False,
):
    """Pass when CSV file ``actual`` matches CSV file ``reference`` row by row.

    Use for: diffing a produced CSV against a reference CSV available on the same machine.
    For inline expectations use csv.compare_rows. Needs the in-guest agent: agentless host
    mode only pulls a ``dst`` parameter, and this function has none.

    Args:
        actual: Guest path to the CSV under test; a glob must match exactly one path, a
            missing or ambiguous file fails.
        reference: Guest path to the reference CSV, resolved like ``actual``.
        columns: 0-based column indices to compare; ``None`` compares all columns.
        ignore_order: ``False`` (default) compares row N with row N; ``True`` matches rows as a multiset.
        allow_extra_rows: Do not fail on rows only in ``actual`` (ordered mode: trailing rows only).
        allow_missing_rows: Do not fail on rows only in ``reference`` (ordered mode: trailing rows only).

    Example:
        function: csv.compare_files
        parameter:
          actual: /home/user/export.csv
          reference: /home/user/reference/export.csv
          ignore_order: true
    """
    # Resolve actual file path
    actual_path, actual_status = ctx.resolve_globfilepath(actual)
    if not actual_path:
        try:
            search_path = Path(actual).parent if '/' in actual or '\\' in actual else Path('.')
            available_files = [str(p.name) for p in search_path.iterdir() if p.is_file()]
            files_info = (
                f"Available files in directory: {available_files}" if available_files else "No files found in directory"
            )
        except (OSError, PermissionError, FileNotFoundError) as e:
            files_info = f"Could not list directory contents: {e}"

        return TestResult.failed(
            [
                f'actual file with path {actual} can\'t be used, because no unambiguous file could be identified (because {actual_status}). {files_info}'
            ]
        )

    # Resolve reference file path
    reference_path, reference_status = ctx.resolve_globfilepath(reference)
    if not reference_path:
        try:
            search_path = Path(reference).parent if '/' in reference or '\\' in reference else Path('.')
            available_files = [str(p.name) for p in search_path.iterdir() if p.is_file()]
            files_info = (
                f"Available files in directory: {available_files}" if available_files else "No files found in directory"
            )
        except (OSError, PermissionError, FileNotFoundError) as e:
            files_info = f"Could not list directory contents: {e}"

        return TestResult.failed(
            [
                f'reference file with path {reference} can\'t be used, because no unambiguous file could be identified (because {reference_status}). {files_info}'
            ]
        )

    log.debug(
        f'actual file {actual_path} will be compared against reference file {reference_path} for test compare_files'
    )

    try:
        # Increase CSV field size limit to handle large fields
        try:
            csv.field_size_limit(sys.maxsize)
        except OverflowError:
            csv.field_size_limit(10485760)  # 10MB

        # Read actual CSV
        with open(actual_path) as f:
            reader = csv.reader(f)
            actual_rows = list(reader)

        # Read reference CSV
        with open(reference_path) as f:
            reader = csv.reader(f)
            reference_rows = list(reader)

        # Log file contents for debugging
        log.debug(f"Actual CSV file '{actual_path}' contains {len(actual_rows)} rows")
        log.debug(f"Reference CSV file '{reference_path}' contains {len(reference_rows)} rows")

        # Choose comparison algorithm based on ignore_order
        if ignore_order:
            return compare_row_sets(
                test_instance=ctx,
                actual_rows=actual_rows,
                reference_rows=reference_rows,
                columns=columns,
                allow_extra=allow_extra_rows,
                allow_missing=allow_missing_rows,
            )
        return compare_row_sequences(
            test_instance=ctx,
            actual_rows=actual_rows,
            reference_rows=reference_rows,
            columns=columns,
            allow_extra=allow_extra_rows,
            allow_missing=allow_missing_rows,
        )

    except FileNotFoundError as e:
        # e.filename, not str(e): on Windows str(e) escapes the backslashes
        # of the path, so a substring search never matches there.
        if e.filename == actual_path:
            return TestResult.failed([f'actual file with path {actual} does not exist'])
        return TestResult.failed([f'reference file with path {reference} does not exist'])
    except (PermissionError, OSError) as e:
        return TestResult.execution_error(e, "Cannot read CSV files")
    except csv.Error as e:
        return TestResult.failed([f"CSV parsing error: {e}"])
