# VLM named profiles + interactive `adare vlm use`

**Date:** 2026-07-21
**Branch:** `worktree-vlm-profiles`
**Builds on:** `2026-07-21-vlm-provider-config-design.md`

## Problem
The first version stored a single flat VLM config. Users want to keep several
configured settings (e.g. a 235B cloud profile, a 32B cloud profile, a local
one) and swap between them quickly, ideally by picking from a menu.

## Decisions (locked)
- **Named profiles** with an `active` pointer (not a single config).
- **Numbered-menu** selection (rich + `click.prompt`) — no new dependency.
- Profiles are created **both** automatically (configuring a provider saves a
  named profile) **and** explicitly (`vlm save <name>`); `vlm rm <name>` deletes.

## Storage — `config/userconfig.py`
`~/.adare/config.json` becomes:
```json
{ "active": "cloud-235b",
  "profiles": { "cloud-235b": {"ADARE_VLLM_*": "..."}, "local": {...} } }
```
- `get(name)` now reads the **active** profile → `config/server.py` unchanged.
- Legacy flat `{ADARE_*: value}` files are migrated on first read into
  `profiles={"default": ...}`, `active="default"` (persisted on next write).
- New API: `active_name()`, `profiles()`, `get_profile()`, `set_profile()`,
  `set_active()`, `remove_profile()`. File stays `chmod 600`; reads never raise.

## Commands — `cli/vlm.py` + `cli/groups/vlm_commands.py`
| Command | Behaviour |
|---|---|
| `vlm use` | numbered menu: saved profiles (active marked) + "+ new Ollama Cloud/local"; pick to activate or create+activate (prompts name, hidden key) |
| `vlm use <name>` | activate an existing profile |
| `vlm use ollama-cloud\|local [--api-key/--base-url/--model] [--name]` | non-interactive create+activate (scriptable) |
| `vlm list` (alias `ls`) | table of profiles, active ✓, model, endpoint, masked key |
| `vlm save <name> [--no-activate]` | snapshot the currently-effective config (env > active profile > default) as a profile |
| `vlm rm <name>` (alias `remove`) | delete; clears `active` if it was active |
| `vlm show` | resolved config + per-key source + active-profile name |

## Non-goals
- No arrow-key TUI (would add a dependency).
- No per-profile env-var export; the active profile is the single source.
- No change to `config/server.py` resolution (`env > file(active) > default`).

## Verification (all passed, isolated temp HOME)
Imports; legacy-flat migration; preset create; `list`; switch by name;
interactive menu (pick existing + create new via piped stdin); `save`;
env-override captured by `save`; `rm` non-active; `rm` active → active cleared +
fallback-to-defaults in `show`. `ruff` clean; files < 1000 lines; no generic
`except`.
