"""Reading .xlsx workbooks for the built-in ``excel`` testfunction collection.

A workbook is opened once per test (:class:`Workbook`) and every sheet the test needs is
read from that one handle; opening it per sheet re-parses the whole archive each time.

Ships with the agent's adarelib wheel (see :mod:`adarelib.testset.compare` for how
collections and adarelib stay in step). Needs pandas and openpyxl, which only the excel
collection imports; importable on Python 3.10.
"""

import zipfile

import pandas as pd
from openpyxl.utils.exceptions import InvalidFileException

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
