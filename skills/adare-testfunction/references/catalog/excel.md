# Excel (`excel.*`)

<!-- Generated; do not edit by hand. -->

Excel workbooks (.xlsx) a spreadsheet application saved: a sheet exists, one cell has a value, a row exists or occurs n times, the header layout, and whole sheets or workbooks compared with reference data. Workbooks are read with pandas and openpyxl, and every cell is compared as a string: an empty cell is `''`, numbers use `str()` (`5.0` when the whole row is numeric), dates read as `2024-01-31 00:00:00` or `2024-01-31T00:00:00`. Rows and columns are 0-based, `sheet` is a name or a 0-based index, and `header_row` is the number of top rows to skip.

## `excel.cell_value_matches`

validates specific cell value with placeholder support

Pass when the cell at (`row`, `column`) of a sheet equals `expected_value`.

With `comparison_type` (`greater`, `less`, ...), `tolerance` or the time parameters the value is compared as a number or timestamp (cell text such as `1500.0` or `2024-01-31 00:00:00` reads as a number or an ISO timestamp).

**Use for:** asserting one value a user typed or a formula result saved in a workbook. Cells are read via pandas and stringified: empty -> `''`; numbers via `str()` (an int may read as `5.0` if pandas upcasts the column/row to float); dates as `2024-01-31 00:00:00` or `2024-01-31T00:00:00` depending on the row's other cells -- use `!re` for dates and numbers when unsure.

asserts: value, order · formats: excel · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Regex values (!re) (`regex_tag`), Placeholders ({{ variable }}) (`placeholder`), Times as expected values (!timestamp) (`timestamp_tag`), Ordered comparison of numbers and times (`ordered_comparison`)

**Not for:**
- a row anywhere in the sheet, whatever its position → `excel.contains_row`
- a sheet exists → `excel.sheet_exists`
- workbook properties (author, last modified by) → `xml.element_text_matches`
- a value in a CSV file → `csv.contains_line`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` | `''` | Guest path to the .xlsx; a glob must match exactly one path. A missing or unreadable file is an error. |
| row | `int` | `0` | 0-based row index in the raw sheet (row 0 = spreadsheet row 1); out of range fails. |
| column | `int` | `0` | 0-based column index (A = 0); out of range fails. |
| expected_value | `str \| int \| float \| bool \| None` | `None` | Compared exactly with `str(expected_value)` (`None` -> `''`). A single `!re`/`!timestamp` tag is matched by type. |
| sheet | `str \| int` | `0` | Sheet name (str) or 0-based sheet index (int); unknown sheets fail. |
| regex_match | `bool` | `False` | Treat `expected_value` as a regex searched in the cell value (`re.search`, unanchored; `^...$` for the whole value); an invalid regex is an error. |
| comparison_type | `str` | `'equals'` | `equals` (default), `not_equals`, `greater`, `less`, `greater_equal` or `less_equal`. Anything but `equals`, or any parameter below, compares the value with `expected_value` as a number or point in time (ordered mode; `less` = earlier); a `!re` tag, `{{placeholder}}` or `regex_match` is then an error, and so is a value that is no number or timestamp. Allowed: `equals`, `not_equals`, `greater`, `less`, `greater_equal`, `less_equal`. |
| value_type | `str` | `'auto'` | `auto` (default; numbers if both sides are numbers, else timestamps), `number` or `timestamp`. Allowed: `auto`, `number`, `timestamp`. |
| tolerance | `int \| float \| None` | `None` | Allowed difference for `equals`/`not_equals` (seconds for timestamps). |
| time_format | `str \| None` | `None` | `strptime` format of text timestamps on both sides; default ISO 8601 or RFC 2822. |
| timestamp_epoch | `int \| None` | `None` | Read numbers as a count since 1 January of `1970`, `1601` or `2001`. Allowed: `1970`, `1601`, `2001`. |
| timestamp_unit | `str \| None` | `None` | Unit of that count: `s` (default), `ms`, `us`, `ns` or `100ns`. Allowed: `s`, `ms`, `us`, `ns`, `100ns`. |
| utc_offset | `str \| None` | `None` | Zone of timestamps without one (`+02:00`); default UTC. |

**Outcomes:**
- PASSED: the cell at (`row`, `column`) matches `expected_value` (exactly, by regex, or by the ordered comparison)
- FAILED: the workbook was read and the cell value does not match
- FAILED: `row` or `column` is outside the sheet's used range; the sheet does not exist
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the file cannot be read or is no valid .xlsx workbook
- ERROR: an invalid regex or unknown placeholder; more than one placeholder in `expected_value`
- ERROR: a cell or `expected_value` that is no number or timestamp for an ordered comparison
- ERROR: `!re`, `{{placeholder}}` or `regex_match` combined with an ordered comparison, or other bad comparison parameters

**Limits:**
- Cells compare as strings: numbers via `str()` (`5.0` when every cell of the row is a number), dates as `2024-01-31 00:00:00` (or `2024-01-31T00:00:00` when every cell of the row is a date). Use `!re` or an ordered comparison when unsure.
- `expected_value` compares as `str(expected_value)`: `1500` matches the cell `1500`, `1500.0` does not.
- `regex_match` uses `re.search` (unanchored); a `!re` tag uses `re.match` (anchored at the start).
- A formula reads as the result the spreadsheet application saved with it; a workbook written without calculated results reads `''`.

**Use cases:**
- A value the user typed: The cell the playbook filled holds the text or number after saving.
- A saved formula result: The computed value stored in the workbook (not the formula) is the expected one.
- A threshold or a date: `comparison_type: greater` for a total, or a date cell later than a point in time.

**Examples:**

*total typed into Q3* → PASSED. Row 1 is spreadsheet row 2, column 2 is column C.

```yaml
tests:
- name: total_typed_into_q3
  function: excel.cell_value_matches
  parameter:
    dst: /home/user/Documents/budget.xlsx
    sheet: Q3
    row: 1
    column: 2
    expected_value: '1500'
