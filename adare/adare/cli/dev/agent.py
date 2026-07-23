"""CLI command handler for the dev-mode vision-LLM GUI agent.

Drives an existing dev session's running VM toward a natural-language goal and,
optionally, records a replayable playbook — the reusable side of the
GUI-automation engine, exposed against an already-installed environment.
"""

import logging
import shutil
import sys
from pathlib import Path

from adare.api import AdareAPI
from adare.cli.dev._helpers import _resolve_session_id
from adare.cli.utils import handle_api_error
from adare.console import print_error_message, print_success_message
from adare.core.dto.devmode import (
    DevCheckpointCreateRequest,
    DevCheckpointDeleteRequest,
    DevCheckpointRestoreRequest,
    DevGuiAgentRequest,
    DevPlaybookExecuteRequest,
    DevSessionStartRequest,
    DevSessionStateRequest,
    DevSessionStopRequest,
)
from adare.exceptions import NoProjectFoundError

log = logging.getLogger(__name__)

# Name of the baseline checkpoint created before an agent run so --verify can
# replay the recorded playbook from the same VM state the agent started from.
VERIFY_CHECKPOINT = 'agent_pre_verify'


def exec_dev_agent(arguments):
    """Run the vision-LLM GUI agent against a dev session's VM.

    Two ways in: attach to a running session with ``-s``, or boot a fresh
    ephemeral VM from an environment with ``-e`` (driven, then torn down unless
    ``--keep``). When a playbook is recorded, the run is validated at the end:
    always parsed, and — with ``--verify`` (default) — replayed on the VM from a
    pre-run baseline checkpoint.
    """
    session_id_arg = getattr(arguments, 'session_id', None)
    environment = getattr(arguments, 'environment', None)
    keep = getattr(arguments, 'keep', False)

    # -e (boot a fresh ephemeral VM) and -s (attach to a running one) are two
    # different entry points — pick exactly one.
    if environment and session_id_arg:
        print_error_message(
            title='Choose one: boot a new VM with -e OR attach with -s',
            next_steps=[
                '-e/--environment NAME boots a fresh VM, drives it, then tears it down',
                '-s/--session ID attaches to an already-running session',
            ],
        )
        exit(1)

    goal = _resolve_goal(arguments)

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

    verify = getattr(arguments, 'verify', True)
    # Replay validation needs a recorded playbook to replay against the VM; a
    # bare drive (no -o / --as-experiment) has nothing to replay.
    want_replay = verify and bool(as_experiment or output_file)

    api = AdareAPI()

    # Resolve the target session: boot a fresh ephemeral one from -e, or attach
    # to -s (or auto-detect). A boot failure exits before any scaffold exists,
    # so there is nothing to clean up.
    ephemeral = environment is not None
    if ephemeral:
        project_directory = _resolve_project_directory(arguments, None)
        # Guard the --as-experiment name BEFORE the (expensive) VM boot: the
        # collision check is pure filesystem, so a name clash should abort
        # instantly instead of after a ~minute of booting + snapshotting.
        if as_experiment:
            _ensure_experiment_available(project_directory, as_experiment)
        session_id = _boot_ephemeral_session(api, project_directory, environment)
    else:
        project_directory = _resolve_project_directory(arguments, session_id_arg)
        session_id = _resolve_session_id(session_id_arg, project_directory)
        if as_experiment:
            _ensure_experiment_available(project_directory, as_experiment)

    planning = getattr(arguments, 'planning', None)
    grounding = getattr(arguments, 'grounding', None)
    video = getattr(arguments, 'video', None)
    # Progress defaults to on only when stdout is an interactive terminal, so a
    # piped / redirected run stays silent as before.
    progress = getattr(arguments, 'progress', None)
    if progress is None:
        progress = sys.stdout.isatty()

    # Lay out the whole plan up front, then mark each phase as it starts — the
    # boot / checkpoint / grounding phases are long and log-noisy, so without
    # this the run looks stuck or broken.
    _announce_agent_run(session_id, goal, planning, grounding, video, as_experiment,
                        output_file, ephemeral, environment, keep, want_replay)

    baseline_created = False
    try:
        # Phase: baseline checkpoint BEFORE the agent runs so --verify can replay
        # from the same VM state the agent started from. If it can't be created,
        # degrade to parse-only validation rather than aborting.
        if want_replay:
            baseline_created = _create_verify_baseline(api, session_id)
            if not baseline_created:
                want_replay = False

        # Phase: scaffold the experiment (files only, no DB load) and point the
        # recorder at its playbook.yml. With -e we already know the environment,
        # so skip the get_state round-trip.
        exp = None
        environment_name = environment
        if as_experiment:
            exp, environment_name = _scaffold_experiment(
                api, project_directory, session_id, as_experiment,
                known_environment=environment)
            output_file = exp.playbookfile
            print(f"→ Experiment files ready: {exp.path}")

        # Phase: drive. Grounding weights can be a slow first-run download, so
        # say so before the (otherwise silent) server startup.
        if grounding:
            print("→ Starting the LocateAnything grounding server "
                  "(first run downloads ~7.3 GB — this can take several minutes) ...")
        print("→ Driving the VM toward the goal (per-step progress follows) ...")

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
                reasoning=getattr(arguments, 'reasoning', True),
                video=video,
            ))
        except KeyboardInterrupt:
            # Fallback only: the service installs a cooperative SIGINT handler
            # that finalizes the run, so this rarely fires. The finally block
            # tears down an ephemeral VM; an attached one is left running.
            if ephemeral and not keep:
                print("\n\nAgent run interrupted — tearing down the ephemeral VM ...")
            else:
                print("\n\nAgent run interrupted — the VM is still running "
                      f"(drive it with: adare dev agent -s {session_id} ...)")
            exit(1)

        if not result.success:
            # A fresh --as-experiment scaffold that recorded nothing (e.g. the
            # grounding server or ffmpeg failed to start) would otherwise be left
            # behind and block a retry with "experiment already exists". Roll it
            # back here; a run that recorded screenshots is kept (see helper).
            salvaged = _cleanup_empty_scaffold(exp) if exp is not None else None
            # The GROUNDING_ERROR/VIDEO_ERROR message carries a " See the server
            # log: <scaffold path>" suffix that names a file the cleanup just
            # deleted. Strip that stale pointer, then print an authoritative one
            # naming the durable copy. handle_api_error() exits, so the pointer is
            # printed first (it still reads as belonging to the error above it).
            if salvaged is not None and result.error and result.error.code in (
                    'GROUNDING_ERROR', 'VIDEO_ERROR'):
                result.error.message = _strip_log_hint(result.error.message)
                print(f'Diagnostic log saved to: {salvaged / "locate_server.log"}')
            handle_api_error(result)  # exits (finally still tears down)
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

        # A cooperatively-interrupted run (Ctrl-C) finalizes whatever partial
        # recording it had; that is not the intended playbook, so never
        # replay-verify it.
        interrupted = r.reason == 'interrupted by user'

        # Validation: always parse a produced playbook; replay-verify only a
        # complete, non-interrupted run.
        playbook_path = str(exp.playbookfile) if exp is not None else r.playbook_path
        parse_ok = True
        replay = None
        if playbook_path and Path(playbook_path).exists():
            parse_ok = _parse_validate(playbook_path)
            if want_replay and parse_ok and not interrupted:
                replay = _verify_by_replay(api, session_id, playbook_path)
            elif want_replay and interrupted:
                print('Verification skipped — the run was interrupted (Ctrl-C).')

        replay_failed = replay is not None and not _replay_ok(replay)
        validation_failed = (not parse_ok) or replay_failed

        next_steps = _agent_next_steps(r, exp, as_experiment, session_id, ephemeral, keep)
        if replay is not None:
            next_steps.insert(0, _replay_summary_line(replay))

        if r.success and not validation_failed:
            print_success_message(
                title=f'Agent finished: {r.summary or r.reason} ({r.steps} steps)',
                next_steps=next_steps or None,
            )
        elif r.success and validation_failed:
            # The recording is still the deliverable — keep it, but flag the
            # failure and exit non-zero so CI can catch it.
            print_error_message(
                title=f'Agent finished ({r.steps} steps) but validation failed',
                next_steps=next_steps or ['Inspect the recording and screenshot report'],
            )
        else:
            print_error_message(
                title=f'Agent did not complete: {r.reason} ({r.steps} steps)',
                next_steps=next_steps or ['Inspect the report and retry with a clearer --goal'],
            )

        if not (r.success and not validation_failed):
            exit(1)
    finally:
        _post_run_cleanup(api, session_id, ephemeral, keep, baseline_created)


