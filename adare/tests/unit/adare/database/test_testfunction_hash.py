"""The per-function hash ignores docstrings, so documenting a testfunction never bumps its version."""

import ast
from pathlib import Path

import pytest

from adare.backend.testfunction.catalog import testfunction_code_without_docstring

pytestmark = pytest.mark.unit

APPDATA = Path(__file__).resolve().parents[4] / 'appdata' / 'testfunctions'


def _functions(source: str):
    return [n for n in ast.parse(source).body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


@pytest.mark.parametrize('path', sorted(APPDATA.glob('*/*.py')), ids=lambda p: p.stem)
def test_undocumented_functions_hash_like_before(path):
    # Pre-change hash input was ast.unparse(func); it must be unchanged for undocumented code.
    for func in _functions(path.read_text()):
        if ast.get_docstring(func) is None:
            assert testfunction_code_without_docstring(func) == ast.unparse(func)


def test_docstring_does_not_change_hash_input():
    plain = 'def f(ctx, dst: str):\n    return dst\n'
    documented = 'def f(ctx, dst: str):\n    """Check.\n\n    Args:\n        dst: path\n    """\n    return dst\n'
    only_doc = 'async def f(ctx):\n    """Only a docstring."""\n'
    (a,), (b,), (c,) = _functions(plain), _functions(documented), _functions(only_doc)
    assert testfunction_code_without_docstring(a) == testfunction_code_without_docstring(b)
    assert testfunction_code_without_docstring(c).startswith('async def f(ctx):')


def test_code_change_still_changes_hash_input():
    (a,), (b,) = _functions('def f(ctx):\n    return 1\n'), _functions('def f(ctx):\n    return 2\n')
    assert testfunction_code_without_docstring(a) != testfunction_code_without_docstring(b)
