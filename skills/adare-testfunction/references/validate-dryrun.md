# Validate & dry-run — reference

Two offline gates, both **VM-free** — run them before installing or integrating.

## `adare test validate <PATH>`

Static, offline contract check of a whole collection (`PATH` = collection directory
or a `.py` file). Reports every authoring-contract violation with a fix hint:

- filename ≠ directory name
- missing `ctx` first parameter
- unannotated parameters
- duplicate testnames within the collection
- import / syntax errors
- missing dependencies

No VM, no DB. This is the gate that catches the contract mistakes described in
`authoring-contract.md`. **Always validate before `test load`.**

```sh
adare test validate testfunctions/mycollection
adare test validate testfunctions/mycollection/mycollection.py
```

## `adare test dry-run <TARGET>`

Executes **one** testfunction against a **local sample file** (no VM). Scope:
`FILE_BASED` / `FILE_CONTENT` tests only — the sample file is passed as the `dst`
parameter.

```sh
adare test dry-run <collection>.<function> -f <sample-file> -P key=value [-P key2=value2]
```

| Flag | Meaning |
| --- | --- |
| `TARGET` | `<collection>.<function>` (e.g. `mycollection.file_contains_word`). |
| `-P, --param TEXT` | A function parameter as `key=value` (repeatable). |
| `-f, --file TEXT` | Local sample file used as the `dst` parameter. |
| `--path TEXT` | Collection dir/.py to load (else resolved from known locations). |

Example — check a JSON key/value function against a fixture:

```sh
adare test dry-run json.value_matches -f ./fixtures/report.json \
  -P key_path=user.profile.name -P expected_value=Alice
```

The values you pass with `-P` are validated against the function's **type
annotations** (that's why annotations are mandatory) — a mismatched type surfaces
here, cheaply, instead of at run time.

## Where dry-run stops

Dry-run proves a file-outcome test's *logic* on a fixture. It does **not** exercise:

- the QGA pull that fetches the real artifact from a guest,
- `QGA_PROBE` / `AGENT_ONLY` / `HOST_NATIVE` categories,
- the playbook `tests:` wiring or variable/placeholder resolution end-to-end.

For those, integrate the test into a playbook's `tests:` block (`adare-playbook`) and
run the experiment for real (`adare exp run`, `adare-experiment`) — that's the only
path that verifies pull + execute + assert together.
