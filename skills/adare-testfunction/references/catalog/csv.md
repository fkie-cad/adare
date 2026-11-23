# CSV (`csv.*`)

<!-- Generated; do not edit by hand. -->

Comma-separated files an application or a tool exports: one record exists, how many records match a layout, and the whole file against rows written in the playbook or against a second CSV file. Files are parsed with Python's default `csv` dialect (comma, double quotes); the header row is a normal row, and a quoted field with a line break is one record. Every function takes `encoding`: a BOM (UTF-8/16/32) or BOM-less UTF-16 is detected, otherwise UTF-8 is read unless a codec is named.

## `csv.compare_files`

compares two CSV files with full diff reporting

Pass when CSV file `actual` matches CSV file `reference` row by row.

**Use for:** diffing a produced CSV against a reference CSV available on the same machine. For inline expectations use csv.compare_rows. Needs the in-guest agent: agentless host mode only pulls a `dst` parameter, and this function has none.

asserts: compare · formats: csv · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Placeholders ({{ variable }}) (`placeholder`), Text encodings (`encoding`)

**Not for:**
- compare with rows written in the playbook → `csv.compare_rows`
- two Excel workbooks → `excel.compare_files`
- byte-identical files → `standard.file_hash_matches`

| parameter | type | default | description |
|---|---|---|---|
| **actual** | `str` | `''` | Guest path to the CSV under test; a glob must match exactly one path, a missing or ambiguous file (or a CSV parse error) is an error. |
| **reference** | `str` | `''` | Guest path to the reference CSV, resolved like `actual`. |
| columns | `list[int]` | `None` | 0-based column indices to compare; `None` compares all columns. |
| ignore_order | `bool` | `False` | `False` (default) compares row N with row N; `True` matches rows as a multiset. |
| allow_extra_rows | `bool` | `False` | Do not fail on rows only in `actual` (ordered mode: trailing rows only). |
| allow_missing_rows | `bool` | `False` | Do not fail on rows only in `reference` (ordered mode: trailing rows only). |
| encoding | `str \| None` | `None` | `None` (default) detects a BOM (UTF-8/16/32) and BOM-less UTF-16, else reads UTF-8; a name (`cp1252`) reads BOM-less files (both) with it. A BOM always wins. Unknown names or undecodable content are an error. |

**Outcomes:**
- PASSED: the rows of `actual` (or the selected `columns`) match those of `reference` within the allowed differences
- FAILED: both files were read and rows differ, are missing or extra; the report lists them by index
- ERROR: `actual` or `reference` does not exist; a glob matches no file or more than one
- ERROR: a file cannot be read or decoded; an unknown encoding; a CSV parse error
- ERROR: an invalid regex or unknown placeholder in a cell of `reference`

**Limits:**
- Needs the in-guest agent; agentless host mode only pulls a `dst` parameter, and this function has none.
- Globs and archive members (`a.zip!/x.csv`) work in `actual` and `reference`; both are read with the same `encoding`.
- Ordered mode (default) compares row N with row N; `allow_extra_rows` / `allow_missing_rows` only excuse trailing rows there.
- A cell of `reference` holding `{{ name }}` is compared with that playbook variable (a regex or timestamp variable matches by type); an unknown name is an error. Other cells compare as exact strings.

**Use cases:**
- Export against a known-good file: A reference CSV placed in the guest before the run.
- Two exports of one run: Two files the application wrote should hold the same rows.

**Examples:**

*export like the reference, any order* → PASSED

```yaml
tests:
- name: export_like_the_reference_any_order
  function: csv.compare_files
  parameter:
    actual: /home/user/out/export.csv
    reference: /home/user/reference/export.csv
    ignore_order: true
```

*the reference inside an archive* → PASSED

```yaml
tests:
- name: the_reference_inside_an_archive
  function: csv.compare_files
  parameter:
    actual: /home/user/out/export.csv
    reference: /home/user/reference/refs.zip!/export.csv
```

*another row order fails in ordered mode* → FAILED

```yaml
tests:
- name: another_row_order_fails_in_ordered_mode
  function: csv.compare_files
  parameter:
    actual: /home/user/out/export.csv
    reference: /home/user/reference/export.csv
```

