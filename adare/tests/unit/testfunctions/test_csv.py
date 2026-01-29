"""Comprehensive unit tests for CSV testfunctions."""

import pytest
import sys
from pathlib import Path

# Add paths for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
ADARELIB_ROOT = PROJECT_ROOT.parent / "adarelib"

# Add to sys.path if not already there
if str(ADARELIB_ROOT) not in sys.path:
    sys.path.insert(0, str(ADARELIB_ROOT))

# Import from adarelib.constants as required
from adarelib.constants import StatusEnum

# Import testfunctions dynamically
from adare.helperfunctions.module import import_module_from_pyfile

# Load CSV testfunctions module
csv_module_path = PROJECT_ROOT / "appdata" / "testfunctions" / "csv" / "csv.py"
csv_module = import_module_from_pyfile(csv_module_path)

# Extract testfunctions from module
ContainsLine = csv_module.ContainsLine
ContainsLineParameter = csv_module.ContainsLineParameter
CompareRows = csv_module.CompareRows
CompareRowsParameter = csv_module.CompareRowsParameter
CompareFiles = csv_module.CompareFiles
CompareFilesParameter = csv_module.CompareFilesParameter

# Import test helpers
import importlib.util
helpers_path = Path(__file__).parent / "helpers.py"
spec = importlib.util.spec_from_file_location("helpers", helpers_path)
helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helpers)

assert_test_success = helpers.assert_test_success
assert_test_failed = helpers.assert_test_failed
assert_test_error = helpers.assert_test_error


# ============================================================================
# ContainsLine Tests
# ============================================================================

