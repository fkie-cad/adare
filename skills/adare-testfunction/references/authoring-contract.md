# Test-function authoring contract — reference

Source of truth: `adarelib/adarelib/testset/api.py` (the `@testfunction` decorator +
`_validate_signature`) and `adarelib/adarelib/testset/basictest.py`
(`HostModeCategory`). The example collections under `adare/appdata/testfunctions/`
(standard, json, csv, xml, sqlite, excel, jsonl) are the canonical models to copy.

## The decorator

```python
@testfunction(
    name: str,                     # unique test name WITHIN the collection
    description: str,
    category: HostModeCategory = HostModeCategory.AGENT_ONLY,
    execute_on_host: bool = False,
)
def my_test(ctx, dst: str, ...): ...
```

The decorator turns the function into a `BasicTest` subclass at import time and
registers it for discovery. It also runs `_validate_signature` — so contract
violations raise **at load time** with an actionable message, not silently at run
time.

## Signature rules (enforced)

1. **First parameter must be `ctx`** — a `TestContext`. Not `self`, not anything
   else. `def my_test(ctx, ...)`.
2. **Every parameter after `ctx` must be type-annotated.** An unannotated param would
   default to `str` and mis-structure playbook values, so it's rejected: annotate
   each (`dst: str`, `expected: int`, `regex_match: bool = False`). Annotations drive
   cattrs validation of the playbook's `parameter:` block. Defaults are allowed and
   become the parameter's default.
3. **`name=` unique per collection**; **filename must equal the directory name**
   (`testfunctions/json/json.py`). Duplicate testnames and filename≠dirname are both
   validate errors.

## `HostModeCategory` — how a test executes in host-mode (no in-guest agent)

| Category | Meaning |
| --- | --- |
| `FILE_BASED` | Pull the target file via QGA, rewrite `dst`, run `test()` on the host. |
| `FILE_CONTENT` | Same as FILE_BASED, for files whose content is read (JSON, CSV, XML, SQLite, INI, images, ...). |
| `QGA_PROBE` | Run a probe command on the guest via QGA, build the `TestResult` on the host. |
| `HOST_NATIVE` | Already runs on the host (e.g. visual tests). |
| `AGENT_ONLY` | Requires the in-guest agent; **not** supported in host mode (the default). |

Only `FILE_BASED` / `FILE_CONTENT` tests are exercisable with `adare test dry-run`
(they operate on a local sample file as `dst`). Author file-outcome checks as one of
those two so you can dry-run them without a VM.

## `TestContext` (`ctx`) helpers

- **Assertions:** `ctx.fail_if(condition, message)` → test *failed*;
  `ctx.error_if(condition, message)` → test *errored* (precondition/setup). Both
  raise; the harness converts them to the right `TestResult`.
- **File resolution:** `ctx.resolve_globfilepath(globpath, match_mode="single"|"any",
  return_list=False)` → `(path_or_paths, status)`. The standard way to locate the
  pulled artifact; check `status` and fail/error on it.
- **Placeholders / variables:** `ctx.resolve_variables(text)`,
  `ctx.has_placeholders(text)`, `ctx.get_placeholders(text)`,
  `ctx.compare_with_placeholder(name, actual)`, `ctx.get_placeholder_metadata(name)`,
  `ctx.has_tolerance_metadata(name)`, `ctx.variable_metadata` — for tests whose
  expected values come from playbook variables/placeholders (with optional tolerance).
- **Host context** (host-mode only): `ctx.host` exposes `screenshot`, `cv`, `vm_file`
  for visual/host-native tests.

## Return values

Return one of:

- `None` → success with no details.
- a `str` → success, that string as the detail.
- a `list` → success, those strings as details.
- a `TestResult` directly (`TestResult.success([...])`, `.failed([...])`,
  `.error([...])`, `.execution_error(exc, msg)`) for full control.

Unhandled exceptions are caught by the harness and turned into an execution error, so
prefer catching *specific* exceptions (e.g. `FileNotFoundError`, `json.JSONDecodeError`,
`OSError`) and returning a precise result — matches the project's "no generic
`except Exception`" rule and gives better forensic messages.

## Failed or error?

- **failed**: the test read the evidence and the condition does not hold.
- **error**: the test could not read the evidence: `dst` missing, a glob matching no file
  or several, unreadable (permissions, I/O) or unparseable content (invalid JSON/CSV/XML,
  corrupt workbook/database), or invalid parameters (wrong type, empty list, both/neither
  of two options, unknown mode, invalid regex). Return `TestResult.error([...])` /
  `.execution_error(exc, msg)`, never `.failed`.

`expect_to_fail` inverts only success/failed; errors stay errors. A missing file reported
as *failed* makes a wrong path, a typo or a failed pull pass every negative test. Only a
test whose subject is existence (`standard.file_exists`, `file_does_not_exist`,
`dir_exists`) may pass or fail on a missing path.

## Shared helpers (adarelib, shipped to the guest with the agent)

- `adarelib.testset.structured`: complete `contains_key` / `value_matches` / `value_count`
  bodies for any format that loads into dicts and lists. Describe the format once with
  `StructuredFormat(label, load, errors)` and delegate (see the plist, yaml and toml
  collections). Also `compare_value`, `compare_count` (`equals`, `greater`, `less`,
  `greater_equal`, `less_equal`) and `count_parameter_errors` for your own count functions.
- `adarelib.testset.compare`: key paths (`a.b`, `*`, `[*]`, `[0]`, `['a.b']`).
- `adarelib.testset.content`: `read_bytes_capped`, `decode_text` (BOM / UTF-16 aware).

Prefer a count function (`expected_count`, `0` = absent) over a separate "absent" test.

Docstring examples use neutral made-up paths (`/home/user/data/app.db`), never a real
application's paths or table names; `test_neutral_docstrings.py` checks this.

## Minimal skeleton

```python
from pathlib import Path
from adarelib.testset.api import testfunction, TestContext
from adarelib.testset.basictest import HostModeCategory
from adarelib.event.event import TestResult

@testfunction(
    name='deleted_file_absent',
    description='fails if the named file still exists (asserts a deletion)',
    category=HostModeCategory.FILE_BASED,
)
def deleted_file_absent(ctx, dst: str):
    paths, status = ctx.resolve_globfilepath(dst, match_mode="any", return_list=True)
    existing = [p for p in (paths or []) if Path(p).is_file()]
    ctx.fail_if(bool(existing), f'{dst} still present: {existing}')
    return [f'{dst} absent — deletion confirmed']
```
