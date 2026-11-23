# TOML (`toml.*`)

<!-- Generated; do not edit by hand. -->

TOML files (`tomllib`, or `tomli` on Python 3.10): settings and state files. The functions check that a key path exists, what its value is (also as a number or point in time), how many values a path selects (`0` = absent) and how two values of one file relate. Tables are mappings (`[server]` with `port` is `server.port`) and an array of tables (`[[items]]`) is an array. Values keep their TOML types; dates and times become ISO 8601 strings.

## `toml.contains_key`

tests if a TOML file contains the specified key path (tables, arrays of tables)

Pass when `key_path` resolves to at least one value in TOML file `dst`.

**Use for:** checking that a settings/config file gained a key. To also check the value use toml.value_matches; to check that a key is absent use toml.value_count with `expected_count: 0` (or `expect_to_fail: true` here: a missing file stays an error).

asserts: exists · formats: toml · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Key paths into structured files (`key_path`)

**Does not support:**
- Text encodings (`encoding`): There is no `encoding` parameter; TOML is always UTF-8.

**Not for:**
- the value of a key → `toml.value_matches`
- a key or value is absent → `toml.value_count`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the TOML file (UTF-8). A glob must match exactly one path; `archive.zip!/member.toml` reads an archive member. A missing, unreadable or invalid file is an error. |
| **key_path** | `str` |  | Dot path from the root table; `[server]` / `server.port = 1` are both `server.port`. An array of tables (`[[items]]`) is an array: `items[*].name` for all entries, `items[0].name` / `items[-1].name` for one. `*` expands all values of a table (`profiles.*.enabled`). Keys with dots (quoted TOML keys such as `"app.window"`) use quotes in brackets: `['app.window'].width`. |

**Outcomes:**
- PASSED: `key_path` selects at least one value
- FAILED: the file was read and `key_path` selects nothing
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the content is not valid TOML (syntax error, duplicate key, impossible date or time, bytes that are not UTF-8)

**Limits:**
- With `expect_to_fail: true` a missing key passes, but a missing file stays an error; toml.value_count with `expected_count: 0` says the same more clearly.

**Use cases:**
- A setting was written: The key exists after the action, whatever its value.

**Examples:**

*a key in a table* → PASSED

```yaml
tests:
- name: a_key_in_a_table
  function: toml.contains_key
  parameter:
    dst: /home/user/.config/app/settings.toml
    key_path: server.port
```

*a key in the last entry of an array of tables* → PASSED

```yaml
tests:
- name: a_key_in_the_last_entry_of_an_array_of_tables
  function: toml.contains_key
  parameter:
    dst: /home/user/.config/app/settings.toml
    key_path: items[-1].tag
```

*a quoted table name with a dot* → PASSED

```yaml
tests:
- name: a_quoted_table_name_with_a_dot
  function: toml.contains_key
  parameter:
    dst: /home/user/.config/app/settings.toml
    key_path: "['app.window'].width"
```

*an absent key fails* → FAILED. To assert absence use toml.value_count with `expected_count` 0, which passes.

```yaml
tests:
- name: an_absent_key_fails
  function: toml.contains_key
  parameter:
    dst: /home/user/.config/app/settings.toml
    key_path: server.user
```

*a duplicate key is an error, not a failure* → ERROR

```yaml
tests:
- name: a_duplicate_key_is_an_error_not_a_failure
  function: toml.contains_key
  parameter:
    dst: /home/user/.config/app/settings.toml
    key_path: server.port
```

## `toml.value_count`

tests how many TOML values exist at a key path, optionally only those matching a value (0 = absent)

Pass when the number of values at `key_path` in TOML file `dst` compares to `expected_count`.

**Use for:** counting entries (`items[*]` for `[[items]]`) and asserting absence: `expected_count: 0` passes when the key path selects nothing (or nothing matches `expected_value`), while a missing or invalid file is still an error. A path that selects one array counts its elements when `expected_value` is given; without it every selected value counts once.

