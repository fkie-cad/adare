# JSONL (`jsonl.*`)

<!-- Generated; do not edit by hand. -->

JSON Lines files (also called NDJSON): one JSON document per line, as written by event logs, history files and line-oriented exports. Every line is parsed on its own; blank lines are skipped and, by default, lines that are not valid JSON are ignored. `value_in_any_line` checks one field, `line_matches` several fields of the same line (in one line or in all of them) and `line_count` counts the lines that meet the conditions (`0` = absent).

## `jsonl.line_count`

counts lines in JSONL file matching conditions and validates against expected count (if None, requires at least 1 match)

Pass when the number of JSONL lines meeting all `conditions` is within `expected_count`.

**Use for:** asserting how many records/events were written (e.g. exactly 3 deletions); absence: `expected_count: 0`. For CSV records use csv.row_count, for lines of a plain text file text.line_count.

asserts: count, absent · formats: jsonl · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Key paths into structured files (`key_path`), Counts with a comparison (`count_comparison`), Negative tests (absence) (`negative`), Regex values (!re) (`regex_tag`), Placeholders ({{ variable }}) (`placeholder`), Times as expected values (!timestamp) (`timestamp_tag`), Text encodings (`encoding`)

**Not for:**
- lines of a plain text file that contain a string → `text.line_count`
- records of a CSV file → `csv.row_count`
- values in a single JSON document → `json.value_count`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` | `''` | Guest path to the JSONL file (one JSON document per line; blank lines are skipped). A glob must match exactly one path; a missing file is an error, a 0-byte file has 0 lines (passes `expected_count: 0`). |
| conditions | `dict[str, str \| int \| float \| bool \| None] \| None` | `None` | Mapping `key_path -> expected value` (all must hold; for multi-value paths one matching element suffices). `None`/empty counts every valid JSON line. |
| expected_count | `int \| dict[str, int] \| None` | `None` | Non-negative `int` compared with `comparison_type`, `{min: N, max: M}` for a range (either bound optional: min defaults to 0, max to unbounded), or `None` for "at least 1". Anything else (a negative number, a boolean, other keys, min > max) is an error. |
| regex_match | `bool` | `False` | Treat string expected values as regexes searched (`re.search`) in `str(value)`; the value `"*"` then means "key exists". Without it, values are compared with type-sensitive `==`; `!re`/`!timestamp` tags always work. |
| skip_malformed | `bool` | `True` | `True` (default) ignores lines that are not valid JSON; `False` makes the first malformed line an error. |
| comparison_type | `str` | `'equals'` | `equals` (default), `greater`, `less`, `greater_equal` or `less_equal`, applied to an `int` `expected_count`. With the range form or `None` only `equals` is allowed; other values are an error. Allowed: `equals`, `greater`, `less`, `greater_equal`, `less_equal`. |
| encoding | `str \| None` | `None` | `None` (default) detects a BOM (UTF-8/16/32) and BOM-less UTF-16, else reads UTF-8; a name reads BOM-less files with it. Unknown names or undecodable content are an error. |

**Outcomes:**
- PASSED: the number of valid lines meeting all `conditions` satisfies `expected_count`
- FAILED: the file was read and the count does not satisfy `expected_count`
- ERROR: the file does not exist; a glob matches no file or more than one
- ERROR: the file cannot be read or decoded; an unknown `encoding`
- ERROR: a malformed line with `skip_malformed` false
- ERROR: an invalid `expected_count` (negative, boolean, other keys than `min` / `max`, `min` > `max`)
- ERROR: an unknown `comparison_type`, or one other than `equals` with a range or no `expected_count`
- ERROR: an invalid regex or unknown placeholder

**Limits:**
- `expected_count` is an int (with `comparison_type`), a range `{min: N, max: M}` (either bound optional) or omitted for "at least 1".
- Without `conditions` every valid JSON line counts; malformed lines never count.
- A 0-byte file has 0 lines and passes `expected_count` 0.

**Use cases:**
- How often an action was recorded: Exactly one `file_deleted` event per deletion the playbook performed.
- Absence of a record: `expected_count: 0` shows that a visit or a cleared entry left no line.

**Examples:**

*two deletions recorded* → PASSED

```yaml
tests:
- name: two_deletions_recorded
  function: jsonl.line_count
  parameter:
    dst: /var/log/app/events.jsonl
    conditions: {event: file_deleted}
    expected_count: 2
```

*deletions within a range* → PASSED

```yaml
tests:
- name: deletions_within_a_range
  function: jsonl.line_count
  parameter:
    dst: /var/log/app/events.jsonl
    conditions: {event: file_deleted}
    expected_count: {min: 1, max: 5}
