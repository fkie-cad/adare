"""Every bundled testfunction documents itself for `adare test search/info` and agents.

The catalog parses a Google-style ``Args:`` section from each docstring; an agent
picking an assertion relies on it to fill the parameters correctly.
"""

from pathlib import Path

import pytest

from adare.backend.testfunction.catalog import load_catalog, parse_args_section

pytestmark = pytest.mark.unit

APPDATA = Path(__file__).resolve().parents[5] / 'appdata' / 'testfunctions'

# sqlite.py is documented separately (concurrent work); drop it from this set once it is.
UNDOCUMENTED_COLLECTIONS = {'sqlite'}


def _bundled_entries():
    entries = load_catalog(sources=[(APPDATA, False)])
    return [e for e in entries if e.collection not in UNDOCUMENTED_COLLECTIONS]


def test_appdata_dir_is_found():
    assert APPDATA.is_dir(), APPDATA
    assert len(_bundled_entries()) >= 40


@pytest.mark.parametrize('entry', _bundled_entries(), ids=lambda e: e.dotnotation)
def test_bundled_function_is_documented(entry):
    summary = entry.doc.strip().splitlines()[0].strip() if entry.doc.strip() else ''
    assert summary, f'{entry.dotnotation} has no docstring summary line'

    documented = parse_args_section(entry.doc)
    missing = [p.name for p in entry.params if p.name not in documented]
    assert not missing, f'{entry.dotnotation}: no Args entry for {missing}'
    empty = [p.name for p in entry.params if not p.doc.strip()]
    assert not empty, f'{entry.dotnotation}: empty Args description for {empty}'