asserts: count, absent · formats: toml · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Key paths into structured files (`key_path`), Counts with a comparison (`count_comparison`), Negative tests (absence) (`negative`), Regex values (!re) (`regex_tag`), Placeholders ({{ variable }}) (`placeholder`), Times as expected values (!timestamp) (`timestamp_tag`)

**Does not support:**
- Text encodings (`encoding`): There is no `encoding` parameter; TOML is always UTF-8.

**Not for:**
- what one value is → `toml.value_matches`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the TOML file; a glob must match exactly one path. |
| **key_path** | `str` |  | Dot path from the root table (syntax as in toml.contains_key). |
| **expected_count** | `int` |  | Non-negative integer to compare with. |
| expected_value | `str \| int \| float \| bool \| None` | `None` | Only count values equal to this (normalised as in toml.value_matches). `None` (default) counts every value. |
| regex_match | `bool` | `False` | Treat a string `expected_value` as a regex searched in `str(value)`. |
| comparison_type | `str` | `'equals'` | `equals` (default), `greater`, `less`, `greater_equal` or `less_equal`. Other values are an error. Allowed: `equals`, `greater`, `less`, `greater_equal`, `less_equal`. |

**Outcomes:**
- PASSED: the number of values at `key_path` (only those matching `expected_value`, if given) satisfies `comparison_type`
- FAILED: the file was read and the count comparison does not hold
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the content is not valid TOML (syntax error, duplicate key, impossible date or time, bytes that are not UTF-8)
- ERROR: a negative or non-integer `expected_count`; an unknown `comparison_type`
- ERROR: an invalid regex or unknown placeholder

**Limits:**
- Without `expected_value` every selected value counts once (an array is one value, `items[*]` counts its entries).
- With `expected_value` a path that selects exactly one array counts its matching elements.

**Use cases:**
- A key or value is absent: `expected_count: 0`.
- How many entries an array holds: Arrays of tables such as accounts or profiles.

**Examples:**

*two entries* → PASSED

```yaml
tests:
- name: two_entries
  function: toml.value_count
  parameter:
    dst: /home/user/.config/app/settings.toml
    key_path: items[*]
    expected_count: 2
```

*one archived entry* → PASSED

```yaml
tests:
- name: one_archived_entry
  function: toml.value_count
  parameter:
    dst: /home/user/.config/app/settings.toml
    key_path: items[*].tag
    expected_value: archived
    expected_count: 1
```

*a key was removed* → PASSED

```yaml
tests:
- name: a_key_was_removed
  function: toml.value_count
  parameter:
    dst: /home/user/.config/app/settings.toml
    key_path: server.user
    expected_count: 0
```

*a negative expected_count is an error* → ERROR

```yaml
tests:
- name: a_negative_expected_count_is_an_error
  function: toml.value_count
  parameter:
    dst: /home/user/.config/app/settings.toml
    key_path: items[*]
    expected_count: -1
```

## `toml.value_matches`

tests if the TOML value at a key path matches the expected value (dates/times as ISO strings)

Pass when the TOML value at `key_path` in `dst` equals (or matches) `expected_value`.

With `comparison_type` (`greater`, `less`, ...), `tolerance` or the time parameters the value is compared as a number or timestamp; to compare two values of one file use toml.values_compare.

**Use for:** asserting a setting/field value. If the path yields several values (a wildcard, or an array value, whose elements are then compared one by one) `wildcard_mode` decides. Values keep their TOML types (integers, floats, booleans, strings); dates and times become ISO 8601 strings: `1979-05-27`, `07:32:00`, `1979-05-27T07:32:00` (local) or `1979-05-27T07:32:00-08:00` (`Z` becomes `+00:00`).

asserts: value, order · formats: toml · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Key paths into structured files (`key_path`), Several matches (wildcard_mode) (`wildcard_mode`), Regex values (!re) (`regex_tag`), Placeholders ({{ variable }}) (`placeholder`), Times as expected values (!timestamp) (`timestamp_tag`), Ordered comparison of numbers and times (`ordered_comparison`), Decoding a stored value (value_decode) (`value_decode`)

