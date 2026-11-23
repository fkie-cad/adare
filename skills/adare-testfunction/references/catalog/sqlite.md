# SQLite (`sqlite.*`)

<!-- Generated; do not edit by hand. -->

SQL queries on SQLite databases and the write-ahead log (`-wal`) next to them: the rows a query returns, how many there are, which rows live only in the WAL, the state after each transaction in the WAL, two query values compared with each other (also across databases), how many frames and transactions the WAL holds, and deleted data left in the free space of the database file. The original files are never opened by SQLite: the database and its `-wal` / `-journal` are copied once and the copy is queried, so uncheckpointed changes are seen, the evidence is not modified and every result names the SHA-256 of the bytes read.

## `sqlite.free_space_pattern_count`

tests how often a text, byte pattern or regex occurs in the free space of an SQLite database (deleted, recoverable data)

Pass when the occurrences of `pattern` in the free space of the SQLite database satisfy `comparison_type`.

A corrupt header or a broken freelist / freeblock chain (a pointer out of range, a cycle, a freelist count that does not match the header) is an error: the free space could not be located.

**Use for:** asserting that a deleted record is still recoverable from the database file (`comparison_type: greater_equal`, `expected_count: 1`) while a query no longer returns it (sqlite.row_count with `expected_count: 0`), or that a delete really erased it (`expected_count: 0`, as with `PRAGMA secure_delete`). The file is parsed per the SQLite file format, without SQLite: freelist pages (pages no longer in use, including the overflow pages of a deleted large row), freeblocks (freed cells inside a b-tree page) and the unallocated space of each b-tree page. Occurrences are counted per region, so a match never spans two regions. Details list which pages and regions matched (absolute file offsets) and the size of each kind of free space. To search the whole file use binary.pattern_count; live rows are counted there too.

asserts: count, absent, content · formats: sqlite · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Counts with a comparison (`count_comparison`), Text encodings (`encoding`), Negative tests (absence) (`negative`)

**Does not support:**
- Regex values (!re) (`regex_tag`): A `!re` or `!timestamp` pattern is an error; use `pattern_type: regex` with a plain string.
- SQLite views of the write-ahead log (`sqlite_view`): `view` is `main_file` or `current` (the `-wal` checkpointed into a copy) only; no `wal_added` / `wal_removed` / `commit:N`.

**Not for:**
- whether a query still returns the row → `sqlite.row_count`
- a pattern anywhere in the file, live rows included → `binary.pattern_count`
- content of stale frames in the write-ahead log → `text.occurrence_count`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the database; a glob must match exactly one file (otherwise an error). A missing file is an error. It and any `-wal`/`-journal` sidecar are copied to a temp dir first; only the copy is read. |
| **pattern** | `str` |  | What to count; must not be empty. Its meaning depends on `pattern_type`. |
| pattern_type | `str` | `'text'` | `text` (default): `pattern` encoded in `encoding`. `bytes`: ASCII characters stand for their byte, Python escapes (`\x00`) are decoded. `hex`: hex digits, whitespace allowed. `regex`: an ASCII regular expression over the raw bytes (empty matches are not counted). Invalid escapes, hex or regexes are an error. Allowed: `text`, `bytes`, `hex`, `regex`. |
| encoding | `str` | `'utf-8'` | Encoding for `text` (default `utf-8`; `utf-16-le`, `utf-16-be` for databases with a UTF-16 text encoding). |
| region | `str` | `'all'` | Which free space is searched: `all` (default), `freelist`, `freeblocks` or `unallocated`. Other values are an error. Allowed: `all`, `freelist`, `freeblocks`, `unallocated`. |
| view | `str` | `'main_file'` | `main_file` (default): the main database file as it is, the `-wal` left out. `current`: the copy after `PRAGMA wal_checkpoint(TRUNCATE)`, i.e. with the `-wal` folded in as SQLite would on a checkpoint. Other values are an error. Allowed: `main_file`, `current`. |
| expected_count | `int` | `1` | Non-negative integer to compare with (default 1); `0` asserts absence. |
| comparison_type | `str` | `'equals'` | `equals` (default), `greater`, `less`, `greater_equal` or `less_equal`. Use `greater_equal` with `expected_count: 1` for "at least once". Allowed: `equals`, `greater`, `less`, `greater_equal`, `less_equal`. |

**Outcomes:**
- PASSED: the occurrences of `pattern` in the chosen free space satisfy `comparison_type`
- FAILED: the file was parsed and the count comparison does not hold
- ERROR: the database does not exist; a glob matches no file or more than one
- ERROR: the database files cannot be copied or read
- ERROR: a corrupt header, or a broken freelist or freeblock chain (a pointer out of range, a cycle, a freelist count that does not match the header): the free space could not be located
- ERROR: `view: current` and SQLite cannot checkpoint the copy
- ERROR: an empty `pattern`; invalid escapes, hex or regex; a `!re` / `!timestamp` pattern
- ERROR: an unknown `region`, `view`, `pattern_type` or `encoding`; a negative or non-integer `expected_count`; an unknown `comparison_type`

