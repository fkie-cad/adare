# FLOW — LLM-authored UI-action playbooks

This is the end-to-end flow for having an **Ollama Cloud vision model author a
robust ADARE UI-action playbook** from a screenshot, validate it against the
real schema, replay-verify it on a VM, and repair it until it works — then pick
the best-performing model.

The harness is `author_playbook.py`; the model contract lives in
`schema_spec.md` (vocabulary) + `authoring_prompt.md` (rules). It produces
**UI-action playbooks only** (`actions:` — never `tests:`).

---

## ASCII overview

```
        goal (natural language)
              │
              ▼
   ┌─────────────────────────┐        orchestrator serializes ALL
   │ boot / attach dev session│◄────── live-VM access (Phase 4).
   │  adare dev start -e ENV  │        The harness isolates each live
   └─────────────────────────┘        step behind a function so the
              │                        author→validate path runs w/o a VM.
              ▼
   ┌─────────────────────────┐
   │ capture screenshot 1080p │  QMP screendump via a 1-action screenshot
   │  (or inject --screenshot)│  playbook  ->  base64 PNG
   └─────────────────────────┘
              │  screenshot_b64
              ▼
   ┌───────────────────────────────────────────────┐
   │ AUTHOR (Ollama Cloud, localhost:11434/api/chat)│
   │  system = authoring_prompt.md                  │
   │           + schema_spec.md + {goal}            │
   │  user   = instruction + screenshot as image    │
   │  strip <think>, extract ```yaml block          │
   └───────────────────────────────────────────────┘
              │  playbook YAML (actions: only)
              ▼
   ┌─────────────────────────┐   parse error text
   │ VALIDATE (parse_playbook)│───────────────┐
   │  strict: forbid_extra_keys│               │
   └─────────────────────────┘               │
              │ ok                             │
              ▼                                │
   ┌─────────────────────────┐  failure output │
   │ REPLAY-VERIFY (pluggable)│──────────────┐ │
   │  replay_cb -> adare dev  │              │ │
   │  playbook -f  (live VM)  │              │ │
   └─────────────────────────┘              │ │
              │ pass                          │ │
              ▼                                ▼ ▼
   ┌─────────────────────────┐   ┌───────────────────────────┐
   │ FINALIZE best playbook   │   │ REPAIR: feed error/failure │
   │  (valid + replayed clean)│   │ back as prior_failure, re- │
   └─────────────────────────┘   │ author (bounded rounds)    │
              │                    └───────────────────────────┘
              ▼                              │ next round / next model
   ┌─────────────────────────┐              │
   │ MODEL SELECTION          │◄─────────────┘
   │ first model to produce a │
   │ valid+passing playbook   │
   │ wins; else best valid.   │
   └─────────────────────────┘
              │
              ▼
   ┌─────────────────────────┐
   │ REPRODUCIBILITY re-check │  (orchestrator, Phase 5) replay the finalized
   │  replay again from a     │  playbook again from the initial checkpoint
   │  clean checkpoint        │  to confirm it is deterministic.
   └─────────────────────────┘
