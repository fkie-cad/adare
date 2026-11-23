# external imports
import re

# internal imports
from adarelib.testset.api import testfunction, TestContext
from adarelib.testset.basictest import HostModeCategory
from adarelib.event.event import TestResult
from adarelib.constants import StatusEnum
from adarelib.testset.compare import (
    compare_with_single_placeholder,
    regex_expected_problem,
    regex_pattern_problem,
    row_matches_pattern,
    rows_regex_problem,
)
from adarelib.testset.structured import compare_count, count_parameter_errors
from adarelib.testset.valuecompare import ordered_setup
from adarelib.testset.workbook import (
    UNREADABLE_WORKBOOK_ERRORS,
    SheetNotFoundError,
    Workbook,
    compare_cell,
    compare_files_failure_details,
    compare_row_lists,
    find_matching_row,
    match_sheets,
    read_sheet,
    sheet_set_differences,
    unresolved_path_error as _unresolved_path_error,
    validate_columns as check_columns,
)

# configure logging
import logging

log = logging.getLogger(__name__)


# --- TESTFUNCTION 1: sheet_exists ---


@testfunction(
    name='sheet_exists',
    description='tests if a sheet exists in an Excel file',
    category=HostModeCategory.FILE_CONTENT,
)
def sheet_exists(ctx: TestContext, dst: str, sheet: str, regex_match: bool = False):
    """Pass when workbook ``dst`` (.xlsx, read with openpyxl) has a sheet named ``sheet``.

    Use for: checking a GUI action added/renamed a worksheet.

    Args:
        dst: Guest path to the .xlsx; a glob must match exactly one path. A missing or
            unreadable file is an error.
        sheet: Exact, case-sensitive sheet name, or a regex if ``regex_match``. A ``!re`` tag is
            matched against each sheet name with ``re.match`` (anchored at the start; add ``$`` to
            anchor the end); an invalid pattern is an error.
        regex_match: Treat ``sheet`` as a Python regex searched in each sheet name
            (``re.search``, unanchored; ``^...$`` for the whole name); an invalid regex is an error,
            even when the workbook has no sheet.

    Example:
        function: excel.sheet_exists
        parameter:
          dst: /home/user/Documents/budget.xlsx
          sheet: Q3
    """
    if regex_match:
        problem = regex_pattern_problem(sheet)
        if problem is not None:
            return problem
    # Resolve file path
    dst_resolved, status = ctx.resolve_globfilepath(dst)
    if not dst_resolved:
        return _unresolved_path_error('file', dst, status)

    log.debug(f'dst file {dst_resolved} will be used for test sheet_exists')

    try:
        # Get all sheet names
        with Workbook(dst_resolved) as wb:
            sheet_names = wb.sheet_names

        if not sheet_names:
            return TestResult.failed(['Excel file contains no sheets'])

        # Check if sheet exists
        if ctx.has_placeholders(sheet):
            # A !re tag (or {{ variable }}) arrives as a placeholder: compare each sheet name with it
            for name in sheet_names:
                holds, _ = compare_with_single_placeholder(ctx, sheet, name)
                if holds:
                    return TestResult.success()
            return TestResult.failed([f'no sheet matches placeholder: {sheet}', f'available sheets: {sheet_names}'])
        if regex_match:
            # Regex matching
            pattern = re.compile(sheet)
            matching_sheets = [name for name in sheet_names if pattern.search(name)]

            if matching_sheets:
                return TestResult.success()
            return TestResult.failed([f'no sheet matches regex pattern: {sheet}', f'available sheets: {sheet_names}'])
        # Exact name matching
        if sheet in sheet_names:
            return TestResult.success()
        return TestResult.failed([f'sheet "{sheet}" not found', f'available sheets: {sheet_names}'])

    except FileNotFoundError:
        return TestResult.error([f'file with path {dst} does not exist'])
    except (PermissionError, OSError) as e:
        return TestResult.execution_error(e, f"Cannot read Excel file {dst_resolved}")
    except UNREADABLE_WORKBOOK_ERRORS as e:
        return TestResult.execution_error(e, f"Cannot parse Excel file {dst_resolved}")


