.DEFAULT_GOAL = help
.PHONY: help install install-qemu update sync adare-clean docs docs-sphinx install-skills test test-cov test-testfunctions test-testfunctions-guest test-cv test-agent test-install guest-venv lock-guest lint lint-fix lint-baseline typecheck hooks

# uv owns the environments and the lock; make only names the tasks. CI calls these
# same targets (with UV_LOCKED=1, i.e. --locked), so each command is written once,
# here. Every target syncs what it needs first, so it never runs on a stale env.
# Syncs into your main .venv are --inexact: they add what a target needs and never
# strip what else is installed (the qemu extra, the CV server, ...).
SYNC = uv sync --inexact --quiet
RUN = uv run --no-sync

help:
	@echo "--------------- HELP -----------------"
	@echo "Available targets:"
	@echo "  help            Show this help message."
	@echo "  install         Install ADARE from uv.lock, with QEMU support (Windows: VirtualBox only)."
	@echo "  install-qemu    Alias for install (kept for backwards compatibility)."
	@echo "  update          Refresh dependencies, appdata, and testfunctions after a git pull."
	@echo "  sync            Bring .venv up to date with uv.lock (keeps the qemu extra; use instead of plain 'uv sync')."
	@echo "  adare-clean     Reset adare state."
	@echo "  install-skills  Symlink the workflow skills in skills/ into Claude Code's skill dirs (project + global)."
	@echo "  docs            Build HTML documentation with Sphinx (warnings are errors)."
	@echo "  docs-sphinx     Build HTML documentation with Sphinx (warnings are errors)."
	@echo "  test            Run the client unit suite (extra pytest flags: PYTEST_ARGS=...)."
	@echo "  test-cov        Run the unit suite with coverage; fails below the floor (COV_MIN)."
	@echo "  test-testfunctions  Run only the testfunction tests on the host Python (no libvirt needed)."
	@echo "  test-testfunctions-guest  Run the testfunction tests on the guests' Python 3.10."
	@echo "  test-cv         Run the CV server suite."
	@echo "  test-agent      Run the guest agent suite on the guests' Python 3.10."
	@echo "  test-install    Run 'make install' then 'make update', and check the installed CLI."
	@echo "  lock-guest      Re-pin requirements-guest-test.txt (the guest test venv)."
	@echo "  lint            Format check + quality ratchet (ruff, mypy, file size) - same as CI."
	@echo "  lint-fix        Apply ruff format and safe autofixes."
	@echo "  lint-baseline   Lock in paid-down debt (lowers quality-baseline.json)."
	@echo "  typecheck       Strict mypy on adare.core (must stay at zero errors)."
	@echo "  hooks           Install the pre-commit hooks."
	@echo "---------------------------------------"

# The install scripts do the work (uv sync --locked, CLIs on PATH, appdata, DB
# migrations); see adare/install/. Windows has no QEMU support and one script,
# safe to re-run, for both install and update.
PS_SCRIPT = powershell.exe -NoProfile -ExecutionPolicy Bypass -File ./adare/install/install.ps1

install:
ifeq ($(OS),Windows_NT)
	@$(PS_SCRIPT)
else
	@bash ./adare/install/install.sh qemu
endif

update:
ifeq ($(OS),Windows_NT)
	@$(PS_SCRIPT)
else
	@bash ./adare/install/update.sh qemu
endif

install-qemu: install

sync:
	uv sync --inexact --extra qemu

adare-clean:
	adare manage reset

