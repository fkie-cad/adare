# Changelog

All notable changes to the ADARE workspace. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/) per package.

## Versioning policy

Each workspace package (`adare`, `adarevm`, `adarelib`, `adare-cv-server`) has its
own version in its `pyproject.toml`. While below 1.0, a **minor** bump marks a
breaking change and a **patch** bump everything else.

`adarelib` needs the most care: guests keep the `adarelib` they were provisioned
with, while testfunctions are uploaded fresh on every run. So:

- Anything a testfunction may rely on (decorator kwargs, `TestResult`, context
  API) is additive only within a minor series.
- Bump the `adarelib` minor version when that contract changes, and note under
  the release which guests need re-provisioning.

Agent wheels are built as `<version>+g<hash12>` of their sources, so a run
reinstalls `adarevm`/`adarelib` in the guest whenever their code changed; the
version above is still what marks a contract change.

Add entries under **Unreleased** as you go. To release a package:

1. Bump `<package>/pyproject.toml` and rename **Unreleased** to
   `## [<package> <version>] - <date>` (start a new empty **Unreleased** above it).
2. Merge to `main`, then on that commit run `make release-check TAG=<package>-v<version>`.
3. Tag it `<package>-v<version>` (e.g. `adarelib-v0.2.0`) and push the tag.

The tag starts `release.yml`: it checks the tag again (version, changelog section,
commit on `main`), runs the full Tests workflow and, once the self-hosted runner is
set up, the live-VM smoke (`live-smoke.yml`), then builds the package's sdist and
wheel and creates a GitHub Release with them and this section as the notes. Nothing
is published to PyPI. A failed check leaves no release; fix it, delete the tag
(`git push --delete origin <tag>`) and tag again.

## [Unreleased]

### Breaking
- **A failed post-setup step fails the run** (adare). A step in an environment's
  `postsetupinstallations` that exits non-zero, times out or loses its transport stops the setup:
  stage and run end FAILED with a message naming the step, exit code, duration and the last 20
  lines of stderr (or stdout). It used to be logged and skipped, and the run passed. Mark optional
  steps `allow_failure: true`.
- **Post-setup steps run as the VM user unless `admin: true`**, on every path. Host tests and host
  GUI runs (QEMU guest agent) used to run them as root, the host-side backend wrote their files as
  root. Steps that write system paths (`/etc`, packages) need `admin: true`. Windows steps run
  elevated in any case (agent: elevated account, guest agent: SYSTEM).
- **Unknown keys in a post-setup step are a load error** naming the key and the step (`admn:` used
  to be dropped silently).

### Added
- Post-setup steps take `admin` (root / elevated), `allow_failure` (a failure is a stage warning
  and a line in the run summary, the run goes on) and `timeout` (seconds, default 600). `adare env
  extend --install` gains `--admin`, `--allow-failure` and `--timeout`. Every step's command,
  rights, cwd, exit code, duration, stdout and stderr go to `<run>/logs/postsetup.log`.
- `adare dev start` runs the environment's post-setup steps after the agent connects, like a run
  does; `--no-postsetup` skips them.

### Fixed
- Post-setup steps run in file order (stored as a position per environment; existing
  environments are backfilled in insertion order), honour `cwd`, report the guest's stderr, and a
  WebSocket timeout ends the step as a failure instead of making the run INTERRUPTED. Host tests
  apply the step timeout (it was a fixed 300 s).

## [adare 0.1.2] - 2026-11-23

Versions: `adare` 0.1.2 and `adarelib` 0.3.0 (breaking changes below).
Guests need no re-provisioning: agent wheels are reinstalled when their code changes.

### Breaking
- **Renamed testfunction parameters** (adare): one name per idea across collections. Old
  names are refused with a precise message (`parameter "expected_text" was renamed to
  "expected_value"`) by `adare exp playbook validate`, host mode / dry-run and the guest
  agent (table in `adarelib.testset.renames`). `scripts/migrate_testfunction_renames.py
  PATH --write` rewrites playbooks in place (comments and layout kept); the playbooks in
  `adare/appdata/examples` and `paper/experiments` are migrated.

  | Function | Old | New |
  |---|---|---|
  | `xml.element_text_matches` | `expected_text` (default `''`) | `expected_value` (required) |
  | `xml.xpath_result_matches` | `expected_result` (default `''`) | `expected_value` (required) |
  | `json.array_contains` | `expected_element` (default `None`) | `expected_value` (required) |
  | `json.value_matches` | `expected_value` (default `None`) | `expected_value` (required; write `null` to expect null) |
  | `jsonl.line_matches` | `match_mode` | `wildcard_mode` |
  | `excel.sheet_exists` | `sheet_name` | `sheet` (required) |
  | `sqlite.query_result` | `expected_rows` | `expected_count` (+ `comparison_type`) |
  | `xml.element_count` | `expected_count` (default 0) | `expected_count` (required) |
  | `linux.log_entry_exists` | `log_file`, `pattern` | `dst`, `content` (+ `regex_match`, default true) |

- `excel.sheet_exists` and `excel.cell_value_matches` with `regex_match` **search** the
  pattern (`re.search`) like every other collection; they used `re.match` (anchored at the
  start). Write `^...$` to match the whole name or value.
- `linux.log_entry_exists` reads the log itself instead of running `tail | grep -E`: the
  pattern is a Python regex (`re.search`; POSIX classes such as `[[:digit:]]` are not
  supported, use `\d`), `dst` takes globs and `archive!member` (rotated `.gz` logs), the
  encoding is detected, and it is a file-content test, so host mode pulls the log like any
  other file. A missing log is an ERROR (it failed). It no longer needs a Linux guest. A POSIX
  class (`[[:space:]]`, valid only for grep) or a `!re`/`!timestamp` tag in `content` is an ERROR
  instead of a pattern that silently never matches.
- A `{{ placeholder }}` without metadata is an ERROR (`unknown placeholder`); it used to be
  compared against an empty string.

### Added
- Testfunction contracts: each collection has a `contract.yaml` saying per function what it
  asserts and reads, which shared features it supports or refuses, goals it is not for (with
  the function to use instead), when it passes / fails / errors, its limits, allowed parameter
  values, use cases and examples; `appdata/testfunctions/library.yaml` holds the shared
  vocabulary, features and known gaps. One source renders `adare test info`, the agent skill's
  references and the reference pages of the docs (Sphinx directive `adare-testfunction`).
  The examples run in the unit suite (`scripts/check_contract.py`).
- `adare test search` returns short cards (why it matched, supports / does not support, not
  for, required parameters), filters `--asserts`, `--reads`, `--feature`, follows "not for -> use
  X" redirects and answers `match: weak` with the matching known gaps when nothing fits.
- `adare test feature [<id>]`, the chat tool `testfunction_feature`, and `adare test catalog
  --markdown-dir` for the split skill references (`catalog/index.md`, `catalog/<collection>.md`,
  `features.md`); `make testfunction-tables` regenerates them with the docs tables.
- `adare exp playbook validate` warns about parameter values outside a function's allowed list.
- CI: release tags `<package>-v<version>` get checked (version, CHANGELOG section, commit
  on `main`), tested and turned into a GitHub Release with the package's sdist + wheel
  (`release.yml`, `make release-check`, `make build`; no PyPI).
- CI: a live-VM smoke test (`live-smoke.yml`, `make smoke-live`) on a self-hosted runner,
  on release tags and on demand only (never on pull requests): `adare env verify`, then
  the `test_loop_simple` example, failing on any non-passing result in the JSON summary.
  Inactive until the runner is registered and the repo variable `LIVE_RUNNER` is `true`.
- CI hygiene on every push/PR (`make ci-hygiene` in the lint job): actionlint, gitleaks,
  no new tracked file over 2 MB, no conflict markers or private keys, and the ruff/mypy
  pins in both `pyproject.toml` files and `.pre-commit-config.yaml` must match.
- CI: `pip-audit` also audits the guest test pins (`requirements-guest-test.txt`), and
  Dependabot also bumps the pre-commit hook revs.
- File testfunctions can read a file **inside an archive** (adare, adarelib; additive):
  `dst: /home/u/backup.tar.gz!/etc/app/config.json`, `dst: /var/log/syslog.2.gz!` for the
  decompressed content, nested archives (`outer.zip!/inner.tar.gz!/data.json`), globs on
  both sides, and a mapping form `dst: {archive: ..., member: ...}`. Formats: tar (plain,
  .gz, .bz2, .xz), zip, gzip, bzip2 and xz, detected from the content, not the extension.
  Only the requested member is extracted, by streaming under a sanitized name, capped by
  `ADARE_ARCHIVE_MAX_BYTES` (default 1 GiB). The extracted copy is removed after the test.
  A missing, corrupt or unsupported archive, a link or `..` member, or a member over the
  cap gives ERROR. An absent member counts like a missing file. Each result gets an
  `archive member: ... sha256=...` provenance line. This works in guest mode and in host
  mode (only the archive is pulled), with no change to any testfunction: it is built into
  `ctx.resolve_globfilepath`. Guide: *Files inside archives*.
- **LZ4** for the archive separator (adarelib; additive): `dst: store.jsonlz4!` or `x.lz4!`
  gives the decompressed content to every file testfunction, also nested
  (`profile.zip!/p/store.jsonlz4!`) and `.tar.lz4`. Both the LZ4 frame format (checksums
  verified, linked/independent and uncompressed blocks, skippable frames) and an LZ4 block
  with an 8-byte magic and size header are read by a pure-Python decoder (no new
  dependency), size-capped like every member. Corrupt or unsupported data gives ERROR.
- **Snappy** for the archive separator (adarelib; additive): files in the Snappy framing
  format (`data.json.sz!`, `backup.tar.sz!/etc/app.json`) are read with chunk checksums
  verified and the same size cap as the other formats; pure Python, no new dependency. Only
  the framing format has magic bytes, so raw Snappy blocks are not detected.
- `!timestamp` reads **numeric timestamps** (adarelib; additive): `epoch: 1970 | 1601 | 2001`
  (default 1970) and `unit: s | ms | us | ns | 100ns` (default s) convert an artifact value
  that is an integer, a digit string or a fraction (SQLite column, JSON number) before it is
  compared, with `tolerance` or `after`/`before`. Covers Unix s/ms/µs/ns, Windows FILETIME
  (1601 + 100ns), microseconds since 1601 and the 2001 reference date. Exact integer
  conversion down to the microsecond; an invalid epoch/unit is a playbook load error, a
  non-numeric value fails the comparison. A numeric value without these options is read as
  Unix seconds (it used to crash the comparison with an ERROR).
- New testfunctions (adare; additive), all with ERROR for a missing/unreadable/corrupt file
  or bad parameters and FAILED only when the file was read and does not match:
  - `json.value_count`; `standard.file_size`; `csv.row_count` (rows matching `entry`;
    counts CSV records, so a quoted line break stays one row).
  - `standard.file_count`: number of files (or directories, `kind: dir|any`) matching a path
    or glob, also archive members (`a.zip!/logs/*.log`); no match counts 0, so
    `expected_count: 0` asserts a group of files is absent.
  - `text.occurrence_count` (string in one or several `encoding`s such as `utf-16-le`, bytes
    or hex, searched in the raw bytes, so it works on binary stores) and `text.line_count`
    (lines containing `content`, or matching it with `regex_match`).
  - `ini.section_exists`, `contains_key`, `value_matches`, `value_count` (tolerant parser:
    duplicates kept, keys before a section, BOM/UTF-16).
  - `image.png_text_matches`, `png_text_count` (tEXt/zTXt/iTXt, CRC checked),
    `exif_value_matches`, `exif_value_count`, `dimensions_match` (Pillow).
  - `plist.*`, `yaml.*`, `toml.*`: `contains_key`, `value_matches`, `value_count`
    (XML and binary plists; multi-document YAML; `tomli` on Python 3.10). Dates compare as
    ISO 8601 strings, binary data as hex.