def _resolve_goal(arguments):
    """Read the goal from --goal or --goal-file; exit(1) if neither is given."""
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
    return goal


def _boot_ephemeral_session(api, project_directory, environment):
    """Boot a fresh dev session from an environment; return its session_id.

    Exits (1) with a clear error if the environment is unknown or the VM cannot
    be booted — nothing has been scaffolded yet, so there is nothing to tear down.
    """
    print(f"Booting a fresh VM from environment '{environment}' ...")
    result = api.devmode.start_session(DevSessionStartRequest(
        project_path=project_directory,
        environment_name=environment,
        name=None,
    ))
    if not result.success:
        handle_api_error(result)  # exits
    session_id = result.data.session_id
    print(f"Booted ephemeral session {session_id}")
    return session_id


def _teardown_session(api, session_id):
    """Stop and remove an ephemeral session's VM and all resources (best-effort)."""
    print(f"\nTearing down ephemeral session {session_id} ...")
    result = api.devmode.stop_session(DevSessionStopRequest(
        session_id=session_id, remove_resources=True))
    if result.success:
        print(f"Removed ephemeral VM and resources for session {session_id}")
    else:
        msg = result.error.message if result.error else 'unknown error'
        print(f"⚠ Could not fully tear down session {session_id}: {msg}")
        print(f"  Clean up manually with: adare dev stop --rm -s {session_id}")


