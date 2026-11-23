# INI (`ini.*`)

<!-- Generated; do not edit by hand. -->

INI-style configuration and key files, read with a tolerant line parser that keeps what applications actually write (duplicate sections and keys, keys before the first section, raw values): whether a section or key exists, the value of a key and how often a key or value occurs (`0` for absence).

## `ini.contains_key`

tests if an INI file contains a key in a section

Pass when `section` of the INI file `dst` has a `key = ...` line (an empty value counts).

**Use for:** checking a setting was written, whatever its value. For "absent" use ini.value_count with `expected_count: 0`.

asserts: exists · formats: ini · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Text encodings (`encoding`)

**Not for:**
- the value of the key → `ini.value_matches`
- a key is absent → `ini.value_count`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the INI file; a glob must match exactly one path. A missing, unreadable or undecodable file is an error. |
| **section** | `str` |  | Section name without brackets; `''` = keys before the first header. Duplicate sections are searched together. |
| **key** | `str` |  | Key name, compared after stripping. The first `=` on a line splits key and value; lines without `=` are ignored, so a bare word is not a key. |
| case_sensitive | `bool` | `True` | `False` compares section and key names case-insensitively. |
| encoding | `str` | `None` | Text encoding; default auto: a BOM wins, BOM-less UTF-16 is recognised, everything else is read as UTF-8. An unknown name is an error. |

**Outcomes:**
- PASSED: `section` has a `key = ...` line (an empty value counts; the details show the first value)
- FAILED: the file was read and the section has no such key
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the file cannot be read or decoded; an unknown `encoding`

**Limits:**
- The first `=` on a line splits key and value; a line without `=` is ignored, so a bare word is no key.
- A section that appears twice is searched as one.
- `case_sensitive: false` compares section and key names case-insensitively.

**Use cases:**
- A setting was written: The key exists after the action, whatever its value.

**Examples:**

*a key written without spaces* → PASSED

```yaml
tests:
- name: a_key_written_without_spaces
  function: ini.contains_key
  parameter:
    dst: /home/user/.config/app/settings.ini
    section: General
    key: last_opened
```

*a key before the first section* → PASSED

```yaml
tests:
- name: a_key_before_the_first_section
  function: ini.contains_key
  parameter:
    dst: /home/user/.config/app/settings.ini
    section: ''
    key: profile
```

*a UTF-16 file on Windows* → PASSED. The byte order mark selects the encoding; no `encoding` parameter needed.

```yaml
tests:
- name: a_utf_16_file_on_windows
  function: ini.contains_key
  parameter:
    dst: C:\Users\user\AppData\Roaming\App\settings.ini
    section: General
    key: language
```

*a bare word is no key* → FAILED. `maximized` has no `=`, so the parser ignores the line.

```yaml
tests:
- name: a_bare_word_is_no_key
  function: ini.contains_key
  parameter:
    dst: /home/user/.config/app/settings.ini
    section: Window
    key: maximized
```

**Related:**
- `ini.section_exists`: only the section

## `ini.section_exists`

tests if an INI file contains a section

Pass when the INI file `dst` has at least one `[section]` header.

**Use for:** checking a settings file gained a section. For "absent" use `expect_to_fail` (or ini.value_count with `expected_count: 0` for a key).

asserts: exists · formats: ini · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Text encodings (`encoding`)

**Not for:**
- a key in the section → `ini.contains_key`
- a key is absent → `ini.value_count`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the INI file; a glob must match exactly one path. A missing, unreadable or undecodable file is an error. |
| **section** | `str` |  | Section name without brackets, compared after stripping. Keys before the first header belong to section `''`, which exists only as a header `[]`. |
| case_sensitive | `bool` | `True` | `False` compares section names case-insensitively. |
| encoding | `str` | `None` | Text encoding; default auto: a BOM wins, BOM-less UTF-16 is recognised, everything else is read as UTF-8. An unknown name is an error. |

**Outcomes:**
- PASSED: the file has at least one `[section]` header with that name
- FAILED: the file was read and has no such header (the details list the sections found)
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the file cannot be read or decoded; an unknown `encoding`

**Limits:**
- The name is compared after stripping; a comment after the closing bracket is allowed (`[Window] ; geometry`).
- Keys before the first header belong to section `''`, which exists here only as a header `[]`.
- For an absent section use `expect_to_fail`; a missing or unreadable file stays an error.