- Key paths of the json, plist, yaml and toml collections (adarelib; additive): numeric
  indexes (`items[0]`, `items[-1]`), a top-level array (`[0].id`, `[*].id`) and quoted keys
  with dots (`['com.example.key']`). An object key equal to a whole dot segment
  (`files[0]`) still wins over the bracket syntax, so existing paths resolve as before. Shared bodies for key-path formats in
  `adarelib.testset.structured`, content helpers in `adarelib.testset.content`.
- Guide *Checking that something is absent*: `expected_count: 0` or `expect_to_fail`, and
  why an ERROR never becomes a pass.
- `jsonl.line_count` takes `comparison_type` (adare; additive; default `equals`) for an
  integer `expected_count`; with the `{min, max}` form only `equals` is allowed (ERROR
  otherwise). A negative or boolean `expected_count` is now an ERROR.
- Guide *Files inside archives*: a section on Office Open XML (`docProps/core.xml`,
  `docProps/app.xml`) and OpenDocument (`meta.xml`) metadata read with `xml.*` tests.
- `sqlite.row_count` and `excel.row_count` (adare; additive): rows a query returns / rows
  of a sheet matching `entry`, with `comparison_type`. `text.line_count` gains
  `case_sensitive`; `ini.value_matches`, `image.png_text_matches` and
  `image.exif_value_matches` gain `wildcard_mode: any|all`.
- `scripts/migrate_testfunction_renames.py` rewrites playbooks to the renamed testfunction
  parameters (see Breaking).
- **Ordered comparisons** for value testfunctions (adare, adarelib; additive):
  `json`/`yaml`/`toml`/`plist`/`ini.value_matches`, `xml.element_text_matches`,
  `xml.attribute_matches`, `jsonl.value_in_any_line`, `excel.cell_value_matches` and
  `image.exif_value_matches` take `comparison_type` (`equals`, `not_equals`, `greater`,
  `less`, `greater_equal`, `less_equal`), `value_type` (`auto`, `number`, `timestamp`),
  `tolerance` and the time parameters `time_format`, `timestamp_epoch`, `timestamp_unit`,
  `utc_offset`. Numbers compare exactly, timestamps as points in time (ISO 8601, RFC 2822,
  `strptime`, numeric epochs). All defaults keep the old equality/regex behaviour. A value
  that is no number or timestamp, or `!re`/`regex_match` together with an ordered
  comparison, gives ERROR. Core: `adarelib.testset.ordering`.
- **`values_compare`** for `json`, `yaml`, `toml`, `plist` and `xml` (adare; additive):
  compares two values of the same file, e.g. one timestamp earlier than another, within N
  seconds of it, or one number equal to another plus `offset`. Each side must select one
  value: none is FAILED, several are ERROR.
- **`binary` collection** (adare, adarelib; additive) for binary containers without a
  parser: `binary.struct_value_matches` (an integer, float, fixed-size string, C string or
  byte run at an offset, compared by equality, regex or ordered comparison),
  `binary.pattern_count` (bytes, hex, text or a bytes regex in a region),
  `binary.pair_value_matches` and `binary.pair_count` (separator-delimited key/value
  string tables). Offsets are numbers (negative from the end) or expressions that follow
  pointers stored in the file (`u32be@-4+8`) or find a byte pattern (`find:<hex>`). An
  offset outside the file or a malformed expression gives ERROR.
- **SQLite views of the write-ahead log** (adare; additive): `sqlite.query_result` and
  `sqlite.row_count` take `view`: `current` (default, the `-wal` replayed, as before),
  `main_file` (the main database file alone, what is already checkpointed), `wal_added`
  (result rows in `current` but not in `main_file`) and `wal_removed` (rows still in the
  main file but gone from `current`, e.g. deleted and not yet checkpointed). Both sides of a
  difference come from one snapshot; a hot `-journal` is rolled back in every view.
- **`sqlite.wal_frame_count`** (adare, adarelib; additive): counts the `valid` frames of a
  database's `-wal` (what SQLite would replay: salts and checksum chain intact, up to the
  last commit), `commits` (transactions), `all` or `stale` (left from before a WAL reset).
  A missing `-wal` next to an existing database is 0 frames; a corrupt header is ERROR.
- **Before/after and cross-file comparisons** (adare, adarelib; additive): `values_compare`
  of `json`, `yaml`, `toml`, `plist` and `xml` takes `other_dst`, so the second value can come
  from another file or archive member, e.g. a copy a `command` action made before the action
  under test. Host mode pulls `other_dst` like `dst` (sidecars, archives, globs); testfunction
  classes declare such parameters in `host_mode_path_params`.
- **Saved variables in ordered comparisons** (adare, adarelib; additive): an `expected_value`
  of exactly `"{{ name }}"` may be a variable saved during the run. A `save_timestamp` (or a
  `!timestamp` variable without tolerance) is compared as that moment, so `timestamp_epoch`,
  `timestamp_unit` and `time_format` describe only the value in the file. A `!re` variable, a
  timestamp with tolerance or an interval, or text around the placeholder is ERROR.
- **`value_decode`** (adarelib; additive) on the value testfunctions (not excel, image) and on
  `values_compare`: a chain of `url`, `base64`, `hex`, `utf16` and `json` (with
  `decoded_key_path`) applied to the value read from the file before it is compared. A value
  that does not decode is ERROR.
- **`sqlite.values_compare`** (adare; additive): compares the first column of two single-row
  queries, from the same or another database (`other_dst`) and view, e.g. a count in
  `current` against `main_file` in one check. No row is FAILED, several rows are ERROR.
- **`sqlite.free_space_pattern_count`** (adare, adarelib; additive): counts a text, bytes, hex
  or regex pattern in the free space of a database (freelist pages, freeblocks, unallocated
  space between cell pointers and cell content), where deleted rows remain until overwritten
  (`secure_delete` off). `view: main_file` or `current` (the `-wal` checkpointed into a copy).
  A corrupt header or a broken freelist or freeblock chain is ERROR. Parser:
  `adarelib.testset.sqlite_freespace` (standard library only).
  `region: overflow_tail` (also in `all`) covers the unused tail of the last page of each
  in-use overflow chain, where a page freed and reused in the same transaction keeps old
  bytes; a broken chain (cycle, shared page, out of range, wrong length) is ERROR.
  `region: whole_file` counts the pattern in the database, its `-wal` and `-journal` as
  seized (each file on its own, nothing parsed), for "gone from the evidence" checks that
  also cover live data still holding deleted values (`sqlite_stat4` samples, full-text index
  segments); `view: current` with it is ERROR.
- **SQLite `view: commit:N`** (adare, adarelib; additive) on `query_result`, `row_count` and
  `values_compare`: the database as it was after the N-th transaction in the `-wal`
  (negative N counts from the end, `commit:0` is the main file). N out of range is ERROR.
- **`text.lines_in_order`** and **`jsonl.lines_in_order`** (adare; additive): patterns (or
  JSONL condition sets) must match lines in the given order, other lines in between allowed.
  A pattern that is missing or only occurs earlier is FAILED and named in the details.

### Changed
- Removed the leftover `CLAUDE:` debug logs (adarelib variables, adarevm MFT / Linux snapshot /
  Windows icons, OCR): pure traces are gone, real diagnostics keep their level and progress
  traces moved to debug, so INFO output is quieter.
- The `testfunction_search` chat tool returns `{match, results: [cards], known_gaps}` instead
  of a list of full entries; `adare test search` defaults to 5 results.
- `adare experiment run` exit codes (adare): `0` only when every run passed, `1` when any
  run did not pass (FAILED, ERROR, INCONCLUSIVE), `130` when a run was interrupted or Ctrl-C
  ended the command. Before, a single-environment run (`-e env`) exited `0` even when it
  failed, and a batch exited `0` for ERROR, INCONCLUSIVE and interrupted runs. **Scripts that
  relied on exit `0` after a failed run now stop there.**
- `excel.*` opens a workbook once per test (it was re-opened for every sheet) through
  `adarelib.testset.workbook`; `csv.row_count` streams rows; `image.dimensions_match` and the
  EXIF functions open the image lazily (no read cap needed); row mismatches log at debug level.
- CI runs the adarelib tests on the guests' Python 3.10 too (`make test-adarelib-guest`, job
  `guest`); adarelib ships in the guest wheel.
- `content_type: bytes` is **strict** (adare, adarelib) in `standard.file_content_contains`:
  `content` may hold only ASCII characters and Python escapes (`\x00`, `\n`, `\\`). A
  literal non-ASCII character (it was silently searched as its UTF-8 bytes) or an unknown
  escape (`\q`, `\x4`; it was silently searched as the literal backslash text) is now an
  ERROR telling you to write `\xNN` escapes or use `content_type: string` with an
  `encoding`. These inputs fail loudly now; no input silently changes from pass to fail.
  `text.occurrence_count` follows the same rule (shared `parse_byte_string` in
  `adarelib.testset.content`).
- Host test mode, dry-run and parameter validation structure union parameters whose members
  are lists or dicts (adare): `json.array_contains` `expected_value`, the `{min, max}` form
  of `jsonl.line_count` and `windows.registry_value_matches` `expected_value` could not be
  loaded there before. The value is passed through as written, as the guest agent does.
- A count of zero is a **negative test** (adare): `expected_count: 0` (comparison `equals` or
  `less_equal`, or `less` than 1; `sqlite.query_result` included), `jsonl.line_count` with
  `{max: 0}` now get the implicit controls of
  `*_does_not_exist` and `expect_to_fail` tests: a pass becomes INCONCLUSIVE when an earlier
  GUI action failed (and, under `effect_check: prove`, was skipped or showed no effect).
  With `expect_to_fail` such a test asserts presence and is not negative.
- Host test mode looks a testfunction up by `collection.name`, not by its short name, so
  collections that share function names (`value_matches`, `line_count`) cannot be confused.
- cv-server: the OCR golden test no longer ships real desktop screenshots; it pins the
  profile, the model hashes and the text read from rendered UI-string frames.
- Neutral names in comments, tests and docs (example project label `MyProject`).
- The file-content testfunctions now end with an **error**, not a failure, when they cannot
  read their file: the path does not exist, a glob matches no file or more than one, or the
  content cannot be parsed (invalid JSON, a malformed JSONL line with `skip_malformed: false`,
  a CSV parse error, a corrupt workbook). This covers `csv.*`, `excel.*`, `json.*`, `jsonl.*`,
  `xml.*` and `standard.file_content_contains`, `file_content_equals`,
  `file_content_matches_regex`, `file_hash_matches`, `file_timestamps` and `file_permissions`;
  it is the rule `sqlite.query_result` already follows. A failure now always means the file
  was read and the condition did not hold, so `expect_to_fail` can no longer turn a wrong path
  or a failed pull into a pass (errors are never inverted). Playbooks that used a content test
  with `expect_to_fail` to assert that a file is gone get an error instead; use
  `standard.file_does_not_exist`. An existing 0-byte file still fails. The testfunction
  authoring guide and skill now state the rule.
- Invalid testfunction parameters are an **error**, not a failure: `csv.compare_rows` and
  `excel.compare_rows` with `reference_rows` not a list, empty or holding a non-list;
  `excel.compare_rows` with both or neither of `reference_rows`/`reference_file`;
  `excel.validate_columns` with `expected_columns` not a list or empty; `excel.compare_files`
  with an unknown `sheet_mode`; more than one placeholder in `json.array_contains` or
  `excel.cell_value_matches`; an unknown `json.value_matches` `wildcard_mode` (now checked
  even for a single value); an invalid regex with `regex_match` in `json.*`, `jsonl.*` and
  `xml.*`.