```

*no line for another user* → PASSED

```yaml
tests:
- name: no_line_for_another_user
  function: jsonl.line_count
  parameter:
    dst: /var/log/app/events.jsonl
    conditions: {user.name: carol}
    expected_count: 0
```

*all valid lines without conditions* → PASSED. Four records; the malformed line and the blank line do not count.

```yaml
tests:
- name: all_valid_lines_without_conditions
  function: jsonl.line_count
  parameter:
    dst: /var/log/app/events.jsonl
    expected_count: 4
```

*more than one event of a user* → PASSED

```yaml
tests:
- name: more_than_one_event_of_a_user
  function: jsonl.line_count
  parameter:
    dst: /var/log/app/events.jsonl
    conditions: {user.name: alice}
    expected_count: 1
    comparison_type: greater
```

*a compressed log* → PASSED. `events.jsonl.gz!` reads the decompressed content.

```yaml
tests:
- name: a_compressed_log
  function: jsonl.line_count
  parameter:
    dst: /var/log/app/events.jsonl.gz!
    conditions: {event: logout}
    expected_count: 1
```

*an empty file has no lines* → PASSED

```yaml
tests:
- name: an_empty_file_has_no_lines
  function: jsonl.line_count
  parameter:
    dst: /var/log/app/events.jsonl
    expected_count: 0
```

*a different count fails* → FAILED

```yaml
tests:
- name: a_different_count_fails
  function: jsonl.line_count
  parameter:
    dst: /var/log/app/events.jsonl
    conditions: {event: file_deleted}
    expected_count: 1
```

*comparison_type with a range is an error* → ERROR

```yaml
tests:
- name: comparison_type_with_a_range_is_an_error
  function: jsonl.line_count
  parameter:
    dst: /var/log/app/events.jsonl
    conditions: {event: file_deleted}
    expected_count: {min: 1}
    comparison_type: greater
```

*a missing file is an error, never a pass* → ERROR

```yaml
tests:
- name: a_missing_file_is_an_error_never_a_pass
  function: jsonl.line_count
  parameter:
    dst: /var/log/app/other.jsonl
    expected_count: 0
```

## `jsonl.line_matches`

tests if lines in JSONL file match specified conditions (supports any/all modes)

Pass when one line (`any`) or every valid line (`all`) of JSONL file `dst` meets all `conditions`.

**Use for:** event logs / NDJSON exports (e.g. "a line with type=login and user=alice exists"). To count matches use jsonl.line_count.

asserts: exists, value · formats: jsonl · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Key paths into structured files (`key_path`), Several matches (wildcard_mode) (`wildcard_mode`), Regex values (!re) (`regex_tag`), Placeholders ({{ variable }}) (`placeholder`), Times as expected values (!timestamp) (`timestamp_tag`), Text encodings (`encoding`)

**Does not support:**
- Ordered comparison of numbers and times (`ordered_comparison`): Conditions compare by equality, regex or tag; for a number or time threshold use jsonl.value_in_any_line with `comparison_type`.

**Not for:**
- how many lines meet the conditions, or none does → `jsonl.line_count`
- one field in any line → `jsonl.value_in_any_line`
- a value in a single JSON document → `json.value_matches`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` | `''` | Guest path to the JSONL file (one JSON document per line; blank lines are skipped). A glob must match exactly one path; a missing file is an error, a 0-byte file fails. |
| conditions | `dict[str, str \| int \| float \| bool \| None]` | `None` | Required mapping `key_path -> expected value`; a line matches when every condition holds. If a path yields several values (wildcard or JSON array), one matching element suffices. Missing keys fail the line. |
| wildcard_mode | `str` | `'any'` | `any` (default) or `all` (every valid line must match; no valid lines fails). Other values are an error. Allowed: `any`, `all`. |
| regex_match | `bool` | `False` | Treat string expected values as regexes searched (`re.search`) in `str(value)`; the value `"*"` then means "key exists". Without it, values are compared with type-sensitive `==`; `!re`/`!timestamp` tags always work. |
| skip_malformed | `bool` | `True` | `True` (default) ignores lines that are not valid JSON; `False` makes the first malformed line an error. |
| encoding | `str \| None` | `None` | `None` (default) detects a BOM (UTF-8/16/32) and BOM-less UTF-16, else reads UTF-8; a name reads BOM-less files with it. Unknown names or undecodable content are an error. |

