"""Reading .xlsx workbooks for the built-in ``excel`` testfunction collection.

A workbook is opened once per test (:class:`Workbook`) and every sheet the test needs is
read from that one handle; opening it per sheet re-parses the whole archive each time.

Also holds the checks the collection shares between its testfunctions (cell and row
comparison, the closest-row report, the whole-workbook report), so the collection module
stays a thin layer of parameter handling and error mapping.

Ships with the agent's adarelib wheel (see :mod:`adarelib.testset.compare` for how
collections and adarelib stay in step). Needs pandas and openpyxl, which only the excel
collection imports; importable on Python 3.10.
"""

import logging
import re
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl.utils.exceptions import InvalidFileException

from adarelib.event.event import TestResult
from adarelib.testset.compare import compare_row_sequences, compare_row_sets, row_matches_pattern
from adarelib.testset.ordering import OrderingError

log = logging.getLogger(__name__)

# What pandas/openpyxl raise for a file that is not a readable workbook (wrong
# format, corrupt archive). The test cannot be evaluated, so these are errors;
# anything else is a bug and surfaces as an ERROR result through the testfunction decorator.
UNREADABLE_WORKBOOK_ERRORS = (ValueError, KeyError, zipfile.BadZipFile, InvalidFileException)


class SheetNotFoundError(LookupError):
    """The workbook was read but has no sheet with the requested name or index.

    Kept apart from ``ValueError`` (which pandas/openpyxl raise for unreadable
    workbooks): a missing sheet in the file under test is a finding (FAILED), an
    unreadable workbook is not (ERROR).
    """


def normalize_cell_value(value) -> str:
    """Cell value as a string for comparison: NaN/None -> ``''``, timestamps -> ISO, else ``str``."""
    if value is None or pd.isna(value):
        return ""
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return str(value)


class Workbook:
    """One open .xlsx file; use as a context manager so the file handle is closed."""

    def __init__(self, path: str):
        self.path = path
        self._file = pd.ExcelFile(path, engine='openpyxl')

    def __enter__(self) -> 'Workbook':
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self._file.close()

    @property
    def sheet_names(self) -> list[str]:
        return list(self._file.sheet_names)

    def resolve_sheet(self, sheet: str | int) -> str:
        """Sheet name for a name or 0-based index.

        :raises SheetNotFoundError: no such sheet
        """
        names = self.sheet_names
        if isinstance(sheet, int):
            if sheet < 0 or sheet >= len(names):
                raise SheetNotFoundError(f"Sheet index {sheet} out of range (file has {len(names)} sheets: {names})")
            return names[sheet]
        if sheet not in names:
            raise SheetNotFoundError(f"Sheet '{sheet}' not found (available sheets: {names})")
        return sheet

    def rows(self, sheet: str | int = 0, header_row: int | None = None) -> list[list[str]]:
        """The sheet's rows as lists of strings; ``header_row`` skips that many rows from the top.

        :raises SheetNotFoundError: no such sheet
        """
        df = self._file.parse(self.resolve_sheet(sheet), header=None)
        if header_row is not None and header_row > 0:
            df = df.iloc[header_row:]
        # iterrows (not itertuples) on purpose: it gives each row one dtype, as results have always shown values
        return [[normalize_cell_value(cell) for cell in row] for _, row in df.iterrows()]


def read_sheet(path: str, sheet: str | int = 0, header_row: int | None = None) -> list[list[str]]:
    """Rows of one sheet of the workbook at ``path`` (see :meth:`Workbook.rows`)."""
    with Workbook(path) as wb:
        return wb.rows(sheet, header_row)


def match_sheets(
    actual_sheets: list[str], reference_sheets: list[str], mode: str, specific_sheets: list[str] | None = None
) -> list[tuple[str, str]]:
    """``(actual, reference)`` sheet pairs to compare for ``mode`` ``by_name``, ``by_index`` or ``specific``.

    :raises ValueError: unknown mode
    """
    if mode == "by_name":
        return [(name, name) for name in reference_sheets if name in actual_sheets]
    if mode == "by_index":
        return list(zip(actual_sheets, reference_sheets, strict=False))
    if mode == "specific":
        return [(n, n) for n in specific_sheets or [] if n in actual_sheets and n in reference_sheets]
    raise ValueError(f"Invalid sheet_mode '{mode}'. Must be 'by_name', 'by_index', or 'specific'")


def format_sheet_diff_report(sheet_name: str, row_comparison_details: list[str]) -> list[str]:
    """Sheet comparison report lines under a ``Sheet '<name>':`` heading."""
    return [f"Sheet '{sheet_name}':"] + [f"  {line}" for line in row_comparison_details]


