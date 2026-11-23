# JSON (`json.*`)

<!-- Generated; do not edit by hand. -->

JSON documents such as settings files, session stores and exported records. The functions check that a key path exists, what its value is (also as a number or point in time), whether an array holds an element, how many values a path selects (`0` = absent) and how two values of one file relate. Files are decoded as UTF-8/16/32 with or without BOM, or in a given `encoding`; LZ4-compressed stores are read through `store.jsonlz4!`.

## `json.array_contains`

tests if JSON array at specified path contains expected element

Pass when the JSON array at `array_path` in `dst` contains `expected_value`.

**Use for:** checking that a list in a JSON file includes an entry. To count entries use json.value_count (`array_path[*]` as key path).

asserts: value · formats: json · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Key paths into structured files (`key_path`), Regex values (!re) (`regex_tag`), Placeholders ({{ variable }}) (`placeholder`), Times as expected values (!timestamp) (`timestamp_tag`), Text encodings (`encoding`)

**Not for:**
- an element whose one field has a value (objects compare whole) → `json.value_matches`
- how many elements, or an element is gone → `json.value_count`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the JSON file; a glob must match exactly one path. A missing file or invalid JSON is an error; an unresolvable path or non-array value fails. `x.jsonlz4!` reads LZ4-compressed JSON. |
| **array_path** | `str` |  | Dot path to the array (same syntax as json.value_matches `key_path`); a wildcard yielding several values is treated as the array of those values. |
| **expected_value** | `str \| int \| float \| bool \| dict \| list \| None` |  | Required. An element equal to it (type-sensitive `==`; dicts and lists must match exactly). A `!re`/`!timestamp` tag passes if any element's `str()` matches; an invalid regex or unknown placeholder is an error. |
| encoding | `str \| None` | `None` | `None` (default) detects UTF-8/16/32 with or without BOM; a name (`latin-1`) decodes BOM-less files with it. Unknown names are an error. |

**Outcomes:**
- PASSED: the array at `array_path` has an element equal to (or matching) `expected_value`
- FAILED: the file was read and the path does not exist, is no array, or no element matches
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the file is not valid JSON or cannot be decoded; an unknown `encoding`
- ERROR: an invalid `!re` or unknown placeholder in `expected_value`

**Limits:**
- Elements compare with type-sensitive `==`; objects and arrays must be equal as a whole.
- A wildcard path that selects several values is treated as the array of those values.
- There is no `regex_match`; use a `!re` tag, which matches the `str()` of each element.

**Use cases:**
- A list in a settings file gained an entry: Recent files, allowed origins or enabled extensions.
- A whole record in a list: An object such as `{action: read, resource: users}` as one element.

**Examples:**

*recent files include a document* → PASSED

```yaml
tests:
- name: recent_files_include_a_document
  function: json.array_contains
  parameter:
    dst: /home/user/.config/app/settings.json
    array_path: recent_files
    expected_value: /home/user/Documents/report.odt
```

*a whole object as element* → PASSED

```yaml
tests:
- name: a_whole_object_as_element
  function: json.array_contains
  parameter:
    dst: /home/user/.config/app/settings.json
    array_path: groups[0].items
    expected_value: {title: Notes, tag: active}
```

*a wildcard path forms the array* → PASSED

```yaml
tests:
- name: a_wildcard_path_forms_the_array
  function: json.array_contains
  parameter:
    dst: /home/user/.config/app/settings.json
    array_path: groups[*].name
    expected_value: home
```

*a partial object does not match* → FAILED. Objects compare whole; for one field use json.value_matches with `groups[0].items[*].title`.

```yaml
tests:
- name: a_partial_object_does_not_match
  function: json.array_contains
  parameter:
    dst: /home/user/.config/app/settings.json
    array_path: groups[0].items
    expected_value: {title: Notes}
```

*a value that is no array fails* → FAILED

```yaml
tests:
- name: a_value_that_is_no_array_fails
  function: json.array_contains
  parameter:
    dst: /home/user/.config/app/settings.json
    array_path: display.theme
    expected_value: dark
```

## `json.contains_key`

tests if JSON file contains specified key path (supports dot notation like "user.profile.name")

Pass when `key_path` resolves to at least one value in JSON file `dst` (`null` counts).

**Use for:** checking a settings/config file gained a key. To also check the value use json.value_matches. Absence of a key: `expect_to_fail: true` here, or json.value_count with `expected_count: 0`.

asserts: exists · formats: json · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Key paths into structured files (`key_path`), Text encodings (`encoding`)

