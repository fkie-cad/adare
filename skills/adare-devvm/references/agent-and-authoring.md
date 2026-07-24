# Vision agent & authoring — reference

Two vision-driven paths. Both need a configured VLM (`ADARE_VLLM_*`; check with
`adare vlm show` / `adare vm gui-doctor`). The **authoring** path (`author`/
`author-ai`) is owned by the `adare-playbook` skill; this reference focuses on the
live **agent** and the grounding backend.

## `adare dev agent` — drive toward a goal

Observes the live screen and clicks/types each step toward a natural-language goal.
Attach to a running session with `-s`, or self-contained with `-e` (boots a fresh
VM, drives it, tears it down unless `--keep`).

| Flag | Meaning |
| --- | --- |
| `-s, --session TEXT` | Attach to a running session (auto-detected if one). |
| `-e, --environment NAME` | Boot a fresh VM from this env, drive, tear down. Mutually exclusive with `-s`. |
| `--keep` | With `-e`, leave the VM running afterwards. |
| `--goal TEXT` / `--goal-file PATH` | The task, inline or from a file. |
| `-o, --out PATH` | Record a replayable playbook to this path. |
| `--as-experiment NAME` | Scaffold `experiments/NAME/` (playbook.yml + img/ crops + metadata.yml). Files only — no DB load; run `adare experiment load NAME` after. Excludes `-o`. |
| `--verify / --no-verify` | After recording, replay from a pre-run baseline checkpoint to validate (default on). Always parse-checks regardless. |
| `--plan / --no-plan` | Iterative plan/verify/backtrack: decompose the goal into sub-goals, checkpoint before each, verify with an independent checker, reset to retry dead ends — building a playbook from only verified sub-goals. Default `ADARE_AGENT_PLAN`. |
| `--ground / --no-ground` | Auto-start the LocateAnything grounding server for the run; clicks grounded to the true element box, torn down at end. Attaches to `ADARE_LOCATE_URL` if set. Needs `uv sync --extra grounding`. Default `ADARE_LOCATE_AUTOSTART`. |
| `--step, --interactive` | Pause before each action to approve / skip / stop. |
| `--max-steps` / `--stall-limit` | Override the step / stall budgets. |
| `--progress / --no-progress` | Live per-step table (default on for TTY). |
| `--reasoning / --no-reasoning` | Show per-step reasoning panel (default on). Global `--verbose`/`--very-verbose` also streams grounding + decision-repair logs. |
| `--video / --no-video` | Record run to `<run_dir>/run.mp4` via ffmpeg (needs ffmpeg). Default `ADARE_AGENT_VIDEO` (off). |

```sh
adare dev agent -s <id> --goal "open the Files app and go to Documents"
adare dev agent -s <id> --goal "…" -o experiments/files.play.yaml
adare dev agent --plan --goal "open LibreOffice and write an invoice" -o inv.play.yaml
adare dev agent -e ubuntu2510-libre --goal "…" --as-experiment demo6 --ground --video
```

### Agent vs authored playbook (know the trade-off)

The live agent **reasons about the screen** (zero authoring, chooses menus on its
own) but is **slow** (~30 s/step on a local 32B), **imprecise**, sometimes
**incomplete**, and **non-deterministic** (a single malformed model decision can
abort a run). A recorded/authored playbook that then replays is **fast, complete,
reproducible**. So: use `dev agent` to explore a UI and *produce a first-draft
playbook*, then validate/replay that playbook as the real artifact — don't treat the
agent as a production runner.

## LocateAnything grounding

`--ground` starts a sidecar that resolves a click description to the true element
bounding box. Its payoff is on the **recorded-playbook** side: it tightens the
agent's fixed ~220×90 click crops into tight, element-shaped crops (proven ~3.8×
tighter for glyphs), which makes a recorded (image-target) playbook more robust at
replay. It does **not** change where the live agent clicks or how fast it runs.

```sh
adare dev grounding-pull                 # pre-download weights (~7.3 GB) up front
adare dev grounding-pull --model <hf-id-or-path>
```

Needs the grounding backend (`uv sync --extra grounding`), an `HF_TOKEN`, and the
accepted NVIDIA license. Skipped if the configured model is already a local dir.

## Authoring paths (see `adare-playbook`)

- `adare dev author -s <id> [--script-file steps.txt | --interactive] -o out.yaml` —
  human text steps, no VLM planner; LocateAnything grounds described clicks; use
  `click @x,y …` to place a click by hand when no grounding backend is available.
- `adare dev author-ai -s <id> --goal "…" [--replay] [-o out.yaml]` — a cloud vision
  model authors an `actions:` playbook, validated against the real schema and (with
  `--replay`) replayed live and repaired on failure. See
  `backend/experiment/vlm/authoring/FLOW.md`.