*a missing reference is an error* → ERROR

```yaml
tests:
- name: a_missing_reference_is_an_error
  function: csv.compare_files
  parameter:
    actual: /home/user/out/export.csv
    reference: /home/user/reference/export.csv
```

## `csv.compare_rows`

compares all rows in CSV against embedded reference data

Pass when the rows of CSV file `dst` match the embedded `reference_rows`.

**Use for:** asserting a whole (small) CSV export. To compare against a second CSV file use csv.compare_files.

asserts: compare, value · formats: csv · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Regex values (!re) (`regex_tag`), Times as expected values (!timestamp) (`timestamp_tag`), Placeholders ({{ variable }}) (`placeholder`), Text encodings (`encoding`)

**Not for:**
- compare with a second CSV file → `csv.compare_files`
- one record anywhere in the file → `csv.contains_line`
- how many rows match a layout, or a row is absent → `csv.row_count`
- the rows of a spreadsheet sheet → `excel.compare_rows`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the CSV file. A glob must match exactly one path; no/ambiguous match, a missing file or a CSV parse error is an error. Default `csv` dialect; header row included. |
| reference_rows | `list[list[str]]` | `None` | Expected rows, a non-empty list of lists of strings (quote numbers in YAML). `!re`/`!timestamp` tags are matched by type; other cells exactly. |
| columns | `list[int]` | `None` | 0-based column indices to compare (others ignored; out-of-range indices are silently dropped). `None` compares all columns. |
| ignore_order | `bool` | `False` | `False` (default) compares row N with row N; `True` matches rows as a multiset regardless of position. |
| allow_extra_rows | `bool` | `False` | Do not fail on actual rows without a reference counterpart (in ordered mode only trailing rows count as extra). |
| allow_missing_rows | `bool` | `False` | Do not fail on reference rows missing from the file (in ordered mode only trailing rows count as missing). |
| encoding | `str \| None` | `None` | `None` (default) detects a BOM (UTF-8/16/32) and BOM-less UTF-16, else reads UTF-8; a name (`cp1252`) reads BOM-less files with it. A BOM always wins. Unknown names or undecodable content are an error. |

**Outcomes:**
- PASSED: the rows (or the selected `columns`) match `reference_rows` within the allowed differences
- FAILED: the file was read and rows differ, are missing or extra; the report lists them by index
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the file cannot be read or decoded; an unknown encoding; a CSV parse error
- ERROR: `reference_rows` is not a list, is empty, or holds an item that is not a list
- ERROR: an invalid regex, an unknown placeholder, more than one placeholder in one cell

**Limits:**
- Cells compare as strings; a number in `reference_rows` must be quoted (`'1024'`), or the row never matches (except in a row that also holds a `!re` / `!timestamp` cell).
- Ordered mode (default) compares row N with reference row N; `allow_extra_rows` / `allow_missing_rows` only excuse trailing rows there.
- `ignore_order: true` matches rows as a multiset: duplicates must occur as often in the file as in `reference_rows`.
- Out-of-range indices in `columns` are dropped silently.
- The header row is a normal row; include it in `reference_rows` or leave it out with `allow_extra_rows` / `columns` as needed.

**Use cases:**
- A small export's full contents: Every row the application wrote, in order, header included.
- Selected columns: `columns` ignores volatile columns such as IDs or times.

**Examples:**

*whole export, header included* → PASSED

```yaml
tests:
- name: whole_export_header_included
  function: csv.compare_rows
  parameter:
    dst: /home/user/out/export.csv
    reference_rows:
    - [name, size]
    - [report.docx, '1024']
    - [notes.txt, '512']
```

*names in any order, more rows allowed* → PASSED

```yaml
tests:
- name: names_in_any_order_more_rows_allowed
  function: csv.compare_rows
  parameter:
    dst: /home/user/out/export.csv
    columns: [0]
    ignore_order: true
    allow_extra_rows: true
    reference_rows: [[notes.txt], [report.docx]]
```

*a regex cell for a volatile size* → PASSED

