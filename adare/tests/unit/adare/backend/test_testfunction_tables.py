"""The docs' testfunction tables are generated from the catalog and must be fresh."""

import importlib.util
from pathlib import Path

import pytest

from adare.backend.testfunction.catalog import CatalogEntry, ParamSpec, bundled_sources, load_catalog

pytestmark = pytest.mark.unit

_SCRIPT = Path(__file__).resolve().parents[5] / 'scripts' / 'gen_testfunction_tables.py'
_SPEC = importlib.util.spec_from_file_location('gen_testfunction_tables', _SCRIPT)
gen = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(gen)


def _entry(dotnotation, summary='tests a thing', params=()):
    collection, name = dotnotation.split('.', 1)
    return CatalogEntry(
        dotnotation=dotnotation,
        collection=collection,
        name=name,
        summary=summary,
        category='FILE_BASED',
        os='any',
        installed=True,
        path='',
        params=tuple(params),
    )


def test_committed_tables_are_fresh():
    """Regenerate with: make testfunction-tables"""
    stale = gen.stale_tables(gen.render_tables(load_catalog(bundled_sources())))
    assert not stale, f'stale docs tables {stale}: run `make testfunction-tables`'


def test_rows_link_pages_and_mark_optional_parameters():
    entries = [
        _entry(
            'text.occurrence_count',
            params=[
                ParamSpec('dst', 'str', True),
                ParamSpec('encoding', 'list[str] | str | None', False, None),
                ParamSpec('raw', '', True),
            ],
        ),
        _entry('linux.user_exists', summary='tests, with "quotes"'),
        _entry('visual.exists'),
    ]
    tables = gen.render_tables(entries)

    assert 'testfunctions_visual.csv' not in tables  # documented in a guide page
    assert tables['testfunctions_text.csv'].splitlines() == [
        'Function Name,S,Description,Parameters',
        ':doc:`occurrence_count <../text/occurrence_count>`,:status-tested:`●`,Tests a thing,'
        '"dst (str), encoding* (list[str]/str), raw"',
    ]
    all_lines = tables['testfunctions_all.csv'].splitlines()
    assert all_lines[0] == 'Function,S,Description,Parameters'
    assert all_lines[1] == ':doc:`linux.user_exists <linux/user_exists>`,:status-dev:`●`,"Tests, with ""quotes""",'
    assert all_lines[3].startswith(':doc:`visual.exists </guide/icon-library>`')


def test_stale_tables_reports_missing_and_changed_files(tmp_path):
    tables = {'a.csv': 'x\n', 'b.csv': 'y\n', 'c.csv': 'z\n'}
    (tmp_path / 'a.csv').write_text('x\n')
    (tmp_path / 'b.csv').write_text('old\n')
    assert gen.stale_tables(tables, tmp_path) == ['b.csv', 'c.csv']