**Use cases:**
- A group of settings was created: A section for a new account, profile or recent file list.

**Examples:**

*section with a comment after the header* → PASSED

```yaml
tests:
- name: section_with_a_comment_after_the_header
  function: ini.section_exists
  parameter:
    dst: /home/user/.config/app/settings.ini
    section: Window
```

*case-insensitive name* → PASSED

```yaml
tests:
- name: case_insensitive_name
  function: ini.section_exists
  parameter:
    dst: /home/user/.config/app/settings.ini
    section: general
    case_sensitive: false
```

*an absent section fails* → FAILED

```yaml
tests:
- name: an_absent_section_fails
  function: ini.section_exists
  parameter:
    dst: /home/user/.config/app/settings.ini
    section: Accounts
```

*a missing file is an error* → ERROR

```yaml
tests:
- name: a_missing_file_is_an_error
  function: ini.section_exists
  parameter:
    dst: /home/user/.config/app/other.ini
    section: General
```

**Related:**
- `ini.value_count`: how often a key occurs in the section (`0` for absence)

## `ini.value_count`

tests the number of occurrences of an INI key (optionally with a matching value)

Pass when the number of `key` lines in `section` (whose value matches `expected_value`, if given) satisfies `comparison_type` against `expected_count`.

**Use for:** duplicate keys (lists written as repeated keys) and absence: `expected_count: 0` asserts the key (or the key with that value) is not in the section.

asserts: count, absent · formats: ini · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Text encodings (`encoding`), Counts with a comparison (`count_comparison`), Negative tests (absence) (`negative`), Regex values (!re) (`regex_tag`), Placeholders ({{ variable }}) (`placeholder`)

**Not for:**
- the value of a key → `ini.value_matches`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the INI file; a glob must match exactly one path. A missing, unreadable or undecodable file is an error. |
| **section** | `str` |  | Section name without brackets; `''` = keys before the first header. Occurrences in duplicate sections are added up. |
| **key** | `str` |  | Key name; the first `=` on a line splits key and value. |
| **expected_count** | `int` |  | Required non-negative integer to compare against; anything else is an error. |
| expected_value | `str \| int \| float \| bool \| None` | `None` | Count only occurrences whose raw value equals/matches this (same rules as ini.value_matches); `None` (default) counts every occurrence. |
| regex_match | `bool` | `False` | Search `expected_value` as a Python regex (`re.search`, unanchored). |
| comparison_type | `str` | `'equals'` | `equals` (default), `greater`, `less`, `greater_equal` or `less_equal`; other values are an error. Allowed: `equals`, `greater`, `less`, `greater_equal`, `less_equal`. |
| case_sensitive | `bool` | `True` | `False` compares section and key names case-insensitively. |
| encoding | `str` | `None` | Text encoding; default auto (BOM, BOM-less UTF-16, else UTF-8). |

**Outcomes:**
- PASSED: the number of `key` lines in `section` (matching `expected_value`, if given) satisfies `comparison_type`
- FAILED: the file was read and the count comparison does not hold
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the file cannot be read or decoded; an unknown `encoding`
- ERROR: a negative or non-integer `expected_count`, an unknown `comparison_type`, an invalid regex

**Limits:**
- Occurrences in every copy of a duplicate section are added up.
- `expected_value` follows the rules of ini.value_matches (raw text, numbers as text).

**Use cases:**
- A setting is absent: `expected_count: 0` without `expected_value`: the key is not in the section.
- An entry was removed from a list: `expected_count: 0` with `expected_value`: no `file = ...` line has that path.
- Duplicate keys: Key files that repeat a key (recent file lists) keep every occurrence.

**Examples:**

*three recent files in two copies of the section* → PASSED

```yaml
tests:
- name: three_recent_files_in_two_copies_of_the_section
  function: ini.value_count
  parameter:
    dst: /home/user/.config/app/settings.ini
    section: RecentFiles
    key: file
    expected_count: 3
```

*a file is no longer in the recent list* → PASSED

```yaml
tests:
- name: a_file_is_no_longer_in_the_recent_list
  function: ini.value_count
  parameter:
    dst: /home/user/.config/app/settings.ini
    section: RecentFiles
    key: file
    expected_value: /home/user/Documents/secret.txt
    expected_count: 0
```

