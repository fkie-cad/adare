# Driving ADARE from an AI agent (Claude Code & OpenCode)

## Do you even need MCP?

**For Claude Code and OpenCode: usually not.** Both agents have a shell and ADARE
ships a full CLI, so the recommended way to work a playbook is the CLI plus direct
file editing — no MCP server, no setup, no upfront tool-schema context tax:

```sh
adare exp playbook show <exp>            # or open experiments/<exp>/playbook.yml
# …edit the YAML with your normal file tools…
adare exp playbook validate <file>       # static parse + schema, no VM
adare exp playbook set <exp> <file>      # validates, backs up .bak, writes, DB bump
```

The agent skill `.claude/skills/adare-playbook/SKILL.md` drives exactly this loop.
It **auto-loads in Claude Code** (which reads `.claude/skills/`); OpenCode does not
read that directory natively — see *Using the ADARE skills across agents* below.

**Reach for MCP only when you actually need it:**

1. **Live-VM driving** (`adare dev mcp`) — step-by-step click / type / screenshot
   on one running VM, and record → save → replay from your own actions. This is
   stateful and cannot be a stateless CLI call, so it's the one genuinely non-CLI
   capability.
2. **Non-CLI hosts** — Claude Desktop / web (and the embedded `adare chat` brain)
   have no shell, so they need `adare mcp serve` to reach the lifecycle at all.

The two servers:

| Server | Transport | When you need it |
| --- | --- | --- |
| `adare dev mcp` | http | **Primary MCP use.** Fine-grained hands on **one running dev session's VM** — click / type / screenshot and record → save → replay. Not reproducible via CLI. |
| `adare mcp serve` | stdio (default) or http | Mirrors the CLI: whole lifecycle (projects, environments, experiments, runs, VMs, dev sessions), LLM authoring (`devmode_author_playbook`), execution (`devmode_execute_playbook`), and the playbook file/DB tools `playbook_read` / `playbook_validate` / `playbook_write`. Only needed for **non-CLI hosts** — redundant in Claude Code / OpenCode. |

The same tool registry backs `adare mcp serve`, every MCP client, and the embedded
`adare chat` REPL, so the tools behave identically everywhere. `adare chat` and
non-CLI hosts get the `playbook_*` tools at zero extra cost — that's why the code
stays even though Claude Code / OpenCode lead with the CLI.

## Using the ADARE skills across agents

ADARE ships a suite of workflow **skills** in the tracked `skills/` directory —
`adare-playbook`, `adare-experiment`, `adare-devvm`, `adare-vm-build`,
`adare-testfunction`. A skill is just a Markdown file (workflow + guardrails + a
trigger line); its value is portable prose that tells any agent the ADARE workflow
and to drive the `adare` CLI over a shell. What differs between agents is only *how
the skill file gets discovered and loaded* — not the model.

### Claude Code (native)

Claude Code auto-loads skills from `.claude/skills/` (this project) and
`~/.claude/skills/` (global — every project). The source of truth is the tracked
`skills/` directory; install it into both locations with the make target:

```sh
make install-skills
```

It symlinks each `skills/adare-*` into `.claude/skills/` **and** `~/.claude/skills/`,
so `skills/` stays the single version-controlled source and edits propagate
everywhere. Undo with `rm ~/.claude/skills/adare-* .claude/skills/adare-*`.

This applies whether you start Claude Code directly (`claude`) or via
`ollama launch claude` — the latter launches the *same* Claude Code binary wired to a
local Ollama model, so skill loading is identical (only the model differs, and a
local model follows the workflows less reliably than Claude).

### OpenCode (needs setup — it does NOT read `.claude/skills/`)

Native OpenCode has no Anthropic-style skills. Pick one:

1. **`opencode-skills` plugin** (faithful to the Agent Skills spec — registers each
   skill as a dynamic tool, so the trigger line stays in context and the body loads
   on demand):
   ```jsonc
   // opencode.json
   { "plugin": ["opencode-skills"] }
   ```
   It scans `.opencode/skills/`, `~/.opencode/skills/`,
   `~/.config/opencode/skills/` — **not** `.claude/skills/`. Point it at ours:
   ```sh
   ln -sfn "$PWD/skills" .opencode/skills
   ```
