"""``adare test info`` and ``adare test catalog --markdown`` show the docstrings' "Use for" prose."""

from types import SimpleNamespace

import pytest
from rich.console import Console

from adare.backend.testfunction.catalog import CatalogEntry, ParamSpec, use_for
from adare.frontend.terminal import testfunction_catalog as render

pytestmark = pytest.mark.unit

DOC = """Pass when the file has ``expected_size`` bytes.

Use for: checking a file is empty
    (``expected_size: 0``).

Sizes of archive members are their extracted size.

Args:
    dst: Guest path.
"""

ENTRY = CatalogEntry(
    dotnotation='demo.file_size',
    collection='demo',
    name='file_size',
    summary='tests the size of a file',
    category='FILE_BASED',
    os='any',
    installed=True,
    path='demo/demo.py',
    doc=DOC,
    params=(ParamSpec('dst', 'str', True, doc='Guest path.'),),
)


def _formatter(kind):
    return SimpleNamespace(format_type=SimpleNamespace(value=kind))


def test_use_for_joins_the_paragraph_and_ignores_args():
    assert use_for(DOC) == 'checking a file is empty (``expected_size: 0``).'
    assert use_for('Summary.\n\nArgs:\n    x: Use for: nothing.\n') == ''
    assert use_for('') == ''


def test_plain_info_prints_use_for_under_the_summary(capsys):
    render.render_entry(ENTRY, _formatter('plain'))
    lines = capsys.readouterr().out.splitlines()
    assert lines[1:3] == ['tests the size of a file', 'Use for: checking a file is empty (``expected_size: 0``).']


def test_plain_info_without_use_for_has_no_empty_label(capsys):
    from dataclasses import replace

    render.render_entry(replace(ENTRY, doc='Pass when.'), _formatter('plain'))
    assert 'Use for' not in capsys.readouterr().out


def test_rich_info_shows_use_for_once_and_the_other_prose():
    console = Console(width=200, record=True)
    console.print(render._info_panel(ENTRY, version=None))
    text = console.export_text()
    assert text.count('Use for:') == 1
    assert 'Use for: checking a file is empty' in text
    assert 'Sizes of archive members are their extracted size.' in text
    assert 'Args:' not in text


def test_catalog_markdown_has_use_for_line():
    markdown = render.catalog_markdown([ENTRY])
    assert '**Use for:** checking a file is empty (``expected_size: 0``).' in markdown