**Limits:**
- The file is parsed per the SQLite file format, without SQLite: freelist pages (with the overflow pages of a deleted large row), freeblocks inside b-tree pages, and the unallocated space of each b-tree page. Live rows are never counted.
- Occurrences are counted per region, so a match never spans two regions. The details list the matching pages and regions (absolute file offsets) and the size of each kind of free space.
- Freeing a cell overwrites its first 4 bytes (the freeblock header), and later writes reuse free space; search for a part of the deleted value that is long enough to be unique.
- `PRAGMA secure_delete` (on in some builds) zeroes freed space, so `expected_count: 0` proves the delete erased it.
- `pattern_type: regex` is an ASCII regular expression over the raw bytes; empty matches are not counted.

**Use cases:**
- A deleted record is still recoverable: `comparison_type: greater_equal` with `expected_count: 1` in the free space, while sqlite.row_count no longer returns the row.
- A delete erased the data: `expected_count: 0`, as with `PRAGMA secure_delete` or after a `VACUUM`.

**Examples:**

*a deleted title is still in the free space* → PASSED

```yaml
tests:
- name: a_deleted_title_is_still_in_the_free_space
  function: sqlite.free_space_pattern_count
  parameter:
    dst: /home/user/app/notes.db
    pattern: deleted-note-title
    expected_count: 1
    comparison_type: greater_equal
```

*a live row is not free space* → PASSED

```yaml
tests:
- name: a_live_row_is_not_free_space
  function: sqlite.free_space_pattern_count
  parameter:
    dst: /home/user/app/notes.db
    pattern: kept-note
    expected_count: 0
```

*a regex over the raw bytes* → PASSED

```yaml
tests:
- name: a_regex_over_the_raw_bytes
  function: sqlite.free_space_pattern_count
  parameter:
    dst: /home/user/app/notes.db
    pattern: 'deleted-[a-z]+-title'
    pattern_type: regex
    expected_count: 1
    comparison_type: greater_equal
```

*secure_delete erased it* → PASSED

```yaml
tests:
- name: secure_delete_erased_it
  function: sqlite.free_space_pattern_count
  parameter:
    dst: /home/user/app/notes.db
    pattern: deleted-note-title
    expected_count: 0
```

*recoverable data fails an erase check* → FAILED

```yaml
tests:
- name: recoverable_data_fails_an_erase_check
  function: sqlite.free_space_pattern_count
  parameter:
    dst: /home/user/app/notes.db
    pattern: deleted-note-title
    expected_count: 0
```

*an empty pattern is an error* → ERROR

```yaml
tests:
- name: an_empty_pattern_is_an_error
  function: sqlite.free_space_pattern_count
  parameter:
    dst: /home/user/app/notes.db
    pattern: ''
```

*a file that is no database is an error* → ERROR

```yaml
tests:
- name: a_file_that_is_no_database_is_an_error
  function: sqlite.free_space_pattern_count
  parameter:
    dst: /home/user/app/notes.db
    pattern: deleted-note-title
```

**Related:**
- `sqlite.row_count`: `expected_count: 0` that the row is gone, next to this test that its bytes remain

## `sqlite.query_result`

executes SQL query against SQLite database and validates result

Pass when `query` runs on the SQLite database and its result matches the expectations.

A test fails only when the query ran and its result does not match. When it cannot be evaluated (missing database, SQL error) it ends with an error, so `expect_to_fail` never turns an unreadable database into a pass.

**Use for:** asserting that a row was written, changed or removed; which rows exist only in the write-ahead log, not yet checkpointed into the main file (`view: wal_added`), or are still in the main file but deleted or changed in the WAL (`view: wal_removed`); the state after one transaction of several in the WAL (`view: commit:N`). The original file is never opened: `dst` and any `-wal`/`-journal` sidecar are copied to a temp dir and the copy is queried, so uncheckpointed changes are seen and the evidence is not modified. Details report `queried snapshot: <file> sha256=...` per copied file and, once the query ran, the rows read (`query result: [...]`, also on success). With neither expectation set, it passes whenever the query runs. To only count rows use sqlite.row_count. Timestamps stored as numbers (Unix seconds, microseconds since 1601) are compared with `!timestamp` and its `epoch`/`unit` options.

asserts: exists, absent, value, count · formats: sqlite · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), SQLite views of the write-ahead log (`sqlite_view`), Counts with a comparison (`count_comparison`), Negative tests (absence) (`negative`), Placeholders ({{ variable }}) (`placeholder`), Regex values (!re) (`regex_tag`), Times as expected values (!timestamp) (`timestamp_tag`)