**Outcomes:**
- PASSED: one line (`any`) or every valid line (`all`) meets all `conditions`
- FAILED: the file was read and no line (`any`) or not every valid line (`all`) meets the conditions
- FAILED: the file is empty (0 bytes), or (`all`) it has no valid JSON line
- ERROR: the file does not exist; a glob matches no file or more than one
- ERROR: the file cannot be read or decoded; an unknown `encoding`
- ERROR: a malformed line with `skip_malformed` false
- ERROR: an invalid `wildcard_mode`; `conditions` missing, empty or no mapping
- ERROR: an invalid regex or unknown placeholder

**Limits:**
- A missing key fails the line. When a path selects several values (a wildcard or an array), one matching value is enough.
- `wildcard_mode` is about lines: `all` means every valid line; malformed lines are skipped, not counted.
- With `regex_match` string values are regexes searched (`re.search`) in `str(value)` and `"*"` means "key exists"; without it values compare with type-sensitive `==`.

**Use cases:**
- An event with several fields: A line with `event` login and `user.name` alice proves the login was recorded as one event, not as two unrelated fields in different lines.
- Uniform exports: `wildcard_mode: all` checks that every record of an export has a field or a value format.

**Examples:**

*a login event of one user* → PASSED

```yaml
tests:
- name: a_login_event_of_one_user
  function: jsonl.line_matches
  parameter:
    dst: /var/log/app/events.jsonl
    conditions:
      event: login
      user.name: alice
```

*one element of an array matches* → PASSED

```yaml
tests:
- name: one_element_of_an_array_matches
  function: jsonl.line_matches
  parameter:
    dst: /var/log/app/events.jsonl
    conditions:
      tags[*]: sso
```

*every record has a time* → PASSED. The malformed line is skipped; `"*"` with `regex_match` means "key exists".

```yaml
tests:
- name: every_record_has_a_time
  function: jsonl.line_matches
  parameter:
    dst: /var/log/app/events.jsonl
    conditions:
      time: '*'
    regex_match: true
    wildcard_mode: all
```

*the fields in different lines do not match* → FAILED. Bob has a deletion and alice a login, but no single line has both.

```yaml
tests:
- name: the_fields_in_different_lines_do_not_match
  function: jsonl.line_matches
  parameter:
    dst: /var/log/app/events.jsonl
    conditions:
      event: login
      user.name: bob
```

*an empty file fails* → FAILED

```yaml
tests:
- name: an_empty_file_fails
  function: jsonl.line_matches
  parameter:
    dst: /var/log/app/events.jsonl
    conditions:
      event: login
```

*a malformed line is an error with skip_malformed false* → ERROR

```yaml
tests:
- name: a_malformed_line_is_an_error_with_skip_malformed
  function: jsonl.line_matches
  parameter:
    dst: /var/log/app/events.jsonl
    conditions:
      event: logout
    skip_malformed: false
```

*an invalid regex is an error* → ERROR

```yaml
tests:
- name: an_invalid_regex_is_an_error
  function: jsonl.line_matches
  parameter:
    dst: /var/log/app/events.jsonl
    conditions:
      event: '[unclosed'
    regex_match: true
```

## `jsonl.value_in_any_line`

tests if specified key path with expected value exists in any line of JSONL file

Pass when `key_path` has a value matching `expected_value` in at least one JSONL line.

With `comparison_type` (`greater`, `less`, ...), `tolerance` or the time parameters the value is compared as a number or timestamp.

**Use for:** a single-field check across a log; for multi-field conditions use jsonl.line_matches.

asserts: exists, value, order · formats: jsonl · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Key paths into structured files (`key_path`), Regex values (!re) (`regex_tag`), Placeholders ({{ variable }}) (`placeholder`), Times as expected values (!timestamp) (`timestamp_tag`), Ordered comparison of numbers and times (`ordered_comparison`), Text encodings (`encoding`)

