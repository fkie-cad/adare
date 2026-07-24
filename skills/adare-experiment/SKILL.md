---
name: adare-experiment
description: "Set up, run, inspect, and share ADARE experiments. Trigger when the user wants to create/clone an experiment, run it on an environment (test or prod), list/inspect runs, visually diff across OS versions, or publish/submit/download results. Not this → editing a playbook.yml's actions (adare-playbook); step-by-step live-VM driving/debugging (adare-devvm); building a base VM or environment (adare-vm-build)."
---

# ADARE experiments

ADARE runs reproducible GUI/forensic experiments inside VMs. An **experiment**
(`<project>/experiments/<name>/`) owns a `playbook.yml` (the UI actions + `tests`)
and is bound to one or more **environments** (a VM + its post-setup software). A
**run** is one execution of an experiment on an environment, identified by a ULID.

This is the productized lifecycle skill: **set up → run → inspect → share → clean**.
It's pure `adare` CLI + Bash — no MCP needed. (For *editing* the playbook, hand off
to `adare-playbook`; for *interactive* click-by-click VM work, `adare-devvm`.)

Auto-loads as a skill in **Claude Code**; the workflow is pure CLI + Bash, so it's
portable to any agent with a shell (on **OpenCode** load it via the `opencode-skills`
plugin or an `AGENTS.md` reference — see `docs/mcp-clients.md`). Keep SKILL.md's common
path in view; load `references/*.md` for full flag matrices and web-sharing depth.

## 1. Set up

```sh
adare project create <name>                    # optional: -d "description"
adare env load <env>                           # register an environment (name or path)
adare env list                                 # what environments exist
adare exp create <exp>                          # new skeleton experiment
adare exp example [name]                        # or start from the shipped example
adare exp clone <src> <target> [-e env ...]    # variation of an existing experiment
adare exp add-env "<pattern>" <env> [<env> …]  # bind env(s) to matching experiments
```

`exp create` makes `experiments/<exp>/` with a skeleton `playbook.yml`. `exp clone`
is the way to make a variation of a working experiment (optionally re-targeting
environments). Most commands take `-p/--project` if you're not in the active one.

## 2. Run

```sh
adare exp run <exp> -e <env>                   # TEST mode (default): fake run, no integrity checks
adare exp run <exp> -e <env> --prod            # PRODUCTION: real run + full forensic integrity
adare exp run <exp>                            # no -e → runs on ALL bound environments
```

**Test before prod.** The default is TEST mode — it creates *fake* runs, skips
integrity checks, and allows modifications, so it's the safe iterate-and-debug
path. Only add `--prod` once the playbook does what you want; prod runs are real,
integrity-checked, and are what you publish. Useful flags (full list in
`references/running.md`): `--debug-screenshots`, `-s/--preserve-snapshot`,
`--diff/--no-diff`, `--vm-memory`, `--vm-cpus`.

**Visual diff** (compare the same UI across OS/software versions — QEMU only, no
agent, ephemeral, no DB records):

```sh
adare exp diff <exp> -e <env>
```

## 3. Inspect

```sh
adare run list                                 # all runs
adare run list --filter <project[.env[.exp]]> # dotnotation filter
adare run info [<ulid>]                        # run detail (latest if no ULID)
adare exp info <name>                           # experiment detail (-u ULID | -d dotnotation)
```

Always **report the run ULID** after a run so the user can `run info <ulid>` it.
Dotnotation is `project.environment.experiment`. See `references/inspecting.md`.

## 4. Share

Publishing/submitting **sends data to an external server** — confirm with the user
first, and prefer a `--prod` (integrity-checked) run as the thing you publish.

```sh
adare web login                                # authenticate first
adare web status                               # check auth
adare web check run <…>                        # is it already on the server?
adare web publish <ulid>                       # publish one run (with progress)
adare web submit experiment|environment|testfunction <…>   # open a PR to the shared repo
adare web download experiment|environment|testfunction|bundle <…>
adare web sync                                 # sync all envs + experiments
```

See `references/sharing.md` for the subcommand args and the external-send caution.

## 5. Clean

```sh
adare exp clean <exp>                          # delete this experiment's fake (test) runs
adare run remove <ulid>                        # delete one run
adare exp remove <exp> [--force] [--keep-files]  # delete experiment (+runs); --force if it has prod runs
```

`exp remove` refuses to drop an experiment with productive runs unless `--force`,
and deletes the directory unless `--keep-files`. Treat both as destructive — the
`--force` path also deletes associated runs.

## Guardrails

- **Test before prod.** Iterate in TEST mode; switch to `--prod` only when the
  playbook is right. Prod runs are the integrity-checked, publishable ones.
- **One live VM at a time.** `exp run`/`exp diff` boot a VM and are serialized with
  every other VM-touching operation (`dev start`, replay, authoring). Don't overlap
  them. The `run`/`exp info`/`list` inspection commands are DB-only and safe anytime.
- **Report the run ULID** after every run.
- **Publishing/submitting is an external send** — confirm before `web publish` /
  `web submit`; data may be cached/indexed on the server even if later removed.
- **Forensic integrity / minimal guest.** Don't leave stray files in the guest;
  clean state is what makes runs comparable.
- **Destructive commands** (`exp remove --force`, `run remove`, `exp clean`) delete
  runs — confirm the ULID/name first.

## Optional: MCP

You don't need MCP here — every command above is the CLI you're already running.
The control-plane server (`adare mcp serve`, stdio) mirrors this whole lifecycle as
MCP tools for **non-CLI hosts** (Claude Desktop / web) and the embedded `adare chat`
brain. See `docs/mcp-clients.md` and the `adare-playbook` skill's MCP appendix.
