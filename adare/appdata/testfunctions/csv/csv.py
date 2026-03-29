# external imports
import attrs
from pathlib import Path
import csv
import sys
from typing import ClassVar, Optional, List, Tuple

# internal imports
from adarelib.testset.basictest import BasicTest, Parameter, HostModeCategory
from adarelib.event.event import TestResult
from adarelib.constants import StatusEnum

# configure logging
import logging
log = logging.getLogger(__name__)


def _row_matches_pattern(test_instance, row, entry_pattern):
    """Check if a CSV row matches the expected pattern using placeholder system.

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


def _extract_columns(row: List[str], columns: Optional[List[int]]) -> List[str]:
    """Extract selected columns from row, or return all if columns is None."""
    if columns is None:
        return row
    return [row[i] for i in columns if i < len(row)]


def _row_to_comparable(test_instance, row: List[str], columns: Optional[List[int]]) -> Tuple[bool, List[str], str]:
    """
    Convert row to comparable form, handling placeholders.

    Returns:
        tuple: (has_placeholders, processed_row, error_message)
            - has_placeholders: True if row contains placeholders that were processed
            - processed_row: The row with selected columns extracted
            - error_message: Empty string on success, error description on failure
    """
    extracted = _extract_columns(row, columns)
    has_placeholders = False

    # Check if any column has placeholders
    for col_value in extracted:
        if test_instance.has_placeholders(str(col_value)):
            has_placeholders = True
            break

    return has_placeholders, extracted, ""


def _compare_row_sets(
    test_instance,
    actual_rows: List[List[str]],
    reference_rows: List[List[str]],
    columns: Optional[List[int]],
    allow_extra: bool,
    allow_missing: bool
) -> TestResult:
    """
    Compare CSV rows as sets (ignore_order=True).

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
    actual_rows: List[List[str]],
    reference_rows: List[List[str]],
    columns: Optional[List[int]],
    allow_extra: bool,
    allow_missing: bool
) -> TestResult:
    """
    Compare CSV rows as ordered sequences (ignore_order=False).

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
    missing_rows: List[Tuple[int, List[str]]],
    extra_rows: List[Tuple[int, List[str]]],
    mismatched_rows: List[Tuple[int, List[str], List[str], List[str]]],
    actual_count: int,
    reference_count: int,
    columns: Optional[List[int]]
) -> List[str]:
    """
    Format detailed comparison report for test failure.

    Returns list of detail strings:
    - Summary: "CSV comparison failed: X missing, Y extra, Z mismatched"
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

    summary = "CSV comparison failed: " + ", ".join(summary_parts)
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


@attrs.define
class ContainsLineParameter(Parameter):
    dst: str
    entry: list


@attrs.define
class ContainsLine(BasicTest):
    testname: ClassVar[str] = 'contains_line'
    testdescription: ClassVar[str] = 'tests if row in a csv file exists that matches the given entry layout'
    host_mode_category: ClassVar[HostModeCategory] = HostModeCategory.FILE_CONTENT

    name: str
    parameter: ContainsLineParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def test(self):
        try:
            dst, status = self.resolve_globfilepath(self.parameter.dst)
            if not dst:
                # List files in directory to help with debugging
                try:
                    from pathlib import Path
                    search_path = Path(self.parameter.dst).parent if '/' in self.parameter.dst or '\\' in self.parameter.dst else Path('.')
                    available_files = [str(p.name) for p in search_path.iterdir() if p.is_file()]
                    files_info = f"Available files in directory: {available_files}" if available_files else "No files found in directory"
                except (OSError, PermissionError, FileNotFoundError) as e:
                    files_info = f"Could not list directory contents: {e}"

                return TestResult.failed([f'file with path {self.parameter.dst} can\'t be used, because no unambiguous file could be identified (because {status}). {files_info}'])

            log.debug(f'dst file {dst} will be used for test {self.name}')

            # The entry pattern will be used directly with the placeholder system
            entry_pattern = self.parameter.entry

            try:
                # Increase CSV field size limit to handle large fields (e.g., prefetch data)
                try:
                    csv.field_size_limit(sys.maxsize)
                except OverflowError:
                    # Fallback for systems where maxsize is too large
                    csv.field_size_limit(10485760)  # 10MB

                with open(dst, 'r') as f:
                    reader = csv.reader(f)
                    rows = list(reader)

                    # Track best matching rows for detailed error reporting
                    match_results = []

                    for i, row in enumerate(rows):
                        is_match, failed_columns, column_count_match = _row_matches_pattern(self, row, entry_pattern)
                        if is_match:
                            return TestResult.success()

                        # Store match details for error reporting
                        match_results.append({
                            'row_index': i,
                            'row': row,
                            'failed_columns': failed_columns,
                            'column_count_match': column_count_match,
                            'failure_count': len(failed_columns)
                        })

                # Log file contents for debugging when test fails
                log.info(f"CSV file '{dst}' contents for failed test '{self.name}':")
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
                        f'analyzed {len(rows)} rows in CSV file'
                    ]

                    # Add up to 3 best matching rows with detailed failures
                    failure_details.append('closest matches:')
                    for i, match in enumerate(best_matches[:3]):
                        failure_details.append(f'  [{i+1}] row {match["row_index"]}: {match["row"]}')
                        failure_details.append(f'      failures: {", ".join(match["failed_columns"])}')

                    return TestResult.failed(failure_details)
                else:
                    return TestResult.failed([
                        f'no matching row found for pattern: {entry_pattern}',
                        'no rows found in CSV file to analyze'
                    ])
            except FileNotFoundError:
                return TestResult.failed([f'file with path {self.parameter.dst} does not exist'])
            except (PermissionError, OSError) as e:
                return TestResult.execution_error(e, f"Cannot read CSV file {dst}")
            except csv.Error as e:
                return TestResult.failed([f"CSV parsing error in file {dst}: {e}"])

        except Exception as e:
            log.error(f"Unexpected error in CSV line matching test: {e}", exc_info=True)
            return TestResult.execution_error(e, "Unexpected error in CSV line matching test")