```

*an amount above a threshold* → PASSED

```yaml
tests:
- name: an_amount_above_a_threshold
  function: excel.cell_value_matches
  parameter:
    dst: /home/user/Documents/budget.xlsx
    sheet: Q2
    row: 1
    column: 2
    expected_value: 900
    comparison_type: greater
```

*a date cell after a point in time* → PASSED

```yaml
tests:
- name: a_date_cell_after_a_point_in_time
  function: excel.cell_value_matches
  parameter:
    dst: /home/user/Documents/budget.xlsx
    sheet: Report 2026
    row: 0
    column: 1
    expected_value: '2026-01-01T00:00:00'
    comparison_type: greater
```

*a number with or without decimals* → PASSED

```yaml
tests:
- name: a_number_with_or_without_decimals
  function: excel.cell_value_matches
  parameter:
    dst: /home/user/Documents/budget.xlsx
    sheet: Q3
    row: 1
    column: 2
    expected_value: !re '^1500(\.0)?$'
```

*a different value fails* → FAILED

```yaml
tests:
- name: a_different_value_fails
  function: excel.cell_value_matches
  parameter:
    dst: /home/user/Documents/budget.xlsx
    sheet: Q2
    row: 1
    column: 2
    expected_value: '950'
```

*a formula without a saved result reads empty* → PASSED. The formula was written without being calculated, so the cell has no stored value.

```yaml
tests:
- name: a_formula_without_a_saved_result_reads_empty
  function: excel.cell_value_matches
  parameter:
    dst: /home/user/Documents/budget.xlsx
    sheet: Report 2026
    row: 1
    column: 1
    expected_value: ''
```

*a row outside the sheet fails* → FAILED

```yaml
tests:
- name: a_row_outside_the_sheet_fails
  function: excel.cell_value_matches
  parameter:
    dst: /home/user/Documents/budget.xlsx
    sheet: Q3
    row: 10
    column: 0
    expected_value: Travel
```

*an ordered comparison on text is an error* → ERROR. The cell holds no number or timestamp, so the test looked at the wrong cell.

```yaml
tests:
- name: an_ordered_comparison_on_text_is_an_error
  function: excel.cell_value_matches
  parameter:
    dst: /home/user/Documents/budget.xlsx
    sheet: Q3
    row: 1
    column: 0
    expected_value: 1000
    comparison_type: greater
