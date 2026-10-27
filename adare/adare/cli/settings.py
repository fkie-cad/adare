"""`adare system settings` - host limits stored in ~/.adare/settings.json."""

import click

from adare.cli.errors import fail


def _check_name(name: str) -> str:
    from adare.config.settings import SETTINGS

    key = name.upper()
    if not key.startswith('ADARE_'):
        key = f'ADARE_{key}'
    if key not in SETTINGS:
        fail('UNKNOWN_SETTING', f'Unknown setting {name!r}', [f'Known: {", ".join(SETTINGS)}'])
    return key


def _show(value) -> str:
    if value is None:
        return 'off'
    return f'{value:g}' if isinstance(value, float) else str(value)


def _rows() -> list[dict]:
    from adare.config.settings import SETTINGS, resolve

    rows = []
    for name, setting in SETTINGS.items():
        value, source = resolve(name)
        rows.append(
            {
                'name': name,
                'value': value,
                'source': source,
                'default': setting.default,
                'description': setting.description,
            }
        )
    return rows


def exec_settings_list(arguments):
    from rich.table import Table

    from adare.cli.output import emit
    from adare.config.settings import path

    rows = _rows()

    def view():
        table = Table(title=f'ADARE settings ({path()})', title_justify='left')
        for column in ('Setting', 'Value', 'Source', 'Default', 'Description'):
            table.add_column(column)
        for row in rows:
            table.add_row(row['name'], _show(row['value']), row['source'], _show(row['default']), row['description'])
        return table

    emit({'settings': rows}, rich=view)


def exec_settings_get(arguments):
    from adare.config.settings import resolve

    name = _check_name(arguments.name)
    value, source = resolve(name)
    click.echo(f'{name}={_show(value)}  ({source})')


def exec_settings_set(arguments):
    import os

    from adare.config.settings import set_value

    name = _check_name(arguments.name)
    try:
        value = set_value(name, arguments.value)
    except ValueError as e:
        fail('INVALID_SETTING', str(e), ['See the allowed values: adare system settings list'])
    click.echo(f'{name}={_show(value)} saved')
    if os.environ.get(name, '').strip():
        click.echo(f'Note: the environment variable {name} is set in this shell and takes precedence.')


def exec_settings_unset(arguments):
    from adare.config.settings import SETTINGS, unset

    name = _check_name(arguments.name)
    if unset(name):
        click.echo(f'{name} removed; back to the default ({_show(SETTINGS[name].default)})')
    else:
        click.echo(f'{name} was not set')
