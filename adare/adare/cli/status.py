"""Status command - quick overview of ADARE system state.

Each section is collected independently so one broken subsystem does not blank
the others; a section that cannot be read reports ``available: false`` and the
reason instead of a bare "unavailable". Only the failures each lookup is known to
raise are caught (database/filesystem errors and ADARE's own LoggedException);
anything else is a bug and propagates.
"""

import logging
from typing import Any

from sqlalchemy.exc import SQLAlchemyError

from adare.exceptions import LoggedException

log = logging.getLogger(__name__)

# What a status section may fail with. Kept narrow on purpose (no `Exception`).
_SECTION_ERRORS = (SQLAlchemyError, OSError, LoggedException)


def _project_section() -> dict[str, Any]:
    from adare.backend.basics import determine_projectdirectory

    try:
        project_directory = determine_projectdirectory(None, silent=True)
    except _SECTION_ERRORS as e:
        log.debug(f'status: project lookup failed: {e}')
        return {'available': False, 'name': None, 'path': None, 'error': str(e)}
    if project_directory is None:
        return {'available': True, 'name': None, 'path': None, 'error': None}
    return {'available': True, 'name': project_directory.name, 'path': str(project_directory),
            'error': None}


def _sessions_section(api, project_path: str | None) -> dict[str, Any]:
    from pathlib import Path

    from adare.core.dto.devmode import DevSessionListRequest

    empty = {'available': False, 'total': 0, 'running': 0, 'stopped': 0, 'other': 0}
    try:
        result = api.devmode.list_sessions(DevSessionListRequest(
            project_path=Path(project_path) if project_path else None,
        ))
    except _SECTION_ERRORS as e:
        log.debug(f'status: session lookup failed: {e}')
        return {**empty, 'error': str(e)}
    if not result.success:
        return {**empty, 'error': result.error.message}
    sessions = result.data or []
    running = sum(1 for s in sessions if s.status == 'running')
    stopped = sum(1 for s in sessions if s.status == 'stopped')
    return {'available': True, 'total': len(sessions), 'running': running, 'stopped': stopped,
            'other': len(sessions) - running - stopped, 'error': None}


def _vms_section(api) -> dict[str, Any]:
    try:
        result = api.vm.list_instances()
    except _SECTION_ERRORS as e:
        log.debug(f'status: VM instance lookup failed: {e}')
        return {'available': False, 'instances': 0, 'error': str(e)}
    if not result.success:
        return {'available': False, 'instances': 0, 'error': result.error.message}
    return {'available': True, 'instances': len(result.data or []), 'error': None}


def _database_section(api) -> dict[str, Any]:
    empty = {'available': False, 'initialized': False, 'valid': False, 'location': None,
             'pending_migrations': [], 'errors': []}
    try:
        result = api.manage.get_db_status()
    except _SECTION_ERRORS as e:
        log.debug(f'status: database status failed: {e}')
        return {**empty, 'errors': [str(e)]}
    if not result.success:
        return {**empty, 'errors': [result.error.message]}
    status = result.data
    return {
        'available': bool(status.global_db_accessible),
        'initialized': bool(status.global_db_exists),
        'valid': bool(status.valid),
        'location': str(status.global_db_location) if status.global_db_location else None,
        'pending_migrations': list(status.pending_migrations or []),
        'errors': list(status.errors or []),
    }


def collect_status(api=None) -> dict[str, Any]:
    """Gather the status overview as a structured dict (also used by ``--json``)."""
    if api is None:
        from adare.api import AdareAPI
        api = AdareAPI()
    project = _project_section()
    return {
        'project': project,
        'sessions': _sessions_section(api, project['path']),
        'vms': _vms_section(api),
        'database': _database_section(api),
    }


def _render_rich(status: dict[str, Any]):
    from rich.console import Group
    from rich.text import Text

    def line(label: str, markup: str) -> Text:
        return Text.from_markup(f'  {label:<11} {markup}')

    project, sessions = status['project'], status['sessions']
    vms, database = status['vms'], status['database']

    if not project['available']:
        project_line = '[dim]unknown[/dim]'
    elif project['name']:
        project_line = f'[green]{project["name"]}[/green] [dim]({project["path"]})[/dim]'
    else:
        project_line = '[dim]none (not inside a registered project directory)[/dim]'

    if not sessions['available']:
        sessions_line = '[dim]unavailable[/dim]'
    else:
        sessions_line = f'[green]{sessions["running"]} running[/green], {sessions["stopped"]} stopped'
        if sessions['other']:
            sessions_line += f', {sessions["other"]} other'

    vms_line = f'{vms["instances"]} instances' if vms['available'] else '[dim]unavailable[/dim]'

    if not database['available']:
        database_line = '[red]unavailable[/red]'
    elif not database['valid']:
        database_line = '[yellow]initialized, has issues[/yellow] (run: adare db status)'
    else:
        database_line = '[green]initialized[/green]'
    if database['pending_migrations']:
        database_line += f', {len(database["pending_migrations"])} pending migration(s)'

    return Group(
        Text(''),
        Text.from_markup('[bold]ADARE Status[/bold]'),
        Text(''),
        line('Project:', project_line),
        line('Sessions:', sessions_line),
        line('VMs:', vms_line),
        line('Database:', database_line),
        Text(''),
    )


def exec_status(arguments):
    """Show quick overview of current ADARE state."""
    from adare.cli.output import emit

    status = collect_status()
    emit(status, rich=lambda: _render_rich(status))
