.DEFAULT_GOAL = help
.PHONY: help install adare-clean docs docs-sphinx

help:
	@echo "--------------- HELP -----------------"
	@echo "Available targets:"
	@echo "  help            Show this help message."
	@echo "  install         Run the installer (PowerShell on Windows, shell on *nix)."
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
	@echo "Running shell script..."
	@./adare/install/install.sh
endif

adare-clean:
	adare manage reset

# Documentation targets
docs: docs-sphinx

docs-sphinx:
	@echo "Building documentation with Sphinx..."
	poetry install --with docs
	poetry run sphinx-build -b html -a -E docsrc/source docs