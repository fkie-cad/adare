# YAML (`yaml.*`)

<!-- Generated; do not edit by hand. -->

YAML files read with PyYAML's safe loader: configuration and state files. The functions check that a key path exists, what its value is (also as a number or point in time), how many values a path selects (`0` = absent) and how two values of one file relate. A file with several documents (`---`) is a top-level list, one entry per document. Values keep their YAML 1.1 types; dates and timestamps become ISO 8601 strings, `!!binary` a lowercase hex string.

## `yaml.contains_key`

tests if a YAML file contains the specified key path (supports several documents)

Pass when `key_path` resolves to at least one value in YAML file `dst` (`null` counts).

**Use for:** checking that a settings/config file gained a key. To also check the value use yaml.value_matches; to check that a key is absent use yaml.value_count with `expected_count: 0` (or `expect_to_fail: true` here: a missing file stays an error).

asserts: exists · formats: yaml · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Key paths into structured files (`key_path`)

**Does not support:**
- Text encodings (`encoding`): There is no `encoding` parameter; files are read as UTF-8, or UTF-16 with a BOM.

**Not for:**
- the value of a key → `yaml.value_matches`
- a key or value is absent → `yaml.value_count`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the YAML file (read with `safe_load`; UTF-8, or UTF-16 with a BOM). A glob must match exactly one path; `archive.zip!/member.yaml` reads an archive member. A missing, unreadable or invalid file is an error. A file with several documents (`---`) is a top-level list, one per document; an empty file has no keys. |
| **key_path** | `str` |  | Dot path from the root, e.g. `display.font.size`. `*` expands all values of a mapping, `name[*]` all elements of sequence `name`, `name[0]` / `name[-1]` one element; a leading `[0]` / `[*]` addresses a top-level sequence or a document of a multi-document file (`[1].kind`, `[*].kind`). Keys with dots use quotes in brackets (`['app.window'].width`). |

**Outcomes:**
- PASSED: `key_path` selects at least one value (a `null` value counts)
- FAILED: the file was read and `key_path` selects nothing (an empty file has no keys)
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the content is not valid YAML (syntax error, unknown or unsafe tag, impossible date, undecodable bytes)

**Limits:**
- With `expect_to_fail: true` a missing key passes, but a missing file stays an error; yaml.value_count with `expected_count: 0` says the same more clearly.

**Use cases:**
- A setting was written: The key exists after the action, whatever its value.

**Examples:**

*nested key exists* → PASSED

```yaml
tests:
- name: nested_key_exists
  function: yaml.contains_key
  parameter:
    dst: /home/user/.config/app/config.yaml
    key_path: display.font.size
```

*a key in the second document* → PASSED

```yaml
tests:
- name: a_key_in_the_second_document
  function: yaml.contains_key
  parameter:
    dst: /home/user/.config/app/profiles.yaml
    key_path: '[1].name'
```

*a key that contains a dot* → PASSED

```yaml
tests:
- name: a_key_that_contains_a_dot
  function: yaml.contains_key
  parameter:
    dst: /home/user/.config/app/config.yaml
    key_path: "['app.window'].width"
```

*an absent key fails* → FAILED. To assert absence use yaml.value_count with `expected_count` 0, which passes.

```yaml
tests:
- name: an_absent_key_fails
  function: yaml.contains_key
  parameter:
    dst: /home/user/.config/app/config.yaml
    key_path: display.language
```

*invalid YAML is an error, not a failure* → ERROR

```yaml
tests:
- name: invalid_yaml_is_an_error_not_a_failure
  function: yaml.contains_key
  parameter:
    dst: /home/user/.config/app/config.yaml
    key_path: display.theme
```

*an unsafe tag is an error* → ERROR. The safe loader does not construct application objects.

```yaml
tests:
- name: an_unsafe_tag_is_an_error
  function: yaml.contains_key
  parameter:
    dst: /home/user/.config/app/config.yaml
    key_path: display
```

## `yaml.value_count`

tests how many YAML values exist at a key path, optionally only those matching a value (0 = absent)

Pass when the number of values at `key_path` in YAML file `dst` compares to `expected_count`.