*the key is absent* → PASSED

```yaml
tests:
- name: the_key_is_absent
  function: ini.value_count
  parameter:
    dst: /home/user/.config/app/settings.ini
    section: General
    key: proxy
    expected_count: 0
```

*a wrong count fails* → FAILED

```yaml
tests:
- name: a_wrong_count_fails
  function: ini.value_count
  parameter:
    dst: /home/user/.config/app/settings.ini
    section: RecentFiles
    key: file
    expected_count: 2
```

*a negative count is an error* → ERROR

```yaml
tests:
- name: a_negative_count_is_an_error
  function: ini.value_count
  parameter:
    dst: /home/user/.config/app/settings.ini
    section: RecentFiles
    key: file
    expected_count: -1
```

## `ini.value_matches`

tests if an INI value equals or matches an expected value (regex and placeholders supported)

Pass when the value of `key` in `section` of `dst` equals (or matches) `expected_value`.

With `comparison_type` (`greater`, `less`, ...), `tolerance` or the time parameters the value is compared as a number or timestamp.

**Use for:** asserting a setting's value. With duplicate keys or sections, one matching occurrence is enough (`wildcard_mode: all`: every occurrence must match). A missing key fails.

asserts: value, order · formats: ini · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Text encodings (`encoding`), Several matches (wildcard_mode) (`wildcard_mode`), Regex values (!re) (`regex_tag`), Placeholders ({{ variable }}) (`placeholder`), Times as expected values (!timestamp) (`timestamp_tag`), Ordered comparison of numbers and times (`ordered_comparison`)

**Not for:**
- a key or value is absent → `ini.value_count`
- only that the key exists, whatever its value → `ini.contains_key`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the INI file; a glob must match exactly one path. A missing, unreadable or undecodable file is an error. |
| **section** | `str` |  | Section name without brackets; `''` = keys before the first header. |
| **key** | `str` |  | Key name; the first `=` on a line splits key and value. |
| **expected_value** | `str \| int \| float \| bool` |  | Compared with the raw value text (stripped; quotes and inline comments are kept, `a = "x" ; note` has the value `"x" ; note`). A YAML number or boolean is compared as its text (`8080`, `true`/`false`). A `!re`/`!timestamp` tag or `{{placeholder}}` is matched by type. |
| regex_match | `bool` | `False` | Search `expected_value` as a Python regex (`re.search`, unanchored). An invalid regex is an error. |
| case_sensitive | `bool` | `True` | `False` compares section and key names case-insensitively; values are always compared as given. |
| encoding | `str` | `None` | Text encoding; default auto (BOM, BOM-less UTF-16, else UTF-8). |
| wildcard_mode | `str` | `'any'` | With several occurrences, `any` (default): one must match; `all`: every one must match. Other values are an error. Allowed: `any`, `all`. |
| comparison_type | `str` | `'equals'` | `equals` (default), `not_equals`, `greater`, `less`, `greater_equal` or `less_equal`. Anything but `equals`, or any parameter below, compares the value with `expected_value` as a number or point in time (ordered mode; `less` = earlier); a `!re` tag, `{{placeholder}}` or `regex_match` is then an error, and so is a value that is no number or timestamp. Allowed: `equals`, `not_equals`, `greater`, `less`, `greater_equal`, `less_equal`. |
| value_type | `str` | `'auto'` | `auto` (default; numbers if both sides are numbers, else timestamps), `number` or `timestamp`. Allowed: `auto`, `number`, `timestamp`. |
| tolerance | `int \| float \| None` | `None` | Allowed difference for `equals`/`not_equals` (seconds for timestamps). |
| time_format | `str \| None` | `None` | `strptime` format of text timestamps on both sides; default ISO 8601 or RFC 2822. |
| timestamp_epoch | `int \| None` | `None` | Read numbers as a count since 1 January of `1970`, `1601` or `2001`. Allowed: `1970`, `1601`, `2001`. |
| timestamp_unit | `str \| None` | `None` | Unit of that count: `s` (default), `ms`, `us`, `ns` or `100ns`. Allowed: `s`, `ms`, `us`, `ns`, `100ns`. |
| utc_offset | `str \| None` | `None` | Zone of timestamps without one (`+02:00`); default UTC. |

