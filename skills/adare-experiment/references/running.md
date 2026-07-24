# Running experiments — full reference

## `adare exp run <EXPERIMENT>`

Runs the experiment on one environment (`-e`) or **all** bound environments if `-e`
is omitted.

| Flag | Meaning |
| --- | --- |
| `-e, --environment PATH` | Environment name or path. Omit → run on every bound env. |
| `--production, --prod` | Real production run with full integrity checks. **Default is TEST mode** (fake runs, integrity checks skipped, modifications allowed). |
| `--debug-screenshots` | Save screenshots into the run directory for debugging. |
| `-s, --preserve-snapshot` | Create an experiment snapshot for preservation (default: only reset to the base snapshot). |
| `--no-runlog` | Don't save the adare log into `run/logs`. |
| `--vm-memory INTEGER` | VM RAM in MB (default 4096 Linux / 8192 Windows). |
| `--vm-cpus INTEGER` | VM CPU count (default 4). |
| `--gui-mode [auto\|agent\|host]` | GUI execution: `auto` (default), `agent` (WebSocket), `host` (QMP, QEMU only). |
| `--test-mode [auto\|agent\|host]` | Test execution: `auto` (default), `agent` (WebSocket), `host` (QGA, QEMU only). |
| `--diff / --no-diff` | Enable/disable filesystem diff (overrides the playbook's setting). |
| `--diff-mode [auto\|guest\|host]` | `auto` (smart), `guest` (VM-based), `host` (QEMU virt-diff). |
| `--project TEXT` | Project name. |

### TEST vs PRODUCTION semantics

- **TEST (default):** creates *fake* runs, **skips integrity checks**, allows
  modifications. This is the iterate/debug loop — cheap and forgiving. Fake runs are
  cleaned with `adare exp clean <exp>`.
- **PRODUCTION (`--prod`):** creates *real* runs with full forensic integrity
  validation. These are the runs you inspect for results and `web publish`.

Rule of thumb: debug in TEST until the playbook reaches its goal cleanly, then do a
single `--prod` run and publish that.

### Memory / boot notes

- Windows environments default to 8192 MB and can be flaky on cold boot; if a run
  dies with "VM did not become ready in time", bump `--vm-memory` and retry (see the
  `adare-vm-build` win11-arm-gotchas reference for the boot-flakiness detail).

## `adare exp diff <EXPERIMENT>`

Visual diff mode for **manual comparison between OS/software versions**.

- QEMU only (`-e` env must be QEMU-based); **required** flag.
- Executes visual actions only (click / keyboard / screenshot).
- **Skips** forensic actions (`save_timestamp`, `pull`, `tests`).
- No database records — ephemeral, no agent installation.

```sh
adare exp diff test_csv -e ubuntu24
adare exp diff firefox_test -e windows11 --project myproject
```

Use it to eyeball how the same playbook renders across, e.g., ubuntu24 vs windows11,
without polluting the run DB.