```yaml
tests:
- name: a_regex_cell_for_a_volatile_size
  function: csv.compare_rows
  parameter:
    dst: /home/user/out/export.csv
    reference_rows:
    - [name, size]
    - [report.docx, !re '[0-9]+']
    - [notes.txt, !re '[0-9]+']
```

*an unquoted number never matches* → FAILED. YAML reads `1024` as a number and the cell is the string `'1024'`; quote numbers.

```yaml
tests:
- name: an_unquoted_number_never_matches
  function: csv.compare_rows
  parameter:
    dst: /home/user/out/export.csv
    reference_rows:
    - [name, size]
    - [report.docx, 1024]
    - [notes.txt, '512']
```

*rows in another order fail in ordered mode* → FAILED

```yaml
tests:
- name: rows_in_another_order_fail_in_ordered_mode
  function: csv.compare_rows
  parameter:
    dst: /home/user/out/export.csv
    reference_rows:
    - [name, size]
    - [report.docx, '1024']
    - [notes.txt, '512']
```

*empty reference rows are an error* → ERROR

```yaml
tests:
- name: empty_reference_rows_are_an_error
  function: csv.compare_rows
  parameter:
    dst: /home/user/out/export.csv
    reference_rows: []
```

## `csv.contains_line`

tests if row in a csv file exists that matches the given entry layout

Pass when at least one row of CSV file `dst` matches `entry` column by column.

**Use for:** checking a tool's CSV output (e.g. a timeline) contains a specific record.

asserts: exists · formats: csv · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Regex values (!re) (`regex_tag`), Times as expected values (!timestamp) (`timestamp_tag`), Placeholders ({{ variable }}) (`placeholder`), Text encodings (`encoding`)

**Not for:**
- a record is absent, or how often it occurs → `csv.row_count`
- the whole file, every row → `csv.compare_rows`
- physical lines of a text file containing a string → `text.line_count`
- a row of a spreadsheet workbook (.xlsx) → `excel.contains_row`
- a JSON Lines record with several fields → `jsonl.line_matches`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the CSV file. A glob must match exactly one path; no/ambiguous match, a missing file or a CSV parse error is an error. Parsed with the default `csv` dialect (comma, double quotes); the header row is a normal row. |
| entry | `list` | `None` | Expected row as a list, one item per column; a row must have exactly this many columns. Items are compared as exact, case-sensitive strings (`str(item)`), or by type for `!re`/`!timestamp` tags (`!re` uses `re.match`, anchored at the start). Required in practice: omitting it is an execution error unless the file is empty. |
| encoding | `str \| None` | `None` | `None` (default) detects a BOM (UTF-8/16/32) and BOM-less UTF-16, else reads UTF-8; a name (`cp1252`) reads BOM-less files with it. A BOM always wins. Unknown names or undecodable content are an error. |

**Outcomes:**
- PASSED: at least one row has as many columns as `entry` and every item matches its column
- FAILED: the file was read and no row matches; the closest rows and their mismatching columns are reported
- FAILED: the file is empty (no rows)
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the file cannot be read or decoded in the encoding; an unknown encoding; a CSV parse error
- ERROR: `entry` is missing (`None`) and the file has rows
- ERROR: an invalid regex, an unknown placeholder, more than one placeholder in one item

**Limits:**
- Only the default `csv` dialect (comma, double quotes); there is no delimiter parameter, so a semicolon- or tab-separated line is one column.
- Items compare as exact, case-sensitive strings (`str(item)`); a `!re` item uses `re.match` (anchored at the start, add `$` for the end).
- A row with another number of columns than `entry` never matches; there is no partial-row match.
- The whole file is parsed into memory.

**Use cases:**
- A record in a tool's export: A timeline, log or report export holds the row for the file or event the playbook created.
- Volatile columns: `!re '.*'` for times or IDs that change from run to run, `!timestamp` to bind a time column to the action.

**Examples:**

*a creation record in a timeline export* → PASSED

```yaml
tests:
- name: a_creation_record_in_a_timeline_export
  function: csv.contains_line
  parameter:
    dst: /home/user/out/timeline.csv
    entry: [report.docx, '2026-01-01T10:00:00', Created]
```

*any time with a regex item* → PASSED

