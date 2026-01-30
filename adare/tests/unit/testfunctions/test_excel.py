"""Comprehensive unit tests for Excel testfunctions."""

import pytest
import sys
from pathlib import Path
import pandas as pd

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

# Load Excel testfunctions module
excel_module_path = PROJECT_ROOT / "appdata" / "testfunctions" / "excel" / "excel.py"
excel_module = import_module_from_pyfile(excel_module_path)

# Extract testfunctions from module
SheetExists = excel_module.SheetExists
SheetExistsParameter = excel_module.SheetExistsParameter
CellValueMatches = excel_module.CellValueMatches
CellValueMatchesParameter = excel_module.CellValueMatchesParameter
ContainsRow = excel_module.ContainsRow
ContainsRowParameter = excel_module.ContainsRowParameter
ValidateColumns = excel_module.ValidateColumns
ValidateColumnsParameter = excel_module.ValidateColumnsParameter
CompareRows = excel_module.CompareRows
CompareRowsParameter = excel_module.CompareRowsParameter
CompareSheets = excel_module.CompareSheets
CompareSheetsParameter = excel_module.CompareSheetsParameter
CompareFiles = excel_module.CompareFiles
CompareFilesParameter = excel_module.CompareFilesParameter

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
# SheetExists Tests
# ============================================================================