```

## `excel.compare_files`

compares entire Excel files with multi-sheet awareness

Pass when all paired sheets of `actual` and `reference` match and no sheet is missing/extra.

**Use for:** whole-workbook comparison. Needs the in-guest agent (agentless host mode only pulls a `dst` parameter).

asserts: compare · formats: excel · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Placeholders ({{ variable }}) (`placeholder`)

**Not for:**
- one pair of sheets → `excel.compare_sheets`
- two CSV files → `csv.compare_files`
- byte-identical files → `standard.file_hash_matches`

| parameter | type | default | description |
|---|---|---|---|
| **actual** | `str` | `''` | Guest path to the workbook under test; glob must match exactly one path. |
| **reference** | `str` | `''` | Guest path to the reference workbook. |
| sheet_mode | `str` | `'by_name'` | `by_name` (default; pair equal names), `by_index` (pair by position) or `specific` (only `specific_sheets` present in both; extra sheets ignored). Other values are an error. Allowed: `by_name`, `by_index`, `specific`. |
| specific_sheets | `list[str] \| None` | `None` | Sheet names for `specific` mode; names absent from `actual` count as missing, names absent only from `reference` are skipped. Empty passes vacuously. |
| columns | `list[int] \| None` | `None` | 0-based column indices to compare; `None` compares all. |
| ignore_order | `bool` | `False` | `True` matches rows as a multiset instead of position by position. |
| allow_extra_rows | `bool` | `False` | Do not fail on extra actual rows (ordered mode: trailing rows only). |
| allow_missing_rows | `bool` | `False` | Do not fail on missing reference rows (ordered mode: trailing only). |
| allow_extra_sheets | `bool` | `False` | Do not fail on sheets only in `actual`. |
| allow_missing_sheets | `bool` | `False` | Do not fail on sheets only in `reference`. |
| header_row | `int \| None` | `None` | Number of top rows to skip in every sheet. |

**Outcomes:**
- PASSED: all paired sheets match and no sheet is missing or extra, within the allowed differences
- FAILED: the workbooks were read and a sheet is missing or extra, or the rows of a paired sheet differ; the report lists the differences per sheet
- ERROR: `actual` or `reference` does not exist; a glob matches no file or more than one
- ERROR: a file or one of its sheets cannot be read, or is no valid .xlsx workbook
- ERROR: an unknown `sheet_mode`
- ERROR: an invalid regex or unknown placeholder in a cell of a reference sheet

**Limits:**
- Needs the in-guest agent; agentless host mode only pulls a `dst` parameter, and this function has none.
- `by_index` pairs sheets by position whatever their names; `specific` compares only `specific_sheets` present in both files, ignores all other sheets, and passes on an empty list.
- In `specific` mode a listed name absent from `actual` counts as missing; one absent only from `reference` is skipped.
- `header_row`, `columns` and the row options apply to every sheet pair.
- Compares cell values only, not formatting, formulas or workbook properties.

**Use cases:**
- Save round trip: A workbook opened and saved again keeps all sheets and rows.
- Version comparison: The export of one application version against the export of another, placed in the guest as a reference.

**Examples:**

*workbook like the reference* → PASSED

```yaml
tests:
- name: workbook_like_the_reference
  function: excel.compare_files
  parameter:
    actual: /home/user/Documents/budget.xlsx
    reference: /home/user/reference/budget.xlsx
```

*an extra sheet fails* → FAILED

```yaml
tests:
- name: an_extra_sheet_fails
  function: excel.compare_files
  parameter:
    actual: /home/user/Documents/budget.xlsx
    reference: /home/user/reference/budget.xlsx
```

*extra sheets allowed* → PASSED

```yaml
tests:
- name: extra_sheets_allowed
  function: excel.compare_files
  parameter:
    actual: /home/user/Documents/budget.xlsx
    reference: /home/user/reference/budget.xlsx
    allow_extra_sheets: true
```

*listed sheets only* → PASSED

```yaml
tests:
- name: listed_sheets_only
  function: excel.compare_files
  parameter:
    actual: /home/user/Documents/budget.xlsx
    reference: /home/user/reference/budget.xlsx
    sheet_mode: specific
    specific_sheets: [Q2, Q3]
```

*a listed sheet missing from actual fails* → FAILED

```yaml
tests:
- name: a_listed_sheet_missing_from_actual_fails
  function: excel.compare_files
  parameter:
    actual: /home/user/Documents/budget.xlsx
    reference: /home/user/reference/budget.xlsx
    sheet_mode: specific
    specific_sheets: [Q3, Q3 (copy)]
```

*a missing reference workbook is an error* → ERROR

```yaml
tests:
- name: a_missing_reference_workbook_is_an_error
  function: excel.compare_files
  parameter:
    actual: /home/user/Documents/budget.xlsx
    reference: /home/user/Documents/budget-reference.xlsx
```

## `excel.compare_rows`

compares sheet rows against reference data (embedded or external file)

Pass when the rows of a sheet match inline `reference_rows` or a sheet of `reference_file`.

**Use for:** asserting sheet contents. Give exactly one of `reference_rows`/`reference_file` (both or neither fails). Cells are stringified as in excel.cell_value_matches.

asserts: compare, value · formats: excel · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Regex values (!re) (`regex_tag`), Times as expected values (!timestamp) (`timestamp_tag`), Placeholders ({{ variable }}) (`placeholder`)

**Not for:**
- all sheets of two workbooks → `excel.compare_files`
- one row anywhere in the sheet → `excel.contains_row`
- the header layout only → `excel.validate_columns`
- the rows of a CSV file → `csv.compare_rows`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` | `''` | Guest path to the .xlsx under test; a glob must match exactly one path. |
| reference_rows | `list[list[str]] \| None` | `None` | Expected rows as a list of lists of strings; `!re`/`!timestamp` tags allowed. |
| reference_file | `str \| None` | `None` | Guest path to a reference .xlsx (not pulled in agentless host mode). |
| reference_sheet | `str \| int` | `0` | Sheet name or 0-based index in `reference_file`. |
| reference_header_row | `int \| None` | `None` | Number of top rows to skip in `reference_file`. |
| sheet | `str \| int` | `0` | Sheet name or 0-based index in `dst`. |
| columns | `list[int] \| None` | `None` | 0-based column indices to compare; `None` compares all. |
| ignore_order | `bool` | `False` | `True` matches rows as a multiset instead of position by position. |
| allow_extra_rows | `bool` | `False` | Do not fail on extra actual rows (ordered mode: trailing rows only). |
| allow_missing_rows | `bool` | `False` | Do not fail on missing reference rows (ordered mode: trailing only). |
| header_row | `int \| None` | `None` | Number of top rows of `dst` to skip (not a row index). |