- `excel.*`: a sheet missing from the workbook under test still fails, but other read errors
  are no longer reported as failures, and a missing sheet in a *reference* workbook
  (`compare_rows` `reference_file`, `compare_sheets` `reference_sheet`) is an error.
  Parse errors in CSV, JSON, JSONL and Excel files now carry the exception type and trace.
- `jsonl.line_count` counts a 0-byte file as 0 lines, so `expected_count: 0` passes on it
  (it used to fail).
- Testfunction docstring examples use neutral made-up paths instead of real application
  paths (browser profiles, office suites, registry keys); a unit test keeps it that way.

### Fixed
- Timestamp variables (adarelib): a time zone, timestamp text or `format` that cannot be applied
  is now a playbook error naming the variable, instead of a silently wrong or raw value. A
  `timezone: +02:00` style offset was never applied (the value stayed naive and was read as UTC
  or local time); it now is, like a zone name. An unknown zone or malformed offset, an unparsable
  timestamp (it used to come through as its raw text) and a non-string `format` raise
  `ValidationError` when the playbook loads. `ValidationError` is now a `ValueError`, so
  `playbook validate` and `experiment run` report it as a playbook error.
- The `timezone(...)` / `format(...)` Jinja filters (adarelib) check their argument before
  storing it on the variable. A bad zone used to be stored and broke every later variable
  resolution in the run; it now fails at that template, and a literal bad zone
  (`{{ t | timezone('Europe/Berln') }}`) already fails when the playbook loads.
- A test whose templates cannot be rendered is now ERROR for that test (the run and the other
  tests go on), never run against the unrendered `{{ ... }}` text. This covers an unknown
  filter, a syntax error, a filter rejecting its value, a `format(...)` on a variable that is not
  set and an **undefined variable**: test templates are now strict, so `{{ nope }}` is ERROR
  naming `nope` instead of rendering as an empty string (`/tmp//x`). Before, these were logged
  and the test ran on the raw text or the empty value, or was reported as "not found" (FAILED).
  Variables saved earlier in the run and loop variables still resolve.
- `format(...)` in templates is Jinja's built-in again for everything but timestamp variables
  (`"%d items" | format(5)` raised; `"%s" | format("x")` silently rendered `%s`).
- The time zone of a `format(...)` in a test template is parsed like everywhere else: `+0400`
  and `+02` offsets now convert (they were silently ignored), and a bad zone is an error.
- `adare experiment create` wrote a `metadata.yml` whose `environments:` held only comments
  (null), so `experiment run` and `experiment add-env` rejected the new experiment. The
  skeleton now writes `environments: []`, and a null list in an existing `metadata.yml` loads as
  empty. `experiment run -e <env>` on an experiment that lists no environments says how to add one.
- The testfunction upload to the guest skipped files whose stored path did not match the state
  directory (e.g. an `ADARE_HOME` reached through a symlink) with only a warning; the guest then
  reported every test as "not found" with an empty list. Paths are compared resolved, a missing
  or misplaced file (or a failed lookup) fails the run before the playbook starts, and the guest
  says when no testfunctions were uploaded.
- A QEMU run whose QMP/QGA socket path exceeds the OS limit (103 characters on macOS, 107 on
  Linux) failed late in setup with a traceback; it now fails at run preparation, before the VM
  starts, naming the path, its length and the fix (a shorter `ADARE_HOME`).
- `xml.element_text_matches` / `attribute_matches`: an unquoted number (`expected_value: 41`)
  equals the text `41` (it never matched); an invalid `wildcard_mode` is an ERROR even when one
  element matches. `xml.xpath_result_matches` with `text`/`number` FAILS on a missing element
  (it read as `''` / `0.0`, so `expected_value: 0` passed on absence), and an empty element is
  no number. `xml.namespace_matches` finds every `xmlns:prefix` declaration, not only the
  root's namespace, and a missing `expected_namespaces` is an ERROR instead of a crash.
- `excel.sheet_exists`: a `!re` tag in `sheet` is matched against the sheet names; it was
  compared as plain text and failed silently.
- `sqlite.query_result`: `!re` / `!timestamp` cells in `expected_result` are compared with the
  typed cell value, so they match INTEGER columns without `CAST(... AS TEXT)`; a NULL never
  matches a placeholder.
- `!timestamp` without `format` (adarelib, additive): an EXIF date `2024:01:02 03:04:06` is
  read with its date; it was read as today at 03:04:06. A malformed colon date is an ERROR.
- `windows.registry_value_matches`: type names are canonical (`REG_DWORD`, `REG_QWORD`; they
  were reported as `REG_DWORD_LITTLE_ENDIAN` / `UNKNOWN_TYPE_11`, so `value_type: REG_DWORD`
  never matched); the old names are still accepted in `value_type`.
- `visual.count_equals` with `n: 0` is a negative test (INCONCLUSIVE without proof of the act).
- Host test mode (QGA) gives the agent's results: `file_permissions` / `file_timestamps` are
  an ERROR for a missing file (were FAILED), resolve globs, refuse archive members, and use
  the guest clock for `within_last` and zone-less dates; `process_running` matches the full
  command line (`pgrep -f`) and honours `min_instances`; `user_exists` checks `uid` and
  `home_dir`; `registry_value_matches` compares typed values with canonical type names.
- `--backend hostside`: `user_exists` checks `uid` / `home_dir`, metadata of a missing file is
  an ERROR, and `visual.*` tests are refused before the run (no screen after shutdown).
- `standard.file_timestamps` / `file_permissions`: an archive member (`a.zip!/x`) is an ERROR;
  the agent read the temporary extracted copy, so `within_last` passed on the extraction time.
- Playbook timestamp variables (adarelib): an EXIF-form value `2024:01:02 03:04:06` keeps its
  date; it was read as today at that time.
- Host test mode: `linux.*` probes on a Windows guest (and `windows.*` elsewhere) are an ERROR,
  as in the guest agent; they ran the PowerShell equivalents.
- `adare test info` / `test search` show the bundled contract of a collection whose installed
  code differs from it, with a note to run `adare test sync` (they showed none).
- Playbook test checks also run for playbooks with `!re` / `!timestamp` values (they were
  skipped because the YAML was read without the playbook's tags).
- An invalid regular expression (`regex_match`, a `!re` tag or a regex placeholder) is an
  ERROR in every collection, checked before the file is read. Before, a key, element, row or
  line that was not found gave FAILED first and hid it (structured formats, json, ini, xml,
  excel, csv, image, binary pairs, jsonl, `standard.file_content_equals`,
  `sqlite.query_result`). Shared check: `adarelib.testset.compare.regex_expected_problem`.
- `value_decode`: a `decoded_key_path` that selects nothing in the decoded value is FAILED
  (like a key path that selects nothing), not ERROR. A step that fails to decode stays ERROR.
- Archive members (adarelib): a zip whose member name is flagged UTF-8 but is not valid UTF-8,
  or (Python 3.10 guests) an empty member name, crashed the testfunction; both are now an
  archive ERROR. Found by the new seeded fuzz tests of the guest-side parsers.
- `binary.struct_value_matches` (adarelib): a NaN or infinite float is a plain ERROR instead of
  an unexpected-exception ERROR.
- Host mode no longer probes `<dst>-wal-wal` / `<dst>-wal-journal` (and deletes stale local
  copies of them) when `dst` is itself a sidecar such as `data.db-wal`.
- Host mode read stale files: one file cache served the whole run, so a test after an
  action got the copy an earlier test had pulled, and before/after tests compared the same
  copy. Every test now pulls its file fresh from the guest.
- `adare test dry-run` crashed on testfunctions with a `str | int | float ...` parameter
  (e.g. `json.value_matches`). It now structures parameters like a real run.
- Host mode, glob paths: copies an earlier test pulled into the local mirror and since deleted
  on the guest were still matched (`file_exists` passed, `file_does_not_exist` failed on a file
  that is gone). Copies the guest glob no longer matches, or that vanished before the pull, are
  now removed before the test runs.
- Host mode quotes guest paths in the commands it runs (adare): a glob or path with a space, a
  quote, `;` or `$(...)` broke the guest command or ran as shell/PowerShell syntax. Glob
  characters stay active, everything else is literal.
- `!timestamp tolerance: [a, b]` crashed the playbook load; a two-number list now bounds
  *expected minus actual* (adarelib). Other tolerance values (a boolean, a one-element list)
  are a load error instead of being taken as 1 or crashing.
- `YamlTimestamp.compare` (direct use from a testfunction) honours `epoch`/`unit` and a list
  tolerance, parses the expected value with `timestamp_format_comparison` (it parsed the
  artifact value), and reports exceptions in `exception` (adarelib).
- A tar inside LZ4/Snappy used the size cap from the environment instead of the one passed to
  `resolve_archive_path`; a stream over the cap is now a size-cap error, not "single-file
  stream" (adarelib).
- An invalid `!re` pattern or an unknown placeholder gave FAILED ("no match") instead of
  ERROR in every collection (adarelib, adare). `compare_with_placeholder` now raises
  `PlaceholderError`, which the `@testfunction` decorator reports as ERROR; no collection turns
  it into a mismatch any more, so `expected_count: 0` can no longer pass on a broken pattern.
  A literal `!re` that does not compile is a playbook load error.
- `text.occurrence_count` / `text.line_count` / `standard.file_content_contains` searched a
  `!re` placeholder literally (`{{ regex_0_resolved }}`); they now refuse it with an ERROR
  that names the function to use instead. `standard.file_content_contains` with an unknown
  `content_type` is an ERROR (it searched text).
- Host mode, plain path: when the guest said "not found", a copy an earlier test pulled into
  the mirror was still read. It is now removed first. A failed guest glob command (QGA or
  GuestFS) is an ERROR; it looked like "no match", so `file_does_not_exist` could pass on a
  transport error.
- `jsonl.line_count` `{min, max}`: other keys, negative or non-integer bounds and min > max
  are an ERROR (they were used as given). `xml.element_count` and `sqlite.query_result`
  validate `expected_count` / `comparison_type` like the other count functions.
- JSON, JSONL and CSV files were decoded with the guest's locale encoding: a UTF-8 file on a
  Windows guest, a BOM or UTF-16 broke them. They now detect a BOM, BOM-less UTF-16 or else
  read UTF-8; a new `encoding` parameter on `json.*`, `jsonl.*` and `csv.*` names another
  encoding. CSV files are opened with `newline=''`, so quoted line breaks stay in one row.
- Errors of the `standard.*` file tests show the `dst` as written, not an empty resolved path.
- A `{{ variable }}` inside a `!re` pattern was never resolved, so the regex never matched
  (adare); it is now replaced by the variable's value, always regex-escaped (also a value that
  looks like a regex, such as `report (1).txt`). An unknown variable in the pattern is an ERROR.
- An `after`/`before` interval whose bounds were never saved or cannot be parsed is an ERROR
  (it FAILED, so `expect_to_fail` passed). `excel.compare_files` with a sheet that cannot be
  read is an ERROR (it was listed as a sheet mismatch).
- A string variable of digits and dots (`build: "2.4"`, `"42"`) was typed as a timestamp and
  rendered as an ISO date (adarelib); it stays a string.
- `standard.file_permissions`: a symbolic value with a letter other than `r`/`w`/`x`/`-` in
  its place (`rwsr-xr-x`, `zzzzzzzzz`) or a non-octal digit is an ERROR; unknown letters were
  read as `-`, so the test FAILED. `standard.file_timestamps`: `time_format` is tried before
  the Unix-seconds reading, as documented (`20240115` with `%Y%m%d` was read as 1970).
- An LZ4 block whose header announces fewer bytes than it holds is reported as corrupt, not
  as over the size cap (adarelib).
- `!re`/`!timestamp` tests in a playbook **without `variables:`** lost their placeholder
  metadata (no registry to store it in), so every such test was an ERROR (adare); the
  metadata is now kept without a registry.
