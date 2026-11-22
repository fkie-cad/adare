"""Testfunction docstrings use made-up, neutral examples, never a real application's paths.

Agents read these docstrings (``adare test info``, the skill catalog, tools built on ADARE) to
pick and parameterise tests. An example such as a browser profile path or a well-known
database table hands them knowledge about where an application keeps its traces, which they
should find out from the evidence instead.
"""

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

COLLECTIONS = Path(__file__).resolve().parents[3] / 'appdata' / 'testfunctions'

# Application or trace names that once appeared in examples. Extend it when you find one.
APP_HINTS = re.compile(
    r'mozilla|firefox|chrom(e|ium)|thunderbird|libreoffice|soffice|places\.sqlite|moz_|sessionstore'
    r'|recently-used|\.xbel|\.config/Code|Microsoft/Office|browser history',
    re.IGNORECASE,
)


def _docstrings():
    for path in sorted(COLLECTIONS.glob('*/*.py')):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                doc = ast.get_docstring(node)
                if doc:
                    yield f'{path.parent.name}.{node.name}', doc


def test_docstrings_name_no_application():
    hits = [
        f'{name}: {line.strip()}' for name, doc in _docstrings() for line in doc.splitlines() if APP_HINTS.search(line)
    ]

    assert not hits, 'use neutral made-up examples (e.g. /home/user/data/app.db):\n' + '\n'.join(hits)
