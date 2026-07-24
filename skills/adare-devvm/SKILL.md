---
name: adare-devvm
description: "Drive or debug a running ADARE VM interactively — start/resume/stop dev sessions, fire single actions, replay playbooks, drive toward a goal with the vision agent, hand-author playbooks, reset/checkpoint the VM, and debug CV/OCR grounding. Trigger for hands-on 'click through the VM', 'check what's on screen', 'checkpoint before I try this', 'why didn't it find that icon'. Not this → productized run/inspect/share of an experiment (adare-experiment); offline editing of a playbook.yml (adare-playbook); building a new base VM or environment (adare-vm-build)."
---

# ADARE dev-VM driving

`adare dev` is the interactive layer: it boots **one** VM as a *session* you drive
step by step — fire actions, replay playbooks, checkpoint and reset, let the vision
agent drive toward a goal, or hand-author a playbook from your own steps. This is
the exploration/debugging counterpart to the productized `adare exp run`
(`adare-experiment`).

Pure `adare` CLI + Bash. The one genuinely non-CLI capability — stateful,
step-by-step live-VM hands for an external harness — is the `dev mcp` server,
covered as an appendix. Auto-loads as a skill in **Claude Code**; portable to any
agent with a shell (on **OpenCode** see `docs/mcp-clients.md` for skill setup).

Keep SKILL.md's common path in view; pull `references/*.md` for full flag matrices
and agent/grounding depth.

## Prerequisites (vision features only)

The vision-driven parts — `dev agent`, `dev author-ai` — need a configured VLM
endpoint (`ADARE_VLLM_*`, e.g. Ollama Cloud). Confirm it before driving:

```sh
adare vlm show                 # resolved VLM config + where each value comes from
adare vlm use [<profile>]      # switch/create a profile (interactive if no arg)
adare vm gui-doctor            # is the endpoint reachable? which coord space?
```

`dev action`, `dev playbook`, checkpoints, and `dev author` (human-step authoring)
need **no** VLM.

## 1. Session lifecycle

```sh
adare dev start -e <env>                 # boot a VM session; prints the session id
adare dev start -e <env> --reuse         # attach to the most-recent running session instead
adare dev start -e <env> --watch         # also open the live screen in the browser
adare dev list                           # active sessions
adare dev state [-s <id>]                # variables, stats, snapshots
adare dev resume [<id>]                  # resume a stopped session (most-recent if omitted)
adare dev stop [-s <id>]                 # stop, keep resources for restart
adare dev stop -s <id> --rm              # stop + remove all resources (alias: dev remove)
adare dev stop --all [-y]                # stop every running session
adare dev cleanup                        # clear stale sessions
```

`-s/--session` is auto-detected when only one session runs; pass it explicitly
otherwise. `--name` on `start` gives a session a friendly label you can select with
`-s <name>`.

## 2. Drive

```sh
adare dev action -s <id> -y '<inline-yaml>'      # one action (also: -i file, --stdin)
adare dev playbook -s <id> -f <file>              # replay a whole playbook
adare dev playbook -s <id> -f <file> --restore    # reset to initial checkpoint first
adare dev playbook -s <id> -f <file> --indices 1-3,5,S-2,7-E   # only selected actions
adare dev playbook-batch -s <id> <glob…>          # many playbooks, checkpoint-restored between each
```

`--indices` selects action ranges (`S`=start, `E`=end) — the way to replay just the
step you're debugging. `playbook-batch` checkpoints once, then restores to it after
each playbook so runs don't contaminate each other.

**Goal-driven (vision agent):**

```sh
adare dev agent -s <id> --goal "open Files and go to Documents"
adare dev agent -s <id> --goal "…" -o out.play.yaml           # also record a replayable playbook
adare dev agent -e <env> --goal "…" --as-experiment demo6     # boot fresh, drive, scaffold an experiment
```

`dev agent` observes the screen and clicks/types live toward a natural-language
goal. With `-o`/`--as-experiment` it records a playbook; `--verify` (default) then
replays it to validate. Full flags (`--plan`, `--ground`, `--step`, `--video`,
`--keep`) in `references/agent-and-authoring.md`. **The live agent is an
authoring/exploration aid, not a production runner** — it's slow and
non-deterministic; the authored/recorded playbook it produces is what you run.

**Hand-authoring** (no VLM planner) is covered by `adare-playbook`:
`adare dev author -s <id> [--script-file … | --interactive]` and the
vision-authored `adare dev author-ai -s <id> --goal "…" [--replay]`.

## 3. Reset & checkpoint

```sh
adare dev reset soft -s <id>                 # variables only, <1s
adare dev reset hard -s <id>                 # full VM restore, 10–30s
adare dev checkpoint create <name> -s <id> [-d "desc"]
adare dev checkpoint list -s <id>
adare dev checkpoint restore <name> -s <id>
adare dev checkpoint remove <name> -s <id>
```

- **soft** — resets ADARE *variables* only, sub-second. Use between playbook tries
  that don't change guest state.
- **hard** — full VM restore (10–30s). Use when the guest filesystem/UI drifted and
  you need the base state back.
- **Checkpoint before any risky op** (installs, destructive clicks) so you can
  `restore` instead of rebuilding the session. Note: on some aarch64/UEFI envs live
  snapshots are unreliable — see the win11-arm notes in `adare-vm-build`; there
  `exp run` on a fresh overlay is the reliable clean-reset path.

## 4. Support / debugging

```sh
adare dev cv start -s <id> [--debug -o <dir>]    # (re)start the CV server, optionally logging
adare dev cv stop -s <id>
adare dev grounding-pull                          # pre-download LocateAnything weights (~7.3 GB)
adare dev update-testfunctions -s <id>            # reload test functions into the running VM
adare vm watch <name>                             # live screen in the browser (view-only; --interactive)
```

CV/OCR image debugging (works off screenshot PNGs, no session needed) —
`cv test-icon`, `cv test-text`, `cv get-all-text` — is in `references/cv-debugging.md`.

## Guardrails

- **One live VM at a time.** `dev start`, `action`, `playbook`, `agent`, `author*`
  are serialized — never overlap two VM-driving operations. Session-state reads
  (`dev list`, `dev state`) are safe anytime.
- **Checkpoint before risky ops**; prefer `restore` over rebuilding a session.
- **Keep guest state minimal** — do not leave stray files or logs in the VM;
  forensic integrity depends on a clean guest (see the no-VM-remnants memory).
- **Stop the sessions you start** (`dev stop`, or `--rm` to reclaim resources).
- The vision agent is **non-deterministic** — treat its output as a draft playbook
  to validate/replay, not a finished run.

## Appendix: live-VM MCP — `adare dev mcp`

The one thing the plain CLI can't do: stateful, step-by-step click/type/screenshot
on **one running VM** for an external harness (Claude Code / OpenCode / any MCP
client), plus record → save → replay from your own actions. It's stateful (QMP
bound to a single event loop), so it's a server, not a stateless CLI call.

```sh
adare dev start -e <env>                 # note the session id
adare dev mcp -s <id> --port 13110
# Claude Code:
claude mcp add --transport http adare-gui http://127.0.0.1:13110/mcp
```

OpenCode: a `"type": "remote"` entry pointing at `http://127.0.0.1:13110/mcp`. See
`docs/mcp-clients.md` for the full client setup.
