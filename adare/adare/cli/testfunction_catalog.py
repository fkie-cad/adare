"""CLI commands backed by the static testfunction catalog: list, search, info, catalog.

None of these need a project or the database: the catalog is read from the
collection sources (see :mod:`adare.backend.testfunction.catalog`).
"""

import logging

from adare.backend.testfunction.catalog import (
    CatalogEntry,
    bundled_sources,
    close_matches,
    find,
    load_catalog,
    search,
)
from adare.exceptions import TestFunctionNotFoundError
from adare.frontend.terminal.testfunction_catalog import catalog_markdown, render_entries, render_entry

log = logging.getLogger(__name__)


def _formatter():
    from adare.run import get_formatter_from_context

    formatter, output_file, _dual = get_formatter_from_context()
    return formatter, output_file


def resolve_entry(dotnotation: str, entries: list[CatalogEntry] | None = None) -> CatalogEntry:
    """Exact catalog entry, else a not-found error that names the closest candidates."""
    entries = entries if entries is not None else load_catalog()
    if entry := find(entries, dotnotation):
        return entry
    # A bare function name is fine when it is unambiguous.
    by_name = [e for e in entries if e.name == dotnotation]
    if len(by_name) == 1:
        return by_name[0]
    candidates = by_name or close_matches(entries, dotnotation) \
        or search(entries, dotnotation.replace('.', ' '), limit=3)
    solutions = [f'did you mean: {", ".join(e.dotnotation for e in candidates)}'] if candidates else []
    solutions.append(f'search by goal: adare test search "{dotnotation.split(".")[-1].replace("_", " ")}"')
    raise TestFunctionNotFoundError(log, f'Testfunction "{dotnotation}" not found', possible_solutions=solutions)


def exec_catalog_list(arguments) -> None:
    formatter, output_file = _formatter()
    entries = search(load_catalog(), collection=arguments.collection, category=arguments.category, os=arguments.os)
    title = f'testfunctions · {arguments.collection}' if arguments.collection else 'testfunctions'
    render_entries(entries, formatter, output_file, title=title, full=arguments.full)


def exec_catalog_search(arguments) -> None:
    formatter, output_file = _formatter()
    entries = search(load_catalog(), arguments.query, collection=arguments.collection, category=arguments.category,
                     os=arguments.os, limit=arguments.limit)
    if not entries:
        raise TestFunctionNotFoundError(log, f'No testfunction matches "{arguments.query}"', possible_solutions=[
            'use fewer or more general words (e.g. "file exists", "registry value")',
            'browse everything: adare test list'])
    render_entries(entries, formatter, output_file, title=f'testfunctions matching "{arguments.query}"',
                   with_example=True)


def exec_catalog_info(arguments) -> None:
    formatter, output_file = _formatter()
    render_entry(resolve_entry(arguments.dotnotation), formatter, output_file, example_only=arguments.example)


def exec_catalog_export(arguments) -> None:
    """Machine-independent reference of the bundled collections (Markdown or structured)."""
    entries = load_catalog(bundled_sources())
    if arguments.markdown:
        print(catalog_markdown(entries), end='')
        return
    formatter, output_file = _formatter()
    render_entries(entries, formatter, output_file, title='bundled testfunctions', full=True)
