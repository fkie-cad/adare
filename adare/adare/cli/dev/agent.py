"""CLI command handler for the dev-mode vision-LLM GUI agent.

Drives an existing dev session's running VM toward a natural-language goal and,
optionally, records a replayable playbook — the reusable side of the
GUI-automation engine, exposed against an already-installed environment.
"""

import logging
import sys
from pathlib import Path

from adare.api import AdareAPI
from adare.cli.dev._helpers import _resolve_session_id
from adare.cli.utils import handle_api_error
from adare.console import print_error_message, print_success_message
from adare.core.dto.devmode import DevGuiAgentRequest, DevSessionStateRequest
from adare.exceptions import NoProjectFoundError

log = logging.getLogger(__name__)


def exec_dev_agent(arguments):
    """Run the vision-LLM GUI agent against a dev session's VM."""
    session_id_arg = getattr(arguments, 'session_id', None)
    project_directory = _resolve_project_directory(arguments, session_id_arg)
    session_id = _resolve_session_id(session_id_arg, project_directory)

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
    as_experiment = getattr(arguments, 'as_experiment', None)

    # --as-experiment owns the output location (it records into the scaffolded
    # experiment's playbook.yml), so it is mutually exclusive with -o/--out.
    if as_experiment and output_file:
        print_error_message(
            title='--as-experiment cannot be combined with -o/--out',
            next_steps=['Use --as-experiment NAME to record into experiments/NAME/',
                        'Or use -o PATH to record a standalone playbook'],
        )
        exit(1)

    api = AdareAPI()

    # Scaffold the experiment (files only, no DB load) and point the recorder at
    # its playbook.yml before the run.
    exp = None
    environment_name = None
    if as_experiment:
        exp, environment_name = _scaffold_experiment(api, project_directory, session_id, as_experiment)
        output_file = exp.playbookfile

    planning = getattr(arguments, 'planning', None)
    grounding = getattr(arguments, 'grounding', None)
    video = getattr(arguments, 'video', None)
    # Progress defaults to on only when stdout is an interactive terminal, so a
    # piped / redirected run stays silent as before.
    progress = getattr(arguments, 'progress', None)
    if progress is None:
        progress = sys.stdout.isatty()

    _announce_agent_run(session_id, goal, planning, grounding, video, exp, output_file)

    try:
        result = api.devmode.run_gui_agent(DevGuiAgentRequest(
            session_id=session_id,
            goal=goal,
            output_file=output_file,
            max_steps=getattr(arguments, 'max_steps', None),
            stall_limit=getattr(arguments, 'stall_limit', None),
            interactive=getattr(arguments, 'interactive', False),
            planning=planning,
            grounding=grounding,
            progress=progress,
            video=video,
        ))
    except KeyboardInterrupt:
        # Fallback only: the service installs a cooperative SIGINT handler that
        # finalizes the run, so this rarely fires. Mirrors cli/dev/session.py.
        print("\n\nAgent run interrupted — the VM is still running "
              f"(drive it with: adare dev agent -s {session_id} ...)")
        exit(1)

    if not result.success:
        # A fresh --as-experiment scaffold that recorded nothing (e.g. the
        # grounding server or ffmpeg failed to start) would otherwise be left
        # behind and block a retry with "experiment already exists". Roll it
        # back here; a run that recorded screenshots is kept (see helper).
        if exp is not None:
            _cleanup_empty_scaffold(exp)
        handle_api_error(result)
        return

    r = result.data

    # Finish the experiment scaffold: write metadata.yml (environments + a
    # description/tag from the goal). Done whether or not the run fully
    # succeeded, so a recorded-but-interrupted experiment is still loadable.
    if exp is not None:
        try:
            _write_experiment_metadata(exp, environment_name, goal)
        except OSError as exc:
            log.warning('Could not write experiment metadata: %s', exc)

    next_steps = _agent_next_steps(r, exp, as_experiment, session_id)

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


def _resolve_project_directory(arguments, session_id):
    """Project from cwd/-p, else from the named session's stored project_path.

    `adare dev agent` needs a project to filter sessions and to place
    --as-experiment output. Normally that comes from the cwd or -p; but a
    session already records its project_path, so with -s we can run from
    anywhere. Raises NoProjectFoundError only when neither the location nor a
    resolvable session yields a project.
    """
    from adare.backend.basics import determine_projectdirectory
    project = getattr(arguments, 'project', None)
    # Quiet the "project not found at cwd" log line only when we have a session
    # to fall back to (otherwise keep the helpful message).
    project_directory = determine_projectdirectory(project, silent=bool(session_id))
    if project_directory:
        return project_directory
    if session_id:
        from adare.database.api.devmode import DevModeApi
        session = DevModeApi().get_session(session_id)
        if session:
            resolved = Path(session.project_path)
            log.info('Resolved project from session %s: %s', session_id, resolved)
            return resolved
    raise NoProjectFoundError(log, specified_project=project)