@attrs.define
class CompareRowsParameter(Parameter):
    dst: str
    reference_rows: List[List[str]]
    columns: Optional[List[int]] = None
    ignore_order: bool = False
    allow_extra_rows: bool = False
    allow_missing_rows: bool = False


@attrs.define
class CompareRows(BasicTest):
    testname: ClassVar[str] = 'compare_rows'
    testdescription: ClassVar[str] = 'compares all rows in CSV against embedded reference data'
    host_mode_category: ClassVar[HostModeCategory] = HostModeCategory.FILE_CONTENT

    name: str
    parameter: CompareRowsParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def test(self):
        try:
            # Resolve file path
            dst, status = self.resolve_globfilepath(self.parameter.dst)
            if not dst:
                try:
                    from pathlib import Path
                    search_path = Path(self.parameter.dst).parent if '/' in self.parameter.dst or '\\' in self.parameter.dst else Path('.')
                    available_files = [str(p.name) for p in search_path.iterdir() if p.is_file()]
                    files_info = f"Available files in directory: {available_files}" if available_files else "No files found in directory"
                except (OSError, PermissionError, FileNotFoundError) as e:
                    files_info = f"Could not list directory contents: {e}"

                return TestResult.failed([f'file with path {self.parameter.dst} can\'t be used, because no unambiguous file could be identified (because {status}). {files_info}'])

            log.debug(f'dst file {dst} will be used for test {self.name}')

            # Validate reference_rows structure
            if not isinstance(self.parameter.reference_rows, list):
                return TestResult.failed(['reference_rows must be a list of rows'])

            if not self.parameter.reference_rows:
                return TestResult.failed(['reference_rows cannot be empty'])

            for i, row in enumerate(self.parameter.reference_rows):
                if not isinstance(row, list):
                    return TestResult.failed([f'reference_rows[{i}] must be a list, got {type(row).__name__}'])

            try:
                # Increase CSV field size limit to handle large fields
                try:
                    csv.field_size_limit(sys.maxsize)
                except OverflowError:
                    csv.field_size_limit(10485760)  # 10MB

                # Read actual CSV
                with open(dst, 'r') as f:
                    reader = csv.reader(f)
                    actual_rows = list(reader)

                # Log file contents for debugging
                log.debug(f"CSV file '{dst}' contains {len(actual_rows)} rows")
                log.debug(f"Reference data contains {len(self.parameter.reference_rows)} rows")

                # Choose comparison algorithm based on ignore_order
                if self.parameter.ignore_order:
                    return _compare_row_sets(
                        test_instance=self,
                        actual_rows=actual_rows,
                        reference_rows=self.parameter.reference_rows,
                        columns=self.parameter.columns,
                        allow_extra=self.parameter.allow_extra_rows,
                        allow_missing=self.parameter.allow_missing_rows
                    )
                else:
                    return _compare_row_sequences(
                        test_instance=self,
                        actual_rows=actual_rows,
                        reference_rows=self.parameter.reference_rows,
                        columns=self.parameter.columns,
                        allow_extra=self.parameter.allow_extra_rows,
                        allow_missing=self.parameter.allow_missing_rows
                    )

            except FileNotFoundError:
                return TestResult.failed([f'file with path {self.parameter.dst} does not exist'])
            except (PermissionError, OSError) as e:
                return TestResult.execution_error(e, f"Cannot read CSV file {dst}")
            except csv.Error as e:
                return TestResult.failed([f"CSV parsing error in file {dst}: {e}"])

        except Exception as e:
            log.error(f"Unexpected error in CSV compare_rows test: {e}", exc_info=True)
            return TestResult.execution_error(e, "Unexpected error in CSV compare_rows test")