**Does not support:**
- Text encodings (`encoding`): There is no `encoding` parameter; TOML is always UTF-8.

**Not for:**
- no value matches, a key is absent → `toml.value_count`
- two values of one file relate (earlier, within seconds, one above) → `toml.values_compare`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the TOML file; a glob must match exactly one path. A missing or invalid file is an error; an unresolvable key path fails. |
| **key_path** | `str` |  | Dot path from the root table (syntax as in toml.contains_key), e.g. `items[*].name` for every `[[items]]` entry. |
| **expected_value** | `str \| int \| float \| bool \| None` |  | Compared with Python `==`, which is type-sensitive (`5` != `"5"`). A `!re` tag (`re.match`) or `{{placeholder}}` compares `str(value)`. |
| regex_match | `bool` | `False` | Treat a string `expected_value` as a regex searched (`re.search`, unanchored) in `str(value)`. An invalid regex is an error. |
| wildcard_mode | `str` | `'any'` | `any` (default): one value must match; `all`: every value must match. Other values are an error. Allowed: `any`, `all`. |
| comparison_type | `str` | `'equals'` | `equals` (default), `not_equals`, `greater`, `less`, `greater_equal` or `less_equal`. Anything but `equals`, or any parameter below, compares the value with `expected_value` as a number or point in time (ordered mode; `less` = earlier); `!re` / `regex_match` are then errors, a lone `{{ name }}` is the saved variable; a value that is no number or timestamp is an error. Allowed: `equals`, `not_equals`, `greater`, `less`, `greater_equal`, `less_equal`. |
| value_type | `str` | `'auto'` | `auto` (default; numbers if both sides are numbers, else timestamps), `number` or `timestamp`. Allowed: `auto`, `number`, `timestamp`. |
| tolerance | `int \| float \| None` | `None` | Allowed difference for `equals`/`not_equals` (seconds for timestamps). |
| time_format | `str \| None` | `None` | `strptime` format of text timestamps on both sides; default ISO 8601 or RFC 2822. |
| timestamp_epoch | `int \| None` | `None` | Read numbers as a count since 1 January of `1970`, `1601` or `2001`. Allowed: `1970`, `1601`, `2001`. |
| timestamp_unit | `str \| None` | `None` | Unit of that count: `s` (default), `ms`, `us`, `ns` or `100ns`. Allowed: `s`, `ms`, `us`, `ns`, `100ns`. |
| utc_offset | `str \| None` | `None` | Zone of timestamps without one (`+02:00`); default UTC. |
| value_decode | `list[str] \| str \| None` | `None` | Decode the value read from the file before comparing: one step or a list applied in order: `url` (percent-decoding), `base64`, `hex`, `utf16` (bytes as UTF-16 text), `json` (parse, then take `decoded_key_path`). Bytes left at the end are UTF-8 text, else hex. A value a step cannot decode, or an unknown step, is an error. |
| decoded_key_path | `str \| None` | `None` | Key path into the value `json` decoded (syntax as in `key_path`); it must select one value: none fails (the value decoded, the key is not in it), several are an error. Required with `json`, an error without it. |

**Outcomes:**
- PASSED: the value at `key_path` (`any`: one of the values, `all`: every value) matches `expected_value`
- FAILED: the file was read and `key_path` selects nothing or an empty array, or the value(s) do not match
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the content is not valid TOML (syntax error, duplicate key, impossible date or time, bytes that are not UTF-8)
- ERROR: an invalid `wildcard_mode`; an invalid regex or unknown placeholder
- ERROR: in ordered mode, a `!re` tag or `regex_match`, text around a `{{ name }}` or a saved variable that is no number or time, bad ordered parameters, or a value that is no number or timestamp

