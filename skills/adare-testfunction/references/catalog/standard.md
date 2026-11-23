# Standard (`standard.*`)

<!-- Generated; do not edit by hand. -->

Files and folders on the guest: whether a file or folder exists or is gone, how many paths match a glob, which entries a folder holds, the size, hash and text content of a file, and its timestamps and permissions. The functions read the file system only; they do not parse any file format (for settings, databases or documents use the format collections).

## `standard.dir_content`

tests if a directory has the expected files/folders

Pass when every name in `files` is a direct entry of directory `dst`.

**Use for:** checking a folder contains expected files/subfolders. Extra entries are allowed (only listed in the failure details); the listing is not recursive.

asserts: exists · formats: directory · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Globs in dst (`glob_dst`)

**Does not support:**
- Files inside archives and compressed files (`archive_dst`): Only file members of an archive can be read, not its folders. Count the members with standard.file_count (`archive.zip!/folder/*`).

**Not for:**
- a folder holds exactly these entries and nothing else → `standard.file_count`
- how many files a folder holds → `standard.file_count`
- files deeper in the tree (recursive) → `standard.file_exists`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` | `''` | Guest path to the directory. A glob must match exactly one path, otherwise the test errors. A missing or unreadable directory is an execution error, not a failure. |
| files | `list` | `None` | Entry names (not paths) that must be present, compared exactly and case-sensitively against the directory listing. `None`/empty always passes. |

**Outcomes:**
- PASSED: every name in `files` is a direct entry of `dst` (extra entries are allowed); an empty `files` always passes
- FAILED: at least one name in `files` is not an entry of `dst` (the details also list the extra entries)
- ERROR: `dst` does not exist or is a file; a glob matches no path or more than one
- ERROR: the directory cannot be read (permission denied, I/O error)

**Limits:**
- Names, not paths; compared exactly and case-sensitively; the listing is not recursive.
- Extra entries never fail the test. For "nothing else" add standard.file_count with `kind: any` and the number of entries.
- Files and folders are not told apart; a listed name passes for either.

**Use cases:**
- An export or extract wrote all its parts: A folder holds the report, the data file and the images folder after an export.
- A project or profile was created: The expected files and subfolders of a new project or profile folder.

**Examples:**

*an export folder holds its parts* → PASSED. The extra `debug.log` does not fail the test.

```yaml
tests:
- name: an_export_folder_holds_its_parts
  function: standard.dir_content
  parameter:
    dst: /home/user/Documents/export
    files: [report.csv, images]
```

*a missing entry fails* → FAILED

```yaml
tests:
- name: a_missing_entry_fails
  function: standard.dir_content
  parameter:
    dst: /home/user/Documents/export
    files: [report.csv, summary.txt]
```

*a missing folder is an error, not a failure* → ERROR

```yaml
tests:
- name: a_missing_folder_is_an_error_not_a_failure
  function: standard.dir_content
  parameter:
    dst: /home/user/Documents/export
    files: [report.csv]
