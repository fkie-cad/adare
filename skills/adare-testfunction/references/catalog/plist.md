# Property list (plist) (`plist.*`)

<!-- Generated; do not edit by hand. -->

Property lists, XML or binary (the format is detected from the content), such as preference files: whether a key path exists, the value at a key path, how many values there are (`0` for absence) and two values of one file compared as numbers or times. `<date>` values are read as ISO 8601 strings in UTC without zone, `<data>` as lowercase hex.

## `plist.contains_key`

tests if a property list (XML or binary plist) contains the specified key path

Pass when `key_path` resolves to at least one value in property list `dst`.

**Use for:** checking that a preferences/settings plist gained a key. To also check the value use plist.value_matches; to check that a key is absent use plist.value_count with `expected_count: 0` (or `expect_to_fail: true` here: a missing file stays an error).

asserts: exists · formats: plist · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Key paths into structured files (`key_path`)

**Not for:**
- the value at the key path → `plist.value_matches`
- a key is absent → `plist.value_count`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the plist; XML and binary plists are detected from the content. A glob must match exactly one path; `archive.zip!/member.plist` reads an archive member. A missing, unreadable or invalid file is an error. |
| **key_path** | `str` |  | Dot path from the root dictionary, e.g. `window.frame`. Keys that contain dots use quotes in brackets (`['com.example.lastVersion']`, also mid-path: `recent['com.example.doc'].name`). `*` expands all values of a dictionary, `name[*]` all elements of array `name`, `name[0]` / `name[-1]` one element; a leading `[0]` / `[*]` addresses a top-level array. |

**Outcomes:**
- PASSED: `key_path` selects at least one value (an empty string or array counts)
- FAILED: the file was read and `key_path` selects nothing
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the content is no valid plist (malformed XML, corrupt binary plist, unknown element, unparsable value)

**Limits:**
- Keys with dots need quotes in brackets: `['com.example.lastVersion']`, also mid-path (`recent['com.example.doc'].name`).

**Use cases:**
- A preference was written: The key exists after the action, whatever its value.

**Examples:**

*a key with dots* → PASSED

```yaml
tests:
- name: a_key_with_dots
  function: plist.contains_key
  parameter:
    dst: /home/user/Library/Preferences/com.example.app.plist
    key_path: "['com.example.lastVersion']"
```

*a nested key in a binary plist* → PASSED

```yaml
tests:
- name: a_nested_key_in_a_binary_plist
  function: plist.contains_key
  parameter:
    dst: /home/user/Library/Preferences/com.example.app.plist
    key_path: window.width
```

*an absent key fails* → FAILED. To assert absence use plist.value_count with `expected_count` 0, which passes.

```yaml
tests:
- name: an_absent_key_fails
  function: plist.contains_key
  parameter:
    dst: /home/user/Library/Preferences/com.example.app.plist
    key_path: "['com.example.lastExport']"
```

*a file that is no plist is an error* → ERROR

```yaml
tests:
- name: a_file_that_is_no_plist_is_an_error
  function: plist.contains_key
  parameter:
    dst: /home/user/Library/Preferences/com.example.app.plist
    key_path: lastVersion
```

**Related:**
- `plist.value_count`: `expected_count: 0` for absence; `expect_to_fail` here works too, a missing file stays an error

## `plist.value_count`

tests how many property list values exist at a key path, optionally only those matching a value (0 = absent)

Pass when the number of values at `key_path` in plist `dst` compares to `expected_count`.

**Use for:** counting entries (`recent[*]`) and asserting absence: `expected_count: 0` passes when the key path selects nothing (or nothing matches `expected_value`), while a missing or invalid file is still an error. A path that selects one array counts its elements when `expected_value` is given; without it every selected value counts once.

asserts: count, absent · formats: plist · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Key paths into structured files (`key_path`), Counts with a comparison (`count_comparison`), Negative tests (absence) (`negative`), Regex values (!re) (`regex_tag`), Placeholders ({{ variable }}) (`placeholder`)

