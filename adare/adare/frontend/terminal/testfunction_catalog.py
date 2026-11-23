"""Renderers for the static testfunction catalog (``adare test list/search/info/catalog``).

Three shapes per view: Rich on a TTY, tab-separated plain text when piped (full
names, no boxes — parseable by scripts and agents), and structured dicts for the
JSON/YAML formatter.
"""

import sys

from rich.console import Group
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table
from rich.text import Text

from adare.backend.testfunction.catalog import CatalogEntry, use_for
from adare.frontend.terminal.console import DefaultConsole


def output_mode(formatter) -> str:
    """``json``/``yaml`` (structured), ``plain`` (TSV) or ``rich``."""
    value = formatter.format_type.value
    if value in ('json', 'yaml', 'plain'):
        return value
    return 'rich' if sys.stdout.isatty() else 'plain'


def _default_text(entry_param) -> str:
    return '' if entry_param.required else repr(entry_param.default)


def _prose(doc: str) -> str:
    """Docstring text before ``Args:``, without the ``Use for:`` paragraph (shown on its own)."""
    paragraphs = doc.split('\nArgs:')[0].strip().split('\n\n')
    return '\n\n'.join(p.strip() for p in paragraphs if p.strip() and not p.strip().startswith('Use for:'))


# ---------------------------------------------------------------------------
# list / search
# ---------------------------------------------------------------------------


def _list_table(entries: list[CatalogEntry], title: str) -> Panel:
    table = Table(expand=True, header_style='bold')
    table.add_column('testfunction', style='cyan', no_wrap=True)
    table.add_column('summary', ratio=3)
    table.add_column('params', ratio=2)
    table.add_column('os', no_wrap=True)
    for entry in entries:
        params = ', '.join(p.name if p.required else f'[dim]{p.name}?[/dim]' for p in entry.params)
        name = entry.dotnotation if entry.installed else f'{entry.dotnotation} [yellow](not synced)[/yellow]'
        table.add_row(name, entry.summary, params, entry.os)
    caption = '[dim]name? = optional · details: adare test info <testfunction> · find: adare test search "<goal>"[/dim]'
    return Panel(Group(table, Text.from_markup(caption)), title=title, border_style='blue', title_align='left')


def render_entries(
    entries: list[CatalogEntry],
    formatter,
    output_file=None,
    *,
    title: str = 'testfunctions',
    full: bool = False,
    with_example: bool = False,
) -> None:
    mode = output_mode(formatter)
    if mode in ('json', 'yaml'):
        records = []
        for entry in entries:
            record = entry.to_dict(compact=not full)
            if with_example and not full:
                record['example'] = entry.example()
            records.append(record)
        formatter.print_or_save({'testfunctions': records}, output_file, False)
    elif mode == 'plain':
        lines = ['testfunction\tsignature\tos\tinstalled\tsummary']
        lines += [f'{e.dotnotation}\t{e.signature()}\t{e.os}\t{str(e.installed).lower()}\t{e.summary}' for e in entries]
        print('\n'.join(lines))
    else:
        DefaultConsole().print(_list_table(entries, f'[b gold3]{title}[/b gold3]'))


# ---------------------------------------------------------------------------
# info
# ---------------------------------------------------------------------------


def _info_panel(entry: CatalogEntry, version: int | None) -> Panel:
    if entry.contract is not None:
        from rich.markdown import Markdown

        title = f'[b gold3]{entry.dotnotation}[/b gold3]' + (f' [dim]v{version}[/dim]' if version else '')
        return Panel(Markdown(_info_markdown(entry, version)), title=title, border_style='blue', title_align='left')
    return _legacy_info_panel(entry, version)


