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
| `gui_files_ops`     | kimi/minimax   | ✅ goal reached (2 folders; "sample" moved into "evidence"; scroll) after 3 engine fixes | 2/2 pass, 17/17 actions |
| `gui_writer_report` | kimi-k2.7-code | ✅ goal reached first candidate/first round (bold+centred heading, 2 paragraphs, 2-col table filled via a `loop`, saved as report.odt) — **no engine fix needed** | 2/2 pass, 44/44 actions |

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
- **`drag` / `scroll` (previously untested): now reproducible after 5 engine
  fixes below.** `gui_files_ops` moves "sample" into "evidence" (Nautilus toast
  "Moved 'sample' to 'evidence'") and scrolls, 2/2 on fresh overlays.

### Scale + loop-in-GUI verdict (`gui_writer_report`, 2026-07-20)
The open questions after the 3 short experiments (12–23 actions) were **(a)** does
cloud authoring scale to a longer, multi-section playbook, and **(b)** does the
`loop` primitive — only ever exercised on shell/variable actions before — work
inside a GUI flow? `gui_writer_report` answers both **yes**:

- **Scale: yes.** `kimi-k2.7-code:cloud` authored a **44-leaf-action** report
  (heading + keyboard formatting + 2 body paragraphs + Ctrl+F12 table + loop +
  save) that **passed goal on the first candidate, first round** — no repair
  iteration, no goal-wording refinement. Roughly 2× the length of the prior
  playbooks with no drop in first-shot quality. The single ~40-action prompt with
  explicit ordered steps (STEP A…G) authored cleanly; the model even added its own
  closing `wait_until exists "report.odt"` title assertion unprompted.
- **loop-in-GUI: yes, reproducibly.** A `loop: {times: 3}` whose body typed
  `Metric {{ index }}` / Tab / `{{ index }}` / Tab filled the three data rows
  reading **Metric 0/1/2** with values 0/1/2. `{{ index }}` (a 0-based *int* auto
  var) expands correctly inside a `keyboard: text:` because the engine sets the
  loop context on the executor and re-resolves each sub-action's `text` through
  Jinja2 (`variable_resolver.resolve_action_variables` →
  `KeyboardAction.text`). **No engine change was required** — the loop replayed
  identically on 2/2 fresh overlays (44/44 actions each, pixel-identical final
  document incl. the `33 words, 182 characters` status bar).
- **Cell traversal caveat (cosmetic, accepted):** the loop body ends each
  iteration with Tab, so the final iteration's trailing Tab creates one extra
  empty table row. Harmless for the goal; if a playbook must end exactly on the
  last filled cell, drop the trailing Tab in the last iteration (or use
  `items:`-style iteration and a `stop:` sibling on the boundary).
- **No new engine bugs.** Unlike the drag/scroll campaign (5 fixes), the deep
  single-app + loop flow surfaced zero host-side defects — the keyboard/OCR/
  `wait_until` primitives and the loop executor were already correct for GUI use.

### Engine bugs found & fixed (all surfaced by the first drag/scroll playbook)
1. **DB playbook serialization of `Target`-valued params** (`database/api/playbook.py`):
   `_serialize_value` gated its `attrs.asdict` branch behind `hasattr('__dict__')`,
   False for slots-based attrs classes like `Target`, so a `DragAction`'s
   `src`/`dst` were `str()`-ified and broke `_json_to_target` on load
   ("string indices must be integers"). Fixed: serialize `Target` symmetrically
   via `_target_to_json`.
2. **Drag result persistence** (`execution/gui_actions.py`, `playbook_controller.py`):
   `execute_drag` put raw `Target` objects in `ActionResult.data`, crashing the
   run at DB flush ("Object of type Target is not JSON serializable"). Fixed:
   store the targets' text/image descriptors; also added `TypeError` to the
   exec-record persistence `except` so a stray non-serializable payload degrades
   to a warning instead of aborting the whole run.
