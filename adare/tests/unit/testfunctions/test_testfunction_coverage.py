"""Every built-in testfunction must have unit tests and a reference page.

Testfunctions produce the evidence ADARE compares across OS/app versions, so an
unnoticed behaviour change is a measurement change. This guard makes sure a new
testfunction cannot land without tests (and docs), so CI covers all of them.
"""

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

PROJECT_ROOT = Path(__file__).parent.parent.parent.parent
ADARELIB_ROOT = PROJECT_ROOT.parent / "adarelib"
if str(ADARELIB_ROOT) not in sys.path:
    sys.path.insert(0, str(ADARELIB_ROOT))

from adare.helperfunctions.module import import_module_from_pyfile

TESTFUNCTIONS_DIR = PROJECT_ROOT / "appdata" / "testfunctions"
TESTS_DIR = Path(__file__).parent
DOCS_DIR = PROJECT_ROOT.parent / "docsrc" / "source" / "reference" / "testfunctions"

# Testfunctions that predate this check and still lack a reference page.
# Remove an entry when its page is written; the test below fails on stale entries.
UNDOCUMENTED = {
    "csv.compare_rows", "csv.compare_files",
    "excel.sheet_exists", "excel.cell_value_matches", "excel.contains_row",
    "excel.validate_columns", "excel.compare_rows", "excel.compare_sheets",
    "excel.compare_files",
    "jsonl.line_matches", "jsonl.line_count", "jsonl.value_in_any_line",
}

# Collections documented in a guide page instead of one reference page per function;
# the guide must mention every testname.
GUIDE_DOCUMENTED = {
    "visual": PROJECT_ROOT.parent / "docsrc" / "source" / "guide" / "icon-library.rst",
}


def _collect():
    """Yield (collection, python function name, testname) for every built-in testfunction."""
    for module_file in sorted(TESTFUNCTIONS_DIR.glob("*/*.py")):
        collection = module_file.parent.name
        module = import_module_from_pyfile(module_file)
        for attr, value in vars(module).items():
            test_class = getattr(value, "_test_class", None)
            if callable(value) and test_class is not None:
                yield collection, attr, test_class.testname


TESTFUNCTIONS = list(_collect())


def test_testfunctions_are_discovered():
    assert {c for c, _, _ in TESTFUNCTIONS} >= {"standard", "sqlite", "csv", "json", "xml"}


@pytest.mark.parametrize(("collection", "func", "testname"), TESTFUNCTIONS,
                         ids=[f"{c}.{t}" for c, _, t in TESTFUNCTIONS])
def test_testfunction_has_unit_tests(collection, func, testname):
    test_file = TESTS_DIR / f"test_{collection}.py"
    assert test_file.exists(), f"{collection} has no test file {test_file.name}"
    assert f".{func}._test_class" in test_file.read_text(encoding="utf-8"), (
        f"{collection}.{testname} is not exercised in {test_file.name} "
        f"(expected a reference to <module>.{func}._test_class)"
    )


@pytest.mark.parametrize(("collection", "func", "testname"), TESTFUNCTIONS,
                         ids=[f"{c}.{t}" for c, _, t in TESTFUNCTIONS])
def test_testfunction_has_reference_page(collection, func, testname):
    if collection in GUIDE_DOCUMENTED:
        guide = GUIDE_DOCUMENTED[collection]
        assert testname in guide.read_text(encoding="utf-8"), f"{testname} is not described in {guide.name}"
        return
    page = DOCS_DIR / collection / f"{testname}.rst"
    if f"{collection}.{testname}" in UNDOCUMENTED:
        assert not page.exists(), f"{page.name} exists now; remove {collection}.{testname} from UNDOCUMENTED"
        pytest.skip("known gap: no reference page yet")
    assert page.exists(), f"{collection}.{testname} has no reference page {page.relative_to(PROJECT_ROOT.parent)}"


def test_undocumented_list_has_no_unknown_entries():
    known = {f"{c}.{t}" for c, _, t in TESTFUNCTIONS}
    assert known >= UNDOCUMENTED, f"unknown testfunctions in UNDOCUMENTED: {UNDOCUMENTED - known}"