**Not for:**
- the value at a key path → `plist.value_matches`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the plist (XML or binary, detected from the content); a glob must match exactly one path. |
| **key_path** | `str` |  | Dot path from the root dictionary (syntax as in plist.contains_key). |
| **expected_count** | `int` |  | Non-negative integer to compare with. |
| expected_value | `str \| int \| float \| bool \| None` | `None` | Only count values equal to this (normalised as in plist.value_matches: dates are ISO strings, data is hex). `None` (default) counts every value. |
| regex_match | `bool` | `False` | Treat a string `expected_value` as a regex searched in `str(value)`. |
| comparison_type | `str` | `'equals'` | `equals` (default), `greater`, `less`, `greater_equal` or `less_equal`. Other values are an error. Allowed: `equals`, `greater`, `less`, `greater_equal`, `less_equal`. |

**Outcomes:**
- PASSED: the number of values at `key_path` (matching `expected_value`, if given) satisfies `comparison_type`
- FAILED: the file was read and the count comparison does not hold
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the content is no valid plist
- ERROR: a negative or non-integer `expected_count`, an unknown `comparison_type`, an invalid regex

**Limits:**
- Without `expected_value` every selected value counts once: `items` counts 1, `items[*]` the elements. With it, a path that selects one array counts its matching elements.
- `expected_value` is normalised and compared as in plist.value_matches (type-sensitive, dates as ISO strings, data as hex).

**Use cases:**
- A key or value is absent: `expected_count: 0` after a delete or clean-up action.
- How many entries a list holds: Recent items, accounts or bookmarks.

**Examples:**

*two recent documents* → PASSED

```yaml
tests:
- name: two_recent_documents
  function: plist.value_count
  parameter:
    dst: /home/user/Library/Preferences/com.example.app.plist
    key_path: "['com.example.recentDocuments'][*]"
    expected_count: 2
```

*a document is no longer in the recent list* → PASSED

```yaml
tests:
- name: a_document_is_no_longer_in_the_recent_list
  function: plist.value_count
  parameter:
    dst: /home/user/Library/Preferences/com.example.app.plist
    key_path: "['com.example.recentDocuments']"
    expected_value: /home/user/Documents/secret.txt
    expected_count: 0
```

*an absent key counts zero* → PASSED

```yaml
tests:
- name: an_absent_key_counts_zero
  function: plist.value_count
  parameter:
    dst: /home/user/Library/Preferences/com.example.app.plist
    key_path: "['com.example.lastExport']"
    expected_count: 0
```

*at least one text document* → PASSED

```yaml
tests:
- name: at_least_one_text_document
  function: plist.value_count
  parameter:
    dst: /home/user/Library/Preferences/com.example.app.plist
    key_path: "['com.example.recentDocuments']"
    expected_value: '\.txt$'
    regex_match: true
    expected_count: 1
    comparison_type: greater_equal
```

*a missing file is an error, not zero* → ERROR

```yaml
tests:
- name: a_missing_file_is_an_error_not_zero
  function: plist.value_count
  parameter:
    dst: /home/user/Library/Preferences/com.example.other.plist
    key_path: "['com.example.recentDocuments'][*]"
    expected_count: 0
```

**Related:**
- `json.value_count`: the same for JSON files

## `plist.value_matches`

tests if the property list value at a key path matches the expected value (dates as ISO strings, data as hex)

Pass when the plist value at `key_path` in `dst` equals (or matches) `expected_value`.

With `comparison_type` (`greater`, `less`, ...), `tolerance` or the time parameters the value is compared as a number or timestamp; to compare two values of one file use plist.values_compare.

**Use for:** asserting a preference value. If the path yields several values (a wildcard, or an array value, whose elements are then compared one by one) `wildcard_mode` decides. Values are normalised before comparing: `<date>` becomes an ISO 8601 string without zone (plist dates are UTC, `2024-01-15T10:30:00`), `<data>` a lowercase hex string (`0a1b`), `<integer>`/`<real>`/`<true/>` stay numbers and booleans.