def _post_run_cleanup(api, session_id, ephemeral, keep, baseline_created):
    """Resource cleanup that must run whether the drive succeeded, failed, or was interrupted.

    Ephemeral (``-e``, no ``--keep``): remove the whole VM/session (which also
    drops the baseline checkpoint). Attached (``-s``): we don't own the VM, so
    just delete the baseline checkpoint we added for --verify. Ephemeral +
    ``--keep``: leave everything in place for the user to drive again.
    """
    if ephemeral and not keep:
        _teardown_session(api, session_id)
    elif not ephemeral and baseline_created:
        _delete_verify_baseline(api, session_id)


def _create_verify_baseline(api, session_id):
    """Create the pre-agent baseline checkpoint used by --verify replay.

    Returns True when the checkpoint exists (replay can proceed), False when it
    could not be created (caller degrades to parse-only validation).
    """
    print('→ Snapshotting the VM as a baseline for --verify (replay starts here) ...')
    result = api.devmode.create_checkpoint(DevCheckpointCreateRequest(
        session_id=session_id,
        name=VERIFY_CHECKPOINT,
        description='pre-agent baseline for --verify',
    ))
    if not result.success:
        msg = result.error.message if result.error else 'unknown error'
        log.warning('Could not create --verify baseline checkpoint: %s', msg)
        print(f"⚠ Could not create the pre-verify checkpoint ({msg}); "
              "replay validation disabled (playbook will still be parse-checked).")
        return False
    print('  ✓ baseline checkpoint ready')
    return True


def _delete_verify_baseline(api, session_id):
    """Drop the baseline checkpoint on an attached (-s) session (best-effort)."""
    result = api.devmode.delete_checkpoint(DevCheckpointDeleteRequest(
        session_id=session_id, name=VERIFY_CHECKPOINT))
    if not result.success:
        msg = result.error.message if result.error else 'unknown error'
        log.warning("Could not delete --verify checkpoint '%s': %s",
                    VERIFY_CHECKPOINT, msg)


def _playbook_parse_error_types():
    """Exceptions parse_playbook / yaml / cattrs raise on a malformed playbook.

    Caught specifically (never a bare ``Exception``) so parse validation can
    report a bad recording instead of crashing the CLI.
    """
    import yaml
    types = [ValueError, KeyError, TypeError, AttributeError, ImportError,
             OSError, yaml.YAMLError]
    try:
        import cattrs.errors
        types.append(cattrs.errors.BaseValidationError)
    except ImportError:  # pragma: no cover - cattrs is a hard dep of the repo
        pass
    return tuple(types)


def _parse_validate(playbook_path):
    """Parse the recorded playbook via ADARE; print + return whether it is valid."""
    from adare.types.playbook import parse_playbook

    try:
        playbook = parse_playbook(playbook_path)
    except _playbook_parse_error_types() as exc:
        print(f"✗ Recorded playbook is NOT structurally valid: {exc}")
        return False
    print(f"✓ Playbook is structurally valid ({len(playbook.actions)} actions).")
    return True


