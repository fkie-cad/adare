"""Every bundled testfunction has a consistent contract, and every contract example holds.

The contract (``<collection>/contract.yaml``) is what agents and the docs say a function can and
cannot do; its examples run here against files built from their spec, so a documented boundary
("an absent key fails", "an offset outside the file is an error") stays true.
"""

import pytest

from adare.backend.testfunction.catalog import PACKAGE_APPDATA, bundled_sources, load_catalog
from adare.backend.testfunction.contract import LIBRARY_FILE, read_library
from adare.backend.testfunction.contract_checks import collection_problems
from adare.backend.testfunction.contract_examples import OUTCOME_STATUS, offline_blocker, run_example

pytestmark = pytest.mark.unit

# Collections whose contract.yaml is still being written; remove an entry when it lands.
WITHOUT_CONTRACT: set[str] = set()

ENTRIES = load_catalog(bundled_sources())
COLLECTIONS = sorted({e.collection for e in ENTRIES})


def test_library_parses():
    library = read_library(PACKAGE_APPDATA / LIBRARY_FILE)
    assert library.asserts and library.formats and library.features and library.gaps


def test_allowlist_has_no_stale_entries():
    stale = sorted(c for c in WITHOUT_CONTRACT if (PACKAGE_APPDATA / c / 'contract.yaml').is_file())
    assert not stale, f'{stale} have a contract.yaml now: remove them from WITHOUT_CONTRACT'


@pytest.mark.parametrize('entry', [e for e in ENTRIES if e.collection not in WITHOUT_CONTRACT], ids=str)
def test_function_has_contract(entry):
    assert entry.contract is not None, f'{entry.dotnotation}: no entry in {entry.collection}/contract.yaml'


@pytest.mark.parametrize('collection', [c for c in COLLECTIONS if c not in WITHOUT_CONTRACT])
def test_contract_is_consistent(collection):
    problems = collection_problems(PACKAGE_APPDATA / collection / f'{collection}.py', ENTRIES)
    assert not problems, '\n'.join(problems)


def _examples():
    for entry in ENTRIES:
        for example in entry.contract.examples if entry.contract else ():
            yield pytest.param(entry, example, id=f'{entry.dotnotation}: {example.title}')


@pytest.mark.parametrize(('entry', 'example'), list(_examples()))
def test_contract_example(entry, example, tmp_path):
    from adarelib.constants import StatusEnum

    blocker = offline_blocker(entry, example)
    if blocker:
        pytest.skip(blocker)
    result = run_example(entry, example, tmp_path)
    status = StatusEnum(result.status).name
    assert status == OUTCOME_STATUS[example.expect], f'expected {example.expect}, got {status}: {result.details}'