3. **Scroll used a non-existent QMP axis** (`hypervisor/qemu/vm.py send_qmp_scroll`):
   sent `{type: rel, axis: "wheel"}` — QEMU has no wheel axis, so QMP rejected it
   and scroll silently failed. Fixed: emit `wheel-up`/`wheel-down` **button**
   press/release per notch.
4. **Drag never triggered GTK/Nautilus DnD** (`hypervisor/qemu/vm.py
   send_qmp_mouse_drag`): it teleported start→end in one `abs` move, so the
   toolkit never saw the continuous motion needed to *initiate* a drag. Fixed:
   press-hold, 25 interpolated intermediate moves with real-time gaps, and a
   settle before release — synthetic DnD now registers the move.
5. **Wrong `dest_coordinates` in the drag-complete event** (`event_manager.py`):
   read `r.coordinates` (== source) for the destination; fixed to
   `r.data['dest_coordinates']` (forensic-log correctness).

### Note on grounding (initially misread as a bug)
The drag endpoints resolved *correctly* the whole time (src "sample"→(911,503),
dst "evidence"→(1138,412)); the "src==dst" seen in the CLI tree was only the
cosmetic event bug (#5). The real blockers were the teleport-drag (#4) and the
scroll axis (#3).

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

---

## Vision-agent loop + LocateAnything (2026-07-20)

The sections above are the **authoring** path (an Ollama-Cloud model *writes* a
playbook that then replays deterministically). This section covers the **other**
path — the closed-loop **vision agent** `adare dev agent`, driven by a local
`qwen3-vl:32b-instruct`, that observes the screen and clicks/types live each
step — and whether **LocateAnything** icon grounding helps it. Same goal as
`gui_writer_report` (bold+centred heading, 2 paragraphs, filled 2-col table,
save as `report.odt`), rephrased as a natural-language goal for the agent. One
WITH-LocateAnything run, partial completion accepted as an honest finding.

### Setup (env-only, no adare code change)
- Vision model: `ADARE_VLLM_BASE_URL=http://localhost:11434/v1`,
  `ADARE_VLLM_MODEL=qwen3-vl:32b-instruct`, `ADARE_VLLM_COORD_SPACE=normalized_1000`,
  `ADARE_VLLM_API_KEY=ollama`. `adare vm gui-doctor` confirmed the endpoint and
  auto-detected `normalized_1000` (model returned (734,312) vs target (740,250) —
  6px normalized error).
- Grounding sidecar: **new stdlib-only HTTP adapter**
  `LocateAnything/locate_adapter.py` (118 lines, `http.server`, no new deps in
  either repo) wraps `app.py`'s warm worker: `GET /health` →
  `{"status":"ok","model":"nvidia/LocateAnything-3B"}`; `POST /locate` builds the
  `GUI Grounding (box)` prompt, runs `get_worker().predict(..., generation_mode)`,
  `parse_output` → boxes, maps to ADARE's `{label, box:[x1,y1,x2,y2], center}`
  contract (adapter computes `center`; empty list on a miss → fixed-crop fallback).
  Run: `uv run python locate_adapter.py --host 127.0.0.1 --port 13111`.
  Enable in the agent with `ADARE_LOCATE_URL=http://127.0.0.1:13111`.
- **Gate test** (LA in isolation, clean 1920×1080 desktop): every centre landed
  on target — Writer dock icon (33,197), Firefox (33,69), Trash (37,390), clock
  (995,14). Model + adapter + `normalized_1000→pixel` scaling proven before
  spending an agent run.

### Result: partial, and the stall was model-side (not LA)
Session `01KY0…KP9W6`, env `ubuntu2510-libre-20260714`, `--max-steps 40`.
**Outcome: FAILED (partial) at step 22**, ~12.5 min wall-clock (~34 s/step). The
live 32B agent got ~90% of the *content* built before stalling:

| Reached | Not reached |
|---|---|
| Opened Writer (clicked dock icon), dismissed Welcome, typed the heading, both body paragraphs, navigated **Table menu → Insert Table…** dialog (genuine vision nav, not a shortcut), inserted the table, typed the "Metric"/"Value" headers, started the first data label | Never saved `report.odt`; stalled mid-table-fill |

The stall cause was **qwen3-vl emitting malformed JSON** for its decision
(`{… "action":"click", "x":528, "309", …}` — a missing `"y":` key), which the
loop treats as fatal (`agent.py` → "model decision failed"). This is a
**model-output defect, unrelated to LocateAnything.** *(Aside / bug-on-`dev`
candidate: a single malformed-JSON decision aborts the whole run rather than
being retried like a stall — worth a lenient re-ask before giving up.)*

Beyond the stall, the live run also showed **imprecision the deterministic
playbook does not have**: the heading was not visibly retained and both
paragraphs came out bold, because the agent "selected the heading" by
click-to-place-cursor **then Ctrl+A** — but Ctrl+A selects the *whole document*,
so bold/centre hit everything; and the table came out with ~20 rows instead of 4
because live typing into the Rows field didn't clear the default first. The
authored playbook avoids both by construction (`Ctrl+Home`, `Shift+End` to select
exactly the heading line; `Ctrl+A` inside the specific spin field before typing).

### LocateAnything effect: 100% grounding hit-rate, real crop-tightening — but no effect on clicking
- **Fires every click, always hits.** `LocateAnything grounding enabled via
  http://127.0.0.1:13111` (`gui_agent.py:87`) logged at startup; the adapter
  served **11/11 click-step `/locate` calls with the agent's own click
  description as the prompt, all returning a box, 0 misses** (plus the 4 gate-test
  calls = 15 total). No `"grounding failed … using fixed crop"` (`agent.py:245`)
  or `"found no box"` (`agent.py:248`) lines.
- **Crops are tightened to the element** (LA's real payoff). Recorded click crops
  are element-proportional vs the fixed ~220×90 (19,800 px²) fallback, using
  `LOCATE_CROP_MIN=72` + `LOCATE_CROP_MARGIN=16`/side:
  - 72×72 (5,184 px², **~3.8× tighter**) for square glyphs (Bold, Center, Insert
    button, table cells);
  - 260×72 for the wide "Insert Table…" menu item (correctly *expands* to the
    real label width);
  - 79×90 Writer dock icon, 103×72 heading start, 147×72 Rows field.
- **LA does NOT change where the agent clicks or how fast it runs** (confirmed
  architectural, `agent.py:280`): the click lands at qwen3-vl's own point; LA's
  bbox only (a) tightens the *recorded* crop saved into the playbook and (b)
  powers the optional described-element resolver at *replay*. So LA improves
  **replay-crop quality / robustness**, not live-loop accuracy or speed — and,
  as expected, it neither caused nor could have prevented the JSON stall.

### Autonomy-vs-determinism verdict
- **Vision agent (`dev agent` + LA):** zero authoring — just a natural-language
  goal — and it *reasons* about the live screen (it chose the Table menu on its
  own). But it is **slow** (~34 s/step under a local 32B), **imprecise**
  (whole-doc Ctrl+A, wrong row count), **incomplete** (stalled at 22/40, never
  saved), and **non-deterministic** (a malformed-JSON decision can kill a run).
- **Authored playbook (`gui_writer_report`):** one-shot authoring, then
  **fast** (~7 min), **complete**, and **reproducible** (pixel-identical 2/2 fresh
  overlays, 44/44 keyboard/OCR actions).
- **Use each for what it's for.** The live agent is a *capability/authoring aid*
  (explore a UI, propose steps, record a first-draft playbook), not a production
  runner. LocateAnything's value is squarely on the **recorded-playbook side**:
  it turns the agent's fixed ~220×90 click boxes into tight, element-shaped crops,
  which is exactly what makes a *recorded* (image-target) playbook — the fallback
  path from the recorder-vs-authored comparison above — more robust at replay.