def _legacy_info_panel(entry: CatalogEntry, version: int | None) -> Panel:
    params = Table(expand=True, header_style='bold')
    for column in ('parameter', 'type', 'default', 'description'):
        params.add_column(column, ratio=3 if column == 'description' else 1)
    for p in entry.params:
        name = p.name if not p.required else f'[b]{p.name}[/b] [red]*[/red]'
        params.add_row(name, p.type or '[dim]untyped[/dim]', _default_text(p), p.doc or '[dim]—[/dim]')

    meta = f'[dim]{entry.category} · os: {entry.os} · {entry.path}[/dim]'
    if not entry.installed:
        meta += '\n[yellow]bundled but not synced: run `adare test sync`[/yellow]'
    parts = [Text(entry.summary, style='bold'), Text.from_markup(meta)]
    if entry.doc:
        parts.append(Text(_prose(entry.doc)))
    if use_for(entry.doc):
        parts.append(Text.assemble(('Use for: ', 'bold green'), use_for(entry.doc)))
    parts += [
        params,
        Text('example (paste into the playbook):', style='bold'),
        Syntax(entry.example_yaml(), 'yaml', background_color='default'),
    ]
    title = f'[b gold3]{entry.dotnotation}[/b gold3]' + (f' [dim]v{version}[/dim]' if version else '')
    return Panel(Group(*parts), title=title, border_style='blue', title_align='left')


def render_entry(
    entry: CatalogEntry, formatter, output_file=None, *, example_only: bool = False, version: int | None = None
) -> None:
    mode = output_mode(formatter)
    if example_only:
        if mode in ('json', 'yaml'):
            formatter.print_or_save({'tests': [entry.example()]}, output_file, False)
        else:
            print(entry.example_yaml(), end='')
    elif mode in ('json', 'yaml'):
        formatter.print_or_save({**entry.to_dict(), 'version': version}, output_file, False)
    elif mode == 'plain':
        # Markdown: what the skill's references say, readable by people and agents alike
        print(_info_markdown(entry, version))
    else:
        DefaultConsole().print(_info_panel(entry, version))


def _info_markdown(entry: CatalogEntry, version: int | None) -> str:
    from adare.backend.testfunction.contract import load_library
    from adare.backend.testfunction.contract_render import function_markdown

    text = function_markdown(entry, load_library(), level=1)
    header = f'signature: `{entry.signature()}`' + (f'  v{version}' if version else '')
    if not entry.installed:
        header += '  (bundled but not synced: run `adare test sync`)'
    return text.replace('\n\n', f'\n\n{header}\n\n', 1).rstrip() + '\n'


# ---------------------------------------------------------------------------
# catalog (Markdown reference for skills/docs)
# ---------------------------------------------------------------------------


def catalog_markdown(entries: list[CatalogEntry]) -> str:
    out = [
        '# ADARE test-function catalog',
        '',
        '<!-- Generated by `adare test catalog --markdown`; do not edit by hand. -->',
        '',
        'Reference a test from a playbook `tests:` block by its dotnotation. Required parameters are '
        'marked **bold**. Search instead of scrolling: `adare test search "<goal>"`.',
        '',
    ]
    collection = None
    for entry in entries:
        if entry.collection != collection:
            collection = entry.collection
            out += [f'## {collection}', '']
        out += [f'### `{entry.dotnotation}`', '', entry.summary, '']
        if use_for(entry.doc):
            out += [f'**Use for:** {use_for(entry.doc)}', '']
        out += [f'*{entry.category}*, os: {entry.os}', '']
        if entry.params:
            out += ['| parameter | type | default | description |', '|---|---|---|---|']
            for p in entry.params:
                name = f'**{p.name}**' if p.required else p.name
                default = f'`{p.default!r}`' if not p.required else ''
                type_text = f'`{p.type}`'.replace('|', '\\|') if p.type else ''
                out.append(f'| {name} | {type_text} | {default} | {p.doc.replace("|", chr(92) + "|")} |')
            out.append('')
        out += ['```yaml', entry.example_yaml().rstrip(), '```', '']
    return '\n'.join(out)


# ---------------------------------------------------------------------------
# search (cards) and features
# ---------------------------------------------------------------------------


