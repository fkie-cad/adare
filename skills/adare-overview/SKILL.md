---
name: adare-overview
description: "Start here for any ADARE task when it is unclear which ADARE skill applies, or the task spans several steps (e.g. 'build an experiment that checks whether deleting a file in Firefox leaves artifacts on Ubuntu and Windows'). Gives the mental model (project → environment → experiment → playbook → tests → run → compare), routes to the right adare-* skill, and sets the agent rules for driving the adare CLI (machine-readable output, one live VM, never --force without asking). Not this → a single well-scoped step that clearly matches one adare-* skill."
---

# ADARE for agents — overview & router

ADARE (Automated Desktop Analysis framework for Reproducible Experiments) answers
"which forensic artifacts does this GUI action leave, and does that change across
OS/software versions?" It replays scripted GUI actions in VMs and asserts outcomes.

## Mental model

```
project            a directory holding experiments (run project-scoped commands inside it)
└─ experiment      one question, e.g. "open a text file in gedit"
   ├─ environment  a VM image to run on (several → compare versions)
   ├─ playbook.yml GUI actions (click/type/key/command) + variables
   │  └─ tests:    assertions, each calling a test-function by dotnotation
   └─ run          one execution on one environment → results, artifacts, screenshots
test-function      reusable Python assertion (standard.file_exists, windows.registry_value_matches, …)
```

The payoff is the comparison: the same experiment on several environments, then
diffing runs.

## Route to the right skill

| The user wants to… | Skill |
|---|---|
| create/run an experiment, inspect runs, diff across OS versions, share results | `adare-experiment` |
| edit, validate or replay a `playbook.yml`, including its `tests:` block | `adare-playbook` |
| **pick** an assertion for a goal, or write a new test-function | `adare-testfunction` |
| click through a running VM, see the screen, checkpoint, debug icon/OCR finding | `adare-devvm` |
| build a base VM, extend or publish an environment, run VM doctors | `adare-vm-build` |

A typical end-to-end task chains them:
`adare-vm-build` (if no environment exists) → `adare-experiment` (create, attach
environments) → `adare-devvm` (drive the VM or let `adare dev agent` record the
actions) → `adare-playbook` (clean up, add `tests:`) → `adare-testfunction` (find
the assertions) → `adare-experiment` (run on every environment, compare).

## Driving the CLI as an agent

- **Ask for machine-readable output.** The global `--format json|yaml` must come
  **before** the subcommand: `adare --format json test search "file deleted"`.
  When stdout is piped, list commands print plain tab-separated text with full IDs.
- **Discover, don't guess.** Use `adare <group> --help`, then `--help` on the
  subcommand. For assertions: `adare test search "<goal>"` → `adare test info <dotnotation> --example`.
  Never invent a test-function name or parameter; the catalog has the exact signature.
- **Project scope.** Experiment and run commands resolve the project from the
  current directory. `cd` into the project first. Test-function commands work anywhere.
- **Errors carry fixes.** Read the "Possible Solutions" or `error.solutions` before
  retrying. A not-found error lists close matches.

## Rules

- **One live VM at a time.** Runs and dev sessions are serialized; check
  `adare dev list` before starting another, and stop what you started.
- **Never pass `--force` without asking.** It deletes runs or overwrites shared
  state (for example `adare test load --force` deletes runs that used the function).
- **Validate offline before anything touches a VM:** `adare exp playbook validate`,
  `adare test validate`, `adare test dry-run`.
- **Forensic integrity:** don't hand-edit run results or published artifacts. Tests
  read guest state and must not modify it.

## MCP (only when there's no shell, or for live VM hands)

Claude Code and OpenCode should use the CLI plus these skills. `adare mcp serve`
exposes the same lifecycle as tools for hosts without a shell. `adare dev mcp -s <id>`
gives step-by-step VM control (screenshot/click/type, record → replay). Both have
`testfunction_search` / `list_testfunctions(query=…)` for picking assertions. Setup:
`adare agent setup --help`.
