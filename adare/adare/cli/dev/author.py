"""CLI command handler for authoring a playbook from human text steps.

Where ``adare dev agent`` lets a vision model plan, ``adare dev author`` lets a
human plan in text: each step names *what* to do ("click the Bold button") and
LocateAnything (ADARE_LOCATE_URL) grounds *where*. The recorded playbook replays
deterministically through the CV/OCR engine, identical in shape to an
agent-recorded one.
"""

import logging
from pathlib import Path

from adare.api import AdareAPI
from adare.cli.dev._helpers import _resolve_session_id
from adare.cli.utils import get_project_path, handle_api_error
from adare.console import print_error_message, print_success_message
from adare.core.dto.devmode import DevGuiAuthorRequest

log = logging.getLogger(__name__)


def exec_dev_author(arguments):
    """Author a playbook from text steps against a dev session's VM."""
    project_directory = get_project_path(arguments)
    session_id = _resolve_session_id(getattr(arguments, 'session_id', None), project_directory)

    script = None
    script_file = getattr(arguments, 'script_file', None)
    if script_file:
        script = Path(script_file).read_text()
    interactive = getattr(arguments, 'interactive', False)

    if not script and not interactive:
        print_error_message(
            title='Nothing to author',
            next_steps=['Pass a script: --script-file steps.txt',
                        'Or author step-by-step: --interactive'],
        )
        exit(1)

    output = getattr(arguments, 'output', None)
    output_file = Path(output).resolve() if output else None

    if interactive and not script:
        print(f"Authoring interactively against session {session_id}.")
    else:
        print(f"Authoring playbook against session {session_id} from script.")
    if output_file:
        print(f"Recording playbook to: {output_file}")

    api = AdareAPI()
    result = api.devmode.run_gui_author(DevGuiAuthorRequest(
        session_id=session_id,
        script=script,
        output_file=output_file,
        interactive=interactive,
    ))

    if not result.success:
        handle_api_error(result)
        return

    r = result.data
    next_steps = []
    if r.report_path:
        next_steps.append(f'View the screenshot report: {r.report_path}')
    if r.playbook_path:
        next_steps.append(f'Replay it: adare dev playbook {session_id} -f {r.playbook_path}')

    if r.success:
        print_success_message(
            title=f'Authored: {r.summary or r.reason} ({r.steps} steps)',
            next_steps=next_steps or None,
        )
    else:
        print_error_message(
            title=f'Authoring did not complete: {r.reason} ({r.steps} steps)',
            next_steps=next_steps or ['Inspect the step screenshots and retry'],
        )
        exit(1)
