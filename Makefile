
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

install:
	${PYTHON} -m pip install .
	${PYTHON} install/copy_appdata.py

test:
	${PYTHON} -m coverage run -m pytest tests integration || exit 0

systemtest:
	${PYTHON} -m coverage run -m pytest integration || exit 0

unittest:
	${PYTHON} -m coverage run -m pytest tests || exit 0

coverage:
	${PYTHON} -m coverage report
	${PYTHON} -m coverage html

doc:
	${PYTHON} setup.py build_sphinx

clean_docs:


clean_install:
	${PYTHON} setup.py bdist_wheel clean
	${PYTHON} -m pip install . --no-cache-dir
	${PYTHON} install/copy_appdata.py

flake:
	${PYTHON} -m flake8 || exit 0