**Not for:**
- only how many rows a query returns → `sqlite.row_count`
- how many frames or transactions the write-ahead log holds → `sqlite.wal_frame_count`
- a value in deleted records or free pages that no query returns → `sqlite.free_space_pattern_count`
- a query value compared with another query value, another view or another database → `sqlite.values_compare`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the database; a glob must match exactly one file (otherwise an error). A missing file is an error. |
| **query** | `str` |  | SQL to execute, e.g. `SELECT name FROM items WHERE name LIKE '%example%'`. A SQL error (syntax, unknown table, unreadable database) is an error. |
| expected_count | `int \| None` | `None` | Number of rows the query must return, compared with `comparison_type`; `None` skips the check. Use `0` to assert a row is gone. A negative number or a non-integer is an error. |
| expected_result | `list \| None` | `None` | Exact expected rows as a list of `{column: value}` mappings, in query order; `None` skips the check. Placeholders compare the stringified result. |
| comparison_type | `str` | `'equals'` | `equals` (default), `greater`, `less`, `greater_equal` or `less_equal` for `expected_count`; other values are an error. Allowed: `equals`, `greater`, `less`, `greater_equal`, `less_equal`. |
| view | `str` | `'current'` | Which state of the database the query sees, compared with `expected_count` / `expected_result`; all views come from one snapshot (the files are copied once). `current` (default): the database as SQLite sees it, the `-wal` replayed. `main_file`: the main database file alone, the `-wal` left out. `wal_added`: the result rows of `current` that are not in `main_file`; `wal_removed`: the rows of `main_file` not in `current` (multiset difference of whole rows, in query order). Select identifying columns for the differences: a changed row appears in both. `commit:N`: the `-wal` replayed through its N-th transaction (`commit:1` the first, `commit:-1` the last, `commit:0` = `main_file`); an N beyond the commits in the `-wal`, or any N but 0 without a `-wal`, is an error. A `-journal` is used in every view, so a hot rollback journal is rolled back. Details name the view, the `-wal` sha256 and, for `commit:N`, the WAL frame it stops at. Other values are an error. |

**Outcomes:**
- PASSED: the query ran and its rows match `expected_count` and `expected_result` (with neither set, whenever the query runs)
- FAILED: the query ran and the number of rows or the rows themselves do not match
- ERROR: the database does not exist; a glob matches no file or more than one
- ERROR: an SQL error (syntax, unknown table or column, a corrupt or unreadable database), also on one side of a `wal_added` / `wal_removed` difference
- ERROR: the database files cannot be copied
- ERROR: a negative or non-integer `expected_count`; an unknown `comparison_type` or `view`
- ERROR: an invalid regex or an unknown placeholder in `expected_result`

**Limits:**
- `expected_result` is compared as a whole: every row, in query order, with every selected column. Add `ORDER BY` for a stable order.
- `!re`, `!timestamp` and placeholders in `expected_result` compare the result as text (`[{'col': 'value'}]`): a placeholder stands for a quoted text value, so an INTEGER column fails against it. Select the column as text: `CAST(visited AS TEXT) AS visited`.
- Differences (`wal_added` / `wal_removed`) compare whole rows; select identifying columns, a changed row appears in both.
- `dst` inside an archive (`backup.zip!/app/data.db`) also extracts the `-wal` / `-journal` members next to it, so the views work there too.
- The rows read are reported in the details, cut after 2000 characters.
- `view` is `current`, `main_file`, `wal_added`, `wal_removed` or `commit:N` (the state after the N-th transaction in the `-wal`; `commit:-1` the last, `commit:0` the main file). An N out of range is an error.

**Use cases:**
- A record was written: A history entry, bookmark or setting row with the expected values after an action.
- A record is gone: `expected_count: 0` on a query for the deleted row.
- A change is still only in the write-ahead log: `view: wal_added` shows rows committed to the `-wal` but not yet checkpointed into the main file; `view: wal_removed` rows deleted there that the main file still holds.
- A time stored as a number: `!timestamp` with `epoch` / `unit` and the times saved around the action, on a column selected as text.

**Examples:**

*a row with the expected values* → PASSED

```yaml
tests:
- name: a_row_with_the_expected_values
  function: sqlite.query_result
  parameter:
    dst: /home/user/app/data.db
    query: SELECT id, name FROM items WHERE name = 'example'
    expected_result: [{id: 1, name: example}]
```

*no such row* → PASSED. Absence of a row; a missing database would be an error, never this pass.

```yaml
tests:
- name: no_such_row
  function: sqlite.query_result
  parameter:
    dst: /home/user/app/data.db
    query: SELECT id FROM items WHERE name = 'secret-project'
    expected_count: 0
```

*other values fail* → FAILED