**Outcomes:**
- PASSED: the rows of `sheet` (or the selected `columns`) match the reference rows within the allowed differences
- FAILED: the workbooks were read and rows differ, are missing or extra; the report lists them by index
- FAILED: the sheet of `dst` does not exist
- ERROR: `dst` or `reference_file` does not exist; a glob matches no file or more than one
- ERROR: a file cannot be read or is no valid .xlsx workbook; `reference_sheet` does not exist
- ERROR: both or neither of `reference_rows` and `reference_file`
- ERROR: `reference_rows` is not a list, is empty, or holds an item that is not a list
- ERROR: an invalid regex, an unknown placeholder, more than one placeholder in one cell

**Limits:**
- Cells compare as strings (see excel.cell_value_matches); a number in `reference_rows` must be quoted (`'3'`), or the row never matches (except in a row that also holds a `!re` / `!timestamp` cell).
- Ordered mode (default) compares row N with reference row N; `allow_extra_rows` / `allow_missing_rows` only excuse trailing rows there.
- `header_row` skips rows of `dst` only; `reference_header_row` skips rows of `reference_file`.
- `reference_file` is not pulled in agentless host mode; it needs the in-guest agent.
- Out-of-range indices in `columns` are dropped silently.

**Use cases:**
- A small sheet's full contents: Every row the playbook entered, and nothing else.
- Selected columns: `columns` ignores volatile columns such as IDs or times.

**Examples:**

*inventory rows below the header* → PASSED

```yaml
tests:
- name: inventory_rows_below_the_header
  function: excel.compare_rows
  parameter:
    dst: /home/user/Documents/inventory.xlsx
    header_row: 1
    reference_rows:
    - [Laptop, '3', Office]
    - [Monitor, '5', Storage]
    - [Laptop, '1', Home]
```

*names and counts in any order* → PASSED

```yaml
tests:
- name: names_and_counts_in_any_order
  function: excel.compare_rows
  parameter:
    dst: /home/user/Documents/inventory.xlsx
    header_row: 1
    columns: [0, 1]
    ignore_order: true
    reference_rows: [[Monitor, '5'], [Laptop, '1'], [Laptop, '3']]
```

*against a sheet of a reference workbook* → PASSED

```yaml
tests:
- name: against_a_sheet_of_a_reference_workbook
  function: excel.compare_rows
  parameter:
    dst: /home/user/Documents/budget.xlsx
    sheet: Q3 (copy)
    reference_file: /home/user/reference/budget.xlsx
    reference_sheet: Q3
```

*a regex for a volatile location* → PASSED

```yaml
tests:
- name: a_regex_for_a_volatile_location
  function: excel.compare_rows
  parameter:
    dst: /home/user/Documents/inventory.xlsx
    header_row: 1
    reference_rows:
    - [Laptop, '3', Office]
    - [Monitor, '5', !re '.*']
    - [Laptop, '1', !re '.*']
```

*an unquoted number never matches* → FAILED. YAML reads `3` as a number and the cell is the string `'3'`; quote numbers.

```yaml
tests:
- name: an_unquoted_number_never_matches
  function: excel.compare_rows
  parameter:
    dst: /home/user/Documents/inventory.xlsx
    sheet: Archive
    header_row: 1
    reference_rows: [[Printer, 1, Office]]
```

*a missing reference sheet is an error* → ERROR. The expectation cannot be built, so this is no finding about `dst`.

```yaml
tests:
- name: a_missing_reference_sheet_is_an_error
  function: excel.compare_rows
  parameter:
    dst: /home/user/Documents/budget.xlsx
    reference_file: /home/user/reference/budget.xlsx
    reference_sheet: Q4
```

*both reference sources are an error* → ERROR

```yaml
tests:
- name: both_reference_sources_are_an_error
  function: excel.compare_rows
  parameter:
    dst: /home/user/Documents/budget.xlsx
    reference_file: /home/user/reference/budget.xlsx
    reference_rows: [[Account, Planned, Spent]]
```

**Related:**
- `excel.compare_sheets`: two sheets given by path, also of the same workbook

