"""``adare agent``: set up AI coding agents (Claude Code, OpenCode) to drive ADARE."""

import logging
from dataclasses import asdict

from rich.table import Table

from adare.backend.agent_setup import CLIENTS, SCOPES, SkillLink, setup, skills_source, status
from adare.exceptions import LoggedErrorException
from adare.frontend.terminal.console import DefaultConsole
from adare.frontend.terminal.testfunction_catalog import output_mode

log = logging.getLogger(__name__)

_STYLE = {
    'ok': 'green',
    'linked': 'green',
    'copied': 'green',
    'updated': 'yellow',
    'missing': 'dim',
    'stale': 'red',
    'conflict': 'red',
    'foreign-link': 'yellow',
}

_NEXT_STEPS = '''
Next steps:
  Claude Code  skills load automatically (restart running sessions); start with the adare-overview skill.
  OpenCode     enable the skills plugin: add "plugin": ["opencode-skills"] to opencode.json,
               or reference skills/*/SKILL.md from AGENTS.md (see docsrc/mcp-clients.md).
  MCP          only for hosts without a shell or for live VM hands:
               claude mcp add adare -- adare mcp serve        (whole lifecycle as tools)
               adare dev mcp -s <session>                     (click/type/screenshot one running VM)
'''


class SkillsSourceNotFoundError(LoggedErrorException):
    pass


def _source():
    source = skills_source()
    if source is None:
        raise SkillsSourceNotFoundError(
            log,
            'No ADARE skills directory found',
            possible_solutions=['run from an ADARE source checkout, or refresh appdata with `make update`'],
        )
    return source


def _render(links: list[SkillLink], title: str) -> None:
    from adare.run import get_formatter_from_context

    formatter, output_file, _dual = get_formatter_from_context()
    mode = output_mode(formatter)
    if mode in ('json', 'yaml'):
        records = [{**asdict(link), 'target': str(link.target)} for link in links]
        formatter.print_or_save({'skills': records}, output_file, False)
    elif mode == 'plain':
        print('client\tscope\tskill\tstatus\ttarget\tdetail')
        for link in links:
            print(f'{link.client}\t{link.scope}\t{link.skill}\t{link.status}\t{link.target}\t{link.detail}')
    else:
        table = Table(title=title, header_style='bold')
        for column in ('client', 'scope', 'skill', 'status', 'target'):
            table.add_column(column, no_wrap=column != 'target')
        for link in links:
            style = _STYLE.get(link.status, '')
            state = f'[{style}]{link.status}[/{style}]' + (f' [dim]({link.detail})[/dim]' if link.detail else '')
            table.add_row(link.client, link.scope, link.skill, state, str(link.target))
        DefaultConsole().print(table)


def _human() -> bool:
    from adare.run import get_formatter_from_context

    return output_mode(get_formatter_from_context()[0]) == 'rich'


def _expand(value: str, choices: tuple[str, ...]) -> tuple[str, ...]:
    return choices if value == 'all' else (value,)


def exec_agent_setup(arguments) -> None:
    links = setup(
        _source(),
        _expand(arguments.client, CLIENTS),
        _expand(arguments.scope, SCOPES),
        copy=arguments.copy,
        force=arguments.force,
        dry_run=arguments.dry_run,
    )
    _render(links, 'ADARE skills' + (' (dry run)' if arguments.dry_run else ''))
    blocked = [link for link in links if link.status in ('conflict', 'foreign-link')]
    if blocked and _human():
        print(f'{len(blocked)} skill(s) left untouched; inspect them, then re-run with --force to re-point links.')
    if _human():
        print(_NEXT_STEPS)


def exec_agent_status(arguments) -> None:
    source = _source()
    links = status(source, _expand(arguments.client, CLIENTS), _expand(arguments.scope, SCOPES))
    _render(links, f'ADARE skills (source: {source})')
