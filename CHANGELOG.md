# Changelog

All notable changes to the ADARE workspace. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/) per package.

## Versioning policy

Each workspace package (`adare`, `adarevm`, `adarelib`, `adare-cv-server`) has its
own version in its `pyproject.toml`. While below 1.0, a **minor** bump marks a
breaking change and a **patch** bump everything else.

`adarelib` needs the most care: guests keep the `adarelib` they were provisioned
with, while testfunctions are uploaded fresh on every run. So:

- Anything a testfunction may rely on (decorator kwargs, `TestResult`, context
  API) is additive only within a minor series.
- Bump the `adarelib` minor version when that contract changes, and note under
  the release which guests need re-provisioning.

Agent wheels are built as `<version>+g<hash12>` of their sources, so a run
reinstalls `adarevm`/`adarelib` in the guest whenever their code changed; the
version above is still what marks a contract change.

Add entries under **Unreleased** as you go; on release, rename it to the version
and date, and tag the commit `<package>-v<version>` (e.g. `adarelib-v0.2.0`).

## [Unreleased]

### Added
- `adare db compact [--dry-run] [--all] [-p PROJECT]` shrinks project databases
  that grew from the base64 screenshot copies older action results kept in
  `action_execution.result_data` (47 GB of a 50 GB database in one project). A
  copy is dropped only when the PNG its `screenshot_path` names is on disk with
  the image's size; rows whose screenshot file is missing stay unchanged and are
  reported as kept. The database is then vacuumed when there is free space of at
  least its size. Refuses to run while another process writes to the database;
  `--dry-run` opens it read-only and reports the reclaimable bytes.
- `adare db check [--all] [-p PROJECT]`: read-only `quick_check`,
  `foreign_key_check` summary and orphaned-row counts per database; exits 1 when
  a database is corrupt. Both commands take `--json`.
- `adare runs prune [--fake] [--older-than DAYS] [--yes] [--json]`: frees disk space
  in the current project's `run/` directory. A dry run by default: lists run folders
  no database run (and no dev session) refers to, with sizes and a total. `--fake`
  also targets fake runs that are not running (rows + folders), `--older-than`
  filters by age, and only `--yes` deletes. A folder is only ever selected when it
  is clearly an ADARE run folder: `run/<known experiment>/<run timestamp>` inside
  `run/` with no symlinks, with a `logs/` or `reporting/` subdirectory, unchanged for
  an hour; users' own files in `run/` are never listed.
