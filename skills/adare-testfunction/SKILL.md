---
name: adare-testfunction
description: "Author or validate a forensic test-function that a playbook's `tests:` block calls to assert an experiment outcome (e.g. a file exists, a JSON key matches, a deleted file is gone). Trigger when the user wants to write/scaffold/validate/dry-run/install/inspect a testfunction. Not this → editing a playbook's UI actions or its `tests:` wiring (adare-playbook); running the experiment that exercises the test (adare-experiment)."
---

# ADARE test-functions

A **test-function** is a decorated Python function ADARE calls after a playbook runs
to assert a forensic outcome — "does this file exist", "does this JSON key match this
value", "is this deleted file actually gone". Test-functions live in **collections**
(`testfunctions/<collection>/<collection>.py`) and are referenced from a playbook's
`tests:` block by `<collection>.<function>`.

This skill is the authoring loop: **scaffold → author (per the contract) → validate
→ dry-run → install → inspect → integrate**. Pure `adare` CLI + Bash + file editing —
no VM needed until end-to-end integration. Auto-loads as a skill in **Claude Code**;
portable to any agent with a shell (on **OpenCode** see `docs/mcp-clients.md`). The
authoring contract and the validate/dry-run detail live in `references/`.

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
adare test list [--set standard]         # all testfunctions (filter by set)
adare test show [-n <file-name>]         # show with optional file filter
adare test info <collection>.<function>  # detail for one testfunction
adare test remove <name>                 # remove a collection file
```

## 7. Integrate

Reference the installed test from a playbook's `tests:` block as
`<collection>.<function>` with a `parameter:` block matching the function's annotated
signature. Wiring the `tests:` block into the playbook itself is `adare-playbook`;
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