**Use for:** counting entries (`recent[*]`, documents `[*]`) and asserting absence: `expected_count: 0` passes when the key path selects nothing (or nothing matches `expected_value`), while a missing or invalid file is still an error. A path that selects one sequence counts its elements when `expected_value` is given; without it every selected value counts once.

asserts: count, absent · formats: yaml · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Key paths into structured files (`key_path`), Counts with a comparison (`count_comparison`), Negative tests (absence) (`negative`), Regex values (!re) (`regex_tag`), Placeholders ({{ variable }}) (`placeholder`), Times as expected values (!timestamp) (`timestamp_tag`)

**Does not support:**
- Text encodings (`encoding`): There is no `encoding` parameter; files are read as UTF-8, or UTF-16 with a BOM.

**Not for:**
- what one value is → `yaml.value_matches`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the YAML file; a glob must match exactly one path. Several documents form a top-level list; an empty file has no values. |
| **key_path** | `str` |  | Dot path from the root (syntax as in yaml.contains_key). |
| **expected_count** | `int` |  | Non-negative integer to compare with. |
| expected_value | `str \| int \| float \| bool \| None` | `None` | Only count values equal to this (normalised as in yaml.value_matches). `None` (default) counts every value. |
| regex_match | `bool` | `False` | Treat a string `expected_value` as a regex searched in `str(value)`. |
| comparison_type | `str` | `'equals'` | `equals` (default), `greater`, `less`, `greater_equal` or `less_equal`. Other values are an error. Allowed: `equals`, `greater`, `less`, `greater_equal`, `less_equal`. |

**Outcomes:**
- PASSED: the number of values at `key_path` (only those matching `expected_value`, if given) satisfies `comparison_type`
- FAILED: the file was read and the count comparison does not hold
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the content is not valid YAML (syntax error, unknown or unsafe tag, impossible date, undecodable bytes)
- ERROR: a negative or non-integer `expected_count`; an unknown `comparison_type`
- ERROR: an invalid regex or unknown placeholder

**Limits:**
- Without `expected_value` every selected value counts once (a sequence is one value, `list[*]` counts its elements).
- With `expected_value` a path that selects exactly one sequence counts its matching elements.
- An empty file has no values.

**Use cases:**
- A key or value is absent: `expected_count: 0`.
- How many entries a list holds: Accounts, profiles, documents or recent items.

**Examples:**

*at least three recent items* → PASSED

```yaml
tests:
- name: at_least_three_recent_items
  function: yaml.value_count
  parameter:
    dst: /home/user/.config/app/config.yaml
    key_path: recent[*]
    expected_count: 3
    comparison_type: greater_equal
```

*two profile documents* → PASSED

```yaml
tests:
- name: two_profile_documents
  function: yaml.value_count
  parameter:
    dst: /home/user/.config/app/profiles.yaml
    key_path: '[*].kind'
    expected_value: Profile
    expected_count: 2
```

*a recent item was removed* → PASSED

```yaml
tests:
- name: a_recent_item_was_removed
  function: yaml.value_count
  parameter:
    dst: /home/user/.config/app/config.yaml
    key_path: recent
    expected_value: /home/user/d.txt
    expected_count: 0
```

*an empty file has no values* → PASSED

```yaml
tests:
- name: an_empty_file_has_no_values
  function: yaml.value_count
  parameter:
    dst: /home/user/.config/app/config.yaml
    key_path: display.theme
    expected_count: 0
```

*a different count fails* → FAILED

```yaml
tests:
- name: a_different_count_fails
  function: yaml.value_count
  parameter:
    dst: /home/user/.config/app/config.yaml
    key_path: servers[*]
    expected_count: 3
```

*a missing file is an error, never a pass* → ERROR

```yaml
tests:
- name: a_missing_file_is_an_error_never_a_pass
  function: yaml.value_count
  parameter:
    dst: /home/user/.config/app/other.yaml
    key_path: display.language
    expected_count: 0
```

## `yaml.value_matches`

tests if the YAML value at a key path matches the expected value (supports wildcards with any/all modes)

Pass when the YAML value at `key_path` in `dst` equals (or matches) `expected_value`.