- Host mode: a glob whose base directory exists but cannot be listed is an ERROR, on Linux
  (`ls … || true` read it as "no match") and Windows (access denied was silenced), so a
  `file_does_not_exist` or `expected_count: 0` test cannot pass on it.
- Docs: playbook examples use real actions and testfunctions (the test-driven analysis and
  diff-analysis guides, the `dir_exists` pages and the filter examples in the action
  reference showed invented ones); a unit test now parses every complete playbook in the docs.
- `adare test dry-run --param entry=[a, b]` passed the list as a string, which became a list of
  characters; `[...]`/`{...}` values of list/dict parameters are read as YAML flow lists/maps now
  (a pattern such as `regex=[Ee]rror` stays a string). Dry-run reports a
  renamed function or parameter instead of "not found" / ignoring it. An invalid regex
  parameter is reported as ERROR without a stack trace.

## [adare 0.1.1] - 2026-11-22

### Added
- Negative results are now proven, not assumed (guide: *Proving negative results*):
  - Every click/keyboard/drag/scroll/goto gets an automatic **effect check**: the screen
    near the input (for keyboard steps: the whole screen) is compared before and after
    (polled up to 1 s, clock/panels ignored).
    `effect: changed|unchanged` goes into the event data and the forensic log; for
    `unchanged` a WebP screenshot is kept and the run summary counts them.
    `settings.effect_check: off|warn|prove|strict` (default `warn`: record only, no
    verdict changes; `prove`: unchanged/when-skipped actions count against negative tests;
    `strict`: `prove` + fail the step); `effect: none` marks an action expected to change
    nothing.
  - New status **INCONCLUSIVE** (15): a passing negative test (`*_does_not_exist`,
    `visual.not_exists`, `count_max` with max 0, `expect_to_fail`, or a testfunction
    declared `@testfunction(..., negative=True)`) is INCONCLUSIVE when an earlier GUI
    action failed or failed its `verify:` (under `prove`/`strict` also: was skipped by
    `when:` or showed no effect). Run verdict
    precedence: FAILED > INCONCLUSIVE > TEST_MISSING > WARNING > SUCCESS. Needs
    adare-server migration `0021_status_inconclusive` before uploading such runs.
    The run summary says "EXPERIMENT INCONCLUSIVE" and counts such tests apart
    ("1 inconclusive", not "failed"); `--format`/batch results report the run as
    INCONCLUSIVE (`summary.inconclusive_runs`).
  - `controls: [test names]` on a test: tests that must have passed before it (else
    INCONCLUSIVE); `adare exp playbook validate` rejects unknown, cyclic or late controls.
  - `verify:` / `verify_timeout` now also on `keyboard`, `drag`, `scroll` and `goto`.
  - Recorded playbooks (`adare dev agent`, `adare dev mcp`) get a generated
    `verify: {exists: {image: ...}}` per click/keyboard step from the region that changed;
    `--plan` adds a `wait_until` gate per verified sub-goal.
- pcap captures (`--capture-pcap`) no longer contain ADARE's own traffic: after the VM
  stops, packets of the adarevm WebSocket (the `adarevm` hostfwd, guest port 18765, incl.
  every `pull`) and of the SLIRP SMB share (`10.0.2.4`) are removed; every other record is
  copied byte for byte. This was typically >90% of a capture (one run: 20.3 MB ->
  61 KB). `<machine>.pcap.filter.json` next to the pcap records the rules, the packet
  counts and the sha256 of the raw and the filtered capture. On by default; keep the raw
  capture with `--no-filter-pcap` or `settings.filter_pcap: false`.
- Web UI **Live** page (sidebar *VMs → Live*, `/live`): lists the running VM instances
  (refreshed every 5 s) and shows the selected one's display view-only and/or its logs
  as they are written (`tail -f` style, one tab per `logs/*.log` of the run holding the
  instance plus the libvirt domain log; filter, pause, follow, wrap). Running instances
  on a VM's page link to it. New endpoints `GET /api/vm-instances/{id}/logs` and
  `GET /api/vm-instances/{id}/logs/{source}?offset=`; instance list rows now carry
  `current_experiment_run_id`.
- Host-side (agent-free) backend: `adare experiment run --backend hostside` (also
  `ADARE_BACKEND`, playbook `settings.backend`; default stays `agent`). Playbooks run
  unchanged with no process of ours in the guest (QEMU Linux guests): GUI through QMP,
  file-effect `command:` actions and environment installations staged into the run
  overlay before first boot (libguestfs or e2fsprogs `debugfs`), `test:` actions
  evaluated on the host over a new `GuestFS` abstraction (offline qcow2/LVM/ext4 via
  dissect) after a clean shutdown, `pull:` and the filesystem diff taken from the image,
  playbook steps written as `marker` events into a qemufile run directory (`<run>/qfm/`).
  Commands that need a guest process fail before boot, naming their class. See
  `docs/guide/hostside-backend`, `scripts/hostside_inventory.py`; optional dependencies
  `uv pip install 'adare[hostside]'`.
- OCR provenance: every run records the cv-server's OCR profile in `<run>/ocr.yml`
  (`ocr-<machine>.yml` per machine): profile, engine and package versions (incl.
  `cv2`), model names + sha256, parameters, language, leading-glyph tolerance and the
  cv-server version, read from the new cv-server MCP tool `get_engine_info`. A server
  that was attached to rather than spawned is recorded as-is, with a warning when its
  profile differs from the requested one.
- Per-experiment OCR pin: `ocr: {engine: rapidocr|paddle, lang: latin|en}` in
  `metadata.yml` overrides the global default (`ADARE_OCR_ENGINE` / `ADARE_OCR_LANG`);
  pin `engine: paddle` to keep an existing experiment on the legacy profile. Dev
  sessions keep their profile across resume and `restart_mcp_server`.
- cv-server: per-frame OCR cache (64-entry LRU keyed by screenshot sha256 + profile
  fingerprint, single-flight). Repeated OCR of the same frame (multi-leaf `wait_until`,
  `when`, `ClosestTo`, failure evidence, polling an unchanged screen) is computed once;
  results are identical by construction.
- cv-server: `--ocr-engine {rapidocr,paddle}` / `--ocr-lang {latin,en}` (env
  `ADARE_OCR_ENGINE` / `ADARE_OCR_LANG`), `ADARE_OCR_THREADS` (onnxruntime threads,
  default 4), `ADARE_OCR_MODEL_DIR`.
- cv-server: golden OCR test on real screenshots and rendered German UI text
  (`make test-cv`), and `adare-cv-server/scripts/ocr_compare.py`, an offline A/B of two
  OCR profiles over a project's recorded runs and text queries.
- Automatic test-run retention: every test-mode run (`adare experiment run` /
  `replicate` without `--production`, not dev sessions) ends by removing older
  finished fake runs of the same experiment **and environment** (rows in one
  transaction, then their run folders), keeping the newest `ADARE_TEST_RUNS_KEEP`
  of that environment (new setting, default 10;
  `adare system settings set ADARE_TEST_RUNS_KEEP N`, `-1` switches it off).
  Counting per environment means a default multi-environment run never removes its
  own results. The run that just finished counts toward the limit and is never
  removed (`0` keeps only it), and neither is the newest successful run (finished,
  result SUCCESS or WARNING), so a burst of failed attempts cannot remove the last
  good run. At most 5 runs per experiment and environment are removed per run, so
  an existing backlog drains gradually (`adare runs prune --fake` removes it at
  once). Runs started less than an hour ago, unfinished runs, dev sessions' runs,
  runs whose folder fails the run-folder test and runs whose folder another project
  sharing `run/` refers to are kept; production runs are never touched. Prints e.g.
  `removed 3 older test runs (1.2 GiB; ADARE_TEST_RUNS_KEEP=10)`, saying also when
  the per-run limit was hit or a folder could not be deleted after its row was; a
  failure (unreadable runs, dev sessions or sharing project) only logs a warning,
  removes nothing and never fails the run. One project had 126 fake runs holding
  10.4 GB of run folders.
- `adare db compact [--dry-run] [--all] [-p PROJECT]` shrinks project databases
  that grew from the base64 screenshot copies older action results kept in
  `action_execution.result_data` (47 GB of a 50 GB database in one project). Only
  image payloads are removed, and only when the decoded image is byte-for-byte
  identical to the PNG its `screenshot_path` names; rows whose screenshot file is
  missing or differs stay unchanged and are reported as kept. Nothing else is
  removed: oversized non-image text (command output) is kept and only counted
  (`rows.non_image_kept`). The database is then vacuumed when there is free space
  of twice the remaining data plus 10 % next to it (and in `TMPDIR` on another
  volume). Refuses to run, naming the blocker, while another process holds the
  write lock, an unfinished run of the project showed activity in the last 30
  minutes (start time or run folder / `logs/` mtime; older ones count as crashed
  and are reported as `stale_runs_ignored`), or a dev session is live.
  `--dry-run` opens the database read-only and reports the reclaimable bytes.
- `adare db check [--all] [-p PROJECT]`: read-only `quick_check`,
  `foreign_key_check` summary and orphaned-row counts per database; exits 1 when
  a database is corrupt. Both commands take `--json`; with `--all` a registered project whose directory or
  database is gone is reported as `missing` (nothing is created on disk) and the
  rest are still processed.
- A command that opens a project database over 512 MiB that still holds
  screenshot copies in `action_execution.result_data` prints a one-line hint on
  stderr to run `adare db compact -p <project>` (not with `--json`/`--format
  json|yaml`). It is shown once; `.adare/compact-hint.json` records the size, and
  the hint returns only after the database grew by half. A successful compact
  writes the marker too. The check is a `stat` below 512 MiB and one
  `octet_length` query (record headers only) above it.