```yaml
tests:
- name: other_values_fail
  function: sqlite.query_result
  parameter:
    dst: /home/user/app/data.db
    query: SELECT name FROM items WHERE id = 2
    expected_result: [{name: example}]
```

*an unknown table is an error, not a failure* → ERROR. The query never ran, so nothing was learnt about the rows; `expect_to_fail` cannot turn it into a pass.

```yaml
tests:
- name: an_unknown_table_is_an_error_not_a_failure
  function: sqlite.query_result
  parameter:
    dst: /home/user/app/data.db
    query: SELECT id FROM bookmarks
    expected_count: 0
```

*a missing database is an error* → ERROR

```yaml
tests:
- name: a_missing_database_is_an_error
  function: sqlite.query_result
  parameter:
    dst: /home/user/app/other.db
    query: SELECT id FROM items
    expected_count: 0
```

*a row only in the write-ahead log* → PASSED. Committed to the `-wal`, not yet checkpointed into the main file.

```yaml
tests:
- name: a_row_only_in_the_write_ahead_log
  function: sqlite.query_result
  parameter:
    dst: /home/user/app/data.db
    query: SELECT id, name FROM items ORDER BY id
    expected_result: [{id: 3, name: example}]
    view: wal_added
```

*a row deleted in the WAL but still in the main file* → PASSED

```yaml
tests:
- name: a_row_deleted_in_the_wal_but_still_in_the_main_f
  function: sqlite.query_result
  parameter:
    dst: /home/user/app/data.db
    query: SELECT id, name FROM items ORDER BY id
    expected_result: [{id: 2, name: removed-entry}]
    view: wal_removed
```

*the current state includes the WAL* → PASSED

```yaml
tests:
- name: the_current_state_includes_the_wal
  function: sqlite.query_result
  parameter:
    dst: /home/user/app/data.db
    query: SELECT id, name FROM items ORDER BY id
    expected_result: [{id: 1, name: kept}, {id: 3, name: example}]
```

*visit time between two saved timestamps* → PASSED. The INTEGER column is selected as text, so the placeholder matches it.

```yaml
tests:
- name: visit_time_between_two_saved_timestamps
  function: sqlite.query_result
  parameter:
    dst: /home/user/app/data.db
    query: SELECT CAST(visited AS TEXT) AS visited FROM visits WHERE url = 'https://example.org/'
    expected_result:
    - visited: !timestamp {after: '{{before_visit}}', before: '{{after_visit}}', epoch: 1970, unit: s}
```

*a URL by pattern* → PASSED

```yaml
tests:
- name: a_url_by_pattern
  function: sqlite.query_result
  parameter:
    dst: /home/user/app/data.db
    query: SELECT url FROM visits
    expected_result: [{url: !re 'https://example\.org/.*'}]
```

**Related:**
- `sqlite.row_count`: the same query and views, but asserts the number of rows only
- `sqlite.wal_frame_count`: counts the frames and transactions of the WAL the views compare

## `sqlite.row_count`

tests the number of rows an SQL query returns on an SQLite database

Pass when the number of rows `query` returns on the SQLite database satisfies `comparison_type`.

**Use for:** asserting how many records an action left behind (exactly one history entry for a URL); asserting a record is gone: `expected_count: 0`; asserting a row is only in the write-ahead log, not yet checkpointed into the main file: one test with `view: wal_added` and `expected_count: 1`. Queried like sqlite.query_result: `dst` and any `-wal`/`-journal` sidecar are copied to a temp dir and the copy is queried, so uncheckpointed changes are seen and the evidence is not modified. Details report the count, the rows read (`query result: [...]`) and `queried snapshot: <file> sha256=...` per copied file. To check the row contents use sqlite.query_result with `expected_result`.

asserts: count, exists, absent · formats: sqlite · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), SQLite views of the write-ahead log (`sqlite_view`), Counts with a comparison (`count_comparison`), Negative tests (absence) (`negative`)

**Not for:**
- the values of the rows → `sqlite.query_result`
- how many frames or transactions the write-ahead log holds → `sqlite.wal_frame_count`
- deleted rows still in the database file's free space → `sqlite.free_space_pattern_count`
- the count in one view against the count in another (one row more in the WAL) → `sqlite.values_compare`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the database; a glob must match exactly one file (otherwise an error). A missing file is an error. |
| **query** | `str` |  | SQL to execute, e.g. `SELECT id FROM items WHERE name = 'example'`; every returned row counts (`SELECT COUNT(*)` returns one row). A SQL error (syntax, unknown table, unreadable database) is an error. |
| **expected_count** | `int` |  | Non-negative integer to compare against; anything else is an error. |
| comparison_type | `str` | `'equals'` | `equals` (default), `greater`, `less`, `greater_equal` or `less_equal`; other values are an error. Allowed: `equals`, `greater`, `less`, `greater_equal`, `less_equal`. |
| view | `str` | `'current'` | Which state of the database is counted; all views come from one snapshot (the files are copied once). `current` (default): the database as SQLite sees it, the `-wal` replayed. `main_file`: the main database file alone, the `-wal` left out. `wal_added`: the result rows of `current` that are not in `main_file`; `wal_removed`: the rows of `main_file` not in `current` (multiset difference of whole rows; their number is counted). Select identifying columns for the differences: a changed row appears in both. `commit:N`: the `-wal` replayed through its N-th transaction (`commit:1` the first, `commit:-1` the last, `commit:0` = `main_file`); an N beyond the commits in the `-wal`, or any N but 0 without a `-wal`, is an error. A `-journal` is used in every view, so a hot rollback journal is rolled back. Details name the view, the `-wal` sha256 and, for `commit:N`, the WAL frame it stops at. Other values are an error. |