```

---

## Numbered steps

1. **Goal.** A natural-language description of the UI task, e.g. *"Open
   LibreOffice Writer, type a sentence, save it as report.odt in Documents."*

2. **Boot / attach a dev session.** `boot_session(environment)` runs
   `adare dev start -e <ENV>` and parses the printed `Dev session started: <id>`.
   In Phase 4 the **orchestrator** owns this — it serializes live VM access and
   passes the session id to the harness (`--session <id>`), because only one
   thing may drive the VM at a time.

3. **Capture the screen (1920x1080).** `screenshot()` drives a QMP screendump
   through a single-action `screenshot` playbook via `adare dev playbook`
   (there is no `dev screenshot` subcommand, and `dev action` / `dev state` are
   known-broken), then reads back the newest PNG under
   `reporting/screenshots/` and base64-encodes it. For VM-less runs,
   `--screenshot <path>` injects a PNG instead. The orchestrator may override
   capture with its own session-aware callback (it holds the executor directly).

4. **Author (Ollama Cloud).** `author(model, goal, screenshot_b64, schema)`
   POSTs to `http://localhost:11434/api/chat` with:
   - **system** = `authoring_prompt.md` with `{schema_spec}` and `{goal}`
     substituted (the full vocabulary + the HARD ROBUSTNESS RULES);
   - **user** = a short instruction + the screenshot in `images:` (base64, no
     `data:` prefix).
   The reply is de-`<think>`-ed and the first ```yaml block is extracted. The
   rules force: OCR `text:` targets + keyboard nav over image clicks; a
   `wait_until` before every click; optional dialogs wrapped in `block.when`;
   no fixed `idle` for sync; **`actions:` only, no `tests:`**.

5. **Validate.** `validate(yaml)` writes a temp file and parses it with ADARE's
   real `parse_playbook` (`forbid_extra_keys = True`). Returns `(ok, error)`.
   This is the deterministic gate that catches hallucinated fields/strategies.

6. **Replay-verify (pluggable).** If a `replay_cb` is supplied, the valid
   playbook is replayed on the live VM via `replay()` → `adare dev playbook -f`.
   The callback is injected by the orchestrator so replay is serialized with
   everything else touching the VM. With no callback (VM-less), a playbook that
   *parses* is the best assertable result.

7. **Repair loop.** On a validation or replay failure, the exact error text is
   fed back as `prior_failure` and the model re-authors — bounded by `--rounds`
   per model. A valid+passing playbook always outranks a merely-valid one.

8. **Finalize + model selection.** `author_verify_repair_loop` tries the models
   in preference order and returns an `AuthoringOutcome`: the best YAML, the
   winning model, and whether it also replayed cleanly. The first model to yield
   a valid **and** passing playbook wins and short-circuits the rest.

9. **Reproducibility re-check (Phase 5).** The orchestrator replays the
   finalized playbook again from a clean checkpoint to confirm determinism
   (the whole point of the robustness rules), then records the model verdict.

---

## Orchestrator's role & the pluggable-replay design

Live VM access must be **serialized** — a VM has one screen and one input focus.
The harness never assumes it may grab the VM whenever it likes. Instead:

- Each live step (`boot_session`, `screenshot`, `replay`) is a standalone
  function that shells out to the real `adare dev …` CLI.
- The verify step in `author_verify_repair_loop` is a **callback**
  (`replay_cb`), defaulting to `None`. The pure author→validate path therefore
  runs anywhere, no VM required (`--dry-run --screenshot shot.png`).
- In Phase 4 the orchestrator injects a `replay_cb` that (a) writes the authored
  YAML into the experiment directory, (b) calls `replay()` against the single
  live session it manages, and (c) returns `(ok, output)` for the repair loop.
  Screenshot capture can be injected the same way. This keeps every VM touch on
  the orchestrator's serialized timeline while the model reasoning / validation
  runs freely.

---

## Exact commands

VM-less author + validate (proves author()+validate(); no VM):

```bash
PYTHONPATH=<worktree>/adare \
  uv run --project /Users/miq/Documents/Projects/ADARE/adare python3 \
  -m adare.backend.experiment.vlm.authoring.author_playbook \
  --goal "open the File menu" \
  --screenshot /path/to/shot.png \
  --dry-run \
  --models kimi-k2.7-code:cloud,minimax-m3:cloud,glm-5.2:cloud \
  --out /tmp/authored.yml
```

Full live loop (orchestrator wires the session; `--replay` enables live verify):

```bash
adare dev start -e ubuntu2510-libre-20260714          # orchestrator boots once
# -> Dev session started: <SID>

PYTHONPATH=<worktree>/adare \
  uv run --project /Users/miq/Documents/Projects/ADARE/adare python3 \
  -m adare.backend.experiment.vlm.authoring.author_playbook \
  --goal "Open LibreOffice Writer, type a sentence, save as report.odt" \
  --session <SID> \
  --replay \
  --rounds 3 \
  --models kimi-k2.7-code:cloud,minimax-m3:cloud,glm-5.2:cloud \
  --out experiments/gui_writer/playbook.yml