**Not for:**
- the value of a key → `json.value_matches`
- a key or value is absent → `json.value_count`
- a list holds an entry → `json.array_contains`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the JSON file; a glob must match exactly one path. A missing file or invalid JSON is an error. LZ4-compressed JSON is read through the archive separator (`/home/user/data/store.jsonlz4!`). |
| **key_path** | `str` |  | Dot path from the root, e.g. `user.profile.name`. `*` expands all values of an object (`config.*.enabled`), `[*]` all elements of an array (`users[*].email`), `[n]` one element (`items[0]`; `items[-1]` = last). A leading bracket addresses a top-level array (`[0].name`, `[*].id`); `['a.b']` quotes a key that contains dots or brackets. |
| encoding | `str \| None` | `None` | `None` (default) detects UTF-8/16/32 with or without BOM; a name (`latin-1`) decodes BOM-less files with it. Unknown names are an error. |

**Outcomes:**
- PASSED: `key_path` selects at least one value (a `null` value counts)
- FAILED: the file was read and `key_path` selects nothing
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the file is not valid JSON or cannot be decoded; an unknown `encoding`

**Limits:**
- With `expect_to_fail: true` a missing key passes, but a missing file stays an error; json.value_count with `expected_count: 0` says the same more clearly.

**Use cases:**
- A setting was written: A settings or configuration file gained a key after an action, whatever its value.

**Examples:**

*nested key exists* → PASSED

```yaml
tests:
- name: nested_key_exists
  function: json.contains_key
  parameter:
    dst: /home/user/data/settings.json
    key_path: display.fontSize
```

*a null value counts as present* → PASSED

```yaml
tests:
- name: a_null_value_counts_as_present
  function: json.contains_key
  parameter:
    dst: /home/user/data/settings.json
    key_path: sync
```

*a key that contains a dot* → PASSED

```yaml
tests:
- name: a_key_that_contains_a_dot
  function: json.contains_key
  parameter:
    dst: /home/user/data/settings.json
    key_path: "['app.window'].width"
```

*an absent key fails* → FAILED. To assert absence use json.value_count with `expected_count` 0, which passes.

```yaml
tests:
- name: an_absent_key_fails
  function: json.contains_key
  parameter:
    dst: /home/user/data/settings.json
    key_path: display.language
```

*invalid JSON is an error, not a failure* → ERROR

```yaml
tests:
- name: invalid_json_is_an_error_not_a_failure
  function: json.contains_key
  parameter:
    dst: /home/user/data/settings.json
    key_path: display.fontSize
```

## `json.value_count`

tests the number of JSON values at a key path (optionally only those matching a value)

Pass when the number of values at `key_path` in JSON file `dst` satisfies `comparison_type`.

**Use for:** counting entries (e.g. exactly 3 bookmarks with a given tag) and asserting absence: `expected_count: 0` without `expected_value` passes when the key path selects nothing, with `expected_value` when no value matches. To check what one value is use json.value_matches.

asserts: count, absent · formats: json · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Key paths into structured files (`key_path`), Counts with a comparison (`count_comparison`), Negative tests (absence) (`negative`), Regex values (!re) (`regex_tag`), Placeholders ({{ variable }}) (`placeholder`), Times as expected values (!timestamp) (`timestamp_tag`), Text encodings (`encoding`)

**Not for:**
- what one value is → `json.value_matches`
- records in a JSON Lines file → `jsonl.line_count`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the JSON file; a glob must match exactly one path. A missing file or invalid JSON is an error. `x.jsonlz4!` reads LZ4-compressed JSON. |
| **key_path** | `str` |  | Dot path from the root, e.g. `user.profile.name`. `*` expands all values of an object (`config.*.enabled`), `[*]` all elements of an array (`users[*].email`), `[n]` one element (`items[0]`; `items[-1]` = last). A leading bracket addresses a top-level array (`[0].name`, `[*].id`); `['a.b']` quotes a key that contains dots or brackets. |
| **expected_count** | `int` |  | Non-negative integer to compare against; anything else is an error. |
| expected_value | `str \| int \| float \| bool \| None` | `None` | `None` (default) counts the values the path selects (a `null` value counts; an array is one value, `items[*]` counts its elements). Otherwise counts the values equal to it (type-sensitive `==`; `!re`/`!timestamp` tags compare `str(value)`; an invalid regex or unknown placeholder is an error); a path that selects exactly one array compares its elements one by one. |
| regex_match | `bool` | `False` | Treat a string `expected_value` as a regex searched (`re.search`, unanchored) in `str(value)`; an invalid regex is an error. |
| comparison_type | `str` | `'equals'` | `equals` (default), `greater`, `less`, `greater_equal` or `less_equal`; other values are an error. Allowed: `equals`, `greater`, `less`, `greater_equal`, `less_equal`. |
| encoding | `str \| None` | `None` | `None` (default) detects UTF-8/16/32 with or without BOM; a name (`latin-1`) decodes BOM-less files with it. Unknown names are an error. |

