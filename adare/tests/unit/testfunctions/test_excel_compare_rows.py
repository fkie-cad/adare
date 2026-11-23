"""Unit tests for excel.compare_rows (test_excel.py is at its size budget).

Runs on the guests' Python 3.10 too (``make test-testfunctions-guest``).
"""

import pytest
import sys
from pathlib import Path

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
CompareRows = excel_module.compare_rows._test_class
CompareRowsParameter = excel_module.compare_rows._parameter_class

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
# CompareRows Tests
# ============================================================================


class TestCompareRows:
    """Tests for CompareRows testfunction."""

    def test_compare_rows_exact_match(self, create_excel_file):
        """Test exact row comparison."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": [["Name", "Age"], ["Alice", "30"], ["Bob", "25"]]})

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(excel_file), reference_rows=[["Name", "Age"], ["Alice", "30"], ["Bob", "25"]]
            ),
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_mismatch(self, create_excel_file):
        """Test row comparison with mismatch."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": [["Alice", "30"], ["Bob", "25"]]})

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(excel_file),
                reference_rows=[
                    ["Alice", "30"],
                    ["Bob", "35"],  # Wrong age
                ],
            ),
        )
        result = test.test()

        assert_test_failed(result)
        assert "Excel comparison failed" in result.details[0]
        assert "mismatched" in result.details[0]

    def test_compare_rows_ignore_order_true(self, create_excel_file):
        """Test comparison with ignore_order=True."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": [["Bob", "25"], ["Alice", "30"]]})

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(excel_file), reference_rows=[["Alice", "30"], ["Bob", "25"]], ignore_order=True
            ),
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_ignore_order_false(self, create_excel_file):
        """Test comparison with ignore_order=False."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": [["Bob", "25"], ["Alice", "30"]]})

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(excel_file), reference_rows=[["Alice", "30"], ["Bob", "25"]], ignore_order=False
            ),
        )
        result = test.test()

        assert_test_failed(result)
        assert "mismatched" in result.details[0]

    def test_compare_rows_column_selection(self, create_excel_file):
        """Test comparison with specific column selection."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": [["Alice", "30", "New York"], ["Bob", "25", "London"]]})

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(excel_file),
                reference_rows=[["Alice", "30"], ["Bob", "25"]],
                columns=[0, 1],  # Only check first two columns
            ),
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_with_placeholder(self, create_excel_file, variable_metadata_simple):
        """Test comparison with placeholder."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": [["Alice", "value1"], ["Bob", "value2"]]})

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(excel_file), reference_rows=[["Alice", "{{VAR1}}"], ["Bob", "{{VAR2}}"]]
            ),
            variable_metadata=variable_metadata_simple,
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_allow_extra_rows(self, create_excel_file):
        """Test with allow_extra_rows=True."""
        excel_file = create_excel_file(
            "test.xlsx",
            {
                "Sheet1": [
                    ["Alice", "30"],
                    ["Bob", "25"],
                    ["Charlie", "35"],  # Extra row
                ]
            },
        )

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(excel_file), reference_rows=[["Alice", "30"], ["Bob", "25"]], allow_extra_rows=True
            ),
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_allow_missing_rows(self, create_excel_file):
        """Test with allow_missing_rows=True."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": [["Alice", "30"]]})

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(excel_file),
                reference_rows=[
                    ["Alice", "30"],
                    ["Bob", "25"],  # Missing in actual
                ],
                allow_missing_rows=True,
            ),
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_different_sheets(self, create_excel_file):
        """Test comparison on different sheet."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": [["A"], ["1"]], "Data": [["B"], ["2"]]})

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(dst=str(excel_file), sheet="Data", reference_rows=[["B"], ["2"]]),
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_empty_reference(self, create_excel_file):
        """Empty reference_rows is a parameter error."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": [["A"], ["1"]]})

        test = CompareRows(name="test_compare", parameter=CompareRowsParameter(dst=str(excel_file), reference_rows=[]))
        result = test.test()

        assert_test_error(result)
        assert "cannot be empty" in result.details[0]

    def test_compare_rows_empty_actual(self, create_excel_file):
        """Test with empty actual sheet."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": []})

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(dst=str(excel_file), reference_rows=[["A"], ["1"]], allow_missing_rows=True),
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_header_skip(self, create_excel_file):
        """Test with header row skip."""
        excel_file = create_excel_file(
            "test.xlsx",
            {
                "Sheet1": [
                    ["Name", "Age"],  # Header
                    ["Alice", "30"],
                    ["Bob", "25"],
                ]
            },
        )

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(excel_file),
                reference_rows=[["Alice", "30"], ["Bob", "25"]],
                header_row=1,  # Skip first row
            ),
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_column_index_invalid(self, create_excel_file):
        """Test with out-of-range column indices."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": [["A", "B"], ["1", "2"]]})

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(excel_file),
                reference_rows=[["A"], ["1"]],
                columns=[0, 5],  # Column 5 doesn't exist, only column 0 extracted
            ),
        )
        result = test.test()

        # Should still work - _extract_columns handles out of range gracefully
        assert_test_success(result)

    def test_compare_rows_mixed_placeholders(self, create_excel_file, variable_metadata_simple):
        """Test with mixed placeholder and literal values."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": [["Alice", "value1"], ["Bob", "literal"]]})

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(excel_file), reference_rows=[["Alice", "{{VAR1}}"], ["Bob", "literal"]]
            ),
            variable_metadata=variable_metadata_simple,
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_timestamp_tolerance(self, create_excel_file, variable_metadata_with_tolerance):
        """Test with timestamp tolerance."""
        excel_file = create_excel_file(
            "test.xlsx",
            {
                "Sheet1": [["1705314602"]]  # 2 seconds after expected
            },
        )

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(dst=str(excel_file), reference_rows=[["{{TIMESTAMP}}"]]),
            variable_metadata=variable_metadata_with_tolerance,
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_regex_placeholder(self, create_excel_file, variable_metadata_with_tolerance):
        """Test with regex placeholder."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": [["123-4567"]]})

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(dst=str(excel_file), reference_rows=[["{{REGEX_VAR}}"]]),
            variable_metadata=variable_metadata_with_tolerance,
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_sheet_not_found(self, create_excel_file):
        """Test failure with non-existent sheet."""
        excel_file = create_excel_file("test.xlsx", {"Sheet1": [["A"], ["1"]]})

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(dst=str(excel_file), sheet="NonExistent", reference_rows=[["A"], ["1"]]),
        )
        result = test.test()

        assert_test_failed(result)

    def test_compare_rows_file_not_found(self, tmp_path):
        """Test error when file doesn't exist."""
        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(dst=str(tmp_path / "nonexistent.xlsx"), reference_rows=[["A"], ["1"]]),
        )
        result = test.test()

        assert_test_error(result)
        assert "does not exist" in result.details[0]