def _announce_agent_run(session_id, goal, planning, grounding, video, exp, output_file):
    """Print what the run will do before it starts."""
    print(f"Driving session {session_id} toward goal:\n  {goal}")
    if planning:
        print("Planning mode: decompose -> checkpoint -> execute -> verify -> backtrack")
    if grounding:
        print("Grounding mode: auto-start LocateAnything (clicks grounded to element boxes)")
    if video:
        print("Recording video of the run (MP4 via ffmpeg)")
    if exp is not None:
        print(f"Creating experiment files under: {exp.path}")
    elif output_file:
        print(f"Recording playbook to: {output_file}")


def _agent_next_steps(r, exp, as_experiment, session_id):
    """Build the CLI next-steps list from the agent result + optional experiment."""
    next_steps = []
    if r.report_path:
        next_steps.append(f'View the screenshot report: {r.report_path}')
    if r.video_path:
        next_steps.append(f'Watch the run video: {r.video_path}')
    if exp is not None:
        next_steps.append(
            f'Files created — load it later with: adare experiment load {as_experiment}')
        next_steps.append(f'Replay it now: adare dev playbook {session_id} -f {exp.playbookfile}')
    elif r.playbook_path:
        next_steps.append(f'Replay it: adare dev playbook {session_id} -f {r.playbook_path}')
    return next_steps


def _scaffold_experiment(api, project_directory, session_id, name):
    """Create experiments/<name>/ (dirs only) and return (ExperimentDirectory, env_name).

    Errors out (exit 1) if the experiment already exists or the session's
    environment cannot be resolved — we never overwrite an existing experiment.
    """
    from adare.backend.experiment.directory import ExperimentDirectory

    state = api.devmode.get_state(DevSessionStateRequest(session_id=session_id))
    if not state.success:
        handle_api_error(state)
        exit(1)
    environment_name = state.data.environment_name

    exp = ExperimentDirectory(project_directory, name)
    if exp.exists():
        print_error_message(
            title=f"Experiment '{name}' already exists at {exp.path}",
            next_steps=['Pick another --as-experiment NAME',
                        f'Or remove the existing one: rm -rf {exp.path}'],
        )
        exit(1)
    exp.create(empty=True)  # directories only — the recorder fills playbook.yml + img/
    return exp, environment_name


def _cleanup_empty_scaffold(exp):
    """Remove a freshly-scaffolded experiment that never recorded anything.

    A pre-run setup failure (grounding server won't start, ffmpeg missing,
    session/VM gone) exits before the agent loop captures a single screenshot,
    leaving an empty scaffold that blocks re-running with the same
    --as-experiment NAME. Delete it only when ``img/`` holds no screenshots, so
    a partially-recorded (interrupted-but-loadable) run is preserved.
    """
    from adare.backend.experiment.exceptions import ExperimentRemovalError

    try:
        recorded = exp.img.exists() and any(exp.img.iterdir())
    except OSError:
        return  # can't inspect it — leave it alone rather than risk deletion
    if recorded:
        return
    try:
        exp.remove()
        print(f'Cleaned up empty experiment scaffold: {exp.path}')
    except (ExperimentRemovalError, OSError) as exc:
        log.warning('Could not remove empty experiment scaffold %s: %s', exp.path, exc)


def _write_experiment_metadata(exp, environment_name, goal):
    """Render the metadata template and patch environments + a goal description."""
    import jinja2
    import yaml

    import adare

    template = (Path(adare.__file__).parent.parent / 'appdata' / 'templates'
                / 'experiment' / 'metadata.yml')
    rendered = jinja2.Template(template.read_text()).render(experiment=exp.experiment)
    data = yaml.safe_load(rendered) or {}
    if environment_name:
        data['environments'] = [environment_name]
    data['description'] = f'Recorded by the ADARE GUI agent. Goal: {goal}'
    data['tags'] = ['gui-agent']
    exp.metadatafile.write_text(
        yaml.safe_dump(data, sort_keys=False, default_flow_style=False))


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