# Install the workflow skills (source of truth: skills/) into the locations
# Claude Code reads: .claude/skills/ (this project) and ~/.claude/skills/ (global).
# Symlinks, so skills/ stays the single source of truth and edits propagate.
install-skills:
	@echo "Installing ADARE agent skills from skills/ ..."
	@mkdir -p .claude/skills "$(HOME)/.claude/skills"
	@for d in $(CURDIR)/skills/*/; do \
		name=$$(basename $$d); \
		ln -sfn "$$d" ".claude/skills/$$name"; \
		ln -sfn "$$d" "$(HOME)/.claude/skills/$$name"; \
		echo "  linked $$name -> .claude/skills/ and ~/.claude/skills/"; \
	done
	@echo "Claude Code: skills are now project-local and global (also via 'ollama launch claude')."
	@echo "OpenCode: 'ln -sfn $(CURDIR)/skills .opencode/skills' + enable the opencode-skills plugin,"
	@echo "          or use an AGENTS.md reference. See docsrc/mcp-clients.md."

# Documentation targets
docs: docs-sphinx

# Build output is not committed (GitHub Pages is deployed by the docs workflow).
# -W: a warning (broken reference, bad heading level, ...) fails the build, so CI
# catches it on the PR instead of after the deploy from main.
DOCS_BUILD = docsrc/build/html
docs-sphinx:
	@echo "Building documentation with Sphinx..."
	$(SYNC) --group docs
	$(RUN) sphinx-build -b html -a -E -W --keep-going docsrc/source $(DOCS_BUILD)
	@echo "Copying demo assets..."
	mkdir -p $(DOCS_BUILD)/demo
	cp paper/demo/*.mp4 $(DOCS_BUILD)/demo/
	touch $(DOCS_BUILD)/.nojekyll

# --- Tests -------------------------------------------------------------------
# `--package adare` keeps adare-cv-server (paddle) out; the unit suite never imports
# it. live_vm tests are deselected by the pytest addopts.
test:
	$(SYNC) --package adare --group test --extra qemu
	cd adare && $(RUN) pytest tests -q $(PYTEST_ARGS)

# Line-coverage floor (39.2% when set). Raise it as coverage grows; never lower it.
COV_MIN = 40
test-cov:
	$(MAKE) test PYTEST_ARGS="--cov --cov-report= --cov-fail-under=$(COV_MIN) $(PYTEST_ARGS)"

# Testfunctions run on the host (host test mode) and in guests. This runs them on the
# host Python, without the qemu extra (which needs libvirt headers); CI runs it on
# macOS. test-testfunctions-guest below runs them on the guests' Python.
test-testfunctions:
	$(SYNC) --package adare --group test
	cd adare && $(RUN) pytest tests/unit/testfunctions -q $(PYTEST_ARGS)

test-cv:
	$(SYNC) --package adare-cv-server --group test
	$(RUN) pytest adare-cv-server/tests -q $(PYTEST_ARGS)

# Guest-side code (the agent, the testfunctions) runs on the guest's Python (3.10+);
# the workspace needs 3.13. So its tests run in their own venv on the oldest guest
# Python, pinned by requirements-guest-test.txt (re-pin: `make lock-guest`), with
# adarelib + adarevm installed from the sources the way their wheels are installed
# in guests. `uv pip check` fails if they need a dependency the pins lack.
GUEST_PYTHON = 3.10
GUEST_VENV = .venv-guest
ifeq ($(OS),Windows_NT)
GUEST_PY = $(GUEST_VENV)/Scripts/python.exe
else
GUEST_PY = $(GUEST_VENV)/bin/python
endif
guest-venv:
	uv venv -q --allow-existing --python $(GUEST_PYTHON) $(GUEST_VENV)
	uv pip sync -q --python $(GUEST_VENV) requirements-guest-test.txt
	uv pip install -q --python $(GUEST_VENV) --no-deps --reinstall-package adarevm --reinstall-package adarelib ./adarelib ./adarevm
	uv pip check -q --python $(GUEST_VENV)

lock-guest:
	uv pip compile -q requirements-guest-test.in --universal --python-version $(GUEST_PYTHON) \
		--no-emit-package adarelib --no-emit-package adarevm -o requirements-guest-test.txt

test-agent: guest-venv
	cd adarevm && ../$(GUEST_PY) -m pytest -q $(PYTEST_ARGS)

# --confcutdir keeps tests/conftest.py (which imports the 3.13 host package) out.
test-testfunctions-guest: guest-venv
	cd adare && ../$(GUEST_PY) -m pytest tests/unit/testfunctions --confcutdir=tests/unit/testfunctions -q $(PYTEST_ARGS)

# What a user does on a fresh clone, then after a pull: CI runs it on all three OSes.
# It is a real install (the same as running those targets yourself).
ifeq ($(OS),Windows_NT)
INSTALLED_ADARE = .venv/Scripts/adare.exe
else
INSTALLED_ADARE = $(HOME)/.local/bin/adare
endif
test-install: install update
	$(INSTALLED_ADARE) --help

# --- Quality -----------------------------------------------------------------
# The ratchet's mypy counts depend on which packages are installed, so lint runs
# in its own env (.venv-lint), synced exactly (not --inexact) so your machine and
# CI count the same thing. It also leaves your main .venv alone.
LINT_ENV = UV_PROJECT_ENVIRONMENT=.venv-lint
LINT_SYNC = $(LINT_ENV) uv sync --package adare --extra qemu --group lint --quiet
LINT_RUN = $(LINT_ENV) $(RUN)


# The ratchet runs mypy once over adare/adare and also fails on any error in
# adare.core, so lint needs no separate `mypy adare/adare/core` pass.
lint:
	$(LINT_SYNC)
	$(LINT_RUN) ruff format --check .
	$(LINT_RUN) python scripts/quality_ratchet.py

lint-fix:
	$(LINT_SYNC)
	$(LINT_RUN) ruff format .
	$(LINT_RUN) ruff check . --fix

lint-baseline:
	$(LINT_SYNC)
	$(LINT_RUN) python scripts/quality_ratchet.py --update

typecheck:
	$(LINT_SYNC)
	$(LINT_RUN) mypy adare/adare/core

hooks:
	pre-commit install