# ============================================================================
# CompareRows Enhancement Tests (External Reference File)
# ============================================================================


class TestCompareRowsEnhancements:
    """Tests for CompareRows enhancements - external reference file support."""

    def test_compare_rows_reference_file_success(self, create_excel_file):
        """Test comparison using external reference file."""
        actual_file = create_excel_file("actual.xlsx", {"Sheet1": [["Name", "Age"], ["Alice", "30"], ["Bob", "25"]]})
        reference_file = create_excel_file(
            "reference.xlsx", {"Sheet1": [["Name", "Age"], ["Alice", "30"], ["Bob", "25"]]}
        )

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(dst=str(actual_file), reference_file=str(reference_file)),
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_reference_file_different_sheet(self, create_excel_file):
        """Test comparison using external reference file with different sheet."""
        actual_file = create_excel_file("actual.xlsx", {"Data": [["A"], ["1"], ["2"]]})
        reference_file = create_excel_file(
            "reference.xlsx", {"Sheet1": [["X"], ["Y"]], "Expected": [["A"], ["1"], ["2"]]}
        )

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(actual_file), sheet="Data", reference_file=str(reference_file), reference_sheet="Expected"
            ),
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_reference_file_with_header(self, create_excel_file):
        """Test comparison with header row skip in both files."""
        actual_file = create_excel_file(
            "actual.xlsx",
            {
                "Sheet1": [
                    ["Name", "Age"],  # Header
                    ["Alice", "30"],
                    ["Bob", "25"],
                ]
            },
        )
        reference_file = create_excel_file(
            "reference.xlsx",
            {
                "Sheet1": [
                    ["Name", "Age"],  # Header
                    ["Alice", "30"],
                    ["Bob", "25"],
                ]
            },
        )

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(actual_file), header_row=1, reference_file=str(reference_file), reference_header_row=1
            ),
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_reference_file_not_found(self, create_excel_file, tmp_path):
        """Test error when reference file doesn't exist."""
        actual_file = create_excel_file("actual.xlsx", {"Sheet1": [["A"], ["1"]]})

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(dst=str(actual_file), reference_file=str(tmp_path / "nonexistent.xlsx")),
        )
        result = test.test()

        assert_test_error(result)
        assert "reference_file" in result.details[0]
        assert "does not exist" in result.details[0]

    def test_compare_rows_reference_file_invalid_sheet(self, create_excel_file):
        """A missing reference sheet leaves nothing to compare: ERROR."""
        actual_file = create_excel_file("actual.xlsx", {"Sheet1": [["A"], ["1"]]})
        reference_file = create_excel_file("reference.xlsx", {"Sheet1": [["A"], ["1"]]})

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(actual_file), reference_file=str(reference_file), reference_sheet="NonExistent"
            ),
        )
        result = test.test()

        assert_test_error(result)
        assert "not found" in result.details[0]

    def test_compare_rows_both_reference_sources_error(self, create_excel_file):
        """Test error when both reference_rows and reference_file provided."""
        actual_file = create_excel_file("actual.xlsx", {"Sheet1": [["A"], ["1"]]})
        reference_file = create_excel_file("reference.xlsx", {"Sheet1": [["A"], ["1"]]})

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(
                dst=str(actual_file), reference_rows=[["A"], ["1"]], reference_file=str(reference_file)
            ),
        )
        result = test.test()

        assert_test_error(result)
        assert "Cannot provide both" in result.details[0]

    def test_compare_rows_no_reference_source_error(self, create_excel_file):
        """Test error when neither reference source provided."""
        actual_file = create_excel_file("actual.xlsx", {"Sheet1": [["A"], ["1"]]})

        test = CompareRows(name="test_compare", parameter=CompareRowsParameter(dst=str(actual_file)))
        result = test.test()

        assert_test_error(result)
        assert "Must provide either" in result.details[0]

    def test_compare_rows_reference_file_with_placeholders(self, create_excel_file, variable_metadata_simple):
        """Test comparison using external reference file with placeholders."""
        actual_file = create_excel_file(
            "actual.xlsx", {"Sheet1": [["Name", "Value"], ["Alice", "value1"], ["Bob", "value2"]]}
        )
        reference_file = create_excel_file(
            "reference.xlsx", {"Sheet1": [["Name", "Value"], ["Alice", "{{VAR1}}"], ["Bob", "{{VAR2}}"]]}
        )

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(dst=str(actual_file), reference_file=str(reference_file)),
            variable_metadata=variable_metadata_simple,
        )
        result = test.test()

        assert_test_success(result)

    def test_compare_rows_reference_file_ignore_order(self, create_excel_file):
        """Test external reference file with ignore_order=True."""
        actual_file = create_excel_file("actual.xlsx", {"Sheet1": [["Bob", "25"], ["Alice", "30"]]})
        reference_file = create_excel_file("reference.xlsx", {"Sheet1": [["Alice", "30"], ["Bob", "25"]]})

        test = CompareRows(
            name="test_compare",
            parameter=CompareRowsParameter(dst=str(actual_file), reference_file=str(reference_file), ignore_order=True),
        )
        result = test.test()

        assert_test_success(result)
