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
  grounding server, which is excluded from it.

### Changed
- Whole workspace formatted with `ruff format`; safe ruff autofixes applied.
- `uv.lock` is committed; CI installs with `--locked`.
- ruff and mypy pinned exactly in a `lint` dependency group.

### Fixed
- `except A or B` handlers that silently caught only `A` (8 places).
- `NameError` on error paths in the event listener and VirtualBox networking.
- Database APIs resolving their path at import time.
- Late-bound loop variables in the chunked file-pull progress callback.
- Unclosed file handles in network-drive setup and web-app upload.

### Security
- Bumped 28 locked dependencies with published advisories (aiohttp, starlette,
  urllib3, cryptography, pyjwt, python-multipart, mcp, fastmcp, …).

### Removed
- Broken console scripts `adareexp` and `mcp_gui` (their modules no longer exist).