def validate_columns(
    actual_columns: list[str], expected_columns: list[str], allow_extra: bool, allow_missing: bool, ignore_order: bool
) -> tuple[bool, list[str]]:
    """Compare column headers (whitespace-stripped); return ``(success, error_details)``."""
    actual_normalized = [str(col).strip() for col in actual_columns]
    expected_normalized = [str(col).strip() for col in expected_columns]
    missing_columns = [col for col in expected_normalized if col not in actual_normalized]
    extra_columns = [col for col in actual_normalized if col not in expected_normalized]
    # order only matters when the sets are equal
    order_mismatch = (
        not ignore_order and not missing_columns and not extra_columns and actual_normalized != expected_normalized
    )
    report_missing = bool(missing_columns) and not allow_missing
    report_extra = bool(extra_columns) and not allow_extra
    if not (report_missing or report_extra or order_mismatch):
        return True, []

    summary_parts = []
    if report_missing:
        summary_parts.append(f"{len(missing_columns)} missing column{'s' if len(missing_columns) != 1 else ''}")
    if report_extra:
        summary_parts.append(f"{len(extra_columns)} extra column{'s' if len(extra_columns) != 1 else ''}")
    if order_mismatch:
        summary_parts.append("column order mismatch")

    error_details = [
        "Column validation failed: " + ", ".join(summary_parts),
        f"Actual: {len(actual_columns)} columns, Expected: {len(expected_columns)} columns",
    ]
    if report_missing:
        error_details += ["", "Missing columns (in expected but not in actual):"] + [
            f"  - {c}" for c in missing_columns
        ]
    if report_extra:
        error_details += ["", "Extra columns (in actual but not in expected):"] + [f"  - {c}" for c in extra_columns]
    if order_mismatch:
        error_details += [
            "",
            "Column order mismatch:",
            f"  Actual:   {actual_normalized}",
            f"  Expected: {expected_normalized}",
        ]
    return False, error_details


def unresolved_path_error(label: str, path: str, status: str) -> TestResult:
    """ERROR for a glob that matched no file or several, listing the directory to help fix the path."""
    try:
        search_path = Path(path).parent if '/' in path or '\\' in path else Path('.')
        available_files = [str(p.name) for p in search_path.iterdir() if p.is_file()]
        files_info = (
            f"Available files in directory: {available_files}" if available_files else "No files found in directory"
        )
    except OSError as e:
        files_info = f"Could not list directory contents: {e}"
    return TestResult.error(
        [
            f"{label} with path {path} can't be used, because no unambiguous file could be identified "
            f"(because {status}). {files_info}"
        ]
    )


def compare_cell(ctx: Any, actual_value: str, expected_value, regex_match: bool, ordered, where: str) -> TestResult:
    """The result of ``excel.cell_value_matches`` for the cell text ``actual_value`` at ``where``."""
    if ordered is not None:
        try:
            holds, message = ordered.compare(actual_value, expected_value)
        except OrderingError as e:
            return TestResult.error([f'cell at {where}: {e}'])
        return (
            TestResult.success([f'cell at {where}: {message}'])
            if holds
            else TestResult.failed([f'cell at {where}: {message}'])
        )
    expected_str = str(expected_value) if expected_value is not None else ""

    # Check for placeholders in expected value
    if ctx.has_placeholders(expected_str):
        placeholder_names = ctx.get_placeholders(expected_str)
        if len(placeholder_names) != 1:
            return TestResult.error(
                [f'expected exactly one placeholder in expected_value, got {len(placeholder_names)}']
            )
        success, message = ctx.compare_with_placeholder(placeholder_names[0], actual_value)
        if success:
            return TestResult.success()
        return TestResult.failed(
            [
                f'cell value mismatch at {where}',
                f'actual: "{actual_value}"',
                f'placeholder: {{{{{placeholder_names[0]}}}}}',
                f'comparison: {message}',
            ]
        )

    # Regex matching
    if regex_match:
        if re.compile(expected_str).search(actual_value):
            return TestResult.success()
        return TestResult.failed(
            [f'cell value does not match regex at {where}', f'actual: "{actual_value}"', f'regex: {expected_str}']
        )

    # Exact string comparison
    if actual_value == expected_str:
        return TestResult.success()
    return TestResult.failed(
        [f'cell value mismatch at {where}', f'actual: "{actual_value}"', f'expected: "{expected_str}"']
    )