**Outcomes:**
- PASSED: the number of values at `key_path` (only those matching `expected_value`, if given) satisfies `comparison_type`
- FAILED: the file was read and the count comparison does not hold
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the file is not valid JSON or cannot be decoded; an unknown `encoding`
- ERROR: a negative or non-integer `expected_count`; an unknown `comparison_type`
- ERROR: an invalid regex or unknown placeholder

**Limits:**
- Without `expected_value` every selected value counts once (`null` too; an array is one value, `list[*]` counts its elements).
- With `expected_value` a path that selects exactly one array counts its matching elements.

**Use cases:**
- A key or value is absent: `expected_count: 0`: the key path selects nothing, or no value matches `expected_value`.
- How many entries a list holds: Exactly three bookmarks, at least one entry with a URL.

**Examples:**

*two archived entries* → PASSED

```yaml
tests:
- name: two_archived_entries
  function: json.value_count
  parameter:
    dst: /home/user/data/settings.json
    key_path: groups[*].items[*].tag
    expected_value: archived
    expected_count: 2
```

*an entry was removed* → PASSED. No title matches, so the count is 0 and the test passes.

```yaml
tests:
- name: an_entry_was_removed
  function: json.value_count
  parameter:
    dst: /home/user/data/settings.json
    key_path: groups[*].items[*].title
    expected_value: Shopping
    expected_count: 0
```

*a key is absent* → PASSED

```yaml
tests:
- name: a_key_is_absent
  function: json.value_count
  parameter:
    dst: /home/user/data/settings.json
    key_path: display.language
    expected_count: 0
```

*at least one recent file* → PASSED

```yaml
tests:
- name: at_least_one_recent_file
  function: json.value_count
  parameter:
    dst: /home/user/data/settings.json
    key_path: recent_files[*]
    expected_count: 1
    comparison_type: greater_equal
```

*tags in an LZ4-compressed store* → PASSED. `store.jsonlz4!` reads the decompressed JSON; `[*]` addresses the top-level array.

```yaml
tests:
- name: tags_in_an_lz4_compressed_store
  function: json.value_count
  parameter:
    dst: /home/user/data/store.jsonlz4!
    key_path: '[*].tag'
    expected_value: a
    expected_count: 2
```

*a missing file is an error, never a pass* → ERROR. `expected_count: 0` proves absence only in a file that was read.

```yaml
tests:
- name: a_missing_file_is_an_error_never_a_pass
  function: json.value_count
  parameter:
    dst: /home/user/data/other.json
    key_path: display.language
    expected_count: 0
```

## `json.value_matches`

tests if JSON value at key path matches expected value using placeholders (supports wildcards [*] and * with any/all modes)

Pass when the JSON value at `key_path` in `dst` equals (or matches) `expected_value`.

With `comparison_type` (`greater`, `less`, ...), `tolerance` or the time parameters the value is compared as a number or timestamp; to compare two values of one file use json.values_compare.

**Use for:** asserting a setting/field value. If the path yields several values (a wildcard, or a JSON array value, whose elements are then compared one by one) `wildcard_mode` decides; a one-element array is unwrapped. Whole arrays cannot be compared. To assert that no value matches use json.value_count with `expected_count: 0`.

asserts: value, order · formats: json · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Key paths into structured files (`key_path`), Several matches (wildcard_mode) (`wildcard_mode`), Regex values (!re) (`regex_tag`), Placeholders ({{ variable }}) (`placeholder`), Times as expected values (!timestamp) (`timestamp_tag`), Ordered comparison of numbers and times (`ordered_comparison`), Text encodings (`encoding`), Decoding a stored value (value_decode) (`value_decode`)