## `excel.compare_sheets`

compares two sheets from same or different files

Pass when sheet `actual_sheet` of `actual` matches `reference_sheet` of `reference`.

**Use for:** comparing two sheets of the same or different workbooks. Needs the in-guest agent (agentless host mode only pulls a `dst` parameter).

asserts: compare · formats: excel · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Placeholders ({{ variable }}) (`placeholder`)

**Not for:**
- rows written in the playbook → `excel.compare_rows`
- all sheets of two workbooks → `excel.compare_files`

| parameter | type | default | description |
|---|---|---|---|
| **actual** | `str` | `''` | Guest path to the workbook under test; glob must match exactly one path. |
| **reference** | `str` | `''` | Guest path to the reference workbook (may equal `actual`). |
| actual_sheet | `str \| int` | `0` | Sheet name or 0-based index in `actual`. |
| reference_sheet | `str \| int` | `0` | Sheet name or 0-based index in `reference`. |
| columns | `list[int] \| None` | `None` | 0-based column indices to compare; `None` compares all. |
| ignore_order | `bool` | `False` | `True` matches rows as a multiset instead of position by position. |
| allow_extra_rows | `bool` | `False` | Do not fail on extra actual rows (ordered mode: trailing rows only). |
| allow_missing_rows | `bool` | `False` | Do not fail on missing reference rows (ordered mode: trailing only). |
| header_row | `int \| None` | `None` | Number of top rows to skip in BOTH sheets. |

**Outcomes:**
- PASSED: the rows of `actual_sheet` (or the selected `columns`) match those of `reference_sheet` within the allowed differences
- FAILED: the workbooks were read and rows differ, are missing or extra; the report lists them by index
- FAILED: `actual_sheet` does not exist in `actual`
- ERROR: `actual` or `reference` does not exist; a glob matches no file or more than one
- ERROR: a file cannot be read or is no valid .xlsx workbook
- ERROR: `reference_sheet` does not exist in `reference`
- ERROR: an invalid regex or unknown placeholder in a cell of the reference sheet

**Limits:**
- Needs the in-guest agent; agentless host mode only pulls a `dst` parameter, and this function has none.
- `reference` may be the same file as `actual`; `header_row` skips rows in both sheets.
- Globs and archive members work in `actual` and `reference`.
- A cell of the reference sheet holding `{{ name }}` is compared with that playbook variable; an unknown name is an error. Other cells compare as exact strings.
- Ordered mode (default) compares row N with row N; `allow_extra_rows` / `allow_missing_rows` only excuse trailing rows there.

**Use cases:**
- Copy or move of a sheet: The copied sheet has the same rows as the original.
- Export against a known-good workbook: A reference workbook placed in the guest before the run.

**Examples:**

*copied sheet identical* → PASSED

```yaml
tests:
- name: copied_sheet_identical
  function: excel.compare_sheets
  parameter:
    actual: /home/user/Documents/budget.xlsx
    reference: /home/user/Documents/budget.xlsx
    actual_sheet: Q3 (copy)
    reference_sheet: Q3
```

*same accounts in both quarters* → PASSED. `columns: [0]` compares the account names only; the amounts differ.

```yaml
tests:
- name: same_accounts_in_both_quarters
  function: excel.compare_sheets
  parameter:
    actual: /home/user/Documents/budget.xlsx
    reference: /home/user/Documents/budget.xlsx
    actual_sheet: Q3
    reference_sheet: Q2
    columns: [0]
```

*two quarters differ* → FAILED

```yaml
tests:
- name: two_quarters_differ
  function: excel.compare_sheets
  parameter:
    actual: /home/user/Documents/budget.xlsx
    reference: /home/user/Documents/budget.xlsx
    actual_sheet: Q3
    reference_sheet: Q2
```

*a missing sheet in actual fails* → FAILED

```yaml
tests:
- name: a_missing_sheet_in_actual_fails
  function: excel.compare_sheets
  parameter:
    actual: /home/user/Documents/budget.xlsx
    reference: /home/user/Documents/budget.xlsx
    actual_sheet: Q4
    reference_sheet: Q3
```

*a missing reference sheet is an error* → ERROR

```yaml
tests:
- name: a_missing_reference_sheet_is_an_error
  function: excel.compare_sheets
  parameter:
    actual: /home/user/Documents/budget.xlsx
    reference: /home/user/Documents/budget.xlsx
    actual_sheet: Q3
    reference_sheet: Q4
```

## `excel.contains_row`

finds row matching pattern in Excel sheet

Pass when at least one row of a sheet matches `entry` column by column.

**Use for:** checking a record exists anywhere in a sheet. Cells are stringified as in excel.cell_value_matches (beware float/date formatting).

