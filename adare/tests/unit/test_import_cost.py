"""Heavy optional dependencies must stay off the import path of common commands.

Every CLI invocation pays for what its modules import at load time. These run in
a fresh interpreter because the test process itself has long since imported
everything.
"""

import subprocess
import sys

import pytest

pytestmark = pytest.mark.unit


def _loaded_after_import(module: str, candidates: list[str]) -> list[str]:
    code = f'import sys, {module}; print(" ".join(m for m in {candidates!r} if m in sys.modules))'
    out = subprocess.run([sys.executable, '-c', code], check=True, capture_output=True, text=True).stdout
    return out.split()


@pytest.mark.parametrize('module', ['adare.database.init', 'adare.services.vm_service'])
def test_db_commands_do_not_import_pandas_or_http_stacks(module):
    assert _loaded_after_import(module, ['pandas', 'requests', 'aiohttp']) == []


def test_data_retrieval_api_still_importable_from_package():
    from adare.database.api import DataRetrievalApi
    from adare.database.api.frontend import DataRetrievalApi as Direct

    assert DataRetrievalApi is Direct