class TestSheetExists:
    """Tests for SheetExists testfunction."""

    def test_sheet_exists_by_name_success(self, create_excel_file):
        """Test successful sheet existence check by name."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [["A", "B"], ["1", "2"]],
            "Data": [["X", "Y"], ["3", "4"]]
        })

        test = SheetExists(
            name="test_sheet_exists",
            parameter=SheetExistsParameter(
                dst=str(excel_file),
                sheet_name="Data"
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_sheet_exists_by_name_failure(self, create_excel_file):
        """Test failure when sheet doesn't exist."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [["A", "B"], ["1", "2"]]
        })

        test = SheetExists(
            name="test_sheet_exists",
            parameter=SheetExistsParameter(
                dst=str(excel_file),
                sheet_name="NonExistent"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "not found" in result.details[0]
        assert "available sheets" in result.details[1]

    def test_sheet_exists_regex_success(self, create_excel_file):
        """Test successful regex matching."""
        excel_file = create_excel_file("test.xlsx", {
            "Data_2024": [["A"], ["1"]],
            "Data_2025": [["B"], ["2"]]
        })

        test = SheetExists(
            name="test_sheet_exists",
            parameter=SheetExistsParameter(
                dst=str(excel_file),
                sheet_name=r"Data_\d{4}",
                regex_match=True
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_sheet_exists_regex_failure(self, create_excel_file):
        """Test regex failure when pattern doesn't match."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [["A"], ["1"]]
        })

        test = SheetExists(
            name="test_sheet_exists",
            parameter=SheetExistsParameter(
                dst=str(excel_file),
                sheet_name=r"Data_\d{4}",
                regex_match=True
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "no sheet matches regex" in result.details[0]

    def test_sheet_exists_invalid_file(self, tmp_path):
        """Test failure when file doesn't exist."""
        test = SheetExists(
            name="test_sheet_exists",
            parameter=SheetExistsParameter(
                dst=str(tmp_path / "nonexistent.xlsx"),
                sheet_name="Sheet1"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "does not exist" in result.details[0]

    def test_sheet_exists_empty_file(self, tmp_path):
        """Test with Excel file containing no sheets (edge case)."""
        # This is hard to create - pandas always creates at least one sheet
        # We'll test the error handling path instead
        excel_file = tmp_path / "test.xlsx"
        # Create a minimal valid xlsx file with one empty sheet
        df = pd.DataFrame()
        df.to_excel(excel_file, index=False, header=False)

        test = SheetExists(
            name="test_sheet_exists",
            parameter=SheetExistsParameter(
                dst=str(excel_file),
                sheet_name="Data"
            )
        )
        result = test.test()

        # Should fail because "Data" sheet doesn't exist
        assert_test_failed(result)


# ============================================================================
# CellValueMatches Tests
# ============================================================================

class TestCellValueMatches:
    """Tests for CellValueMatches testfunction."""

    def test_cell_value_exact_match(self, create_excel_file):
        """Test exact cell value match."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [
                ["Name", "Age", "City"],
                ["Alice", "30", "New York"],
                ["Bob", "25", "London"]
            ]
        })

        test = CellValueMatches(
            name="test_cell",
            parameter=CellValueMatchesParameter(
                dst=str(excel_file),
                row=1,
                column=0,
                expected_value="Alice"
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_cell_value_mismatch(self, create_excel_file):
        """Test cell value mismatch."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [["A", "B"], ["1", "2"]]
        })

        test = CellValueMatches(
            name="test_cell",
            parameter=CellValueMatchesParameter(
                dst=str(excel_file),
                row=1,
                column=0,
                expected_value="2"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "mismatch" in result.details[0]

    def test_cell_value_with_placeholder(self, create_excel_file, variable_metadata_simple):
        """Test cell value with placeholder."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [["Name", "Value"], ["Alice", "value1"]]
        })

        test = CellValueMatches(
            name="test_cell",
            parameter=CellValueMatchesParameter(
                dst=str(excel_file),
                row=1,
                column=1,
                expected_value="{{VAR1}}"
            ),
            variable_metadata=variable_metadata_simple
        )
        result = test.test()

        assert_test_success(result)

    def test_cell_value_out_of_bounds(self, create_excel_file):
        """Test row index out of bounds."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [["A"], ["1"]]
        })

        test = CellValueMatches(
            name="test_cell",
            parameter=CellValueMatchesParameter(
                dst=str(excel_file),
                row=10,
                column=0,
                expected_value="1"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "out of bounds" in result.details[0]

    def test_cell_value_numeric(self, create_excel_file):
        """Test with numeric cell value."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [["ID", "Score"], ["1", "95.5"]]
        })

        test = CellValueMatches(
            name="test_cell",
            parameter=CellValueMatchesParameter(
                dst=str(excel_file),
                row=1,
                column=1,
                expected_value="95.5"
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_cell_value_empty_cell(self, create_excel_file):
        """Test with empty cell (NaN)."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [["A", "B"], ["1", ""]]
        })

        test = CellValueMatches(
            name="test_cell",
            parameter=CellValueMatchesParameter(
                dst=str(excel_file),
                row=1,
                column=1,
                expected_value=""
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_cell_value_sheet_by_index(self, create_excel_file):
        """Test accessing sheet by index."""
        excel_file = create_excel_file("test.xlsx", {
            "First": [["A"], ["1"]],
            "Second": [["B"], ["2"]]
        })

        test = CellValueMatches(
            name="test_cell",
            parameter=CellValueMatchesParameter(
                dst=str(excel_file),
                sheet=1,  # Second sheet
                row=1,
                column=0,
                expected_value="2"
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_cell_value_sheet_by_name(self, create_excel_file):
        """Test accessing sheet by name."""
        excel_file = create_excel_file("test.xlsx", {
            "First": [["A"], ["1"]],
            "Second": [["B"], ["2"]]
        })

        test = CellValueMatches(
            name="test_cell",
            parameter=CellValueMatchesParameter(
                dst=str(excel_file),
                sheet="Second",
                row=1,
                column=0,
                expected_value="2"
            )
        )
        result = test.test()

        assert_test_success(result)


# ============================================================================
# ContainsRow Tests
# ============================================================================

class TestContainsRow:
    """Tests for ContainsRow testfunction."""

    def test_contains_row_success_exact(self, create_excel_file):
        """Test successful row match with exact values."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [
                ["Name", "Age", "City"],
                ["Alice", "30", "New York"],
                ["Bob", "25", "London"]
            ]
        })

        test = ContainsRow(
            name="test_contains",
            parameter=ContainsRowParameter(
                dst=str(excel_file),
                entry=["Bob", "25", "London"]
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_contains_row_failure(self, create_excel_file):
        """Test failure when no row matches."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [
                ["Name", "Age"],
                ["Alice", "30"],
                ["Bob", "25"]
            ]
        })

        test = ContainsRow(
            name="test_contains",
            parameter=ContainsRowParameter(
                dst=str(excel_file),
                entry=["Charlie", "35"]
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "no matching row found" in result.details[0]

    def test_contains_row_with_placeholder(self, create_excel_file, variable_metadata_simple):
        """Test row match with placeholder."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [
                ["Name", "Value"],
                ["Alice", "value1"],
                ["Bob", "value2"]
            ]
        })

        test = ContainsRow(
            name="test_contains",
            parameter=ContainsRowParameter(
                dst=str(excel_file),
                entry=["Bob", "{{VAR2}}"]
            ),
            variable_metadata=variable_metadata_simple
        )
        result = test.test()

        assert_test_success(result)

    def test_contains_row_specific_sheet_by_name(self, create_excel_file):
        """Test row search in specific sheet by name."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [["A"], ["1"]],
            "Data": [["B"], ["2"]]
        })

        test = ContainsRow(
            name="test_contains",
            parameter=ContainsRowParameter(
                dst=str(excel_file),
                sheet="Data",
                entry=["2"]
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_contains_row_sheet_by_index(self, create_excel_file):
        """Test row search in specific sheet by index."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [["A"], ["1"]],
            "Sheet2": [["B"], ["2"]]
        })

        test = ContainsRow(
            name="test_contains",
            parameter=ContainsRowParameter(
                dst=str(excel_file),
                sheet=1,
                entry=["2"]
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_contains_row_with_header(self, create_excel_file):
        """Test row search with header skip."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [
                ["Name", "Age"],  # Header row
                ["Alice", "30"],
                ["Bob", "25"]
            ]
        })

        test = ContainsRow(
            name="test_contains",
            parameter=ContainsRowParameter(
                dst=str(excel_file),
                entry=["Bob", "25"],
                header_row=1  # Skip first row
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_contains_row_empty_sheet(self, create_excel_file):
        """Test failure with empty sheet."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": []
        })

        test = ContainsRow(
            name="test_contains",
            parameter=ContainsRowParameter(
                dst=str(excel_file),
                entry=["A"]
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "no rows found" in result.details[1]

    def test_contains_row_partial_match(self, create_excel_file):
        """Test failure when only some columns match."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [
                ["Alice", "30", "New York"],
                ["Bob", "25", "London"]
            ]
        })

        test = ContainsRow(
            name="test_contains",
            parameter=ContainsRowParameter(
                dst=str(excel_file),
                entry=["Alice", "30", "London"]  # Wrong city
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "no matching row found" in result.details[0]
        assert "closest matches" in result.details[2]

    def test_contains_row_multiple_matches(self, create_excel_file):
        """Test with multiple matching rows (should succeed on first match)."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [
                ["Alice", "30"],
                ["Bob", "25"],
                ["Alice", "30"]  # Duplicate
            ]
        })

        test = ContainsRow(
            name="test_contains",
            parameter=ContainsRowParameter(
                dst=str(excel_file),
                entry=["Alice", "30"]
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_contains_row_column_mismatch(self, create_excel_file):
        """Test failure when column count doesn't match."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [
                ["Name", "Age", "City"],
                ["Alice", "30", "New York"]
            ]
        })

        test = ContainsRow(
            name="test_contains",
            parameter=ContainsRowParameter(
                dst=str(excel_file),
                entry=["Alice", "30"]  # Only 2 columns
            )
        )
        result = test.test()

        assert_test_failed(result)

    def test_contains_row_file_not_found(self, tmp_path):
        """Test failure when file doesn't exist."""
        test = ContainsRow(
            name="test_contains",
            parameter=ContainsRowParameter(
                dst=str(tmp_path / "nonexistent.xlsx"),
                entry=["A"]
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "does not exist" in result.details[0]

    def test_contains_row_invalid_sheet(self, create_excel_file):
        """Test failure with invalid sheet name."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [["A"], ["1"]]
        })

        test = ContainsRow(
            name="test_contains",
            parameter=ContainsRowParameter(
                dst=str(excel_file),
                sheet="NonExistent",
                entry=["1"]
            )
        )
        result = test.test()

        assert_test_failed(result)


# ============================================================================
# CompareRows Tests
# ============================================================================

class TestCompareRows:
    """Tests for CompareRows testfunction."""

    def test_compare_rows_exact_match(self, create_excel_file):
        """Test exact row comparison."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [
                ["Name", "Age"],
                ["Alice", "30"],
                ["Bob", "25"]
            ]
        })

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(excel_file),
                reference_rows=[
                    ["Name", "Age"],
                    ["Alice", "30"],
                    ["Bob", "25"]
                ]
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_mismatch(self, create_excel_file):
        """Test row comparison with mismatch."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [
                ["Alice", "30"],
                ["Bob", "25"]
            ]
        })

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(excel_file),
                reference_rows=[
                    ["Alice", "30"],
                    ["Bob", "35"]  # Wrong age
                ]
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "Excel comparison failed" in result.details[0]
        assert "mismatched" in result.details[0]

    def test_compare_rows_ignore_order_true(self, create_excel_file):
        """Test comparison with ignore_order=True."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [
                ["Bob", "25"],
                ["Alice", "30"]
            ]
        })

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(excel_file),
                reference_rows=[
                    ["Alice", "30"],
                    ["Bob", "25"]
                ],
                ignore_order=True
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_ignore_order_false(self, create_excel_file):
        """Test comparison with ignore_order=False."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [
                ["Bob", "25"],
                ["Alice", "30"]
            ]
        })

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(excel_file),
                reference_rows=[
                    ["Alice", "30"],
                    ["Bob", "25"]
                ],
                ignore_order=False
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "mismatched" in result.details[0]

    def test_compare_rows_column_selection(self, create_excel_file):
        """Test comparison with specific column selection."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [
                ["Alice", "30", "New York"],
                ["Bob", "25", "London"]
            ]
        })

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(excel_file),
                reference_rows=[
                    ["Alice", "30"],
                    ["Bob", "25"]
                ],
                columns=[0, 1]  # Only check first two columns
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_with_placeholder(self, create_excel_file, variable_metadata_simple):
        """Test comparison with placeholder."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [
                ["Alice", "value1"],
                ["Bob", "value2"]
            ]
        })

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(excel_file),
                reference_rows=[
                    ["Alice", "{{VAR1}}"],
                    ["Bob", "{{VAR2}}"]
                ]
            ),
            variable_metadata=variable_metadata_simple
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_allow_extra_rows(self, create_excel_file):
        """Test with allow_extra_rows=True."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [
                ["Alice", "30"],
                ["Bob", "25"],
                ["Charlie", "35"]  # Extra row
            ]
        })

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(excel_file),
                reference_rows=[
                    ["Alice", "30"],
                    ["Bob", "25"]
                ],
                allow_extra_rows=True
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_allow_missing_rows(self, create_excel_file):
        """Test with allow_missing_rows=True."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [
                ["Alice", "30"]
            ]
        })

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(excel_file),
                reference_rows=[
                    ["Alice", "30"],
                    ["Bob", "25"]  # Missing in actual
                ],
                allow_missing_rows=True
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_different_sheets(self, create_excel_file):
        """Test comparison on different sheet."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [["A"], ["1"]],
            "Data": [["B"], ["2"]]
        })

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(excel_file),
                sheet="Data",
                reference_rows=[["B"], ["2"]]
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_empty_reference(self, create_excel_file):
        """Test failure with empty reference."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [["A"], ["1"]]
        })

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(excel_file),
                reference_rows=[]
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "cannot be empty" in result.details[0]

    def test_compare_rows_empty_actual(self, create_excel_file):
        """Test with empty actual sheet."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": []
        })

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(excel_file),
                reference_rows=[["A"], ["1"]],
                allow_missing_rows=True
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_header_skip(self, create_excel_file):
        """Test with header row skip."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [
                ["Name", "Age"],  # Header
                ["Alice", "30"],
                ["Bob", "25"]
            ]
        })

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(excel_file),
                reference_rows=[
                    ["Alice", "30"],
                    ["Bob", "25"]
                ],
                header_row=1  # Skip first row
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_column_index_invalid(self, create_excel_file):
        """Test with out-of-range column indices."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [["A", "B"], ["1", "2"]]
        })

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(excel_file),
                reference_rows=[["A"], ["1"]],
                columns=[0, 5]  # Column 5 doesn't exist, only column 0 extracted
            )
        )
        result = test.test()

        # Should still work - _extract_columns handles out of range gracefully
        assert_test_success(result)

    def test_compare_rows_mixed_placeholders(self, create_excel_file, variable_metadata_simple):
        """Test with mixed placeholder and literal values."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [
                ["Alice", "value1"],
                ["Bob", "literal"]
            ]
        })

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(excel_file),
                reference_rows=[
                    ["Alice", "{{VAR1}}"],
                    ["Bob", "literal"]
                ]
            ),
            variable_metadata=variable_metadata_simple
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_timestamp_tolerance(self, create_excel_file, variable_metadata_with_tolerance):
        """Test with timestamp tolerance."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [["1705314602"]]  # 2 seconds after expected
        })

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(excel_file),
                reference_rows=[["{{TIMESTAMP}}"]]
            ),
            variable_metadata=variable_metadata_with_tolerance
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_regex_placeholder(self, create_excel_file, variable_metadata_with_tolerance):
        """Test with regex placeholder."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [["123-4567"]]
        })

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(excel_file),
                reference_rows=[["{{REGEX_VAR}}"]]
            ),
            variable_metadata=variable_metadata_with_tolerance
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_sheet_not_found(self, create_excel_file):
        """Test failure with non-existent sheet."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [["A"], ["1"]]
        })

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(excel_file),
                sheet="NonExistent",
                reference_rows=[["A"], ["1"]]
            )
        )
        result = test.test()

        assert_test_failed(result)

    def test_compare_rows_file_not_found(self, tmp_path):
        """Test failure when file doesn't exist."""
        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(tmp_path / "nonexistent.xlsx"),
                reference_rows=[["A"], ["1"]]
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "does not exist" in result.details[0]


