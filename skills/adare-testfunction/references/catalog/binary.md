# Binary (`binary.*`)

<!-- Generated; do not edit by hand. -->

Application-specific binary containers that no dedicated parser knows: entry files whose last bytes point at a metadata block, index files of fixed-size records, tables of NUL-separated key/value strings. The functions read values at offsets, count byte patterns in a region and look up keys in string tables. No format is built in: the test says where to look.

## `binary.pair_count`

tests how often a key (optionally with a value) occurs in a key/value string table of a binary file

Pass when the number of entries of `key` (with `expected_value`, if given) in the table satisfies `comparison_type`.

**Use for:** asserting a metadata element is absent from a key/value string table (`expected_count: 0`) or occurs a given number of times. The table is read as in binary.pair_value_matches.

asserts: count, absent · formats: binary · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Offset expressions (binary files) (`offset_expression`), Counts with a comparison (`count_comparison`), Text encodings (`encoding`), Negative tests (absence) (`negative`)

**Not for:**
- the value of a key → `binary.pair_value_matches`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the file; a glob must match exactly one path. A missing file is an error. |
| **key** | `str` |  | Key string to count. |
| **expected_count** | `int` |  | Non-negative integer to compare with; `0` asserts absence. |
| expected_value | `str \| int \| float \| bool \| None` | `None` | Only count entries whose value matches this (as in binary.pair_value_matches). `None` (default) counts every entry of `key`. |
| start | `int \| str` | `0` | Offset of the first key (default 0); int or offset expression. |
| end | `int \| str \| None` | `None` | End of the table, exclusive (default: end of file). |
| separator | `str` | `'\x00'` | Bytes between the strings (default NUL), ASCII and Python escapes. |
| encoding | `str` | `'utf-8'` | Encoding of keys and values (default `utf-8`). |
| regex_match | `bool` | `False` | Treat a string `expected_value` as a regex searched in each value. |
| comparison_type | `str` | `'equals'` | `equals` (default), `greater`, `less`, `greater_equal` or `less_equal`. Allowed: `equals`, `greater`, `less`, `greater_equal`, `less_equal`. |

**Outcomes:**
- PASSED: the count comparison holds
- FAILED: the table was read and the count comparison does not hold
- ERROR: as for binary.pair_value_matches (file, offsets, table layout, encoding)
- ERROR: a negative `expected_count` or an unknown `comparison_type`

**Limits:**
- The table is read as in binary.pair_value_matches; the region must hold whole key/value pairs.

**Use cases:**
- A metadata element was removed: `expected_count: 0` after a clean-up action.

**Examples:**

*no alternative source* → PASSED

```yaml
tests:
- name: no_alternative_source
  function: binary.pair_count
  parameter:
    dst: /home/user/app/cache/entry.bin
    start: u32be@-4+16
    end: -4
    key: alt-source
    expected_count: 0
```

*two origins* → PASSED

```yaml
tests:
- name: two_origins
  function: binary.pair_count
  parameter:
    dst: /home/user/app/cache/entry.bin
    start: u32be@-4+16
    end: -4
    key: origin
    expected_count: 2
```

## `binary.pair_value_matches`

tests the value of a key in a table of separator-delimited key/value strings in a binary file

Pass when `key` in the key/value string table at `[start, end)` of `dst` has `expected_value`.

**Use for:** "metadata element X has value Y" in a binary container that stores its metadata as alternating key and value strings (`key\0value\0key\0value\0`), e.g. in a block that the file's last bytes point to. An absent key fails; to assert absence use binary.pair_count with `expected_count: 0`.

asserts: value · formats: binary · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Offset expressions (binary files) (`offset_expression`), Regex values (!re) (`regex_tag`), Placeholders ({{ variable }}) (`placeholder`), Text encodings (`encoding`), Several matches (wildcard_mode) (`wildcard_mode`)

**Not for:**
- a metadata element is absent → `binary.pair_count`
- one value at an offset (numbers, timestamps, fixed-size strings) → `binary.struct_value_matches`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the file; a glob must match exactly one path. A missing file is an error. |
| **key** | `str` |  | Key string to look up (compared exactly after decoding). |
| **expected_value** | `str \| int \| float \| bool \| None` |  | The value the key must have, compared as text (a number as its text). A `!re` tag (`re.match`) or `{{placeholder}}` is supported. A value not valid in `encoding` is an error. |
| start | `int \| str` | `0` | Offset of the first key (default 0); an int (negative from the end) or an offset expression as in binary.struct_value_matches (`u32be@-4+4`). |
| end | `int \| str \| None` | `None` | End of the table, exclusive (default: end of file). The region must hold whole key/value pairs: one separator after the last value is allowed, an odd number of strings is an error. |
| separator | `str` | `'\x00'` | Bytes between the strings (default NUL), ASCII and Python escapes (`\x00`, `\n`). For UTF-16 tables use `\x00\x00`; matches are aligned to the encoding's code units. |
| encoding | `str` | `'utf-8'` | Encoding of keys and values (default `utf-8`; `utf-16-le`, ...). |
| regex_match | `bool` | `False` | Treat a string `expected_value` as a regex searched (`re.search`). |
| wildcard_mode | `str` | `'any'` | When the key occurs several times: `any` (default): one value must match; `all`: every value must match. Allowed: `any`, `all`. |