**Outcomes:**
- PASSED: the number of rows the query returns satisfies `comparison_type`
- FAILED: the query ran and the count comparison does not hold
- ERROR: the database does not exist; a glob matches no file or more than one
- ERROR: an SQL error (syntax, unknown table or column, a corrupt or unreadable database), also on one side of a difference; an empty `query`
- ERROR: the database files cannot be copied
- ERROR: a negative or non-integer `expected_count`; an unknown `comparison_type` or `view`

**Limits:**
- Every returned row counts, so `SELECT COUNT(*)` returns one row; select the rows themselves.
- Differences (`wal_added` / `wal_removed`) compare whole rows; select identifying columns, a changed row appears in both.
- `dst` inside an archive also extracts the `-wal` / `-journal` members next to it.
- `view` is `current`, `main_file`, `wal_added`, `wal_removed` or `commit:N` (the state after the N-th transaction in the `-wal`; `commit:-1` the last, `commit:0` the main file). An N out of range is an error.

**Use cases:**
- Record created exactly once: An action must add one row (one history entry, one bookmark), not zero and not two.
- Record removed: `expected_count: 0` after a delete or "clear history" action.
- Row not yet checkpointed: `view: wal_added` counts the rows that live only in the write-ahead log; `view: wal_removed` the rows deleted there that the main file still holds.
- Growth of a table: `comparison_type: greater_equal` when an action may add a varying number of rows.

**Examples:**

*exactly one matching entry* → PASSED

```yaml
tests:
- name: exactly_one_matching_entry
  function: sqlite.row_count
  parameter:
    dst: /home/user/app/data.db
    query: SELECT id FROM items WHERE name LIKE '%example%'
    expected_count: 1
```

*entry deleted* → PASSED

```yaml
tests:
- name: entry_deleted
  function: sqlite.row_count
  parameter:
    dst: /home/user/app/data.db
    query: SELECT id FROM items WHERE name = 'secret-project'
    expected_count: 0
```

*COUNT(*) is one row* → FAILED. The query returns one row holding 2; count the rows themselves (`SELECT id ...`).

```yaml
tests:
- name: count_is_one_row
  function: sqlite.row_count
  parameter:
    dst: /home/user/app/data.db
    query: SELECT COUNT(*) FROM items
    expected_count: 2
```

*the one database in a folder, whatever its name* → PASSED

```yaml
tests:
- name: the_one_database_in_a_folder_whatever_its_name
  function: sqlite.row_count
  parameter:
    dst: /home/user/app/*.db
    query: SELECT id FROM items
    expected_count: 1
    comparison_type: greater_equal
```

*a glob matching two databases is an error* → ERROR

```yaml
tests:
- name: a_glob_matching_two_databases_is_an_error
  function: sqlite.row_count
  parameter:
    dst: /home/user/app/*.db
    query: SELECT id FROM items
    expected_count: 2
```

*entry not yet checkpointed* → PASSED

```yaml
tests:
- name: entry_not_yet_checkpointed
  function: sqlite.row_count
  parameter:
    dst: /home/user/app/data.db
    query: SELECT id FROM items WHERE name = 'example'
    expected_count: 1
    view: wal_added
```

*deleted entry still in the main file* → PASSED

```yaml
tests:
- name: deleted_entry_still_in_the_main_file
  function: sqlite.row_count
  parameter:
    dst: /home/user/app/data.db
    query: SELECT id FROM items WHERE name = 'removed-entry'
    expected_count: 1
    view: main_file
```

*the deleted entry was still there after the first transaction* → PASSED. `commit:1` replays the `-wal` through its first transaction (the insert), before the delete.

```yaml
tests:
- name: the_deleted_entry_was_still_there_after_the_firs
  function: sqlite.row_count
  parameter:
    dst: /home/user/app/data.db
    query: SELECT id FROM items WHERE name = 'removed-entry'
    expected_count: 1
    view: commit:1
```

*a commit the WAL does not hold is an error* → ERROR