@attrs.define
class CompareFilesParameter(Parameter):
    actual: str
    reference: str
    columns: Optional[List[int]] = None
    ignore_order: bool = False
    allow_extra_rows: bool = False
    allow_missing_rows: bool = False


@attrs.define
class CompareFiles(BasicTest):
    testname: ClassVar[str] = 'compare_files'
    testdescription: ClassVar[str] = 'compares two CSV files with full diff reporting'
    host_mode_category: ClassVar[HostModeCategory] = HostModeCategory.FILE_CONTENT

    name: str
    parameter: CompareFilesParameter
    description: Optional[str] = ''
    variable_metadata: Optional[dict] = None

    def test(self):
        try:
            # Resolve actual file path
            actual_path, actual_status = self.resolve_globfilepath(self.parameter.actual)
            if not actual_path:
                try:
                    from pathlib import Path
                    search_path = Path(self.parameter.actual).parent if '/' in self.parameter.actual or '\\' in self.parameter.actual else Path('.')
                    available_files = [str(p.name) for p in search_path.iterdir() if p.is_file()]
                    files_info = f"Available files in directory: {available_files}" if available_files else "No files found in directory"
                except (OSError, PermissionError, FileNotFoundError) as e:
                    files_info = f"Could not list directory contents: {e}"

                return TestResult.failed([f'actual file with path {self.parameter.actual} can\'t be used, because no unambiguous file could be identified (because {actual_status}). {files_info}'])

            # Resolve reference file path
            reference_path, reference_status = self.resolve_globfilepath(self.parameter.reference)
            if not reference_path:
                try:
                    from pathlib import Path
                    search_path = Path(self.parameter.reference).parent if '/' in self.parameter.reference or '\\' in self.parameter.reference else Path('.')
                    available_files = [str(p.name) for p in search_path.iterdir() if p.is_file()]
                    files_info = f"Available files in directory: {available_files}" if available_files else "No files found in directory"
                except (OSError, PermissionError, FileNotFoundError) as e:
                    files_info = f"Could not list directory contents: {e}"

                return TestResult.failed([f'reference file with path {self.parameter.reference} can\'t be used, because no unambiguous file could be identified (because {reference_status}). {files_info}'])

            log.debug(f'actual file {actual_path} will be compared against reference file {reference_path} for test {self.name}')

            try:
                # Increase CSV field size limit to handle large fields
                try:
                    csv.field_size_limit(sys.maxsize)
                except OverflowError:
                    csv.field_size_limit(10485760)  # 10MB

                # Read actual CSV
                with open(actual_path, 'r') as f:
                    reader = csv.reader(f)
                    actual_rows = list(reader)

                # Read reference CSV
                with open(reference_path, 'r') as f:
                    reader = csv.reader(f)
                    reference_rows = list(reader)

                # Log file contents for debugging
                log.debug(f"Actual CSV file '{actual_path}' contains {len(actual_rows)} rows")
                log.debug(f"Reference CSV file '{reference_path}' contains {len(reference_rows)} rows")

                # Choose comparison algorithm based on ignore_order
                if self.parameter.ignore_order:
                    return _compare_row_sets(
                        test_instance=self,
                        actual_rows=actual_rows,
                        reference_rows=reference_rows,
                        columns=self.parameter.columns,
                        allow_extra=self.parameter.allow_extra_rows,
                        allow_missing=self.parameter.allow_missing_rows
                    )
                else:
                    return _compare_row_sequences(
                        test_instance=self,
                        actual_rows=actual_rows,
                        reference_rows=reference_rows,
                        columns=self.parameter.columns,
                        allow_extra=self.parameter.allow_extra_rows,
                        allow_missing=self.parameter.allow_missing_rows
                    )

            except FileNotFoundError as e:
                if str(e).find(actual_path) >= 0 or str(e).find(self.parameter.actual) >= 0:
                    return TestResult.failed([f'actual file with path {self.parameter.actual} does not exist'])
                else:
                    return TestResult.failed([f'reference file with path {self.parameter.reference} does not exist'])
            except (PermissionError, OSError) as e:
                return TestResult.execution_error(e, f"Cannot read CSV files")
            except csv.Error as e:
                return TestResult.failed([f"CSV parsing error: {e}"])

        except Exception as e:
            log.error(f"Unexpected error in CSV compare_files test: {e}", exc_info=True)
            return TestResult.execution_error(e, "Unexpected error in CSV compare_files test")