asserts: exists · formats: excel · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Regex values (!re) (`regex_tag`), Times as expected values (!timestamp) (`timestamp_tag`), Placeholders ({{ variable }}) (`placeholder`)

**Not for:**
- a row is absent, or how often it occurs → `excel.row_count`
- one cell at a fixed position → `excel.cell_value_matches`
- every row of the sheet → `excel.compare_rows`
- a record in a CSV file → `csv.contains_line`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` | `''` | Guest path to the .xlsx; a glob must match exactly one path. A missing or unreadable file is an error. |
| entry | `list[str]` | `None` | Expected row; a row must have exactly as many columns as the sheet's used width. Items compared as exact strings, or by type for `!re`/`!timestamp` tags. |
| sheet | `str \| int` | `0` | Sheet name (str) or 0-based index (int); unknown sheets fail. |
| header_row | `int \| None` | `None` | Number of top rows to skip before searching (not a row index); `None` skips none. |

**Outcomes:**
- PASSED: at least one row has the sheet's used width and every item of `entry` matches its column
- FAILED: the workbook was read and no row matches (also an empty sheet); the closest rows are reported
- FAILED: the sheet does not exist
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the file cannot be read or is no valid .xlsx workbook
- ERROR: `entry` is missing and the sheet has rows
- ERROR: an invalid regex, an unknown placeholder, more than one placeholder in one item

**Limits:**
- `entry` needs one item per column of the sheet's used width; empty trailing cells read as `''`.
- Items compare as `str(item)` with the cell string (`3` and `'3'` both match the cell `3`); see the cell formatting in excel.cell_value_matches.
- `header_row` skips that many top rows; without it the header row can match too.

**Use cases:**
- A record was added: A new line item exists anywhere in the sheet, whatever its position.
- A record was removed: `excel.row_count` with `expected_count: 0`.

**Examples:**

*a laptop in the office* → PASSED

```yaml
tests:
- name: a_laptop_in_the_office
  function: excel.contains_row
  parameter:
    dst: /home/user/Documents/inventory.xlsx
    header_row: 1
    entry: [Laptop, '3', Office]
```

*any count, with a regex item* → PASSED

```yaml
tests:
- name: any_count_with_a_regex_item
  function: excel.contains_row
  parameter:
    dst: /home/user/Documents/inventory.xlsx
    entry: [Laptop, !re '[0-9]+', Home]
```

*a row of another sheet* → PASSED

```yaml
tests:
- name: a_row_of_another_sheet
  function: excel.contains_row
  parameter:
    dst: /home/user/Documents/inventory.xlsx
    sheet: Archive
    entry: [Printer, 1, Office]
```

*a shorter entry fails* → FAILED. The sheet is three columns wide; an entry with two items matches no row.

```yaml
tests:
- name: a_shorter_entry_fails
  function: excel.contains_row
  parameter:
    dst: /home/user/Documents/inventory.xlsx
    entry: [Laptop, '3']
```

*an absent row fails* → FAILED. To assert absence use excel.row_count with `expected_count` 0, which passes.

```yaml
tests:
- name: an_absent_row_fails
  function: excel.contains_row
  parameter:
    dst: /home/user/Documents/inventory.xlsx
    entry: [Printer, '1', Office]
```

*an unknown sheet fails* → FAILED

```yaml
tests:
- name: an_unknown_sheet_fails
  function: excel.contains_row
  parameter:
    dst: /home/user/Documents/inventory.xlsx
    sheet: Stock
    entry: [Laptop, '3', Office]
```

*a missing file is an error* → ERROR

```yaml
tests:
- name: a_missing_file_is_an_error
  function: excel.contains_row
  parameter:
    dst: /home/user/Documents/stock.xlsx
    entry: [Laptop, '3', Office]
