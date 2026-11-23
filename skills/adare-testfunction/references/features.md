# Shared features and known gaps

<!-- Generated; do not edit by hand. -->

## Files inside archives and compressed files (`archive_dst`)

`dst` can name a member of an archive or the decompressed content of a compressed file, with `!`. tar (plain and compressed), zip (also .docx/.xlsx/.odt) and single-file gzip, bzip2, xz, LZ4 (frame format and the LZ4 block with a magic header of `.jsonlz4` stores) and Snappy. The format comes from the content, not the extension. Archives nest. Only file members can be read.

```
archive!/member/path     a member of a tar or zip (member paths always use /)
file.gz!                 the decompressed content of a single-file archive
outer.zip!/inner.tar!/x  an archive inside an archive
{archive: ..., member: ...}  mapping form, same meaning
```

Supported by: `binary.pair_count`, `binary.pair_value_matches`, `binary.pattern_count`, `binary.struct_value_matches`, `csv.compare_files`, `csv.compare_rows`, `csv.contains_line`, `csv.row_count`, `excel.cell_value_matches`, `excel.compare_files`, `excel.compare_rows`, `excel.compare_sheets`, `excel.contains_row`, `excel.row_count`, `excel.sheet_exists`, `excel.validate_columns`, `image.dimensions_match`, `image.exif_value_count`, `image.exif_value_matches`, `image.png_text_count`, `image.png_text_matches`, `ini.contains_key`, `ini.section_exists`, `ini.value_count`, `ini.value_matches`, `json.array_contains`, `json.contains_key`, `json.value_count`, `json.value_matches`, `json.values_compare`, `jsonl.line_count`, `jsonl.line_matches`, `jsonl.lines_in_order`, `jsonl.value_in_any_line`, `linux.log_entry_exists`, `plist.contains_key`, `plist.value_count`, `plist.value_matches`, `plist.values_compare`, `sqlite.free_space_pattern_count`, `sqlite.query_result`, `sqlite.row_count`, `sqlite.values_compare`, `sqlite.wal_frame_count`, `standard.file_content_contains`, `standard.file_content_equals`, `standard.file_content_matches_regex`, `standard.file_count`, `standard.file_does_not_exist`, `standard.file_exists`, `standard.file_hash_matches`, `standard.file_size`, `text.line_count`, `text.lines_in_order`, `text.occurrence_count`, `toml.contains_key`, `toml.value_count`, `toml.value_matches`, `toml.values_compare`, `xml.attribute_matches`, `xml.element_count`, `xml.element_exists`, `xml.element_text_matches`, `xml.namespace_matches`, `xml.values_compare`, `xml.xpath_result_matches`, `yaml.contains_key`, `yaml.value_count`, `yaml.value_matches`, `yaml.values_compare`

Not supported by: `standard.dir_content`, `standard.dir_does_not_exist`, `standard.dir_exists`, `standard.file_permissions`, `standard.file_timestamps`

## Globs in dst (`glob_dst`)

`dst` may be a glob (`*`, `?`, `[...]`). Unless the function says otherwise the glob must match exactly one path: none or several is an ERROR, not a failure. Existence and count functions accept several matches (`match_mode` / `expected_count`).

```
/home/*/app/settings.json      one user's file, whoever the user is
C:\Users\*\AppData\...\x.db    Windows paths take globs too
```

