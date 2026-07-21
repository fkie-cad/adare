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

    planning = getattr(arguments, 'planning', None)
    grounding = getattr(arguments, 'grounding', None)

    print(f"Driving session {session_id} toward goal:\n  {goal}")
    if planning:
        print("Planning mode: decompose -> checkpoint -> execute -> verify -> backtrack")
    if grounding:
        print("Grounding mode: auto-start LocateAnything (clicks grounded to element boxes)")
    if output_file:
        print(f"Recording playbook to: {output_file}")

    api = AdareAPI()
    result = api.devmode.run_gui_agent(DevGuiAgentRequest(
        session_id=session_id,
        goal=goal,
        output_file=output_file,
        max_steps=getattr(arguments, 'max_steps', None),
        stall_limit=getattr(arguments, 'stall_limit', None),
        interactive=getattr(arguments, 'interactive', False),
        planning=planning,
        grounding=grounding,
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


def exec_dev_grounding_pull(arguments):
    """Pre-download the LocateAnything grounding weights (~7.3 GB).

    Avoids paying the cold-download cost on the first ``--ground`` run's
    ``/health`` poll. Needs the grounding backend installed
    (``uv sync --extra grounding``) plus an ``HF_TOKEN`` and the accepted NVIDIA
    license. If the configured model is already a local directory, nothing is
    downloaded.
    """
    from adare.config.server import LOCATE_MODEL_PATH

    model = getattr(arguments, 'model', None) or LOCATE_MODEL_PATH or 'nvidia/LocateAnything-3B'

    local = Path(model).expanduser()
    if local.exists():
        print_success_message(
            title=f'Model already present locally: {local}',
            next_steps=[f'Use it offline: ADARE_LOCATE_MODEL_PATH={local} HF_HUB_OFFLINE=1 '
                        'adare dev agent --ground --goal "..."'],
        )
        return

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        print_error_message(
            title='Grounding backend not installed',
            next_steps=['Install it: uv sync --extra grounding',
                        'Or point ADARE_LOCATE_PYTHON at a venv that already has it'],
        )
        exit(1)

    print(f'Downloading {model} (~7.3 GB — needs HF_TOKEN and the accepted NVIDIA license) ...')
    try:
        path = snapshot_download(repo_id=model)
    except (OSError, ValueError) as exc:  # gated/auth/HTTP errors subclass OSError
        print_error_message(
            title=f'Could not download {model}: {exc}',
            next_steps=['Accept the license at https://huggingface.co/nvidia/LocateAnything-3B',
                        'Export a token: export HF_TOKEN=hf_...',
                        'Or set ADARE_LOCATE_MODEL_PATH to a local weights directory'],
        )
        exit(1)

    print_success_message(
        title=f'Grounding weights ready: {path}',
        next_steps=['Run: adare dev agent --ground --goal "..."'],
    )