**Not for:**
- several fields of the same line → `jsonl.line_matches`
- how many lines have the value, or none has it → `jsonl.line_count`
- a string anywhere in the raw file → `text.occurrence_count`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` | `''` | Guest path to the JSONL file (one JSON document per line; blank lines are skipped). A glob must match exactly one path; a missing file is an error, a 0-byte file fails. |
| **key_path** | `str` | `''` | Dot path inside each line's object, e.g. `event.type`; `*` expands object values, `name[*]` array elements. No numeric indexes. For multi-value paths one matching element suffices. |
| expected_value | `str \| int \| float \| bool \| None` | `None` | Value to find; see `regex_match` for how it is compared. |
| regex_match | `bool` | `False` | Treat string expected values as regexes searched (`re.search`) in `str(value)`; the value `"*"` then means "key exists". Without it, values are compared with type-sensitive `==`; `!re`/`!timestamp` tags always work. |
| skip_malformed | `bool` | `True` | `True` (default) ignores lines that are not valid JSON; `False` makes the first malformed line an error. |
| encoding | `str \| None` | `None` | `None` (default) detects a BOM (UTF-8/16/32) and BOM-less UTF-16, else reads UTF-8; a name reads BOM-less files with it. Unknown names or undecodable content are an error. |
| comparison_type | `str` | `'equals'` | `equals` (default), `not_equals`, `greater`, `less`, `greater_equal` or `less_equal`. Anything but `equals`, or any parameter below, compares the value with `expected_value` as a number or point in time (ordered mode; `less` = earlier); a `!re` tag, `{{placeholder}}` or `regex_match` is then an error, and so is a value that is no number or timestamp. Allowed: `equals`, `not_equals`, `greater`, `less`, `greater_equal`, `less_equal`. |
| value_type | `str` | `'auto'` | `auto` (default; numbers if both sides are numbers, else timestamps), `number` or `timestamp`. Allowed: `auto`, `number`, `timestamp`. |
| tolerance | `int \| float \| None` | `None` | Allowed difference for `equals`/`not_equals` (seconds for timestamps). |
| time_format | `str \| None` | `None` | `strptime` format of text timestamps on both sides; default ISO 8601 or RFC 2822. |
| timestamp_epoch | `int \| None` | `None` | Read numbers as a count since 1 January of `1970`, `1601` or `2001`. Allowed: `1970`, `1601`, `2001`. |
| timestamp_unit | `str \| None` | `None` | Unit of that count: `s` (default), `ms`, `us`, `ns` or `100ns`. Allowed: `s`, `ms`, `us`, `ns`, `100ns`. |
| utc_offset | `str \| None` | `None` | Zone of timestamps without one (`+02:00`); default UTC. |

**Outcomes:**
- PASSED: at least one valid line has a value at `key_path` that matches `expected_value`
- FAILED: the file was read and no line has a matching value (or the key at all), or the file is empty (0 bytes)
- ERROR: the file does not exist; a glob matches no file or more than one
- ERROR: the file cannot be read or decoded; an unknown `encoding`
- ERROR: a malformed line with `skip_malformed` false
- ERROR: an invalid regex or unknown placeholder
- ERROR: in ordered mode, a `!re` tag, placeholder or `regex_match`, bad ordered parameters, or a value in a line that is no number or timestamp

**Limits:**
- When a path selects several values (a wildcard or an array), one matching value is enough.
- With `regex_match` a string `expected_value` is a regex searched (`re.search`) in `str(value)` and `"*"` means "key exists"; without it values compare with type-sensitive `==`.
- In ordered mode every line that has the key must hold a number or timestamp there.

**Use cases:**
- A value was logged: A file name, URL or search term shows up in a history or event log.
- A field exists somewhere: `expected_value: "*"` with `regex_match: true` passes when any line has the key.
- An event after a point in time: `comparison_type: greater` on a time field.

**Examples:**

*a deleted path was logged* → PASSED

```yaml
tests:
- name: a_deleted_path_was_logged
  function: jsonl.value_in_any_line
  parameter:
    dst: /home/user/data/events.jsonl
    key_path: path
    expected_value: '^/home/bob/'
    regex_match: true
```

*a nested field* → PASSED

```yaml
tests:
- name: a_nested_field
  function: jsonl.value_in_any_line
  parameter:
    dst: /home/user/data/events.jsonl
    key_path: user.name
    expected_value: bob
```

*an array element by index* → PASSED

```yaml
tests:
- name: an_array_element_by_index
  function: jsonl.value_in_any_line
  parameter:
    dst: /home/user/data/events.jsonl
    key_path: tags[1]
    expected_value: sso
```

*an event after a point in time* → PASSED

```yaml
tests:
- name: an_event_after_a_point_in_time
  function: jsonl.value_in_any_line
  parameter:
    dst: /home/user/data/events.jsonl
    key_path: time
    expected_value: '2026-01-01T10:08:00Z'
    comparison_type: greater
```

*a value no line has fails* → FAILED

```yaml
tests:
- name: a_value_no_line_has_fails
  function: jsonl.value_in_any_line
  parameter:
    dst: /home/user/data/events.jsonl
    key_path: user.name
    expected_value: carol
```

*an ordered comparison of text is an error* → ERROR

```yaml
tests:
- name: an_ordered_comparison_of_text_is_an_error
  function: jsonl.value_in_any_line
  parameter:
    dst: /home/user/data/events.jsonl
    key_path: event
    expected_value: 5
    comparison_type: greater
```