Supported by: `binary.pair_count`, `binary.pair_value_matches`, `binary.pattern_count`, `binary.struct_value_matches`, `csv.compare_files`, `csv.compare_rows`, `csv.contains_line`, `csv.row_count`, `excel.cell_value_matches`, `excel.compare_files`, `excel.compare_rows`, `excel.compare_sheets`, `excel.contains_row`, `excel.row_count`, `excel.sheet_exists`, `excel.validate_columns`, `image.dimensions_match`, `image.exif_value_count`, `image.exif_value_matches`, `image.png_text_count`, `image.png_text_matches`, `ini.contains_key`, `ini.section_exists`, `ini.value_count`, `ini.value_matches`, `json.array_contains`, `json.contains_key`, `json.value_count`, `json.value_matches`, `json.values_compare`, `jsonl.line_count`, `jsonl.line_matches`, `jsonl.lines_in_order`, `jsonl.value_in_any_line`, `linux.log_entry_exists`, `plist.contains_key`, `plist.value_count`, `plist.value_matches`, `plist.values_compare`, `sqlite.free_space_pattern_count`, `sqlite.query_result`, `sqlite.row_count`, `sqlite.values_compare`, `sqlite.wal_frame_count`, `standard.dir_content`, `standard.dir_does_not_exist`, `standard.dir_exists`, `standard.file_content_contains`, `standard.file_content_equals`, `standard.file_content_matches_regex`, `standard.file_count`, `standard.file_does_not_exist`, `standard.file_exists`, `standard.file_hash_matches`, `standard.file_permissions`, `standard.file_size`, `standard.file_timestamps`, `text.line_count`, `text.lines_in_order`, `text.occurrence_count`, `toml.contains_key`, `toml.value_count`, `toml.value_matches`, `toml.values_compare`, `xml.attribute_matches`, `xml.element_count`, `xml.element_exists`, `xml.element_text_matches`, `xml.namespace_matches`, `xml.values_compare`, `xml.xpath_result_matches`, `yaml.contains_key`, `yaml.value_count`, `yaml.value_matches`, `yaml.values_compare`

## Regex values (!re) (`regex_tag`)

An expected value written as `!re '<pattern>'` matches with Python's `re.match` (anchored at the start; add `$` to anchor the end). `!reALL` matches any value. A literal pattern is checked when the playbook loads; an invalid one is an ERROR. Functions with a `regex_match` parameter take a plain string pattern instead.

```
expected_value: !re '^[0-9]{4}-'
expected_value: !reALL
```

Supported by: `binary.pair_value_matches`, `binary.struct_value_matches`, `csv.compare_rows`, `csv.contains_line`, `csv.row_count`, `excel.cell_value_matches`, `excel.compare_rows`, `excel.contains_row`, `excel.row_count`, `excel.sheet_exists`, `image.exif_value_count`, `image.exif_value_matches`, `image.png_text_count`, `image.png_text_matches`, `ini.value_count`, `ini.value_matches`, `json.array_contains`, `json.value_count`, `json.value_matches`, `jsonl.line_count`, `jsonl.line_matches`, `jsonl.lines_in_order`, `jsonl.value_in_any_line`, `plist.value_count`, `plist.value_matches`, `sqlite.query_result`, `standard.file_content_equals`, `toml.value_count`, `toml.value_matches`, `xml.attribute_matches`, `xml.element_text_matches`, `yaml.value_count`, `yaml.value_matches`

Not supported by: `binary.pattern_count`, `excel.validate_columns`, `linux.log_entry_exists`, `linux.system_service_status`, `plist.values_compare`, `sqlite.free_space_pattern_count`, `standard.file_content_contains`, `text.line_count`, `text.lines_in_order`, `text.occurrence_count`, `windows.registry_value_matches`, `xml.values_compare`, `xml.xpath_result_matches`

## Placeholders ({{ variable }}) (`placeholder`)

`{{ name }}` in a parameter is replaced by a playbook variable or a value saved during the run (`save_timestamp`) before the test runs. An unknown placeholder is an ERROR.

```
expected_value: '{{ username }}'
```

Supported by: `binary.pair_value_matches`, `binary.struct_value_matches`, `csv.compare_files`, `csv.compare_rows`, `csv.contains_line`, `csv.row_count`, `excel.cell_value_matches`, `excel.compare_files`, `excel.compare_rows`, `excel.compare_sheets`, `excel.contains_row`, `excel.row_count`, `image.exif_value_count`, `image.exif_value_matches`, `image.png_text_count`, `image.png_text_matches`, `ini.value_count`, `ini.value_matches`, `json.array_contains`, `json.value_count`, `json.value_matches`, `jsonl.line_count`, `jsonl.line_matches`, `jsonl.lines_in_order`, `jsonl.value_in_any_line`, `linux.process_running`, `linux.system_service_status`, `linux.user_exists`, `plist.value_count`, `plist.value_matches`, `sqlite.query_result`, `standard.file_content_equals`, `text.line_count`, `text.lines_in_order`, `text.occurrence_count`, `toml.value_count`, `toml.value_matches`, `windows.registry_key_exists`, `windows.registry_value_matches`, `xml.attribute_matches`, `xml.element_text_matches`, `yaml.value_count`, `yaml.value_matches`

