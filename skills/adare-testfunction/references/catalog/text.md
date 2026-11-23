# Text (`text.*`)

<!-- Generated; do not edit by hand. -->

Counts content in any file: occurrences of a string or byte sequence in the raw bytes (binary files included, in one or several encodings at once), and lines of a text file that contain a string or match a regex. Absence is `expected_count: 0`; a missing, unreadable or undecodable file is an error, never a pass.

## `text.line_count`

tests the number of text lines that contain a string or match a regex

Pass when the number of lines of text file `dst` containing `content` satisfies `comparison_type`.

**Use for:** counting log or history entries (exactly 2 lines with a file name); asserting a line is gone: `expected_count: 0`. For binary files use text.occurrence_count.

asserts: count, absent, content · formats: text · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Counts with a comparison (`count_comparison`), Text encodings (`encoding`), Negative tests (absence) (`negative`), Placeholders ({{ variable }}) (`placeholder`)

**Does not support:**
- Regex values (!re) (`regex_tag`): A `!re` in `content` is an error; write the pattern as a plain string with `regex_match: true`.
- Times as expected values (!timestamp) (`timestamp_tag`): A `!timestamp` in `content` is an error.

**Not for:**
- occurrences in a binary file or in several encodings at once → `text.occurrence_count`
- CSV records (a quoted field with a line break is one record) → `csv.row_count`
- JSON Lines records that meet conditions → `jsonl.line_count`
- a trace in the last lines of a plain-text log → `linux.log_entry_exists`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the text file; a glob must match exactly one path. A missing file or content not valid in the encoding is an error; an empty file has 0 lines. Lines end at `\n`, `\r\n` or `\r`. |
| **content** | `str` |  | Substring a line must contain (see `case_sensitive`); an empty string counts every line. With `regex_match` a regex searched in each line (`re.search`); an invalid regex is an error. A `!re` or `!timestamp` placeholder is an error: write the pattern with `regex_match`. |
| **expected_count** | `int` |  | Non-negative integer to compare against; anything else is an error. |
| comparison_type | `str` | `'equals'` | `equals` (default), `greater`, `less`, `greater_equal` or `less_equal`; other values are an error. Allowed: `equals`, `greater`, `less`, `greater_equal`, `less_equal`. |
| encoding | `str \| None` | `None` | Text encoding; `None` (default) detects a BOM (UTF-8/16/32) and BOM-less UTF-16, else reads UTF-8. A BOM always wins. Unknown names are an error. |
| regex_match | `bool` | `False` | Treat `content` as a regex (see `content`). |
| case_sensitive | `bool` | `True` | `True` (default) matches case exactly. `False` compares the substring after casefolding line and `content` (`Report` = `REPORT`, sharp s = `ss`), or compiles the regex with `re.IGNORECASE`. A non-boolean is an error. |

**Outcomes:**
- PASSED: the number of lines that contain (or match) `content` satisfies `comparison_type`
- FAILED: the file was read and the count comparison does not hold
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the file cannot be read, is larger than the read cap or is not valid in the encoding
- ERROR: an unknown encoding; an invalid regex; a `!re` / `!timestamp` tag or unknown placeholder in `content`
- ERROR: a negative or non-integer `expected_count`; an unknown `comparison_type`; a non-boolean `case_sensitive`

**Limits:**
- Lines end at `\n`, `\r\n` or `\r`; an empty file has 0 lines; an empty `content` counts every line.
- Without `encoding` a BOM selects UTF-8/16/32, BOM-less UTF-16 is detected from its zero bytes, else UTF-8. A BOM always wins.
- A line with several matches counts once.
- `case_sensitive: false` casefolds line and `content` (sharp s = `ss`), or compiles the regex with `re.IGNORECASE`.

**Use cases:**
- Log or history entries: Exactly two lines that record a deletion.
- A line is gone: `expected_count: 0` after a clean-up action.

**Examples:**

*two deletions logged* → PASSED

```yaml
tests:
- name: two_deletions_logged
  function: text.line_count
  parameter:
    dst: /home/user/app/app.log
    content: 'deleted: .*report'
    regex_match: true
    expected_count: 2
```

*entry removed from the history* → PASSED

```yaml
tests:
- name: entry_removed_from_the_history
  function: text.line_count
  parameter:
    dst: /home/user/app/app.log
    content: secret-project
    expected_count: 0
```

*errors in any case* → PASSED

```yaml
tests:
- name: errors_in_any_case
  function: text.line_count
  parameter:
    dst: /home/user/app/app.log
    content: error
    case_sensitive: false
    expected_count: 1
```

*a case-sensitive search misses other cases* → FAILED