**Not for:**
- no value matches, a key is absent → `json.value_count`
- two values of one file relate (earlier, within seconds, one above) → `json.values_compare`
- a list holds a whole object or a value as one element → `json.array_contains`
- one field in any line of a JSON Lines log → `jsonl.value_in_any_line`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the JSON file; a glob must match exactly one path. A missing file or invalid JSON is an error; an unresolvable key path fails. `x.jsonlz4!` reads LZ4-compressed JSON. |
| **key_path** | `str` |  | Dot path from the root, e.g. `user.profile.name`. `*` expands all values of an object (`config.*.enabled`), `[*]` all elements of an array (`users[*].email`), `[n]` one element (`items[0]`; `items[-1]` = last). A leading bracket addresses a top-level array (`[0].name`, `[*].id`); `['a.b']` quotes a key that contains dots or brackets. |
| **expected_value** | `str \| int \| float \| bool \| None` |  | Required. Compared with Python `==`, which is type-sensitive (`5` != `"5"`; a JSON `null` needs `expected_value: null`). A `!re`/`!timestamp` tag compares `str(value)` by type; an invalid regex or unknown placeholder is an error. |
| regex_match | `bool` | `False` | Treat a string `expected_value` as a regex searched (`re.search`, unanchored) in `str(value)`. |
| wildcard_mode | `str` | `'any'` | `any` (default): one value must match; `all`: every value must match. Other values are an error. Allowed: `any`, `all`. |
| encoding | `str \| None` | `None` | `None` (default) detects UTF-8/16/32 with or without BOM; a name (`latin-1`) decodes BOM-less files with it. Unknown names are an error. |
| comparison_type | `str` | `'equals'` | `equals` (default), `not_equals`, `greater`, `less`, `greater_equal` or `less_equal`. Anything but `equals`, or any parameter below, compares the value with `expected_value` as a number or point in time (ordered mode; `less` = earlier); `!re` / `regex_match` are then errors, a lone `{{ name }}` is the saved variable; a value that is no number or timestamp is an error. Allowed: `equals`, `not_equals`, `greater`, `less`, `greater_equal`, `less_equal`. |
| value_type | `str` | `'auto'` | `auto` (default; numbers if both sides are numbers, else timestamps), `number` or `timestamp`. Allowed: `auto`, `number`, `timestamp`. |
| tolerance | `int \| float \| None` | `None` | Allowed difference for `equals`/`not_equals` (seconds for timestamps). |
| time_format | `str \| None` | `None` | `strptime` format of text timestamps on both sides; default ISO 8601 or RFC 2822. |
| timestamp_epoch | `int \| None` | `None` | Read numbers as a count since 1 January of `1970`, `1601` or `2001`. Allowed: `1970`, `1601`, `2001`. |
| timestamp_unit | `str \| None` | `None` | Unit of that count: `s` (default), `ms`, `us`, `ns` or `100ns`. Allowed: `s`, `ms`, `us`, `ns`, `100ns`. |
| utc_offset | `str \| None` | `None` | Zone of timestamps without one (`+02:00`); default UTC. |
| value_decode | `list[str] \| str \| None` | `None` | Decode the value read from the file before comparing: one step or a list applied in order: `url` (percent-decoding), `base64`, `hex`, `utf16` (bytes as UTF-16 text), `json` (parse, then take `decoded_key_path`). Bytes left at the end are UTF-8 text, else hex. A value a step cannot decode, or an unknown step, is an error. |
| decoded_key_path | `str \| None` | `None` | Key path into the value `json` decoded (syntax as in `key_path`); it must select one value. Required with `json`, an error without it. |

**Outcomes:**
- PASSED: the value at `key_path` (`any`: one of the values, `all`: every value) matches `expected_value`
- FAILED: the file was read and `key_path` selects nothing, or the value(s) do not match
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the file is not valid JSON or cannot be decoded; an unknown `encoding`
- ERROR: an invalid `wildcard_mode`; an invalid regex or unknown placeholder
- ERROR: in ordered mode, a `!re` tag or `regex_match`, text around a `{{ name }}` or a saved variable that is no number or time, bad ordered parameters, or a value that is no number or timestamp

**Limits:**
- Equality is Python `==` and type-sensitive (`5` is not `"5"`; a JSON `null` needs `expected_value: null`).
- A path that selects an array compares its elements one by one (a one-element array is unwrapped); a whole array cannot be compared.
- `regex_match` searches (`re.search`, unanchored); a `!re` tag matches from the start (`re.match`).

**Use cases:**
- A setting has a value: A setting changed in the GUI is stored in a JSON settings file.
- Every entry of a list has a property: `list[*].field` with `wildcard_mode: all`.
- A number or time above or below a threshold: `comparison_type: greater` with the time parameters for times stored as numbers.

