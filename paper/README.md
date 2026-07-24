# Paper artifacts

Companion artifacts for the ADARE paper. §5 states that all case-study experiments,
"including their playbooks and environments, are available on GitHub" — this directory is
that claim, and this file is the map from each paper section to the files backing it.

- `experiments/` — one directory per case study, one experiment directory per run
- `demo/` — the two minimal demo playbooks and screen recordings referenced by the
  paper's footnote 5 and Appendix C (`playbook_ubuntu2204.yml`, `playbook_windows11.yml`)

## Section → directory map

| § | Case study | Directory | Experiments | Environments |
|---|---|---|--:|---|
| 5.1 | Explorative Artifact Research | `experiments/1_artifact_research/playbooks/` | 7 | `ubuntu-1804`, `ubuntu-2004`, `ubuntu-2204`, `ubuntu-2404`, `fedora-41`, `fedora-42` |
| 5.2 | Artifact Regression Testing | `experiments/2_artifact_regression_testing/` | 7 | `ubuntu-2004`, `ubuntu-2204`, `ubuntu-2404`, `kubuntu-2004`, `kubuntu-2204`, `kubuntu-2404`, `fedora-42` |
| 5.3 | Tool Validation of PECmd | `experiments/3_tool_validation/pecmd/` | 1 | `win11` |
| 5.4 | Autopsy Tool Regression Testing | `experiments/4_autopsy_tool_regression_testing/` | 24 | `win11-autopsy-solr4`, `win11-autopsy-solr8` |
| 5.5 | Cross-Tool Validation | `experiments/5_cross_tool_validation/` | 3 | `ubuntu24043`, `win11` |

Each case-study directory has its own `README.md` with the claim-to-assertion mapping, the
prerequisites, and the caveats specific to that study. Start there.

## What is deliberately not shipped

Nothing here is a placeholder — each omission has a reason and a documented route to
obtaining the missing piece.

| Artifact | Section | Why | Route |
|---|---|---|---|
| The three malicious LNK samples | 5.5 | Redistributing malware from a public research repository is not appropriate — the same argument §6 makes about unshareable evidence. | Appendix-A SHA-256 hashes plus VirusTotal retrieval instructions in `experiments/5_cross_tool_validation/provisioning/README.md`. A generator for benign stand-ins that reproduces the measured behaviour split ships alongside. |
| `2020JimmyWilson.E01` | 5.4 | NIST CFReDS disk image, far too large to commit. | <https://cfreds.nist.gov/> → the project's `shared/data/`. |
| All VM images | all | Multi-gigabyte disk images. | Built from OS profiles + `adare vm create` / `adare env extend`; §5.4's build runbook is in `experiments/4_autopsy_tool_regression_testing/provisioning/README.md`. |
| Autopsy 4.22.0 | 5.4 | **Not a gap.** 4.22.0 is Figure 2's "Missing Version (X)" column — the version whose release notes the paper consulted, not one it ran. 24 playbooks + X = the figure's 25 columns. | — |
| LECmd, PECmd binaries | 5.3, 5.5 | Third-party tools, provisioned into the environments' shared tools rather than vendored. | <https://ericzimmerman.github.io/> |

## Missing OS profiles — the main barrier to a full replication

§5.1 and §5.2 name distributions that have no OS profile in `adare/appdata/os-profiles/`
yet, so those environments cannot be built today. Present: `fedora41`, `kubuntu2404`,
`ubuntu2204`, `ubuntu2404`, `ubuntu2510`, `ubuntu2604`, `windows10`, `windows11`, plus
arm64 variants. **Absent: `ubuntu1804`, `ubuntu2004`, `kubuntu2004`, `kubuntu2204`,
`fedora42`.**

The playbooks name those environments anyway, because the environment list *is* the
paper's claim and a playbook that quietly narrows its scope to whatever happens to be
installed is worse than one that names what it needs. Creating those profiles and images
is a separate task; each case-study README lists the specific profiles it is waiting on.

## Environment naming

§5.1 and §5.2 use hyphenated `<distro>-<version>` names (`ubuntu-2404`, `kubuntu-2204`,
`fedora-42`). §5.3 and §5.5's Windows experiment use the paper's plain `win11`. §5.4 uses
the two real provisioned environment names, `win11-autopsy-solr4` / `-solr8`.

**One unresolved collision:** §5.5's two Linux experiments name `ubuntu24043` — the form
used in `docsrc/source/guide/experiments.rst` and in the Autopsy metadata before this
change — while §5.2 names the same OS `ubuntu-2404`. Both spellings predate this work and
picking a winner is an environment-registry decision, not a documentation one, so both are
left as they are and flagged here. Whichever is adopted, the other case study's
`metadata.yml` files need the matching edit.

Registered environments on a given host will not necessarily match any of these names —
run with an explicit `--environment` when they differ.

## Verification status

Everything here is statically validated: every `playbook.yml` parses under
`adare experiment playbook validate`, and every `metadata.yml` structures cleanly into
`ExperimentMetadata`. Beyond that, each case-study README states exactly which assertions
were executed against real tool output on a host and which still need their first VM run.
Two known limits are worth reading before trusting a green result:

- `adare experiment playbook validate` does **not** reject unknown keys nested inside
  action bodies (the strict per-class cattrs hooks are registered on the outer converter,
  but `_validate_attrs_class` structures with a fresh converter that lacks them). A
  passing validation is necessary, not sufficient. An illegal `pull: name:` had been
  sitting in §5.2 unnoticed because of this; it is fixed.
- `adare testfunction dry-run` currently cannot run any test function whose parameter is
  union-typed (`json.value_matches`, `jsonl.line_matches`, …) — `cattrs` has no structure
  hook for `str | int | float | bool | None`, so the CLI raises
  `StructureHandlerNotFoundError` before the test executes. The test-function contracts
  here were therefore verified by invoking the functions directly rather than through
  that CLI.

Neither is a defect in these artifacts, but both change how much a clean validation run
proves, so they are recorded here rather than left for the next person to rediscover.
