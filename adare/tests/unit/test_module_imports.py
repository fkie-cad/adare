"""Every module of the host package must import cleanly.

Most modules are only reached through CLI paths or live VMs that the unit suite
never exercises, so import-time errors (a bad annotation evaluated in a class
body, a missing import, a renamed module) would otherwise ship unnoticed.
"""

import importlib
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

PACKAGE_DIR = Path(__file__).parent.parent.parent / "adare"

# Modules that predate this check and import modules that no longer exist.
# Delete the module (or fix it) and drop the entry; stale entries fail below.
KNOWN_BROKEN: set[str] = set()


def _module_names() -> list[str]:
    names = []
    for path in sorted(PACKAGE_DIR.rglob("*.py")):
        parts = path.relative_to(PACKAGE_DIR).with_suffix("").parts
        if "__pycache__" in parts or parts[0] in ("appdata", "install"):
            continue
        names.append(".".join(("adare", *parts)).removesuffix(".__init__"))
    return names


MODULES = _module_names()


@pytest.mark.parametrize("module", [m for m in MODULES if m not in KNOWN_BROKEN])
def test_module_imports(module):
    importlib.import_module(module)


@pytest.mark.parametrize("module", sorted(KNOWN_BROKEN))
def test_known_broken_entries_are_still_broken(module):
    assert module in MODULES, f"{module} no longer exists; remove it from KNOWN_BROKEN"
    with pytest.raises(ImportError):
        importlib.import_module(module)
