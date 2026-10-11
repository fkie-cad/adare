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
  `adare ws action` / `adare icons dump-all` take `--token` / `ADARE_AGENT_TOKEN`.

### Changed
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
- Broken console scripts `adareexp` and `mcp_gui` (their modules no longer exist).
- Stale CV server scripts (`reproduce_ocr.py`, a pipeline test for an API that
  no longer exists, sample images).
- Dead code: `networkdrive`, `helperfunctions.subprocess`, `webappaccess.request`,
  the experiment backup model, adarevm templating, legacy `setup.py` files and the
  root `requirements.txt`.