def _verify_by_replay(api, session_id, playbook_path):
    """Restore the pre-agent baseline, then replay the playbook on the VM.

    Returns the DevPlaybookResult, or None when replay could not run (baseline
    restore or execution failed — reported as a warning, never fatal here).
    """
    print('→ Verifying: restoring the pre-agent baseline ...')
    restore = api.devmode.restore_checkpoint(DevCheckpointRestoreRequest(
        session_id=session_id, name=VERIFY_CHECKPOINT))
    if not restore.success:
        msg = restore.error.message if restore.error else 'unknown error'
        print(f"⚠ Replay skipped: could not restore the pre-verify baseline ({msg}).")
        return None

    print('  replaying the recorded playbook against the VM ...')
    result = api.devmode.execute_playbook(DevPlaybookExecuteRequest(
        session_id=session_id,
        playbook_source='file',
        playbook_content=str(playbook_path),
        restore_initial=False,
        indices=None,
    ))
    if not result.success:
        msg = result.error.message if result.error else 'unknown error'
        print(f"⚠ Replay could not run: {msg}")
        return None
    return result.data


def _replay_ok(replay):
    """True when every action of the replay succeeded."""
    return replay.success and replay.failed_actions == 0


def _replay_summary_line(replay):
    """One-line PASS/FAIL summary of a DevPlaybookResult for the next-steps list."""
    if _replay_ok(replay):
        return f'Replay: PASS ({replay.successful_actions}/{replay.total_actions} actions)'
    detail = replay.error_message or 'see the screenshot report'
    return (f'Replay: FAIL ({replay.failed_actions}/{replay.total_actions} actions failed '
            f'— {detail})')


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


def _announce_agent_run(session_id, goal, planning, grounding, video, as_experiment,
                        output_file, ephemeral, environment, keep, want_replay):
    """Print the goal + an ordered plan of the phases this run will go through.

    Printed once up front so the long, log-noisy boot/checkpoint/grounding phases
    are legible; each phase then prints its own ``→`` marker as it starts.
    """
    print(f"\nDriving session {session_id} toward goal:\n  {goal}")
    if ephemeral:
        fate = 'kept running afterwards (--keep)' if keep else \
            'torn down afterwards (use --keep to keep it)'
        print(f"VM: freshly booted from '{environment}', {fate}")

    steps = []
    if want_replay:
        steps.append('snapshot a VM baseline (for --verify replay)')
    if as_experiment:
        steps.append(f"record into experiment '{as_experiment}'")
    elif output_file:
        steps.append(f'record a playbook to {output_file}')
    if grounding:
        steps.append('start the LocateAnything grounding server (first run downloads ~7.3 GB)')
    if video:
        steps.append('record the run to MP4 (ffmpeg)')
    if planning:
        steps.append('plan / verify / backtrack over sub-goals')
    steps.append('drive the VM toward the goal')
    if want_replay:
        steps.append('verify by replaying the recording on the VM')
    if ephemeral and not keep:
        steps.append('tear down the VM')

    print('Plan:')
    for i, step in enumerate(steps, 1):
        print(f'  {i}. {step}')
    print()


def _agent_next_steps(r, exp, as_experiment, session_id, ephemeral, keep):
    """Build the CLI next-steps list from the agent result + optional experiment."""
    next_steps = []
    if r.report_path:
        next_steps.append(f'View the screenshot report: {r.report_path}')
    if r.video_path:
        next_steps.append(f'Watch the run video: {r.video_path}')

    # An ephemeral VM that is about to be torn down can't be replayed against, so
    # only suggest a live replay when the session will still be around.
    session_persists = keep or not ephemeral

    if exp is not None:
        next_steps.append(
            f'Files created — load it later with: adare experiment load {as_experiment}')
        if session_persists:
            next_steps.append(f'Replay it now: adare dev playbook {session_id} -f {exp.playbookfile}')
    elif r.playbook_path and session_persists:
        next_steps.append(f'Replay it: adare dev playbook {session_id} -f {r.playbook_path}')

    if ephemeral and keep:
        next_steps.append(
            f'VM kept running — drive it again: adare dev agent -s {session_id} --goal "..."')
        next_steps.append(f'Stop it when done: adare dev stop --rm -s {session_id}')
    return next_steps