```

**Related:**
- `standard.file_count`: the number of entries, or that no entry matches a glob

## `standard.dir_does_not_exist`

tests if directory(ies) with path destination(dst) do NOT exist (supports glob patterns with match_mode)

Pass when no directory exists at `dst` (for globs: no match is a directory).

**Use for:** verifying a folder was removed or never created. Opposite: standard.dir_exists. A regular file at `dst` does not count as a directory, so it passes.

asserts: absent · formats: directory · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Globs in dst (`glob_dst`), Negative tests (absence) (`negative`)

**Does not support:**
- Files inside archives and compressed files (`archive_dst`): Only file members of an archive can be read. Assert that a folder in an archive is empty with standard.file_count (`archive.zip!/folder/*`, `expected_count: 0`).

**Not for:**
- a file was deleted → `standard.file_does_not_exist`
- the files inside a folder are gone but the folder stays → `standard.file_count`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` | `''` | Guest path; glob characters `* ? [ ]` expanded with Python `glob` (not recursive). |
| match_mode | `str` | `'any'` | `any` (default; anything except `single`): passes when zero matches are directories. `single`: a glob must match exactly one path, else the test ERRORS -- a glob with no matches errors instead of passing. Allowed: `any`, `single`. |

**Outcomes:**
- PASSED: nothing exists at `dst`, or `dst` is a file (a file is not a directory)
- PASSED: for a glob, no match is a directory (also when nothing matches)
- FAILED: `dst` (or a glob match) is a directory
- ERROR: `match_mode: single` with a glob that matches no path or more than one
- ERROR: the path cannot be examined (permission denied, I/O error)

**Limits:**
- A pass asserts absence: it is SUCCESS only when the run shows that the actions before it took effect, otherwise INCONCLUSIVE. Add a control test that proves the act.
- Keep `match_mode: any` for globs; `single` turns "no match" into an error.

**Use cases:**
- A folder was removed: An uninstall, a deleted project folder, a cleared cache folder.

**Examples:**

*a removed folder is absent* → PASSED

```yaml
tests:
- name: a_removed_folder_is_absent
  function: standard.dir_does_not_exist
  parameter:
    dst: /home/user/Projects/old_project
```

*a file at dst passes* → PASSED

```yaml
tests:
- name: a_file_at_dst_passes
  function: standard.dir_does_not_exist
  parameter:
    dst: /home/user/Projects/old_project
```

*an existing folder fails* → FAILED

```yaml
tests:
- name: an_existing_folder_fails
  function: standard.dir_does_not_exist
  parameter:
    dst: /home/user/Projects/old_project
```

**Related:**
- `standard.dir_exists`: the opposite assertion, often the control test that proves the folder existed

## `standard.dir_exists`

tests if directory(ies) with path destination(dst) exist (supports glob patterns with match_mode)

Pass when a directory exists at `dst` (for globs: at least one match is a directory).

**Use for:** verifying an install/extract step created a folder. Opposite: standard.dir_does_not_exist.

asserts: exists · formats: directory · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Globs in dst (`glob_dst`)

**Does not support:**
- Files inside archives and compressed files (`archive_dst`): Only file members of an archive can be read; a folder inside an archive is not found or is an error. Test a file inside it with standard.file_exists.

**Not for:**
- a folder holds given files → `standard.dir_content`
- how many folders match a glob → `standard.file_count`
- a file exists → `standard.file_exists`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` | `''` | Guest path to the directory; glob characters `* ? [ ]` expanded with Python `glob` (not recursive). A path that exists but is a file fails. |
| match_mode | `str` | `'any'` | `any` (default; anything except `single`): passes if one match is a directory. `single`: a glob must match exactly one path, else the test ERRORS. Allowed: `any`, `single`. |

**Outcomes:**
- PASSED: `dst` is a directory; for a glob, at least one match is a directory
- FAILED: nothing exists at `dst` or no glob match is a directory
- FAILED: `dst` (or every match) is a file
- ERROR: `match_mode: single` with a glob that matches no path or more than one
- ERROR: the path cannot be examined (permission denied, I/O error)

**Limits:**
- Globs use Python `glob`: not recursive, `*` skips dotfiles.

**Use cases:**
- A folder was created: An install or extract step, a new profile folder, a folder made in a file manager.

**Examples:**

*a profile folder exists* → PASSED

```yaml
tests:
- name: a_profile_folder_exists
  function: standard.dir_exists
  parameter:
    dst: /home/user/.config/app/profile
```

*a profile folder with a random name* → PASSED

```yaml
tests:
- name: a_profile_folder_with_a_random_name
  function: standard.dir_exists
  parameter:
    dst: /home/user/.config/app/*.default
```

*a file is not a directory* → FAILED

```yaml
tests:
- name: a_file_is_not_a_directory
  function: standard.dir_exists
  parameter:
    dst: /home/user/.config/app/profile
```

**Related:**
- `standard.dir_does_not_exist`: the opposite assertion

## `standard.file_content_contains`

tests if file content contains specified string or byte pattern

Pass when file `dst` contains `content` as a substring (text) or byte sequence.

**Use for:** checking a value/marker was written into a file. For patterns use standard.file_content_matches_regex; to count occurrences, search several encodings at once or assert a value is gone from a binary file use text.occurrence_count.

asserts: content · formats: text, file · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Text encodings (`encoding`)

**Does not support:**
- Regex values (!re) (`regex_tag`): A `!re` or `!timestamp` placeholder in `content` is an error; use standard.file_content_matches_regex.
- Times as expected values (!timestamp) (`timestamp_tag`): A `!timestamp` placeholder in `content` is an error; `content` is plain text.

**Not for:**
- a value occurs n times, or was wiped (expected_count 0) → `text.occurrence_count`
- a string in a binary file or in several encodings at once → `text.occurrence_count`
- a pattern (regex) → `standard.file_content_matches_regex`
- how many lines contain a string → `text.line_count`
- a trace in the last lines of a log → `linux.log_entry_exists`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` | `''` | Guest path to the file. A glob must match exactly one path, otherwise the test errors. A missing file is an error. |
| **content** | `str` | `''` | Text to find (case-sensitive). An empty value always passes. In `bytes` mode ASCII characters stand for their byte and Python escapes (`\x00`, `\n`, `\\`) are decoded; a non-ASCII character or an unknown escape is an error (write `\xNN`, or use `string` mode with an `encoding`). |
| content_type | `str` | `'string'` | `string` (default) searches the decoded text, `bytes` the raw file bytes; other values are an error. A `!re`/`!timestamp` placeholder in `content` is an error (use standard.file_content_matches_regex). Allowed: `string`, `bytes`. |
| encoding | `str` | `'utf-8'` | Codec for `string` mode; undecodable bytes are silently dropped. `BOM` detects UTF-8/16/32 from the byte-order mark and errors if there is none. |
| strip_bom | `bool` | `False` | Remove a leading U+FEFF from the decoded text (`string` mode only). |

**Outcomes:**
- PASSED: `content` occurs in the decoded text (`string`) or in the raw bytes (`bytes`); an empty `content` always passes
- FAILED: the file was read and `content` does not occur
- ERROR: the file does not exist; a glob matches no file or more than one
- ERROR: an unknown `content_type`; a `!re` / `!timestamp` placeholder in `content`
- ERROR: `bytes` mode with a non-ASCII character or an unknown escape in `content`
- ERROR: `encoding: BOM` and the file has no byte-order mark
- ERROR: the file cannot be read (permission denied, I/O error)

**Limits:**
- Case-sensitive, one encoding per test. In `string` mode bytes not valid in `encoding` are dropped silently, so text in another encoding is not found (a failure, not an error).
- In `bytes` mode `content` holds ASCII characters and Python escapes (`\x00`, `\n`, `\\`); write `\xNN` for every other byte.
- A failure does not prove absence in other encodings; for "the value is gone" use text.occurrence_count with `expected_count: 0`.

**Use cases:**
- A value was written into a text file: A history line, a log message, a setting or a marker in a configuration file.
- A byte signature: `content_type: bytes` with escapes, e.g. a NUL-terminated name `admin\x00`.

**Examples:**

*a command in the shell history* → PASSED

```yaml
tests:
- name: a_command_in_the_shell_history
  function: standard.file_content_contains
  parameter:
    dst: /home/user/.bash_history
    content: rm -rf ~/evidence
```

*a NUL-terminated name in a binary file* → PASSED

```yaml
tests:
- name: a_nul_terminated_name_in_a_binary_file
  function: standard.file_content_contains
  parameter:
    dst: /home/user/app/state.bin
    content: 'admin\x00'
    content_type: bytes
```

*UTF-16 text with the matching encoding* → PASSED

```yaml
tests:
- name: utf_16_text_with_the_matching_encoding
  function: standard.file_content_contains
  parameter:
    dst: C:\Users\user\app\log.txt
    content: Service started
    encoding: utf-16-le
```

*UTF-16 text is not found in the default utf-8* → FAILED. The NUL bytes of UTF-16 stay in the decoded text, so the string does not occur. text.occurrence_count searches several encodings at once.

```yaml
tests:
- name: utf_16_text_is_not_found_in_the_default_utf_8
  function: standard.file_content_contains
  parameter:
    dst: C:\Users\user\app\log.txt
    content: Service started
```

*an unknown escape in bytes mode is an error* → ERROR

```yaml
tests:
- name: an_unknown_escape_in_bytes_mode_is_an_error
  function: standard.file_content_contains
  parameter:
    dst: /home/user/app/state.bin
    content: 'admin\q'
    content_type: bytes
```

*a regex placeholder is an error* → ERROR

```yaml
tests:
- name: a_regex_placeholder_is_an_error
  function: standard.file_content_contains
  parameter:
    dst: /home/user/.bash_history
    content: !re 'rm -rf .*'
```

**Related:**
- `text.occurrence_count`: counts, searches several encodings at once and asserts absence

## `standard.file_content_equals`

tests if file content equals the given content

Pass when the text of file `dst` equals `content` (leading/trailing whitespace ignored).

**Use for:** exact output checks, e.g. a tool's exit code or a saved text document. That a file is empty: standard.file_size with `expected_size: 0`.

asserts: content, value · formats: text · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Text encodings (`encoding`), Placeholders ({{ variable }}) (`placeholder`), Regex values (!re) (`regex_tag`), Times as expected values (!timestamp) (`timestamp_tag`)

**Not for:**
- a file is empty → `standard.file_size`
- a file is byte-identical to a known one (binary files) → `standard.file_hash_matches`
- a value or marker somewhere in the file → `standard.file_content_contains`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` | `''` | Guest path to the file. A glob must match exactly one path, otherwise the test errors. A missing file is an error; a failure includes a unified diff. |
| **content** | `str` | `''` | Expected text. Both sides are `strip()`-ed; inner whitespace must match (line endings are normalised to `\n` by text-mode reading). `!re`/`!timestamp` tags inside the value become placeholders matched by type; the literal text around them must match exactly. An invalid `!re` regex is an error even when the text around it does not match. |
| encoding | `str` | `'utf-8'` | Python codec used to decode the file (strict). `BOM` detects UTF-8/16/32 from the byte-order mark and errors if there is none. |
| strip_bom | `bool` | `False` | Remove a leading U+FEFF from the decoded text before comparing. |

**Outcomes:**
- PASSED: the decoded text equals `content` after both are stripped of leading and trailing whitespace
- FAILED: the file was read and the text differs (the details hold a unified diff)
- ERROR: the file does not exist; a glob matches no file or more than one
- ERROR: bytes not valid in `encoding`; `encoding: BOM` and the file has no byte-order mark
- ERROR: the file cannot be read (permission denied, I/O error)

**Limits:**
- Inner whitespace must match; line endings are read as `\n`.
- A leading byte-order mark is part of the text unless `strip_bom` is set or `encoding` removes it (`utf-8-sig`, `BOM`).
- Decoding is strict; a file in another encoding is an error, not a failure.
- A variable defined with `!re` or `!timestamp` and used as `{{ name }}` in `content` matches by type; the text around it must match exactly.

**Use cases:**
- The exact output of a command or export: An exit code, a status word or a small generated text file.
- Output with a variable part: A line with a user name or time stamp, as `{{ name }}` in `content`.

**Examples:**

*an exit code file* → PASSED. The trailing line break is stripped from both sides.

```yaml
tests:
- name: an_exit_code_file
  function: standard.file_content_equals
  parameter:
    dst: /home/user/out/exit_code.txt
    content: '0'
```

*Windows line endings compare as \n* → PASSED

```yaml
tests:
- name: windows_line_endings_compare_as_n
  function: standard.file_content_equals
  parameter:
    dst: C:\Users\user\out\status.txt
    content: "done\nexported 3 files"
```

*a UTF-8 file with a byte-order mark* → PASSED

```yaml
tests:
- name: a_utf_8_file_with_a_byte_order_mark
  function: standard.file_content_equals
  parameter:
    dst: C:\Users\user\out\status.txt
    content: done
    strip_bom: true
```

*a variable part from a playbook variable* → PASSED. `{{ username }}` is replaced before the test runs; a variable defined with `!re` matches by pattern.

```yaml
tests:
- name: a_variable_part_from_a_playbook_variable
  function: standard.file_content_equals
  parameter:
    dst: /home/user/out/owner.txt
    content: 'exported by {{ username }}'
```

*different inner whitespace fails* → FAILED

```yaml
tests:
- name: different_inner_whitespace_fails
  function: standard.file_content_equals
  parameter:
    dst: /home/user/out/status.txt
    content: exported 3 files
```

*a missing file is an error, not a failure* → ERROR

```yaml
tests:
- name: a_missing_file_is_an_error_not_a_failure
  function: standard.file_content_equals
  parameter:
    dst: /home/user/out/result.txt
    content: '0'
```

## `standard.file_content_matches_regex`

tests if file content matches a given regex expression

Pass when the regex `regex` is found anywhere in the text of file `dst`.

**Use for:** loose content checks (a value appears, a line has a given shape). For exact content use standard.file_content_equals; for a plain substring standard.file_content_contains.

asserts: content · formats: text · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Text encodings (`encoding`)

**Not for:**
- a plain substring → `standard.file_content_contains`
- exactly this content → `standard.file_content_equals`
- how many lines match a regex → `text.line_count`
- a value in a settings or structured file → `json.value_matches`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` | `''` | Guest path to the file. A glob must match exactly one path, otherwise the test errors. A missing file is an error. |
| **regex** | `str` | `''` | Python `re` pattern applied with `re.search` to the whole file. Default flags: case-sensitive, `^`/`$` match only file start/end; use inline flags such as `(?im)`. An empty pattern always passes; an invalid one errors. |
| encoding | `str` | `'utf-8'` | Python codec used to decode the file (strict: undecodable bytes error). `BOM` detects UTF-8/16/32 from the byte-order mark and errors if there is none. |
| strip_bom | `bool` | `False` | Remove a leading U+FEFF from the decoded text before matching. |

**Outcomes:**
- PASSED: `re.search` finds `regex` in the decoded text; an empty `regex` always passes
- FAILED: the file was read and the regex does not match
- ERROR: the file does not exist; a glob matches no file or more than one
- ERROR: an invalid regex
- ERROR: bytes not valid in `encoding`; `encoding: BOM` and the file has no byte-order mark
- ERROR: the file cannot be read (permission denied, I/O error)

**Limits:**
- The whole file is one string: `^` / `$` match only at its start and end and `.` does not match a line break. Use inline flags: `(?m)` for lines, `(?s)` to cross lines, `(?i)` to ignore case.
- Decoding is strict; a file in another encoding is an error, not a failure.

**Use cases:**
- A line has a given shape: A log line with a user name and a number, a version string, a setting with any value.
- A value whose exact text is not known: Dates, counters, generated IDs inside a text file.

**Examples:**

*a total line in a report* → PASSED

```yaml
tests:
- name: a_total_line_in_a_report
  function: standard.file_content_matches_regex
  parameter:
    dst: /home/user/notes.txt
    regex: '(?m)^Total: [0-9]+$'
```

*without (?m) ^ matches only at the start of the file* → FAILED

```yaml
tests:
- name: without_m_matches_only_at_the_start_of_the_file
  function: standard.file_content_matches_regex
  parameter:
    dst: /home/user/notes.txt
    regex: '^Total: [0-9]+$'
```

*a UTF-16 file found by its byte-order mark* → PASSED

```yaml
tests:
- name: a_utf_16_file_found_by_its_byte_order_mark
  function: standard.file_content_matches_regex
  parameter:
    dst: C:\Users\user\Documents\log.txt
    regex: 'version [0-9]+\.[0-9]+\.[0-9]+'
    encoding: BOM
```

*a file in another encoding is an error* → ERROR. UTF-16 bytes are not valid UTF-8, so the default `encoding` cannot read the file.

```yaml
tests:
- name: a_file_in_another_encoding_is_an_error
  function: standard.file_content_matches_regex
  parameter:
    dst: C:\Users\user\Documents\log.txt
    regex: version
```

*an invalid regex is an error* → ERROR

```yaml
tests:
- name: an_invalid_regex_is_an_error
  function: standard.file_content_matches_regex
  parameter:
    dst: /home/user/notes.txt
    regex: 'Total: [0-9'
```

## `standard.file_count`

tests the number of files (or directories) matching a path or glob

Pass when the number of paths matching `dst` that are of `kind` satisfies `comparison_type`.

**Use for:** how many files an application wrote (exactly 3 logs, at least one export) and absence of a whole group of files: `expected_count: 0`. One file: standard.file_exists.

asserts: count, exists, absent · formats: file, directory · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Counts with a comparison (`count_comparison`), Negative tests (absence) (`negative`)

**Not for:**
- one file exists → `standard.file_exists`
- a folder holds files with given names → `standard.dir_content`
- how often a value occurs inside a file → `text.occurrence_count`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path or glob (Python `glob`, not recursive: `**` acts like `*`; `*` skips dotfiles), e.g. `/home/user/logs/*.log`. No match counts 0, it is not an error; an empty `dst` or an unresolved `{{placeholder}}` is. Inside an archive (`a.zip!/logs/*.log`) the matching file members are counted; the archive itself must exist and be readable, otherwise an error. |
| **expected_count** | `int` |  | Non-negative integer to compare against; anything else is an error. |
| comparison_type | `str` | `'equals'` | `equals` (default), `greater`, `less`, `greater_equal` or `less_equal`; other values are an error. Allowed: `equals`, `greater`, `less`, `greater_equal`, `less_equal`. |
| kind | `str` | `'file'` | `file` (default): regular files (also through a symlink); `dir`: directories; `any`: every existing path. Archives have file members only, so `dir` with an archive path is an error. Allowed: `file`, `dir`, `any`. |

**Outcomes:**
- PASSED: the number of paths matching `dst` that are of `kind` satisfies `comparison_type`; no match counts 0
- FAILED: the paths were examined and the count comparison does not hold (also when nothing matches and `expected_count` is above 0)
- ERROR: an empty `dst` or one with an unresolved `{{ placeholder }}`
- ERROR: a negative or non-integer `expected_count`; an unknown `comparison_type` or `kind`
- ERROR: `kind: dir` with an archive path
- ERROR: an archive that is missing or cannot be read (also an archive glob that matches a link member)
- ERROR: in host test mode, a failed guest listing

**Limits:**
- Globs use Python `glob`: not recursive (`**` acts like `*`), `*` skips dotfiles (write `.*` to count them).
- `kind: file` counts regular files, also through a symlink; `any` counts every existing path, broken symlinks included.
- In host test mode the guest lists the matching paths and their kinds; no file is pulled, so a copy pulled by an earlier test is never counted.
- Inside an archive only file members are counted, never folders.

**Use cases:**
- How many files were written: Exactly three exports, at least one rotated log, one file inside an archive.
- A group of files is gone: `expected_count: 0` on a glob: cleared cache or temporary files, the content of a deleted folder.

**Examples:**

*three exports written* → PASSED

```yaml
tests:
- name: three_exports_written
  function: standard.file_count
  parameter:
    dst: /home/user/Documents/export-*.csv
    expected_count: 3
```

*no temporary files left* → PASSED

```yaml
tests:
- name: no_temporary_files_left
  function: standard.file_count
  parameter:
    dst: /home/user/.cache/app/*.tmp
    expected_count: 0
```

** skips dotfiles* → PASSED. The hidden `.lock.tmp` is not matched by `*.tmp`; write `.*.tmp` to count it.

```yaml
tests:
- name: skips_dotfiles
  function: standard.file_count
  parameter:
    dst: /home/user/.cache/app/*.tmp
    expected_count: 0
```

*profile folders* → PASSED

```yaml
tests:
- name: profile_folders
  function: standard.file_count
  parameter:
    dst: /home/user/.config/app/*.default*
    expected_count: 2
    kind: dir
```

*logs inside a backup archive* → PASSED

```yaml
tests:
- name: logs_inside_a_backup_archive
  function: standard.file_count
  parameter:
    dst: /home/user/backup.zip!/logs/*.log
    expected_count: 1
    comparison_type: greater_equal
```

*a different count fails* → FAILED

```yaml
tests:
- name: a_different_count_fails
  function: standard.file_count
  parameter:
    dst: /home/user/Documents/export-*.csv
    expected_count: 3
```

*a missing archive is an error, not zero members* → ERROR

```yaml
tests:
- name: a_missing_archive_is_an_error_not_zero_members
  function: standard.file_count
  parameter:
    dst: /home/user/backup.zip!/logs/*.log
    expected_count: 0
```

*folders inside an archive are an error* → ERROR

```yaml
tests:
- name: folders_inside_an_archive_are_an_error
  function: standard.file_count
  parameter:
    dst: /home/user/backup.zip!/*
    expected_count: 0
    kind: dir
```

**Related:**
- `standard.file_size`: the size of one file

## `standard.file_does_not_exist`

tests if file(s) with path destination(dst) do NOT exist (supports glob patterns with match_mode)

Pass when no regular file exists at `dst` (for globs: no match is a file).

**Use for:** verifying a file was deleted or never written. Opposite: standard.file_exists. A directory at `dst` does not count as a file, so it passes.

asserts: absent · formats: file · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Negative tests (absence) (`negative`)

**Not for:**
- a whole group of files is gone, or fewer than n are left → `standard.file_count`
- a value was wiped from a file that still exists → `text.occurrence_count`
- a folder was removed → `standard.dir_does_not_exist`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` | `''` | Guest path; glob characters `* ? [ ]` expanded with Python `glob` (not recursive). Case sensitivity follows the guest filesystem. |
| match_mode | `str` | `'any'` | `any` (default; anything except `single`): passes when zero matches are files. `single`: a glob must match exactly one path, else the test ERRORS -- so a glob with no matches errors instead of passing; keep `any` for globs. Allowed: `any`, `single`. |

**Outcomes:**
- PASSED: nothing exists at `dst`, or `dst` is a directory (a directory is not a file)
- PASSED: for a glob, no match is a regular file (also when nothing matches)
- PASSED: for an archive path, the archive has no such member
- FAILED: `dst` (or a glob match) is a regular file
- ERROR: `match_mode: single` with a glob that matches no path or more than one
- ERROR: an archive that is missing or cannot be read
- ERROR: the path cannot be examined (permission denied, I/O error)

**Limits:**
- A pass asserts absence: it is SUCCESS only when the run shows that the actions before it took effect, otherwise INCONCLUSIVE. Add a control test that proves the act.
- Keep `match_mode: any` for globs; `single` turns "no match" into an error.
- Globs use Python `glob`: not recursive, `*` skips dotfiles.

**Use cases:**
- A file was deleted: A document deleted in a file manager, a temporary file cleaned up, a file moved away from its old place.
- A file was never written: A private mode or a setting that should keep an application from writing a cache or history file.

**Examples:**

*a deleted file is absent* → PASSED

```yaml
tests:
- name: a_deleted_file_is_absent
  function: standard.file_does_not_exist
  parameter:
    dst: /home/user/Documents/secret.txt
```

*a glob without matches passes* → PASSED

```yaml
tests:
- name: a_glob_without_matches_passes
  function: standard.file_does_not_exist
  parameter:
    dst: /home/user/.cache/app/*.tmp
```

*a member removed from an archive* → PASSED

```yaml
tests:
- name: a_member_removed_from_an_archive
  function: standard.file_does_not_exist
  parameter:
    dst: /home/user/backup.zip!/notes/secret.txt
```

*a directory at dst passes* → PASSED. Only regular files count; to assert that a folder is gone use standard.dir_does_not_exist.

```yaml
tests:
- name: a_directory_at_dst_passes
  function: standard.file_does_not_exist
  parameter:
    dst: /home/user/Documents/secret
```

*an existing file fails* → FAILED

```yaml
tests:
- name: an_existing_file_fails
  function: standard.file_does_not_exist
  parameter:
    dst: /home/user/Documents/secret.txt
```

*match_mode single with a glob without matches is an error* → ERROR

```yaml
tests:
- name: match_mode_single_with_a_glob_without_matches_is
  function: standard.file_does_not_exist
  parameter:
    dst: /home/user/.cache/app/*.tmp
    match_mode: single
```

**Related:**
- `standard.file_exists`: the opposite assertion, often the control test that proves the file existed before

## `standard.file_exists`

tests if file(s) with path destination(dst) exist (supports glob patterns with match_mode)

Pass when a regular file exists at `dst` (for globs: at least one match is a file).

**Use for:** verifying a GUI action created/saved a file. Opposite: standard.file_does_not_exist. How many files match a glob: standard.file_count; an empty file: standard.file_size.

asserts: exists · formats: file · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`)

**Not for:**
- a file was deleted or never written → `standard.file_does_not_exist`
- how many files match a glob (exactly 3, at least one, none left) → `standard.file_count`
- a file is empty or non-empty → `standard.file_size`
- a folder exists → `standard.dir_exists`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` | `''` | Guest path to the file. Glob characters `* ? [ ]` are expanded with Python `glob` (not recursive: `**` acts like `*`; `*` skips dotfiles), e.g. `C:/Users/*/Desktop/*.txt`. Case sensitivity follows the guest filesystem. A path that exists but is a directory fails. |
| match_mode | `str` | `'any'` | `any` (default; any value except `single` behaves the same): passes if at least one match is a regular file. `single`: a glob must match exactly one path, otherwise the test ERRORS (not fails). Allowed: `any`, `single`. |

**Outcomes:**
- PASSED: `dst` is a regular file; for a glob, at least one match is a regular file
- FAILED: nothing exists at `dst` or no glob match is a file
- FAILED: `dst` (or every match) is a directory
- FAILED: `match_mode: single`: the one match is not a file
- ERROR: `match_mode: single` with a glob that matches no path or more than one
- ERROR: an archive that is missing or cannot be read; a member that is a directory or a link
- ERROR: the path cannot be examined (permission denied, I/O error)

**Limits:**
- Globs use Python `glob`: not recursive (`**` acts like `*`), `*` skips dotfiles; case sensitivity follows the guest file system.
- Any `match_mode` other than `single` behaves like `any`.
- An empty file passes; for "non-empty" use standard.file_size.

**Use cases:**
- A file was created or saved: A document saved, a log or cache file created, a download finished after a GUI action.
- A file whose name changes: A glob (`export-*.csv`, `C:/Users/*/Desktop/*.txt`) for names with a date or a random part.
- A file inside a backup or export archive: `backup.zip!/notes/todo.txt` checks a member without extracting it in a `run` action.

**Examples:**

*a saved document exists* → PASSED

```yaml
tests:
- name: a_saved_document_exists
  function: standard.file_exists
  parameter:
    dst: /home/user/Documents/report.txt
```

*a glob with several matches passes* → PASSED. In the default `match_mode` (`any`) one matching file is enough.

```yaml
tests:
- name: a_glob_with_several_matches_passes
  function: standard.file_exists
  parameter:
    dst: /home/user/Documents/export-*.csv
```

*a member of an archive* → PASSED

```yaml
tests:
- name: a_member_of_an_archive
  function: standard.file_exists
  parameter:
    dst: /home/user/backup.zip!/notes/todo.txt
```

*a missing file fails* → FAILED

```yaml
tests:
- name: a_missing_file_fails
  function: standard.file_exists
  parameter:
    dst: /home/user/Documents/draft.txt
```

*a directory is not a file* → FAILED

```yaml
tests:
- name: a_directory_is_not_a_file
  function: standard.file_exists
  parameter:
    dst: /home/user/Documents/export
```

*match_mode single with several matches is an error* → ERROR. The test cannot tell which file is meant, so it does not fail but errors.

```yaml
tests:
- name: match_mode_single_with_several_matches_is_an_err
  function: standard.file_exists
  parameter:
    dst: /home/user/Documents/export-*.csv
    match_mode: single
```

**Related:**
- `standard.file_count`: when the number of matching files matters

## `standard.file_hash_matches`

tests if file hash matches expected value

Pass when the `hash_type` digest of file `dst` equals `expected_hash`.

**Use for:** verifying a file is byte-identical to a known artifact.

asserts: content · formats: file · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`)

**Not for:**
- the text of a file, ignoring surrounding whitespace → `standard.file_content_equals`
- a file is empty → `standard.file_size`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` | `''` | Guest path to the file. A glob must match exactly one path, otherwise the test errors. A missing file is an error. |
| **expected_hash** | `str` | `''` | Hex digest; compared case-insensitively but otherwise exactly (no whitespace stripping, no prefix such as `sha256:`). |
| hash_type | `str` | `'sha256'` | `md5`, `sha1`, `sha256` (default) or `sha512` (case-insensitive); anything else is an execution error. Allowed: `md5`, `sha1`, `sha256`, `sha512`. |

**Outcomes:**
- PASSED: the `hash_type` digest of the file equals `expected_hash` (case-insensitive)
- FAILED: the file was hashed and the digest differs (also for a prefix such as `sha256:` or surrounding spaces)
- ERROR: the file does not exist; a glob matches no file or more than one
- ERROR: an unknown `hash_type`
- ERROR: the file cannot be read (permission denied, I/O error)

**Limits:**
- `expected_hash` is the bare hex digest: no prefix, no whitespace.
- An archive member (`a.zip!/x`, `x.gz!`) is hashed as extracted or decompressed content.

**Use cases:**
- A file is byte-identical to a known one: A download, a restored backup or a copied file matches its published or original checksum.
- A file was not modified: The digest taken before an action still matches after it.

**Examples:**

*a downloaded installer matches its SHA-256* → PASSED

```yaml
tests:
- name: a_downloaded_installer_matches_its_sha_256
  function: standard.file_hash_matches
  parameter:
    dst: C:\Users\user\Downloads\setup.bin
    expected_hash: 910B575269DAF86A6BD5661C3BC185EBE5A736891155CE307EBC516E091BFE19
```

*an MD5 of a compressed file's content* → PASSED. `x.gz!` is the decompressed content.

```yaml
tests:
- name: an_md5_of_a_compressed_file_s_content
  function: standard.file_hash_matches
  parameter:
    dst: /home/user/backup/setup.bin.gz!
    expected_hash: d982352c042e4e61711114024f3df98a
    hash_type: md5
```

*a prefixed digest fails* → FAILED

```yaml
tests:
- name: a_prefixed_digest_fails
  function: standard.file_hash_matches
  parameter:
    dst: C:\Users\user\Downloads\setup.bin
    expected_hash: sha256:910b575269daf86a6bd5661c3bc185ebe5a736891155ce307ebc516e091bfe19
```

*a missing file is an error, not a failure* → ERROR

```yaml
tests:
- name: a_missing_file_is_an_error_not_a_failure
  function: standard.file_hash_matches
  parameter:
    dst: C:\Users\user\Downloads\setup2.bin
    expected_hash: 910b575269daf86a6bd5661c3bc185ebe5a736891155ce307ebc516e091bfe19
```

## `standard.file_permissions`

tests file permissions, owner, and group

Pass when the permission bits (and optional owner/group) of `dst` match exactly.

**Use for:** Unix mode/ownership checks after chmod/chown or a file save. Only meaningful on Linux guests: Windows reports synthetic mode bits and no owner/group (owner checks fail).

asserts: metadata · formats: file, directory · runs: guest agent or host test mode; hostside; no dry-run · os: any

**Supports:** Globs in dst (`glob_dst`)

**Does not support:**
- Files inside archives and compressed files (`archive_dst`): An archive member would be a temporary extracted copy with its own mode and owner, so an archive path is an error (in the guest agent and in host test mode); name the archive file itself.

**Not for:**
- a file exists → `standard.file_exists`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` | `''` | Guest path to the file or directory. A glob must match exactly one path, otherwise the test errors. A missing path is an error, and so is an archive member (its mode and owner would be those of a temporary extracted copy). |
| **expected_permissions** | `str` | `''` | Octal digits (`'644'`, `'0755'`) or 9-char symbolic (`rwxr-xr-x`), compared with `st_mode & 0o777` (no setuid/sticky). Quote it in YAML (unquoted `0644` is read as decimal 420). Empty/invalid values error. |
| check_owner | `str` | `None` | Expected owner user name (not UID); `None` skips the check. |
| check_group | `str` | `None` | Expected group name (not GID); `None` skips the check. |

**Outcomes:**
- PASSED: `st_mode & 0o777` equals `expected_permissions` and the given owner and group match
- FAILED: the path was examined and the mode, owner or group differs (each is listed)
- ERROR: the path does not exist; a glob matches no path or more than one
- ERROR: an empty or invalid `expected_permissions`
- ERROR: the path cannot be examined (permission denied, I/O error)

**Limits:**
- Linux guests only. Windows reports synthetic mode bits and no owner or group, so such checks fail.
- Only the nine permission bits; setuid, setgid and sticky are ignored.
- Quote `expected_permissions` in YAML: unquoted `0644` is read as the decimal number 420.
- Owner and group are names, not numeric ids.

**Use cases:**
- A private file stays private: A key or credential file has mode `600` and belongs to the user.
- A script was made executable: Mode `755` after a `chmod` or a save with the executable flag.

**Examples:**

*a private key readable only by its owner* → PASSED

```yaml
tests:
- name: a_private_key_readable_only_by_its_owner
  function: standard.file_permissions
  parameter:
    dst: /home/user/.ssh/id_ed25519
    expected_permissions: '600'
    check_owner: user
```

*symbolic notation with a group* → PASSED

```yaml
tests:
- name: symbolic_notation_with_a_group
  function: standard.file_permissions
  parameter:
    dst: /var/log/app.log
    expected_permissions: rw-r-----
    check_group: adm
```

## `standard.file_size`

tests the size of a file in bytes

Pass when the size in bytes of file `dst` satisfies `comparison_type` against `expected_size`.

**Use for:** checking a file is empty (`expected_size: 0`), non-empty (`greater` 0) or grew/shrank past a threshold. Existence alone: standard.file_exists.

asserts: content · formats: file · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`)

**Not for:**
- a file exists, whatever its size → `standard.file_exists`
- how many files match a glob → `standard.file_count`
- a value is still inside the file → `text.occurrence_count`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the file. A glob must match exactly one path; a missing file or a directory is an error. An archive member (`a.zip!/p/x.db`) has its extracted size. |
| **expected_size** | `int` |  | Non-negative integer number of bytes; anything else is an error. |
| comparison_type | `str` | `'equals'` | `equals` (default), `greater`, `less`, `greater_equal` or `less_equal`; other values are an error. Allowed: `equals`, `greater`, `less`, `greater_equal`, `less_equal`. |

**Outcomes:**
- PASSED: the size in bytes satisfies `comparison_type` against `expected_size`
- FAILED: the file was examined and the size comparison does not hold
- ERROR: the file does not exist or is a directory; a glob matches no file or more than one
- ERROR: a negative or non-integer `expected_size`; an unknown `comparison_type`
- ERROR: the file cannot be examined (permission denied, I/O error)

**Limits:**
- An archive member has its extracted size, a compressed file (`x.gz!`) its decompressed size.

**Use cases:**
- An empty file: `expected_size: 0` shows that a file was truncated or created empty but still exists (a missing file is an error).
- A file grew or shrank: `comparison_type: greater` after an action that appends to a log or database.

**Examples:**

*a cache file was emptied* → PASSED

```yaml
tests:
- name: a_cache_file_was_emptied
  function: standard.file_size
  parameter:
    dst: /home/user/data/cache.bin
    expected_size: 0
```

*a log was written* → PASSED

```yaml
tests:
- name: a_log_was_written
  function: standard.file_size
  parameter:
    dst: /home/user/data/app.log
    expected_size: 0
    comparison_type: greater
```

*the extracted size of an archive member* → PASSED

```yaml
tests:
- name: the_extracted_size_of_an_archive_member
  function: standard.file_size
  parameter:
    dst: /home/user/backup.zip!/notes/todo.txt
    expected_size: 10
```

*a non-empty file is not empty* → FAILED

```yaml
tests:
- name: a_non_empty_file_is_not_empty
  function: standard.file_size
  parameter:
    dst: /home/user/data/cache.bin
    expected_size: 0
```

*a missing file is an error, never an empty one* → ERROR

```yaml
tests:
- name: a_missing_file_is_an_error_never_an_empty_one
  function: standard.file_size
  parameter:
    dst: /home/user/data/cache.bin
    expected_size: 0
```

**Related:**
- `standard.file_count`: how many files match a glob

## `standard.file_timestamps`

tests file timestamps with various comparison types and formats

Pass when the chosen timestamp of file `dst` satisfies `comparison_type`.

**Use for:** MACB timestamp assertions (modified recently, accessed after an action, ...).

asserts: metadata, order · formats: file · runs: guest agent or host test mode; hostside; no dry-run · os: any

**Supports:** Globs in dst (`glob_dst`)

**Does not support:**
- Files inside archives and compressed files (`archive_dst`): An archive member would be a temporary extracted copy with its own times, so an archive path is an error (in the guest agent and in host test mode); name the archive file itself.
- Times as expected values (!timestamp) (`timestamp_tag`): `expected_time`, `start_time` and `end_time` are epoch seconds or date strings, not `!timestamp` tags.
- Ordered comparison of numbers and times (`ordered_comparison`): `comparison_type` here is `equals`, `before`, `after`, `between` or `within_last` (see choices), with `tolerance_seconds`.

**Not for:**
- a time stored inside a file (a database column, a JSON field) → `json.value_matches`
- a time stored at an offset of a binary file → `binary.struct_value_matches`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` | `''` | Guest path to the file. A glob must match exactly one path, otherwise the test errors. A missing file is an error, and so is an archive member (`a.zip!/x`): its times would be those of a temporary extracted copy. |
| timestamp_type | `str` | `'modified'` | `modified` (mtime, default), `accessed` (atime) or `created`: creation time on Windows; elsewhere `st_birthtime` if Python exposes it, else `st_ctime` (inode change time on Linux). Other values error. Allowed: `modified`, `accessed`, `created`. |
| comparison_type | `str` | `'equals'` | `equals` (default, within `tolerance_seconds`), `before` / `after` (strict, vs `expected_time`), `between` (inclusive, `start_time`.. `end_time`) or `within_last` (`within_duration` before the guest's now). Allowed: `equals`, `before`, `after`, `between`, `within_last`. |
| expected_time | `str \| int \| float` | `None` | Reference for equals/before/after: Unix epoch seconds or a date string (see `time_format`). Naive strings are read in the guest's local timezone (the trailing `Z` format too). Missing/unparseable values error. |
| time_format | `str` | `None` | `strptime` format tried first; then `%Y-%m-%d %H:%M:%S`, `%Y-%m-%dT%H:%M:%S`, `%Y-%m-%dT%H:%M:%SZ`, `%Y-%m-%d`, `%m/%d/%Y %H:%M:%S`, `%m/%d/%Y`. |
| tolerance_seconds | `int` | `None` | Allowed absolute difference for `equals`; `None` means 0, which rarely matches sub-second filesystem times. |
| start_time | `str \| int \| float` | `None` | Lower bound for `between` (same formats as `expected_time`). |
| end_time | `str \| int \| float` | `None` | Upper bound for `between`. |
| within_duration | `str` | `None` | For `within_last`: integer plus unit `s`/`m`/`h`/`d`, e.g. `15m`. |

**Outcomes:**
- PASSED: the chosen timestamp satisfies `comparison_type`
- FAILED: the timestamp was read and the comparison does not hold
- ERROR: the file does not exist; a glob matches no file or more than one
- ERROR: a missing or unparseable `expected_time` / `start_time` / `end_time` / `within_duration`
- ERROR: an unknown `timestamp_type` or `comparison_type`

**Limits:**
- `created` is the creation time on Windows; on Linux guests it is the inode change time (ctime), not a birth time.
- Date strings without a zone are read in local time, a trailing `Z` too; epoch seconds avoid the ambiguity.
- `equals` without `tolerance_seconds` means 0 s, which rarely matches sub-second file system times.
- `before` / `after` are strict, `between` includes both bounds.
- In host test mode the times come from a guest command, and the guest clock and time zone (QGA) stand for "now" and for date strings without a zone, as in the agent. If the guest does not answer, the host clock and zone are used and the result says so. In the hostside backend the times are the image's inode times, "now" is the host clock and the zone is the image's.
- Access times are often not updated (`relatime`, `noatime`, Windows defaults).

**Use cases:**
- A file was modified by the action: `within_last` right after the action, or `between` the times saved around it.
- A file was not touched: `before` the start of the action.

**Examples:**

*modified in the last ten minutes* → PASSED

```yaml
tests:
- name: modified_in_the_last_ten_minutes
  function: standard.file_timestamps
  parameter:
    dst: /home/user/Documents/report.odt
    comparison_type: within_last
    within_duration: 10m
```

*created at a known time, within 30 seconds* → PASSED

```yaml
tests:
- name: created_at_a_known_time_within_30_seconds
  function: standard.file_timestamps
  parameter:
    dst: /home/user/Documents/report.odt
    timestamp_type: created
    expected_time: 1767265200
    tolerance_seconds: 30
```

*accessed during a time window* → PASSED

```yaml
tests:
- name: accessed_during_a_time_window
  function: standard.file_timestamps
  parameter:
    dst: /home/user/Documents/report.odt
    timestamp_type: accessed
    comparison_type: between
    start_time: '2026-01-15 09:00:00'
    end_time: '2026-01-15 17:00:00'
```

*a custom date format* → PASSED

```yaml
tests:
- name: a_custom_date_format
  function: standard.file_timestamps
  parameter:
    dst: /home/user/Documents/report.odt
    comparison_type: after
    expected_time: 15/01/2026 2:30 PM
    time_format: '%d/%m/%Y %I:%M %p'
```