```yaml
tests:
- name: a_case_sensitive_search_misses_other_cases
  function: text.line_count
  parameter:
    dst: /home/user/app/app.log
    content: error
    expected_count: 1
```

*a UTF-16 file with BOM is detected* → PASSED

```yaml
tests:
- name: a_utf_16_file_with_bom_is_detected
  function: text.line_count
  parameter:
    dst: /home/user/app/history.txt
    content: opened
    expected_count: 2
```

*a log member of a compressed archive* → PASSED

```yaml
tests:
- name: a_log_member_of_a_compressed_archive
  function: text.line_count
  parameter:
    dst: /home/user/backup/logs.tar.gz!/var/log/app.log
    content: opened
    expected_count: 1
```

*content not valid UTF-8 is an error* → ERROR

```yaml
tests:
- name: content_not_valid_utf_8_is_an_error
  function: text.line_count
  parameter:
    dst: /home/user/app/app.log
    content: ok
    expected_count: 1
```

*an invalid regex is an error* → ERROR

```yaml
tests:
- name: an_invalid_regex_is_an_error
  function: text.line_count
  parameter:
    dst: /home/user/app/app.log
    content: 'deleted: ('
    regex_match: true
    expected_count: 0
```

## `text.occurrence_count`

tests how often a string or byte sequence occurs in a (text or binary) file

Pass when the number of non-overlapping occurrences of `content` in `dst` satisfies `comparison_type`.

**Use for:** how many times a word or value appears in any file (`expected_count: N`), binary ones included (a database, a cache, a memory dump), in one or several encodings at once; asserting a value was wiped: `expected_count: 0`. For line-based text use text.line_count.

asserts: count, absent, content · formats: text, binary · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Counts with a comparison (`count_comparison`), Text encodings (`encoding`), Negative tests (absence) (`negative`), Placeholders ({{ variable }}) (`placeholder`)

**Does not support:**
- Regex values (!re) (`regex_tag`): A `!re` in `content` is an error (it would be searched literally); for patterns use text.line_count with `regex_match` or standard.file_content_matches_regex.
- Times as expected values (!timestamp) (`timestamp_tag`): A `!timestamp` in `content` is an error.

**Not for:**
- whether a string is in a text file, without counting → `standard.file_content_contains`
- lines of a text file that contain a string or match a regex → `text.line_count`
- a regular expression in the content → `standard.file_content_matches_regex`
- rows of a SQLite database (the `.db` alone misses the `-wal`) → `sqlite.row_count`
- a byte pattern in one region of a binary file → `binary.pattern_count`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the file; a glob must match exactly one path. A missing file is an error. The raw bytes are searched, nothing is decoded. |
| **content** | `str` |  | What to find; must not be empty. Its meaning depends on `content_type`. A `!re` or `!timestamp` placeholder is an error: for patterns use text.line_count with `regex_match`. |
| **expected_count** | `int` |  | Non-negative integer to compare against; anything else is an error. |
| content_type | `str` | `'string'` | `string` (default): `content` encoded in each of `encoding`. `bytes`: ASCII characters stand for their byte, Python escapes (`\x00`, `\n`, `\\`) are decoded; a non-ASCII character or an unknown escape is an error (write `\xNN`, or use `string` with an encoding). `hex`: hex digits, whitespace allowed (`4d 5a 90 00`). Allowed: `string`, `bytes`, `hex`. |
| encoding | `list[str] \| str \| None` | `None` | Encoding(s) for `string` mode: one name (`utf-16-le`) or a list (default `[utf-8]`), e.g. `[utf-8, utf-16-le]`. Occurrences of the distinct encoded forms are summed (the same text stored once in each of two forms counts twice); a match on bytes already counted for an earlier form is skipped. `utf-16`/`utf-32` search both byte orders without BOM. Forms are matched at any byte offset, not aligned to characters. Unknown encodings, or `content` not encodable in one, are an error. |
| case_sensitive | `bool` | `True` | `False` matches each character in any of its one-character case forms (`a`/`A`, `ä`/`Ä`); case mappings to several characters (German sharp s to `SS`) are not matched. `string` mode only, otherwise an error. |
| comparison_type | `str` | `'equals'` | `equals` (default), `greater`, `less`, `greater_equal` or `less_equal`; other values are an error. Allowed: `equals`, `greater`, `less`, `greater_equal`, `less_equal`. |