With `comparison_type` (`greater`, `less`, ...), `tolerance` or the time parameters the value is compared as a number or timestamp; to compare two values of one file use yaml.values_compare.

**Use for:** asserting a setting/field value. If the path yields several values (a wildcard, or a sequence value, whose elements are then compared one by one) `wildcard_mode` decides. Values keep their YAML 1.1 types (`5` is an int, `true`/`yes`/`on` and `false`/`no`/`off` are booleans); dates and timestamps become ISO 8601 strings (`2024-01-15`, `2024-01-15T10:30:00`, `+00:00` for a `Z` zone), `!!binary` a lowercase hex string.

asserts: value, order · formats: yaml · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Key paths into structured files (`key_path`), Several matches (wildcard_mode) (`wildcard_mode`), Regex values (!re) (`regex_tag`), Placeholders ({{ variable }}) (`placeholder`), Times as expected values (!timestamp) (`timestamp_tag`), Ordered comparison of numbers and times (`ordered_comparison`)

**Does not support:**
- Text encodings (`encoding`): There is no `encoding` parameter; files are read as UTF-8, or UTF-16 with a BOM.

**Not for:**
- no value matches, a key is absent → `yaml.value_count`
- two values of one file relate (earlier, within seconds, one above) → `yaml.values_compare`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the YAML file; a glob must match exactly one path. Several documents form a top-level list. A missing or invalid file is an error; an unresolvable key path fails. |
| **key_path** | `str` |  | Dot path from the root (syntax as in yaml.contains_key), e.g. `servers[*].port` or `[0].kind` for the first document. |
| **expected_value** | `str \| int \| float \| bool \| None` |  | Compared with Python `==`, which is type-sensitive (`5` != `"5"`; `null` needs `null`). A `!re` tag (`re.match`) or `{{placeholder}}` compares `str(value)`. |
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
- PASSED: the value at `key_path` (`any`: one of the values, `all`: every value) matches `expected_value`
- FAILED: the file was read and `key_path` selects nothing or an empty sequence, or the value(s) do not match
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the content is not valid YAML (syntax error, unknown or unsafe tag, impossible date, undecodable bytes)
- ERROR: an invalid `wildcard_mode`; an invalid regex or unknown placeholder
- ERROR: in ordered mode, a `!re` tag, placeholder or `regex_match`, bad ordered parameters, or a value that is no number or timestamp

**Limits:**
- Equality is Python `==` and type-sensitive (`5` is not `"5"`; `null` needs `expected_value: null`).
- YAML 1.1 types apply (`yes` / `on` are `true`); dates and timestamps compare as ISO 8601 strings (`Z` becomes `+00:00`).
- A path that selects a sequence compares its elements one by one; a whole sequence cannot be compared.
- `regex_match` searches (`re.search`, unanchored); a `!re` tag matches from the start (`re.match`).

**Use cases:**
- A setting has a value: A setting changed in the GUI is stored in a YAML configuration.
- Every entry of a list has a property: `servers[*].port` with `wildcard_mode: all`.

**Examples:**

*every server uses one port* → PASSED

```yaml
tests:
- name: every_server_uses_one_port
  function: yaml.value_matches
  parameter:
    dst: /home/user/.config/app/config.yaml
    key_path: servers[*].port
    expected_value: 8080
    wildcard_mode: all
```

*a YAML 1.1 boolean* → PASSED. `autosave: yes` is the boolean `true`.

```yaml
tests:
- name: a_yaml_1_1_boolean
  function: yaml.value_matches
  parameter:
    dst: /home/user/.config/app/config.yaml
    key_path: autosave
    expected_value: true
```

*a timestamp as ISO 8601 text* → PASSED

```yaml
tests:
- name: a_timestamp_as_iso_8601_text
  function: yaml.value_matches
  parameter:
    dst: /home/user/.config/app/config.yaml
    key_path: session.opened
    expected_value: '2026-01-01T10:00:00+00:00'
```

*closed after a point in time* → PASSED

```yaml
tests:
- name: closed_after_a_point_in_time
  function: yaml.value_matches
  parameter:
    dst: /home/user/.config/app/config.yaml
    key_path: session.closed
    expected_value: '2026-01-01T10:15:00Z'
    comparison_type: greater
```