**Examples:**

*a setting has a value* → PASSED

```yaml
tests:
- name: a_setting_has_a_value
  function: json.value_matches
  parameter:
    dst: /home/user/data/settings.json
    key_path: display.theme
    expected_value: dark
```

*one entry in nested arrays has a title* → PASSED

```yaml
tests:
- name: one_entry_in_nested_arrays_has_a_title
  function: json.value_matches
  parameter:
    dst: /home/user/data/settings.json
    key_path: groups[*].items[*].title
    expected_value: Example Entry
```

*not every entry is archived* → FAILED. `wildcard_mode: all` needs every selected value to match.

```yaml
tests:
- name: not_every_entry_is_archived
  function: json.value_matches
  parameter:
    dst: /home/user/data/settings.json
    key_path: groups[*].items[*].tag
    expected_value: archived
    wildcard_mode: all
```

*equality is type-sensitive* → FAILED. The file holds the number 14; the string `"14"` does not match.

```yaml
tests:
- name: equality_is_type_sensitive
  function: json.value_matches
  parameter:
    dst: /home/user/data/settings.json
    key_path: display.fontSize
    expected_value: '14'
```

*saved after a point in time* → PASSED. The value counts milliseconds since 1970.

```yaml
tests:
- name: saved_after_a_point_in_time
  function: json.value_matches
  parameter:
    dst: /home/user/data/settings.json
    key_path: window.lastSaved
    expected_value: '2026-01-01T10:30:00Z'
    comparison_type: greater
    timestamp_epoch: 1970
    timestamp_unit: ms
```

*a regex on every recent file* → PASSED

```yaml
tests:
- name: a_regex_on_every_recent_file
  function: json.value_matches
  parameter:
    dst: /home/user/data/settings.json
    key_path: recent_files
    expected_value: '\.odt$'
    regex_match: true
    wildcard_mode: all
```

*a time within the interval of an action* → PASSED. The times saved around the action bound the stored value.

```yaml
tests:
- name: a_time_within_the_interval_of_an_action
  function: json.value_matches
  parameter:
    dst: /home/user/data/settings.json
    key_path: window.lastSaved
    expected_value: !timestamp {after: '{{before_save}}', before: '{{after_save}}', epoch: 1970, unit: ms}
```

*an ordered comparison of text is an error* → ERROR. The test looked at the wrong field; it cannot fail.

```yaml
tests:
- name: an_ordered_comparison_of_text_is_an_error
  function: json.value_matches
  parameter:
    dst: /home/user/data/settings.json
    key_path: display.theme
    expected_value: 5
    comparison_type: greater
```

*a glob with several matches is an error* → ERROR

```yaml
tests:
- name: a_glob_with_several_matches_is_an_error
  function: json.value_matches
  parameter:
    dst: /home/user/data/profile-*.json
    key_path: display.theme
    expected_value: dark
```

*an invalid regex is an error* → ERROR

```yaml
tests:
- name: an_invalid_regex_is_an_error
  function: json.value_matches
  parameter:
    dst: /home/user/data/settings.json
    key_path: display.theme
    expected_value: '[unclosed'
    regex_match: true
```

## `json.values_compare`

compares two values of one JSON file (or of two files) as numbers or timestamps (earlier/later, within a tolerance, A = B + offset)

Pass when the value at `key_path` compares to the value at `other_key_path` (+ `offset`).

**Use for:** relations inside one file (or between two, `other_dst`): a last-saved value later than the first-opened one, two timestamps within a few seconds of each other, a counter one above another (`comparison_type: equals` with `offset: 1`). To compare one value with a constant use json.value_matches with `comparison_type`.

asserts: order, compare · formats: json · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Key paths into structured files (`key_path`), Ordered comparison of numbers and times (`ordered_comparison`), Text encodings (`encoding`), Decoding a stored value (value_decode) (`value_decode`), A second file (other_dst) (`other_dst`)