```

## `excel.row_count`

tests the number of rows in an Excel sheet that match the given entry layout

Pass when the number of rows of a sheet matching `entry` satisfies `comparison_type`.

**Use for:** asserting how often a record occurs (exactly one row for an item); absence of a row: `expected_count: 0` (or `expect_to_fail: true` on excel.contains_row).

asserts: count, absent · formats: excel · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Counts with a comparison (`count_comparison`), Regex values (!re) (`regex_tag`), Times as expected values (!timestamp) (`timestamp_tag`), Placeholders ({{ variable }}) (`placeholder`), Negative tests (absence) (`negative`)

**Not for:**
- rows of a CSV file → `csv.row_count`
- every row of the sheet → `excel.compare_rows`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the .xlsx; a glob must match exactly one path. A missing or unreadable file is an error. |
| **entry** | `list` |  | Expected row as a list, matched exactly like excel.contains_row: one item per column of the sheet's used width (a row with another width never matches), exact strings or `!re`/`!timestamp` tags. A non-list is an error. |
| **expected_count** | `int` |  | Non-negative integer to compare against; anything else is an error. |
| comparison_type | `str` | `'equals'` | `equals` (default), `greater`, `less`, `greater_equal` or `less_equal`; other values are an error. Allowed: `equals`, `greater`, `less`, `greater_equal`, `less_equal`. |
| sheet | `str \| int` | `0` | Sheet name (str) or 0-based index (int); an unknown sheet fails, like excel.contains_row. |
| header_row | `int \| None` | `None` | Number of top rows to skip before counting; `None` skips none. A negative number or a non-integer is an error. |

**Outcomes:**
- PASSED: the number of rows matching `entry` satisfies `comparison_type` against `expected_count`
- FAILED: the workbook was read and the count comparison does not hold
- FAILED: the sheet does not exist (as in excel.contains_row)
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the file cannot be read or is no valid .xlsx workbook
- ERROR: `entry` is not a list; a negative or non-integer `expected_count` or `header_row`; an unknown `comparison_type`
- ERROR: an invalid regex, an unknown placeholder, more than one placeholder in one item

**Limits:**
- Rows match exactly as in excel.contains_row (used width, `str(item)`, `!re` / `!timestamp` items).
- Without `header_row` the header row is counted like any other row.

**Use cases:**
- Record added exactly once: An edit or import must add one row, not zero and not a duplicate.
- Row removed: `expected_count: 0` after deleting a row in the spreadsheet application; pair it with a control test.
- Several rows of one kind: `comparison_type: greater_equal` with `!re` items.

**Examples:**

*two laptop rows* → PASSED

```yaml
tests:
- name: two_laptop_rows
  function: excel.row_count
  parameter:
    dst: /home/user/Documents/inventory.xlsx
    entry: [Laptop, !re '[0-9]+', !re '.*']
    expected_count: 2
```

*one laptop in the office* → PASSED

```yaml
tests:
- name: one_laptop_in_the_office
  function: excel.row_count
  parameter:
    dst: /home/user/Documents/inventory.xlsx
    header_row: 1
    entry: [Laptop, '3', Office]
    expected_count: 1
```

*the printer is gone from the items sheet* → PASSED

```yaml
tests:
- name: the_printer_is_gone_from_the_items_sheet
  function: excel.row_count
  parameter:
    dst: /home/user/Documents/inventory.xlsx
    sheet: Items
    entry: [Printer, '1', Office]
    expected_count: 0
```

*an unknown sheet fails, it does not count zero* → FAILED

```yaml
tests:
- name: an_unknown_sheet_fails_it_does_not_count_zero
  function: excel.row_count
  parameter:
    dst: /home/user/Documents/inventory.xlsx
    sheet: Stock
    entry: [Printer, '1', Office]
    expected_count: 0
```

*absence in a missing file is an error, not a pass* → ERROR

```yaml
tests:
- name: absence_in_a_missing_file_is_an_error_not_a_pass
  function: excel.row_count
  parameter:
    dst: /home/user/Documents/stock.xlsx
    entry: [Printer, '1', Office]
    expected_count: 0
```

*a negative header_row is an error* → ERROR

```yaml
tests:
- name: a_negative_header_row_is_an_error
  function: excel.row_count
  parameter:
    dst: /home/user/Documents/inventory.xlsx
    header_row: -1
    entry: [Laptop, '3', Office]
    expected_count: 1
```

**Related:**
- `excel.contains_row`: one matching row, with the closest rows reported on failure

## `excel.sheet_exists`

tests if a sheet exists in an Excel file

Pass when workbook `dst` (.xlsx, read with openpyxl) has a sheet named `sheet`.

**Use for:** checking a GUI action added/renamed a worksheet.

asserts: exists · formats: excel · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`)

**Does not support:**
- Regex values (!re) (`regex_tag`): A `!re` tag as `sheet` is compared as plain text and never matches; use `regex_match: true` with a plain pattern.

**Not for:**
- a value in a cell of the sheet → `excel.cell_value_matches`
- workbook properties (author, last modified by) → `xml.element_text_matches`
- all sheet names and contents of two workbooks → `excel.compare_files`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the .xlsx; a glob must match exactly one path. A missing or unreadable file is an error. |
| **sheet** | `str` |  | Exact, case-sensitive sheet name, or a regex if `regex_match`. |
| regex_match | `bool` | `False` | Treat `sheet` as a Python regex searched in each sheet name (`re.search`, unanchored; `^...$` for the whole name); an invalid regex is an error. |

**Outcomes:**
- PASSED: a sheet is named `sheet` (exact, case-sensitive) or, with `regex_match`, a sheet name matches the regex
- FAILED: the workbook was read and no sheet has the name, or the workbook has no sheets
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the file cannot be read or is no valid .xlsx workbook
- ERROR: an invalid regex with `regex_match`

