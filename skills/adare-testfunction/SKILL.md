---
name: adare-testfunction
description: "Find the right forensic test-function (assertion) for a goal, or author/validate a new one, for a playbook's `tests:` block (e.g. a file exists, a registry value matches, a deleted file is gone, an icon is visible). Trigger when the user or a task needs to pick, look up, write, scaffold, validate, dry-run or install a testfunction, or asks 'which test should I use to check X'. Not this → editing a playbook's UI actions (adare-playbook); running the experiment that exercises the test (adare-experiment)."
---

# ADARE test-functions

A **test-function** is a decorated Python function ADARE calls after a playbook runs
to assert a forensic outcome — "does this file exist", "does this JSON key match this
value", "is this deleted file actually gone". Test-functions live in **collections**
(`testfunctions/<collection>/<collection>.py`) and are referenced from a playbook's
`tests:` block by `<collection>.<function>`.

**Find before you write**: the bundled catalog (about 80 functions in 17 collections) covers
most assertions. Writing a new one is the authoring loop: **scaffold → author (per the
contract) → validate → dry-run → install → integrate**. Pure `adare` CLI + Bash + file editing —
no VM needed until end-to-end integration. Auto-loads as a skill in **Claude Code**;
portable to any agent with a shell (on **OpenCode** see `docsrc/mcp-clients.md`). The
authoring contract and the validate/dry-run detail live in `references/`.

## 0. Find an existing test-function: go one layer deeper only when needed

Every function has a **contract**: what it asserts, which formats and shared features it
supports, which it explicitly does **not**, goals it is **not for** (and what to use
instead), when it passes / fails / errors, its limits and examples that run in ADARE's test
suite. Read it in layers, stopping as soon as the choice is clear:

| Layer | Ask | Command (offline: file) |
|---|---|---|
| 1. Candidates | which functions fit the goal? | `adare test search "<goal>"` (`references/catalog/index.md`) |
| 2. Contract | parameters, allowed values, outcomes, limits, examples | `adare test info <name>` (`references/catalog/<collection>.md`) |
| 3. Shared syntax | archives in `dst`, globs, `!re`, `!timestamp`, ordering, key paths, offsets | `adare test feature [<id>]` (`references/features.md`) |
| 4. Proof | does my test do what I think on a sample? | `adare exp playbook validate`, `adare test dry-run` |

```sh
adare test search "the deleted file is gone"                    # 5 short cards + an example
adare test search "value gone" --asserts absent --reads sqlite  # filter by facet
adare test search "x" --feature archive_dst                     # only functions supporting a feature
adare test info sqlite.row_count                                # the full contract (Markdown)
adare test feature                                              # all shared features + known gaps
adare --format json test search "registry value" --os windows   # machine-readable cards
```

Filters (vocabulary in `references/features.md` and `adare test feature`):
`--asserts` exists | absent | value | count | order | compare | content | metadata | state | ui;
`--reads` file | directory | text | binary | json | jsonl | csv | xml | excel | sqlite | ini | plist |
yaml | toml | image | registry | system | screen; `--feature` archive_dst | glob_dst | regex_tag |
placeholder | timestamp_tag | ordered_comparison | count_comparison | key_path | wildcard_mode |
encoding | offset_expression | sqlite_view | negative.

How to read a search answer:
- **`match: weak`** means no function clearly covers the goal. Read `known_gaps` (goals no
  bundled function does, with what to do instead) and do not force a near miss: narrow the
  filters, or write a collection (sections 1–7).
- **`redirected`** / **`not for`**: a function said "not for this goal, use X". Follow it.
- **`does_not_support`**: the function refuses that feature (e.g. a `!re` tag as `pattern`);
  the reason says what to write instead. A feature in neither list is untested there: check
  with `adare test dry-run` before relying on it.
- **`required`**: fill every one. Use the exact dotnotation and parameter names from `test
  info`; never guess. An unknown name errors with close matches, and `adare exp playbook
  validate` warns about unknown parameters and values outside a parameter's allowed list.

Rules that hold for every function (the contracts give the per-function detail):
- **FAILED** means the evidence was read and the claim does not hold. A missing `dst`, a glob
  matching none or several, unparseable content or a bad parameter is **ERROR**, never a pass,
  also with `expect_to_fail` (it inverts only SUCCESS/FAILED).
- Prefer the explicit inverse over negating: `standard.file_does_not_exist`, not `file_exists`
  expected to fail. Absence of content is a count function with `expected_count: 0`. Both are
  negative tests: INCONCLUSIVE without proof of the act; pair them with a control test
  (`controls:`, see adare-playbook).
- `visual.*` tests run on the host against the VM screen: UI state, not files.
- Renamed functions and parameters are rejected with "X was renamed to Y".

Only if nothing fits, write a new collection (sections 1–7), with a `contract.yaml`
(`references/authoring-contract.md`).

## 1. Scaffold

```sh
adare test create <name>                 # new collection under testfunctions/<name>/
```

`test` aliases: `tf`, `testfunction`. Creates the collection skeleton — a directory
whose `.py` filename **must equal** the directory name (a contract rule).

## 2. Author

