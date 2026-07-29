# Sessions, reset & checkpoints — reference

## Starting sessions

`adare dev start`:

| Flag | Meaning |
| --- | --- |
| `-e, --environment TEXT` | Environment name. **Required.** |
| `-p, --project TEXT` | Project name/path. |
| `--name TEXT` | Friendly session label; select later with `-s <name>`. |
| `--gui-mode / --test-mode [auto\|agent\|host]` | Execution modes (see `adare-experiment`). |
| `--vm-memory INTEGER` | RAM in MB (default 4096 Linux / 8192 Windows). |
| `--vm-cpus INTEGER` | CPU count (default 4). |
| `--shared-dir TEXT` | Shared dir as `HOST_PATH:VM_PATH`. |
| `--debug-screenshots` | Save screenshots for debugging. |
| `--reuse` | Attach to the most-recent running session for the project instead of booting a new VM. |
| `--watch` | Open the live screen (read-only) in the browser via VirtualSpice (needs `adare web start`). |

`-s/--session` on every other `dev` command is **auto-detected when only one session
runs**; pass it (id or `--name`) when several are up.

## Stop / resume / clean

```sh
adare dev stop [-s <id>]        # stop VM, keep resources for restart
adare dev stop -s <id> --rm     # stop + remove all resources (== dev remove)
adare dev stop --all [-y]       # stop every running session (-y skips confirm)
adare dev resume [<id>]         # resume a stopped session (most-recent if omitted)
adare dev cleanup [-p project]  # clear stale sessions
adare dev list [-p project]     # active sessions
adare dev state [-s <id>]       # variables, stats, snapshots
```

## Reset: soft vs hard

| | `dev reset soft` | `dev reset hard` |
| --- | --- | --- |
| Scope | ADARE **variables only** | **Full VM restore** |
| Speed | <1 second | 10–30 seconds |
| Use when | Re-trying a playbook that leaves no guest state | Guest filesystem/UI drifted; need base state back |

## Checkpoints

```sh
adare dev checkpoint create <name> -s <id> [-d "description"]
adare dev checkpoint list    -s <id>
adare dev checkpoint restore <name> -s <id>
adare dev checkpoint remove  <name> -s <id>
```

Live snapshots. Create one **before** any risky operation (software install,
destructive click sequence) and `restore` instead of rebuilding the session.

**Caveat (aarch64/UEFI):** on some Windows-ARM64 / UEFI environments live snapshots
are unreliable — `--restore`/checkpoint restore may fail. There, the reliable
clean-reset path is `adare exp run` on a fresh overlay (each run resets to the base
snapshot). See the win11-arm gotchas reference in `adare-vm-build`.

## Batch replay

```sh
adare dev playbook-batch -s <id> experiments/*/playbook.yml [--checkpoint-name base] [--timeout N]
```

Creates a base checkpoint, runs each playbook, and restores to the checkpoint after
each — so playbooks don't contaminate one another. Accepts explicit paths or globs.