def find_matching_row(ctx: Any, rows: list[list[str]], entry: list[str]) -> TestResult:
    """SUCCESS when a row of ``rows`` matches ``entry``; else FAILED listing the three closest rows."""
    # Track best matching rows for detailed error reporting
    match_results = []

    for i, row_item in enumerate(rows):
        is_match, failed_columns, column_count_match = row_matches_pattern(ctx, row_item, entry)
        if is_match:
            return TestResult.success()

        # Store match details for error reporting
        match_results.append(
            {
                'row_index': i,
                'row': row_item,
                'failed_columns': failed_columns,
                'column_count_match': column_count_match,
                'failure_count': len(failed_columns),
            }
        )

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
        failure_details = [f'no matching row found for pattern: {entry}', f'analyzed {len(rows)} rows in Excel sheet']

        # Add up to 3 best matching rows with detailed failures
        failure_details.append('closest matches:')
        for i, match in enumerate(best_matches[:3]):
            failure_details.append(f'  [{i + 1}] row {match["row_index"]}: {match["row"]}')
            failure_details.append(f'      failures: {", ".join(match["failed_columns"])}')

        return TestResult.failed(failure_details)
    return TestResult.failed([f'no matching row found for pattern: {entry}', 'no rows found in Excel sheet to analyze'])


def compare_row_lists(
    ctx: Any,
    actual_rows: list[list[str]],
    reference_rows: list[list[str]],
    columns: list[int] | None,
    ignore_order: bool,
    allow_extra_rows: bool,
    allow_missing_rows: bool,
) -> TestResult:
    """Compare two row lists as a multiset (``ignore_order``) or position by position."""
    compare = compare_row_sets if ignore_order else compare_row_sequences
    return compare(
        test_instance=ctx,
        actual_rows=actual_rows,
        reference_rows=reference_rows,
        columns=columns,
        allow_extra=allow_extra_rows,
        allow_missing=allow_missing_rows,
        label='Excel',
    )


def sheet_set_differences(
    sheet_mode: str,
    actual_sheets: list[str],
    reference_sheets: list[str],
    specific_sheets: list[str] | None,
    sheet_matches: list[tuple[str, str]],
) -> tuple[list[str], list[str]]:
    """``(missing, extra)`` sheet names of a workbook comparison in ``sheet_mode`` (see :func:`match_sheets`)."""
    if sheet_mode == "by_name":
        matched_names = {s for s, _ in sheet_matches}
        return (
            [s for s in reference_sheets if s not in matched_names],
            [s for s in actual_sheets if s not in set(reference_sheets)],
        )
    if sheet_mode == "by_index":
        return reference_sheets[len(actual_sheets) :], actual_sheets[len(reference_sheets) :]
    if sheet_mode == "specific":
        # extra sheets are not counted in specific mode
        return [s for s in specific_sheets or [] if s not in actual_sheets], []
    return [], []


def compare_files_failure_details(
    sheet_mode: str,
    actual_sheets: list[str],
    reference_sheets: list[str],
    missing_sheets: list[str],
    extra_sheets: list[str],
    allow_missing_sheets: bool,
    allow_extra_sheets: bool,
    sheet_comparison_failures: list[dict],
) -> list[str]:
    """Report lines for a failed workbook comparison; empty when nothing failed.

    ``sheet_comparison_failures`` holds one ``{'sheet': name, 'details': lines}`` per sheet pair with row differences.
    """
    sheet_failures = []
    summary_parts = []
    if missing_sheets and not allow_missing_sheets:
        sheet_failures.append(f"Missing sheets (in reference but not in actual): {missing_sheets}")
        summary_parts.append(f"{len(missing_sheets)} missing sheet(s)")
    if extra_sheets and not allow_extra_sheets:
        sheet_failures.append(f"Extra sheets (in actual but not in reference): {extra_sheets}")
        summary_parts.append(f"{len(extra_sheets)} extra sheet(s)")
    if sheet_comparison_failures:
        summary_parts.append(f"{len(sheet_comparison_failures)} sheet(s) with row differences")
    if not summary_parts:
        return []

    failure_details = [
        "Excel file comparison failed: " + ", ".join(summary_parts),
        f"Actual: {len(actual_sheets)} sheets, Reference: {len(reference_sheets)} sheets",
        f"Sheet matching mode: {sheet_mode}",
    ]
    if sheet_failures:
        failure_details.append("")
        failure_details.extend(sheet_failures)
    if sheet_comparison_failures:
        failure_details.append("")
        failure_details.append("Sheet comparison failures:")
        for failure in sheet_comparison_failures:
            failure_details.append("")
            failure_details.extend(format_sheet_diff_report(failure['sheet'], failure['details']))
    return failure_details
