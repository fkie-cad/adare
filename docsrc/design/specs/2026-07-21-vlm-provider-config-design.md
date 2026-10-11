# VLM provider config + `adare vlm` CLI

**Date:** 2026-07-21
**Branch:** `worktree-vlm-config`
**Status:** approved (design), pending implementation

## Problem

The GUI-automation vision-LLM (used by `dev agent`, `dev record`, `dev author`,
self-heal) is configured only through `ADARE_VLLM_*` environment variables,
resolved once at import time in `config/server.py`. The built-in defaults point
at a **local** vLLM server (`http://localhost:8000/v1`, `Qwen/Qwen2-VL-7B-Instruct`).
There is no persisted configuration and no way to switch providers without
exporting env vars in every shell.

Goal: make **Ollama Cloud** the working default on this machine, and add a CLI to
configure the VLM provider persistently.

## Decisions (locked)

- **Persisted config file**, not hardcoded code defaults. `~/.adare/config.json`
  (`APPDATA_DIR/config.json`), `chmod 600`. JSON → **no new dependency**.
- **Resolution precedence: env var > config file > code default.** A one-off
  `ADARE_VLLM_*=… adare …` still wins over the saved file. Code defaults stay
  `localhost` / Qwen2-VL — the shared repo default is untouched.
- **Config keys mirror the env-var names** (`ADARE_VLLM_BASE_URL`, …) so the file
  is self-documenting and the resolver is a one-liner.
- **Top-level `adare vlm` group** (config affects more than `dev agent`).
- **API key stored in the config file** (`chmod 600`), masked on display.
- **Cloud preset:** `base_url=https://ollama.com/v1`, `model=qwen3-vl:235b-cloud`,
  `coord_space=normalized_1000`.

## Components

### 1. `config/userconfig.py` (new, ~80 lines)
Persisted key/value store, flat `{ "ADARE_*": "value" }`.
- `load() -> dict` — read + cache once per process; `{}` on missing/unreadable
  (catch `OSError` and `json.JSONDecodeError` only — no generic `except`).
- `get(name) -> str | None` — file value for one key.
- `set_values(mapping: dict)` — merge into the file, write, `chmod 0o600`. Creates
  `APPDATA_DIR` if absent. Invalidates the cache.
- `unset(keys: list[str])` — remove keys, rewrite (drop the file if empty).
- `path() -> Path` — `APPDATA_DIR/config.json` (for `vlm show`).

### 2. `config/server.py` (edit)
```python
from . import userconfig
def _cfg(name, default):
    return os.environ.get(name) or userconfig.get(name) or default
```
Route the four VLM keys through `_cfg`:
`VLLM_BASE_URL`, `VLLM_MODEL`, `VLLM_API_KEY`, `VLLM_COORD_SPACE`.
Everything else unchanged (YAGNI; helper is generic for later adoption).

### 3. `cli/vlm.py` (new, handlers, ~120 lines)
- `exec_vlm_use(arguments)` — `arguments.provider` in {`ollama-cloud`, `local`}.
  - `ollama-cloud`: resolve key from `--api-key` or prompt (hidden); write
    base_url/model/coord_space/api_key (applying the cloud preset, overridable by
    `--base-url`/`--model`). Error clearly if no key given (non-interactive).
  - `local`: write local preset, `coord_space=absolute`, `unset` the api key.
  - Success message points at `adare vm gui-doctor` to verify the live endpoint.
- `exec_vlm_show(arguments)` — print resolved base_url / model / coord_space /
  api_key (**masked**, last 4 shown), each annotated with its **source**
  (`env` / `config-file` / `default`) plus the config-file path.

### 4. `cli/groups/vlm_commands.py` (new) + `run.py` (edit)
Mirror `cli/groups/dev_commands.py`: `register(cli, AliasedGroup, exec_with_error_printing)`
defining a `vlm` group with `use <provider>` and `show`. Import + call
`register_vlm_commands(...)` in `run.py` next to the other `register_*` calls.

## Behaviour

| Command | Effect |
|---|---|
| `adare vlm use ollama-cloud --api-key K` | writes cloud preset + key to config.json (0600) |
| `adare vlm use ollama-cloud` | prompts for the key (hidden), then as above |
| `adare vlm use local` | reverts to local preset, clears the key |
| `adare vlm show` | prints resolved config + per-key source + masked key |
| `ADARE_VLLM_BASE_URL=… adare dev agent …` | env still overrides the file |

## Non-goals
- No generic `adare config set KEY VALUE` (provider switch only, per decision).
- No endpoint/key validation in `use` (that's `vm gui-doctor`'s job).
- No change to the hardcoded code defaults.
- Running processes don't hot-reload the file (each CLI call is a fresh process).

## Verification
1. Byte-compile + import the new/edited modules.
2. `adare vlm show` on a clean machine → all sources `default`, key `default`.
3. `adare vlm use ollama-cloud --api-key TESTKEY` → config.json written, `0600`.
4. `adare vlm show` → base_url/model/coord source `config-file`, key masked.
5. `ADARE_VLLM_MODEL=x adare vlm show` → model source `env` (precedence proof).
6. `adare vlm use local` → key cleared, sources back to config-file/default.
7. `ruff check` clean; files < 1000 lines; no generic `except Exception`.

Live flip to Ollama Cloud needs the user's real key (never passes through the
assistant unless pasted); `vm gui-doctor` confirms the endpoint.