*one document is a settings document* → PASSED

```yaml
tests:
- name: one_document_is_a_settings_document
  function: yaml.value_matches
  parameter:
    dst: /home/user/.config/app/profiles.yaml
    key_path: '[*].kind'
    expected_value: Settings
```

*equality is type-sensitive* → FAILED. The file holds the number 12; the string `"12"` does not match.

```yaml
tests:
- name: equality_is_type_sensitive
  function: yaml.value_matches
  parameter:
    dst: /home/user/.config/app/config.yaml
    key_path: display.font.size
    expected_value: '12'
```

*a value from the run* → PASSED

```yaml
tests:
- name: a_value_from_the_run
  function: yaml.value_matches
  parameter:
    dst: /home/user/.config/app/config.yaml
    key_path: recent[*]
    expected_value: '{{ saved_file }}'
```

*an invalid regex is an error* → ERROR

```yaml
tests:
- name: an_invalid_regex_is_an_error
  function: yaml.value_matches
  parameter:
    dst: /home/user/.config/app/config.yaml
    key_path: display.theme
    expected_value: '[unclosed'
    regex_match: true
```

## `yaml.values_compare`

compares two values of one YAML file as numbers or timestamps (earlier/later, within a tolerance, A = B + offset)

Pass when the value at `key_path` compares to the value at `other_key_path` (+ `offset`).

**Use for:** relations inside one file: a last-saved value later than the first-opened one, two timestamps within a few seconds of each other, a counter one above another (`comparison_type: equals` with `offset: 1`). To compare one value with a constant use yaml.value_matches with `comparison_type`.

asserts: order, compare · formats: yaml · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Key paths into structured files (`key_path`), Ordered comparison of numbers and times (`ordered_comparison`)

**Does not support:**
- Text encodings (`encoding`): There is no `encoding` parameter; files are read as UTF-8, or UTF-16 with a BOM.

**Not for:**
- one value against a constant → `yaml.value_matches`
- two text values are equal → `yaml.value_matches`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the YAML file; a glob must match exactly one path. Several documents form a top-level list. A missing or invalid file is an error. |
| **key_path** | `str` |  | Dot path of the first value (syntax as in yaml.contains_key). It must select exactly one value (a one-element array counts as its element): nothing fails, several values are an error. |
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
- FAILED: the file was read and a side selects nothing, or the comparison does not hold
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the content is not valid YAML
- ERROR: a side selects several values
- ERROR: a value that is no number or timestamp, or a number compared with a timestamp
- ERROR: invalid parameters (`comparison_type`, `value_type`, `tolerance` with an order comparison, `timestamp_epoch`, ...)

**Limits:**
- Each side must select exactly one value (a one-element sequence counts as its element).
- Numbers and times only; two text values cannot be compared.

**Use cases:**
- A is earlier than B: A last-saved value later than the first-opened one, an end after a start (`comparison_type` `less` / `greater`).
- A within a few seconds of B: Two timestamps written by one action (`tolerance: 5`).
- A = B + n: A counter one above another (`offset: 1`), or a time a fixed interval after another (`offset` in seconds).

**Examples:**

*closed after opened* → PASSED

```yaml
tests:
- name: closed_after_opened
  function: yaml.values_compare
  parameter:
    dst: /home/user/.config/app/state.yaml
    key_path: session.closed
    other_key_path: session.opened
    comparison_type: greater
```

*closed within an hour of opening* → PASSED

```yaml
tests:
- name: closed_within_an_hour_of_opening
  function: yaml.values_compare
  parameter:
    dst: /home/user/.config/app/state.yaml
    key_path: session.closed
    other_key_path: session.opened
    tolerance: 3600
```

*a counter one above another* → PASSED

```yaml
tests:
- name: a_counter_one_above_another
  function: yaml.values_compare
  parameter:
    dst: /home/user/.config/app/state.yaml
    key_path: counters.next
    other_key_path: counters.last
    offset: 1
```

*a text value is an error* → ERROR

```yaml
tests:
- name: a_text_value_is_an_error
  function: yaml.values_compare
  parameter:
    dst: /home/user/.config/app/state.yaml
    key_path: display.theme
    other_key_path: session.opened
```