**Outcomes:**
- PASSED: the value of `key` (`any`: one of its values, `all`: every value) matches
- FAILED: the table was read and `key` does not occur, or its value(s) do not match
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: a malformed offset expression, an offset outside the file, `end` before `start`
- ERROR: an odd number of strings in the region; an empty key
- ERROR: an invalid separator (or one that is not a whole number of code units); an unknown encoding or a value not valid in it
- ERROR: an invalid regex or placeholder, or an invalid `wildcard_mode`

**Limits:**
- The region must hold whole key/value pairs; one separator after the last value is allowed.
- Values compare as text (a number as its text); there is no ordered comparison.

**Use cases:**
- A metadata element has a value: Response headers, origins, titles or flags stored as key/value strings in a binary container.

**Examples:**

*content type of a cache entry* → PASSED. The table starts 16 bytes after the offset stored in the last 4 bytes and ends before them.

```yaml
tests:
- name: content_type_of_a_cache_entry
  function: binary.pair_value_matches
  parameter:
    dst: /home/user/app/cache/entry.bin
    start: u32be@-4+16
    end: -4
    key: content-type
    expected_value: text/plain
```

*every origin on example.org* → PASSED

```yaml
tests:
- name: every_origin_on_example_org
  function: binary.pair_value_matches
  parameter:
    dst: /home/user/app/cache/entry.bin
    start: u32be@-4+16
    end: -4
    key: origin
    expected_value: 'example\.org'
    regex_match: true
    wildcard_mode: all
```

*an absent key fails* → FAILED. To assert absence use binary.pair_count with `expected_count` 0, which passes.

```yaml
tests:
- name: an_absent_key_fails
  function: binary.pair_value_matches
  parameter:
    dst: /home/user/app/cache/entry.bin
    start: u32be@-4+16
    end: -4
    key: referrer
    expected_value: https://example.org/
```

## `binary.pattern_count`

tests how often a byte pattern, text or regex occurs within a region of a binary file

Pass when the non-overlapping occurrences of `pattern` in `[start, end)` of `dst` satisfy `comparison_type`.

**Use for:** counting records, markers or values inside one part of a binary file (only the metadata block a trailer points to, the records after a header); a regex over raw bytes; asserting a value is gone from that part: `expected_count: 0`. For the whole file in several encodings at once use text.occurrence_count.

asserts: count, absent · formats: binary · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Offset expressions (binary files) (`offset_expression`), Counts with a comparison (`count_comparison`), Text encodings (`encoding`), Negative tests (absence) (`negative`)

**Does not support:**
- Regex values (!re) (`regex_tag`): A `!re` or `!timestamp` tag as `pattern` is an error; write the regex as a plain string with `pattern_type: regex`.

**Not for:**
- a string anywhere in the whole file, in several encodings at once → `text.occurrence_count`
- one value at an offset → `binary.struct_value_matches`
- how often a key occurs in a key/value string table → `binary.pair_count`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the file; a glob must match exactly one path. A missing file is an error; the region is read whole, up to the read cap. |
| **pattern** | `str` |  | What to count; must not be empty. Its meaning depends on `pattern_type`. |
| pattern_type | `str` | `'bytes'` | `bytes` (default): ASCII characters stand for their byte, Python escapes (`\x00`) are decoded. `hex`: hex digits, whitespace allowed (`00 00 01 00`). `regex`: an ASCII regular expression over the raw bytes (`\x00` escapes for other bytes; empty matches are not counted). `text`: `pattern` encoded in `encoding`. Invalid escapes, hex or regexes are an error. Allowed: `bytes`, `hex`, `regex`, `text`. |
| start | `int \| str` | `0` | Offset where the region starts (default 0); an int (negative from the end) or an offset expression as in binary.struct_value_matches (`u32be@-4`). |
| end | `int \| str \| None` | `None` | Offset where the region ends, exclusive (default: the end of the file). An offset outside the file, or `end` before `start`, is an error. |
| encoding | `str` | `'utf-8'` | Encoding for `text` (default `utf-8`; `utf-16-le`, `utf-16-be`, ...). |
| expected_count | `int` | `1` | Non-negative integer to compare with (default 1); `0` asserts absence. |
| comparison_type | `str` | `'equals'` | `equals` (default, like every count function), `greater`, `less`, `greater_equal` or `less_equal`. Use `greater_equal` with `expected_count: 1` for "at least once". Allowed: `equals`, `greater`, `less`, `greater_equal`, `less_equal`. |