```yaml
tests:
- name: a_commit_the_wal_does_not_hold_is_an_error
  function: sqlite.row_count
  parameter:
    dst: /home/user/app/data.db
    query: SELECT id FROM items
    expected_count: 1
    view: commit:5
```

*but gone in the current state* → PASSED

```yaml
tests:
- name: but_gone_in_the_current_state
  function: sqlite.row_count
  parameter:
    dst: /home/user/app/data.db
    query: SELECT id FROM items WHERE name = 'removed-entry'
    expected_count: 0
```

*a database inside an archive, with its WAL* → PASSED. The `-wal` member next to the database member is extracted with it.

```yaml
tests:
- name: a_database_inside_an_archive_with_its_wal
  function: sqlite.row_count
  parameter:
    dst: /home/user/backup/app.zip!/data.db
    query: SELECT id FROM items WHERE name = 'example'
    expected_count: 1
    view: wal_added
```

**Related:**
- `sqlite.query_result`: the same query and views, and checks the returned rows themselves

## `sqlite.values_compare`

compares the values two SQL queries return on SQLite databases or views of one (earlier/later, within a tolerance, A = B + offset)

Pass when the value `query` returns compares to the value `other_query` returns (+ `offset`).

**Use for:** one check for "the write-ahead log adds exactly one row": `SELECT count(*)` on `view: current` equal to `other_view: main_file` with `offset: 1`; how a value changed between two transactions in the WAL (`view: commit:2`, `other_view: commit:1`); two timestamps of one record in order (`other_query` on another column); the same value in two databases (`other_dst`). Each side is the first column of the single row its query returns. With one database both sides come from one snapshot (the files are copied once, as in sqlite.query_result), so they show the same moment; the evidence is never opened. To compare one value with a constant use sqlite.query_result.

asserts: compare, order · formats: sqlite · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), SQLite views of the write-ahead log (`sqlite_view`), Ordered comparison of numbers and times (`ordered_comparison`), A second file (other_dst) (`other_dst`)

**Not for:**
- one query value against a constant → `sqlite.query_result`
- how many rows a query returns → `sqlite.row_count`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the database; a glob must match exactly one file (otherwise an error). A missing file is an error. |
| **query** | `str` |  | SQL returning the first value, e.g. `SELECT count(*) FROM items`. It must return exactly one row (its first column is compared): no row fails, more rows are an error. A SQL error is an error. |
| other_query | `str \| None` | `None` | SQL returning the second value; `None` (default) runs `query` again (on `other_dst` / `other_view`). Same rules. |
| other_dst | `str \| None` | `None` | Database of the second value; `None` (default) = `dst`. Same rules as `dst`; it gets its own snapshot. |
| view | `str` | `'current'` | State of `dst` the first query sees: `current` (default, the `-wal` replayed), `main_file` (the `-wal` left out) or `commit:N` (the `-wal` replayed through its N-th transaction; `commit:-1` the last, `commit:0` = `main_file`), as in sqlite.query_result. An N out of range is an error. |
| other_view | `str \| None` | `None` | State the second query sees; `None` (default) = `view`. |
| comparison_type | `str` | `'equals'` | How the first value relates to the second: `equals` (default), `not_equals`, `greater`, `less`, `greater_equal` or `less_equal` (`less` = earlier for timestamps). Other values are an error. Allowed: `equals`, `not_equals`, `greater`, `less`, `greater_equal`, `less_equal`. |
| value_type | `str` | `'auto'` | `auto` (default; numbers if both are numbers, else timestamps), `number` or `timestamp`. A value that is no number or timestamp (NULL, a BLOB) is an error. Allowed: `auto`, `number`, `timestamp`. |
| tolerance | `int \| float \| None` | `None` | Allowed difference for `equals`/`not_equals` (seconds for timestamps). |
| offset | `int \| float \| None` | `None` | Added to the second value before comparing (seconds for timestamps, may be negative): `first <comparison_type> second + offset`. |
| time_format | `str \| None` | `None` | `strptime` format of text timestamps on both sides; default ISO 8601 or RFC 2822. |
| timestamp_epoch | `int \| None` | `None` | Read numbers as a count since 1 January of `1970`, `1601` or `2001`. |
| timestamp_unit | `str \| None` | `None` | Unit of that count: `s` (default), `ms`, `us`, `ns` or `100ns`. |
| utc_offset | `str \| None` | `None` | Zone of timestamps without one (`+02:00`); default UTC. |

**Outcomes:**
- PASSED: the value `query` returns relates to the value `other_query` returns, plus `offset`, as `comparison_type` says
- FAILED: a query returns no row
- FAILED: the queries ran and the comparison does not hold
- ERROR: a database does not exist; a glob matches no file or more than one
- ERROR: a query returns more than one row; an SQL error; an empty `query`
- ERROR: a value that is no number or timestamp (NULL, a BLOB, text that is no time)
- ERROR: an unknown `view`, or `commit:N` out of range
- ERROR: bad comparison parameters (`comparison_type`, `value_type`, `timestamp_epoch`, ...)

