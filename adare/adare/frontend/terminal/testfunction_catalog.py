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

from adare.backend.testfunction.catalog import CatalogEntry
from adare.frontend.terminal.console import DefaultConsole


def output_mode(formatter) -> str:
    """``json``/``yaml`` (structured), ``plain`` (TSV) or ``rich``."""
    value = formatter.format_type.value
    if value in ('json', 'yaml', 'plain'):
        return value
    return 'rich' if sys.stdout.isatty() else 'plain'


def _default_text(entry_param) -> str:
    return '' if entry_param.required else repr(entry_param.default)


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
        parts.append(Text(entry.doc.split('\nArgs:')[0].strip()))
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
        header = entry.signature() + (f'  v{version}' if version else '')
        lines = [header, entry.summary, '', 'parameter\ttype\trequired\tdefault\tdescription']
        lines += [f'{p.name}\t{p.type}\t{str(p.required).lower()}\t{_default_text(p)}\t{p.doc}' for p in entry.params]
        lines += ['', entry.example_yaml().rstrip()]
        print('\n'.join(lines))
    else:
        DefaultConsole().print(_info_panel(entry, version))


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
