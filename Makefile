
ifeq ($(OS),Windows_NT)
    detected_OS := Windows
    PYTHON = py
else
    detected_OS := $(shell uname)  # same as "uname -s"
    PYTHON = python3
endif


# .PHONY defines parts of the makefile that are not dependant on any specific file
# This is most often used to store functions
.PHONY = help install test systemtest unittest coverage clean flake # executable

# Defines the default target that `make` will to try to make, or in the case of a phony target, execute the specified commands
# This target is executed whenever we just type `make`
.DEFAULT_GOAL = help

.ONESHELL:

help:
	@echo "---------------HELP-----------------"
	@echo "to install the project type make install"
	@echo "to execute unit as well as system tests run make test"
	@echo "to execute the unittests type unittest"
	@echo "to execute the systemtests type systemtests"
	@echo "to show the coverage report and create a html report type make coverage (please make sure you run make test before)"
	@echo "------------------------------------"

appdata:
	${PYTHON} install/copy_appdata.py

adare:
	cd adare
	poetry install
	@ln -sf $(shell cd adare; poetry run which adare) ~/.local/bin/adare
	${PYTHON} install/copy_appdata.py

adarevm:
	cd adarevm
	poetry install