```yaml
tests:
- name: any_time_with_a_regex_item
  function: csv.contains_line
  parameter:
    dst: /home/user/out/timeline.csv
    entry: [report.docx, !re '2026-01-01T', Modified]
```

*a quoted field with a line break is one column* → PASSED

```yaml
tests:
- name: a_quoted_field_with_a_line_break_is_one_column
  function: csv.contains_line
  parameter:
    dst: /home/user/out/timeline.csv
    entry: ["notes\nold.txt", '2026-01-01T10:06:00', Deleted]
```

*a UTF-16 export with BOM is detected* → PASSED

```yaml
tests:
- name: a_utf_16_export_with_bom_is_detected
  function: csv.contains_line
  parameter:
    dst: /home/user/out/export.csv
    entry: [report.docx, '1024']
```

*a legacy code page needs encoding* → PASSED

```yaml
tests:
- name: a_legacy_code_page_needs_encoding
  function: csv.contains_line
  parameter:
    dst: C:\Users\user\Documents\owners.csv
    entry: [report.docx, "M\xFCller"]
    encoding: cp1252
```

*the same file read as UTF-8 is an error* → ERROR. The file could not be decoded, so the test never saw the rows.

```yaml
tests:
- name: the_same_file_read_as_utf_8_is_an_error
  function: csv.contains_line
  parameter:
    dst: C:\Users\user\Documents\owners.csv
    entry: [report.docx, "M\xFCller"]
```

*a row inside an archive* → PASSED

```yaml
tests:
- name: a_row_inside_an_archive
  function: csv.contains_line
  parameter:
    dst: /home/user/backup.zip!/out/timeline.csv
    entry: [report.docx, '2026-01-01T10:05:00', Modified]
```

*too few items fail* → FAILED. The rows have three columns; an entry with two items matches none of them.

```yaml
tests:
- name: too_few_items_fail
  function: csv.contains_line
  parameter:
    dst: /home/user/out/timeline.csv
    entry: [report.docx, Created]
```

*a semicolon-separated file is one column per line* → FAILED. Without a delimiter parameter, `name;size` is one field, so a two-item entry fails.

```yaml
tests:
- name: a_semicolon_separated_file_is_one_column_per_lin
  function: csv.contains_line
  parameter:
    dst: /home/user/out/export.csv
    entry: [report.docx, '1024']
```

*an absent record fails* → FAILED. To assert absence use csv.row_count with `expected_count` 0, which passes.

```yaml
tests:
- name: an_absent_record_fails
  function: csv.contains_line
  parameter:
    dst: /home/user/out/timeline.csv
    entry: [report.docx, '2026-01-01T10:05:00', Deleted]
```

*a glob with several matches is an error* → ERROR

```yaml
tests:
- name: a_glob_with_several_matches_is_an_error
  function: csv.contains_line
  parameter:
    dst: /home/user/out/*.csv
    entry: [report.docx, '1024']
```

*a missing file is an error, not a failure* → ERROR

```yaml
tests:
- name: a_missing_file_is_an_error_not_a_failure
  function: csv.contains_line
  parameter:
    dst: /home/user/out/missing.csv
    entry: [report.docx, '1024']
```

**Related:**
- `csv.row_count`: counts the rows this function would accept (`0` for absence)
- `excel.contains_row`: the same check for a sheet of an Excel workbook

## `csv.row_count`

tests the number of rows (records) in a CSV file that match the given entry layout

Pass when the number of rows of CSV file `dst` matching `entry` satisfies `comparison_type`.

**Use for:** asserting how often a record occurs (exactly one row for a file); absence of a row: `expected_count: 0` (or `expect_to_fail: true` on csv.contains_line). Counts CSV records, so a quoted field with a line break is one row; for physical lines use text.line_count, for JSON Lines records jsonl.line_count.

asserts: count, absent · formats: csv · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Counts with a comparison (`count_comparison`), Regex values (!re) (`regex_tag`), Times as expected values (!timestamp) (`timestamp_tag`), Placeholders ({{ variable }}) (`placeholder`), Text encodings (`encoding`), Negative tests (absence) (`negative`)