**Outcomes:**
- PASSED: the number of non-overlapping occurrences in `[start, end)` satisfies `comparison_type`
- FAILED: the region was read and the count comparison does not hold
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: an empty or invalid pattern (escape, hex, regex, not encodable); an unknown `pattern_type` or encoding
- ERROR: a `!re` / `!timestamp` placeholder as pattern
- ERROR: a malformed offset expression, an offset outside the file, `end` before `start`
- ERROR: a region over the read cap; a negative `expected_count` or an unknown `comparison_type`

**Limits:**
- The region is read whole, up to the read cap (`ADARE_ARCHIVE_MAX_BYTES`).
- A `regex` pattern is an ASCII regular expression over raw bytes; empty matches are not counted.

**Use cases:**
- Records in one part of a file: Count record markers after a header or inside a metadata block only.
- A value is gone from a block: `expected_count: 0` on the region that held it, so other copies elsewhere in the file do not count.

**Examples:**

*two origins in the metadata block* → PASSED

```yaml
tests:
- name: two_origins_in_the_metadata_block
  function: binary.pattern_count
  parameter:
    dst: /home/user/app/cache/entry.bin
    pattern: 'https://[a-z.]+\.org'
    pattern_type: regex
    start: u32be@-4
    end: -4
    expected_count: 2
```

*the payload marker is not in the metadata block* → PASSED. The marker occurs in the file, but before the region, so it does not count.

```yaml
tests:
- name: the_payload_marker_is_not_in_the_metadata_block
  function: binary.pattern_count
  parameter:
    dst: /home/user/app/cache/entry.bin
    pattern: PAYLOAD
    start: u32be@-4
    end: -4
    expected_count: 0
```

*end before start is an error* → ERROR

```yaml
tests:
- name: end_before_start_is_an_error
  function: binary.pattern_count
  parameter:
    dst: /home/user/app/cache/entry.bin
    pattern: origin
    start: 20
    end: 10
    expected_count: 0
```

## `binary.struct_value_matches`

tests a number, string, byte sequence or timestamp read at an offset of a binary file

Pass when the value of `value_format` read at `offset` of `dst` compares to `expected_value`.

**Use for:** a field of a binary container no parser knows: a counter, flag, size or timestamp in a header, a record of an index file, a string in a metadata block that the file's last bytes point to. `offset` follows pointers (`u32be@-4`), so the field is found even when the block moves. For key/value string tables use binary.pair_value_matches; to count byte patterns use binary.pattern_count.

asserts: value, order · formats: binary · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Offset expressions (binary files) (`offset_expression`), Ordered comparison of numbers and times (`ordered_comparison`), Regex values (!re) (`regex_tag`), Placeholders ({{ variable }}) (`placeholder`), Times as expected values (!timestamp) (`timestamp_tag`), Text encodings (`encoding`)

