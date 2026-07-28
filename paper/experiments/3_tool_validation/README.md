# Case study 5.3 — Tool Validation of PECmd

> "We executed a single program (regedit) ten times and, after each execution, invoked PECmd
> to export its parsed results for the Prefetch directory. We then asserted two deterministic
> expectations at every step: first, that the reported run count increased in lockstep with
> the iteration number, and second, that the last-run timestamp corresponded to the recorded
> execution time (within a small tolerance)."
> — ADARE paper, §5.3

One experiment, `pecmd/`, on `win11arm64-fresh`. It is the reference shape for State
Transition Testing in ADARE: the export and both assertions live *inside* the loop, so all
ten transitions are checked rather than only the end state.

## Which assertion encodes which claim

| Paper claim | Test | Where |
|---|---|---|
| A clean starting state | `check_regedit_pf_does_not_exists` | before the loop |
| Windows created a Prefetch file for regedit | `check_regedit_pf_exists` | every iteration |
| PECmd produced an export | `check_pecmd_output_file_exists` | every iteration |
| **Run count increases in lockstep with the iteration** | `check_prefetch_run_count` | every iteration |
| **Last-run timestamp matches the recorded execution time (±5 s)** | `check_prefetch_last_run` | every iteration |

## Verification status

**First execution against a live VM: 2026-07-28** (aarch64, QEMU/HVF on macOS).

| What ran | Environment | Result | Run ID |
|---|---|---|---|
| `pecmd`, loop shortened to 2 iterations | `win11arm64-fresh` | **green — all per-iteration tests pass on both transitions** | `01KYMG6V2KDT320B5R16ERWDE8` |

The 2-iteration run is the mechanism check: it exercises the pre-launch marker, the flush
wait, the staged parser, and both per-iteration assertions on transition 1 *and* on
transition 2 — where the RunCount must advance and the previous iteration's `.pf` must not be
mistaken for this one's. The pulled export reports
`RunCount=2, LastRun=2026-07-28 12:16:35, Hash=DAB4D60B`. The full 10-iteration run is the
same loop body ten times.

## Two failures the first run exposed, and their fixes

Run `01KYJCP6FBC3GBTMS9MRR0AF9V` failed at `check_regedit_pf_exists` in iteration 1 and never
reached PECmd. Both causes were measured in-guest; both fixes are in the playbook with the
evidence written next to them.

### 1. `PECmd.exe` cannot be executed from the shared-tools mount

The mount is a symlink to a QEMU/Samba share (`C:\adare\project_shared` →
`\\10.0.2.4\qemu\project_shared`) whose files carry read-only ACLs (`Everyone:(R)`, no
`(X)`), so `CreateProcess` returns ERROR_ACCESS_DENIED:

```
Program 'PECmd.exe' failed to run: Access is denied
```

No process is created, hence no output and no exit code. Reading from the share is fine; the
same bytes copied to a local directory run and exit 0. The playbook now stages `PECmd.exe`
to a local disk and removes it again at the end of the run. `5_cross_tool_validation`'s
LECmd playbook needed the identical fix — **this applies to every Windows tool-validation
playbook, not just these two.**

### 2. `idle: 10` after the launch was a coin flip, not a wait

Prefetch is *not* disabled in this image and regedit *does* launch — both were the obvious
suspects and both are wrong:

```
SysMain: Status=Running StartType=Automatic (WMI State=Running, StartMode=Auto)
HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management\PrefetchParameters
  EnablePrefetcher=3   BootId=3   BaseTime=788044322
C:\Windows\Prefetch: 144 .pf files, newest written seconds before the check
Get-PhysicalDisk: QEMU NVMe Ctrl, MediaType=SSD, BusType=NVMe
```

and a screenshot taken 5 s after Enter shows the Registry Editor window open, with no UAC
prompt (the interactive Run box already carries "This task will be created with
administrative privileges").

The real cause is the prefetcher's trace window. It traces roughly the first 10 seconds of a
process's life and only then flushes:

```
regedit.exe                      started  2026-07-28T19:00:28.663Z  (pid 5420, session 1)
REGEDIT.EXE-DAB4D60B.pf          written  2026-07-28T19:00:38.876Z  (10888 bytes)
                                          -> 10.213 s after process start
```

A 10 s idle therefore expires at or inside the flush latency. A longer constant would only be
a slower race, so the idle was replaced by an explicit poll: the `.pf`'s mtime is recorded
*before* the launch and the wait returns as soon as it advances. Waiting for mere existence
would be wrong from iteration 2 onwards, where the previous iteration's file is already
present and PECmd would read a stale `RunCount`.

One thing the failing run's log does **not** settle: whether that iteration lost the flush
race or never launched regedit at all. The original playbook allowed only the 1 s default
pause between Win+R and typing, which is thin for the Run dialog to appear and take focus on
an emulated aarch64 guest, and a miss there is silent — the keystrokes land nowhere and the
failure surfaces later as a missing `.pf`. Both paths are now closed: the poll removes the
race, and an explicit 3 s settle after Win+R (the value the in-guest probe launched reliably
with) removes the focus gamble.

## Why the loop works even though regedit is single-instance

Worth knowing before trusting the RunCount column: iterations 2..10 do **not** leave a second
regedit process behind. The newly started `regedit.exe` activates the existing window and
exits immediately — after the second Win+R the only process present is still pid 5420 from
the first launch. Windows counts it as a run anyway:

```
before: RunCount=1  LastRun=2026-07-28 19:00:28
after:  RunCount=2  LastRun=2026-07-28 19:05:44   (pf mtime 19:05:44.300Z)
```

so the paper's lockstep claim holds. But because that second process exits at once its trace
closes at once, and its `.pf` flush is sub-second instead of ~10 s. The flush latency is
therefore *not* a constant across iterations — a second reason the wait has to be a poll.

## Tool provenance

PECmd is not vendored; it is provisioned into the environment's shared tools from
<https://ericzimmerman.github.io/>. The binary measured here reports version **2026.5.0**
(`FileVersion 2026.5.0.0`, informational version
`2026.5.0+bde430c69ba4d97fea8b71fdddb6df7849419c10`), is a 32-bit IL assembly
(`ILONLY | 32BITREQUIRED`) and runs under x86 emulation on Windows-on-ARM64 without trouble.
Unlike LECmd it **does** support `--jsonf`, and its JSON export is one object per line, which
is what `jsonl.line_matches` needs.

## Running it

```bash
adare experiment run pecmd --environment win11arm64-fresh --production
```

Prerequisite: `PECmd.exe` in the project's `shared/tools/`.