def _card_text(card: dict) -> str:
    """One result card as plain text: a few short lines per hit."""
    lines = [
        f'## {card["testfunction"]}  [{", ".join(card.get("asserts", []))} · {", ".join(card.get("formats", []))}]'
    ]
    lines.append(card.get('use_for') or card['summary'])
    if card.get('redirected'):
        lines.append(f'chosen because {card["redirected"]}')
    if card.get('matched'):
        lines.append(f'matched: {card["matched"]}')
    if card.get('supports'):
        lines.append(f'supports: {", ".join(card["supports"])}')
    for feature, why in (card.get('does_not_support') or {}).items():
        lines.append(f'does NOT support {feature}: {why}')
    for redirect in card.get('not_for', []):
        lines.append(f'not for: {redirect}')
    lines.append(f'required: {", ".join(card["required"]) or "-"} · os: {card["os"]} · details: {card["next"]}')
    return '\n'.join(lines)


def render_search(result_data: dict, formatter, output_file=None) -> None:
    """``adare test search``: structured cards, or the same cards as text."""
    import yaml

    mode = output_mode(formatter)
    if mode in ('json', 'yaml'):
        formatter.print_or_save(result_data, output_file, False)
        return
    parts = [f'# testfunctions for "{result_data["query"]}" (match: {result_data["match"]})']
    if result_data.get('advice'):
        parts.append(result_data['advice'])
    for gap in result_data.get('known_gaps', []):
        parts.append(f'KNOWN GAP: {gap["gap"]} Instead: {gap["instead"]}')
    for card in result_data['results']:
        parts.append(_card_text(card))
    if result_data['results']:
        first = result_data['results'][0]
        parts.append(
            'example (first result):\n' + yaml.safe_dump({'tests': [first['example']]}, sort_keys=False).rstrip()
        )
    text = '\n\n'.join(parts)
    if mode == 'plain':
        print(text)
    else:
        from rich.markdown import Markdown

        DefaultConsole().console.print(Panel(Markdown(text), border_style='blue'))


def render_features(entries: list[CatalogEntry], feature_id: str | None, formatter, output_file=None) -> None:
    from adare.backend.testfunction.contract import load_library
    from adare.backend.testfunction.contract_render import feature_markdown

    library = load_library()
    mode = output_mode(formatter)
    if feature_id is None:
        if mode in ('json', 'yaml'):
            data = {
                'features': [
                    {
                        'id': f.id,
                        'title': f.title,
                        'summary': f.summary,
                        'supported_by': [e.dotnotation for e in entries if e.contract and f.id in e.contract.features],
                    }
                    for f in library.features.values()
                ],
                'known_gaps': [{'id': g.id, 'gap': g.summary, 'instead': g.instead} for g in library.gaps],
            }
            formatter.print_or_save(data, output_file, False)
            return
        lines = ['feature\tfunctions\ttitle']
        for f in library.features.values():
            count = sum(1 for e in entries if e.contract and f.id in e.contract.features)
            lines.append(f'{f.id}\t{count}\t{f.title}')
        lines += [
            '',
            'details: adare test feature <feature> · functions: adare test search "<goal>" --feature <feature>',
        ]
        lines += ['', 'known gaps (no bundled testfunction does this):']
        lines += [f'- {g.summary} Instead: {g.instead}' for g in library.gaps]
        print('\n'.join(lines))
        return
    feature = library.features[feature_id]
    if mode in ('json', 'yaml'):
        formatter.print_or_save(
            {
                'id': feature.id,
                'title': feature.title,
                'summary': feature.summary,
                'syntax': feature.syntax,
                'example': feature.example,
                'doc': feature.doc,
                'supported_by': [e.dotnotation for e in entries if e.contract and feature.id in e.contract.features],
                'not_supported_by': {
                    e.dotnotation: e.contract.unsupported[feature.id]
                    for e in entries
                    if e.contract and feature.id in e.contract.unsupported
                },
            },
            output_file,
            False,
        )
        return
    text = feature_markdown(feature_id, entries, library)
    if mode == 'plain':
        print(text)
    else:
        from rich.markdown import Markdown

        DefaultConsole().console.print(Panel(Markdown(text), border_style='blue'))