asserts: value, order · formats: plist · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Key paths into structured files (`key_path`), Several matches (wildcard_mode) (`wildcard_mode`), Regex values (!re) (`regex_tag`), Placeholders ({{ variable }}) (`placeholder`), Times as expected values (!timestamp) (`timestamp_tag`), Ordered comparison of numbers and times (`ordered_comparison`)

**Not for:**
- a key or value is absent → `plist.value_count`
- two values of one file compared with each other → `plist.values_compare`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the plist (XML or binary, detected from the content); a glob must match exactly one path. A missing or invalid file is an error; an unresolvable key path fails. |
| **key_path** | `str` |  | Dot path from the root dictionary; `['com.example.key']` for keys with dots, `*` all values of a dictionary, `name[*]` / `name[0]` array elements, a leading `[0]` / `[*]` for a top-level array. |
| **expected_value** | `str \| int \| float \| bool \| None` |  | Compared with Python `==`, which is type-sensitive (`5` != `"5"`). A `!re` tag (`re.match`) or `{{placeholder}}` compares `str(value)`. |
| regex_match | `bool` | `False` | Treat a string `expected_value` as a regex searched (`re.search`, unanchored) in `str(value)`. An invalid regex is an error. |
| wildcard_mode | `str` | `'any'` | `any` (default): one value must match; `all`: every value must match. Other values are an error. Allowed: `any`, `all`. |
| comparison_type | `str` | `'equals'` | `equals` (default), `not_equals`, `greater`, `less`, `greater_equal` or `less_equal`. Anything but `equals`, or any parameter below, compares the value with `expected_value` as a number or point in time (ordered mode; `less` = earlier); a `!re` tag, `{{placeholder}}` or `regex_match` is then an error, and so is a value that is no number or timestamp. Allowed: `equals`, `not_equals`, `greater`, `less`, `greater_equal`, `less_equal`. |
| value_type | `str` | `'auto'` | `auto` (default; numbers if both sides are numbers, else timestamps), `number` or `timestamp`. Allowed: `auto`, `number`, `timestamp`. |
| tolerance | `int \| float \| None` | `None` | Allowed difference for `equals`/`not_equals` (seconds for timestamps). |
| time_format | `str \| None` | `None` | `strptime` format of text timestamps on both sides; default ISO 8601 or RFC 2822. |
| timestamp_epoch | `int \| None` | `None` | Read numbers as a count since 1 January of `1970`, `1601` or `2001`. Allowed: `1970`, `1601`, `2001`. |
| timestamp_unit | `str \| None` | `None` | Unit of that count: `s` (default), `ms`, `us`, `ns` or `100ns`. Allowed: `s`, `ms`, `us`, `ns`, `100ns`. |
| utc_offset | `str \| None` | `None` | Zone of timestamps without one (`+02:00`); default UTC. |

**Outcomes:**
- PASSED: the value at `key_path` (several: `any` one, or `all`) equals or matches `expected_value`
- FAILED: the file was read and `key_path` selects nothing or an empty array, or the value(s) do not match
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the content is no valid plist
- ERROR: an invalid regex or placeholder; an invalid `wildcard_mode`
- ERROR: in ordered mode, a value that is no number or timestamp, or a `!re` / placeholder / `regex_match` with it
- ERROR: bad ordered parameters (`comparison_type`, `value_type`, `timestamp_epoch`, ...)

**Limits:**
- Equality is Python `==` and type-sensitive: `41` is not `'41'`. `!re`, placeholders and `regex_match` compare `str(value)`.
- `<date>` is an ISO 8601 string without zone (UTC): `2024-01-15T10:30:00`; `<data>` is lowercase hex (`000102`); integers, reals and booleans stay numbers and booleans.
- A path that selects one array compares its elements one by one.

**Use cases:**
- A preference has a value: A setting changed in the GUI, a recent file path, a date of last use.

**Examples:**

*window width* → PASSED

```yaml
tests:
- name: window_width
  function: plist.value_matches
  parameter:
    dst: /home/user/Library/Preferences/com.example.app.plist
    key_path: window.width
    expected_value: 1280
```