**Limits:**
- Each side is the first column of the single row its query returns. `other_query` defaults to `query`, `other_view` to `view`, `other_dst` to `dst`.
- With one database both sides come from one snapshot, so they show the same moment; `other_dst` gets its own snapshot.
- `offset` is added to the second value (seconds for timestamps): `first <comparison_type> second + offset`.
- `view` and `other_view` are `current`, `main_file` or `commit:N`; the differences `wal_added` / `wal_removed` are not values.
- Two text values cannot be compared; numbers and times only.

**Use cases:**
- The WAL adds exactly one row: `SELECT count(*)` on `view: current` equal to `other_view: main_file` with `offset: 1`, in one check.
- How a value changed between two transactions: `view: commit:2` against `other_view: commit:1`.
- Two times of one record in order: A modification time after the creation time, with `other_query` on the other column.
- Before and after an action: `other_dst` on a copy of the database a `command` action made before the action under test.

**Examples:**

*the WAL adds exactly one matching row* → PASSED

```yaml
tests:
- name: the_wal_adds_exactly_one_matching_row
  function: sqlite.values_compare
  parameter:
    dst: /home/user/app/data.db
    query: SELECT count(*) FROM items WHERE name = 'example'
    view: current
    other_view: main_file
    offset: 1
```

*fewer rows after the second transaction than after the first* → PASSED

```yaml
tests:
- name: fewer_rows_after_the_second_transaction_than_aft
  function: sqlite.values_compare
  parameter:
    dst: /home/user/app/data.db
    query: SELECT count(*) FROM items
    view: commit:1
    other_view: commit:2
    comparison_type: greater
```

*modified after created, as times* → PASSED

```yaml
tests:
- name: modified_after_created_as_times
  function: sqlite.values_compare
  parameter:
    dst: /home/user/docs/index.db
    query: SELECT modified FROM documents WHERE name = 'report.txt'
    other_query: SELECT created FROM documents WHERE name = 'report.txt'
    comparison_type: greater
    value_type: timestamp
    timestamp_epoch: 1970
```

*within two minutes of each other* → PASSED

```yaml
tests:
- name: within_two_minutes_of_each_other
  function: sqlite.values_compare
  parameter:
    dst: /home/user/docs/index.db
    query: SELECT modified FROM documents
    other_query: SELECT created FROM documents
    value_type: timestamp
    timestamp_epoch: 1970
    tolerance: 120
```

*against a copy made before the action* → PASSED

```yaml
tests:
- name: against_a_copy_made_before_the_action
  function: sqlite.values_compare
  parameter:
    dst: /home/user/app/data.db
    query: SELECT max(id) FROM items
    other_dst: /tmp/before/data.db
    comparison_type: greater
```

*equal counts fail when the WAL added a row* → FAILED

```yaml
tests:
- name: equal_counts_fail_when_the_wal_added_a_row
  function: sqlite.values_compare
  parameter:
    dst: /home/user/app/data.db
    query: SELECT count(*) FROM items WHERE name = 'example'
    other_view: main_file
```

*no row fails* → FAILED

```yaml
tests:
- name: no_row_fails
  function: sqlite.values_compare
  parameter:
    dst: /home/user/app/data.db
    query: SELECT id FROM items WHERE name = 'missing'
    other_query: SELECT id FROM items WHERE name = 'example'
```

*several rows are an error* → ERROR. Each query must return exactly one row; aggregate (`count(*)`, `max(...)`) or add a `WHERE`.

```yaml
tests:
- name: several_rows_are_an_error
  function: sqlite.values_compare
  parameter:
    dst: /home/user/app/data.db
    query: SELECT id FROM items
```

*a text value is an error* → ERROR

```yaml
tests:
- name: a_text_value_is_an_error
  function: sqlite.values_compare
  parameter:
    dst: /home/user/app/data.db
    query: SELECT name FROM items WHERE id = 1
```

**Related:**
- `sqlite.query_result`: the same snapshot and views, for the rows themselves
- `sqlite.wal_frame_count`: how many transactions `commit:N` can choose from

## `sqlite.wal_frame_count`

tests the number of frames in the write-ahead log (-wal) of an SQLite database

Pass when the number of `frames` in the SQLite write-ahead log satisfies `comparison_type`.

**Use for:** asserting that changes are still in the WAL, not yet checkpointed into the main file (`frames: valid` greater than 0), how many transactions the WAL holds (`frames: commits`), or that a checkpoint emptied it (`expected_count: 0`); finding old frames a WAL reset left behind that SQLite no longer reads (`frames: stale`). The WAL is parsed per the SQLite file format, without SQLite: header magic and version, page size, salts and the checksum chain. A copy of the WAL is read, never the original. Details report the header fields, all four counts and `read snapshot: <file> sha256=...`. To find which rows live only in the WAL use sqlite.row_count with `view: wal_added`.