## Times as expected values (!timestamp) (`timestamp_tag`)

`!timestamp` compares a stored time with an interval or a tolerance: `after` / `before` (often the times saved around the action), `tolerance` in seconds, and `epoch` (1970, 1601, 2001) plus `unit` (s, ms, us, ns, 100ns) for times stored as numbers. Needs `tolerance` or `after` and `before`.

```
expected_value: !timestamp {after: '{{t0}}', before: '{{t1}}', epoch: 1601, unit: 100ns}
```

Supported by: `binary.struct_value_matches`, `csv.compare_rows`, `csv.contains_line`, `csv.row_count`, `excel.cell_value_matches`, `excel.compare_rows`, `excel.contains_row`, `excel.row_count`, `image.exif_value_count`, `image.exif_value_matches`, `image.png_text_count`, `image.png_text_matches`, `ini.value_matches`, `json.array_contains`, `json.value_count`, `json.value_matches`, `jsonl.line_count`, `jsonl.line_matches`, `jsonl.lines_in_order`, `jsonl.value_in_any_line`, `plist.value_matches`, `sqlite.query_result`, `standard.file_content_equals`, `toml.value_count`, `toml.value_matches`, `xml.attribute_matches`, `xml.element_text_matches`, `yaml.value_count`, `yaml.value_matches`

Not supported by: `standard.file_content_contains`, `standard.file_timestamps`, `text.line_count`, `text.lines_in_order`, `text.occurrence_count`, `windows.registry_value_matches`

## Ordered comparison of numbers and times (`ordered_comparison`)

`comparison_type` (equals, not_equals, greater, less, greater_equal, less_equal), `value_type` (auto, number, timestamp), `tolerance` and the time parameters (`time_format`, `timestamp_epoch`, `timestamp_unit`, `utc_offset`) compare the found value with `expected_value` as a number or a point in time. A value that is no number or time is an ERROR (the test looked at the wrong field). `!re` and `regex_match` cannot be combined with them. An `expected_value` of exactly `'{{ name }}'` may be a variable saved during the run: a `save_timestamp` is compared as that moment (the time parameters then describe only the value in the file); text around the placeholder, or a `!re` / interval variable, is an ERROR.

```
comparison_type: greater
timestamp_epoch: 1970
timestamp_unit: ms
```

Supported by: `binary.struct_value_matches`, `excel.cell_value_matches`, `image.exif_value_matches`, `ini.value_matches`, `json.value_matches`, `json.values_compare`, `jsonl.value_in_any_line`, `plist.value_matches`, `plist.values_compare`, `sqlite.values_compare`, `toml.value_matches`, `toml.values_compare`, `xml.attribute_matches`, `xml.element_text_matches`, `xml.values_compare`, `yaml.value_matches`, `yaml.values_compare`

Not supported by: `jsonl.line_matches`, `jsonl.lines_in_order`, `standard.file_timestamps`, `windows.registry_value_matches`, `xml.xpath_result_matches`

## Counts with a comparison (`count_comparison`)

Count functions take `expected_count` and `comparison_type` (equals by default, greater, less, greater_equal, less_equal). `expected_count: 0` asserts absence and makes the test a negative test.

```
expected_count: 0                          # absent
expected_count: 1, comparison_type: greater_equal   # at least once
```

Supported by: `binary.pair_count`, `binary.pattern_count`, `csv.row_count`, `excel.row_count`, `image.exif_value_count`, `image.png_text_count`, `ini.value_count`, `json.value_count`, `jsonl.line_count`, `plist.value_count`, `sqlite.free_space_pattern_count`, `sqlite.query_result`, `sqlite.row_count`, `sqlite.wal_frame_count`, `standard.file_count`, `text.line_count`, `text.occurrence_count`, `toml.value_count`, `xml.element_count`, `yaml.value_count`

