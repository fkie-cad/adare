#!/usr/bin/env python3
"""Generate the testfunction tables of the docs from the catalog.

    python scripts/gen_testfunction_tables.py           # write the tables
    python scripts/gen_testfunction_tables.py --check   # exit 1 if a table is stale

Writes ``docsrc/source/_static/tables/testfunctions_<collection>.csv`` (one per
collection with reference pages, included by ``reference/testfunctions/<collection>/index.rst``)
and ``testfunctions_all.csv`` (``reference/testfunctions/index.rst``). The source is the
static catalog of the bundled collections (``adare test catalog``), so a new testfunction
or changed parameter shows up after ``make testfunction-tables``; a unit test fails while a
committed table differs from the generated one.
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
from pathlib import Path

from adare.backend.testfunction.catalog import CatalogEntry, bundled_sources, load_catalog

ROOT = Path(__file__).resolve().parents[1]
TABLES_DIR = ROOT / 'docsrc' / 'source' / '_static' / 'tables'

# Collections documented in a guide page instead of per-function reference pages.
GUIDE_PAGES = {'visual': '/guide/icon-library'}

# Status column. Everything else is "tested": unit tests are enforced for every
# built-in testfunction (test_testfunction_coverage.py).
DEVELOPMENT_COLLECTIONS = frozenset({'linux', 'sqlite', 'windows', 'xml'})
STATUS_TESTED = ':status-tested:`●`'
STATUS_DEV = ':status-dev:`●`'

COLLECTION_HEADER = ('Function Name', 'S', 'Description', 'Parameters')
ALL_HEADER = ('Function', 'S', 'Description', 'Parameters')


def _status(entry: CatalogEntry) -> str:
    return STATUS_DEV if entry.collection in DEVELOPMENT_COLLECTIONS else STATUS_TESTED


def _description(entry: CatalogEntry) -> str:
    summary = entry.summary.strip()
    return summary[:1].upper() + summary[1:]


def _type_text(annotation: str) -> str:
    parts = [p.strip() for p in annotation.split('|') if p.strip() and p.strip() != 'None']
    return '/'.join(parts)


def _parameters(entry: CatalogEntry) -> str:
    """``dst (str), expected_count (int), comparison_type* (str)``; ``*`` marks optional ones."""
    out = []
    for p in entry.params:
        name = p.name if p.required else f'{p.name}*'
        type_text = _type_text(p.type)
        out.append(f'{name} ({type_text})' if type_text else name)
    return ', '.join(out)


def _csv(header: tuple[str, ...], rows: list[tuple[str, ...]]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator='\n')
    writer.writerow(header)
    writer.writerows(rows)
    return buffer.getvalue()


def render_tables(entries: list[CatalogEntry]) -> dict[str, str]:
    """``{file name: CSV text}`` for every table, ordered by dotnotation."""
    entries = sorted(entries, key=lambda e: e.dotnotation)
    tables: dict[str, str] = {}
    by_collection: dict[str, list[CatalogEntry]] = {}
    for entry in entries:
        by_collection.setdefault(entry.collection, []).append(entry)

    for collection, members in by_collection.items():
        if collection in GUIDE_PAGES:
            continue
        rows = [
            (
                f':doc:`{e.name} <../{collection}/{e.name}>`',
                _status(e),
                _description(e),
                _parameters(e),
            )
            for e in members
        ]
        tables[f'testfunctions_{collection}.csv'] = _csv(COLLECTION_HEADER, rows)

    all_rows = []
    for e in entries:
        target = GUIDE_PAGES.get(e.collection, f'{e.collection}/{e.name}')
        all_rows.append((f':doc:`{e.dotnotation} <{target}>`', _status(e), _description(e), _parameters(e)))
    tables['testfunctions_all.csv'] = _csv(ALL_HEADER, all_rows)
    return tables


def stale_tables(tables: dict[str, str], directory: Path = TABLES_DIR) -> list[str]:
    """Names of the tables whose file is missing or differs from the generated text."""
    stale = []
    for name, text in tables.items():
        path = directory / name
        if not path.is_file() or path.read_text(encoding='utf-8') != text:
            stale.append(name)
    return stale


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--check', action='store_true', help='only report stale tables (exit 1 if any)')
    args = parser.parse_args(argv)

    tables = render_tables(load_catalog(bundled_sources()))
    stale = stale_tables(tables)
    if args.check:
        for name in stale:
            print(f'stale: {TABLES_DIR / name}')
        return 1 if stale else 0
    for name in stale:
        (TABLES_DIR / name).write_text(tables[name], encoding='utf-8')
        print(f'wrote {(TABLES_DIR / name).relative_to(ROOT)}')
    if not stale:
        print('testfunction tables are up to date')
    return 0


if __name__ == '__main__':
    sys.exit(main())