- SQLite upkeep: every connection caps the `-wal` file at 64 MiB after a
  checkpoint (`journal_size_limit`, also on `adare db compact`'s connection), and
  each CLI command and the web API run `PRAGMA optimize` (bounded by
  `analysis_limit=400`, 1 s busy timeout; a read-only or locked database is
  skipped) on the databases they used when they end.
- `adare runs prune [--fake] [--older-than DAYS] [--yes] [--json]`: frees disk space
  in the current project's `run/` directory. A dry run by default: lists run folders
  no database run (and no dev session) refers to, with sizes and a total. A run that
  failed before it recorded its folder (e.g. during VM preparation) keeps every
  folder of its experiment within 16 h of its start, and the runs of every registered
  project whose `run/` resolves to the same directory count too (when one of them
  cannot be read, nothing is pruned). `--fake` also targets finished fake runs (not
  pending/running, not a dev session's run; rows + folders), `--older-than` filters
  by age, and only `--yes` deletes. A folder is only ever selected when it
  is clearly an ADARE run folder: `run/<known experiment>/<run timestamp>` inside
  `run/` with no symlinks, with a `logs/` or `reporting/` subdirectory, unchanged for
  an hour; users' own files in `run/` are never listed.
- Terminal and Claude in the web UI: a terminal panel on every page (sidebar or
  Ctrl+`) runs Claude Code or a shell in a chosen project, as tabs that survive
  page changes and reloads. *Build with Claude* (experiments), *Work on it with
  Claude* (experiment) and *Debug with Claude* (run) start Claude with the task
  set. Terminals only accept requests from this machine (loopback client, local
  `Host` and `Origin`).
- Host resources and run capacity. The web UI has a **System** page (and host tiles
  on the home dashboard): live CPU, memory and disk, every running VM, how many
  more runs of each environment fit right now and what limits them, usage history
  charts, and where the disk space goes, including run disks without an owner that
  `adare vm prune` can reclaim. `adare system resources|capacity|usage|storage`
  report the same. Every experiment run now records what its VM used (peak RAM,
  CPU, disk), and the capacity estimate is sized from those measurements.
- VM images have a record: `adare vm create` registers the disk at once and writes
  `<disk>.image.yml` (install method, OS profile + hash, ISO + SHA256, setup level,
  ADARE version/commit, QEMU version, date) and the guest's package list
  `<disk>.packages.txt`; `adare vm test` adds its result; `adare vm info` shows it.
- `adare vm publish <image> --vm-url <url>` records where an image is hosted;
  `adare env publish-prepare` embeds the image record as `image:` in the
  environment file, and `adare env load` adopts it (and takes `os` from it).
- Every experiment run records the SHA256 of the disk it booted (run row and
  `forensic_log.yml` `vm_sha256`) and writes `image.yml` (environment version and
  image record) into the run directory.
- `adare vm create` for `install_mode: playbook` profiles draws a live status
  block in the terminal: current step, elapsed time, OCR attempt or screen text.
  `--display` now also applies to playbook installs and shows the VM in a QEMU
  window to watch (headless stays the default; a window that cannot open falls
  back to headless).
  The scrollback keeps one line per step with its duration, retries and
  screenshot instead of a line per `click_text` retry. A `click_text` that fails
  reports the text that was on screen; QEMU's output goes to
  `<vm>_playbook/qemu.log`.
- Quality ratchet (`scripts/quality_ratchet.py`, `quality-baseline.json`): ruff
  and mypy violations plus files over 1000 lines are budgeted and may only shrink.
- CI `lint` job (format, strict mypy on `adare.core`, ratchet), weekly
  `pip-audit` workflow, Dependabot, and a coverage summary on the unit job.
- Pre-commit hooks (`make hooks`): ruff-format, ratchet, gitleaks, file checks.
- `make test`, `lint`, `lint-fix`, `lint-baseline`, `typecheck` targets.
- Import smoke test covering every host-package module.
- MIT license (Fraunhofer FKIE); `THIRD_PARTY_NOTICES.md` lists the NVIDIA-derived
  grounding server, which is excluded from it, and the bundled RBCmd.exe (MIT).
- `ADARE_HOME` relocates the whole state directory (default `~/.adare`); the unit
  suite runs against a temp dir and never touches the real one.
- `ADARE_FORWARD_BIND` sets the host address VM port forwards listen on.
- `ADARE_MCP_PORT` sets the `adare mcp serve --transport http` port.
- Guest agent test suite (`adarevm/tests`, `make test-agent`) run on Python 3.10
  in CI on Linux and Windows; a non-blocking CI job runs the CV server tests.
- `adarelib.testset.compare`: row/column comparison, diff report, nested lookup
  and placeholder helpers shared by the csv/excel/json/jsonl/xml collections.
- Guest agent protocol 2 (`adarevm`/`adarelib` 0.2.0): the agent requires the
  run's token (`agent_token` in `config.json`, sent as `Authorization: Bearer`),
  opens every connection with a `welcome` carrying `protocol_version`, versions
  and tools, and serves exactly the `Tool` enum. The host rejects other protocol
  versions (reinstalling the agent once first) and only calls advertised tools.
  `adare debug ws action` / `adare icons dump-all` take `--token` / `ADARE_AGENT_TOKEN`.
- `adare vm test` writes a debug log to `./adare-vm-test-<target>-<timestamp>.log`
  and prints its path at the end, failures included. `--log-file` picks the path,
  `--no-log` turns it off, and an existing global `--logfile` is used as is.
- `adare vm create` for `install_mode: playbook` profiles (Ubuntu 18.04–24.04,
  Kubuntu 20.04–24.04) now makes the installed desktop ADARE-ready for
  `--setup base`/`full` (the default): it installs `qemu-guest-agent` from a text
  console, then over the agent sets passwordless sudo, automatic login, no idle
  lock/blanking, no first-login wizard and no background apt updates (`full`:
  `python3-pip` + `uv`), reboots and checks the agent and the autologin session.
  Any failed step fails the build with a screenshot. Profiles can override the
  console part with `bootstrap_steps`. Before, these images had no guest agent,
  so `adare vm test` and experiments waited on it until every boot retry was spent.
- Every unattended `adare vm create` (autoinstall, preseed, kickstart, AutoYaST,
  Windows autounattend) ends with a readiness pass for `--setup base`/`full`: the
  finished disk boots once, the guest agent must answer, Linux desktops get no
  idle lock/blanking (GNOME, Plasma 5/6, Xfce) and no first-login wizard, and
  after a reboot the `adare` autologin session must exist (Windows: checks only).
  A failure fails the build and keeps the installed disk;
  `<disk>_readiness.log` has every command. Recipe base disks get it too.
- Manual Linux installs (`install_mode: manual`) get the same setup as playbook
  installs after you finish: ADARE logs in as `adare`/`adare` on a text console,
  installs `qemu-guest-agent` (apt, dnf, zypper or pacman), provisions over the
  agent and checks it after a reboot; a failure only warns. NixOS gets the
  `configuration.nix` lines instead. Autologin now also covers LightDM (Mint,
  elementary) and picks the display manager that is actually enabled.
  `--setup bare` skips all in-guest setup for every install mode.
- A Linux guest that boots but whose guest agent never connects now fails after
  the first boot attempt with "guest agent never connected, although the guest
  finished booting" and a screenshot, instead of a bare timeout after three cold
  boots (~19 min). The guest's screen sitting still for a minute is what tells it
  apart from a slow boot.
- Image targets honour the offset `base` (`top-left`, `center-left`, ...) like text
  targets: the box comes from the new `sizes` field of `find_icon` (or the
  template's native size). `center` (the default) is unchanged. Image and icon
  candidates below the confidence floor are dropped before the strategy runs, and
  `target.min_margin` (0.0-1.0) accepts a match only if it beats the best other
  above-floor candidate by that margin.
- `click` takes `verify: {exists|not_exists: <target>}`, `retries: n` (default 0)
  and `verify_timeout` (seconds, default 3): after the click the condition is
  polled; if it does not hold the target is re-resolved and clicked again, up to
  `retries` more times, and the action fails if the effect never appears. Without
  `verify` a click behaves exactly as before.
- `ADARE_CLICK_SETTLE_MS` sets the QMP pointer-move-to-press gap (default 10 ms,
  the previous fixed value).
- Evidence on a failed action: screenshot of the last search, a fresh screenshot,
  the full OCR dump and the target description(s) are written to
  `<run>/reporting/failure/aNN_*` (switch off with `ADARE_FAILURE_EVIDENCE=0`).
- Playbook-level `on_failure:` action list: runs once after the first failure that
  stops the playbook and before the run ends; never changes the failed status.
  Accepted by `adare exp playbook validate` and validated like normal steps.
- Cross-process VM slots (`adare.backend.vm.slots`): `N` flock files under
  `<appdata>/vm_slots/` cap the live VMs across all `adare` processes (N =
  the `ADARE_MAX_VMS` setting, default 20, the
  old per-VM instance limit). Every run's VM (QEMU run instance or pooled
  VirtualBox instance) takes one slot before it boots (waits up to
  `ADARE_VM_SLOT_TIMEOUT`, default 30 s) and keeps it until the run is removed or
  the instance released, so parallel runs cannot exhaust host memory; the kernel frees a crashed
  process's slot. `adare vm slots status [--json]` shows the slots;
  `adare vm slots exclusive [--timeout s] -- <cmd>` runs a command holding every
  slot (its adare child processes run under that lease). A slot belongs to the
  allocating process, so a VM that outlives it (detached dev session) stops counting.
- `adare dev remove --stopped [--older-than 14d] [-y]` removes stopped dev
  sessions in bulk, listing each with the VM disk it keeps (on this host 25
  forgotten sessions held ~164 GiB). `adare vm prune` reports that space too.
- `adare system settings list|get|set|unset`: host limits saved in
  `~/.adare/settings.json` (`ADARE_MAX_VMS`, `ADARE_VM_SLOT_TIMEOUT`,
  `ADARE_MIN_FREE_DISK_GB`, `ADARE_DEV_SESSION_MAX_AGE_DAYS`), each resolved
  environment variable > saved setting > default and validated when set.
- Opt-in expiry of forgotten dev sessions: with the `ADARE_DEV_SESSION_MAX_AGE_DAYS`
  setting, every experiment run and `adare vm prune --force` remove stopped/crashed
  sessions unused for longer than that (never running ones, never one whose VM is
  up, never from inside a dev session). Off by default.
- Runs refuse to start when a filesystem they write to has less than
  the `ADARE_MIN_FREE_DISK_GB` setting free (default 10 GiB, 0 disables), with the cleanup
  commands as suggestions, instead of filling the disk mid-run.

### Changed
- Run screenshots (`reporting/screenshots/`, failure evidence) are re-encoded losslessly
  as PNG at zlib level 9 in a background thread after they are written: pixel-identical,
  roughly 25-50% smaller. The file is swapped atomically and only when smaller; a run
  waits for pending jobs before it finishes. The file's sha256 is no longer that of the
  bytes the guest sent. `ADARE_SCREENSHOT_PNG_LEVEL=0-9` picks the level, `off` keeps
  the captured bytes.
- `sqlite.query_result` now ends with an **error**, not a failure, when the database cannot be
  evaluated: a missing database file, or any SQL error (syntax, unknown table or column, a
  corrupt or unreadable database). A failure now always means the query ran and the result did
  not match, so `expect_to_fail` can no longer turn a missing database into a pass (errors are
  never inverted). Playbooks that used `expect_to_fail` on a missing table or database get an
  error instead; assert absence with a query that runs (e.g. `expected_rows: 0`). Every result
  after the query ran, a pass included, now reports the rows read as `query result: [...]`
  (cut after 2000 characters).
- Locked dependencies upgraded to clear the 68 pip-audit advisories (authlib 1.9.5,
  certifi 2026.10.23, dnspython 2.9.2, fastmcp 3.4.11, filelock 4.2.9, joserfc 1.8.0,
  mcp 1.30.0, opentelemetry-api 1.45.2, pillow 13.0.0, setuptools 84.2.1). The guest
  packages' minimums are unchanged (guests stay on Python 3.10).
- `paddlepaddle` (cv-server `paddle` extra) now comes from PyPI (same 3.2.2 wheels, now
  hash-pinned in `uv.lock`) instead of paddlepaddle.org.cn, whose index answers GitHub
  with 403 and made every Dependabot `uv` update fail. Dependabot now updates `uv.lock`
  only (`versioning-strategy: lockfile-only`).
- **OCR engine: RapidOCR is the new default.** New cv-servers use the pinned profile
  `rapidocr-v5m-latin`: RapidOCR on onnxruntime (CPU on Linux, Windows and macOS),
  PP-OCRv5 mobile detection + mobile Latin recognition, model files verified by sha256
  (a mismatch is a hard error). Measured on real experiment screenshots: 0.2-0.3 s and ~1 GB
  per frame instead of 11.3 s and 6-21 GB (PaddleOCR), word recall 97.4% vs 95.1%,
  rendered German UI lines 92% vs 76%. OCR results - and so clicks - can differ from
  the PaddleOCR runs (about one in six anchored-line queries; two words up to ~30 px
  apart now read as one line): pin `ocr: {engine: paddle}` for experiments that must
  stay on the old profile. With this profile only, a line also matches with one
  leading run of 1-2 glyphs stripped (`>Bookmarks Menu`, `• Other`).
- PaddleOCR is now the `paddle-legacy` profile, unchanged, in the optional
  `adare-cv-server[paddle]` extra (the workspace still installs it). The cv-server
  starts it with `PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True` (~3 s faster start).
- OpenCV is pinned to 4.10.0.84 for `opencv-python`, `opencv-python-headless` and
  `opencv-contrib-python` (workspace `constraint-dependencies`): all three install the
  same `cv2` module, so which version loaded depended on install order (the lock said
  4.13, the environment ran 4.10).
- `adare runs remove`, `DELETE /api/runs/{ulid}`, `adare experiment clean` and
  `adare experiment remove` also delete the run folders of the runs they remove,
  through the same run-folder safety test as `runs prune` (a refused folder is kept
  and reported; the rows are deleted anyway). Database run paths are matched by
  their `run/<experiment>/<timestamp>` tail, so moved projects still match.
  `runs remove --keep-files` (web: `keep_files=true`) and `experiment remove
  --keep-files` keep the files. A folder a dev session refers to (any status) is
  never deleted, and neither is any folder when the dev sessions cannot be read.
  `experiment clean` keeps fake runs that are still pending or running and dev
  sessions' runs. The automatic fake-run cleanup after a test run
  still removes only the rows; `runs prune` collects those folders.
- SQLite databases now use write-ahead logging (`journal_mode=WAL`) with
  `synchronous=NORMAL` and a 30 s busy timeout (was 5 s), set on every connection:
  readers no longer block a writer, so the CLI, web UI and a running experiment can
  share a database without `database is locked`. WAL is recorded in the database
  file, which gains `-wal`/`-shm` sidecar files next to it. A read-only database
  file or directory, where the switch to WAL cannot be written, keeps its journal
  mode and stays readable. Foreign-key enforcement stays off. See *Connection
  settings* in the database migrations docs.
- Development tasks have one definition: CI runs the Makefile targets (`make lint`,
  `make test`, `make test-agent`, …) instead of its own copies of the commands.
  Every target syncs what it needs first (`--inexact`, so it never strips the
  qemu extra or the CV server from `.venv`); new: `make sync` (use instead of
  plain `uv sync`), `make test-testfunctions`, `make test-cv`, and `make test`
  takes `PYTEST_ARGS=...`. `make test-agent` now also works on Windows.
- CI tests guest code on the guests' Python: the testfunction tests also run on
  Python 3.10 (`make test-testfunctions-guest`, Linux + Windows), next to the
  agent suite, in one venv (`.venv-guest`, replaces `.venv-agent`) pinned by
  `requirements-guest-test.txt` (`make lock-guest` re-pins it).
- CI also runs `make install` + `make update` on Linux, macOS and Windows
  (`make test-install`), the unit suite on macOS, and builds the docs on every PR.
  `make docs` treats Sphinx warnings as errors.
- The unit suite has a coverage floor (`make test-cov`, 39%); the CV server job
  now blocks merges; `make lint` runs mypy once (the ratchet fails on any error in
  `adare.core`). Pushes to dev/main no longer cancel each other's CI runs.
- `make install` / `make update` install exactly what `uv.lock` pins (`--locked`)
  and stop at the first failing step instead of carrying on. They no longer need
  a system Python (uv provides 3.13), work from any directory, and never remove
  extras you added. The installation guide gained an *Updating* section.
- Images never change. A different disk under a registered name is a new image:
  `--force` (`vm create`, `env load`) keeps the replaced image as
  `<name>-<sha12>` for the environment versions that use it, or removes it when
  none does. A recipe image whose disk is missing is no longer rebuilt silently
  during a run (the rebuild has other bytes); the run says to reload with
  `adare env load --force`, which makes it a new environment version.
- `adare env load <name>` finds the registered environment's file; a `name:` key
  that differs from the file name is reported as ignored; a disk is hashed once
  per load.
- OS profiles: a YAML profile is now the only definition of its OS. The 12
  built-in catalog entries that a shipped profile replaced (never used, several
  stale) are gone; a test keeps it that way, and another requires every x86_64
  Ubuntu/Kubuntu LTS profile to install the desktop edition. The VM image guide
  records when each profile last ran.
- `adare vm test` on a registered (QEMU) VM now gives the guest its agent the way
  an experiment run does: the same agent wheels, shares and `config.json` with the
  agent token, the same install and launch, and the same WebSocket connection
  (retries, guest diagnostics). The agent starting and answering now decides the
  verdict, since experiments run their tests through it; before, the test started
  adarevm its own way and its failure did not count. A failed test keeps its run
  directory with adarevm's logs under `~/.adare/state/vm-test/run/`.
- CLI commands renamed or moved to the group they belong to. The old names
  still work (hidden from `--help`) and print the new name on stderr:
  - `adare run list/info/remove` -> `adare runs ...` (no longer looks like
    `adare experiment run`)
  - `adare agent setup/status` -> `adare skills install/status` (no clash with
    `adare dev agent`)
  - local web UI: `adare web start/services/build/install-spice` ->
    `adare ui start/status/build/install-spice`; `adare web` is now only the
    ADARE Web platform (login, download, publish, submit)
  - `adare cv ...` / `adare ws ...` -> `adare debug cv ...` / `adare debug ws ...`
  - `adare os-profile` -> `adare vm profile`, `adare vm gui-doctor` ->
    `adare vlm doctor`, `adare dev grounding-pull` -> `adare vlm pull-grounding`
  `adare vlm rm` is now `adare vlm remove` (`rm` stays an alias, `l` joins `ls`),
  and `adare experiment run` accepts `-p` for `--project` like its siblings.
- `adare vm remove <name-or-id>` removes what `adare vm list` shows: a registered
  VM (with the environments that run on it, after showing what goes and asking;
  `-y` skips the prompt) or a VM instance, by name or ID. It refuses while an
  instance is running, and never removes a VM that another version of one of
  those environments runs on. `--id` still works. Usage errors now exit 2.
  `vm prune` lists registered VMs no environment uses (it does not delete them).
- `vm reset`, `vm remove --env` and their prompts now say what they do: remove
  instances. Registered VMs were never deleted by them.
- `env remove` refuses without `--force` when a registered project cannot be
  checked for references, and deletes exactly the versions it checked.
- `env load --force` on an unchanged file whose disk is unchanged no longer adds
  a duplicate environment version.
- VM snapshots (`SnapshotManager`) are VirtualBox-only; QEMU runs have no
  instance to snapshot.
- `adare vm` help separates registered VMs (`list`, `info`, `reset`) from
  instances (`usage`, `remove`, `snapshot`, `prune`); `vm create` no longer
  suggests `--no-copy` for a disk already in managed storage.
- A run fails early when its environment and VM disagree on the hypervisor
  (possible for environments loaded before the load-time check).
- `--preserve-snapshot` on a QEMU run warns that it is VirtualBox-only and points
  to `--export-disk-image` instead of silently doing nothing.
- QEMU runs no longer copy the environment disk into a pooled instance (a full
  `qemu-img convert`, ~12 GB, per instance). Each run boots a throwaway overlay
  directly on the read-only environment disk with its own UEFI varstore, domain
  config and domain UUID, all removed when the run ends; runs of one environment
  are independent and can run concurrently. Non-qcow2 disks are converted once.
- The QEMU vTPM is per run: every run boots a copy of the environment's vTPM
  template (adopted from the previously shared vTPM, or manufactured once), so
  the TPM identity stays stable but no run inherits another run's TPM changes.
- The run-time disk integrity check hashes the full disk only when it changed
  since its last verification (size/mtime/ctime/inode, cached under
  `~/.adare/state/disk-digests/`); managed disk copies are read-only on POSIX.
- VM instances record their owning process (`owner_pid`, migration
  `add_owner_pid_to_vm_instance`). Instances of crashed runs are reclaimed by the
  next QEMU run and `adare vm prune`, which also removes pooled QEMU instances
  left from before per-run overlays; a live run's instance is never touched.
- `adare vm remove --all` / `--env` remove instances, as documented; they used to
  delete the VM registrations and break every environment using them (`adare vm
  reset` remains the command for that).
- Environments are versioned. `adare env load --force` on a changed file adds a
  new version and keeps the old one with its runs; it used to delete the old
  environment and every run of it in every project. `env remove` deletes all
  versions, and `--force` now detaches experiments instead of leaving them
  pointing at a deleted environment. Migration `add_environment_versioning`.
- An environment without `hypervisor:` infers it from the disk (VirtualBox for
  OVA/OVF/VDI/VMDK, QEMU otherwise) instead of always defaulting to VirtualBox.
- `env load` refuses a disk-image environment without an `os` block, a
  `vagrantbox`-only environment, and a local disk that does not match a declared
  `vm_sha256` (only URL disks were checked).
- Environments sharing one disk must agree on its hypervisor and guest
  platform/architecture; `--force` refuses to replace a disk another environment
  uses, and a run fails if its environment's disk was replaced after loading.
- `env create --with-vm` writes the disk path into the new file instead of
  registering the disk (`env load` does that).
- `-p` is hidden on the environment commands that ignored it (environments are global).
- Whole workspace formatted with `ruff format`; safe ruff autofixes applied.
- `uv.lock` is committed; CI installs with `--locked`.
- ruff and mypy pinned exactly in a `lint` dependency group.
- Built-in testfunctions report an unexpected exception as ERROR (they used to
  catch everything; Excel read errors even became FAILED). Unreadable workbooks
  and uninterpretable placeholder values still fail the test.
- Sphinx output is no longer committed: `make docs` builds to
  `docsrc/build/html` and the docs workflow publishes it; `docs/mcp-clients.md`
  moved to `docsrc/mcp-clients.md`, design notes to `docsrc/design/`.
- `adare mcp serve --transport http` defaults to port 13112 (was 13111, which the
  LocateAnything grounding server also uses).
- Guest agent wheels carry a content-hash version (`0.1.1+g<hash12>`); guests
  provisioned with a plain `0.1.1` reinstall the agent once on their next run.
- `make install`/`update` copy only what ADARE reads at runtime into
  `~/.adare/adare` and prune everything else (an existing copy shrinks from
  several GB to ~10 MB on the next `make update`).
- Importing `adare.config.configdirectory` no longer creates directories; the CLI
  and web API create them at startup.
- New `adare.services` functions must be fully typed (mypy override restored).
- Database APIs share one engine per database file and set the schema up once
  per process; nested `with api:` blocks join the outer transaction.
- Web API handlers run services off the event loop (threadpool / `to_thread`).
- Mixins declare their host for type checking (`QEMUVMHost`, `VirtualBoxVMHost`,
  `ActionsExecutorCore`, DB API hosts): ~720 fewer mypy errors.
- Fewer fixed waits on the VM path: guest-agent polls back off from 50 ms instead
  of a flat 0.5 s (≥0.5 s saved per guest command), the agent connection probes
  the real WebSocket handshake instead of sleeping 3 s (6 s in `vm test`), dev
  snapshot create/restore run off the event loop, and host-mode screenshots skip
  a 0.1 s settle and encode PNGs faster (level 1: same pixels, ~1.5x larger files).
- Downloads stream 1 MiB chunks into `<file>.part` and are renamed into place
  only when complete, hashing as they go; the sha256 check after an ISO/VM
  download no longer re-reads the file.
- Installer ISO / downloaded VM digests are cached in a `<file>.sha256` sidecar
  (size, mtime, inode); `vm create` and `env load` re-hash only a changed file.
- Faster startup: pandas, requests/aiohttp, trogon and the OS-profile catalog
  load on first use (`import adare.run` ~98 -> ~44 ms, DB commands ~-160 ms);
  `load_catalog()` is cached until a testfunction source changes.
- cv-server: `find_icon` runs off the event loop and decodes its inputs once
  per request; OCR calls share one executor (they queue instead of running
  concurrently on the shared PaddleOCR instance).

### Fixed
- `adare experiment run` without `-e` (all environments): the closing summary crashed on a
  missing helper and, past that, deadlocked on the console lock; it now prints.
- `settings.effect_check: off` written unquoted (YAML reads it as false) is accepted as off.
- False passes: a host-mode (QGA/hostside) test whose file read failed for any reason other
  than "no such file" (guest agent down, timeout, permission) is now ERROR. Before, a
  `*_does_not_exist` test passed on a transport error and a glob match that failed to pull
  silently dropped out of the test.
- Test results are stored with their real status (SUCCESS/FAILED/ERROR/WARNING/
  INCONCLUSIVE) instead of only SUCCESS/FAILED; under `expect_to_fail` the test's own
  answer is kept in the details, and a WARNING under `expect_to_fail` now explicitly
  counts as "passed although expected to fail".
- The forensic log now carries a GUI action's error message, `verify:` outcome
  (`verified`, `click_attempts`), the typed `text`, `skipped` (a false `when:`) and the
  effect check; action events finally fill `Event.error`.
- Idiom templates: `delete_file_and_verify` used a non-existent testfunction
  (`filesystem.file_does_not_exist`, `path:`) and never ran its test; it now uses
  `standard.file_does_not_exist` with a `file_present_before` control.
  `open_app_and_verify` used the non-existent `visual.text_on_screen` (now `visual.exists`)
  and never ran its test either.
- Playbook `tests:` entries now reject unknown keys (e.g. a `paramter:` typo) at parse time,
  with a `did you mean: parameter?` hint, instead of silently dropping the key and failing
  at the end of the run with `NotAnAttrsClassError`. Validation errors from `parse_playbook`
  are now a readable path-qualified `ValueError` rather than a bare cattrs `ClassValidationError`.
- Runs list (`/api/runs`, `adare runs list`, web Runs page) is newest first across all
  projects instead of project by project in database order, so running runs are on top.
  The web Runs page sorts by any column (click a header), counts active runs, and
  refreshes itself (every 5 s while a run is active, else 15 s) so CLI-started runs appear.
- Times in the web UI were shown shifted by the UTC offset: the backend stores naive UTC and
  the browser read the zone-less strings as local time; adare-web now reads them as UTC.
  Dev-mode sessions, checkpoints and restored dev-session runs wrote local time instead of
  UTC (which also skewed stale-session expiry); they now write UTC like everything else.
  Rows written earlier by dev mode keep their local time.
- Two VMs starting at the same moment no longer fail with "UNIQUE constraint failed:
  vm_instance.websocket_port". The loser of the port race now moves on to the next
  free port; its retry handler used to crash on a missing `session` attribute. A
  clash on anything other than the port, such as a duplicate instance name, is
  reported directly instead of being retried across the whole port range.
- Unattended Windows 10 x64 builds: the answer file selects an edition (generic Pro
  key, no activation), so the multi-edition 22H2 ISO no longer stops at "Windows
  cannot read the <ProductKey> setting from the unattend answer file", and it loads
  viostor from the Autounattend floppy (A:\) only, like Windows 11. `vm create`'s
  Setup error watch now also stops on "Windows cannot ..." dialogs instead of waiting
  for the 90-minute timeout.
- `--test-mode host`: every host-evaluated test read as failed (UNKNOWN) whatever the test
  function returned, because its result was handed on in the wrong shape; and tests with
  `str | int | float` parameters (`standard.file_timestamps`) could not be loaded host-side.
- Web API / web UI contract sweep (every route now has contract tests in
  `tests/unit/adare/webapi`, asserting the fields adare-web reads):
  - Security: `/api/playbooks/save` only accepts a bare file name; run-artifact and
    static-file serving no longer admit same-prefix sibling directories; unknown
    `/api/...` paths are JSON 404s instead of the SPA page.
  - The web client rejects HTTP-200 `success: false` responses, so refused actions
    show the server's error instead of a success toast.
  - Runs: Test results tab lists each test once with its status; OS / VM box,
    result column, run-to-environment (now the run's own environment, also for the
    environment filter) and delete-by-ULID work.
  - Experiments: real `project_path`, `run_count`/`last_run`, tag filter across
    projects, list links by dotnotation, validate reports the verdict.
  - VMs: running-VM links from the System page, Path column, instance names,
    remove-stopped toast; snapshot delete on a QEMU host returns an error, not a 500.
    `VmInstanceUsage.stopped_instances` (always 0) is now `cleanup_pending_instances`.
  - Environments: OS label, sync and recipe badges, Verify without a project, one
    malformed YAML no longer breaks the list, Check URL sends `vm_format`.
  - Projects: get by path and delete by name no longer 500; vanished testfunctions are
    hidden; `/api/web/sync` fails when nobody is logged in.
  - Develop sessions: soft/hard reset work (web UI and `adare dev reset`), session
    labels, checkpoint sizes, cleanup counts; unsafe checkpoint names are rejected.
  - Action palette: `/api/actions/types` is generated from the playbook parser's
    action classes, and the workbench emits actions the parser accepts.
- Web UI: experiment pages opened from the Runs list or an Environment page showed
  `["experiment", …] data is undefined`. Those links pass the `Project.experiment`
  dotnotation, which `GET /api/experiments/{name}` now resolves (short names still
  work); a missing experiment now shows "not found" instead. The page also scopes its
  runs to the experiment's project and enables Run from the detail payload's
  `environments`.
- SMB file transfer no longer reverts host-written run files. The SMB share serves a
  copy of the run directory taken at VM setup, and the writeback at retrieval copied
  that whole copy back, resetting every file the host kept writing (`logs/mcp_gui.log`,
  `qemu_debug.log`, ...) to its setup-time content and mtime: SMB runs (e.g. all
  arm64 runs) kept only the cv-server's first ~2 s of log, losing every OCR/CV call.
  The writeback now copies only files the guest created or changed since staging
  (replacing the `adare.log`-only exclusion).
- On Windows, any adare command that printed a character the console encoding
  (cp1252) cannot represent crashed with `UnicodeEncodeError`; e.g. `adare db
  migrate` (run by `make install`) aborted on a migration's `✓`. The CLI now
  prints `?` for such characters instead.
- Editing a playbook and starting a default (test-mode) `adare experiment run` or
  `replicate` deleted the experiment and every run of it, production runs
  included, and recreated it under a new id: the load before a test run used
  `--force`. A changed experiment without production runs is now reloaded in
  place (same id; metadata, environments, tags, tests and playbook refreshed; its
  finished fake runs deleted with their run folders, unfinished ones and dev
  sessions' runs kept). A changed experiment *with* production runs is refused in
  both modes, naming the run count and the ways out (clone it under a new name,
  restore the playbook, or `adare experiment load --force`), because a run does
  not record the playbook it ran and would otherwise end up under one it never
  executed. `adare experiment add-env` / `remove-env` reloaded with `--force` too
  and now report such an experiment as failed (its `metadata.yml` is updated)
  instead of replacing it. Only the explicit `adare experiment load --force` still
  replaces the experiment with all its runs. `adare experiment playbook set` now refreshes the
  experiment's content hash and tests too, so the next run no longer sees a
  change, and refuses a changed playbook (writing nothing) when production runs
  exist.
- Re-ingesting a playbook while a run of the experiment was in progress deleted
  the items that run had not executed yet, so its later action executions pointed
  at missing items. While a run is unfinished and showed activity in the last 30
  minutes (as `adare db compact` decides), every old item is kept, marked
  superseded; the next re-ingest without an active run deletes the ones nothing
  executed.
- Nested run events stored the enclosing action's key in `event.parent_event_id`,
  a foreign key to `event.id`, so every nested event was a foreign-key violation
  (`adare db check` reported 44k `event -> event` violations in one project). The
  key now lives in the new `event.parent_group_id` column; the
  `move_parent_event_keys` project migration adds it (indexed) and moves the keys
  earlier versions wrote, keeping any value that names a real event. Run views
  and run tallies read the new column, and `adare runs info` no longer issues one
  query per nested event to compute its indentation.
- Loading an experiment's playbook again (`adare experiment playbook set`, or a
  reload of a changed playbook) deleted all of its playbook items, so the action
  executions of earlier runs pointed at items that no longer existed (`adare db
  check` counted them as `action_execution_dangling_playbook_item`). Re-ingest now
  keeps every item an execution references, marked superseded (new column
  `playbook_item.superseded`, added by the `add_superseded_to_playbook_item`
  migration), and deletes only the others; runs and the run controller use only
  the current items. Removing the experiment still deletes all of them.
- `adare db reset` and `adare db clean-install` deleted only the main database
  file and left its `-wal`/`-shm`/`-journal` files behind, which could corrupt the
  next database created under that name; they now remove all of them. Removing a
  project closes its pooled database connections before deleting the directory.
- Deleting runs left rows behind in the project database: every run delete
  (`adare runs remove`, `adare experiment clean`, `adare experiment remove`,
  fake-run cleanup after a test run, `adare environment remove --force`, and
  replacing an in-use testfunction) kept the run's action executions (with their
  result blobs), its run-files row and its two log-file rows, because foreign keys
  are off in SQLite and the ORM cascade does not reach them. All of them now go
  through one `delete_runs` helper that removes these rows too. A project
  migration (`delete_orphan_run_rows`) deletes the action executions, run-files
  and log-file rows earlier deletions left. The freed space is reused by the
  database but the file only shrinks after a vacuum.
- Replacing an in-use testfunction with `--force` said it deleted the runs that
  used it but deleted none: it searched the global database, while runs live in
  each project's database. It now deletes them in every registered project.
- `adare runs list` took ~150 s on a project with 4.5k runs and now takes under a
  second: every run's verdict lazy-loaded all of its events through an unindexed
  column. Verdicts are now read for all runs in two queries (also in the web UI's
  run list), and a migration indexes the columns that look up a run's events,
  stages, action executions and playbook items. `adare runs info` loads only the
  requested run instead of every run of every project.
- `adare runs list` inside a project registered under a name other than its
  directory's (e.g. `MyProject` at `.../adare`) listed no runs; it filters by the
  registered name and no longer reads the other projects' databases.
- The same directory-name-instead-of-registered-name mixup also affected
  experiment/environment dotnotations resolved from the current directory and
  the "current project" used to shorten names in experiment, environment and
  testfunction listings. All of them now resolve the registered name through one
  helper, `adare.backend.basics.registered_project_name` (falling back to the
  directory name for an unregistered directory).
- Database read helpers (`safe_query_*`, `safe_count`, `safe_get_*`), the global
  reference manager and the current-project lookup caught every exception, so a
  programming error looked like a missing row or an empty listing. They now turn
  only the expected database errors (SQLAlchemy, sqlite3, the database API's own,
  `OSError`) into their default and let anything else propagate.
- Removing a dev session (or any old pooled QEMU instance) whose VM config was
  already gone deleted only its database rows and left its full disk copy
  (`<name>-base.qcow2`, ~4-50 GiB) behind; the copy is now removed by name. The
  removal also no longer warns "Could not restore websocket_port" per session.
- Two runs started at the same moment can no longer get the same CV/OCR server
  port: `find_free_cv_port` also reserves the port with a lock file until the
  server stops. VirtualBox experiment snapshots are named after the random tail
  of the run ULID, not its timestamp, so runs started together no longer collide.
- A crashed or killed run (`kill -9`, closed terminal, interrupted session) no
  longer leaves its QEMU VM running with its RAM until the next run or
  `adare vm prune`: the first QEMU run of a process starts a small reaper that
  waits for the process to exit and then removes its leftover runs
  (`reconcile_instances`; other processes' runs and dev sessions are untouched).
- A crashed or killed run no longer leaves its CV/OCR server running (up to
  ~1.6 GB each, holding its port): runs start it with the new
  `adare-cv-server --exit-with-parent`, which exits once its `adare` process is
  gone. Dev-session servers keep outliving the CLI as before.
- `adare exp run`'s result summary (`--output json/yaml/...`) reports the run's
  real duration and start/end time instead of 0.0, and a failed run says
  "Experiment failed" instead of blaming the tests.
- `adare vm slots status` reports the configured `ADARE_MAX_VMS` as the total
  instead of the number of slot files on disk.
- Two runs of the same experiment started in the same second no longer fail with
  "Failed to create run directory structure ... File exists": the second run
  gets `<timestamp>_2` (also for diff runs).
- Project databases no longer fill up with screenshots: each action's result was
  stored with its base64 screenshot inline (~170 KB per action, one project
  reached 47 GB). Image payloads and strings over 16 KiB are now replaced by a
  size marker; explicit screenshots stay on disk under `reporting/screenshots`.
- The web UI's live VM view runs on the current VirtualSpice (with `vspice`,
  MCP and one server per data dir): `adare ui start` gives its VirtualSpice its
  own data dir (`~/.adare/virtualspice`), so it no longer fails while the
  VirtualSpice app is open and ADARE's run VMs stay out of its library; reuses a
  VirtualSpice already answering on the port; skips VirtualSpice builds too old
  for this; says why VirtualSpice did not start; writes its output to
  `~/.adare/virtualspice/adare-server.log` (an unread pipe could fill and freeze
  it). `--spice-port` now also moves the viewer and `adare vm watch` lookup,
  which were fixed to 8081. Clicking and typing in the viewer needs a
  VirtualSpice with the input fix (mouse message ids, key releases).
- VMs with shared folders start on libvirt 10.0 and newer (e.g. Ubuntu 24.04):
  defining the domain failed with "invalid idmap start/target/count settings".
  The virtio-fs `<idmap>` used attributes libvirt does not have; older libvirt
  ignored the element, so it is now left out and shares behave as before.
- The Windows installer (`install.ps1`) works with the single workspace `.venv`
  again: it found no `adare.exe` and stopped. It now also puts the CLIs on your
  user `PATH`, migrates the database and syncs testfunctions like the Linux/macOS
  installer, and doubles as the Windows update (`make update`).
- `vm create windows11` (x86_64) failed right after boot with "Windows
  installation encountered an unexpected error. Error code: 0x80070103 - 0x40031"
  on current media (WinPE 26100): Setup aborts on answer-file driver paths that
  do not exist, and the answer file guessed 24 of them on drives D: to J:. The
  virtio disk driver now rides on the Autounattend floppy (A:) and is loaded from
  there only. The answer file also selects an edition (generic Pro key, no
  activation), so multi-edition ISOs no longer stop at the product key screen.
- A Windows Setup error dialog now stops `vm create` within a minute, with the
  error text in the message and a `<vm>_setup-error.png` screenshot next to the
  disk, instead of waiting out the 90-minute install timeout.
- The readiness check of a new Windows VM failed at its first step ("provision
  step 1/2 'reboot' did not complete: guest-exec transport error: timed out"):
  the first `guest-exec` after boot took 13 s to answer, past the 10 s every agent
  call allowed (launches and status polls now get 60 s), and the step would then
  have run `/bin/bash` in the Windows guest (it runs PowerShell there now).
- x86_64 Windows VMs (`windows10`, `windows11`) could not mount ADARE's shares on
  a Linux host: `virtiofs.exe` needs WinFsp, which the answer files never
  installed, so `C:\adare` stayed empty and the agent could not start. WinFsp 2.1
  is installed at first logon now (`--setup base` and up).
- Windows answer files installed the *latest* Miniforge, and 26.9.4-0
  (2026-10-22) ships a conda whose `create` fails on Windows ("Could not find
  'share/conda-launchers/cli-64.exe'"), leaving an empty `pyadare` env. Miniforge
  is pinned to 26.7.2-0.
- The agent installer took a missing `pyadare` conda env on Windows for an
  existing one (`if ($?)` after `| Out-Null` is always true), so its recovery
  `conda create` never ran.
- `vm create` now checks x86_64 Windows guests for WinFsp and, with `--setup
  full`, a working `pyadare` Python before calling the VM ready.
- `ubuntu2604` installs the genuine desktop edition from the 26.04.1 desktop ISO
  by playbook, like `ubuntu2404`, including 26.04's new "Encryption and file
  system" screen. It used the server ISO with a desktop source the server ISO
  does not carry, so it could not install at all.
- Ubuntu 26.04 guests opened a "Welcome to Ubuntu 26.04" wizard over the desktop
  on every login: its per-release welcome (a systemd user unit, not autostart)
  runs once the initial-setup done marker exists, which provisioning writes. The
  release's own stamp is now written too.
- An unattended Linux install whose installer failed (subiquity's "An error
  occurred. Press enter to start a shell", a failed curtin step, ...) is now
  stopped within seconds instead of waiting out the 150-minute install timeout.
  For a crashed subiquity, ADARE opens the installer's rescue shell over the
  serial console and puts its traceback into the install log and the error.
- The Ubuntu rolling autoinstall template (`ubuntu2510`, `ubuntu2604arm64`)
  asked for the `ubuntu-desktop-minimal` source, which server ISOs do not carry,
  so subiquity crashed before installing anything. The desktop now comes from
  the package list, as in the LTS template.
- `adare vm test` on Linux guests hung at "Starting AdareVM server" until the
  300 s guest-command timeout and then failed: the backgrounded launch kept
  the guest agent's output pipe open for as long as adarevm ran.
- Bullet lists and examples in command help (`experiment run`, `env load`,
  `vm test`, ...) were re-wrapped into one run-on paragraph; they now keep
  their line breaks. `adare experiment list` no longer claims to list "in an
  environment" (it lists every project's experiments).
- Playbook VM creation printed its step labels (`[install 25]`, `[provision]`)
  as Rich markup, so they never appeared in the terminal.
- Playbook VM creation piped QEMU's output without reading it; a chatty QEMU
  could fill the pipe and stall.
- Deleting a VM in the web UI only dropped its database row: instances, QEMU
  templates and the managed disk were left behind, and environments using it
  silently lost their VM. It now tears the VM down fully and refuses a VM that
  environments use.
- Deleting a VM with force (`env remove --force`, web UI) deleted a running
  instance's row but left its domain running; force now reaches the instance cleanup.
- Concurrent QEMU runs could delete each other's run files: the crashed-run
  sweep at run start now scans files before reading instance rows.
- `experiment run` without `-e` failed with "multiple environments" after
  `env load --force`; an experiment now keeps one version per environment name.
- A failed or concurrent `env load` removes the VM row, disk copy and managed
  file it created, and reports a concurrent load of the same name clearly.
- A failed `env load --force` no longer deletes a VM it only updated in place.
- Run setup reads an environment's version, file and VM in one query, so a
  concurrent reload cannot pair one version's file with another's ULID.
- A managed copy such as `win_20261023_<hash>.yml` reloads under its registered
  name instead of losing the date suffix.
- `env load` reports the environment's real hypervisor instead of `virtualbox`.
- File-transfer factory tests no longer depend on the host having virtiofsd.
- `adare vm test` let the guest (as root) build its uv venv and bytecode inside
  the shared `~/.adare/adare`, leaving root-owned files there that made the next
  `make install` fail with `PermissionError`. The guest now keeps its venv in
  the guest (`UV_PROJECT_ENVIRONMENT`), writes no bytecode and leaves `uv.lock`
  alone (`--frozen`). The installer stops with the `chown` command to run instead
  of a traceback, and no longer continues after the appdata copy failed.
- `adare vm snapshot remove` always failed (it went through a deprecated
  template-level path that refused every deletion).
- Concurrent QEMU runs of one environment deleted each other's overlays (the
  orphan sweep matched every overlay of the template), and `--no-copy` overlays
  were written next to the user's disk.
- Multi-machine runs on one VM collided on the instance name and released only
  the last machine's instance.
- `adare vm test` used a fixed host port (19000), so two tests collided; it now
  also works for non-qcow2 disks and removes its config/varstore afterwards.
- `adare vm test` on a QEMU VM crashed with `'NoneType' object has no attribute
  'path'` when the first boot missed the guest-agent budget: the boot retry re-ran
  the experiment file-transfer setup, which needs a run directory the test lacks.
- Running an experiment without `-e` looked up an environment named after the
  managed file (`<name>_<hash8>`) and failed.
- Environment installation / platform lookups queried a non-existent `ulid` column.
- Python API `vm.load` failed with a TypeError (missing `project_path`).
- Every dev-session web route failed: async handlers called services that run
  their own `asyncio.run`; `/api/sessions/start` also passed a removed field and
  several routes read `result.value`/`is_success()`, which `Result` lacks.
- A nested `with` on a database API committed and closed the session its outer
  block was still using.
- The QEMU shared-folder guard raised `TypeError` instead of
  `UnsupportedFeatureException`.
- Experiments started from chat (`experiment_run` tool) were cancelled
  immediately; they now run to completion.
- Changed `adarevm`/`adarelib` code never reached guests: the skip check compared
  unbumped static versions (and adarelib against adarevm's version).
- A testfunction collection needing a newer adarelib API suggested `uv add
  adarelib.…`; it now says the guest's adarelib is outdated.
- `except A or B` handlers that silently caught only `A` (8 places).
- `NameError` on error paths in the event listener and VirtualBox networking.
- Database APIs resolving their path at import time.
- Late-bound loop variables in the chunked file-pull progress callback.
- Unclosed file handles in network-drive setup and web-app upload.
- `adare vm create` playbook installs counted a crash dialog or a hung progress
  bar as "installed" (any screen still for 45 s), and Kubuntu logins were never
  checked. A new `wait_text` step (`gone`, `fail_on`, `timeout`) now waits for
  the installer's "done" screen and fails fast on crash/error texts; the login
  check fails unless the greeter goes away without an error. All seven playbook
  profiles use it. The live session is powered off via ACPI before the hard
  stop, `wait_stable` takes `required: true`, and a failing step saves
  `<phase>_<nn>_FAILED.png`.
- Playbook installs went silent for up to an hour while waiting. Every step now
  prints a timestamp and its duration, and waits print a progress line each
  minute (elapsed / timeout, current on-screen text) plus a "may be stuck"
  warning once the screen has not changed for 10 minutes.

### Security
- The guest agent no longer accepts unauthenticated connections (per-run token);
  the token is redacted from host logs.
- VM port forwards (QEMU hostfwd, VirtualBox NAT) listened on all interfaces,
  exposing the guest agent to the LAN; they now bind to 127.0.0.1.
- The guest agent no longer logs command environment values.
- Bumped 28 locked dependencies with published advisories (aiohttp, starlette,
  urllib3, cryptography, pyjwt, python-multipart, mcp, fastmcp, …).
- `linux.log_entry_exists` (guest and host-mode QGA paths) passed `log_file` and
  `pattern` to the shell unquoted, allowing command injection from a playbook.

### Removed
- The unused `Event.parent_event` / `child_events` ORM relationship and the
  broken `ActionEvent.display_level` property (it called a `query` attribute the
  models do not have).
- `adare server start`, which failed with `ModuleNotFoundError` and duplicated
  `adare web start` (now `adare ui start`), and the empty `adare help` group.
- Duplicate libvirt domain teardown: the run path, its signal handler and
  `vm test` share `run_resources.destroy_run_domain`; dead QEMU branches in the
  VirtualBox instance preparation, the broken `ensure_vm_available_for_environment`
  and unused environment queries (`get_environment_by_hash`, summaries).
- Dead VM/environment code: template-level snapshot shims, always-true VM
  "verification", the duplicated VirtualBox re-import in the run path (it now
  re-allocates through the normal path), unused environment API helpers and the
  second `parse_environment_file`.
- Broken console scripts `adareexp` and `mcp_gui` (their modules no longer exist).
- Stale CV server scripts (`reproduce_ocr.py`, a pipeline test for an API that
  no longer exists, sample images).
- Dead code: `networkdrive`, `helperfunctions.subprocess`, `webappaccess.request`,
  the experiment backup model, adarevm templating, legacy `setup.py` files and the
  root `requirements.txt`.