**Limits:**
- Equality is Python `==` and type-sensitive (`5` is not `"5"`).
- Dates and times compare as ISO 8601 strings: `2026-01-01` (local date), `07:32:00` (local time), `2026-01-01T11:00:00` (local date-time), `2026-01-01T10:00:00+00:00` (`Z` becomes `+00:00`).
- A path that selects an array compares its elements one by one; a whole array cannot be compared.
- `regex_match` searches (`re.search`, unanchored); a `!re` tag matches from the start (`re.match`).

**Use cases:**
- A setting has a value: A setting changed in the GUI is stored in a TOML configuration.
- An entry of an array of tables: `items[*].name` for every `[[items]]` entry.

**Examples:**

*one entry has a name* → PASSED

```yaml
tests:
- name: one_entry_has_a_name
  function: toml.value_matches
  parameter:
    dst: /home/user/.config/app/settings.toml
    key_path: items[*].name
    expected_value: Example Entry
```

*an offset date-time as ISO 8601 text* → PASSED. `Z` becomes `+00:00`.

```yaml
tests:
- name: an_offset_date_time_as_iso_8601_text
  function: toml.value_matches
  parameter:
    dst: /home/user/.config/app/settings.toml
    key_path: session.opened
    expected_value: '2026-01-01T10:00:00+00:00'
```

*a port of at least 1024* → PASSED

```yaml
tests:
- name: a_port_of_at_least_1024
  function: toml.value_matches
  parameter:
    dst: /home/user/.config/app/settings.toml
    key_path: server.port
    expected_value: 1024
    comparison_type: greater_equal
```

*not every entry is archived* → FAILED

```yaml
tests:
- name: not_every_entry_is_archived
  function: toml.value_matches
  parameter:
    dst: /home/user/.config/app/settings.toml
    key_path: items[*].tag
    expected_value: archived
    wildcard_mode: all
```

*a host name pattern* → PASSED

```yaml
tests:
- name: a_host_name_pattern
  function: toml.value_matches
  parameter:
    dst: /home/user/.config/app/settings.toml
    key_path: server.host
    expected_value: !re '^local'
```

*a glob with several matches is an error* → ERROR

```yaml
tests:
- name: a_glob_with_several_matches_is_an_error
  function: toml.value_matches
  parameter:
    dst: /home/user/.config/app/settings-*.toml
    key_path: server.port
    expected_value: 8080
```

## `toml.values_compare`

compares two values of one TOML file (or of two files) as numbers or timestamps (earlier/later, within a tolerance, A = B + offset)

Pass when the value at `key_path` compares to the value at `other_key_path` (+ `offset`).

**Use for:** relations inside one file (or between two, `other_dst`): a last-saved value later than the first-opened one, two timestamps within a few seconds of each other, a counter one above another (`comparison_type: equals` with `offset: 1`). To compare one value with a constant use toml.value_matches with `comparison_type`.

asserts: order, compare · formats: toml · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Key paths into structured files (`key_path`), Ordered comparison of numbers and times (`ordered_comparison`), Decoding a stored value (value_decode) (`value_decode`), A second file (other_dst) (`other_dst`)

**Does not support:**
- Text encodings (`encoding`): There is no `encoding` parameter; TOML is always UTF-8.