- Terminal and Claude in the web UI: a terminal panel on every page (sidebar or
  Ctrl+`) runs Claude Code or a shell in a chosen project, as tabs that survive
  page changes and reloads. *Build with Claude* (experiments), *Work on it with
  Claude* (experiment) and *Debug with Claude* (run) start Claude with the task
  set. Terminals only accept requests from this machine (loopback client, local
  `Host` and `Origin`).
- Host resources and run capacity. The web UI has a **System** page (and host tiles
  on the home dashboard): live CPU, memory and disk, every running VM, how many
  more runs of each environment fit right now and what limits them, usage history
  charts, and where the disk space goes, including run disks without an owner that
  `adare vm prune` can reclaim. `adare system resources|capacity|usage|storage`
  report the same. Every experiment run now records what its VM used (peak RAM,
  CPU, disk), and the capacity estimate is sized from those measurements.
- VM images have a record: `adare vm create` registers the disk at once and writes
  `<disk>.image.yml` (install method, OS profile + hash, ISO + SHA256, setup level,
  ADARE version/commit, QEMU version, date) and the guest's package list
  `<disk>.packages.txt`; `adare vm test` adds its result; `adare vm info` shows it.
- `adare vm publish <image> --vm-url <url>` records where an image is hosted;
  `adare env publish-prepare` embeds the image record as `image:` in the
  environment file, and `adare env load` adopts it (and takes `os` from it).
- Every experiment run records the SHA256 of the disk it booted (run row and
  `forensic_log.yml` `vm_sha256`) and writes `image.yml` (environment version and
  image record) into the run directory.
- `adare vm create` for `install_mode: playbook` profiles draws a live status
  block in the terminal: current step, elapsed time, OCR attempt or screen text.
  `--display` now also applies to playbook installs and shows the VM in a QEMU
  window to watch (headless stays the default; a window that cannot open falls
  back to headless).
  The scrollback keeps one line per step with its duration, retries and
  screenshot instead of a line per `click_text` retry. A `click_text` that fails
  reports the text that was on screen; QEMU's output goes to
  `<vm>_playbook/qemu.log`.
- Quality ratchet (`scripts/quality_ratchet.py`, `quality-baseline.json`): ruff
  and mypy violations plus files over 1000 lines are budgeted and may only shrink.
- CI `lint` job (format, strict mypy on `adare.core`, ratchet), weekly
  `pip-audit` workflow, Dependabot, and a coverage summary on the unit job.
- Pre-commit hooks (`make hooks`): ruff-format, ratchet, gitleaks, file checks.
- `make test`, `lint`, `lint-fix`, `lint-baseline`, `typecheck` targets.
- Import smoke test covering every host-package module.
- MIT license (Fraunhofer FKIE); `THIRD_PARTY_NOTICES.md` lists the NVIDIA-derived
  grounding server, which is excluded from it, and the bundled RBCmd.exe (MIT).
- `ADARE_HOME` relocates the whole state directory (default `~/.adare`); the unit
  suite runs against a temp dir and never touches the real one.
- `ADARE_FORWARD_BIND` sets the host address VM port forwards listen on.
- `ADARE_MCP_PORT` sets the `adare mcp serve --transport http` port.
- Guest agent test suite (`adarevm/tests`, `make test-agent`) run on Python 3.10
  in CI on Linux and Windows; a non-blocking CI job runs the CV server tests.
- `adarelib.testset.compare`: row/column comparison, diff report, nested lookup
  and placeholder helpers shared by the csv/excel/json/jsonl/xml collections.
- Guest agent protocol 2 (`adarevm`/`adarelib` 0.2.0): the agent requires the
  run's token (`agent_token` in `config.json`, sent as `Authorization: Bearer`),
  opens every connection with a `welcome` carrying `protocol_version`, versions
  and tools, and serves exactly the `Tool` enum. The host rejects other protocol
  versions (reinstalling the agent once first) and only calls advertised tools.
  `adare debug ws action` / `adare icons dump-all` take `--token` / `ADARE_AGENT_TOKEN`.
- `adare vm test` writes a debug log to `./adare-vm-test-<target>-<timestamp>.log`
  and prints its path at the end, failures included. `--log-file` picks the path,
  `--no-log` turns it off, and an existing global `--logfile` is used as is.
- `adare vm create` for `install_mode: playbook` profiles (Ubuntu 18.04–24.04,
  Kubuntu 20.04–24.04) now makes the installed desktop ADARE-ready for
  `--setup base`/`full` (the default): it installs `qemu-guest-agent` from a text
  console, then over the agent sets passwordless sudo, automatic login, no idle
  lock/blanking, no first-login wizard and no background apt updates (`full`:
  `python3-pip` + `uv`), reboots and checks the agent and the autologin session.
  Any failed step fails the build with a screenshot. Profiles can override the
  console part with `bootstrap_steps`. Before, these images had no guest agent,
  so `adare vm test` and experiments waited on it until every boot retry was spent.
- Every unattended `adare vm create` (autoinstall, preseed, kickstart, AutoYaST,
  Windows autounattend) ends with a readiness pass for `--setup base`/`full`: the
  finished disk boots once, the guest agent must answer, Linux desktops get no
  idle lock/blanking (GNOME, Plasma 5/6, Xfce) and no first-login wizard, and
  after a reboot the `adare` autologin session must exist (Windows: checks only).
  A failure fails the build and keeps the installed disk;
  `<disk>_readiness.log` has every command. Recipe base disks get it too.
- Manual Linux installs (`install_mode: manual`) get the same setup as playbook
  installs after you finish: ADARE logs in as `adare`/`adare` on a text console,
  installs `qemu-guest-agent` (apt, dnf, zypper or pacman), provisions over the
  agent and checks it after a reboot; a failure only warns. NixOS gets the
  `configuration.nix` lines instead. Autologin now also covers LightDM (Mint,
  elementary) and picks the display manager that is actually enabled.
  `--setup bare` skips all in-guest setup for every install mode.
- A Linux guest that boots but whose guest agent never connects now fails after
  the first boot attempt with "guest agent never connected, although the guest
  finished booting" and a screenshot, instead of a bare timeout after three cold
  boots (~19 min). The guest's screen sitting still for a minute is what tells it
  apart from a slow boot.
- Image targets honour the offset `base` (`top-left`, `center-left`, ...) like text
  targets: the box comes from the new `sizes` field of `find_icon` (or the
  template's native size). `center` (the default) is unchanged. Image and icon
  candidates below the confidence floor are dropped before the strategy runs, and
  `target.min_margin` (0.0-1.0) accepts a match only if it beats the best other
  above-floor candidate by that margin.
- `click` takes `verify: {exists|not_exists: <target>}`, `retries: n` (default 0)
  and `verify_timeout` (seconds, default 3): after the click the condition is
  polled; if it does not hold the target is re-resolved and clicked again, up to
  `retries` more times, and the action fails if the effect never appears. Without
  `verify` a click behaves exactly as before.
- `ADARE_CLICK_SETTLE_MS` sets the QMP pointer-move-to-press gap (default 10 ms,
  the previous fixed value).
- Evidence on a failed action: screenshot of the last search, a fresh screenshot,
  the full OCR dump and the target description(s) are written to
  `<run>/reporting/failure/aNN_*` (switch off with `ADARE_FAILURE_EVIDENCE=0`).
- Playbook-level `on_failure:` action list: runs once after the first failure that
  stops the playbook and before the run ends; never changes the failed status.
  Accepted by `adare exp playbook validate` and validated like normal steps.
- Cross-process VM slots (`adare.backend.vm.slots`): `N` flock files under
  `<appdata>/vm_slots/` cap the live VMs across all `adare` processes (N =
  the `ADARE_MAX_VMS` setting, default 20, the
  old per-VM instance limit). Every run's VM (QEMU run instance or pooled
  VirtualBox instance) takes one slot before it boots (waits up to
  `ADARE_VM_SLOT_TIMEOUT`, default 30 s) and keeps it until the run is removed or
  the instance released, so parallel runs cannot exhaust host memory; the kernel frees a crashed
  process's slot. `adare vm slots status [--json]` shows the slots;
  `adare vm slots exclusive [--timeout s] -- <cmd>` runs a command holding every
  slot (its adare child processes run under that lease). A slot belongs to the
  allocating process, so a VM that outlives it (detached dev session) stops counting.
- `adare dev remove --stopped [--older-than 14d] [-y]` removes stopped dev
  sessions in bulk, listing each with the VM disk it keeps (on this host 25
  forgotten sessions held ~164 GiB). `adare vm prune` reports that space too.
- `adare system settings list|get|set|unset`: host limits saved in
  `~/.adare/settings.json` (`ADARE_MAX_VMS`, `ADARE_VM_SLOT_TIMEOUT`,
  `ADARE_MIN_FREE_DISK_GB`, `ADARE_DEV_SESSION_MAX_AGE_DAYS`), each resolved
  environment variable > saved setting > default and validated when set.
- Opt-in expiry of forgotten dev sessions: with the `ADARE_DEV_SESSION_MAX_AGE_DAYS`
  setting, every experiment run and `adare vm prune --force` remove stopped/crashed
  sessions unused for longer than that (never running ones, never one whose VM is
  up, never from inside a dev session). Off by default.
- Runs refuse to start when a filesystem they write to has less than
  the `ADARE_MIN_FREE_DISK_GB` setting free (default 10 GiB, 0 disables), with the cleanup
  commands as suggestions, instead of filling the disk mid-run.

### Changed
- `adare runs remove`, `DELETE /api/runs/{ulid}`, `adare experiment clean` and
  `adare experiment remove` also delete the run folders of the runs they remove,
  through the same run-folder safety test as `runs prune` (a refused folder is kept
  and reported; the rows are deleted anyway). Database run paths are matched by
  their `run/<experiment>/<timestamp>` tail, so moved projects still match.
  `runs remove --keep-files` (web: `keep_files=true`) and `experiment remove
  --keep-files` keep the files. The automatic fake-run cleanup after a test run
  still removes only the rows; `runs prune` collects those folders.
- SQLite databases now use write-ahead logging (`journal_mode=WAL`) with
  `synchronous=NORMAL` and a 30 s busy timeout (was 5 s), set on every connection:
  readers no longer block a writer, so the CLI, web UI and a running experiment can
  share a database without `database is locked`. WAL is recorded in the database
  file, which gains `-wal`/`-shm` sidecar files next to it. Foreign-key enforcement
  stays off. See *Connection settings* in the database migrations docs.
- Development tasks have one definition: CI runs the Makefile targets (`make lint`,
  `make test`, `make test-agent`, …) instead of its own copies of the commands.
  Every target syncs what it needs first (`--inexact`, so it never strips the
  qemu extra or the CV server from `.venv`); new: `make sync` (use instead of
  plain `uv sync`), `make test-testfunctions`, `make test-cv`, and `make test`
  takes `PYTEST_ARGS=...`. `make test-agent` now also works on Windows.
- CI tests guest code on the guests' Python: the testfunction tests also run on
  Python 3.10 (`make test-testfunctions-guest`, Linux + Windows), next to the
  agent suite, in one venv (`.venv-guest`, replaces `.venv-agent`) pinned by
  `requirements-guest-test.txt` (`make lock-guest` re-pins it).
- CI also runs `make install` + `make update` on Linux, macOS and Windows
  (`make test-install`), the unit suite on macOS, and builds the docs on every PR.
  `make docs` treats Sphinx warnings as errors.
- The unit suite has a coverage floor (`make test-cov`, 39%); the CV server job
  now blocks merges; `make lint` runs mypy once (the ratchet fails on any error in
  `adare.core`). Pushes to dev/main no longer cancel each other's CI runs.
- `make install` / `make update` install exactly what `uv.lock` pins (`--locked`)
  and stop at the first failing step instead of carrying on. They no longer need
  a system Python (uv provides 3.13), work from any directory, and never remove
  extras you added. The installation guide gained an *Updating* section.
- Images never change. A different disk under a registered name is a new image:
  `--force` (`vm create`, `env load`) keeps the replaced image as
  `<name>-<sha12>` for the environment versions that use it, or removes it when
  none does. A recipe image whose disk is missing is no longer rebuilt silently
  during a run (the rebuild has other bytes); the run says to reload with
  `adare env load --force`, which makes it a new environment version.
- `adare env load <name>` finds the registered environment's file; a `name:` key
  that differs from the file name is reported as ignored; a disk is hashed once
  per load.
- OS profiles: a YAML profile is now the only definition of its OS. The 12
  built-in catalog entries that a shipped profile replaced (never used, several
  stale) are gone; a test keeps it that way, and another requires every x86_64
  Ubuntu/Kubuntu LTS profile to install the desktop edition. The VM image guide
  records when each profile last ran.
- `adare vm test` on a registered (QEMU) VM now gives the guest its agent the way
  an experiment run does: the same agent wheels, shares and `config.json` with the
  agent token, the same install and launch, and the same WebSocket connection
  (retries, guest diagnostics). The agent starting and answering now decides the
  verdict, since experiments run their tests through it; before, the test started
  adarevm its own way and its failure did not count. A failed test keeps its run
  directory with adarevm's logs under `~/.adare/state/vm-test/run/`.
- CLI commands renamed or moved to the group they belong to. The old names
  still work (hidden from `--help`) and print the new name on stderr:
  - `adare run list/info/remove` -> `adare runs ...` (no longer looks like
    `adare experiment run`)
  - `adare agent setup/status` -> `adare skills install/status` (no clash with
    `adare dev agent`)
  - local web UI: `adare web start/services/build/install-spice` ->
    `adare ui start/status/build/install-spice`; `adare web` is now only the
    ADARE Web platform (login, download, publish, submit)
  - `adare cv ...` / `adare ws ...` -> `adare debug cv ...` / `adare debug ws ...`
  - `adare os-profile` -> `adare vm profile`, `adare vm gui-doctor` ->
    `adare vlm doctor`, `adare dev grounding-pull` -> `adare vlm pull-grounding`
  `adare vlm rm` is now `adare vlm remove` (`rm` stays an alias, `l` joins `ls`),
  and `adare experiment run` accepts `-p` for `--project` like its siblings.
- `adare vm remove <name-or-id>` removes what `adare vm list` shows: a registered
  VM (with the environments that run on it, after showing what goes and asking;
  `-y` skips the prompt) or a VM instance, by name or ID. It refuses while an
  instance is running, and never removes a VM that another version of one of
  those environments runs on. `--id` still works. Usage errors now exit 2.
  `vm prune` lists registered VMs no environment uses (it does not delete them).
- `vm reset`, `vm remove --env` and their prompts now say what they do: remove
  instances. Registered VMs were never deleted by them.
- `env remove` refuses without `--force` when a registered project cannot be
  checked for references, and deletes exactly the versions it checked.
- `env load --force` on an unchanged file whose disk is unchanged no longer adds
  a duplicate environment version.
- VM snapshots (`SnapshotManager`) are VirtualBox-only; QEMU runs have no
  instance to snapshot.
- `adare vm` help separates registered VMs (`list`, `info`, `reset`) from
  instances (`usage`, `remove`, `snapshot`, `prune`); `vm create` no longer
  suggests `--no-copy` for a disk already in managed storage.
- A run fails early when its environment and VM disagree on the hypervisor
  (possible for environments loaded before the load-time check).
- `--preserve-snapshot` on a QEMU run warns that it is VirtualBox-only and points
  to `--export-disk-image` instead of silently doing nothing.
- QEMU runs no longer copy the environment disk into a pooled instance (a full
  `qemu-img convert`, ~12 GB, per instance). Each run boots a throwaway overlay
  directly on the read-only environment disk with its own UEFI varstore, domain
  config and domain UUID, all removed when the run ends; runs of one environment
  are independent and can run concurrently. Non-qcow2 disks are converted once.
- The QEMU vTPM is per run: every run boots a copy of the environment's vTPM
  template (adopted from the previously shared vTPM, or manufactured once), so
  the TPM identity stays stable but no run inherits another run's TPM changes.
- The run-time disk integrity check hashes the full disk only when it changed
  since its last verification (size/mtime/ctime/inode, cached under
  `~/.adare/state/disk-digests/`); managed disk copies are read-only on POSIX.
- VM instances record their owning process (`owner_pid`, migration
  `add_owner_pid_to_vm_instance`). Instances of crashed runs are reclaimed by the
  next QEMU run and `adare vm prune`, which also removes pooled QEMU instances
  left from before per-run overlays; a live run's instance is never touched.
- `adare vm remove --all` / `--env` remove instances, as documented; they used to
  delete the VM registrations and break every environment using them (`adare vm
  reset` remains the command for that).
- Environments are versioned. `adare env load --force` on a changed file adds a
  new version and keeps the old one with its runs; it used to delete the old
  environment and every run of it in every project. `env remove` deletes all
  versions, and `--force` now detaches experiments instead of leaving them
  pointing at a deleted environment. Migration `add_environment_versioning`.
- An environment without `hypervisor:` infers it from the disk (VirtualBox for
  OVA/OVF/VDI/VMDK, QEMU otherwise) instead of always defaulting to VirtualBox.
- `env load` refuses a disk-image environment without an `os` block, a
  `vagrantbox`-only environment, and a local disk that does not match a declared
  `vm_sha256` (only URL disks were checked).
- Environments sharing one disk must agree on its hypervisor and guest
  platform/architecture; `--force` refuses to replace a disk another environment
  uses, and a run fails if its environment's disk was replaced after loading.
- `env create --with-vm` writes the disk path into the new file instead of
  registering the disk (`env load` does that).
- `-p` is hidden on the environment commands that ignored it (environments are global).
- Whole workspace formatted with `ruff format`; safe ruff autofixes applied.
- `uv.lock` is committed; CI installs with `--locked`.
- ruff and mypy pinned exactly in a `lint` dependency group.
- Built-in testfunctions report an unexpected exception as ERROR (they used to
  catch everything; Excel read errors even became FAILED). Unreadable workbooks
  and uninterpretable placeholder values still fail the test.
- Sphinx output is no longer committed: `make docs` builds to
  `docsrc/build/html` and the docs workflow publishes it; `docs/mcp-clients.md`
  moved to `docsrc/mcp-clients.md`, design notes to `docsrc/design/`.
- `adare mcp serve --transport http` defaults to port 13112 (was 13111, which the
  LocateAnything grounding server also uses).
- Guest agent wheels carry a content-hash version (`0.1.1+g<hash12>`); guests
  provisioned with a plain `0.1.1` reinstall the agent once on their next run.
- `make install`/`update` copy only what ADARE reads at runtime into
  `~/.adare/adare` and prune everything else (an existing copy shrinks from
  several GB to ~10 MB on the next `make update`).
- Importing `adare.config.configdirectory` no longer creates directories; the CLI
  and web API create them at startup.
- New `adare.services` functions must be fully typed (mypy override restored).
- Database APIs share one engine per database file and set the schema up once
  per process; nested `with api:` blocks join the outer transaction.
- Web API handlers run services off the event loop (threadpool / `to_thread`).
- Mixins declare their host for type checking (`QEMUVMHost`, `VirtualBoxVMHost`,
  `ActionsExecutorCore`, DB API hosts): ~720 fewer mypy errors.
- Fewer fixed waits on the VM path: guest-agent polls back off from 50 ms instead
  of a flat 0.5 s (≥0.5 s saved per guest command), the agent connection probes
  the real WebSocket handshake instead of sleeping 3 s (6 s in `vm test`), dev
  snapshot create/restore run off the event loop, and host-mode screenshots skip
  a 0.1 s settle and encode PNGs faster (level 1: same pixels, ~1.5x larger files).
- Downloads stream 1 MiB chunks into `<file>.part` and are renamed into place
  only when complete, hashing as they go; the sha256 check after an ISO/VM
  download no longer re-reads the file.
- Installer ISO / downloaded VM digests are cached in a `<file>.sha256` sidecar
  (size, mtime, inode); `vm create` and `env load` re-hash only a changed file.
- Faster startup: pandas, requests/aiohttp, trogon and the OS-profile catalog
  load on first use (`import adare.run` ~98 -> ~44 ms, DB commands ~-160 ms);
  `load_catalog()` is cached until a testfunction source changes.
- cv-server: `find_icon` runs off the event loop and decodes its inputs once
  per request; OCR calls share one executor (they queue instead of running
  concurrently on the shared PaddleOCR instance).

### Fixed
- `adare db reset` and `adare db clean-install` deleted only the main database
  file and left its `-wal`/`-shm`/`-journal` files behind, which could corrupt the
  next database created under that name; they now remove all of them. Removing a
  project closes its pooled database connections before deleting the directory.
- Deleting runs left rows behind in the project database: every run delete
  (`adare runs remove`, `adare experiment clean`, `adare experiment remove`,
  fake-run cleanup after a test run, `adare environment remove --force`, and
  replacing an in-use testfunction) kept the run's action executions (with their
  result blobs), its run-files row and its two log-file rows, because foreign keys
  are off in SQLite and the ORM cascade does not reach them. All of them now go
  through one `delete_runs` helper that removes these rows too. A project
  migration (`delete_orphan_run_rows`) deletes what earlier deletions left; dev
  session action executions (no run) are kept. The freed space is reused by the
  database but the file only shrinks after a vacuum.
- Replacing an in-use testfunction with `--force` said it deleted the runs that
  used it but deleted none: it searched the global database, while runs live in
  each project's database. It now deletes them in every registered project.
- `adare runs list` took ~150 s on a project with 4.5k runs and now takes under a
  second: every run's verdict lazy-loaded all of its events through an unindexed
  column. Verdicts are now read for all runs in two queries (also in the web UI's
  run list), and a migration indexes the columns that look up a run's events,
  stages, action executions and playbook items. `adare runs info` loads only the
  requested run instead of every run of every project.
- `adare runs list` inside a project registered under a name other than its
  directory's (e.g. `T2F` at `.../adare`) listed no runs; it filters by the
  registered name and no longer reads the other projects' databases.
- The same directory-name-instead-of-registered-name mixup also affected
  experiment/environment dotnotations resolved from the current directory and
  the "current project" used to shorten names in experiment, environment and
  testfunction listings. All of them now resolve the registered name through one
  helper, `adare.backend.basics.registered_project_name` (falling back to the
  directory name for an unregistered directory).
- Database read helpers (`safe_query_*`, `safe_count`, `safe_get_*`), the global
  reference manager and the current-project lookup caught every exception, so a
  programming error looked like a missing row or an empty listing. They now turn
  only the expected database errors (SQLAlchemy, sqlite3, the database API's own,
  `OSError`) into their default and let anything else propagate.
- Removing a dev session (or any old pooled QEMU instance) whose VM config was
  already gone deleted only its database rows and left its full disk copy
  (`<name>-base.qcow2`, ~4-50 GiB) behind; the copy is now removed by name. The
  removal also no longer warns "Could not restore websocket_port" per session.
- Two runs started at the same moment can no longer get the same CV/OCR server
  port: `find_free_cv_port` also reserves the port with a lock file until the
  server stops. VirtualBox experiment snapshots are named after the random tail
  of the run ULID, not its timestamp, so runs started together no longer collide.
- A crashed or killed run (`kill -9`, closed terminal, interrupted session) no
  longer leaves its QEMU VM running with its RAM until the next run or
  `adare vm prune`: the first QEMU run of a process starts a small reaper that
  waits for the process to exit and then removes its leftover runs
  (`reconcile_instances`; other processes' runs and dev sessions are untouched).
- A crashed or killed run no longer leaves its CV/OCR server running (up to
  ~1.6 GB each, holding its port): runs start it with the new
  `adare-cv-server --exit-with-parent`, which exits once its `adare` process is
  gone. Dev-session servers keep outliving the CLI as before.
- `adare exp run`'s result summary (`--output json/yaml/...`) reports the run's
  real duration and start/end time instead of 0.0, and a failed run says
  "Experiment failed" instead of blaming the tests.
- `adare vm slots status` reports the configured `ADARE_MAX_VMS` as the total
  instead of the number of slot files on disk.
- Two runs of the same experiment started in the same second no longer fail with
  "Failed to create run directory structure ... File exists": the second run
  gets `<timestamp>_2` (also for diff runs).
- Project databases no longer fill up with screenshots: each action's result was
  stored with its base64 screenshot inline (~170 KB per action, one project
  reached 47 GB). Image payloads and strings over 16 KiB are now replaced by a
  size marker; explicit screenshots stay on disk under `reporting/screenshots`.
- The web UI's live VM view runs on the current VirtualSpice (with `vspice`,
  MCP and one server per data dir): `adare ui start` gives its VirtualSpice its
  own data dir (`~/.adare/virtualspice`), so it no longer fails while the
  VirtualSpice app is open and ADARE's run VMs stay out of its library; reuses a
  VirtualSpice already answering on the port; skips VirtualSpice builds too old
  for this; says why VirtualSpice did not start; writes its output to
  `~/.adare/virtualspice/adare-server.log` (an unread pipe could fill and freeze
  it). `--spice-port` now also moves the viewer and `adare vm watch` lookup,
  which were fixed to 8081. Clicking and typing in the viewer needs a
  VirtualSpice with the input fix (mouse message ids, key releases).
- VMs with shared folders start on libvirt 10.0 and newer (e.g. Ubuntu 24.04):
  defining the domain failed with "invalid idmap start/target/count settings".
  The virtio-fs `<idmap>` used attributes libvirt does not have; older libvirt
  ignored the element, so it is now left out and shares behave as before.
- The Windows installer (`install.ps1`) works with the single workspace `.venv`
  again: it found no `adare.exe` and stopped. It now also puts the CLIs on your
  user `PATH`, migrates the database and syncs testfunctions like the Linux/macOS
  installer, and doubles as the Windows update (`make update`).
- `vm create windows11` (x86_64) failed right after boot with "Windows
  installation encountered an unexpected error. Error code: 0x80070103 - 0x40031"
  on current media (WinPE 26100): Setup aborts on answer-file driver paths that
  do not exist, and the answer file guessed 24 of them on drives D: to J:. The
  virtio disk driver now rides on the Autounattend floppy (A:) and is loaded from
  there only. The answer file also selects an edition (generic Pro key, no
  activation), so multi-edition ISOs no longer stop at the product key screen.
- A Windows Setup error dialog now stops `vm create` within a minute, with the
  error text in the message and a `<vm>_setup-error.png` screenshot next to the
  disk, instead of waiting out the 90-minute install timeout.
- The readiness check of a new Windows VM failed at its first step ("provision
  step 1/2 'reboot' did not complete: guest-exec transport error: timed out"):
  the first `guest-exec` after boot took 13 s to answer, past the 10 s every agent
  call allowed (launches and status polls now get 60 s), and the step would then
  have run `/bin/bash` in the Windows guest (it runs PowerShell there now).
- x86_64 Windows VMs (`windows10`, `windows11`) could not mount ADARE's shares on
  a Linux host: `virtiofs.exe` needs WinFsp, which the answer files never
  installed, so `C:\adare` stayed empty and the agent could not start. WinFsp 2.1
  is installed at first logon now (`--setup base` and up).
- Windows answer files installed the *latest* Miniforge, and 26.9.4-0
  (2026-10-22) ships a conda whose `create` fails on Windows ("Could not find
  'share/conda-launchers/cli-64.exe'"), leaving an empty `pyadare` env. Miniforge
  is pinned to 26.7.2-0.
- The agent installer took a missing `pyadare` conda env on Windows for an
  existing one (`if ($?)` after `| Out-Null` is always true), so its recovery
  `conda create` never ran.
- `vm create` now checks x86_64 Windows guests for WinFsp and, with `--setup
  full`, a working `pyadare` Python before calling the VM ready.
- `ubuntu2604` installs the genuine desktop edition from the 26.04.1 desktop ISO
  by playbook, like `ubuntu2404`, including 26.04's new "Encryption and file
  system" screen. It used the server ISO with a desktop source the server ISO
  does not carry, so it could not install at all.
- Ubuntu 26.04 guests opened a "Welcome to Ubuntu 26.04" wizard over the desktop
  on every login: its per-release welcome (a systemd user unit, not autostart)
  runs once the initial-setup done marker exists, which provisioning writes. The
  release's own stamp is now written too.
- An unattended Linux install whose installer failed (subiquity's "An error
  occurred. Press enter to start a shell", a failed curtin step, ...) is now
  stopped within seconds instead of waiting out the 150-minute install timeout.
  For a crashed subiquity, ADARE opens the installer's rescue shell over the
  serial console and puts its traceback into the install log and the error.
- The Ubuntu rolling autoinstall template (`ubuntu2510`, `ubuntu2604arm64`)
  asked for the `ubuntu-desktop-minimal` source, which server ISOs do not carry,
  so subiquity crashed before installing anything. The desktop now comes from
  the package list, as in the LTS template.
- `adare vm test` on Linux guests hung at "Starting AdareVM server" until the
  300 s guest-command timeout and then failed: the backgrounded launch kept
  the guest agent's output pipe open for as long as adarevm ran.
- Bullet lists and examples in command help (`experiment run`, `env load`,
  `vm test`, ...) were re-wrapped into one run-on paragraph; they now keep
  their line breaks. `adare experiment list` no longer claims to list "in an
  environment" (it lists every project's experiments).
- Playbook VM creation printed its step labels (`[install 25]`, `[provision]`)
  as Rich markup, so they never appeared in the terminal.
- Playbook VM creation piped QEMU's output without reading it; a chatty QEMU
  could fill the pipe and stall.
- Deleting a VM in the web UI only dropped its database row: instances, QEMU
  templates and the managed disk were left behind, and environments using it
  silently lost their VM. It now tears the VM down fully and refuses a VM that
  environments use.
- Deleting a VM with force (`env remove --force`, web UI) deleted a running
  instance's row but left its domain running; force now reaches the instance cleanup.
- Concurrent QEMU runs could delete each other's run files: the crashed-run
  sweep at run start now scans files before reading instance rows.
- `experiment run` without `-e` failed with "multiple environments" after
  `env load --force`; an experiment now keeps one version per environment name.
- A failed or concurrent `env load` removes the VM row, disk copy and managed
  file it created, and reports a concurrent load of the same name clearly.
- A failed `env load --force` no longer deletes a VM it only updated in place.
- Run setup reads an environment's version, file and VM in one query, so a
  concurrent reload cannot pair one version's file with another's ULID.
- A managed copy such as `win_20261023_<hash>.yml` reloads under its registered
  name instead of losing the date suffix.
- `env load` reports the environment's real hypervisor instead of `virtualbox`.
- File-transfer factory tests no longer depend on the host having virtiofsd.
- `adare vm test` let the guest (as root) build its uv venv and bytecode inside
  the shared `~/.adare/adare`, leaving root-owned files there that made the next
  `make install` fail with `PermissionError`. The guest now keeps its venv in
  the guest (`UV_PROJECT_ENVIRONMENT`), writes no bytecode and leaves `uv.lock`
  alone (`--frozen`). The installer stops with the `chown` command to run instead
  of a traceback, and no longer continues after the appdata copy failed.
- `adare vm snapshot remove` always failed (it went through a deprecated
  template-level path that refused every deletion).
- Concurrent QEMU runs of one environment deleted each other's overlays (the
  orphan sweep matched every overlay of the template), and `--no-copy` overlays
  were written next to the user's disk.
- Multi-machine runs on one VM collided on the instance name and released only
  the last machine's instance.
- `adare vm test` used a fixed host port (19000), so two tests collided; it now
  also works for non-qcow2 disks and removes its config/varstore afterwards.
- `adare vm test` on a QEMU VM crashed with `'NoneType' object has no attribute
  'path'` when the first boot missed the guest-agent budget: the boot retry re-ran
  the experiment file-transfer setup, which needs a run directory the test lacks.
- Running an experiment without `-e` looked up an environment named after the
  managed file (`<name>_<hash8>`) and failed.
- Environment installation / platform lookups queried a non-existent `ulid` column.
- Python API `vm.load` failed with a TypeError (missing `project_path`).
- Every dev-session web route failed: async handlers called services that run
  their own `asyncio.run`; `/api/sessions/start` also passed a removed field and
  several routes read `result.value`/`is_success()`, which `Result` lacks.
- A nested `with` on a database API committed and closed the session its outer
  block was still using.
- The QEMU shared-folder guard raised `TypeError` instead of
  `UnsupportedFeatureException`.
- Experiments started from chat (`experiment_run` tool) were cancelled
  immediately; they now run to completion.
- Changed `adarevm`/`adarelib` code never reached guests: the skip check compared
  unbumped static versions (and adarelib against adarevm's version).
- A testfunction collection needing a newer adarelib API suggested `uv add
  adarelib.…`; it now says the guest's adarelib is outdated.
- `except A or B` handlers that silently caught only `A` (8 places).
- `NameError` on error paths in the event listener and VirtualBox networking.
- Database APIs resolving their path at import time.
- Late-bound loop variables in the chunked file-pull progress callback.
- Unclosed file handles in network-drive setup and web-app upload.
- `adare vm create` playbook installs counted a crash dialog or a hung progress
  bar as "installed" (any screen still for 45 s), and Kubuntu logins were never
  checked. A new `wait_text` step (`gone`, `fail_on`, `timeout`) now waits for
  the installer's "done" screen and fails fast on crash/error texts; the login
  check fails unless the greeter goes away without an error. All seven playbook
  profiles use it. The live session is powered off via ACPI before the hard
  stop, `wait_stable` takes `required: true`, and a failing step saves
  `<phase>_<nn>_FAILED.png`.
- Playbook installs went silent for up to an hour while waiting. Every step now
  prints a timestamp and its duration, and waits print a progress line each
  minute (elapsed / timeout, current on-screen text) plus a "may be stuck"
  warning once the screen has not changed for 10 minutes.

### Security
- The guest agent no longer accepts unauthenticated connections (per-run token);
  the token is redacted from host logs.
- VM port forwards (QEMU hostfwd, VirtualBox NAT) listened on all interfaces,
  exposing the guest agent to the LAN; they now bind to 127.0.0.1.
- The guest agent no longer logs command environment values.
- Bumped 28 locked dependencies with published advisories (aiohttp, starlette,
  urllib3, cryptography, pyjwt, python-multipart, mcp, fastmcp, …).
- `linux.log_entry_exists` (guest and host-mode QGA paths) passed `log_file` and
  `pattern` to the shell unquoted, allowing command injection from a playbook.

### Removed
- `adare server start`, which failed with `ModuleNotFoundError` and duplicated
  `adare web start` (now `adare ui start`), and the empty `adare help` group.
- Duplicate libvirt domain teardown: the run path, its signal handler and
  `vm test` share `run_resources.destroy_run_domain`; dead QEMU branches in the
  VirtualBox instance preparation, the broken `ensure_vm_available_for_environment`
  and unused environment queries (`get_environment_by_hash`, summaries).
- Dead VM/environment code: template-level snapshot shims, always-true VM
  "verification", the duplicated VirtualBox re-import in the run path (it now
  re-allocates through the normal path), unused environment API helpers and the
  second `parse_environment_file`.
- Broken console scripts `adareexp` and `mcp_gui` (their modules no longer exist).
- Stale CV server scripts (`reproduce_ocr.py`, a pipeline test for an API that
  no longer exists, sample images).
- Dead code: `networkdrive`, `helperfunctions.subprocess`, `webappaccess.request`,
  the experiment backup model, adarevm templating, legacy `setup.py` files and the
  root `requirements.txt`.
