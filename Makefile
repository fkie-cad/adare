.DEFAULT_GOAL = help
.PHONY: help install update adare-clean docs docs-sphinx

help:
	@echo "--------------- HELP -----------------"
	@echo "Available targets:"
	@echo "  help            Show this help message."
	@echo "  install         Run the installer (PowerShell on Windows, shell on *nix; QEMU support included on *nix)."
	@echo "  install-qemu    Alias for install (kept for backwards compatibility)."
	@echo "  update          Refresh dependencies, appdata, and testfunctions (hash-based, no symlink rebuild)."
	@echo "  adare-clean     Reset adare state."
	@echo "  docs            Build HTML documentation with Sphinx."
	@echo "  docs-sphinx     Build HTML documentation with Sphinx."
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

# Documentation targets
docs: docs-sphinx

docs-sphinx:
	@echo "Building documentation with Sphinx..."
	uv sync --group docs
	uv run sphinx-build -b html -a -E docsrc/source docs
	@echo "Copying demo assets..."
	mkdir -p docs/demo
	cp paper/demo/*.mp4 docs/demo/
	touch docs/.nojekyll