Not supported by: `linux.log_entry_exists`, `linux.process_running`, `visual.count_equals`, `visual.count_max`, `visual.count_min`

## Key paths into structured files (`key_path`)

Dot paths from the root: `a.b.c`; `*` expands every value of an object, `name[*]` every array element, `name[0]` / `name[-1]` one element; a leading `[0]` addresses a top-level array and `['a.b']` a key containing dots. When a path selects several values, `wildcard_mode` decides whether one (any) or all must match.

```
key_path: profiles[*].name
key_path: "['window.size'].width"
```

Supported by: `json.array_contains`, `json.contains_key`, `json.value_count`, `json.value_matches`, `json.values_compare`, `jsonl.line_count`, `jsonl.line_matches`, `jsonl.lines_in_order`, `jsonl.value_in_any_line`, `plist.contains_key`, `plist.value_count`, `plist.value_matches`, `plist.values_compare`, `toml.contains_key`, `toml.value_count`, `toml.value_matches`, `toml.values_compare`, `yaml.contains_key`, `yaml.value_count`, `yaml.value_matches`, `yaml.values_compare`

## Several matches (wildcard_mode) (`wildcard_mode`)

When a path, glob, key or several lines select several values, `wildcard_mode: any` (usual default) passes if one matches and `all` only if every one matches.

```
wildcard_mode: all
```

Supported by: `binary.pair_value_matches`, `image.exif_value_matches`, `image.png_text_matches`, `ini.value_matches`, `json.value_matches`, `jsonl.line_matches`, `plist.value_matches`, `toml.value_matches`, `xml.element_text_matches`, `yaml.value_matches`

Not supported by: `plist.values_compare`, `xml.attribute_matches`, `xml.values_compare`

## Text encodings (`encoding`)

An `encoding` parameter reads the file in a given encoding (`utf-8`, `utf-16-le`, ...); functions that take a list search in each. A BOM is honoured where the function says so.

```
encoding: utf-16-le
encoding: [utf-8, utf-16-le]
```

Supported by: `binary.pair_count`, `binary.pair_value_matches`, `binary.pattern_count`, `binary.struct_value_matches`, `csv.compare_files`, `csv.compare_rows`, `csv.contains_line`, `csv.row_count`, `ini.contains_key`, `ini.section_exists`, `ini.value_count`, `ini.value_matches`, `json.array_contains`, `json.contains_key`, `json.value_count`, `json.value_matches`, `json.values_compare`, `jsonl.line_count`, `jsonl.line_matches`, `jsonl.lines_in_order`, `jsonl.value_in_any_line`, `sqlite.free_space_pattern_count`, `standard.file_content_contains`, `standard.file_content_equals`, `standard.file_content_matches_regex`, `text.line_count`, `text.lines_in_order`, `text.occurrence_count`

Not supported by: `linux.log_entry_exists`, `toml.contains_key`, `toml.value_count`, `toml.value_matches`, `toml.values_compare`, `yaml.contains_key`, `yaml.value_count`, `yaml.value_matches`, `yaml.values_compare`

## Offset expressions (binary files) (`offset_expression`)

`offset` / `start` / `end` of the `binary` functions take an int (negative counts from the end) or an expression: `u32be@-4` reads a big-endian u32 at -4 and uses it as the offset (a trailer pointer), `+N` / `-N` adds, parentheses nest, up to 4 `@` reads, and `find:<hex>` is the offset of the first occurrence of those bytes.

```
16, 0x10, -4
u32be@-4+8
u32le@(u32le@0+4)
find:6b6579+3
```

Supported by: `binary.pair_count`, `binary.pair_value_matches`, `binary.pattern_count`, `binary.struct_value_matches`

## SQLite views of the write-ahead log (`sqlite_view`)

`view` chooses which state of a database in WAL mode a query sees: `current` (main file plus committed WAL frames, as an application sees it), `main_file` (the file alone), `wal_added` / `wal_removed` (rows the WAL adds or removes), `commit:N` (the state after the N-th transaction in the WAL; negative N counts from the end, `commit:0` is the main file; N out of range is an ERROR). All views come from one snapshot.

