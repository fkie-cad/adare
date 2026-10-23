.DEFAULT_GOAL = help
.PHONY: help install update adare-clean docs docs-sphinx install-skills test test-agent lint lint-fix lint-baseline typecheck hooks

help:
	@echo "--------------- HELP -----------------"
	@echo "Available targets:"
	@echo "  help            Show this help message."
	@echo "  install         Run the installer (PowerShell on Windows, shell on *nix); installs QEMU support and reports on system tool availability."
	@echo "  install-qemu    Alias for install (kept for backwards compatibility)."
	@echo "  update          Refresh dependencies, appdata, and testfunctions (hash-based, no symlink rebuild)."
	@echo "  adare-clean     Reset adare state."
	@echo "  install-skills  Symlink the workflow skills in skills/ into Claude Code's skill dirs (project + global)."
	@echo "  docs            Build HTML documentation with Sphinx."
	@echo "  docs-sphinx     Build HTML documentation with Sphinx."
	@echo "  test            Run the client unit suite."
	@echo "  test-agent      Run the guest agent suite on Python 3.10 (own venv, like CI)."
	@echo "  lint            Format check + quality ratchet (ruff, mypy, file size) - same as CI."
	@echo "  lint-fix        Apply ruff format and safe autofixes."
	@echo "  lint-baseline   Lock in paid-down debt (lowers quality-baseline.json)."
	@echo "  typecheck       Strict mypy on adare.core (must stay at zero errors)."
	@echo "  hooks           Install the pre-commit hooks."
	@echo "---------------------------------------"

install:
ifeq ($(OS),Windows_NT)
	@echo "Running PowerShell script..."
	@powershell.exe -File ./adare/install/install.ps1
else
	chmod +x ./adare/install/install.sh
	@echo "Running shell script (with QEMU support)..."
	@./adare/install/install.sh qemu
endif

update:
ifeq ($(OS),Windows_NT)
	@echo "update.ps1 is not yet provided; please run the steps from update.sh manually on Windows."
	@exit 1
else
	chmod +x ./adare/install/update.sh
	@./adare/install/update.sh qemu
endif

install-qemu:
	chmod +x ./adare/install/install.sh
	@echo "Running Adare installer script with QEMU support..."
	@./adare/install/install.sh qemu

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
DOCS_BUILD = docsrc/build/html
docs-sphinx:
	@echo "Building documentation with Sphinx..."
	uv sync --group docs
	uv run sphinx-build -b html -a -E docsrc/source $(DOCS_BUILD)
	@echo "Copying demo assets..."
	mkdir -p $(DOCS_BUILD)/demo
	cp paper/demo/*.mp4 $(DOCS_BUILD)/demo/
	touch $(DOCS_BUILD)/.nojekyll

# --- Quality -----------------------------------------------------------------
# The ratchet's mypy counts depend on which packages are installed, so lint runs
# in its own env (.venv-lint) built exactly like the CI lint job. This also keeps
# `uv sync` from stripping extras (e.g. qemu) out of your main .venv.
LINT_ENV = UV_PROJECT_ENVIRONMENT=.venv-lint
LINT_SYNC = $(LINT_ENV) uv sync --package adare --extra qemu --group lint --quiet

test:
	cd adare && uv run --no-sync pytest tests -q

# The guest agent targets the guest's Python (3.10+); the workspace needs 3.13,
# so the agent suite runs in its own venv, as in CI's `agent` job.
AGENT_VENV = .venv-agent
test-agent:
	uv venv -q --allow-existing --python 3.10 $(AGENT_VENV)
	uv pip install -q --python $(AGENT_VENV) --reinstall-package adarevm --reinstall-package adarelib ./adarelib ./adarevm 'pytest>=7.4.0' 'pytest-asyncio>=0.21.0'
	cd adarevm && ../$(AGENT_VENV)/bin/python -m pytest -q

lint:
	$(LINT_SYNC)
	$(LINT_ENV) uv run --no-sync ruff format --check .
	$(LINT_ENV) uv run --no-sync mypy adare/adare/core
	$(LINT_ENV) uv run --no-sync python scripts/quality_ratchet.py

lint-fix:
	$(LINT_SYNC)
	$(LINT_ENV) uv run --no-sync ruff format .
	$(LINT_ENV) uv run --no-sync ruff check . --fix

lint-baseline:
	$(LINT_SYNC)
	$(LINT_ENV) uv run --no-sync python scripts/quality_ratchet.py --update

typecheck:
	$(LINT_SYNC)
	$(LINT_ENV) uv run --no-sync mypy adare/adare/core

hooks:
	pre-commit install