**Outcomes:**
- PASSED: the value of `key` (several occurrences: `any` one, or `all`) equals or matches `expected_value`
- FAILED: the file was read and the key is missing or no occurrence (`all`, not every one) matches; the details list the non-matching values with line numbers
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the file cannot be read or decoded; an unknown `encoding`
- ERROR: an invalid regex or placeholder; an invalid `wildcard_mode`
- ERROR: in ordered mode, a value that is no number or timestamp, or a `!re` / placeholder / `regex_match` with it
- ERROR: bad ordered parameters (`comparison_type`, `value_type`, `timestamp_epoch`, ...)

**Limits:**
- Values are raw text, stripped: quotes, inline comments and `%(name)s` stay (`title = "Report" ; draft` has the value `"Report" ; draft`). No continuation lines.
- A YAML number or boolean is compared as its text (`8080`, `true` / `false`).
- `case_sensitive` applies to section and key names; values are always compared as given (use `regex_match` with `(?i)`).
- Occurrences in duplicate sections and duplicate keys are all compared.

**Use cases:**
- A setting has a value: A language, port or path after it was changed in the GUI.
- A recent file list: Repeated keys (`file = ...`) where one or every entry must match.

**Examples:**

*language setting* → PASSED

```yaml
tests:
- name: language_setting
  function: ini.value_matches
  parameter:
    dst: /home/user/.config/app/settings.ini
    section: General
    key: language
    expected_value: de_DE
```

*a number compares as its text* → PASSED

```yaml
tests:
- name: a_number_compares_as_its_text
  function: ini.value_matches
  parameter:
    dst: /home/user/.config/app/settings.ini
    section: General
    key: port
    expected_value: 8080
```

*quotes and inline comments are part of the value* → PASSED

```yaml
tests:
- name: quotes_and_inline_comments_are_part_of_the_value
  function: ini.value_matches
  parameter:
    dst: /home/user/.config/app/settings.ini
    section: General
    key: title
    expected_value: '"Report" ; draft'
```

*one recent file, also in the repeated section* → PASSED

```yaml
tests:
- name: one_recent_file_also_in_the_repeated_section
  function: ini.value_matches
  parameter:
    dst: /home/user/.config/app/settings.ini
    section: RecentFiles
    key: file
    expected_value: 'plan\.txt$'
    regex_match: true
```

*every recent file under Documents* → PASSED

```yaml
tests:
- name: every_recent_file_under_documents
  function: ini.value_matches
  parameter:
    dst: /home/user/.config/app/settings.ini
    section: RecentFiles
    key: file
    expected_value: '^/home/user/Documents/'
    regex_match: true
    wildcard_mode: all
```

*a settings file inside a backup archive* → PASSED

```yaml
tests:
- name: a_settings_file_inside_a_backup_archive
  function: ini.value_matches
  parameter:
    dst: /home/user/backup.zip!/settings.ini
    section: General
    key: language
    expected_value: de_DE
```

*port above a number* → PASSED

```yaml
tests:
- name: port_above_a_number
  function: ini.value_matches
  parameter:
    dst: /home/user/.config/app/settings.ini
    section: General
    key: port
    expected_value: 1024
    comparison_type: greater
```

*last opened file by regex tag* → PASSED

```yaml
tests:
- name: last_opened_file_by_regex_tag
  function: ini.value_matches
  parameter:
    dst: /home/user/.config/app/settings.ini
    section: General
    key: last_opened
    expected_value: !re '/home/user/Documents/.*\.txt$'
```

*not every recent file matches* → FAILED

```yaml
tests:
- name: not_every_recent_file_matches
  function: ini.value_matches
  parameter:
    dst: /home/user/.config/app/settings.ini
    section: RecentFiles
    key: file
    expected_value: 'report\.txt$'
    regex_match: true
    wildcard_mode: all
```

*an absent key fails* → FAILED. To assert absence use ini.value_count with `expected_count` 0, which passes.

```yaml
tests:
- name: an_absent_key_fails
  function: ini.value_matches
  parameter:
    dst: /home/user/.config/app/settings.ini
    section: General
    key: theme
    expected_value: dark
```

*an unknown encoding is an error* → ERROR

```yaml
tests:
- name: an_unknown_encoding_is_an_error
  function: ini.value_matches
  parameter:
    dst: /home/user/.config/app/settings.ini
    section: General
    key: language
    expected_value: de_DE
    encoding: utf-99
```
