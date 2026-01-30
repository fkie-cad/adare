# Excel Testfunction Enhancements

## Summary

Two major enhancements have been added to the Excel testfunction module:

1. **External Reference File Support** for `excel.compare_rows`
2. **Column Validation Testfunction** (`excel.validate_columns`)

## Enhancement 1: External Reference File Support

The `excel.compare_rows` testfunction now supports loading reference data from external Excel files in addition to embedded YAML data.

### Parameters Added

- `reference_file`: Optional path to external reference Excel file
- `reference_sheet`: Sheet name or index in reference file (default: 0)
- `reference_header_row`: Number of header rows to skip in reference file (default: None)

### Validation

- Exactly one reference source must be provided: either `reference_rows` OR `reference_file`
- Cannot provide both sources simultaneously
- Clear error messages when reference file is not found or sheet doesn't exist

### Usage Examples

#### Option 1: Embedded Reference (Existing Behavior)
```yaml
tests:
  - name: "Compare data with embedded reference"
    testname: "excel.compare_rows"
    dst: "output/results.xlsx"
    sheet: "Data"
    reference_rows:
      - ["ID", "Name", "Score"]
      - ["1", "Alice", "95"]
      - ["2", "Bob", "87"]
    ignore_order: true
```

#### Option 2: External Reference File (NEW)
```yaml
tests:
  - name: "Compare data with external baseline"
    testname: "excel.compare_rows"
    dst: "output/results.xlsx"
    sheet: "Data"
    reference_file: "baseline/expected_results.xlsx"
    reference_sheet: "ExpectedData"
    reference_header_row: 1
    ignore_order: true
```

### Benefits

- Cleaner playbook YAML files (reference data stored separately)
- Reuse reference files across multiple tests
- Store baseline data in native Excel format
- Easier to maintain reference data (edit in Excel instead of YAML)

## Enhancement 2: Column Validation Testfunction

New testfunction `excel.validate_columns` for validating column headers before data comparison.

### Parameters

- `dst`: Path to Excel file (required)
- `expected_columns`: List of expected column names (required)
- `sheet`: Sheet name or index (default: 0)
- `column_row`: Row index containing column headers (default: 0)
- `allow_extra_columns`: Allow extra columns in actual (default: False)
- `allow_missing_columns`: Allow missing columns in actual (default: False)
- `ignore_order`: Ignore column order (default: False)

### Features

- Validates column headers match expected list
- Detects missing columns (in expected but not in actual)
- Detects extra columns (in actual but not in expected)
- Validates column order (when `ignore_order=False`)
- Normalizes whitespace in column names for comparison
- Clear error messages showing exactly which columns are missing/extra

### Usage Examples

#### Basic Column Validation
```yaml
tests:
  - name: "Validate report structure"
    testname: "excel.validate_columns"
    dst: "output/report.xlsx"
    sheet: "Data"
    expected_columns: ["ID", "Name", "Score", "Date"]
```

#### Column Validation with Flexible Options
```yaml
tests:
  - name: "Validate columns (allow extras, ignore order)"
    testname: "excel.validate_columns"
    dst: "output/report.xlsx"
    expected_columns: ["ID", "Name", "Score"]
    allow_extra_columns: true
    ignore_order: true
```

#### Combined Workflow: Validate Columns First, Then Compare Data
```yaml
tests:
  # Step 1: Validate structure
  - name: "Check report structure"
    testname: "excel.validate_columns"
    dst: "output/report.xlsx"
    sheet: "Data"
    expected_columns: ["ID", "Name", "Score"]
    column_row: 0

  # Step 2: Compare data (skip header row)
  - name: "Compare report data"
    testname: "excel.compare_rows"
    dst: "output/report.xlsx"
    sheet: "Data"
    reference_file: "baseline/expected_report.xlsx"
    reference_sheet: "Data"
    header_row: 1
    ignore_order: true
```

## Benefits of Column Validation

1. **Early Failure Detection**: Validates structure before attempting data comparison
2. **Better Error Messages**: Shows exactly which columns are missing/extra
3. **Flexible Validation**: Can allow extra columns, missing columns, or different order
4. **Reusable**: Useful for smoke tests to verify schema before detailed comparison

## Test Coverage

- **CompareRows Enhancements**: 9 new tests
- **ValidateColumns**: 13 new tests
- **Total**: 93 tests (all passing)

## File Statistics

- `excel.py`: 1,390 lines (was 1,170 lines)
- `test_excel.py`: 2,108 lines (was 1,601 lines)
- Added ~220 lines to implementation, ~507 lines to tests

## Backwards Compatibility

Both enhancements are fully backwards compatible:
- Existing `reference_rows` parameter continues to work as before
- New `reference_file` parameters are optional
- `excel.validate_columns` is a new testfunction, no conflicts with existing code
