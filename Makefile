ifeq ($(OS),Windows_NT)
    detected_OS := Windows
    PYTHON = py
else
    detected_OS := $(shell uname)  # same as "uname -s"
    PYTHON = python3
endif

.DEFAULT_GOAL = help
.PHONY = help adare

help:
	@echo "---------------HELP-----------------"
	@echo "------------------------------------"

adare:
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

adarevm:
ifeq ($(OS),Windows_NT)
	@echo "Running PowerShell script..."
	@powershell.exe -File ./adarevm/install/install.ps1
else
	@echo "Running shell script..."
	@./adarevm/install/install.sh
endif