**Limits:**
- `regex_match` uses `re.search` (unanchored); write `^...$` for the whole name.
- A deleted or renamed sheet is asserted with `expect_to_fail: true` on the old name; there is no sheet count.

**Use cases:**
- A GUI action added or renamed a sheet: The new name exists after the action; the old one fails with `expect_to_fail: true`.

**Examples:**

*quarter sheet added* → PASSED

```yaml
tests:
- name: quarter_sheet_added
  function: excel.sheet_exists
  parameter:
    dst: /home/user/Documents/budget.xlsx
    sheet: Q3
```

*some report sheet, by regex* → PASSED

```yaml
tests:
- name: some_report_sheet_by_regex
  function: excel.sheet_exists
  parameter:
    dst: /home/user/Documents/budget.xlsx
    sheet: '^Report \d{4}$'
    regex_match: true
```

*a sheet inside a backup archive* → PASSED

```yaml
tests:
- name: a_sheet_inside_a_backup_archive
  function: excel.sheet_exists
  parameter:
    dst: C:\Users\user\backup.zip!/Documents/budget.xlsx
    sheet: Q2
```

*names are case-sensitive* → FAILED

```yaml
tests:
- name: names_are_case_sensitive
  function: excel.sheet_exists
  parameter:
    dst: /home/user/Documents/budget.xlsx
    sheet: q3
```

*a file that is no workbook is an error* → ERROR

```yaml
tests:
- name: a_file_that_is_no_workbook_is_an_error
  function: excel.sheet_exists
  parameter:
    dst: /home/user/Documents/budget.xlsx
    sheet: Q3
```

*an invalid regex is an error* → ERROR

```yaml
tests:
- name: an_invalid_regex_is_an_error
  function: excel.sheet_exists
  parameter:
    dst: /home/user/Documents/budget.xlsx
    sheet: 'Report ['
    regex_match: true
```

## `excel.validate_columns`

validates column headers in Excel sheet

Pass when the header names in row `column_row` match `expected_columns`.

**Use for:** verifying a sheet's column layout/schema.

asserts: value · formats: excel · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`)

**Does not support:**
- Regex values (!re) (`regex_tag`): Header names compare as exact text (whitespace-stripped, case-sensitive); a `!re` tag never matches.

**Not for:**
- the data rows too → `excel.compare_rows`
- a sheet exists → `excel.sheet_exists`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` | `''` | Guest path to the .xlsx; a glob must match exactly one path. A missing or unreadable file is an error. |
| expected_columns | `list[str]` | `None` | Non-empty list of header names; whitespace-stripped, case-sensitive. Empty header cells read as `''` and count as extra columns. |
| sheet | `str \| int` | `0` | Sheet name (str) or 0-based index (int). |
| column_row | `int` | `0` | 0-based row holding the headers; out of range or empty row fails. |
| allow_extra_columns | `bool` | `False` | Do not fail on headers not in `expected_columns`. |
| allow_missing_columns | `bool` | `False` | Do not fail on expected headers absent from the sheet. |
| ignore_order | `bool` | `False` | Skip the order check (order is only checked when the names match exactly). |

**Outcomes:**
- PASSED: the header names in row `column_row` match `expected_columns` within the allowed differences
- FAILED: the workbook was read and headers are missing, extra or (when the names match exactly) in another order
- FAILED: `column_row` is outside the sheet or the row is empty; the sheet does not exist
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the file cannot be read or is no valid .xlsx workbook
- ERROR: `expected_columns` is not a list or is empty

**Limits:**
- Empty header cells inside the used width read as `''` and count as extra columns.
- The order is checked only when the sets of names are equal; `ignore_order` skips that check.

**Use cases:**
- Export layout: A version of the application writes the same column layout as the last one.
- Inserted or removed columns: A GUI action that adds or deletes a column changes the header row.

**Examples:**

*inventory layout* → PASSED

```yaml
tests:
- name: inventory_layout
  function: excel.validate_columns
  parameter:
    dst: /home/user/Documents/inventory.xlsx
    expected_columns: [Item, Count, Location]
```

*required columns present, others allowed* → PASSED

```yaml
tests:
- name: required_columns_present_others_allowed
  function: excel.validate_columns
  parameter:
    dst: /home/user/Documents/inventory.xlsx
    expected_columns: [Count, Item]
    allow_extra_columns: true
    ignore_order: true
```

*another order fails* → FAILED

```yaml
tests:
- name: another_order_fails
  function: excel.validate_columns
  parameter:
    dst: /home/user/Documents/inventory.xlsx
    expected_columns: [Item, Location, Count]
```

*an empty list is an error* → ERROR

```yaml
tests:
- name: an_empty_list_is_an_error
  function: excel.validate_columns
  parameter:
    dst: /home/user/Documents/inventory.xlsx
    expected_columns: []
```