# ============================================================================
# CompareRows Enhancement Tests (External Reference File)
# ============================================================================

class TestCompareRowsEnhancements:
    """Tests for CompareRows enhancements - external reference file support."""

    def test_compare_rows_reference_file_success(self, create_excel_file):
        """Test comparison using external reference file."""
        actual_file = create_excel_file("actual.xlsx", {
            "Sheet1": [
                ["Name", "Age"],
                ["Alice", "30"],
                ["Bob", "25"]
            ]
        })
        reference_file = create_excel_file("reference.xlsx", {
            "Sheet1": [
                ["Name", "Age"],
                ["Alice", "30"],
                ["Bob", "25"]
            ]
        })

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(actual_file),
                reference_file=str(reference_file)
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_reference_file_different_sheet(self, create_excel_file):
        """Test comparison using external reference file with different sheet."""
        actual_file = create_excel_file("actual.xlsx", {
            "Data": [["A"], ["1"], ["2"]]
        })
        reference_file = create_excel_file("reference.xlsx", {
            "Sheet1": [["X"], ["Y"]],
            "Expected": [["A"], ["1"], ["2"]]
        })

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(actual_file),
                sheet="Data",
                reference_file=str(reference_file),
                reference_sheet="Expected"
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_reference_file_with_header(self, create_excel_file):
        """Test comparison with header row skip in both files."""
        actual_file = create_excel_file("actual.xlsx", {
            "Sheet1": [
                ["Name", "Age"],  # Header
                ["Alice", "30"],
                ["Bob", "25"]
            ]
        })
        reference_file = create_excel_file("reference.xlsx", {
            "Sheet1": [
                ["Name", "Age"],  # Header
                ["Alice", "30"],
                ["Bob", "25"]
            ]
        })

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(actual_file),
                header_row=1,
                reference_file=str(reference_file),
                reference_header_row=1
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_reference_file_not_found(self, create_excel_file, tmp_path):
        """Test failure when reference file doesn't exist."""
        actual_file = create_excel_file("actual.xlsx", {
            "Sheet1": [["A"], ["1"]]
        })

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(actual_file),
                reference_file=str(tmp_path / "nonexistent.xlsx")
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "reference_file" in result.details[0]
        assert "does not exist" in result.details[0]

    def test_compare_rows_reference_file_invalid_sheet(self, create_excel_file):
        """Test failure when reference file sheet doesn't exist."""
        actual_file = create_excel_file("actual.xlsx", {
            "Sheet1": [["A"], ["1"]]
        })
        reference_file = create_excel_file("reference.xlsx", {
            "Sheet1": [["A"], ["1"]]
        })

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(actual_file),
                reference_file=str(reference_file),
                reference_sheet="NonExistent"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "Error reading reference file" in result.details[0]

    def test_compare_rows_both_reference_sources_error(self, create_excel_file):
        """Test error when both reference_rows and reference_file provided."""
        actual_file = create_excel_file("actual.xlsx", {
            "Sheet1": [["A"], ["1"]]
        })
        reference_file = create_excel_file("reference.xlsx", {
            "Sheet1": [["A"], ["1"]]
        })

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(actual_file),
                reference_rows=[["A"], ["1"]],
                reference_file=str(reference_file)
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "Cannot provide both" in result.details[0]

    def test_compare_rows_no_reference_source_error(self, create_excel_file):
        """Test error when neither reference source provided."""
        actual_file = create_excel_file("actual.xlsx", {
            "Sheet1": [["A"], ["1"]]
        })

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(actual_file)
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "Must provide either" in result.details[0]

    def test_compare_rows_reference_file_with_placeholders(self, create_excel_file, variable_metadata_simple):
        """Test comparison using external reference file with placeholders."""
        actual_file = create_excel_file("actual.xlsx", {
            "Sheet1": [
                ["Name", "Value"],
                ["Alice", "value1"],
                ["Bob", "value2"]
            ]
        })
        reference_file = create_excel_file("reference.xlsx", {
            "Sheet1": [
                ["Name", "Value"],
                ["Alice", "{{VAR1}}"],
                ["Bob", "{{VAR2}}"]
            ]
        })

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(actual_file),
                reference_file=str(reference_file)
            ),
            variable_metadata=variable_metadata_simple
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_reference_file_ignore_order(self, create_excel_file):
        """Test external reference file with ignore_order=True."""
        actual_file = create_excel_file("actual.xlsx", {
            "Sheet1": [
                ["Bob", "25"],
                ["Alice", "30"]
            ]
        })
        reference_file = create_excel_file("reference.xlsx", {
            "Sheet1": [
                ["Alice", "30"],
                ["Bob", "25"]
            ]
        })

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(actual_file),
                reference_file=str(reference_file),
                ignore_order=True
            )
        )
        result = test.test()

        assert_test_success(result)