Edit `testfunctions/<name>/<name>.py`. Each test is a plain function decorated with
`@testfunction(...)`:

```python
from adarelib.testset.api import testfunction, TestContext
from adarelib.testset.basictest import HostModeCategory
from adarelib.event.event import TestResult

@testfunction(
    name='file_exists',
    description='tests if file(s) exist',
    category=HostModeCategory.FILE_BASED,
)
def file_exists(ctx, dst: str, match_mode: str = "any"):
    paths, status = ctx.resolve_globfilepath(dst, match_mode=match_mode, return_list=True)
    ctx.error_if(status, f'path {dst} cannot be resolved ({status})')
    files = [p for p in paths if Path(p).is_file()]
    ctx.fail_if(not files, f'no files match {dst}')
    return [f'{len(files)} file(s) found']
```

**Non-negotiable contract rules** (enforced at load time — see
`references/authoring-contract.md` for the full list and the `category` types):

- First parameter **must** be `ctx` (a `TestContext`).
- **Every** other parameter must have a type annotation (drives cattrs validation of
  the playbook's `parameter:` block). Give defaults where sensible.
- `name=` must be **unique within the collection**; the file must be named after its
  directory.
- Assert with `ctx.fail_if(cond, msg)` (test failed) / `ctx.error_if(cond, msg)`
  (precondition/setup error); return a str/list (success) or a `TestResult`.
- **Failed means the evidence was read and the condition does not hold.** A missing
  `dst`, a glob matching no file or several, unparseable content or invalid parameters is an *error*, never
  a failure: `expect_to_fail` inverts only success/failed, so a failure there would let a
  wrong path pass a negative test. Only existence tests (`file_exists`,
  `file_does_not_exist`) may fail on a missing path.
- **A test whose pass means "something is absent"** (cleared, deleted, never written)
  should declare `@testfunction(..., negative=True)` (a count function needs no flag:
  `expected_count: 0` is recognised as negative). The host then reports an
  unproven pass (an earlier GUI action skipped or without visible effect) as
  INCONCLUSIVE instead of SUCCESS, so every playbook that uses it gets that for
  free. Names ending in `_does_not_exist` are recognised without the flag. Tell
  playbook authors to pair it with a control test (`controls:`), see the
  adare-playbook skill. A missing file/key must be reported by the test itself, not
  inferred from a read error: only a real "not found" may pass.

## 3. Validate (offline, no VM)

```sh
adare test validate <path>               # collection dir or .py file
```

Static contract check: filename≠dirname, missing `ctx`, unannotated params,
duplicate testnames, import/syntax errors, missing dependencies — each with a fix
hint. **Never install a collection that doesn't validate.**

## 4. Dry-run (against a local sample, no VM)

```sh
adare test dry-run <collection>.<function> -P key=value -f <sample-file>
```

Executes **one** `FILE_BASED`/`FILE_CONTENT` test against a local sample used as the
`dst` parameter — the fast way to prove the logic without booting a VM. `-P` is
repeatable for the function's other parameters. Details in
`references/validate-dryrun.md`.

## 5. Install

```sh
adare test load <name> [--force]         # register a collection (name/path)
adare test sync                          # sync all appdata testfunctions (new/changed/unchanged)
```

`test load` skips testfunctions currently used in experiment runs by default;
`--force` overwrites them **and deletes the associated runs** — use deliberately.

## 6. Inspect

```sh
adare test list [--collection standard] [--os windows]   # every testfunction + parameters
adare test info <collection>.<function>                  # detail for one testfunction
adare test versions <collection>[.<function>]            # version history
adare test remove <name>                                 # remove a collection file
```

## 7. Integrate

Reference the installed test from a playbook's `tests:` block as
`<collection>.<function>` with a `parameter:` block matching the function's annotated
signature, then run it at the right moment with a `- test: <name>` action:

```yaml
tests:
  - name: report_deleted
    description: 'The report must be gone after the delete action'
    function: standard.file_does_not_exist
    parameter:
      dst: '{{ report_file }}'
actions:
  # … GUI actions that delete the file …
  - test: report_deleted
```

Write a docstring with a summary, a `Use for:` paragraph and an `Args:` section for every
new function, and a `contract.yaml` next to the collection (`references/authoring-contract.md`):
the catalog, `test search/info` and the agent tools show both, `test validate` warns about gaps
and inconsistencies. Docstring and contract edits don't bump the function's version. Wiring the `tests:` block into the playbook itself is `adare-playbook`;
verify the whole thing end-to-end with a real `adare exp run` (`adare-experiment`) —
the dry-run only proves the function in isolation.

## Guardrails

- **Validate before install.** `test validate` is offline and fast; a collection
  that fails it will fail at load/run.
- **`test load --force` deletes runs** tied to the testfunction — confirm first.
- **Contract is enforced at load time**, not run time — a missing annotation or a
  bad `ctx` signature raises loudly on load. Fix at authoring, don't work around.
- **No VM needed** for scaffold/author/validate/dry-run; only end-to-end integration
  (`exp run`) touches a VM (and is serialized — one live VM at a time).
- **Forensic integrity:** test-functions read guest-pulled artifacts on the host;
  keep them side-effect-free (no writes into the guest, no remnants).