*a date as ISO string* → PASSED

```yaml
tests:
- name: a_date_as_iso_string
  function: plist.value_matches
  parameter:
    dst: /home/user/Library/Preferences/com.example.app.plist
    key_path: "['com.example.lastLaunch']"
    expected_value: '2024-01-15T10:30:00'
```

*data as hex* → PASSED

```yaml
tests:
- name: data_as_hex
  function: plist.value_matches
  parameter:
    dst: /home/user/Library/Preferences/com.example.app.plist
    key_path: token
    expected_value: '000102'
```

*a recent document by regex* → PASSED. The path selects an array, so each element is compared; `any` passes on one.

```yaml
tests:
- name: a_recent_document_by_regex
  function: plist.value_matches
  parameter:
    dst: /home/user/Library/Preferences/com.example.app.plist
    key_path: "['com.example.recentDocuments']"
    expected_value: 'report\.txt$'
    regex_match: true
```

*launched after a point in time* → PASSED

```yaml
tests:
- name: launched_after_a_point_in_time
  function: plist.value_matches
  parameter:
    dst: /home/user/Library/Preferences/com.example.app.plist
    key_path: "['com.example.lastLaunch']"
    expected_value: '2024-01-01T00:00:00Z'
    comparison_type: greater
```

*a value in a binary plist* → PASSED

```yaml
tests:
- name: a_value_in_a_binary_plist
  function: plist.value_matches
  parameter:
    dst: /home/user/Library/Preferences/com.example.app.plist
    key_path: launchCount
    expected_value: 41
```

*launched during the action* → PASSED. The two times are saved with `save_timestamp` before and after the action.

```yaml
tests:
- name: launched_during_the_action
  function: plist.value_matches
  parameter:
    dst: /home/user/Library/Preferences/com.example.app.plist
    key_path: "['com.example.lastLaunch']"
    expected_value: !timestamp {after: '{{before_launch}}', before: '{{after_launch}}'}
```

*a number is not its text* → FAILED. `launchCount` is an integer; the string `'41'` does not equal it.

```yaml
tests:
- name: a_number_is_not_its_text
  function: plist.value_matches
  parameter:
    dst: /home/user/Library/Preferences/com.example.app.plist
    key_path: launchCount
    expected_value: '41'
```

*an absent key fails* → FAILED

```yaml
tests:
- name: an_absent_key_fails
  function: plist.value_matches
  parameter:
    dst: /home/user/Library/Preferences/com.example.app.plist
    key_path: "['com.example.lastExport']"
    expected_value: /home/user/Documents/report.pdf
```

*an invalid regex is an error* → ERROR

```yaml
tests:
- name: an_invalid_regex_is_an_error
  function: plist.value_matches
  parameter:
    dst: /home/user/Library/Preferences/com.example.app.plist
    key_path: "['com.example.recentDocuments']"
    expected_value: 'report(\.txt'
    regex_match: true
```

**Related:**
- `json.value_matches`: the same for JSON files

## `plist.values_compare`

compares two values of one property list file as numbers or timestamps (earlier/later, within a tolerance, A = B + offset)

Pass when the value at `key_path` compares to the value at `other_key_path` (+ `offset`).

**Use for:** relations inside one file: a last-saved value later than the first-opened one, two timestamps within a few seconds of each other, a counter one above another (`comparison_type: equals` with `offset: 1`). To compare one value with a constant use plist.value_matches with `comparison_type`.

asserts: compare, order · formats: plist · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Key paths into structured files (`key_path`), Ordered comparison of numbers and times (`ordered_comparison`)

**Does not support:**
- Several matches (wildcard_mode) (`wildcard_mode`): Each key path must select exactly one value (a one-element array counts as its element); several are an error.
- Regex values (!re) (`regex_tag`): Values compare as numbers or times only; test text with plist.value_matches.