2. **Plugin-free — `AGENTS.md` lazy `@`-references** (OpenCode's native rules file).
   A short always-in-context index that the model reads on demand, reusing the same
   SKILL.md files:
   ```markdown
   # ADARE workflows
   CRITICAL: when a reference below is relevant, use the Read tool to load it
   on a need-to-know basis (lazy). Treat loaded content as mandatory.

   - Run/inspect/share experiments → @skills/adare-experiment/SKILL.md
   - Drive/debug a live VM          → @skills/adare-devvm/SKILL.md
   - Edit/validate/replay a playbook → @skills/adare-playbook/SKILL.md
   - Build/verify a VM or env        → @skills/adare-vm-build/SKILL.md
   - Author a forensic test-function → @skills/adare-testfunction/SKILL.md
   ```
3. **Custom commands** (`.opencode/command/*.md`, invoked as `/name`) for deliberate,
   manual invocation instead of auto-routing.

Either agent can also drive a **local Ollama model** (`ollama launch claude`,
`ollama launch opencode`, or an Ollama provider in `opencode.json`) — the skills load
by the mechanism above regardless; only reliability tracks the model.

### Non-CLI / any MCP client

Hosts without a shell (Claude Desktop / web) can't run skills at all — use ADARE's
MCP servers below, which expose the same capabilities as tools. This is also the
model/host-agnostic path for any MCP client, including one driving a local Ollama
model.

## Live VM hands — `adare dev mcp` (primary MCP use)

This server binds to one already-running dev session and speaks HTTP.

```sh
adare dev start -e <env>          # boot a VM; note the session id
adare dev mcp -s <id> --port 13110
```

### Claude Code

```sh
claude mcp add --transport http adare-gui http://127.0.0.1:13110/mcp
```

### OpenCode (`opencode.json`)

```json
{
  "mcp": {
    "adare-gui": {
      "type": "remote",
      "url": "http://127.0.0.1:13110/mcp",
      "enabled": true
    }
  }
}
```

## Control plane — `adare mcp serve` (non-CLI hosts only)

Skip this in Claude Code / OpenCode — the `adare exp playbook …` CLI above covers
the same ground. It exists for hosts without a shell (Claude Desktop / web). Best
launched over stdio directly by the client.

### Claude Code

```sh
claude mcp add adare -- adare mcp serve
```

### OpenCode (`opencode.json`)

```json
{
  "mcp": {
    "adare": {
      "type": "local",
      "command": ["adare", "mcp", "serve"],
      "enabled": true
    }
  }
}
```

### HTTP variant (shared / long-lived server)

```sh
adare mcp serve --transport http --port 13111
# Claude Code:
claude mcp add --transport http adare http://127.0.0.1:13111/mcp
```

OpenCode HTTP equivalent: a `"type": "remote"` entry with
`"url": "http://127.0.0.1:13111/mcp"`.

## The "fix a playbook" loop (over MCP tools)

If you are on a non-CLI host using `adare mcp serve`, the same loop is available as
tools:

1. `playbook_read(experiment=…)` — or open `experiments/<name>/playbook.yml`.
2. Edit the YAML.
3. `playbook_validate(yaml=…)` — static parse + schema, no VM; returns
   `{valid, errors}`.
4. `devmode_execute_playbook(session_id=…, playbook_yaml=…)` — replay on a live
   session (start one with `devmode_start_session(environment=…)`).
5. `playbook_write(experiment=…, yaml=…)` — re-validates, backs up to
   `playbook.yml.bak`, writes, and re-ingests the DB (version bump).

In Claude Code / OpenCode, use the CLI equivalents instead (no MCP client needed):

```sh
adare exp playbook show <exp>
adare exp playbook validate <file>
adare exp playbook set <exp> <file> [--no-backup]
```

## Notes

- **One live VM at a time.** VM-touching tools are serialized; the playbook
  file/DB tools are not and are safe anytime.
- Always validate before writing — `playbook_write` / `adare exp playbook set`
  refuse invalid YAML (`PLAYBOOK_INVALID`).
- Do not leave stray files/logs inside a guest VM; forensic integrity depends on
  a clean guest.