class TestContainsLine:
    """Tests for ContainsLine testfunction."""

    def test_contains_line_success_exact_match(self, create_csv_file):
        """Test successful row match with exact values."""
        csv_file = create_csv_file("test.csv", [
            ["Name", "Age", "City"],
            ["Alice", "30", "New York"],
            ["Bob", "25", "London"],
        ])

        test = ContainsLine(
            name="test_contains",
            parameter=ContainsLineParameter(
                dst=str(csv_file),
                entry=["Bob", "25", "London"]
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_contains_line_success_first_row(self, create_csv_file):
        """Test matching the first row."""
        csv_file = create_csv_file("test.csv", [
            ["Name", "Age", "City"],
            ["Alice", "30", "New York"],
        ])

        test = ContainsLine(
            name="test_contains",
            parameter=ContainsLineParameter(
                dst=str(csv_file),
                entry=["Name", "Age", "City"]
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_contains_line_success_last_row(self, create_csv_file):
        """Test matching the last row."""
        csv_file = create_csv_file("test.csv", [
            ["Name", "Age", "City"],
            ["Alice", "30", "New York"],
            ["Bob", "25", "London"],
            ["Charlie", "35", "Paris"],
        ])

        test = ContainsLine(
            name="test_contains",
            parameter=ContainsLineParameter(
                dst=str(csv_file),
                entry=["Charlie", "35", "Paris"]
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_contains_line_failure_no_match(self, create_csv_file):
        """Test failure when no row matches."""
        csv_file = create_csv_file("test.csv", [
            ["Name", "Age", "City"],
            ["Alice", "30", "New York"],
            ["Bob", "25", "London"],
        ])

        test = ContainsLine(
            name="test_contains",
            parameter=ContainsLineParameter(
                dst=str(csv_file),
                entry=["Charlie", "35", "Paris"]
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "no matching row found" in result.details[0]

    def test_contains_line_failure_partial_match(self, create_csv_file):
        """Test failure when only some columns match."""
        csv_file = create_csv_file("test.csv", [
            ["Name", "Age", "City"],
            ["Alice", "30", "New York"],
            ["Bob", "25", "London"],
        ])

        test = ContainsLine(
            name="test_contains",
            parameter=ContainsLineParameter(
                dst=str(csv_file),
                entry=["Alice", "30", "London"]  # Wrong city
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "no matching row found" in result.details[0]

    def test_contains_line_failure_column_count_mismatch(self, create_csv_file):
        """Test failure when column count doesn't match."""
        csv_file = create_csv_file("test.csv", [
            ["Name", "Age", "City"],
            ["Alice", "30", "New York"],
        ])

        test = ContainsLine(
            name="test_contains",
            parameter=ContainsLineParameter(
                dst=str(csv_file),
                entry=["Alice", "30"]  # Only 2 columns instead of 3
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "no matching row found" in result.details[0]

    def test_contains_line_empty_csv(self, create_csv_file):
        """Test failure with empty CSV file."""
        csv_file = create_csv_file("test.csv", [])

        test = ContainsLine(
            name="test_contains",
            parameter=ContainsLineParameter(
                dst=str(csv_file),
                entry=["Alice", "30"]
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "no rows found" in result.details[1]

    def test_contains_line_file_not_found(self, tmp_path):
        """Test failure when CSV file doesn't exist."""
        test = ContainsLine(
            name="test_contains",
            parameter=ContainsLineParameter(
                dst=str(tmp_path / "nonexistent.csv"),
                entry=["Alice", "30"]
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "does not exist" in result.details[0]

    def test_contains_line_with_placeholder_simple(self, create_csv_file, variable_metadata_simple):
        """Test row match with simple placeholder."""
        csv_file = create_csv_file("test.csv", [
            ["Name", "Value"],
            ["Alice", "value1"],
            ["Bob", "value2"],
        ])

        test = ContainsLine(
            name="test_contains",
            parameter=ContainsLineParameter(
                dst=str(csv_file),
                entry=["Bob", "{{VAR2}}"]
            ),
            variable_metadata=variable_metadata_simple
        )
        result = test.test()

        assert_test_success(result)

    def test_contains_line_with_placeholder_no_match(self, create_csv_file, variable_metadata_simple):
        """Test failure when placeholder doesn't match."""
        csv_file = create_csv_file("test.csv", [
            ["Name", "Value"],
            ["Alice", "value1"],
            ["Bob", "wrong_value"],
        ])

        test = ContainsLine(
            name="test_contains",
            parameter=ContainsLineParameter(
                dst=str(csv_file),
                entry=["Bob", "{{VAR2}}"]
            ),
            variable_metadata=variable_metadata_simple
        )
        result = test.test()

        assert_test_failed(result)

    def test_contains_line_single_column(self, create_csv_file):
        """Test with single column CSV."""
        csv_file = create_csv_file("test.csv", [
            ["Value"],
            ["A"],
            ["B"],
            ["C"],
        ])

        test = ContainsLine(
            name="test_contains",
            parameter=ContainsLineParameter(
                dst=str(csv_file),
                entry=["B"]
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_contains_line_with_special_characters(self, create_csv_file):
        """Test with special characters in CSV data."""
        csv_file = create_csv_file("test.csv", [
            ["Name", "Description"],
            ["Item1", "Contains, comma"],
            ["Item2", "Contains \"quotes\""],
        ])

        test = ContainsLine(
            name="test_contains",
            parameter=ContainsLineParameter(
                dst=str(csv_file),
                entry=["Item1", "Contains, comma"]
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_contains_line_multiple_placeholders_error(self, create_csv_file, variable_metadata_simple):
        """Test error when multiple placeholders are in a single cell."""
        csv_file = create_csv_file("test.csv", [
            ["Name", "Value"],
            ["Alice", "value1_value2"],
        ])

        test = ContainsLine(
            name="test_contains",
            parameter=ContainsLineParameter(
                dst=str(csv_file),
                entry=["Alice", "{{VAR1}}_{{VAR2}}"]  # Multiple placeholders in one cell
            ),
            variable_metadata=variable_metadata_simple
        )
        result = test.test()

        # Should fail because multiple placeholders in one cell are not supported
        assert_test_failed(result)

    def test_contains_line_numeric_values(self, create_csv_file):
        """Test with numeric values (converted to strings in CSV)."""
        csv_file = create_csv_file("test.csv", [
            ["ID", "Score"],
            ["1", "100"],
            ["2", "95"],
        ])

        test = ContainsLine(
            name="test_contains",
            parameter=ContainsLineParameter(
                dst=str(csv_file),
                entry=["2", "95"]
            )
        )
        result = test.test()

        assert_test_success(result)


# ============================================================================
# CompareRows Tests
# ============================================================================

class TestCompareRows:
    """Tests for CompareRows testfunction."""

    def test_compare_rows_success_exact_match(self, create_csv_file):
        """Test successful comparison with exact match."""
        csv_file = create_csv_file("test.csv", [
            ["Name", "Age"],
            ["Alice", "30"],
            ["Bob", "25"],
        ])

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(csv_file),
                reference_rows=[
                    ["Name", "Age"],
                    ["Alice", "30"],
                    ["Bob", "25"],
                ]
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_failure_mismatch(self, create_csv_file):
        """Test failure when rows don't match."""
        csv_file = create_csv_file("test.csv", [
            ["Name", "Age"],
            ["Alice", "30"],
            ["Bob", "25"],
        ])

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(csv_file),
                reference_rows=[
                    ["Name", "Age"],
                    ["Alice", "35"],  # Wrong age
                    ["Bob", "25"],
                ]
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "mismatched row" in result.details[0]

    def test_compare_rows_failure_extra_rows_not_allowed(self, create_csv_file):
        """Test failure when actual has extra rows and not allowed."""
        csv_file = create_csv_file("test.csv", [
            ["Name", "Age"],
            ["Alice", "30"],
            ["Bob", "25"],
            ["Charlie", "35"],
        ])

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(csv_file),
                reference_rows=[
                    ["Name", "Age"],
                    ["Alice", "30"],
                ],
                allow_extra_rows=False
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "extra row" in result.details[0]

    def test_compare_rows_success_extra_rows_allowed(self, create_csv_file):
        """Test success when actual has extra rows and allowed."""
        csv_file = create_csv_file("test.csv", [
            ["Name", "Age"],
            ["Alice", "30"],
            ["Bob", "25"],
            ["Charlie", "35"],
        ])

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(csv_file),
                reference_rows=[
                    ["Name", "Age"],
                    ["Alice", "30"],
                ],
                allow_extra_rows=True
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_failure_missing_rows_not_allowed(self, create_csv_file):
        """Test failure when actual has missing rows and not allowed."""
        csv_file = create_csv_file("test.csv", [
            ["Name", "Age"],
            ["Alice", "30"],
        ])

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(csv_file),
                reference_rows=[
                    ["Name", "Age"],
                    ["Alice", "30"],
                    ["Bob", "25"],
                    ["Charlie", "35"],
                ],
                allow_missing_rows=False
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "missing row" in result.details[0]

    def test_compare_rows_success_missing_rows_allowed(self, create_csv_file):
        """Test success when actual has missing rows and allowed."""
        csv_file = create_csv_file("test.csv", [
            ["Name", "Age"],
            ["Alice", "30"],
        ])

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(csv_file),
                reference_rows=[
                    ["Name", "Age"],
                    ["Alice", "30"],
                    ["Bob", "25"],
                ],
                allow_missing_rows=True
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_ignore_order_success(self, create_csv_file):
        """Test success with different order when ignore_order=True."""
        csv_file = create_csv_file("test.csv", [
            ["Name", "Age"],
            ["Bob", "25"],
            ["Alice", "30"],
            ["Charlie", "35"],
        ])

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(csv_file),
                reference_rows=[
                    ["Name", "Age"],
                    ["Alice", "30"],
                    ["Bob", "25"],
                    ["Charlie", "35"],
                ],
                ignore_order=True
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_ignore_order_failure(self, create_csv_file):
        """Test failure with different order when ignore_order=False."""
        csv_file = create_csv_file("test.csv", [
            ["Name", "Age"],
            ["Bob", "25"],
            ["Alice", "30"],
        ])

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(csv_file),
                reference_rows=[
                    ["Name", "Age"],
                    ["Alice", "30"],
                    ["Bob", "25"],
                ],
                ignore_order=False
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "mismatched row" in result.details[0]

    def test_compare_rows_column_selection(self, create_csv_file):
        """Test comparing only specific columns."""
        csv_file = create_csv_file("test.csv", [
            ["Name", "Age", "City"],
            ["Alice", "30", "New York"],
            ["Bob", "25", "London"],
        ])

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(csv_file),
                reference_rows=[
                    ["Name", "Age", "Paris"],  # City is different but will be ignored
                    ["Alice", "30", "Tokyo"],
                    ["Bob", "25", "Berlin"],
                ],
                columns=[0, 1]  # Only compare Name and Age columns
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_column_selection_mismatch(self, create_csv_file):
        """Test failure when selected columns don't match."""
        csv_file = create_csv_file("test.csv", [
            ["Name", "Age", "City"],
            ["Alice", "30", "New York"],
            ["Bob", "25", "London"],
        ])

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(csv_file),
                reference_rows=[
                    ["Name", "Age", "City"],
                    ["Alice", "35", "New York"],  # Age is different
                    ["Bob", "25", "London"],
                ],
                columns=[0, 1]  # Compare Name and Age
            )
        )
        result = test.test()

        assert_test_failed(result)

    def test_compare_rows_with_placeholder(self, create_csv_file, variable_metadata_simple):
        """Test comparison with placeholder in reference data."""
        csv_file = create_csv_file("test.csv", [
            ["Name", "Value"],
            ["Alice", "value1"],
            ["Bob", "value2"],
        ])

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(csv_file),
                reference_rows=[
                    ["Name", "Value"],
                    ["Alice", "{{VAR1}}"],
                    ["Bob", "{{VAR2}}"],
                ]
            ),
            variable_metadata=variable_metadata_simple
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_validation_error_not_list(self, create_csv_file):
        """Test validation error when reference_rows is not a list."""
        csv_file = create_csv_file("test.csv", [["Name"], ["Alice"]])

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(csv_file),
                reference_rows="not a list"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "must be a list" in result.details[0]

    def test_compare_rows_validation_error_empty(self, create_csv_file):
        """Test validation error when reference_rows is empty."""
        csv_file = create_csv_file("test.csv", [["Name"], ["Alice"]])

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(csv_file),
                reference_rows=[]
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "cannot be empty" in result.details[0]

    def test_compare_rows_validation_error_row_not_list(self, create_csv_file):
        """Test validation error when a row is not a list."""
        csv_file = create_csv_file("test.csv", [["Name"], ["Alice"]])

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(csv_file),
                reference_rows=[
                    ["Name"],
                    "not a list"
                ]
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "must be a list" in result.details[0]

    def test_compare_rows_file_not_found(self, tmp_path):
        """Test failure when CSV file doesn't exist."""
        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(tmp_path / "nonexistent.csv"),
                reference_rows=[["Name"], ["Alice"]]
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "does not exist" in result.details[0]

    def test_compare_rows_empty_csv(self, create_csv_file):
        """Test comparison with empty CSV file."""
        csv_file = create_csv_file("test.csv", [])

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(csv_file),
                reference_rows=[["Name"], ["Alice"]],
                allow_missing_rows=False
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "missing row" in result.details[0]

    def test_compare_rows_ignore_order_with_duplicates(self, create_csv_file):
        """Test ignore_order with duplicate rows."""
        csv_file = create_csv_file("test.csv", [
            ["Name", "Age"],
            ["Alice", "30"],
            ["Alice", "30"],  # Duplicate
            ["Bob", "25"],
        ])

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(csv_file),
                reference_rows=[
                    ["Name", "Age"],
                    ["Alice", "30"],
                    ["Bob", "25"],
                ],
                ignore_order=True,
                allow_extra_rows=True
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_column_selection_out_of_bounds(self, create_csv_file):
        """Test column selection with indices that exceed row length."""
        csv_file = create_csv_file("test.csv", [
            ["A", "B"],
            ["1", "2"],
        ])

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(csv_file),
                reference_rows=[
                    ["A", "B"],
                    ["1", "2"],
                ],
                columns=[0, 1, 5]  # Column 5 doesn't exist
            )
        )
        result = test.test()

        # Should still pass as _extract_columns handles out of bounds gracefully
        assert_test_success(result)


# ============================================================================
# CompareFiles Tests
# ============================================================================

class TestCompareFiles:
    """Tests for CompareFiles testfunction."""

    def test_compare_files_success_exact_match(self, create_csv_file):
        """Test successful comparison with exact match."""
        actual_file = create_csv_file("actual.csv", [
            ["Name", "Age"],
            ["Alice", "30"],
            ["Bob", "25"],
        ])
        reference_file = create_csv_file("reference.csv", [
            ["Name", "Age"],
            ["Alice", "30"],
            ["Bob", "25"],
        ])

        test = CompareFiles(
            name="test_compare",
            parameter=CompareFilesParameter(
                actual=str(actual_file),
                reference=str(reference_file)
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_files_failure_mismatch(self, create_csv_file):
        """Test failure when files don't match."""
        actual_file = create_csv_file("actual.csv", [
            ["Name", "Age"],
            ["Alice", "30"],
            ["Bob", "25"],
        ])
        reference_file = create_csv_file("reference.csv", [
            ["Name", "Age"],
            ["Alice", "35"],  # Wrong age
            ["Bob", "25"],
        ])

        test = CompareFiles(
            name="test_compare",
            parameter=CompareFilesParameter(
                actual=str(actual_file),
                reference=str(reference_file)
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "mismatched row" in result.details[0]

    def test_compare_files_failure_extra_rows_not_allowed(self, create_csv_file):
        """Test failure when actual has extra rows and not allowed."""
        actual_file = create_csv_file("actual.csv", [
            ["Name", "Age"],
            ["Alice", "30"],
            ["Bob", "25"],
            ["Charlie", "35"],
        ])
        reference_file = create_csv_file("reference.csv", [
            ["Name", "Age"],
            ["Alice", "30"],
        ])

        test = CompareFiles(
            name="test_compare",
            parameter=CompareFilesParameter(
                actual=str(actual_file),
                reference=str(reference_file),
                allow_extra_rows=False
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "extra row" in result.details[0]

    def test_compare_files_success_extra_rows_allowed(self, create_csv_file):
        """Test success when actual has extra rows and allowed."""
        actual_file = create_csv_file("actual.csv", [
            ["Name", "Age"],
            ["Alice", "30"],
            ["Bob", "25"],
        ])
        reference_file = create_csv_file("reference.csv", [
            ["Name", "Age"],
            ["Alice", "30"],
        ])

        test = CompareFiles(
            name="test_compare",
            parameter=CompareFilesParameter(
                actual=str(actual_file),
                reference=str(reference_file),
                allow_extra_rows=True
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_files_failure_missing_rows_not_allowed(self, create_csv_file):
        """Test failure when actual has missing rows and not allowed."""
        actual_file = create_csv_file("actual.csv", [
            ["Name", "Age"],
            ["Alice", "30"],
        ])
        reference_file = create_csv_file("reference.csv", [
            ["Name", "Age"],
            ["Alice", "30"],
            ["Bob", "25"],
        ])

        test = CompareFiles(
            name="test_compare",
            parameter=CompareFilesParameter(
                actual=str(actual_file),
                reference=str(reference_file),
                allow_missing_rows=False
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "missing row" in result.details[0]

    def test_compare_files_success_missing_rows_allowed(self, create_csv_file):
        """Test success when actual has missing rows and allowed."""
        actual_file = create_csv_file("actual.csv", [
            ["Name", "Age"],
            ["Alice", "30"],
        ])
        reference_file = create_csv_file("reference.csv", [
            ["Name", "Age"],
            ["Alice", "30"],
            ["Bob", "25"],
        ])

        test = CompareFiles(
            name="test_compare",
            parameter=CompareFilesParameter(
                actual=str(actual_file),
                reference=str(reference_file),
                allow_missing_rows=True
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_files_ignore_order_success(self, create_csv_file):
        """Test success with different order when ignore_order=True."""
        actual_file = create_csv_file("actual.csv", [
            ["Name", "Age"],
            ["Bob", "25"],
            ["Alice", "30"],
        ])
        reference_file = create_csv_file("reference.csv", [
            ["Name", "Age"],
            ["Alice", "30"],
            ["Bob", "25"],
        ])

        test = CompareFiles(
            name="test_compare",
            parameter=CompareFilesParameter(
                actual=str(actual_file),
                reference=str(reference_file),
                ignore_order=True
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_files_ignore_order_failure(self, create_csv_file):
        """Test failure with different order when ignore_order=False."""
        actual_file = create_csv_file("actual.csv", [
            ["Name", "Age"],
            ["Bob", "25"],
            ["Alice", "30"],
        ])
        reference_file = create_csv_file("reference.csv", [
            ["Name", "Age"],
            ["Alice", "30"],
            ["Bob", "25"],
        ])

        test = CompareFiles(
            name="test_compare",
            parameter=CompareFilesParameter(
                actual=str(actual_file),
                reference=str(reference_file),
                ignore_order=False
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "mismatched row" in result.details[0]

    def test_compare_files_column_selection(self, create_csv_file):
        """Test comparing only specific columns."""
        actual_file = create_csv_file("actual.csv", [
            ["Name", "Age", "City"],
            ["Alice", "30", "New York"],
            ["Bob", "25", "London"],
        ])
        reference_file = create_csv_file("reference.csv", [
            ["Name", "Age", "City"],
            ["Alice", "30", "Paris"],  # City is different but will be ignored
            ["Bob", "25", "Tokyo"],
        ])

        test = CompareFiles(
            name="test_compare",
            parameter=CompareFilesParameter(
                actual=str(actual_file),
                reference=str(reference_file),
                columns=[0, 1]  # Only compare Name and Age columns
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_files_column_selection_mismatch(self, create_csv_file):
        """Test failure when selected columns don't match."""
        actual_file = create_csv_file("actual.csv", [
            ["Name", "Age", "City"],
            ["Alice", "30", "New York"],
        ])
        reference_file = create_csv_file("reference.csv", [
            ["Name", "Age", "City"],
            ["Alice", "35", "New York"],  # Age is different
        ])

        test = CompareFiles(
            name="test_compare",
            parameter=CompareFilesParameter(
                actual=str(actual_file),
                reference=str(reference_file),
                columns=[0, 1]  # Compare Name and Age
            )
        )
        result = test.test()

        assert_test_failed(result)

    def test_compare_files_with_placeholder(self, create_csv_file, variable_metadata_simple):
        """Test comparison with placeholder in reference file."""
        actual_file = create_csv_file("actual.csv", [
            ["Name", "Value"],
            ["Alice", "value1"],
            ["Bob", "value2"],
        ])
        reference_file = create_csv_file("reference.csv", [
            ["Name", "Value"],
            ["Alice", "{{VAR1}}"],
            ["Bob", "{{VAR2}}"],
        ])

        test = CompareFiles(
            name="test_compare",
            parameter=CompareFilesParameter(
                actual=str(actual_file),
                reference=str(reference_file)
            ),
            variable_metadata=variable_metadata_simple
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_files_actual_not_found(self, create_csv_file, tmp_path):
        """Test failure when actual file doesn't exist."""
        reference_file = create_csv_file("reference.csv", [["Name"], ["Alice"]])

        test = CompareFiles(
            name="test_compare",
            parameter=CompareFilesParameter(
                actual=str(tmp_path / "nonexistent.csv"),
                reference=str(reference_file)
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "actual file" in result.details[0]
        assert "does not exist" in result.details[0]

    def test_compare_files_reference_not_found(self, create_csv_file, tmp_path):
        """Test failure when reference file doesn't exist."""
        actual_file = create_csv_file("actual.csv", [["Name"], ["Alice"]])

        test = CompareFiles(
            name="test_compare",
            parameter=CompareFilesParameter(
                actual=str(actual_file),
                reference=str(tmp_path / "nonexistent.csv")
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "reference file" in result.details[0]
        assert "does not exist" in result.details[0]

    def test_compare_files_empty_actual(self, create_csv_file):
        """Test comparison with empty actual file."""
        actual_file = create_csv_file("actual.csv", [])
        reference_file = create_csv_file("reference.csv", [["Name"], ["Alice"]])

        test = CompareFiles(
            name="test_compare",
            parameter=CompareFilesParameter(
                actual=str(actual_file),
                reference=str(reference_file),
                allow_missing_rows=False
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "missing row" in result.details[0]

    def test_compare_files_empty_reference(self, create_csv_file):
        """Test comparison with empty reference file."""
        actual_file = create_csv_file("actual.csv", [["Name"], ["Alice"]])
        reference_file = create_csv_file("reference.csv", [])

        test = CompareFiles(
            name="test_compare",
            parameter=CompareFilesParameter(
                actual=str(actual_file),
                reference=str(reference_file),
                allow_extra_rows=False
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "extra row" in result.details[0]

    def test_compare_files_both_empty(self, create_csv_file):
        """Test comparison with both files empty."""
        actual_file = create_csv_file("actual.csv", [])
        reference_file = create_csv_file("reference.csv", [])

        test = CompareFiles(
            name="test_compare",
            parameter=CompareFilesParameter(
                actual=str(actual_file),
                reference=str(reference_file)
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_files_ignore_order_with_extra_and_missing(self, create_csv_file):
        """Test ignore_order with extra and missing rows allowed."""
        actual_file = create_csv_file("actual.csv", [
            ["Name", "Age"],
            ["Charlie", "35"],
            ["Alice", "30"],
        ])
        reference_file = create_csv_file("reference.csv", [
            ["Name", "Age"],
            ["Alice", "30"],
            ["Bob", "25"],
        ])

        test = CompareFiles(
            name="test_compare",
            parameter=CompareFilesParameter(
                actual=str(actual_file),
                reference=str(reference_file),
                ignore_order=True,
                allow_extra_rows=True,
                allow_missing_rows=True
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_files_large_dataset(self, create_csv_file):
        """Test comparison with larger dataset."""
        rows = [["ID", "Value"]]
        for i in range(100):
            rows.append([str(i), f"value_{i}"])

        actual_file = create_csv_file("actual.csv", rows)
        reference_file = create_csv_file("reference.csv", rows)

        test = CompareFiles(
            name="test_compare",
            parameter=CompareFilesParameter(
                actual=str(actual_file),
                reference=str(reference_file)
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_files_single_row(self, create_csv_file):
        """Test comparison with single row."""
        actual_file = create_csv_file("actual.csv", [["Value"]])
        reference_file = create_csv_file("reference.csv", [["Value"]])

        test = CompareFiles(
            name="test_compare",
            parameter=CompareFilesParameter(
                actual=str(actual_file),
                reference=str(reference_file)
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_files_with_numeric_columns(self, create_csv_file):
        """Test comparison with numeric data."""
        actual_file = create_csv_file("actual.csv", [
            ["ID", "Score", "Percent"],
            ["1", "100", "95.5"],
            ["2", "85", "80.2"],
        ])
        reference_file = create_csv_file("reference.csv", [
            ["ID", "Score", "Percent"],
            ["1", "100", "95.5"],
            ["2", "85", "80.2"],
        ])

        test = CompareFiles(
            name="test_compare",
            parameter=CompareFilesParameter(
                actual=str(actual_file),
                reference=str(reference_file)
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_files_placeholder_with_ignore_order(self, create_csv_file, variable_metadata_simple):
        """Test placeholder matching with ignore_order enabled."""
        actual_file = create_csv_file("actual.csv", [
            ["Name", "Value"],
            ["Bob", "value2"],
            ["Alice", "value1"],
        ])
        reference_file = create_csv_file("reference.csv", [
            ["Name", "Value"],
            ["Alice", "{{VAR1}}"],
            ["Bob", "{{VAR2}}"],
        ])

        test = CompareFiles(
            name="test_compare",
            parameter=CompareFilesParameter(
                actual=str(actual_file),
                reference=str(reference_file),
                ignore_order=True
            ),
            variable_metadata=variable_metadata_simple
        )
        result = test.test()

        assert_test_success(result)