asserts: count, absent · formats: sqlite · runs: guest agent, host test mode or hostside; dry-run on a local file · os: any

**Supports:** Files inside archives and compressed files (`archive_dst`), Globs in dst (`glob_dst`), Counts with a comparison (`count_comparison`), Negative tests (absence) (`negative`)

**Not for:**
- which rows live only in the WAL → `sqlite.row_count`
- the values of rows in the WAL → `sqlite.query_result`
- a value in stale WAL frames → `text.occurrence_count`

| parameter | type | default | description |
|---|---|---|---|
| **dst** | `str` |  | Guest path to the database; its `<dst>-wal` is read. A missing `-wal` next to an existing database counts as 0 frames, a missing database is an error. May also name the `-wal` file itself (then it must exist). A glob must match exactly one file. |
| **expected_count** | `int` |  | Non-negative integer to compare against; anything else is an error. |
| comparison_type | `str` | `'equals'` | `equals` (default), `greater`, `less`, `greater_equal` or `less_equal`; other values are an error. Allowed: `equals`, `greater`, `less`, `greater_equal`, `less_equal`. |
| frames | `str` | `'valid'` | `valid` (default): the frames SQLite replays, i.e. salts matching the header and an intact checksum chain, up to the last commit frame; `commits`: commit frames among them (one per transaction); `all`: every complete frame in the file; `stale`: `all` minus `valid` (frames from before a WAL reset, an unfinished transaction). Other values are an error. Allowed: `valid`, `commits`, `all`, `stale`. |

**Outcomes:**
- PASSED: the number of `frames` of the chosen kind satisfies `comparison_type`; a missing `-wal` next to the database and an empty one have 0 frames
- FAILED: the WAL was read and the count comparison does not hold
- ERROR: the database does not exist, or `dst` names a `-wal` that does not exist; a glob matches no file or more than one
- ERROR: the WAL cannot be read
- ERROR: an invalid WAL header: shorter than 32 bytes, a wrong magic, a version other than 3007000, a bad page size, a header checksum mismatch
- ERROR: a negative or non-integer `expected_count`; an unknown `comparison_type` or `frames`

**Limits:**
- The WAL is parsed per the SQLite file format, without SQLite; a copy is read and its SHA-256 reported.
- Counts frames, not rows; one transaction may write several frames, one per changed page.
- `dst` inside an archive reads the `-wal` member next to the database member (or names the `-wal` member itself).

**Use cases:**
- Changes not yet checkpointed: `frames: commits` with `comparison_type: greater_equal` after an action, while the application still holds the database open.
- Checkpoint ran: `expected_count: 0` after the application closed: the WAL was checkpointed and truncated or deleted.
- Leftovers of earlier transactions: `frames: stale` greater than 0: frames from before a WAL reset that SQLite no longer reads, whose pages may still hold earlier content.

**Examples:**

*transactions not yet checkpointed* → PASSED

```yaml
tests:
- name: transactions_not_yet_checkpointed
  function: sqlite.wal_frame_count
  parameter:
    dst: /home/user/app/data.db
    expected_count: 1
    comparison_type: greater_equal
    frames: commits
```

*old frames after a WAL reset* → PASSED. `dst` may name the `-wal` itself.

```yaml
tests:
- name: old_frames_after_a_wal_reset
  function: sqlite.wal_frame_count
  parameter:
    dst: /home/user/app/data.db-wal
    expected_count: 1
    comparison_type: greater_equal
    frames: stale
```

*a WAL that still holds frames fails a checkpoint check* → FAILED

```yaml
tests:
- name: a_wal_that_still_holds_frames_fails_a_checkpoint
  function: sqlite.wal_frame_count
  parameter:
    dst: /home/user/app/data.db
    expected_count: 0
```

*no -wal next to the database is 0 frames* → PASSED

```yaml
tests:
- name: no_wal_next_to_the_database_is_0_frames
  function: sqlite.wal_frame_count
  parameter:
    dst: /home/user/app/data.db
    expected_count: 0
```

*a named -wal that does not exist is an error* → ERROR

```yaml
tests:
- name: a_named_wal_that_does_not_exist_is_an_error
  function: sqlite.wal_frame_count
  parameter:
    dst: /home/user/app/data.db-wal
    expected_count: 0
```

*a WAL with a wrong magic is an error* → ERROR

```yaml
tests:
- name: a_wal_with_a_wrong_magic_is_an_error
  function: sqlite.wal_frame_count
  parameter:
    dst: /home/user/app/data.db
    expected_count: 0
```

**Related:**
- `sqlite.row_count`: `view: wal_added` / `wal_removed` show which rows the WAL adds or removes