```
view: wal_removed
view: commit:-2
```

Supported by: `sqlite.query_result`, `sqlite.row_count`, `sqlite.values_compare`

Not supported by: `sqlite.free_space_pattern_count`

## Decoding a stored value (value_decode) (`value_decode`)

`value_decode` decodes the value read from the file before it is compared: one step or a list applied in order, from `url`, `base64`, `hex`, `utf16` and `json`. After `json`, `decoded_key_path` (key path syntax) selects one value of the decoded document. A value a step cannot decode, or an unknown step, is an ERROR.

```
value_decode: base64
value_decode: [url, base64, json]
decoded_key_path: session.user
```

Supported by: `ini.value_matches`, `json.value_matches`, `json.values_compare`, `jsonl.value_in_any_line`, `plist.value_matches`, `plist.values_compare`, `toml.value_matches`, `toml.values_compare`, `xml.attribute_matches`, `xml.element_text_matches`, `xml.values_compare`, `yaml.value_matches`, `yaml.values_compare`

## A second file (other_dst) (`other_dst`)

`values_compare` takes `other_dst`: the second value is read from another file or archive member instead of `dst`, e.g. a copy a `command` action made before the action under test. Globs, archives and host mode work as for `dst`.

```
other_dst: /tmp/before/settings.json
```

Supported by: `json.values_compare`, `plist.values_compare`, `sqlite.values_compare`, `toml.values_compare`, `xml.values_compare`, `yaml.values_compare`

## Negative tests (absence) (`negative`)

A pass that means "something is absent" is only reported as SUCCESS when ADARE can show that the actions before it took effect; otherwise it is INCONCLUSIVE. Pair the test with a control test (`controls:`) that proves the act. A missing or unreadable file is an ERROR, never a pass.

```
expected_count: 0          # count functions
controls: [file_was_written]
```

Supported by: `binary.pair_count`, `binary.pattern_count`, `csv.row_count`, `excel.row_count`, `image.exif_value_count`, `image.png_text_count`, `ini.value_count`, `json.value_count`, `jsonl.line_count`, `plist.value_count`, `sqlite.free_space_pattern_count`, `sqlite.query_result`, `sqlite.row_count`, `sqlite.wal_frame_count`, `standard.dir_does_not_exist`, `standard.file_count`, `standard.file_does_not_exist`, `text.line_count`, `text.occurrence_count`, `toml.value_count`, `visual.count_equals`, `visual.count_max`, `visual.not_exists`, `xml.element_count`, `yaml.value_count`

Not supported by: `linux.process_running`

## Known gaps (no bundled testfunction does this)

- **A directory entry inside an archive cannot be tested; only file members can be read.** Instead: Test a file inside that directory (`a.zip!/dir/file`), or list the archive in a `run` action and test its output.
- **7z and RAR archives cannot be read through `!` (tar, zip, gzip, bzip2, xz, LZ4 and Snappy can).** Instead: Extract the archive in a `run` action first, then test the extracted file.
- **No testfunction parses Windows event logs (.evtx).** Instead: Export the events to XML or CSV in a `run` action (`wevtutil qe ... /f:xml`) and use the xml or csv functions, or write a collection.
- **No parsers for Windows artifacts such as prefetch, LNK, jump lists, shellbags or the recycle bin index files.** Instead: Read fixed fields with the binary functions (offsets, string tables), or write a collection with a parser.
- **The csv functions read comma-separated files only; there is no delimiter parameter (semicolon or tab files read as one column).** Instead: Match whole lines with `text.line_count` (`regex_match`) or `standard.file_content_matches_regex`.
- **values_compare compares numbers and times only, not two text values.** Instead: Test each value against the expected text with `value_matches`.
- **Stale or uncommitted frames of an SQLite write-ahead log are not carved; free space is only searched in the main file (or the checkpointed `current` copy).** Instead: Search the raw bytes of the `-wal` with `text.occurrence_count` or `binary.pattern_count`.
- **Testfunctions read files and guest state, not memory dumps or network captures.** Instead: Analyse such evidence outside the playbook tests.