def _scaffold_experiment(api, project_directory, session_id, name, known_environment=None):
    """Create experiments/<name>/ (dirs only) and return (ExperimentDirectory, env_name).

    Errors out (exit 1) if the experiment already exists or the session's
    environment cannot be resolved — we never overwrite an existing experiment.
    When ``known_environment`` is supplied (the -e path already knows it), the
    get_state round-trip is skipped.
    """
    if known_environment is not None:
        environment_name = known_environment
    else:
        state = api.devmode.get_state(DevSessionStateRequest(session_id=session_id))
        if not state.success:
            handle_api_error(state)
            exit(1)
        environment_name = state.data.environment_name

    exp = _ensure_experiment_available(project_directory, name)
    exp.create(empty=True)  # directories only — the recorder fills playbook.yml + img/
    return exp, environment_name


def _ensure_experiment_available(project_directory, name):
    """Return the ExperimentDirectory for ``name``, exiting if it already exists.

    The collision guard is pure filesystem (no session/VM), so callers run it
    before an ephemeral boot to fail a name clash instantly rather than after
    booting. We never overwrite an existing experiment.
    """
    from adare.backend.experiment.directory import ExperimentDirectory

    exp = ExperimentDirectory(project_directory, name)
    if exp.exists():
        print_error_message(
            title=f"Experiment '{name}' already exists at {exp.path}",
            next_steps=['Pick another --as-experiment NAME',
                        f'Or remove the existing one: rm -rf {exp.path}'],
        )
        exit(1)
    return exp


def _cleanup_empty_scaffold(exp):
    """Remove a freshly-scaffolded experiment that never recorded anything.

    A pre-run setup failure (grounding server won't start, ffmpeg missing,
    session/VM gone) exits before the agent loop captures a single screenshot,
    leaving an empty scaffold that blocks re-running with the same
    --as-experiment NAME. Delete it only when ``img/`` holds no screenshots, so
    a partially-recorded (interrupted-but-loadable) run is preserved.

    Before deleting, salvage any diagnostic ``*.log`` from ``playbook_run/`` to a
    durable sibling ``.diagnostics/<name>/`` so the error message can point at a
    file that still exists (the scaffold rmtree would otherwise delete the very
    ``locate_server.log`` the message names). Returns that diagnostics directory
    (or ``None`` if nothing was salvaged / the scaffold was kept).
    """
    from adare.backend.experiment.exceptions import ExperimentRemovalError

    try:
        recorded = exp.img.exists() and any(exp.img.iterdir())
    except OSError:
        return None  # can't inspect it — leave it alone rather than risk deletion
    if recorded:
        return None

    salvaged = _salvage_diagnostic_logs(exp)
    try:
        exp.remove()
        print(f'Cleaned up empty experiment scaffold: {exp.path}')
    except (ExperimentRemovalError, OSError) as exc:
        log.warning('Could not remove empty experiment scaffold %s: %s', exp.path, exc)
    return salvaged


def _salvage_diagnostic_logs(exp):
    """Copy ``playbook_run/*.log`` to a durable ``.diagnostics/<name>/`` sibling.

    Returns the diagnostics directory when at least one log was copied, else
    ``None``. Never blocks cleanup: any :class:`OSError` skips the salvage.
    """
    try:
        run_dir = exp.path / 'playbook_run'
        logs = sorted(run_dir.glob('*.log')) if run_dir.exists() else []
        if not logs:
            return None
        dest = exp.path.parent / '.diagnostics' / exp.path.name
        dest.mkdir(parents=True, exist_ok=True)
        for src in logs:
            shutil.copy2(src, dest / src.name)
        return dest
    except OSError as exc:
        log.warning('Could not salvage diagnostic logs from %s: %s', exp.path, exc)
        return None


def _strip_log_hint(message):
    """Drop the trailing ' See the server log: <path>' hint from an error message.

    The grounding manager appends that hint pointing inside the experiment
    scaffold; once the scaffold is deleted the path is stale, so we remove it and
    print a fresh pointer at the salvaged copy instead.
    """
    marker = ' See the server log:'
    idx = message.find(marker)
    return message[:idx].rstrip() if idx != -1 else message


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