**Not for:**
- one value against a constant → `json.value_matches`
- two text values are equal → `json.value_matches`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the JSON file; a glob must match exactly one path. A missing file or invalid JSON is an error. `x.jsonlz4!` reads LZ4-compressed JSON. |
| **key_path** | `str` |  | Dot path of the first value (syntax as in json.value_matches). It must select exactly one value (a one-element array counts as its element): nothing fails, several values are an error. |
| **other_key_path** | `str` |  | Dot path of the second value; same rules. |
| comparison_type | `str` | `'equals'` | How the first value relates to the second: `equals` (default), `not_equals`, `greater`, `less`, `greater_equal` or `less_equal` (`less` = earlier for timestamps). Other values are an error. Allowed: `equals`, `not_equals`, `greater`, `less`, `greater_equal`, `less_equal`. |
| value_type | `str` | `'auto'` | `auto` (default; numbers if both are numbers, else timestamps), `number` or `timestamp`. A value that is no number or timestamp is an error. Allowed: `auto`, `number`, `timestamp`. |
| tolerance | `int \| float \| None` | `None` | Allowed difference for `equals`/`not_equals` (seconds for timestamps). |
| offset | `int \| float \| None` | `None` | Added to the second value before comparing (seconds for timestamps, may be negative; `'{{ name }}'` = a saved number): `first <comparison_type> second + offset`. |
| time_format | `str \| None` | `None` | `strptime` format of text timestamps on both sides; default ISO 8601 or RFC 2822. |
| timestamp_epoch | `int \| None` | `None` | Read numbers as a count since 1 January of `1970`, `1601` or `2001`. Allowed: `1970`, `1601`, `2001`. |
| timestamp_unit | `str \| None` | `None` | Unit of that count: `s` (default), `ms`, `us`, `ns` or `100ns`. Allowed: `s`, `ms`, `us`, `ns`, `100ns`. |
| utc_offset | `str \| None` | `None` | Zone of timestamps without one (`+02:00`); default UTC. |
| encoding | `str \| None` | `None` | `None` (default) detects UTF-8/16/32 with or without BOM; a name (`latin-1`) decodes BOM-less files with it. Unknown names are an error. |
| other_dst | `str \| None` | `None` | Guest path of a second file to read `other_key_path` from (same rules as `dst`, `archive!/member` included); default `None`: `dst`. A missing file is an error. Compares a file with a copy saved before an action. |
| value_decode | `list[str] \| str \| None` | `None` | Decode both values before comparing (steps as in json.value_matches). |
| decoded_key_path | `str \| None` | `None` | With `json` in `value_decode`: key path into the decoded value. |

**Outcomes:**
- PASSED: `first <comparison_type> second + offset` holds
- FAILED: the file was read and a side selects nothing, or the comparison does not hold
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the file is not valid JSON or cannot be decoded; an unknown `encoding`
- ERROR: a side selects several values
- ERROR: a value that is no number or timestamp, or a number compared with a timestamp
- ERROR: invalid parameters (`comparison_type`, `value_type`, `tolerance` with an order comparison, `timestamp_epoch`, ...)

**Limits:**
- Each side must select exactly one value (a one-element array counts as its element).
- Numbers and times only; two text values cannot be compared.

**Use cases:**
- A is earlier than B: A last-saved value later than the first-opened one, an end after a start (`comparison_type` `less` / `greater`).
- A within a few seconds of B: Two timestamps written by one action (`tolerance: 5`).
- A = B + n: A counter one above another (`offset: 1`), or a time a fixed interval after another (`offset` in seconds).

**Examples:**

*saved after opened* → PASSED

```yaml
tests:
- name: saved_after_opened
  function: json.values_compare
  parameter:
    dst: /home/user/data/session.json
    key_path: window.lastSaved
    other_key_path: window.opened
    comparison_type: greater
    timestamp_epoch: 1970
    timestamp_unit: ms
```

*saved one hour after opened* → PASSED

```yaml
tests:
- name: saved_one_hour_after_opened
  function: json.values_compare
  parameter:
    dst: /home/user/data/session.json
    key_path: window.lastSaved
    other_key_path: window.opened
    offset: 3600
    timestamp_epoch: 1970
    timestamp_unit: ms
```

*a counter one above another* → PASSED

```yaml
tests:
- name: a_counter_one_above_another
  function: json.values_compare
  parameter:
    dst: /home/user/data/session.json
    key_path: counters.next
    other_key_path: counters.last
    offset: 1
```

*a side that selects nothing fails* → FAILED

```yaml
tests:
- name: a_side_that_selects_nothing_fails
  function: json.values_compare
  parameter:
    dst: /home/user/data/session.json
    key_path: window.closed
    other_key_path: window.opened
    comparison_type: greater
```

*a side with several values is an error* → ERROR

```yaml
tests:
- name: a_side_with_several_values_is_an_error
  function: json.values_compare
  parameter:
    dst: /home/user/data/session.json
    key_path: groups[*].name
    other_key_path: window.opened
```