**Not for:**
- physical lines of a text file (a quoted line break counts twice there) → `text.line_count`
- JSON Lines records → `jsonl.line_count`
- rows of a spreadsheet sheet → `excel.row_count`
- the whole file → `csv.compare_rows`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the CSV file. A glob must match exactly one path; no/ambiguous match, a missing file, undecodable content or a CSV parse error is an error. Parsed like csv.contains_line (default `csv` dialect; the header row is a normal row). |
| **entry** | `list` |  | Expected row as a list, matched exactly like csv.contains_line: one item per column (a row with another column count never matches), exact case-sensitive strings or `!re`/`!timestamp` tags. A non-list is an error. |
| **expected_count** | `int` |  | Non-negative integer to compare against; anything else is an error. |
| comparison_type | `str` | `'equals'` | `equals` (default), `greater`, `less`, `greater_equal` or `less_equal`; other values are an error. Allowed: `equals`, `greater`, `less`, `greater_equal`, `less_equal`. |
| encoding | `str \| None` | `None` | `None` (default) detects a BOM (UTF-8/16/32) and BOM-less UTF-16, else reads UTF-8; a name (`cp1252`) reads BOM-less files with it. A BOM always wins. Unknown names or undecodable content are an error. |

**Outcomes:**
- PASSED: the number of rows matching `entry` satisfies `comparison_type` against `expected_count`
- FAILED: the file was read and the count comparison does not hold
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the file cannot be read or decoded; an unknown encoding; a CSV parse error
- ERROR: `entry` is not a list; a negative or non-integer `expected_count`; an unknown `comparison_type`
- ERROR: an invalid regex, an unknown placeholder, more than one placeholder in one item

**Limits:**
- Rows match exactly as in csv.contains_line (column count, exact strings, `!re` / `!timestamp` items).
- Counts CSV records, not lines; the header row counts like any other row.
- Only the default `csv` dialect (comma, double quotes).

**Use cases:**
- A record occurs once: Exactly one row for a deleted file in a timeline export, not zero and not a duplicate.
- A record is gone: `expected_count: 0` after a clean-up action; pair it with a control test.

**Examples:**

*two records for one file* → PASSED

```yaml
tests:
- name: two_records_for_one_file
  function: csv.row_count
  parameter:
    dst: /home/user/out/timeline.csv
    entry: [report.docx, !re '.*', !re '.*']
    expected_count: 2
```

*one deletion recorded* → PASSED. The record with a quoted line break in its name counts as one row.

```yaml
tests:
- name: one_deletion_recorded
  function: csv.row_count
  parameter:
    dst: /home/user/out/timeline.csv
    entry: ["notes\nold.txt", '2026-01-01T10:06:00', Deleted]
    expected_count: 1
```

*no record for a file that was never touched* → PASSED

```yaml
tests:
- name: no_record_for_a_file_that_was_never_touched
  function: csv.row_count
  parameter:
    dst: /home/user/out/timeline.csv
    entry: [budget.xlsx, '2026-01-01T10:00:00', Created]
    expected_count: 0
```

*at least one row with three columns* → PASSED. The header row matches a layout of plain strings too.

```yaml
tests:
- name: at_least_one_row_with_three_columns
  function: csv.row_count
  parameter:
    dst: /home/user/out/timeline.csv
    entry: [name, time, action]
    expected_count: 1
    comparison_type: greater_equal
```

*a wrong count fails* → FAILED

```yaml
tests:
- name: a_wrong_count_fails
  function: csv.row_count
  parameter:
    dst: /home/user/out/timeline.csv
    entry: [report.docx, '2026-01-01T10:00:00', Created]
    expected_count: 2
```

*absence in a missing file is an error, not a pass* → ERROR

```yaml
tests:
- name: absence_in_a_missing_file_is_an_error_not_a_pass
  function: csv.row_count
  parameter:
    dst: /home/user/out/other.csv
    entry: [report.docx, '2026-01-01T10:00:00', Created]
    expected_count: 0
```

*an entry that is no list is an error* → ERROR

```yaml
tests:
- name: an_entry_that_is_no_list_is_an_error
  function: csv.row_count
  parameter:
    dst: /home/user/out/timeline.csv
    entry: report.docx
    expected_count: 1
```

**Related:**
- `csv.contains_line`: one matching row, with the closest rows reported on failure
