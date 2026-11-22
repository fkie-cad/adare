"""`adare system` - host resources, storage, run capacity and measured run usage."""

import click

from adare.cli.errors import fail
from adare.cli.output import is_structured_output


def _size(num_bytes: float | None) -> str:
    if num_bytes is None:
        return '-'
    value = float(num_bytes)
    for unit in ('B', 'KiB', 'MiB', 'GiB', 'TiB'):
        if abs(value) < 1024 or unit == 'TiB':
            return f'{value:.0f} {unit}' if unit in ('B', 'KiB') else f'{value:.1f} {unit}'
        value /= 1024
    return f'{value:.1f} TiB'


def _data(result):
    if not result.success:
        fail(result.error.code, result.error.message, result.error.solutions)
    return result.data


def _resources_view(data: dict):
    from rich.console import Group
    from rich.table import Table
    from rich.text import Text

    cpu, mem = data['cpu'], data['memory']
    lines = [
        Text.from_markup(f'  CPU      {cpu["percent"]:.0f}% of {cpu["count"]} cores'),
        Text.from_markup(
            f'  Memory   {_size(mem["used_bytes"])} / {_size(mem["total_bytes"])} '
            f'[dim]({_size(mem["available_bytes"])} available)[/dim]'
        ),
    ]
    for disk in data['disks']:
        lines.append(
            Text.from_markup(
                f'  Disk     {_size(disk["used_bytes"])} / {_size(disk["total_bytes"])} '
                f'[dim]({_size(disk["free_bytes"])} free, {disk["path"]})[/dim]'
            )
        )
    table = Table(title='Running VMs', title_justify='left')
    for column in ('Name', 'RAM (RSS)', 'CPU', 'Guest', 'Status'):
        table.add_column(column)
    for vm in data['vms']:
        guest = f'{vm["cpus"] or "?"} vCPU / {_size((vm["memory_mb"] or 0) * 1024**2)}'
        table.add_row(vm['name'], _size(vm['rss_bytes']), f'{vm["cpu_percent"]:.0f}%', guest, vm.get('status') or '-')
    return Group(Text(''), *lines, Text(''), table if data['vms'] else Text('  No VMs running'))


def exec_system_resources(arguments):
    from adare.api import AdareAPI
    from adare.cli.output import emit

    data = _data(AdareAPI().system.get_resources())
    emit(data, rich=lambda: _resources_view(data))


def _storage_view(data: dict):
    from rich.console import Group
    from rich.table import Table
    from rich.text import Text

    categories = Table(title='ADARE storage', title_justify='left')
    categories.add_column('Category')
    categories.add_column('Size', justify='right')
    categories.add_column('Path', style='dim')
    for c in data['categories']:
        categories.add_row(c['label'], _size(c['bytes']), c['path'])
    projects = Table(title='Projects', title_justify='left')
    projects.add_column('Project')
    projects.add_column('Size', justify='right')
    for p in data['projects']:
        projects.add_row(p['name'], _size(p['bytes']))
    orphaned = [o for o in data['disk_owners'] if o['state'] == 'orphaned']
    note = Text.from_markup(
        f'  [yellow]{_size(data["reclaimable_bytes"])}[/yellow] of run disks in {len(orphaned)} group(s) '
        'have no database owner - preview with [bold]adare vm prune[/bold]'
        if orphaned
        else '  No orphaned run disks'
    )
    return Group(Text(''), categories, Text(''), projects, Text(''), note)


def exec_system_storage(arguments):
    from adare.api import AdareAPI
    from adare.cli.output import emit

    data = _data(AdareAPI().system.get_storage(refresh=arguments.refresh))
    emit(data, rich=lambda: _storage_view(data))


def _capacity_view(data: dict):
    from rich.console import Group
    from rich.table import Table
    from rich.text import Text

    room = data['headroom']
    header = Text.from_markup(
        f'  Free for new runs: {_size(room["memory_bytes"])} RAM, {room["cpu_cores"]:.1f} cores, '
        f'{_size(room["disk_bytes"])} disk [dim](after the host reserve)[/dim]'
    )
    table = Table()
    for column in ('Environment', 'Fits', 'Limited by', 'RAM / run', 'Cores / run', 'Disk / run', 'Based on'):
        table.add_column(column)
    for env in data['environments']:
        need = env['need']
        basis = f'{need["measured_runs"]} measured run(s)' if need['source'] == 'measured' else 'configured size'
        table.add_row(
            env['environment'],
            str(env['fits']),
            env['limited_by'],
            _size(need['memory_bytes']),
            f'{need["cpu_cores"]:.1f}',
            _size(need['disk_bytes']),
            basis,
        )
    return Group(Text(''), header, Text(''), table)


def exec_system_capacity(arguments):
    from adare.api import AdareAPI
    from adare.cli.output import emit

    data = _data(AdareAPI().system.get_capacity())
    emit(data, rich=lambda: _capacity_view(data))


def _usage_view(rows: list[dict]):
    from rich.table import Table

    table = Table(title='Measured run usage', title_justify='left')
    for column in ('Started', 'Environment', 'Experiment', 'Peak RAM', 'Avg CPU', 'Disk', 'Duration'):
        table.add_column(column)
    for row in rows:
        duration = row['duration_seconds']
        table.add_row(
            (row['started_at'] or '')[:16].replace('T', ' '),
            row['environment_name'] or '-',
            row['experiment_name'] or '-',
            _size(row['peak_rss_bytes']),
            f'{row["avg_cpu_percent"]:.0f}%',
            _size(row['disk_bytes']),
            f'{duration / 60:.0f} min' if duration else '-',
        )
    return table


def exec_system_usage(arguments):
    from adare.api import AdareAPI
    from adare.cli.output import emit

    rows = _data(AdareAPI().system.get_run_usage(environment_name=arguments.environment, limit=arguments.limit))
    if not rows and not is_structured_output():
        click.echo('No measured runs yet - usage is recorded for every experiment run from now on.')
        return
    emit(rows, rich=lambda: _usage_view(rows))