**Outcomes:**
- PASSED: the number of non-overlapping occurrences of `content` (summed over the encoded forms) satisfies `comparison_type`
- FAILED: the file was read and the count comparison does not hold
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: the file cannot be read or is larger than the read cap (`ADARE_ARCHIVE_MAX_BYTES`)
- ERROR: empty `content`; a `!re` / `!timestamp` tag or unknown placeholder in `content`
- ERROR: an unknown `content_type` or encoding; `content` not encodable in a listed encoding; an invalid escape or hex string
- ERROR: `case_sensitive: false` outside `content_type: string`
- ERROR: a negative or non-integer `expected_count`; an unknown `comparison_type`

**Limits:**
- The raw bytes are searched, nothing is decoded; forms match at any byte offset, not aligned to characters.
- The same text stored once in each of two encodings counts twice; a match on bytes already counted for an earlier encoding is skipped.
- `utf-16` / `utf-32` search both byte orders without BOM.
- `case_sensitive: false` matches one-character case forms only (`ä` / `Ä`, not sharp s / `SS`).
- In YAML, `"\x00ab"` (double quotes) is decoded by YAML; in single quotes the escape reaches `content_type: bytes` and is decoded there. Both give the same bytes.

**Use cases:**
- A value was wiped: `expected_count: 0` on a cache, database or memory dump, in every encoding the application may use (`encoding: [utf-8, utf-16-le]`).
- A value was written n times: Exact counts in binary files that no structured function can parse.
- A file signature or marker: `content_type: hex` for byte sequences such as a magic number.

**Examples:**

*a token wiped in UTF-8 and UTF-16* → PASSED

```yaml
tests:
- name: a_token_wiped_in_utf_8_and_utf_16
  function: text.occurrence_count
  parameter:
    dst: /home/user/app/cache.bin
    content: secret-token
    encoding: [utf-8, utf-16-le]
    expected_count: 0
```

*a UTF-16 string is found with its encoding* → PASSED

```yaml
tests:
- name: a_utf_16_string_is_found_with_its_encoding
  function: text.occurrence_count
  parameter:
    dst: /home/user/app/cache.bin
    content: analyst
    encoding: [utf-8, utf-16-le]
    expected_count: 1
```

*but not in the default UTF-8* → FAILED. Without `encoding` only the UTF-8 form is searched, so a value stored as UTF-16 counts 0.

```yaml
tests:
- name: but_not_in_the_default_utf_8
  function: text.occurrence_count
  parameter:
    dst: /home/user/app/cache.bin
    content: analyst
    expected_count: 1
```

*the same text in two encodings counts twice* → PASSED

```yaml
tests:
- name: the_same_text_in_two_encodings_counts_twice
  function: text.occurrence_count
  parameter:
    dst: /home/user/app/store.dat
    content: token
    encoding: [utf-8, utf-16-le]
    expected_count: 2
```

*overlapping forms count once* → PASSED. The UTF-8 `a` is the first byte of the UTF-16-LE `a`; the bytes are counted once.

```yaml
tests:
- name: overlapping_forms_count_once
  function: text.occurrence_count
  parameter:
    dst: /home/user/app/one.dat
    content: a
    encoding: [utf-8, utf-16-le]
    expected_count: 1
```

*header bytes once* → PASSED

```yaml
tests:
- name: header_bytes_once
  function: text.occurrence_count
  parameter:
    dst: /home/user/app/blob.dat
    content: 4d 5a 90 00
    content_type: hex
    expected_count: 1
```

*in any case, at least once* → PASSED

```yaml
tests:
- name: in_any_case_at_least_once
  function: text.occurrence_count
  parameter:
    dst: /home/user/app/app.log
    content: Error
    case_sensitive: false
    expected_count: 1
    comparison_type: greater_equal
```

*inside a compressed file* → PASSED

```yaml
tests:
- name: inside_a_compressed_file
  function: text.occurrence_count
  parameter:
    dst: /home/user/app/app.log.gz!
    content: report
    expected_count: 2
```

*a missing file is an error, not an absence* → ERROR

```yaml
tests:
- name: a_missing_file_is_an_error_not_an_absence
  function: text.occurrence_count
  parameter:
    dst: /home/user/app/cache2.bin
    content: secret-token
    expected_count: 0
```

*case-insensitive hex is an error* → ERROR

```yaml
tests:
- name: case_insensitive_hex_is_an_error
  function: text.occurrence_count
  parameter:
    dst: /home/user/app/blob.dat
    content: 4d 5a
    content_type: hex
    case_sensitive: false
    expected_count: 1
```

*a regex tag in content is an error* → ERROR. Use text.line_count with `regex_match` for patterns.

```yaml
tests:
- name: a_regex_tag_in_content_is_an_error
  function: text.occurrence_count
  parameter:
    dst: /home/user/app/app.log
    content: !re 'report-\d+'
    expected_count: 1
```
