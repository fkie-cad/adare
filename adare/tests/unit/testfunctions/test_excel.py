"""Comprehensive unit tests for Excel testfunctions."""

import pytest
import sys
from pathlib import Path
import pandas as pd

pytestmark = pytest.mark.unit

# Add paths for imports
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
ADARELIB_ROOT = PROJECT_ROOT.parent / "adarelib"

# Add to sys.path if not already there
if str(ADARELIB_ROOT) not in sys.path:
    sys.path.insert(0, str(ADARELIB_ROOT))

# Import testfunctions dynamically
from adarelib.helper.module import import_module_from_pyfile

# Load Excel testfunctions module
excel_module_path = PROJECT_ROOT / "appdata" / "testfunctions" / "excel" / "excel.py"
excel_module = import_module_from_pyfile(excel_module_path)

# Extract testfunctions from module
SheetExists = excel_module.sheet_exists._test_class
SheetExistsParameter = excel_module.sheet_exists._parameter_class
CellValueMatches = excel_module.cell_value_matches._test_class
CellValueMatchesParameter = excel_module.cell_value_matches._parameter_class
ContainsRow = excel_module.contains_row._test_class
ContainsRowParameter = excel_module.contains_row._parameter_class
ValidateColumns = excel_module.validate_columns._test_class
ValidateColumnsParameter = excel_module.validate_columns._parameter_class

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
        excel_file = create_excel_file(
            "test.xlsx", {"Sheet1": [["A", "B"], ["1", "2"]], "Data": [["X", "Y"], ["3", "4"]]}
        )

        test = SheetExists(name="test_sheet_exists", parameter=SheetExistsParameter(dst=str(excel_file), sheet="Data"))
        result = test.test()

        assert_test_success(result)

    def test_sheet_exists_by_name_failure(self, create_excel_file):
        """Test failure when sheet doesn't exist."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": [["A", "B"], ["1", "2"]]})

        test = SheetExists(
            name="test_sheet_exists", parameter=SheetExistsParameter(dst=str(excel_file), sheet="NonExistent")
        )
        result = test.test()

        assert_test_failed(result)
        assert "not found" in result.details[0]
        assert "available sheets" in result.details[1]

    def test_sheet_exists_regex_success(self, create_excel_file):
        """Test successful regex matching."""
        excel_file = create_excel_file("test.xlsx", {"Data_2024": [["A"], ["1"]], "Data_2025": [["B"], ["2"]]})

        test = SheetExists(
            name="test_sheet_exists",
            parameter=SheetExistsParameter(dst=str(excel_file), sheet=r"Data_\d{4}", regex_match=True),
        )
        result = test.test()

        assert_test_success(result)

    def test_sheet_exists_regex_failure(self, create_excel_file):
        """Test regex failure when pattern doesn't match."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": [["A"], ["1"]]})

        test = SheetExists(
            name="test_sheet_exists",
            parameter=SheetExistsParameter(dst=str(excel_file), sheet=r"Data_\d{4}", regex_match=True),
        )
        result = test.test()

        assert_test_failed(result)
        assert "no sheet matches regex" in result.details[0]

    def test_sheet_exists_invalid_file(self, tmp_path):
        """Test error when file doesn't exist."""
        test = SheetExists(
            name="test_sheet_exists",
            parameter=SheetExistsParameter(dst=str(tmp_path / "nonexistent.xlsx"), sheet="Sheet1"),
        )
        result = test.test()

        assert_test_error(result)
        assert "does not exist" in result.details[0]

    def test_sheet_exists_empty_file(self, tmp_path):
        """Test with Excel file containing no sheets (edge case)."""
        # This is hard to create - pandas always creates at least one sheet
        # We'll test the error handling path instead
        excel_file = tmp_path / "test.xlsx"
        # Create a minimal valid xlsx file with one empty sheet
        df = pd.DataFrame()
        df.to_excel(excel_file, index=False, header=False)

        test = SheetExists(name="test_sheet_exists", parameter=SheetExistsParameter(dst=str(excel_file), sheet="Data"))
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
        excel_file = create_excel_file(
            "test.xlsx", {"Sheet1": [["Name", "Age", "City"], ["Alice", "30", "New York"], ["Bob", "25", "London"]]}
        )

        test = CellValueMatches(
            name="test_cell",
            parameter=CellValueMatchesParameter(dst=str(excel_file), row=1, column=0, expected_value="Alice"),
        )
        result = test.test()

        assert_test_success(result)

    def test_cell_value_mismatch(self, create_excel_file):
        """Test cell value mismatch."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": [["A", "B"], ["1", "2"]]})

        test = CellValueMatches(
            name="test_cell",
            parameter=CellValueMatchesParameter(dst=str(excel_file), row=1, column=0, expected_value="2"),
        )
        result = test.test()

        assert_test_failed(result)
        assert "mismatch" in result.details[0]

    def test_cell_value_with_placeholder(self, create_excel_file, variable_metadata_simple):
        """Test cell value with placeholder."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": [["Name", "Value"], ["Alice", "value1"]]})

        test = CellValueMatches(
            name="test_cell",
            parameter=CellValueMatchesParameter(dst=str(excel_file), row=1, column=1, expected_value="{{VAR1}}"),
            variable_metadata=variable_metadata_simple,
        )
        result = test.test()

        assert_test_success(result)

    def test_cell_value_out_of_bounds(self, create_excel_file):
        """Test row index out of bounds."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": [["A"], ["1"]]})

        test = CellValueMatches(
            name="test_cell",
            parameter=CellValueMatchesParameter(dst=str(excel_file), row=10, column=0, expected_value="1"),
        )
        result = test.test()

        assert_test_failed(result)
        assert "out of bounds" in result.details[0]

    def test_cell_value_numeric(self, create_excel_file):
        """Test with numeric cell value."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": [["ID", "Score"], ["1", "95.5"]]})

        test = CellValueMatches(
            name="test_cell",
            parameter=CellValueMatchesParameter(dst=str(excel_file), row=1, column=1, expected_value="95.5"),
        )
        result = test.test()

        assert_test_success(result)

    def test_cell_value_empty_cell(self, create_excel_file):
        """Test with empty cell (NaN)."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": [["A", "B"], ["1", ""]]})

        test = CellValueMatches(
            name="test_cell",
            parameter=CellValueMatchesParameter(dst=str(excel_file), row=1, column=1, expected_value=""),
        )
        result = test.test()

        assert_test_success(result)

    def test_cell_value_sheet_by_index(self, create_excel_file):
        """Test accessing sheet by index."""
        excel_file = create_excel_file("test.xlsx", {"First": [["A"], ["1"]], "Second": [["B"], ["2"]]})

        test = CellValueMatches(
            name="test_cell",
            parameter=CellValueMatchesParameter(
                dst=str(excel_file),
                sheet=1,  # Second sheet
                row=1,
                column=0,
                expected_value="2",
            ),
        )
        result = test.test()

        assert_test_success(result)

    def test_cell_value_sheet_by_name(self, create_excel_file):
        """Test accessing sheet by name."""
        excel_file = create_excel_file("test.xlsx", {"First": [["A"], ["1"]], "Second": [["B"], ["2"]]})

        test = CellValueMatches(
            name="test_cell",
            parameter=CellValueMatchesParameter(
                dst=str(excel_file), sheet="Second", row=1, column=0, expected_value="2"
            ),
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
        excel_file = create_excel_file(
            "test.xlsx", {"Sheet1": [["Name", "Age", "City"], ["Alice", "30", "New York"], ["Bob", "25", "London"]]}
        )

        test = ContainsRow(
            name="test_contains", parameter=ContainsRowParameter(dst=str(excel_file), entry=["Bob", "25", "London"])
        )
        result = test.test()

        assert_test_success(result)

    def test_contains_row_failure(self, create_excel_file):
        """Test failure when no row matches."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": [["Name", "Age"], ["Alice", "30"], ["Bob", "25"]]})

        test = ContainsRow(
            name="test_contains", parameter=ContainsRowParameter(dst=str(excel_file), entry=["Charlie", "35"])
        )
        result = test.test()

        assert_test_failed(result)
        assert "no matching row found" in result.details[0]

    def test_contains_row_with_placeholder(self, create_excel_file, variable_metadata_simple):
        """Test row match with placeholder."""
        excel_file = create_excel_file(
            "test.xlsx", {"Sheet1": [["Name", "Value"], ["Alice", "value1"], ["Bob", "value2"]]}
        )

        test = ContainsRow(
            name="test_contains",
            parameter=ContainsRowParameter(dst=str(excel_file), entry=["Bob", "{{VAR2}}"]),
            variable_metadata=variable_metadata_simple,
        )
        result = test.test()

        assert_test_success(result)

    def test_contains_row_specific_sheet_by_name(self, create_excel_file):
        """Test row search in specific sheet by name."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": [["A"], ["1"]], "Data": [["B"], ["2"]]})

        test = ContainsRow(
            name="test_contains", parameter=ContainsRowParameter(dst=str(excel_file), sheet="Data", entry=["2"])
        )
        result = test.test()

        assert_test_success(result)

    def test_contains_row_sheet_by_index(self, create_excel_file):
        """Test row search in specific sheet by index."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": [["A"], ["1"]], "Sheet2": [["B"], ["2"]]})

        test = ContainsRow(
            name="test_contains", parameter=ContainsRowParameter(dst=str(excel_file), sheet=1, entry=["2"])
        )
        result = test.test()

        assert_test_success(result)

    def test_contains_row_with_header(self, create_excel_file):
        """Test row search with header skip."""
        excel_file = create_excel_file(
            "test.xlsx",
            {
                "Sheet1": [
                    ["Name", "Age"],  # Header row
                    ["Alice", "30"],
                    ["Bob", "25"],
                ]
            },
        )

        test = ContainsRow(
            name="test_contains",
            parameter=ContainsRowParameter(
                dst=str(excel_file),
                entry=["Bob", "25"],
                header_row=1,  # Skip first row
            ),
        )
        result = test.test()

        assert_test_success(result)

    def test_contains_row_empty_sheet(self, create_excel_file):
        """Test failure with empty sheet."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": []})

        test = ContainsRow(name="test_contains", parameter=ContainsRowParameter(dst=str(excel_file), entry=["A"]))
        result = test.test()

        assert_test_failed(result)
        assert "no rows found" in result.details[1]

    def test_contains_row_partial_match(self, create_excel_file):
        """Test failure when only some columns match."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": [["Alice", "30", "New York"], ["Bob", "25", "London"]]})

        test = ContainsRow(
            name="test_contains",
            parameter=ContainsRowParameter(
                dst=str(excel_file),
                entry=["Alice", "30", "London"],  # Wrong city
            ),
        )
        result = test.test()

        assert_test_failed(result)
        assert "no matching row found" in result.details[0]
        assert "closest matches" in result.details[2]

    def test_contains_row_multiple_matches(self, create_excel_file):
        """Test with multiple matching rows (should succeed on first match)."""
        excel_file = create_excel_file(
            "test.xlsx",
            {
                "Sheet1": [
                    ["Alice", "30"],
                    ["Bob", "25"],
                    ["Alice", "30"],  # Duplicate
                ]
            },
        )

        test = ContainsRow(
            name="test_contains", parameter=ContainsRowParameter(dst=str(excel_file), entry=["Alice", "30"])
        )
        result = test.test()

        assert_test_success(result)

    def test_contains_row_column_mismatch(self, create_excel_file):
        """Test failure when column count doesn't match."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": [["Name", "Age", "City"], ["Alice", "30", "New York"]]})

        test = ContainsRow(
            name="test_contains",
            parameter=ContainsRowParameter(
                dst=str(excel_file),
                entry=["Alice", "30"],  # Only 2 columns
            ),
        )
        result = test.test()

        assert_test_failed(result)

    def test_contains_row_file_not_found(self, tmp_path):
        """Test error when file doesn't exist."""
        test = ContainsRow(
            name="test_contains", parameter=ContainsRowParameter(dst=str(tmp_path / "nonexistent.xlsx"), entry=["A"])
        )
        result = test.test()

        assert_test_error(result)
        assert "does not exist" in result.details[0]

    def test_contains_row_invalid_sheet(self, create_excel_file):
        """Test failure with invalid sheet name."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": [["A"], ["1"]]})

        test = ContainsRow(
            name="test_contains", parameter=ContainsRowParameter(dst=str(excel_file), sheet="NonExistent", entry=["1"])
        )
        result = test.test()

        assert_test_failed(result)


# ============================================================================
# ValidateColumns Tests
# ============================================================================


class TestValidateColumns:
    """Tests for ValidateColumns testfunction."""

    def test_validate_columns_exact_match(self, create_excel_file):
        """Test exact column match."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": [["ID", "Name", "Score"], ["1", "Alice", "95"]]})

        test = ValidateColumns(
            name="test_validate",
            parameter=ValidateColumnsParameter(dst=str(excel_file), expected_columns=["ID", "Name", "Score"]),
        )
        result = test.test()

        assert_test_success(result)

    def test_validate_columns_missing_columns(self, create_excel_file):
        """Test failure with missing columns."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": [["ID", "Name"], ["1", "Alice"]]})

        test = ValidateColumns(
            name="test_validate",
            parameter=ValidateColumnsParameter(dst=str(excel_file), expected_columns=["ID", "Name", "Score"]),
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
        excel_file = create_excel_file(
            "test.xlsx", {"Sheet1": [["ID", "Name", "Score", "Extra"], ["1", "Alice", "95", "X"]]}
        )

        test = ValidateColumns(
            name="test_validate",
            parameter=ValidateColumnsParameter(dst=str(excel_file), expected_columns=["ID", "Name", "Score"]),
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
        excel_file = create_excel_file(
            "test.xlsx", {"Sheet1": [["ID", "Name", "Score", "Extra"], ["1", "Alice", "95", "X"]]}
        )

        test = ValidateColumns(
            name="test_validate",
            parameter=ValidateColumnsParameter(
                dst=str(excel_file), expected_columns=["ID", "Name", "Score"], allow_extra_columns=True
            ),
        )
        result = test.test()

        assert_test_success(result)

    def test_validate_columns_allow_missing_columns(self, create_excel_file):
        """Test success with allow_missing_columns=True."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": [["ID", "Name"], ["1", "Alice"]]})

        test = ValidateColumns(
            name="test_validate",
            parameter=ValidateColumnsParameter(
                dst=str(excel_file), expected_columns=["ID", "Name", "Score"], allow_missing_columns=True
            ),
        )
        result = test.test()

        assert_test_success(result)

    def test_validate_columns_ignore_order_true(self, create_excel_file):
        """Test success with different column order when ignore_order=True."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": [["Score", "ID", "Name"], ["95", "1", "Alice"]]})

        test = ValidateColumns(
            name="test_validate",
            parameter=ValidateColumnsParameter(
                dst=str(excel_file), expected_columns=["ID", "Name", "Score"], ignore_order=True
            ),
        )
        result = test.test()

        assert_test_success(result)

    def test_validate_columns_ignore_order_false(self, create_excel_file):
        """Test failure with different column order when ignore_order=False."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": [["Score", "ID", "Name"], ["95", "1", "Alice"]]})

        test = ValidateColumns(
            name="test_validate",
            parameter=ValidateColumnsParameter(
                dst=str(excel_file), expected_columns=["ID", "Name", "Score"], ignore_order=False
            ),
        )
        result = test.test()

        assert_test_failed(result)
        details_text = '\n'.join(result.details)
        assert "Column validation failed" in details_text
        assert "order mismatch" in details_text

    def test_validate_columns_different_sheet(self, create_excel_file):
        """Test validation on specific sheet."""
        excel_file = create_excel_file(
            "test.xlsx", {"Sheet1": [["A", "B"], ["1", "2"]], "Data": [["ID", "Name"], ["1", "Alice"]]}
        )

        test = ValidateColumns(
            name="test_validate",
            parameter=ValidateColumnsParameter(dst=str(excel_file), sheet="Data", expected_columns=["ID", "Name"]),
        )
        result = test.test()

        assert_test_success(result)

    def test_validate_columns_empty_row(self, create_excel_file):
        """Test failure with empty column row."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": [["", "", ""], ["1", "Alice", "95"]]})

        test = ValidateColumns(
            name="test_validate",
            parameter=ValidateColumnsParameter(dst=str(excel_file), expected_columns=["ID", "Name", "Score"]),
        )
        result = test.test()

        assert_test_failed(result)
        assert "is empty" in result.details[0]

    def test_validate_columns_file_not_found(self, tmp_path):
        """Test error when file doesn't exist."""
        test = ValidateColumns(
            name="test_validate",
            parameter=ValidateColumnsParameter(dst=str(tmp_path / "nonexistent.xlsx"), expected_columns=["ID", "Name"]),
        )
        result = test.test()

        assert_test_error(result)
        assert "does not exist" in result.details[0]

    def test_validate_columns_column_row_out_of_bounds(self, create_excel_file):
        """Test failure when column_row is out of bounds."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": [["ID", "Name"], ["1", "Alice"]]})

        test = ValidateColumns(
            name="test_validate",
            parameter=ValidateColumnsParameter(dst=str(excel_file), column_row=10, expected_columns=["ID", "Name"]),
        )
        result = test.test()

        assert_test_failed(result)
        assert "out of bounds" in result.details[0]

    def test_validate_columns_sheet_by_index(self, create_excel_file):
        """Test accessing sheet by index."""
        excel_file = create_excel_file(
            "test.xlsx", {"First": [["A", "B"], ["1", "2"]], "Second": [["ID", "Name"], ["1", "Alice"]]}
        )

        test = ValidateColumns(
            name="test_validate",
            parameter=ValidateColumnsParameter(dst=str(excel_file), sheet=1, expected_columns=["ID", "Name"]),
        )
        result = test.test()

        assert_test_success(result)

    def test_validate_columns_whitespace_normalization(self, create_excel_file):
        """Test that whitespace is normalized in column names."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": [["  ID  ", " Name ", "Score  "], ["1", "Alice", "95"]]})

        test = ValidateColumns(
            name="test_validate",
            parameter=ValidateColumnsParameter(dst=str(excel_file), expected_columns=["ID", "Name", "Score"]),
        )
        result = test.test()

        assert_test_success(result)