# ============================================================================
# ValidateColumns Tests
# ============================================================================

class TestValidateColumns:
    """Tests for ValidateColumns testfunction."""

    def test_validate_columns_exact_match(self, create_excel_file):
        """Test exact column match."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [
                ["ID", "Name", "Score"],
                ["1", "Alice", "95"]
            ]
        })

        test = ValidateColumns(
            name="test_validate",
            parameter=ValidateColumnsParameter(
                dst=str(excel_file),
                expected_columns=["ID", "Name", "Score"]
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_validate_columns_missing_columns(self, create_excel_file):
        """Test failure with missing columns."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [
                ["ID", "Name"],
                ["1", "Alice"]
            ]
        })

        test = ValidateColumns(
            name="test_validate",
            parameter=ValidateColumnsParameter(
                dst=str(excel_file),
                expected_columns=["ID", "Name", "Score"]
            )
        )
        result = test.test()

        assert_test_failed(result)
        details_text = '\n'.join(result.details)
        assert "Column validation failed" in details_text
        assert "missing column" in details_text
        assert "Missing columns" in details_text
        assert "Score" in details_text

    def test_validate_columns_extra_columns(self, create_excel_file):
        """Test failure with extra columns."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [
                ["ID", "Name", "Score", "Extra"],
                ["1", "Alice", "95", "X"]
            ]
        })

        test = ValidateColumns(
            name="test_validate",
            parameter=ValidateColumnsParameter(
                dst=str(excel_file),
                expected_columns=["ID", "Name", "Score"]
            )
        )
        result = test.test()

        assert_test_failed(result)
        details_text = '\n'.join(result.details)
        assert "Column validation failed" in details_text
        assert "extra column" in details_text
        assert "Extra columns" in details_text
        assert "Extra" in details_text

    def test_validate_columns_allow_extra_columns(self, create_excel_file):
        """Test success with allow_extra_columns=True."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [
                ["ID", "Name", "Score", "Extra"],
                ["1", "Alice", "95", "X"]
            ]
        })

        test = ValidateColumns(
            name="test_validate",
            parameter=ValidateColumnsParameter(
                dst=str(excel_file),
                expected_columns=["ID", "Name", "Score"],
                allow_extra_columns=True
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_validate_columns_allow_missing_columns(self, create_excel_file):
        """Test success with allow_missing_columns=True."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [
                ["ID", "Name"],
                ["1", "Alice"]
            ]
        })

        test = ValidateColumns(
            name="test_validate",
            parameter=ValidateColumnsParameter(
                dst=str(excel_file),
                expected_columns=["ID", "Name", "Score"],
                allow_missing_columns=True
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_validate_columns_ignore_order_true(self, create_excel_file):
        """Test success with different column order when ignore_order=True."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [
                ["Score", "ID", "Name"],
                ["95", "1", "Alice"]
            ]
        })

        test = ValidateColumns(
            name="test_validate",
            parameter=ValidateColumnsParameter(
                dst=str(excel_file),
                expected_columns=["ID", "Name", "Score"],
                ignore_order=True
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_validate_columns_ignore_order_false(self, create_excel_file):
        """Test failure with different column order when ignore_order=False."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [
                ["Score", "ID", "Name"],
                ["95", "1", "Alice"]
            ]
        })

        test = ValidateColumns(
            name="test_validate",
            parameter=ValidateColumnsParameter(
                dst=str(excel_file),
                expected_columns=["ID", "Name", "Score"],
                ignore_order=False
            )
        )
        result = test.test()

        assert_test_failed(result)
        details_text = '\n'.join(result.details)
        assert "Column validation failed" in details_text
        assert "order mismatch" in details_text

    def test_validate_columns_different_sheet(self, create_excel_file):
        """Test validation on specific sheet."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [["A", "B"], ["1", "2"]],
            "Data": [["ID", "Name"], ["1", "Alice"]]
        })

        test = ValidateColumns(
            name="test_validate",
            parameter=ValidateColumnsParameter(
                dst=str(excel_file),
                sheet="Data",
                expected_columns=["ID", "Name"]
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_validate_columns_empty_row(self, create_excel_file):
        """Test failure with empty column row."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [
                ["", "", ""],
                ["1", "Alice", "95"]
            ]
        })

        test = ValidateColumns(
            name="test_validate",
            parameter=ValidateColumnsParameter(
                dst=str(excel_file),
                expected_columns=["ID", "Name", "Score"]
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "is empty" in result.details[0]

    def test_validate_columns_file_not_found(self, tmp_path):
        """Test failure when file doesn't exist."""
        test = ValidateColumns(
            name="test_validate",
            parameter=ValidateColumnsParameter(
                dst=str(tmp_path / "nonexistent.xlsx"),
                expected_columns=["ID", "Name"]
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "does not exist" in result.details[0]

    def test_validate_columns_column_row_out_of_bounds(self, create_excel_file):
        """Test failure when column_row is out of bounds."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [
                ["ID", "Name"],
                ["1", "Alice"]
            ]
        })

        test = ValidateColumns(
            name="test_validate",
            parameter=ValidateColumnsParameter(
                dst=str(excel_file),
                column_row=10,
                expected_columns=["ID", "Name"]
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "out of bounds" in result.details[0]

    def test_validate_columns_sheet_by_index(self, create_excel_file):
        """Test accessing sheet by index."""
        excel_file = create_excel_file("test.xlsx", {
            "First": [["A", "B"], ["1", "2"]],
            "Second": [["ID", "Name"], ["1", "Alice"]]
        })

        test = ValidateColumns(
            name="test_validate",
            parameter=ValidateColumnsParameter(
                dst=str(excel_file),
                sheet=1,
                expected_columns=["ID", "Name"]
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_validate_columns_whitespace_normalization(self, create_excel_file):
        """Test that whitespace is normalized in column names."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [
                ["  ID  ", " Name ", "Score  "],
                ["1", "Alice", "95"]
            ]
        })

        test = ValidateColumns(
            name="test_validate",
            parameter=ValidateColumnsParameter(
                dst=str(excel_file),
                expected_columns=["ID", "Name", "Score"]
            )
        )
        result = test.test()

        assert_test_success(result)


# ============================================================================
# CompareSheets Tests
# ============================================================================

class TestCompareSheets:
    """Tests for CompareSheets testfunction."""

    def test_compare_sheets_exact_match(self, create_excel_file):
        """Test exact sheet comparison."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [["A", "B"], ["1", "2"]],
            "Sheet2": [["A", "B"], ["1", "2"]]
        })

        test = CompareSheets(
            name="test_compare_sheets",
            parameter=CompareSheetsParameter(
                actual=str(excel_file),
                reference=str(excel_file),
                actual_sheet="Sheet1",
                reference_sheet="Sheet2"
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_sheets_mismatch(self, create_excel_file):
        """Test sheet comparison with mismatch."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [["A"], ["1"]],
            "Sheet2": [["A"], ["2"]]
        })

        test = CompareSheets(
            name="test_compare_sheets",
            parameter=CompareSheetsParameter(
                actual=str(excel_file),
                reference=str(excel_file),
                actual_sheet="Sheet1",
                reference_sheet="Sheet2"
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "Excel comparison failed" in result.details[0]

    def test_compare_sheets_different_files(self, create_excel_file):
        """Test comparing sheets from different files."""
        actual_file = create_excel_file("actual.xlsx", {
            "Data": [["X", "Y"], ["1", "2"]]
        })
        reference_file = create_excel_file("reference.xlsx", {
            "Data": [["X", "Y"], ["1", "2"]]
        })

        test = CompareSheets(
            name="test_compare_sheets",
            parameter=CompareSheetsParameter(
                actual=str(actual_file),
                reference=str(reference_file),
                actual_sheet="Data",
                reference_sheet="Data"
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_sheets_same_file_different_sheets(self, create_excel_file):
        """Test comparing different sheets in same file."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [["A"], ["1"]],
            "Sheet2": [["A"], ["1"]]
        })

        test = CompareSheets(
            name="test_compare_sheets",
            parameter=CompareSheetsParameter(
                actual=str(excel_file),
                reference=str(excel_file),
                actual_sheet=0,
                reference_sheet=1
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_sheets_with_placeholders(self, create_excel_file, variable_metadata_simple):
        """Test sheet comparison with placeholders."""
        actual_file = create_excel_file("actual.xlsx", {
            "Data": [["Name", "Value"], ["Alice", "value1"]]
        })
        reference_file = create_excel_file("reference.xlsx", {
            "Data": [["Name", "Value"], ["Alice", "{{VAR1}}"]]
        })

        test = CompareSheets(
            name="test_compare_sheets",
            parameter=CompareSheetsParameter(
                actual=str(actual_file),
                reference=str(reference_file)
            ),
            variable_metadata=variable_metadata_simple
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_sheets_ignore_order(self, create_excel_file):
        """Test sheet comparison with ignore_order=True."""
        actual_file = create_excel_file("actual.xlsx", {
            "Data": [["B"], ["A"]]
        })
        reference_file = create_excel_file("reference.xlsx", {
            "Data": [["A"], ["B"]]
        })

        test = CompareSheets(
            name="test_compare_sheets",
            parameter=CompareSheetsParameter(
                actual=str(actual_file),
                reference=str(reference_file),
                ignore_order=True
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_sheets_column_selection(self, create_excel_file):
        """Test sheet comparison with column selection."""
        actual_file = create_excel_file("actual.xlsx", {
            "Data": [["A", "B", "C"], ["1", "2", "X"]]
        })
        reference_file = create_excel_file("reference.xlsx", {
            "Data": [["A", "B"], ["1", "2"]]
        })

        test = CompareSheets(
            name="test_compare_sheets",
            parameter=CompareSheetsParameter(
                actual=str(actual_file),
                reference=str(reference_file),
                columns=[0, 1]
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_sheets_allow_extra_rows(self, create_excel_file):
        """Test sheet comparison with allow_extra_rows=True."""
        actual_file = create_excel_file("actual.xlsx", {
            "Data": [["A"], ["1"], ["2"]]
        })
        reference_file = create_excel_file("reference.xlsx", {
            "Data": [["A"], ["1"]]
        })

        test = CompareSheets(
            name="test_compare_sheets",
            parameter=CompareSheetsParameter(
                actual=str(actual_file),
                reference=str(reference_file),
                allow_extra_rows=True
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_sheets_sheet_by_name(self, create_excel_file):
        """Test accessing sheets by name."""
        excel_file = create_excel_file("test.xlsx", {
            "First": [["A"], ["1"]],
            "Second": [["A"], ["1"]]
        })

        test = CompareSheets(
            name="test_compare_sheets",
            parameter=CompareSheetsParameter(
                actual=str(excel_file),
                reference=str(excel_file),
                actual_sheet="First",
                reference_sheet="Second"
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_sheets_sheet_by_index(self, create_excel_file):
        """Test accessing sheets by index."""
        excel_file = create_excel_file("test.xlsx", {
            "First": [["A"], ["1"]],
            "Second": [["A"], ["1"]]
        })

        test = CompareSheets(
            name="test_compare_sheets",
            parameter=CompareSheetsParameter(
                actual=str(excel_file),
                reference=str(excel_file),
                actual_sheet=0,
                reference_sheet=1
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_sheets_mixed_sheet_identifiers(self, create_excel_file):
        """Test mixing sheet name and index."""
        excel_file = create_excel_file("test.xlsx", {
            "First": [["A"], ["1"]],
            "Second": [["A"], ["1"]]
        })

        test = CompareSheets(
            name="test_compare_sheets",
            parameter=CompareSheetsParameter(
                actual=str(excel_file),
                reference=str(excel_file),
                actual_sheet="First",
                reference_sheet=1  # Index for second sheet
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_sheets_sheet_not_found(self, create_excel_file):
        """Test failure with non-existent sheet."""
        excel_file = create_excel_file("test.xlsx", {
            "Sheet1": [["A"], ["1"]]
        })

        test = CompareSheets(
            name="test_compare_sheets",
            parameter=CompareSheetsParameter(
                actual=str(excel_file),
                reference=str(excel_file),
                actual_sheet="NonExistent",
                reference_sheet="Sheet1"
            )
        )
        result = test.test()

        assert_test_failed(result)


# ============================================================================
# CompareFiles Tests
# ============================================================================

class TestCompareFiles:
    """Tests for CompareFiles testfunction."""

    def test_compare_files_single_sheet_exact(self, create_excel_file):
        """Test exact match with single sheet."""
        actual_file = create_excel_file("actual.xlsx", {
            "Sheet1": [["A", "B"], ["1", "2"]]
        })
        reference_file = create_excel_file("reference.xlsx", {
            "Sheet1": [["A", "B"], ["1", "2"]]
        })

        test = CompareFiles(
            name="test_compare_files",
            parameter=CompareFilesParameter(
                actual=str(actual_file),
                reference=str(reference_file)
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_files_multi_sheet_exact(self, create_excel_file):
        """Test exact match with multiple sheets."""
        actual_file = create_excel_file("actual.xlsx", {
            "Sheet1": [["A"], ["1"]],
            "Sheet2": [["B"], ["2"]],
            "Sheet3": [["C"], ["3"]]
        })
        reference_file = create_excel_file("reference.xlsx", {
            "Sheet1": [["A"], ["1"]],
            "Sheet2": [["B"], ["2"]],
            "Sheet3": [["C"], ["3"]]
        })

        test = CompareFiles(
            name="test_compare_files",
            parameter=CompareFilesParameter(
                actual=str(actual_file),
                reference=str(reference_file)
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_files_by_name_matching(self, create_excel_file):
        """Test by_name mode with matching sheet names."""
        actual_file = create_excel_file("actual.xlsx", {
            "Data": [["A"], ["1"]],
            "Summary": [["B"], ["2"]]
        })
        reference_file = create_excel_file("reference.xlsx", {
            "Summary": [["B"], ["2"]],  # Different order
            "Data": [["A"], ["1"]]
        })

        test = CompareFiles(
            name="test_compare_files",
            parameter=CompareFilesParameter(
                actual=str(actual_file),
                reference=str(reference_file),
                sheet_mode="by_name"
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_files_by_index_matching(self, create_excel_file):
        """Test by_index mode matching sheets by position."""
        actual_file = create_excel_file("actual.xlsx", {
            "Sheet1": [["A"], ["1"]],
            "Sheet2": [["B"], ["2"]]
        })
        reference_file = create_excel_file("reference.xlsx", {
            "Different1": [["A"], ["1"]],
            "Different2": [["B"], ["2"]]
        })

        test = CompareFiles(
            name="test_compare_files",
            parameter=CompareFilesParameter(
                actual=str(actual_file),
                reference=str(reference_file),
                sheet_mode="by_index"
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_files_specific_sheets(self, create_excel_file):
        """Test specific sheet mode."""
        actual_file = create_excel_file("actual.xlsx", {
            "Data": [["A"], ["1"]],
            "Summary": [["B"], ["2"]],
            "Extra": [["C"], ["3"]]
        })
        reference_file = create_excel_file("reference.xlsx", {
            "Data": [["A"], ["1"]],
            "Summary": [["B"], ["2"]],
            "Other": [["D"], ["4"]]
        })

        test = CompareFiles(
            name="test_compare_files",
            parameter=CompareFilesParameter(
                actual=str(actual_file),
                reference=str(reference_file),
                sheet_mode="specific",
                specific_sheets=["Data", "Summary"]
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_files_extra_sheets_allowed(self, create_excel_file):
        """Test with allow_extra_sheets=True."""
        actual_file = create_excel_file("actual.xlsx", {
            "Sheet1": [["A"], ["1"]],
            "Extra": [["B"], ["2"]]
        })
        reference_file = create_excel_file("reference.xlsx", {
            "Sheet1": [["A"], ["1"]]
        })

        test = CompareFiles(
            name="test_compare_files",
            parameter=CompareFilesParameter(
                actual=str(actual_file),
                reference=str(reference_file),
                allow_extra_sheets=True
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_files_missing_sheets_allowed(self, create_excel_file):
        """Test with allow_missing_sheets=True."""
        actual_file = create_excel_file("actual.xlsx", {
            "Sheet1": [["A"], ["1"]]
        })
        reference_file = create_excel_file("reference.xlsx", {
            "Sheet1": [["A"], ["1"]],
            "Missing": [["B"], ["2"]]
        })

        test = CompareFiles(
            name="test_compare_files",
            parameter=CompareFilesParameter(
                actual=str(actual_file),
                reference=str(reference_file),
                allow_missing_sheets=True
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_files_sheet_order_different(self, create_excel_file):
        """Test that by_name mode handles different sheet orders."""
        actual_file = create_excel_file("actual.xlsx", {
            "Sheet1": [["A"], ["1"]],
            "Sheet2": [["B"], ["2"]],
            "Sheet3": [["C"], ["3"]]
        })
        reference_file = create_excel_file("reference.xlsx", {
            "Sheet3": [["C"], ["3"]],
            "Sheet1": [["A"], ["1"]],
            "Sheet2": [["B"], ["2"]]
        })

        test = CompareFiles(
            name="test_compare_files",
            parameter=CompareFilesParameter(
                actual=str(actual_file),
                reference=str(reference_file),
                sheet_mode="by_name"
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_files_mixed_failures(self, create_excel_file):
        """Test with both sheet structure and content failures."""
        actual_file = create_excel_file("actual.xlsx", {
            "Sheet1": [["A"], ["1"]],
            "Extra": [["B"], ["2"]]
        })
        reference_file = create_excel_file("reference.xlsx", {
            "Sheet1": [["A"], ["999"]],  # Content mismatch
            "Missing": [["C"], ["3"]]
        })

        test = CompareFiles(
            name="test_compare_files",
            parameter=CompareFilesParameter(
                actual=str(actual_file),
                reference=str(reference_file)
            )
        )
        result = test.test()

        assert_test_failed(result)
        assert "Excel file comparison failed" in result.details[0]

    def test_compare_files_all_parameters(self, create_excel_file):
        """Test with all parameters enabled."""
        actual_file = create_excel_file("actual.xlsx", {
            "Data": [
                ["Name", "Age", "City"],  # Header
                ["Bob", "25", "London"],
                ["Alice", "30", "New York"]
            ]
        })
        reference_file = create_excel_file("reference.xlsx", {
            "Data": [
                ["Name", "Age", "Extra"],  # Different header
                ["Alice", "30", "X"],
                ["Bob", "25", "Y"]
            ]
        })

        test = CompareFiles(
            name="test_compare_files",
            parameter=CompareFilesParameter(
                actual=str(actual_file),
                reference=str(reference_file),
                sheet_mode="by_name",
                columns=[0, 1],  # Only compare Name and Age
                ignore_order=True,
                header_row=1  # Skip header
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_files_ignore_order(self, create_excel_file):
        """Test file comparison with ignore_order=True."""
        actual_file = create_excel_file("actual.xlsx", {
            "Sheet1": [["2"], ["1"]]
        })
        reference_file = create_excel_file("reference.xlsx", {
            "Sheet1": [["1"], ["2"]]
        })

        test = CompareFiles(
            name="test_compare_files",
            parameter=CompareFilesParameter(
                actual=str(actual_file),
                reference=str(reference_file),
                ignore_order=True
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_files_column_selection(self, create_excel_file):
        """Test file comparison with column selection."""
        actual_file = create_excel_file("actual.xlsx", {
            "Sheet1": [["A", "B", "X"], ["1", "2", "Y"]]
        })
        reference_file = create_excel_file("reference.xlsx", {
            "Sheet1": [["A", "B"], ["1", "2"]]
        })

        test = CompareFiles(
            name="test_compare_files",
            parameter=CompareFilesParameter(
                actual=str(actual_file),
                reference=str(reference_file),
                columns=[0, 1]
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_files_with_placeholders(self, create_excel_file, variable_metadata_simple):
        """Test file comparison with placeholders."""
        actual_file = create_excel_file("actual.xlsx", {
            "Sheet1": [["Name", "Value"], ["Alice", "value1"]]
        })
        reference_file = create_excel_file("reference.xlsx", {
            "Sheet1": [["Name", "Value"], ["Alice", "{{VAR1}}"]]
        })

        test = CompareFiles(
            name="test_compare_files",
            parameter=CompareFilesParameter(
                actual=str(actual_file),
                reference=str(reference_file)
            ),
            variable_metadata=variable_metadata_simple
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_files_empty_files(self, tmp_path):
        """Test with empty Excel files."""
        actual_file = tmp_path / "actual.xlsx"
        reference_file = tmp_path / "reference.xlsx"

        # Create minimal Excel files with empty sheets
        pd.DataFrame().to_excel(actual_file, index=False, header=False)
        pd.DataFrame().to_excel(reference_file, index=False, header=False)

        test = CompareFiles(
            name="test_compare_files",
            parameter=CompareFilesParameter(
                actual=str(actual_file),
                reference=str(reference_file)
            )
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_files_complex_scenario(self, create_excel_file, variable_metadata_simple):
        """Test complex scenario with multiple features."""
        actual_file = create_excel_file("actual.xlsx", {
            "Summary": [
                ["ID", "Name", "Score", "Extra"],
                ["2", "Bob", "value2", "X"],
                ["1", "Alice", "value1", "Y"]
            ],
            "Details": [["A"], ["1"]]
        })
        reference_file = create_excel_file("reference.xlsx", {
            "Summary": [
                ["ID", "Name", "Score", "Diff"],
                ["1", "Alice", "{{VAR1}}", "Z"],
                ["2", "Bob", "{{VAR2}}", "W"]
            ],
            "Details": [["A"], ["1"]],
            "Extra": [["B"], ["2"]]
        })

        test = CompareFiles(
            name="test_compare_files",
            parameter=CompareFilesParameter(
                actual=str(actual_file),
                reference=str(reference_file),
                sheet_mode="by_name",
                columns=[0, 1, 2],  # Compare ID, Name, Score only
                ignore_order=True,
                allow_extra_sheets=True,
                allow_missing_sheets=True,  # Allow Extra sheet in reference but not actual
                header_row=1  # Skip header
            ),
            variable_metadata=variable_metadata_simple
        )
        result = test.test()

        assert_test_success(result)
