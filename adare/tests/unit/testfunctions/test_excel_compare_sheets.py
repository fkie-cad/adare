"""Unit tests for excel.compare_sheets and excel.compare_files (test_excel.py is at its size budget).

Runs on the guests' Python 3.10 too (``make test-testfunctions-guest``).
"""

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
CompareSheets = excel_module.compare_sheets._test_class
CompareSheetsParameter = excel_module.compare_sheets._parameter_class
CompareFiles = excel_module.compare_files._test_class
CompareFilesParameter = excel_module.compare_files._parameter_class

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
# CompareSheets Tests
# ============================================================================


class TestCompareSheets:
    """Tests for CompareSheets testfunction."""

    def test_compare_sheets_exact_match(self, create_excel_file):
        """Test exact sheet comparison."""
        excel_file = create_excel_file(
            "test.xlsx", {"Sheet1": [["A", "B"], ["1", "2"]], "Sheet2": [["A", "B"], ["1", "2"]]}
        )

        test = CompareSheets(
            name="test_compare_sheets",
            parameter=CompareSheetsParameter(
                actual=str(excel_file), reference=str(excel_file), actual_sheet="Sheet1", reference_sheet="Sheet2"
            ),
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_sheets_mismatch(self, create_excel_file):
        """Test sheet comparison with mismatch."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": [["A"], ["1"]], "Sheet2": [["A"], ["2"]]})

        test = CompareSheets(
            name="test_compare_sheets",
            parameter=CompareSheetsParameter(
                actual=str(excel_file), reference=str(excel_file), actual_sheet="Sheet1", reference_sheet="Sheet2"
            ),
        )
        result = test.test()

        assert_test_failed(result)
        assert "Excel comparison failed" in result.details[0]

    def test_compare_sheets_different_files(self, create_excel_file):
        """Test comparing sheets from different files."""
        actual_file = create_excel_file("actual.xlsx", {"Data": [["X", "Y"], ["1", "2"]]})
        reference_file = create_excel_file("reference.xlsx", {"Data": [["X", "Y"], ["1", "2"]]})

        test = CompareSheets(
            name="test_compare_sheets",
            parameter=CompareSheetsParameter(
                actual=str(actual_file), reference=str(reference_file), actual_sheet="Data", reference_sheet="Data"
            ),
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_sheets_same_file_different_sheets(self, create_excel_file):
        """Test comparing different sheets in same file."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": [["A"], ["1"]], "Sheet2": [["A"], ["1"]]})

        test = CompareSheets(
            name="test_compare_sheets",
            parameter=CompareSheetsParameter(
                actual=str(excel_file), reference=str(excel_file), actual_sheet=0, reference_sheet=1
            ),
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_sheets_with_placeholders(self, create_excel_file, variable_metadata_simple):
        """Test sheet comparison with placeholders."""
        actual_file = create_excel_file("actual.xlsx", {"Data": [["Name", "Value"], ["Alice", "value1"]]})
        reference_file = create_excel_file("reference.xlsx", {"Data": [["Name", "Value"], ["Alice", "{{VAR1}}"]]})

        test = CompareSheets(
            name="test_compare_sheets",
            parameter=CompareSheetsParameter(actual=str(actual_file), reference=str(reference_file)),
            variable_metadata=variable_metadata_simple,
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_sheets_ignore_order(self, create_excel_file):
        """Test sheet comparison with ignore_order=True."""
        actual_file = create_excel_file("actual.xlsx", {"Data": [["B"], ["A"]]})
        reference_file = create_excel_file("reference.xlsx", {"Data": [["A"], ["B"]]})

        test = CompareSheets(
            name="test_compare_sheets",
            parameter=CompareSheetsParameter(actual=str(actual_file), reference=str(reference_file), ignore_order=True),
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_sheets_column_selection(self, create_excel_file):
        """Test sheet comparison with column selection."""
        actual_file = create_excel_file("actual.xlsx", {"Data": [["A", "B", "C"], ["1", "2", "X"]]})
        reference_file = create_excel_file("reference.xlsx", {"Data": [["A", "B"], ["1", "2"]]})

        test = CompareSheets(
            name="test_compare_sheets",
            parameter=CompareSheetsParameter(actual=str(actual_file), reference=str(reference_file), columns=[0, 1]),
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_sheets_allow_extra_rows(self, create_excel_file):
        """Test sheet comparison with allow_extra_rows=True."""
        actual_file = create_excel_file("actual.xlsx", {"Data": [["A"], ["1"], ["2"]]})
        reference_file = create_excel_file("reference.xlsx", {"Data": [["A"], ["1"]]})

        test = CompareSheets(
            name="test_compare_sheets",
            parameter=CompareSheetsParameter(
                actual=str(actual_file), reference=str(reference_file), allow_extra_rows=True
            ),
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_sheets_sheet_by_name(self, create_excel_file):
        """Test accessing sheets by name."""
        excel_file = create_excel_file("test.xlsx", {"First": [["A"], ["1"]], "Second": [["A"], ["1"]]})

        test = CompareSheets(
            name="test_compare_sheets",
            parameter=CompareSheetsParameter(
                actual=str(excel_file), reference=str(excel_file), actual_sheet="First", reference_sheet="Second"
            ),
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_sheets_sheet_by_index(self, create_excel_file):
        """Test accessing sheets by index."""
        excel_file = create_excel_file("test.xlsx", {"First": [["A"], ["1"]], "Second": [["A"], ["1"]]})

        test = CompareSheets(
            name="test_compare_sheets",
            parameter=CompareSheetsParameter(
                actual=str(excel_file), reference=str(excel_file), actual_sheet=0, reference_sheet=1
            ),
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_sheets_mixed_sheet_identifiers(self, create_excel_file):
        """Test mixing sheet name and index."""
        excel_file = create_excel_file("test.xlsx", {"First": [["A"], ["1"]], "Second": [["A"], ["1"]]})

        test = CompareSheets(
            name="test_compare_sheets",
            parameter=CompareSheetsParameter(
                actual=str(excel_file),
                reference=str(excel_file),
                actual_sheet="First",
                reference_sheet=1,  # Index for second sheet
            ),
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_sheets_sheet_not_found(self, create_excel_file):
        """Test failure with non-existent sheet."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": [["A"], ["1"]]})

        test = CompareSheets(
            name="test_compare_sheets",
            parameter=CompareSheetsParameter(
                actual=str(excel_file), reference=str(excel_file), actual_sheet="NonExistent", reference_sheet="Sheet1"
            ),
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
        actual_file = create_excel_file("actual.xlsx", {"Sheet1": [["A", "B"], ["1", "2"]]})
        reference_file = create_excel_file("reference.xlsx", {"Sheet1": [["A", "B"], ["1", "2"]]})

        test = CompareFiles(
            name="test_compare_files",
            parameter=CompareFilesParameter(actual=str(actual_file), reference=str(reference_file)),
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_files_multi_sheet_exact(self, create_excel_file):
        """Test exact match with multiple sheets."""
        actual_file = create_excel_file(
            "actual.xlsx", {"Sheet1": [["A"], ["1"]], "Sheet2": [["B"], ["2"]], "Sheet3": [["C"], ["3"]]}
        )
        reference_file = create_excel_file(
            "reference.xlsx", {"Sheet1": [["A"], ["1"]], "Sheet2": [["B"], ["2"]], "Sheet3": [["C"], ["3"]]}
        )

        test = CompareFiles(
            name="test_compare_files",
            parameter=CompareFilesParameter(actual=str(actual_file), reference=str(reference_file)),
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_files_by_name_matching(self, create_excel_file):
        """Test by_name mode with matching sheet names."""
        actual_file = create_excel_file("actual.xlsx", {"Data": [["A"], ["1"]], "Summary": [["B"], ["2"]]})
        reference_file = create_excel_file(
            "reference.xlsx",
            {
                "Summary": [["B"], ["2"]],  # Different order
                "Data": [["A"], ["1"]],
            },
        )

        test = CompareFiles(
            name="test_compare_files",
            parameter=CompareFilesParameter(
                actual=str(actual_file), reference=str(reference_file), sheet_mode="by_name"
            ),
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_files_by_index_matching(self, create_excel_file):
        """Test by_index mode matching sheets by position."""
        actual_file = create_excel_file("actual.xlsx", {"Sheet1": [["A"], ["1"]], "Sheet2": [["B"], ["2"]]})
        reference_file = create_excel_file(
            "reference.xlsx", {"Different1": [["A"], ["1"]], "Different2": [["B"], ["2"]]}
        )

        test = CompareFiles(
            name="test_compare_files",
            parameter=CompareFilesParameter(
                actual=str(actual_file), reference=str(reference_file), sheet_mode="by_index"
            ),
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_files_specific_sheets(self, create_excel_file):
        """Test specific sheet mode."""
        actual_file = create_excel_file(
            "actual.xlsx", {"Data": [["A"], ["1"]], "Summary": [["B"], ["2"]], "Extra": [["C"], ["3"]]}
        )
        reference_file = create_excel_file(
            "reference.xlsx", {"Data": [["A"], ["1"]], "Summary": [["B"], ["2"]], "Other": [["D"], ["4"]]}
        )

        test = CompareFiles(
            name="test_compare_files",
            parameter=CompareFilesParameter(
                actual=str(actual_file),
                reference=str(reference_file),
                sheet_mode="specific",
                specific_sheets=["Data", "Summary"],
            ),
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_files_extra_sheets_allowed(self, create_excel_file):
        """Test with allow_extra_sheets=True."""
        actual_file = create_excel_file("actual.xlsx", {"Sheet1": [["A"], ["1"]], "Extra": [["B"], ["2"]]})
        reference_file = create_excel_file("reference.xlsx", {"Sheet1": [["A"], ["1"]]})

        test = CompareFiles(
            name="test_compare_files",
            parameter=CompareFilesParameter(
                actual=str(actual_file), reference=str(reference_file), allow_extra_sheets=True
            ),
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_files_missing_sheets_allowed(self, create_excel_file):
        """Test with allow_missing_sheets=True."""
        actual_file = create_excel_file("actual.xlsx", {"Sheet1": [["A"], ["1"]]})
        reference_file = create_excel_file("reference.xlsx", {"Sheet1": [["A"], ["1"]], "Missing": [["B"], ["2"]]})

        test = CompareFiles(
            name="test_compare_files",
            parameter=CompareFilesParameter(
                actual=str(actual_file), reference=str(reference_file), allow_missing_sheets=True
            ),
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_files_sheet_order_different(self, create_excel_file):
        """Test that by_name mode handles different sheet orders."""
        actual_file = create_excel_file(
            "actual.xlsx", {"Sheet1": [["A"], ["1"]], "Sheet2": [["B"], ["2"]], "Sheet3": [["C"], ["3"]]}
        )
        reference_file = create_excel_file(
            "reference.xlsx", {"Sheet3": [["C"], ["3"]], "Sheet1": [["A"], ["1"]], "Sheet2": [["B"], ["2"]]}
        )

        test = CompareFiles(
            name="test_compare_files",
            parameter=CompareFilesParameter(
                actual=str(actual_file), reference=str(reference_file), sheet_mode="by_name"
            ),
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_files_mixed_failures(self, create_excel_file):
        """Test with both sheet structure and content failures."""
        actual_file = create_excel_file("actual.xlsx", {"Sheet1": [["A"], ["1"]], "Extra": [["B"], ["2"]]})
        reference_file = create_excel_file(
            "reference.xlsx",
            {
                "Sheet1": [["A"], ["999"]],  # Content mismatch
                "Missing": [["C"], ["3"]],
            },
        )

        test = CompareFiles(
            name="test_compare_files",
            parameter=CompareFilesParameter(actual=str(actual_file), reference=str(reference_file)),
        )
        result = test.test()

        assert_test_failed(result)
        assert "Excel file comparison failed" in result.details[0]

    def test_compare_files_all_parameters(self, create_excel_file):
        """Test with all parameters enabled."""
        actual_file = create_excel_file(
            "actual.xlsx",
            {
                "Data": [
                    ["Name", "Age", "City"],  # Header
                    ["Bob", "25", "London"],
                    ["Alice", "30", "New York"],
                ]
            },
        )
        reference_file = create_excel_file(
            "reference.xlsx",
            {
                "Data": [
                    ["Name", "Age", "Extra"],  # Different header
                    ["Alice", "30", "X"],
                    ["Bob", "25", "Y"],
                ]
            },
        )

        test = CompareFiles(
            name="test_compare_files",
            parameter=CompareFilesParameter(
                actual=str(actual_file),
                reference=str(reference_file),
                sheet_mode="by_name",
                columns=[0, 1],  # Only compare Name and Age
                ignore_order=True,
                header_row=1,  # Skip header
            ),
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_files_ignore_order(self, create_excel_file):
        """Test file comparison with ignore_order=True."""
        actual_file = create_excel_file("actual.xlsx", {"Sheet1": [["2"], ["1"]]})
        reference_file = create_excel_file("reference.xlsx", {"Sheet1": [["1"], ["2"]]})

        test = CompareFiles(
            name="test_compare_files",
            parameter=CompareFilesParameter(actual=str(actual_file), reference=str(reference_file), ignore_order=True),
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_files_column_selection(self, create_excel_file):
        """Test file comparison with column selection."""
        actual_file = create_excel_file("actual.xlsx", {"Sheet1": [["A", "B", "X"], ["1", "2", "Y"]]})
        reference_file = create_excel_file("reference.xlsx", {"Sheet1": [["A", "B"], ["1", "2"]]})

        test = CompareFiles(
            name="test_compare_files",
            parameter=CompareFilesParameter(actual=str(actual_file), reference=str(reference_file), columns=[0, 1]),
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_files_with_placeholders(self, create_excel_file, variable_metadata_simple):
        """Test file comparison with placeholders."""
        actual_file = create_excel_file("actual.xlsx", {"Sheet1": [["Name", "Value"], ["Alice", "value1"]]})
        reference_file = create_excel_file("reference.xlsx", {"Sheet1": [["Name", "Value"], ["Alice", "{{VAR1}}"]]})

        test = CompareFiles(
            name="test_compare_files",
            parameter=CompareFilesParameter(actual=str(actual_file), reference=str(reference_file)),
            variable_metadata=variable_metadata_simple,
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
            parameter=CompareFilesParameter(actual=str(actual_file), reference=str(reference_file)),
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_files_complex_scenario(self, create_excel_file, variable_metadata_simple):
        """Test complex scenario with multiple features."""
        actual_file = create_excel_file(
            "actual.xlsx",
            {
                "Summary": [
                    ["ID", "Name", "Score", "Extra"],
                    ["2", "Bob", "value2", "X"],
                    ["1", "Alice", "value1", "Y"],
                ],
                "Details": [["A"], ["1"]],
            },
        )
        reference_file = create_excel_file(
            "reference.xlsx",
            {
                "Summary": [
                    ["ID", "Name", "Score", "Diff"],
                    ["1", "Alice", "{{VAR1}}", "Z"],
                    ["2", "Bob", "{{VAR2}}", "W"],
                ],
                "Details": [["A"], ["1"]],
                "Extra": [["B"], ["2"]],
            },
        )

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
                header_row=1,  # Skip header
            ),
            variable_metadata=variable_metadata_simple,
        )
        result = test.test()

        assert_test_success(result)