# --- TESTFUNCTION 2: cell_value_matches ---


@testfunction(
    name='cell_value_matches',
    description='validates specific cell value with placeholder support',
    category=HostModeCategory.FILE_CONTENT,
)
def cell_value_matches(
    ctx: TestContext,
    dst: str = '',
    row: int = 0,
    column: int = 0,
    expected_value: str | int | float | bool | None = None,
    sheet: str | int = 0,
    regex_match: bool = False,
    comparison_type: str = 'equals',
    value_type: str = 'auto',
    tolerance: int | float | None = None,
    time_format: str | None = None,
    timestamp_epoch: int | None = None,
    timestamp_unit: str | None = None,
    utc_offset: str | None = None,
):
    """Pass when the cell at (``row``, ``column``) of a sheet equals ``expected_value``.

    Use for: asserting one value a user typed or a formula result saved in a workbook.
    Cells are read via pandas and stringified: empty -> ``''``; numbers via ``str()`` (an int
    may read as ``5.0`` if pandas upcasts the column/row to float); dates as
    ``2024-01-31 00:00:00`` or ``2024-01-31T00:00:00`` depending on the row's other cells --
    use ``!re`` for dates and numbers when unsure.

    With ``comparison_type`` (``greater``, ``less``, ...), ``tolerance`` or the time
    parameters the value is compared as a number or timestamp (cell text such as ``1500.0`` or ``2024-01-31 00:00:00`` reads as a number or an ISO timestamp).

    Args:
        dst: Guest path to the .xlsx; a glob must match exactly one path. A missing or unreadable file is an error.
        row: 0-based row index in the raw sheet (row 0 = spreadsheet row 1); out of range fails.
        column: 0-based column index (A = 0); out of range fails.
        expected_value: Compared exactly with ``str(expected_value)`` (``None`` -> ``''``).
            A single ``!re``/``!timestamp`` tag is matched by type.
        sheet: Sheet name (str) or 0-based sheet index (int); unknown sheets fail.
        regex_match: Treat ``expected_value`` as a regex searched in the cell value (``re.search``,
            unanchored; ``^...$`` for the whole value); an invalid regex is an error.
        comparison_type: ``equals`` (default), ``not_equals``, ``greater``, ``less``,
            ``greater_equal`` or ``less_equal``. Anything but ``equals``, or any parameter
            below, compares the value with ``expected_value`` as a number or point in time
            (ordered mode; ``less`` = earlier); ``!re`` / ``regex_match`` are then errors, a lone
            ``{{ name }}`` is the saved variable; a value that is no number or timestamp is an error.
        value_type: ``auto`` (default; numbers if both sides are numbers, else timestamps),
            ``number`` or ``timestamp``.
        tolerance: Allowed difference for ``equals``/``not_equals`` (seconds for timestamps).
        time_format: ``strptime`` format of text timestamps on both sides; default ISO 8601 or RFC 2822.
        timestamp_epoch: Read numbers as a count since 1 January of ``1970``, ``1601`` or ``2001``.
        timestamp_unit: Unit of that count: ``s`` (default), ``ms``, ``us``, ``ns`` or ``100ns``.
        utc_offset: Zone of timestamps without one (``+02:00``); default UTC.

    Example:
        function: excel.cell_value_matches
        parameter:
          dst: /home/user/Documents/budget.xlsx
          row: 1
          column: 2
          expected_value: '1500'
    """
    ordered, expected_value, problem = ordered_setup(
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
    if ordered is None:
        problem = regex_expected_problem(ctx, [expected_value], regex_match)
        if problem is not None:
            return problem
    # Resolve file path
    dst_resolved, status = ctx.resolve_globfilepath(dst)
    if not dst_resolved:
        return _unresolved_path_error('file', dst, status)

    log.debug(f'dst file {dst_resolved} will be used for test cell_value_matches')

    try:
        # Read sheet
        rows = read_sheet(dst_resolved, sheet=sheet)

        # Validate row and column indices
        if row < 0 or row >= len(rows):
            return TestResult.failed(
                [f'row index {row} out of bounds', f'sheet has {len(rows)} rows (valid indices: 0-{len(rows) - 1})']
            )

        row_data = rows[row]

        if column < 0 or column >= len(row_data):
            return TestResult.failed(
                [
                    f'column index {column} out of bounds',
                    f'row has {len(row_data)} columns (valid indices: 0-{len(row_data) - 1})',
                ]
            )

        return compare_cell(ctx, row_data[column], expected_value, regex_match, ordered, f'row {row}, column {column}')

    except FileNotFoundError:
        return TestResult.error([f'file with path {dst} does not exist'])
    except SheetNotFoundError as e:
        return TestResult.failed([str(e)])
    except (PermissionError, OSError) as e:
        return TestResult.execution_error(e, f"Cannot read Excel file {dst_resolved}")
    except UNREADABLE_WORKBOOK_ERRORS as e:
        return TestResult.execution_error(e, f"Cannot parse Excel file {dst_resolved}")


# --- TESTFUNCTION 3: contains_row ---


@testfunction(
    name='contains_row',
    description='finds row matching pattern in Excel sheet',
    category=HostModeCategory.FILE_CONTENT,
)
def contains_row(
    ctx: TestContext, dst: str = '', entry: list[str] = None, sheet: str | int = 0, header_row: int | None = None
):
    """Pass when at least one row of a sheet matches ``entry`` column by column.

    Use for: checking a record exists anywhere in a sheet. Cells are stringified as in
    excel.cell_value_matches (beware float/date formatting).

    Args:
        dst: Guest path to the .xlsx; a glob must match exactly one path. A missing or unreadable file is an error.
        entry: Expected row; a row must have exactly as many columns as the sheet's used width.
            Items compared as exact strings, or by type for ``!re``/``!timestamp`` tags.
        sheet: Sheet name (str) or 0-based index (int); unknown sheets fail.
        header_row: Number of top rows to skip before searching (not a row index); ``None`` skips none.

    Example:
        function: excel.contains_row
        parameter:
          dst: /home/user/Documents/inventory.xlsx
          entry: [Laptop, '3', Office]
    """
    problem = rows_regex_problem(ctx, [entry])
    if problem is not None:
        return problem
    # Resolve file path
    dst_resolved, status = ctx.resolve_globfilepath(dst)
    if not dst_resolved:
        return _unresolved_path_error('file', dst, status)

    log.debug(f'dst file {dst_resolved} will be used for test contains_row')

    try:
        # Read sheet
        rows = read_sheet(dst_resolved, sheet=sheet, header_row=header_row)

        return find_matching_row(ctx, rows, entry)

    except FileNotFoundError:
        return TestResult.error([f'file with path {dst} does not exist'])
    except SheetNotFoundError as e:
        return TestResult.failed([str(e)])
    except (PermissionError, OSError) as e:
        return TestResult.execution_error(e, f"Cannot read Excel file {dst_resolved}")
    except UNREADABLE_WORKBOOK_ERRORS as e:
        return TestResult.execution_error(e, f"Cannot parse Excel file {dst_resolved}")


@testfunction(
    name='row_count',
    description='tests the number of rows in an Excel sheet that match the given entry layout',
    category=HostModeCategory.FILE_CONTENT,
)
def row_count(
    ctx: TestContext,
    dst: str,
    entry: list,
    expected_count: int,
    comparison_type: str = 'equals',
    sheet: str | int = 0,
    header_row: int | None = None,
):
    """Pass when the number of rows of a sheet matching ``entry`` satisfies ``comparison_type``.

    Use for: asserting how often a record occurs (exactly one row for an item); absence of a
    row: ``expected_count: 0`` (or ``expect_to_fail: true`` on excel.contains_row).

    Args:
        dst: Guest path to the .xlsx; a glob must match exactly one path. A missing or unreadable file is an error.
        entry: Expected row as a list, matched exactly like excel.contains_row: one item per
            column of the sheet's used width (a row with another width never matches), exact
            strings or ``!re``/``!timestamp`` tags. A non-list is an error.
        expected_count: Non-negative integer to compare against; anything else is an error.
        comparison_type: ``equals`` (default), ``greater``, ``less``, ``greater_equal`` or
            ``less_equal``; other values are an error.
        sheet: Sheet name (str) or 0-based index (int); an unknown sheet fails, like excel.contains_row.
        header_row: Number of top rows to skip before counting; ``None`` skips none. A
            negative number or a non-integer is an error.

    Example:
        function: excel.row_count
        parameter:
          dst: /home/user/Documents/inventory.xlsx
          entry: [Laptop, !re '[0-9]+', Office]
          expected_count: 1
    """
    problems = count_parameter_errors(expected_count, comparison_type)
    if not isinstance(entry, list):
        problems.append(f'entry must be a list (one item per column), got {entry!r}')
    if header_row is not None and (isinstance(header_row, bool) or not isinstance(header_row, int) or header_row < 0):
        problems.append(f'header_row must be a non-negative integer or None, got {header_row!r}')
    if problems:
        return TestResult.error(problems)
    problem = rows_regex_problem(ctx, [entry])
    if problem is not None:
        return problem
    dst_resolved, status = ctx.resolve_globfilepath(dst)
    if not dst_resolved:
        return _unresolved_path_error('file', dst, status)
    log.debug(f'dst file {dst_resolved} will be used for test row_count')
    try:
        rows = read_sheet(dst_resolved, sheet=sheet, header_row=header_row)
    except FileNotFoundError:
        return TestResult.error([f'file with path {dst} does not exist'])
    except SheetNotFoundError as e:
        return TestResult.failed([str(e)])
    except (PermissionError, OSError) as e:
        return TestResult.execution_error(e, f"Cannot read Excel file {dst_resolved}")
    except UNREADABLE_WORKBOOK_ERRORS as e:
        return TestResult.execution_error(e, f"Cannot parse Excel file {dst_resolved}")
    matching = sum(1 for row in rows if row_matches_pattern(ctx, row, entry)[0])
    ok, message = compare_count(matching, expected_count, comparison_type)
    details = [f'{matching} of {len(rows)} row(s) match {entry}', message]
    return TestResult.success(details) if ok else TestResult.failed(details)


# --- TESTFUNCTION 4: validate_columns ---


@testfunction(
    name='validate_columns',
    description='validates column headers in Excel sheet',
    category=HostModeCategory.FILE_CONTENT,
)
def validate_columns(
    ctx: TestContext,
    dst: str = '',
    expected_columns: list[str] = None,
    sheet: str | int = 0,
    column_row: int = 0,
    allow_extra_columns: bool = False,
    allow_missing_columns: bool = False,
    ignore_order: bool = False,
):
    """Pass when the header names in row ``column_row`` match ``expected_columns``.

    Use for: verifying a sheet's column layout/schema.

    Args:
        dst: Guest path to the .xlsx; a glob must match exactly one path. A missing or unreadable file is an error.
        expected_columns: Non-empty list of header names; whitespace-stripped, case-sensitive.
            Empty header cells read as ``''`` and count as extra columns.
        sheet: Sheet name (str) or 0-based index (int).
        column_row: 0-based row holding the headers; out of range or empty row fails.
        allow_extra_columns: Do not fail on headers not in ``expected_columns``.
        allow_missing_columns: Do not fail on expected headers absent from the sheet.
        ignore_order: Skip the order check (order is only checked when the names match exactly).

    Example:
        function: excel.validate_columns
        parameter:
          dst: /home/user/Documents/inventory.xlsx
          expected_columns: [Item, Count, Location]
    """
    # Resolve file path
    dst_resolved, status = ctx.resolve_globfilepath(dst)
    if not dst_resolved:
        return _unresolved_path_error('file', dst, status)

    log.debug(f'dst file {dst_resolved} will be used for test validate_columns')

    # Validate expected_columns parameter
    if not isinstance(expected_columns, list):
        return TestResult.error(['expected_columns must be a list'])

    if not expected_columns:
        return TestResult.error(['expected_columns cannot be empty'])

    try:
        # Read sheet
        rows = read_sheet(dst_resolved, sheet=sheet)

        # Validate column_row index
        if column_row < 0 or column_row >= len(rows):
            return TestResult.failed(
                [
                    f'column_row index {column_row} out of bounds',
                    f'sheet has {len(rows)} rows (valid indices: 0-{len(rows) - 1})',
                ]
            )

        # Get actual columns from specified row
        actual_columns = rows[column_row]

        # Check if row is empty
        if not actual_columns or all(col == "" for col in actual_columns):
            return TestResult.failed([f'column_row {column_row} is empty', 'cannot validate columns from an empty row'])

        # Validate columns
        success, error_details = check_columns(
            actual_columns=actual_columns,
            expected_columns=expected_columns,
            allow_extra=allow_extra_columns,
            allow_missing=allow_missing_columns,
            ignore_order=ignore_order,
        )

        if success:
            return TestResult.success()
        return TestResult.failed(error_details)

    except FileNotFoundError:
        return TestResult.error([f'file with path {dst} does not exist'])
    except SheetNotFoundError as e:
        return TestResult.failed([str(e)])
    except (PermissionError, OSError) as e:
        return TestResult.execution_error(e, f"Cannot read Excel file {dst_resolved}")
    except UNREADABLE_WORKBOOK_ERRORS as e:
        return TestResult.execution_error(e, f"Cannot parse Excel file {dst_resolved}")


# --- TESTFUNCTION 5: compare_rows ---


def _embedded_rows_problem(ctx: TestContext, reference_rows) -> TestResult | None:
    """ERROR result for ``reference_rows`` that are no non-empty list of lists or hold an invalid regex."""
    if not isinstance(reference_rows, list):
        return TestResult.error(['reference_rows must be a list of rows'])
    if not reference_rows:
        return TestResult.error(['reference_rows cannot be empty'])
    for i, row_item in enumerate(reference_rows):
        if not isinstance(row_item, list):
            return TestResult.error([f'reference_rows[{i}] must be a list, got {type(row_item).__name__}'])
    return rows_regex_problem(ctx, reference_rows)


@testfunction(
    name='compare_rows',
    description='compares sheet rows against reference data (embedded or external file)',
    category=HostModeCategory.FILE_CONTENT,
)
def compare_rows(
    ctx: TestContext,
    dst: str = '',
    reference_rows: list[list[str]] | None = None,
    reference_file: str | None = None,
    reference_sheet: str | int = 0,
    reference_header_row: int | None = None,
    sheet: str | int = 0,
    columns: list[int] | None = None,
    ignore_order: bool = False,
    allow_extra_rows: bool = False,
    allow_missing_rows: bool = False,
    header_row: int | None = None,
):
    """Pass when the rows of a sheet match inline ``reference_rows`` or a sheet of ``reference_file``.

    Use for: asserting sheet contents. Give exactly one of ``reference_rows``/``reference_file``
    (both or neither fails). Cells are stringified as in excel.cell_value_matches.

    Args:
        dst: Guest path to the .xlsx under test; a glob must match exactly one path.
        reference_rows: Expected rows as a list of lists of strings; ``!re``/``!timestamp`` tags allowed.
        reference_file: Guest path to a reference .xlsx (not pulled in agentless host mode).
        reference_sheet: Sheet name or 0-based index in ``reference_file``.
        reference_header_row: Number of top rows to skip in ``reference_file``.
        sheet: Sheet name or 0-based index in ``dst``.
        columns: 0-based column indices to compare; ``None`` compares all.
        ignore_order: ``True`` matches rows as a multiset instead of position by position.
        allow_extra_rows: Do not fail on extra actual rows (ordered mode: trailing rows only).
        allow_missing_rows: Do not fail on missing reference rows (ordered mode: trailing only).
        header_row: Number of top rows of ``dst`` to skip (not a row index).

    Example:
        function: excel.compare_rows
        parameter:
          dst: /home/user/Documents/inventory.xlsx
          header_row: 1
          reference_rows: [[Laptop, '3'], [Monitor, '5']]
    """
    # Resolve file path
    dst_resolved, status = ctx.resolve_globfilepath(dst)
    if not dst_resolved:
        return _unresolved_path_error('file', dst, status)

    log.debug(f'dst file {dst_resolved} will be used for test compare_rows')

    # Validate reference source (exactly one must be provided)
    has_embedded = reference_rows is not None
    has_file = reference_file is not None

    if not has_embedded and not has_file:
        return TestResult.error(['Must provide either reference_rows or reference_file'])
    if has_embedded and has_file:
        return TestResult.error(['Cannot provide both reference_rows and reference_file'])

    # Load reference data from file if specified
    if has_file:
        ref_file_path, ref_status = ctx.resolve_globfilepath(reference_file)
        if not ref_file_path:
            return TestResult.error([f'reference_file {reference_file} not found (because {ref_status})'])

        try:
            ref_rows = read_sheet(ref_file_path, sheet=reference_sheet, header_row=reference_header_row)
        except SheetNotFoundError as e:
            # The expectation cannot be built, so this is no finding about dst.
            return TestResult.error([f'reference_file {reference_file}: {e}'])
        except FileNotFoundError:
            return TestResult.error([f'reference_file {reference_file} does not exist'])
        except (PermissionError, OSError) as e:
            return TestResult.execution_error(e, f"Cannot read reference Excel file {ref_file_path}")
        except UNREADABLE_WORKBOOK_ERRORS as e:
            return TestResult.execution_error(e, f"Cannot parse reference Excel file {ref_file_path}")
    else:
        ref_rows = reference_rows
        problem = _embedded_rows_problem(ctx, ref_rows)
        if problem is not None:
            return problem

    try:
        # Read sheet
        actual_rows = read_sheet(dst_resolved, sheet=sheet, header_row=header_row)

        # Log contents for debugging
        log.debug(f"Excel sheet contains {len(actual_rows)} rows")
        log.debug(f"Reference data contains {len(ref_rows)} rows")

        return compare_row_lists(
            ctx, actual_rows, ref_rows, columns, ignore_order, allow_extra_rows, allow_missing_rows
        )

    except FileNotFoundError:
        return TestResult.error([f'file with path {dst} does not exist'])
    except SheetNotFoundError as e:
        return TestResult.failed([str(e)])
    except (PermissionError, OSError) as e:
        return TestResult.execution_error(e, f"Cannot read Excel file {dst_resolved}")
    except UNREADABLE_WORKBOOK_ERRORS as e:
        return TestResult.execution_error(e, f"Cannot parse Excel file {dst_resolved}")


# --- TESTFUNCTION 6: compare_sheets ---


@testfunction(
    name='compare_sheets',
    description='compares two sheets from same or different files',
    category=HostModeCategory.FILE_CONTENT,
)
def compare_sheets(
    ctx: TestContext,
    actual: str = '',
    reference: str = '',
    actual_sheet: str | int = 0,
    reference_sheet: str | int = 0,
    columns: list[int] | None = None,
    ignore_order: bool = False,
    allow_extra_rows: bool = False,
    allow_missing_rows: bool = False,
    header_row: int | None = None,
):
    """Pass when sheet ``actual_sheet`` of ``actual`` matches ``reference_sheet`` of ``reference``.

    Use for: comparing two sheets of the same or different workbooks. Needs the in-guest
    agent (agentless host mode only pulls a ``dst`` parameter).

    Args:
        actual: Guest path to the workbook under test; glob must match exactly one path.
        reference: Guest path to the reference workbook (may equal ``actual``).
        actual_sheet: Sheet name or 0-based index in ``actual``.
        reference_sheet: Sheet name or 0-based index in ``reference``.
        columns: 0-based column indices to compare; ``None`` compares all.
        ignore_order: ``True`` matches rows as a multiset instead of position by position.
        allow_extra_rows: Do not fail on extra actual rows (ordered mode: trailing rows only).
        allow_missing_rows: Do not fail on missing reference rows (ordered mode: trailing only).
        header_row: Number of top rows to skip in BOTH sheets.

    Example:
        function: excel.compare_sheets
        parameter:
          actual: /home/user/Documents/budget.xlsx
          reference: /home/user/Documents/budget.xlsx
          actual_sheet: Q3
          reference_sheet: Q2
    """
    # Resolve actual file path
    actual_path, actual_status = ctx.resolve_globfilepath(actual)
    if not actual_path:
        return _unresolved_path_error('actual file', actual, actual_status)

    # Resolve reference file path
    reference_path, reference_status = ctx.resolve_globfilepath(reference)
    if not reference_path:
        return _unresolved_path_error('reference file', reference, reference_status)

    log.debug(
        f'actual file {actual_path} sheet {actual_sheet} will be compared against reference file {reference_path} sheet {reference_sheet} for test compare_sheets'
    )

    try:
        # Read sheets
        actual_rows = read_sheet(actual_path, sheet=actual_sheet, header_row=header_row)
        try:
            reference_rows = read_sheet(reference_path, sheet=reference_sheet, header_row=header_row)
        except SheetNotFoundError as e:
            # A missing reference sheet leaves nothing to compare against: no finding about actual.
            return TestResult.error([f'reference file {reference}: {e}'])

        # Log contents for debugging
        log.debug(f"Actual sheet contains {len(actual_rows)} rows")
        log.debug(f"Reference sheet contains {len(reference_rows)} rows")

        return compare_row_lists(
            ctx, actual_rows, reference_rows, columns, ignore_order, allow_extra_rows, allow_missing_rows
        )

    except FileNotFoundError as e:
        error_str = str(e)
        if actual_path in error_str or actual in error_str:
            return TestResult.error([f'actual file with path {actual} does not exist'])
        return TestResult.error([f'reference file with path {reference} does not exist'])
    except SheetNotFoundError as e:
        return TestResult.failed([str(e)])
    except (PermissionError, OSError) as e:
        return TestResult.execution_error(e, "Cannot read Excel files")
    except UNREADABLE_WORKBOOK_ERRORS as e:
        return TestResult.execution_error(e, "Cannot parse Excel files")


# --- TESTFUNCTION 7: compare_files ---


@testfunction(
    name='compare_files',
    description='compares entire Excel files with multi-sheet awareness',
    category=HostModeCategory.FILE_CONTENT,
)
def compare_files(
    ctx: TestContext,
    actual: str = '',
    reference: str = '',
    sheet_mode: str = "by_name",
    specific_sheets: list[str] | None = None,
    columns: list[int] | None = None,
    ignore_order: bool = False,
    allow_extra_rows: bool = False,
    allow_missing_rows: bool = False,
    allow_extra_sheets: bool = False,
    allow_missing_sheets: bool = False,
    header_row: int | None = None,
):
    """Pass when all paired sheets of ``actual`` and ``reference`` match and no sheet is missing/extra.

    Use for: whole-workbook comparison. Needs the in-guest agent (agentless host mode only
    pulls a ``dst`` parameter).

    Args:
        actual: Guest path to the workbook under test; glob must match exactly one path.
        reference: Guest path to the reference workbook.
        sheet_mode: ``by_name`` (default; pair equal names), ``by_index`` (pair by position)
            or ``specific`` (only ``specific_sheets`` present in both; extra sheets ignored).
            Other values are an error.
        specific_sheets: Sheet names for ``specific`` mode; names absent from ``actual`` count as
            missing, names absent only from ``reference`` are skipped. Empty passes vacuously.
        columns: 0-based column indices to compare; ``None`` compares all.
        ignore_order: ``True`` matches rows as a multiset instead of position by position.
        allow_extra_rows: Do not fail on extra actual rows (ordered mode: trailing rows only).
        allow_missing_rows: Do not fail on missing reference rows (ordered mode: trailing only).
        allow_extra_sheets: Do not fail on sheets only in ``actual``.
        allow_missing_sheets: Do not fail on sheets only in ``reference``.
        header_row: Number of top rows to skip in every sheet.

    Example:
        function: excel.compare_files
        parameter:
          actual: C:/Users/user/Documents/report.xlsx
          reference: C:/reference/report.xlsx
    """
    # Resolve actual file path
    actual_path, actual_status = ctx.resolve_globfilepath(actual)
    if not actual_path:
        return _unresolved_path_error('actual file', actual, actual_status)

    # Resolve reference file path
    reference_path, reference_status = ctx.resolve_globfilepath(reference)
    if not reference_path:
        return _unresolved_path_error('reference file', reference, reference_status)

    log.debug(f'comparing Excel files: {actual_path} vs {reference_path} for test compare_files')

    actual_wb = reference_wb = None
    try:
        # each workbook is opened once; every sheet is read from that handle
        actual_wb = Workbook(actual_path)
        reference_wb = Workbook(reference_path)
        actual_sheets = actual_wb.sheet_names
        reference_sheets = reference_wb.sheet_names

        log.debug(f"Actual file has {len(actual_sheets)} sheets: {actual_sheets}")
        log.debug(f"Reference file has {len(reference_sheets)} sheets: {reference_sheets}")

        # Match sheets based on mode
        try:
            sheet_matches = match_sheets(actual_sheets, reference_sheets, sheet_mode, specific_sheets)
        except ValueError as e:
            # Invalid sheet_mode parameter
            return TestResult.error([str(e)])

        missing_sheets, extra_sheets = sheet_set_differences(
            sheet_mode, actual_sheets, reference_sheets, specific_sheets, sheet_matches
        )

        # Compare each matched sheet
        sheet_comparison_failures = []
        for act_sheet, ref_sheet in sheet_matches:
            try:
                # Read sheets
                actual_rows = actual_wb.rows(act_sheet, header_row)
                reference_rows = reference_wb.rows(ref_sheet, header_row)

                result = compare_row_lists(
                    ctx, actual_rows, reference_rows, columns, ignore_order, allow_extra_rows, allow_missing_rows
                )

                # Track failures
                if result.status != StatusEnum.SUCCESS:
                    sheet_comparison_failures.append({'sheet': act_sheet, 'details': result.details})

            except UNREADABLE_WORKBOOK_ERRORS as e:
                # a sheet that cannot be read was not compared: ERROR, never a mismatch
                return TestResult.execution_error(e, f"Cannot read sheet '{act_sheet}' for comparison")

        failure_details = compare_files_failure_details(
            sheet_mode,
            actual_sheets,
            reference_sheets,
            missing_sheets,
            extra_sheets,
            allow_missing_sheets,
            allow_extra_sheets,
            sheet_comparison_failures,
        )
        if not failure_details:
            return TestResult.success()
        return TestResult.failed(failure_details)

    except FileNotFoundError as e:
        error_str = str(e)
        if actual_path in error_str or actual in error_str:
            return TestResult.error([f'actual file with path {actual} does not exist'])
        return TestResult.error([f'reference file with path {reference} does not exist'])
    except (PermissionError, OSError) as e:
        return TestResult.execution_error(e, "Cannot read Excel files")
    except UNREADABLE_WORKBOOK_ERRORS as e:
        return TestResult.execution_error(e, "Cannot parse Excel files")
    finally:
        for wb in (actual_wb, reference_wb):
            if wb is not None:
                wb.close()
