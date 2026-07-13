"""CLI command handler for the dev-mode vision-LLM GUI agent.

Drives an existing dev session's running VM toward a natural-language goal and,
optionally, records a replayable playbook — the reusable side of the
GUI-automation engine, exposed against an already-installed environment.
"""

import logging
from pathlib import Path

from adare.api import AdareAPI
from adare.cli.dev._helpers import _resolve_session_id
from adare.cli.utils import get_project_path, handle_api_error
from adare.console import print_error_message, print_success_message
from adare.core.dto.devmode import DevGuiAgentRequest

log = logging.getLogger(__name__)


def exec_dev_agent(arguments):
    """Run the vision-LLM GUI agent against a dev session's VM."""
    project_directory = get_project_path(arguments)
    session_id = _resolve_session_id(getattr(arguments, 'session_id', None), project_directory)

    goal = getattr(arguments, 'goal', None)
    goal_file = getattr(arguments, 'goal_file', None)
    if goal_file:
        goal = Path(goal_file).read_text().strip()
    if not goal:
        print_error_message(
            title='No goal provided',
            next_steps=['Pass a goal: --goal "open the Files app"',
                        'Or a file: --goal-file goal.txt'],
        )
        exit(1)

    output = getattr(arguments, 'output', None)
    output_file = Path(output).resolve() if output else None

    print(f"Driving session {session_id} toward goal:\n  {goal}")
    if output_file:
        print(f"Recording playbook to: {output_file}")

    api = AdareAPI()
    result = api.devmode.run_gui_agent(DevGuiAgentRequest(
        session_id=session_id,
        goal=goal,
        output_file=output_file,
        max_steps=getattr(arguments, 'max_steps', None),
        stall_limit=getattr(arguments, 'stall_limit', None),
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
            title=f'Agent finished: {r.summary or r.reason} ({r.steps} steps)',
            next_steps=next_steps or None,
        )
    else:
        print_error_message(
            title=f'Agent did not complete: {r.reason} ({r.steps} steps)',
            next_steps=next_steps or ['Inspect the report and retry with a clearer --goal'],
        )
        exit(1)
