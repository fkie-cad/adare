"""CLI handler for ``adare dev author-ai`` — LLM-author a UI-action playbook.

Where ``adare dev author`` has a human plan the steps in text, ``author-ai`` has
a cloud vision model author the whole ``actions:`` playbook from a screenshot of
the session VM. The harness validates the playbook against the real schema and,
with ``--replay``, verifies it live on the VM and repairs on failure, then picks
the best model. See ``backend/experiment/vlm/authoring/FLOW.md``.
"""

import logging
from pathlib import Path

from adare.api import AdareAPI
from adare.cli.dev._helpers import _resolve_session_id
from adare.cli.utils import get_project_path, handle_api_error
from adare.console import print_error_message, print_success_message
from adare.core.dto.devmode import DevAuthorPlaybookRequest

log = logging.getLogger(__name__)


def exec_dev_author_ai(arguments):
    """Have a vision LLM author a playbook against a dev session's VM."""
    project_directory = get_project_path(arguments)
    session_id = _resolve_session_id(getattr(arguments, 'session_id', None), project_directory)

    goal = getattr(arguments, 'goal', None)
    if not goal:
        print_error_message(
            title='No goal given',
            next_steps=['Pass a natural-language goal: --goal "open the File menu"'],
        )
        exit(1)

    models_arg = getattr(arguments, 'models', None)
    models = [m.strip() for m in models_arg.split(',') if m.strip()] if models_arg else None

    output = getattr(arguments, 'output', None)
    output_file = Path(output).resolve() if output else None

    api = AdareAPI()
    request = DevAuthorPlaybookRequest(
        session_id=session_id,
        goal=goal,
        models=models,
        rounds=getattr(arguments, 'rounds', 3),
        replay=getattr(arguments, 'replay', False),
        os_key=getattr(arguments, 'os_key', 'linux'),
        output_file=output_file,
    )

    print(f"Authoring a playbook against session {session_id}.")
    print(f"Goal: {goal}")
    if request.replay:
        print("Live replay-verify enabled (serialized on the session VM).\n")
    else:
        print("Author + validate only (no live replay).\n")

    result = api.devmode.author_playbook(request)
    if not result.success:
        handle_api_error(result)
        return

    r = result.data
    print("=== authoring summary ===")
    for rnd in r.rounds:
        flags = f"valid={rnd.valid} replayed={rnd.replayed} passing={rnd.passing}"
        line = f"  {rnd.model} round {rnd.round}: {flags}"
        if rnd.error:
            line += f" | {rnd.error}"
        print(line)

    next_steps = []
    if r.output_file:
        next_steps.append(f'Replay it: adare dev playbook -s {session_id} -f {r.output_file}')
    elif r.playbook_yaml:
        next_steps.append('Re-run with -o <path> to save the authored playbook')

    if r.success:
        verdict = 'valid + replayed clean' if r.best_passing else 'valid'
        print_success_message(
            title=f'Authored a {verdict} playbook (best model: {r.best_model})',
            next_steps=next_steps or None,
        )
    else:
        print_error_message(
            title='No usable playbook authored',
            next_steps=['Refine the --goal', 'Inspect the per-round errors above'],
        )
        exit(1)