**Not for:**
- one value against a constant → `plist.value_matches`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the plist (XML or binary, detected from the content); a glob must match exactly one path. A missing or invalid file is an error. `<date>` values are UTC. |
| **key_path** | `str` |  | Dot path of the first value (syntax as in plist.contains_key). It must select exactly one value (a one-element array counts as its element): nothing fails, several values are an error. |
| **other_key_path** | `str` |  | Dot path of the second value; same rules. |
| comparison_type | `str` | `'equals'` | How the first value relates to the second: `equals` (default), `not_equals`, `greater`, `less`, `greater_equal` or `less_equal` (`less` = earlier for timestamps). Other values are an error. Allowed: `equals`, `not_equals`, `greater`, `less`, `greater_equal`, `less_equal`. |
| value_type | `str` | `'auto'` | `auto` (default; numbers if both are numbers, else timestamps), `number` or `timestamp`. A value that is no number or timestamp is an error. Allowed: `auto`, `number`, `timestamp`. |
| tolerance | `int \| float \| None` | `None` | Allowed difference for `equals`/`not_equals` (seconds for timestamps). |
| offset | `int \| float \| None` | `None` | Added to the second value before comparing (seconds for timestamps, may be negative): `first <comparison_type> second + offset`. |
| time_format | `str \| None` | `None` | `strptime` format of text timestamps on both sides; default ISO 8601 or RFC 2822. |
| timestamp_epoch | `int \| None` | `None` | Read numbers as a count since 1 January of `1970`, `1601` or `2001`. Allowed: `1970`, `1601`, `2001`. |
| timestamp_unit | `str \| None` | `None` | Unit of that count: `s` (default), `ms`, `us`, `ns` or `100ns`. Allowed: `s`, `ms`, `us`, `ns`, `100ns`. |
| utc_offset | `str \| None` | `None` | Zone of timestamps without one (`+02:00`); default UTC. |

**Outcomes:**
- PASSED: `first <comparison_type> second + offset` holds
- FAILED: the file was read and a key path selects nothing, or the comparison does not hold
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the content is no valid plist
- ERROR: a key path selects several values
- ERROR: a value is no number or timestamp, or one is a number and the other a timestamp
- ERROR: bad parameters (`comparison_type`, `value_type`, `tolerance` with an order comparison, `timestamp_epoch`, ...)

**Limits:**
- `<date>` values are UTC.

**Use cases:**
- A is earlier than B: A last-saved value later than the first-opened one, an end after a start (`comparison_type` `less` / `greater`).
- A within a few seconds of B: Two timestamps written by one action (`tolerance: 5`).
- A = B + n: A counter one above another (`offset: 1`), or a time a fixed interval after another (`offset` in seconds).

**Examples:**

*saved after launch* → PASSED

```yaml
tests:
- name: saved_after_launch
  function: plist.values_compare
  parameter:
    dst: /home/user/Library/Preferences/com.example.app.plist
    key_path: "['com.example.lastSave']"
    other_key_path: "['com.example.lastLaunch']"
    comparison_type: greater_equal
```

*saved within five minutes of launch* → PASSED

```yaml
tests:
- name: saved_within_five_minutes_of_launch
  function: plist.values_compare
  parameter:
    dst: /home/user/Library/Preferences/com.example.app.plist
    key_path: "['com.example.lastSave']"
    other_key_path: "['com.example.lastLaunch']"
    tolerance: 300
```

*one save more than launches* → PASSED

```yaml
tests:
- name: one_save_more_than_launches
  function: plist.values_compare
  parameter:
    dst: /home/user/Library/Preferences/com.example.app.plist
    key_path: saveCount
    other_key_path: launchCount
    offset: 1
```

*a missing side fails* → FAILED

```yaml
tests:
- name: a_missing_side_fails
  function: plist.values_compare
  parameter:
    dst: /home/user/Library/Preferences/com.example.app.plist
    key_path: printCount
    other_key_path: launchCount
```

*a side with several values is an error* → ERROR

```yaml
tests:
- name: a_side_with_several_values_is_an_error
  function: plist.values_compare
  parameter:
    dst: /home/user/Library/Preferences/com.example.app.plist
    key_path: window.*
    other_key_path: launchCount
    comparison_type: greater
```
