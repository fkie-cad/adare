---
name: adare-playbook
description: "Fix, validate, read, author, and replay ADARE experiment playbooks. Trigger when the user wants to fix/edit/validate/read/create/replay a playbook.yml. Default path is the adare CLI + direct file editing (no MCP needed); MCP is optional, only for live-VM driving or non-CLI hosts."
---

# ADARE playbooks

ADARE runs GUI/forensic experiments inside VMs. Each experiment owns one
`playbook.yml` (`<project>/experiments/<name>/playbook.yml`) — an ordered list of
UI actions (click / keyboard / scroll / command / screenshot / pull / waituntil …)
plus `settings` and `tests`. A playbook is a plain file, so you fix it exactly how
you fix code: **read → edit → validate → (optional replay) → write back**.

**You do not need MCP for this.** ADARE ships a full CLI, and you have `Read`,
`Edit`, and `Bash`. The default loop below is pure CLI + file editing — no MCP
server, no setup, no upfront tool-schema tax. MCP is an *optional* layer, covered
last, only for the one thing the CLI can't do (step-by-step live-VM driving) and
for non-CLI hosts (Claude Desktop / web).

This skill auto-loads in **Claude Code** (which reads `.claude/skills/`); the loop
itself is pure Bash + the `adare` CLI, so it's portable to any agent with a shell. On
**OpenCode** — which does *not* natively read `.claude/skills/` — load skills via the
`opencode-skills` plugin or an `AGENTS.md` reference (see `docs/mcp-clients.md`).

**Related skills** (this one owns *editing/authoring/validating/replaying the
`playbook.yml` file*; hand off when the job is really something else):
- Step-by-step **live-VM driving/debugging** (actions, checkpoints, reset, CV/OCR) →
  `adare-devvm`.
- **Running / inspecting / sharing** an experiment (test vs prod runs, run ULIDs,
  publish) → `adare-experiment`.
- Writing the forensic functions a playbook's **`tests:` block** calls →
  `adare-testfunction`.
- Building the **base VM / environment** a playbook runs on → `adare-vm-build`.

## Fix an existing playbook (default — CLI + file edit, no MCP)

The tight, deterministic loop. Prefer this whenever a playbook exists.

1. **Read** — open `experiments/<name>/playbook.yml` directly with `Read`/`Edit`
   (editing the file is your strength), or dump it with
   `adare exp playbook show <exp>` (reads disk, falls back to the DB).
2. **Edit** — make the minimal YAML change (a typed string, a target text, an
   action's order).
3. **Validate** — `adare exp playbook validate <file>`. Static parse + schema, no
   VM. On failure it prints the errors; fix and re-validate. **Never skip this
   before writing.**
4. **Replay** *(optional but recommended)* — verify the change on a real VM before
   committing it. Start a dev session (`adare dev start -e <env>`) and replay the
   file on it. Fine-grained, step-by-step replay is the one thing the CLI can't do
   directly — that's the live-VM MCP server (see *Optional: MCP* below).
5. **Write back** — `adare exp playbook set <exp> <file> [--no-backup]`. It
   re-validates, backs up the old file to `playbook.yml.bak`, writes
   `playbook.yml`, and re-ingests the DB (version bump). It **refuses invalid
   YAML** — treat that as a signal to fix, not retry. Report the new version.

```sh
adare exp playbook show <exp>            # or: Read experiments/<exp>/playbook.yml
# …edit the YAML…
adare exp playbook validate <file>       # parse + schema, no VM
adare exp playbook set <exp> <file>      # validates, .bak backup, writes, DB bump
```

## Author a new playbook

Two ways, pick per task — both are CLI:

- **From human text steps:** `adare dev author -s <id> [--script-file steps.txt |
  --interactive]` on a live dev session — no vision model, you provide the actions.
- **Vision-authored:** `adare dev author-ai -s <id> --goal "…" [--replay]`. A cloud
  vision model drafts the UI actions from a screenshot, validates, and (with
  `--replay`) verifies live and repairs on failure. Records the best YAML.

Start the session first with `adare dev start -e <env>`. Finish by installing the
result into an experiment: `adare exp playbook set <exp> <file>` (validated +
backed up + DB-ingested).

## Optional: MCP (only if you need it)

You do **not** need this for the loops above. Reach for MCP only in these two
cases.

### Live-VM hands — `adare dev mcp` (HTTP) — the one genuinely non-CLI capability

Step-by-step click / type / screenshot on **one running VM**, plus record → save →
replay a playbook from your own actions. This is stateful (QMP bound to a single
event loop), so it can't be a stateless CLI call — an MCP server is the right tool.

1. `adare dev start -e <env>` → note the session id
2. `adare dev mcp -s <id> --port 13110`
3. Register it:
   - **Claude Code:** `claude mcp add --transport http adare-gui http://127.0.0.1:13110/mcp`
   - **OpenCode** (`opencode.json`):
     ```json
     {
       "mcp": {
         "adare-gui": { "type": "remote", "url": "http://127.0.0.1:13110/mcp", "enabled": true }
       }
     }
     ```

### Control plane — `adare mcp serve` (stdio) — mirrors the CLI

Exposes the whole lifecycle (project / env / experiment / run / vm / dev-session),
LLM playbook authoring, execution, and the `playbook_read/validate/write` tools as
MCP tools. **In Claude Code / OpenCode you don't need it** — every one of these is
already the `adare` CLI you're running via Bash. It's useful for **non-CLI hosts**
(Claude Desktop / web) and the embedded `adare chat` brain.

- **Claude Code:** `claude mcp add adare -- adare mcp serve`
- **OpenCode** (`opencode.json`): a `"type": "local"` entry with
  `"command": ["adare", "mcp", "serve"]`.

See `docs/mcp-clients.md` for the human-facing copy of this setup.

## Guardrails

- **One live VM at a time.** VM-touching commands/tools (`adare dev start`,
  replay, `adare dev author*`, `experiment run`) are serialized — don't overlap
  them. The playbook file/DB operations (`show`/`validate`/`set`) are *not* VM
  operations and are safe anytime.
- **Always validate before writing.** `adare exp playbook set` /
  `playbook_write` refuse invalid YAML (`PLAYBOOK_INVALID`).
- **Report the run ULID / replay summary** after any execution so the user can
  inspect it.
- **Keep guest state minimal** — do not leave stray files or logs inside the VM;
  forensic integrity depends on a clean guest.
- Stop any dev session you started when the loop is done.
