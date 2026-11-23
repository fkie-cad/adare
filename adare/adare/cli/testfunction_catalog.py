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
from adare.frontend.terminal.testfunction_catalog import (
    catalog_markdown,
    render_entries,
    render_entry,
    render_features,
    render_search,
)

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
    candidates = (
        by_name or close_matches(entries, dotnotation) or search(entries, dotnotation.replace('.', ' '), limit=3)
    )
    solutions = [f'did you mean: {", ".join(e.dotnotation for e in candidates)}'] if candidates else []
    solutions.append(f'search by goal: adare test search "{dotnotation.split(".")[-1].replace("_", " ")}"')
    raise TestFunctionNotFoundError(log, f'Testfunction "{dotnotation}" not found', possible_solutions=solutions)


def exec_catalog_list(arguments) -> None:
    formatter, output_file = _formatter()
    entries = search(load_catalog(), collection=arguments.collection, category=arguments.category, os=arguments.os)
    title = f'testfunctions · {arguments.collection}' if arguments.collection else 'testfunctions'
    render_entries(entries, formatter, output_file, title=title, full=arguments.full)


def exec_catalog_search(arguments) -> None:
    from adare.backend.testfunction.search_cards import result_dict, search_goal

    formatter, output_file = _formatter()
    _check_facets(arguments)
    result = search_goal(
        load_catalog(),
        arguments.query,
        collection=arguments.collection,
        category=arguments.category,
        os=arguments.os,
        asserts=arguments.asserts,
        fmt=arguments.reads,
        feature=arguments.feature,
        limit=arguments.limit,
    )
    if not result.hits and not result.gaps:
        raise TestFunctionNotFoundError(
            log,
            f'No testfunction matches "{arguments.query}"',
            possible_solutions=[
                'use fewer or more general words (e.g. "file exists", "registry value")',
                'drop --asserts/--reads/--feature, or browse: adare test list',
            ],
        )
    render_search(result_dict(result, arguments.query), formatter, output_file)


def _check_facets(arguments) -> None:
    """Unknown facet values are a usage error that lists the vocabulary."""
    from adare.backend.testfunction.contract import load_library

    library = load_library()
    for value, vocabulary, option in (
        (arguments.asserts, library.asserts, '--asserts'),
        (arguments.reads, library.formats, '--reads'),
        (arguments.feature, library.features, '--feature'),
    ):
        if value and value not in vocabulary:
            raise TestFunctionNotFoundError(
                log, f'{option} {value} is unknown', possible_solutions=[f'one of: {", ".join(vocabulary)}']
            )


def exec_catalog_feature(arguments) -> None:
    from adare.backend.testfunction.contract import load_library

    formatter, output_file = _formatter()
    library = load_library()
    if arguments.feature and arguments.feature not in library.features:
        raise TestFunctionNotFoundError(
            log,
            f'Feature "{arguments.feature}" not found',
            possible_solutions=[f'one of: {", ".join(library.features)}', 'list them: adare test feature'],
        )
    render_features(load_catalog(), arguments.feature, formatter, output_file)


def installed_version(entry: CatalogEntry) -> int | None:
    """Current method version from the global DB (best effort; None if not loaded)."""
    from sqlalchemy.exc import SQLAlchemyError

    from adare.database.api.base import GlobalDatabaseApi
    from adare.database.models.global_models import TestFunction, TestFunctionFile

    try:
        with GlobalDatabaseApi() as api:
            row = (
                api._session.query(TestFunction.version)
                .join(TestFunctionFile)
                .filter(
                    TestFunctionFile.name == entry.collection,
                    TestFunction.name == entry.name.split('.')[-1],
                    TestFunction.is_current.is_(True),
                )
                .first()
            )
    except (SQLAlchemyError, OSError) as e:
        log.debug(f'No version for {entry.dotnotation}: {e}')
        return None
    return row[0] if row else None


def exec_catalog_info(arguments) -> None:
    formatter, output_file = _formatter()
    entry = resolve_entry(arguments.dotnotation)
    version = None if arguments.example or not entry.installed else installed_version(entry)
    render_entry(entry, formatter, output_file, example_only=arguments.example, version=version)


def exec_catalog_export(arguments) -> None:
    """Machine-independent reference of the bundled collections (Markdown or structured)."""
    entries = load_catalog(bundled_sources())
    if arguments.markdown_dir:
        from pathlib import Path

        from adare.backend.testfunction.contract import load_library
        from adare.backend.testfunction.contract_render import markdown_files

        root = Path(arguments.markdown_dir)
        for relative, content in markdown_files(entries, load_library()).items():
            (root / relative).parent.mkdir(parents=True, exist_ok=True)
            (root / relative).write_text(content, encoding='utf-8')
        print(f'wrote the testfunction references to {root}')
        return
    if arguments.markdown:
        print(catalog_markdown(entries), end='')
        return
    formatter, output_file = _formatter()
    render_entries(entries, formatter, output_file, title='bundled testfunctions', full=True)
