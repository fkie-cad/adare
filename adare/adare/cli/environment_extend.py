"""CLI handler for `adare environment extend`."""

import logging
from pathlib import Path

from adare.api import AdareAPI
from adare.cli.utils import handle_api_error
from adare.console import console, print_error_message, print_success_message
from adare.core.dto.environment import EnvironmentExtendRequest

log = logging.getLogger(__name__)


def _parse_install(spec: str) -> tuple[str, str]:
    """Split an `--install "name:command"` value on the FIRST colon."""
    if ':' not in spec:
        raise ValueError(
            f'--install value "{spec}" is missing a ":" separating name from command'
        )
    name, command = spec.split(':', 1)
    return name.strip(), command.strip()


def exec_environment_extend(arguments):
    """
    Extend an environment (or VM) into a new environment using the AdareAPI.
    """
    try:
        installs = [_parse_install(spec) for spec in arguments.install]
    except ValueError as e:
        print_error_message(title=str(e))
        exit(1)
        return

    from_file = Path(arguments.from_file) if arguments.from_file else None

    if arguments.console and not arguments.interactive:
        console.print(
            '  [yellow]Note:[/yellow] --console has no effect without '
            '--interactive; ignoring it.'
        )

    api = AdareAPI()
    result = api.environment.extend(EnvironmentExtendRequest(
        source=arguments.source,
        name=arguments.name,
        installs=installs,
        from_file=from_file,
        shell=arguments.shell,
        cwd=arguments.cwd,
        interactive=arguments.interactive,
        console=arguments.console,
        ram=arguments.ram,
        cpus=arguments.cpus,
        disk_name=arguments.disk_name,
        compress=arguments.compress,
        description=arguments.description,
        tags=list(arguments.tag),
        force=arguments.force,
        project=arguments.project,
    ))

    if result.success:
        if result.data.discarded:
            print_success_message(
                title='Session discarded — no environment created.',
                next_steps=result.data.next_steps,
                tip=result.data.tip
            )
        else:
            print_success_message(
                title=f'Environment "{result.data.name}" created successfully!',
                location=str(result.data.file_path) if result.data.file_path else None,
                next_steps=result.data.next_steps,
                tip=result.data.tip
            )
    else:
        handle_api_error(result)