**Not for:**
- one value against a constant → `toml.value_matches`
- two text values are equal → `toml.value_matches`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the TOML file; a glob must match exactly one path. A missing or invalid file is an error. Dates and times are read as ISO 8601 (a local date-time without zone is in `utc_offset`). |
| **key_path** | `str` |  | Dot path of the first value (syntax as in toml.contains_key). It must select exactly one value (a one-element array counts as its element): nothing fails, several values are an error. |
| **other_key_path** | `str` |  | Dot path of the second value; same rules. |
| comparison_type | `str` | `'equals'` | How the first value relates to the second: `equals` (default), `not_equals`, `greater`, `less`, `greater_equal` or `less_equal` (`less` = earlier for timestamps). Other values are an error. Allowed: `equals`, `not_equals`, `greater`, `less`, `greater_equal`, `less_equal`. |
| value_type | `str` | `'auto'` | `auto` (default; numbers if both are numbers, else timestamps), `number` or `timestamp`. A value that is no number or timestamp is an error. Allowed: `auto`, `number`, `timestamp`. |
| tolerance | `int \| float \| None` | `None` | Allowed difference for `equals`/`not_equals` (seconds for timestamps). |
| offset | `int \| float \| None` | `None` | Added to the second value before comparing (seconds for timestamps, may be negative; `'{{ name }}'` = a saved number): `first <comparison_type> second + offset`. |
| time_format | `str \| None` | `None` | `strptime` format of text timestamps on both sides; default ISO 8601 or RFC 2822. |
| timestamp_epoch | `int \| None` | `None` | Read numbers as a count since 1 January of `1970`, `1601` or `2001`. Allowed: `1970`, `1601`, `2001`. |
| timestamp_unit | `str \| None` | `None` | Unit of that count: `s` (default), `ms`, `us`, `ns` or `100ns`. Allowed: `s`, `ms`, `us`, `ns`, `100ns`. |
| utc_offset | `str \| None` | `None` | Zone of timestamps without one (`+02:00`); default UTC. |
| other_dst | `str \| None` | `None` | Guest path of a second file to read `other_key_path` from (same rules as `dst`, `archive!/member` included); default `None`: `dst`. A missing file is an error. Compares a file with a copy saved before an action. |
| value_decode | `list[str] \| str \| None` | `None` | Decode both values before comparing (steps as in toml.value_matches). |
| decoded_key_path | `str \| None` | `None` | With `json` in `value_decode`: key path into the decoded value; it must select one value: none fails, several are an error. |

**Outcomes:**
- PASSED: `first <comparison_type> second + offset` holds
- FAILED: the file was read and a side selects nothing, or the comparison does not hold
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the content is not valid TOML
- ERROR: a side selects several values
- ERROR: a value that is no number or timestamp, or a number compared with a timestamp
- ERROR: invalid parameters (`comparison_type`, `value_type`, `tolerance` with an order comparison, `timestamp_epoch`, ...)

**Limits:**
- Each side must select exactly one value (a one-element array counts as its element).
- Numbers and times only; two text values cannot be compared.
- A local date-time (no zone) is read in `utc_offset` (default UTC).

**Use cases:**
- A is earlier than B: A last-saved value later than the first-opened one, an end after a start (`comparison_type` `less` / `greater`).
- A within a few seconds of B: Two timestamps written by one action (`tolerance: 5`).
- A = B + n: A counter one above another (`offset: 1`), or a time a fixed interval after another (`offset` in seconds).

**Examples:**

*a counter not above another* → PASSED

```yaml
tests:
- name: a_counter_not_above_another
  function: toml.values_compare
  parameter:
    dst: /home/user/.config/app/state.toml
    key_path: counters.opened
    other_key_path: counters.saved
    comparison_type: less_equal
```

*closed half an hour after opened* → PASSED

```yaml
tests:
- name: closed_half_an_hour_after_opened
  function: toml.values_compare
  parameter:
    dst: /home/user/.config/app/state.toml
    key_path: session.closed
    other_key_path: session.opened
    offset: 1800
```

*a local date-time in a time zone* → PASSED. 11:00 local at `+01:00` is 10:00 UTC, the time `session.opened` holds.

```yaml
tests:
- name: a_local_date_time_in_a_time_zone
  function: toml.values_compare
  parameter:
    dst: /home/user/.config/app/state.toml
    key_path: session.local
    other_key_path: session.opened
    utc_offset: '+01:00'
```

*the comparison does not hold* → FAILED

```yaml
tests:
- name: the_comparison_does_not_hold
  function: toml.values_compare
  parameter:
    dst: /home/user/.config/app/state.toml
    key_path: session.opened
    other_key_path: session.closed
    comparison_type: greater
```

*a side with several values is an error* → ERROR

```yaml
tests:
- name: a_side_with_several_values_is_an_error
  function: toml.values_compare
  parameter:
    dst: /home/user/.config/app/state.toml
    key_path: items[*].name
    other_key_path: counters.saved
```