**Not for:**
- a value in a table of key/value strings → `binary.pair_value_matches`
- how often a byte pattern or string occurs → `binary.pattern_count`
- a string anywhere in the file, in several encodings → `text.occurrence_count`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the file; a glob must match exactly one path; `archive.tar!/member` reads an archive member. A missing file is an error. |
| **offset** | `int \| str` |  | Where the value starts. An int (negative counts from the end: `-8`) or an offset expression: `u32be@-4` (the offset stored as big-endian u32 in the last 4 bytes), `u32be@-4+8` (that plus 8), `u32le@(u32le@0+4)` (pointer read at pointer+4), `find:6b6579` (first occurrence of the hex bytes). Integer types: `u8`, `i8`, `u16le`/`u16be` ... `i64le`/`i64be`; numbers may be `0x`-hex. A malformed expression, or an offset or value outside the file, is an error. |
| **value_format** | `str` |  | `u8`, `i8`, `u16le` ... `i64be` (integers), `f32le`/`be`, `f64le`/`be` (floats), `bytes:<n>` (n bytes, compared as lowercase hex), `string:<n>` (n bytes decoded with `encoding`, trailing NULs dropped) or `cstring` (up to the first NUL, `\x00\x00` in UTF-16). A string not valid in `encoding` is an error. |
| **expected_value** | `str \| int \| float \| bool \| None` |  | What the value must be. Numbers and timestamps compare by value (`comparison_type`); strings compare as text, a number written here as its text; `bytes:<n>` as hex (whitespace ignored: `de ad be ef`). A `!re` tag or `{{placeholder}}` compares the value's text (a `!timestamp` placeholder with `epoch`/`unit` reads a numeric field as a time). |
| comparison_type | `str` | `'equals'` | `equals` (default), `not_equals`, `greater`, `less`, `greater_equal` or `less_equal`. Ordered comparisons need numbers or timestamps (a string field is read as one); for text and `bytes` only `equals`/`not_equals`. Allowed: `equals`, `not_equals`, `greater`, `less`, `greater_equal`, `less_equal`. |
| tolerance | `int \| float \| None` | `None` | For `equals`/`not_equals` of numbers or timestamps: the largest difference that still counts as equal (seconds for timestamps). |
| regex_match | `bool` | `False` | Treat a string `expected_value` as a regex searched (`re.search`) in the value's text; an invalid regex is an error. |
| encoding | `str` | `'utf-8'` | Encoding of `string`/`cstring` values (default `utf-8`; `utf-16-le` ...). Encodings without a fixed byte order (`utf-16`) are an error. |
| value_type | `str` | `'auto'` | `auto` (default), `number` or `timestamp`. `auto` compares as timestamps when `timestamp_epoch` or `time_format` is set, else as numbers, else as ISO 8601 / RFC 2822 timestamps; a value of neither kind is an error. Allowed: `auto`, `number`, `timestamp`. |
| timestamp_epoch | `int \| None` | `None` | Read a number as time since 1 January of 1970, 1601 or 2001 (also a numeric `expected_value`). Allowed: `1970`, `1601`, `2001`. |
| timestamp_unit | `str` | `'s'` | Unit of such numbers: `s` (default), `ms`, `us`, `ns`, `100ns`. Allowed: `s`, `ms`, `us`, `ns`, `100ns`. |
| utc_offset | `str \| None` | `None` | Zone of times without one, e.g. `+02:00`; default UTC. |
| time_format | `str \| None` | `None` | `strptime` format of a string timestamp (`%d.%m.%Y %H:%M`). |

**Outcomes:**
- PASSED: the value read at `offset` compares to `expected_value`
- FAILED: the file was read and the value does not match
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: a malformed offset expression or value format; an offset or value outside the file
- ERROR: a `find:` pattern that does not occur; a `cstring` without terminator
- ERROR: a string not valid in `encoding`; a NaN or infinite float
- ERROR: a value or `expected_value` that is no number or timestamp for an ordered comparison
- ERROR: an invalid regex or placeholder, or other bad parameters

**Limits:**
- Ordered comparisons need numbers or timestamps; text and `bytes:<n>` values support only `equals` / `not_equals`.
- Encodings without a fixed byte order (`utf-16`) are an error; name the order (`utf-16-le`).
- At most 4 `@` pointer reads per offset expression.

**Use cases:**
- A counter or flag changed: A header or metadata field (hit count, state flag) after an action in the GUI.
- A timestamp field: Times stored as numbers (`timestamp_epoch` / `timestamp_unit`) compared with the time of an action.
- A string in a block a trailer points to: `cstring` at `u32be@-4+N` finds the field even when the payload before it changes size.

**Examples:**

*entry modified after a point in time* → PASSED. The last 4 bytes hold the offset of the metadata block; its third u32 is a Unix time.

```yaml
tests:
- name: entry_modified_after_a_point_in_time
  function: binary.struct_value_matches
  parameter:
    dst: /home/user/app/cache/entry.bin
    offset: u32be@-4+8
    value_format: u32be
    timestamp_epoch: 1970
    expected_value: '2026-01-01T10:00:00Z'
    comparison_type: greater_equal
```

*hit count at least two* → PASSED

```yaml
tests:
- name: hit_count_at_least_two
  function: binary.struct_value_matches
  parameter:
    dst: /home/user/app/cache/entry.bin
    offset: u32be@-4+4
    value_format: u32be
    expected_value: 2
    comparison_type: greater_equal
```

*a different count fails* → FAILED

```yaml
tests:
- name: a_different_count_fails
  function: binary.struct_value_matches
  parameter:
    dst: /home/user/app/cache/entry.bin
    offset: u32be@-4+4
    value_format: u32be
    expected_value: 5
```

*an offset outside the file is an error, not a failure* → ERROR. The test never looked at the claimed value, so it cannot fail; `expect_to_fail` cannot turn it into a pass.

```yaml
tests:
- name: an_offset_outside_the_file_is_an_error_not_a_fai
  function: binary.struct_value_matches
  parameter:
    dst: /home/user/app/cache/entry.bin
    offset: 4096
    value_format: u32be
    expected_value: 3
```
