# external imports
import attrs
from pathlib import Path
import csv
from typing import ClassVar, Optional

# internal imports
from adarelib.testset.basictest import BasicTest, Parameter
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


@attrs.define
class ContainsLineParameter(Parameter):
    dst: str
    entry: list


@attrs.define
class ContainsLine(BasicTest):
    testname: ClassVar[str] = 'contains_line'
    testdescription: ClassVar[str] = 'tests if row in a csv file exists that matches the given entry layout'

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