# Reproducibility re-check (Phase 5):
adare dev playbook -f experiments/gui_writer/playbook.yml -s <SID> --restore
```

The harness can also `--boot` its own session (`--boot --environment <ENV>`),
but under the multi-agent plan the orchestrator boots and owns the session.

---

## Findings from the live authoring campaign (2026-07-20)

Env: `ubuntu2510-libre-20260714` (aarch64). Author models tried:
`kimi-k2.7-code:cloud`, `minimax-m3:cloud`, `glm-5.2:cloud`. Verification path:
`adare experiment run --prod --debug-screenshots` on a fresh overlay per run
(dev-session live snapshots fail on this aarch64/UEFI env — `--restore` is not
usable there, so `experiment run` is the reliable clean-reset path and doubles
as the reproducibility harness).

### Results
| Experiment | Author model | Outcome | Reproducibility (2× fresh overlay) |
|---|---|---|---|
| `gui_writer_format` | kimi-k2.7-code | ✅ goal reached (bold+italic text) | 2/2 pass, 12/12 actions |
| `gui_writer_table`  | kimi-k2.7-code | ✅ goal reached (3×2 table, A1/A2)  | 2/2 pass, 23/23 actions |
| `gui_files_ops`     | kimi/minimax   | ⚠️ folder-create OK; drag no-op + scroll fail (see below) | n/a |

### Per-interaction reproducibility verdict
- **Keyboard (keys / combinations / typed text): deterministic.** Every passing
  step in both Writer playbooks is keyboard-driven; identical action counts on
  independent overlays. This is the most reproducible primitive.
- **OCR `text:` targets + `wait_until`: reproducible, but text-sensitive.** Works
  well for stable UI labels (menus, dialog titles). Sensitive to (a) truncated
  labels (GNOME search results show "LibreOffice Wri…" — never wait for the full
  name) and (b) duplicate on-screen text (see drag below).
- **`wait_until`-gated synchronization: the key to reproducibility.** Replacing
  fixed `idle` with `wait_until` is what makes runs repeatable. BUT: `block:
  when:` is a *point-in-time* check and races against dialogs that appear after a
  delay — for a dialog KNOWN to appear (e.g. LibreOffice first-run Welcome on a
  fresh profile), do NOT guard it; `wait_until exists → esc → wait_until
  not_exists` deterministically. This single fix took `writer_format` from
  "executes but types into the void" to fully goal-reproducible.
- **Keyboard shortcuts beat menu-structure assumptions.** `writer_table` only
  worked once switched from "Insert menu → Table" (that item does not exist in
  this build; table insert lives under the Table menu) to the `Ctrl+F12`
  shortcut. Prefer documented shortcuts over authored menu navigation.
- **`drag` / `scroll` (previously untested): new data — see open findings.**

### Engine bugs found & fixed (surfaced by the first drag-using playbook)
1. **DB playbook serialization of `Target`-valued params** (`database/api/playbook.py`):
   `_serialize_value` gated its `attrs.asdict` branch behind `hasattr('__dict__')`,
   which is False for slots-based attrs classes like `Target`, so a `DragAction`'s
   `src`/`dst` were `str()`-ified and broke `_json_to_target` on load
   ("string indices must be integers"). Fixed: serialize `Target` symmetrically
   via `_target_to_json`.
2. **Drag result persistence** (`execution/gui_actions.py`, `playbook_controller.py`):
   `execute_drag` put raw `Target` objects in `ActionResult.data`, crashing the
   run at DB flush ("Object of type Target is not JSON serializable"). Fixed:
   store the targets' text/image descriptors; also added `TypeError` to the
   exec-record persistence `except` so a stray non-serializable payload degrades
   to a warning instead of aborting the whole run.

### Open findings (not fixed — need a decision)
- **Drag grounding, dual same-type targets:** in `gui_files_ops`, `src: text
  "sample"` and `dst: text "evidence"` both resolved to the *same* coordinate,
  so the drag was a no-op. Two OCR-text targets of the same kind are not being
  disambiguated by the resolver in the drag path. Candidate directions: use
  distinct strategies / regions per endpoint, or `position:`-based drag, or a
  drag that keys off the selected item.
- **Scroll on the agent GUI executor:** `execute_scroll` is wired
  (`gui_actions.execute_scroll` → `websocket_client.scroll`), but the VM agent
  returns non-success instantly for a `direction: down, amount: N` scroll. Needs
  investigation of the agent-side scroll command semantics.

### Harness / prompt improvements folded back in
- `validate()` now flattens cattrs sub-exceptions (`transform_error`) so the
  repair loop gets field-level detail instead of "N sub-exceptions".
- `glm-5.2:cloud` returns HTTP 400 on image input (not vision-capable via
  `/api/chat`); the two vision authors that work are `kimi-k2.7-code:cloud`
  (primary; authored both passing Writer playbooks) and `minimax-m3:cloud`.
- Robustness rules added: no `any`/`all` inside `when:` (only in
  `wait_until.condition`); GNOME super-key app launch + truncated-label caveat;
  the deterministic first-run-dialog pattern above.

### Recorder-vs-authored robustness comparison (structural)
The hardened recorder (Phase 2) emits **image-crop `click` targets** each gated
by a `wait_until { exists: <same crop> }`. The Ollama-Cloud-authored playbooks
use **OCR `text:` targets + keyboard shortcuts**, also `wait_until`-gated.
- *Authored (text/keyboard):* resolution is font/label-text dependent but
  resolution-independent; keyboard steps are fully deterministic. No image
  assets to drift. Most robust for menu/dialog/keyboard flows — proven 2/2
  reproducible here.
- *Recorded (image crops):* resolution/theme/font-render sensitive (a re-themed
  or re-scaled UI shifts the crop match), but works where there is no stable OCR
  text or accelerator (e.g. a dock icon, a toolbar glyph). The Phase 2
  wait-before-click gate removes the recorder's old "click into the void" race,
  closing the biggest reproducibility gap in recorded playbooks.
- *Verdict:* prefer authored text/keyboard playbooks for reproducibility; fall
  back to recorded image targets only for elements with no text/accelerator.
  The two paths are complementary, not competing.
