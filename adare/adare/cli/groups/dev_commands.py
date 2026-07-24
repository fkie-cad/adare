from types import SimpleNamespace

import click


def register(cli, AliasedGroup, exec_with_error_printing):
    """Register dev mode commands with the CLI."""

    # ------------------------------
    # Development mode commands
    # ------------------------------
    @cli.group(name='dev', cls=AliasedGroup)
    def dev():
        """Development mode commands for interactive playbook development."""
        pass

    @dev.command()
    @click.option('-e', '--environment', required=True, help='Environment name')
    @click.option('--project', '-p', help='Project name/path')
    @click.option('--name', 'name', default=None,
                  help='Human-friendly session label, selectable later via -s <name>')
    @click.option('--gui-mode', type=click.Choice(['auto', 'agent', 'host']),
                  help='GUI execution mode: auto (default), agent (WebSocket), or host (QMP for QEMU)')
    @click.option('--test-mode', type=click.Choice(['auto', 'agent', 'host']),
                  help='Test execution mode: auto (default), agent (WebSocket), or host (QGA for QEMU)')
    @click.option('--vm-memory', type=int, help='VM RAM in MB (default: 4096 for Linux, 8192 for Windows)')
    @click.option('--vm-cpus', type=int, help='VM CPU count (default: 4)')
    @click.option('--shared-dir', multiple=True, help='Shared directories in format HOST_PATH:VM_PATH')
    @click.option('--debug-screenshots', is_flag=True, help='Save screenshots for debugging')
    @click.option('--reuse', is_flag=True,
                  help='Attach to the most-recent running session for this project instead of booting a new VM')
    @click.option('--watch', is_flag=True,
                  help="Open the session VM's live screen (read-only) in the browser via "
                       'VirtualSpice once it is up. Needs VirtualSpice running (adare web start).')
    def start(environment, project, name, gui_mode, test_mode, vm_memory, vm_cpus,
              shared_dir, debug_screenshots, reuse, watch):
        """Start a new dev mode session."""
        from adare.cli.dev import exec_dev_start
        args = SimpleNamespace(
            environment=environment,
            project=project,
            name=name,
            gui_mode=gui_mode,
            test_mode=test_mode,
            vm_memory=vm_memory,
            vm_cpus=vm_cpus,
            shared_dir=shared_dir,
            debug_screenshots=debug_screenshots,
            reuse=reuse,
            watch=watch
        )
        exec_with_error_printing(exec_dev_start, args)

    @dev.command()
    @click.argument('session_id', required=False)
    @click.option('--project', '-p', help='Project name/path')

    def resume(session_id, project):
        """Resume a stopped dev mode session.

        If SESSION_ID is provided, resumes that specific session.
        If SESSION_ID is omitted, resumes the most recently stopped session.

        Examples:
            adare dev resume                      # Resume most recent stopped session
            adare dev resume 01K72Q...            # Resume specific session by ID
        """
        from adare.cli.dev import exec_dev_resume
        args = SimpleNamespace(
            session_id=session_id,
            project=project
        )
        exec_with_error_printing(exec_dev_resume, args)

    @dev.command()
    @click.option('-s', '--session', 'session_id', default=None,
                  help='Session id or name (auto-detected if only one running)')
    @click.option('--rm', is_flag=True, help='Remove all resources (VM, snapshots, database entries)')
    @click.option('--all', 'all_sessions', is_flag=True, help='Stop every running session')
    @click.option('-y', '--yes', is_flag=True, help='Skip the confirmation prompt (with --all)')
    def stop(session_id, rm, all_sessions, yes):
        """Stop a dev mode session.

        Without --rm: Stops the VM but keeps all resources for future restart.
        With --rm: Completely removes the session and all associated resources.
        With --all: Stops every running session (confirms first unless --yes).
        """
        from adare.cli.dev import exec_dev_stop
        args = SimpleNamespace(
            session_id=session_id, remove_resources=rm,
            all_sessions=all_sessions, yes=yes
        )
        exec_with_error_printing(exec_dev_stop, args)

    @dev.command()
    @click.option('-s', '--session', 'session_id', default=None, help='Session ID (auto-detected if only one running)')
    def remove(session_id):
        """Remove a dev mode session and all resources (alias for 'stop --rm')."""
        from adare.cli.dev import exec_dev_stop
        args = SimpleNamespace(session_id=session_id, remove_resources=True)
        exec_with_error_printing(exec_dev_stop, args)

    @dev.command()
    @click.option('--project', '-p', help='Filter by project')
    def list(project):
        """List active dev mode sessions."""
        from adare.cli.dev import exec_dev_list
        args = SimpleNamespace(project=project)
        exec_with_error_printing(exec_dev_list, args)

    @dev.command()
    @click.option('-s', '--session', 'session_id', default=None, help='Session ID (auto-detected if only one running)')
    @click.option('-i', '--input', 'action_file', help='Action YAML file')
    @click.option('-y', '--yaml', 'action_yaml', help='Inline YAML string')
    @click.option('--stdin', is_flag=True, help='Read from stdin')
    def action(session_id, action_file, action_yaml, stdin):
        """Execute a single action."""
        from adare.cli.dev import exec_dev_action
        args = SimpleNamespace(
            session_id=session_id,
            action_file=action_file,
            action_yaml=action_yaml,
            stdin=stdin
        )
        exec_with_error_printing(exec_dev_action, args)

    @dev.command()
    @click.option('-s', '--session', 'session_id', default=None, help='Session ID (auto-detected if only one running)')
    @click.option('-f', '--file', 'playbook_file', help='Playbook YAML file')
    @click.option('-u', '--url', help='Playbook URL')
    @click.option('--stdin', is_flag=True, help='Read from stdin')
    @click.option('--restore', is_flag=True, help='Restore to initial checkpoint before execution')
    @click.option('--indices', help='Select specific action indices to execute (e.g. 1-3,5,7-9,S-5,7,23-E). S=start, E=end')
    def playbook(session_id, playbook_file, url, stdin, restore, indices):
        """Execute a playbook."""
        from adare.cli.dev import exec_dev_playbook
        args = SimpleNamespace(
            session_id=session_id,
            playbook_file=playbook_file,
            url=url,
            stdin=stdin,
            restore=restore,
            indices=indices
        )
        exec_with_error_printing(exec_dev_playbook, args)

    @dev.group(name='cv')
    def dev_cv():
        """CV Server management commands."""
        pass

    @dev_cv.command(name='start')
    @click.option('-s', '--session', 'session_id', default=None, help='Session ID (auto-detected if only one running)')
    @click.option('--debug/--no-debug', default=None, help='Enable/disable CV debug logging (default: keep existing)')
    @click.option('--debug-output', '-o', type=click.Path(), help='Directory for debug screenshots')
    def dev_cv_start(session_id, debug, debug_output):
        """Start/Restart CV server with logging options."""
        from adare.cli.dev import exec_dev_cv_start
        args = SimpleNamespace(
            session_id=session_id,
            debug=debug is True,
            no_debug=debug is False,
            debug_output=debug_output
        )
        exec_with_error_printing(exec_dev_cv_start, args)

    @dev_cv.command(name='stop')
    @click.option('-s', '--session', 'session_id', default=None, help='Session ID (auto-detected if only one running)')
    def dev_cv_stop(session_id):
        """Stop CV server."""
        from adare.cli.dev import exec_dev_cv_stop
        args = SimpleNamespace(
            session_id=session_id
        )
        exec_with_error_printing(exec_dev_cv_stop, args)

    @dev.group()
    def reset():
        """Reset commands for dev session."""
        pass

    @reset.command(name='soft')
    @click.option('-s', '--session', 'session_id', default=None, help='Session ID (auto-detected if only one running)')
    def reset_soft(session_id):
        """Soft reset: Reset variables only (<1 second)."""
        from adare.cli.dev import exec_dev_reset_soft
        args = SimpleNamespace(session_id=session_id)
        exec_with_error_printing(exec_dev_reset_soft, args)

    @reset.command(name='hard')
    @click.option('-s', '--session', 'session_id', default=None, help='Session ID (auto-detected if only one running)')
    def reset_hard(session_id):
        """Hard reset: Full VM restore (10-30 seconds)."""
        from adare.cli.dev import exec_dev_reset_hard
        args = SimpleNamespace(session_id=session_id)
        exec_with_error_printing(exec_dev_reset_hard, args)

    @dev.group()
    def checkpoint():
        """Checkpoint management commands."""
        pass

    @checkpoint.command(name='create')
    @click.option('-s', '--session', 'session_id', default=None, help='Session ID (auto-detected if only one running)')
    @click.argument('name')
    @click.option('-d', '--description', default='', help='Checkpoint description')
    def checkpoint_create(session_id, name, description):
        """Create a named checkpoint (live snapshot)."""
        from adare.cli.dev import exec_dev_checkpoint_create
        args = SimpleNamespace(session_id=session_id, name=name, description=description)
        exec_with_error_printing(exec_dev_checkpoint_create, args)

    @checkpoint.command(name='restore')
    @click.option('-s', '--session', 'session_id', default=None, help='Session ID (auto-detected if only one running)')
    @click.argument('name')
    def checkpoint_restore(session_id, name):
        """Restore to a named checkpoint."""
        from adare.cli.dev import exec_dev_checkpoint_restore
        args = SimpleNamespace(session_id=session_id, name=name)
        exec_with_error_printing(exec_dev_checkpoint_restore, args)

    @checkpoint.command(name='list')
    @click.option('-s', '--session', 'session_id', default=None, help='Session ID (auto-detected if only one running)')
    def checkpoint_list(session_id):
        """List available checkpoints."""
        from adare.cli.dev import exec_dev_checkpoint_list
        args = SimpleNamespace(session_id=session_id)
        exec_with_error_printing(exec_dev_checkpoint_list, args)

    @checkpoint.command(name='remove')
    @click.option('-s', '--session', 'session_id', default=None, help='Session ID (auto-detected if only one running)')
    @click.argument('name')
    def checkpoint_remove(session_id, name):
        """Remove a checkpoint."""
        from adare.cli.dev import exec_dev_checkpoint_delete
        args = SimpleNamespace(session_id=session_id, name=name)
        exec_with_error_printing(exec_dev_checkpoint_delete, args)

    @dev.command()
    @click.option('-s', '--session', 'session_id', default=None, help='Session ID (auto-detected if only one running)')
    def state(session_id):
        """Show session state (variables, stats, snapshots)."""
        from adare.cli.dev import exec_dev_state
        args = SimpleNamespace(session_id=session_id)
        exec_with_error_printing(exec_dev_state, args)

    @dev.command()
    @click.option('--project', '-p', help='Filter by project')
    def cleanup(project):
        """Cleanup stale sessions."""
        from adare.cli.dev import exec_dev_cleanup
        args = SimpleNamespace(project=project)
        exec_with_error_printing(exec_dev_cleanup, args)

    @dev.command()
    @click.option('-s', '--session', 'session_id', default=None, help='Session ID (auto-detected if only one running)')
    @click.option('-e', '--environment', 'environment', default=None, metavar='NAME',
                  help='Boot a fresh VM from this environment, drive it, then tear it down. '
                       'Self-contained — no prior `adare dev start` needed. Mutually '
                       'exclusive with -s/--session.')
    @click.option('--keep', 'keep', is_flag=True,
                  help='With -e, leave the booted VM/session running afterwards instead of '
                       'tearing it down (prints how to drive it again / stop it).')
    @click.option('--verify/--no-verify', 'verify', default=True,
                  help='After recording a playbook (-o or --as-experiment), validate it by '
                       'replaying it on the VM from a pre-run baseline checkpoint '
                       '(default: on). The playbook is always parse-checked regardless. '
                       'No-op for a bare drive that records nothing.')
    @click.option('--goal', help='Natural-language goal for the agent to accomplish')
    @click.option('--goal-file', type=click.Path(exists=True), help='Read the goal from a file')
    @click.option('-o', '--out', 'output', type=click.Path(), help='Record a replayable playbook to this path')
    @click.option('--max-steps', type=int, default=None, help='Override the agent step budget')
    @click.option('--stall-limit', type=int, default=None, help='Override the agent stall budget')
    @click.option('--step', '--interactive', 'interactive', is_flag=True,
                  help='Pause before each action to approve / skip / stop')
    @click.option('--plan/--no-plan', 'planning', default=None,
                  help='Iterative plan/verify/backtrack mode (default: ADARE_AGENT_PLAN). '
                       'Decomposes a terse goal into sub-goals, checkpoints the VM before '
                       'each, verifies with an independent checker, and resets to retry on a '
                       'dead end — building a playbook from only the verified sub-goals.')
    @click.option('--ground/--no-ground', 'grounding', default=None,
                  help='Auto-start the LocateAnything grounding server for this run '
                       '(default: ADARE_LOCATE_AUTOSTART). Clicks are grounded to the true '
                       'element box and the server is torn down at run end. Attaches to '
                       'ADARE_LOCATE_URL if set instead of spawning. Needs the grounding '
                       'backend: `uv sync --extra grounding` or ADARE_LOCATE_PYTHON.')
    @click.option('--progress/--no-progress', 'progress', default=None,
                  help='Show a live per-step table while the agent runs '
                       '(default: on when stdout is a TTY).')
    @click.option('--reasoning/--no-reasoning', 'reasoning', default=True,
                  help='Show the model\'s per-step reasoning in a "chat" panel below the '
                       'progress table (default: on). Use global --verbose/--very-verbose to '
                       'also stream grounding + decision-repair logs live; the full per-step '
                       'reasoning + raw reply is always saved to the run\'s steps/step_NNN.json '
                       'and install_report.md.')
    @click.option('--video/--no-video', 'video', default=None,
                  help='Record the whole run to <run_dir>/run.mp4 via ffmpeg '
                       '(default: ADARE_AGENT_VIDEO; off). Needs the ffmpeg binary.')
    @click.option('--as-experiment', 'as_experiment', default=None, metavar='NAME',
                  help='Scaffold experiments/NAME/ and record the run into it '
                       '(playbook.yml + img/ crops + metadata.yml). Files only — no DB '
                       'load; run `adare experiment load NAME` later. Excludes -o/--out.')
    def agent(session_id, environment, keep, verify, goal, goal_file, output, max_steps,
              stall_limit, interactive, planning, grounding, progress, reasoning, video,
              as_experiment):
        """Drive a VM toward a goal with the vision-LLM GUI agent.

        Uses the configured vLLM endpoint (ADARE_VLLM_*; works with Ollama Cloud).
        Attach to a running session with -s, or boot a fresh VM from an
        environment with -e (driven, then torn down unless --keep). With --out or
        --as-experiment, records a reusable playbook; --verify (default) then
        replays it on the VM to validate it.

        Examples:
            adare dev agent -s <id> --goal "open the Files app and go to Documents"
            adare dev agent -s <id> --goal "..." -o experiments/files.play.yaml
            adare dev agent --plan --goal "open LibreOffice and write an invoice" -o inv.play.yaml
            adare dev agent -e ubuntu2510-libre --goal "..." --as-experiment demo_invoice6 --ground --video
        """
        from adare.cli.dev import exec_dev_agent
        args = SimpleNamespace(
            session_id=session_id,
            environment=environment,
            keep=keep,
            verify=verify,
            goal=goal,
            goal_file=goal_file,
            output=output,
            max_steps=max_steps,
            stall_limit=stall_limit,
            interactive=interactive,
            planning=planning,
            grounding=grounding,
            progress=progress,
            reasoning=reasoning,
            video=video,
            as_experiment=as_experiment,
        )
        exec_with_error_printing(exec_dev_agent, args)

    @dev.command(name='grounding-pull')
    @click.option('--model', default=None,
                  help='HF id or local path (default: ADARE_LOCATE_MODEL_PATH or '
                       'nvidia/LocateAnything-3B)')
    def grounding_pull(model):
        """Pre-download the LocateAnything grounding weights (~7.3 GB).

        Pays the cold-download cost up front instead of on the first
        `adare dev agent --ground` run. Needs the grounding backend
        (`uv sync --extra grounding`), an HF_TOKEN and the accepted NVIDIA
        license. Skipped if the configured model is already a local directory.
        """
        from adare.cli.dev import exec_dev_grounding_pull
        args = SimpleNamespace(model=model)
        exec_with_error_printing(exec_dev_grounding_pull, args)

    @dev.command()
    @click.option('-s', '--session', 'session_id', default=None, help='Session ID (auto-detected if only one running)')
    @click.option('--script-file', type=click.Path(exists=True), help='Read text steps from a file (one action per line)')
    @click.option('-o', '--out', 'output', type=click.Path(), help='Record the authored playbook to this path')
    @click.option('-i', '--interactive', 'interactive', is_flag=True,
                  help='Author step-by-step in a REPL (used when no --script-file)')
    def author(session_id, script_file, output, interactive):
        """Author a playbook from human text steps — no VLM planner.

        Each step names WHAT to do; LocateAnything (ADARE_LOCATE_URL) grounds
        WHERE for described clicks. The recorded playbook replays deterministically,
        identical in shape to an agent-recorded one. Use `click @x,y ...` to place
        a click by hand when no grounding backend is available.

        Examples:
            adare dev author -s <id> --script-file steps.txt -o report.play.yaml
            adare dev author -s <id> --interactive -o report.play.yaml
        """
        from adare.cli.dev import exec_dev_author
        args = SimpleNamespace(
            session_id=session_id,
            script_file=script_file,
            output=output,
            interactive=interactive,
        )
        exec_with_error_printing(exec_dev_author, args)

    @dev.command(name='author-ai')
    @click.option('-s', '--session', 'session_id', default=None, help='Session ID (auto-detected if only one running)')
    @click.option('--goal', required=True, help='Natural-language task the authored playbook must accomplish')
    @click.option('--models', default=None,
                  help='Comma-separated Ollama Cloud vision models, in preference order '
                       '(default: the harness DEFAULT_MODELS)')
    @click.option('--rounds', type=int, default=3, help='Max author/repair rounds per model')
    @click.option('--replay', is_flag=True,
                  help='Verify each valid playbook by replaying it live on the session VM '
                       '(serialized), repairing on failure. Off = author + validate only.')
    @click.option('--os-key', default='linux', help='Replay OS key / CV grounding profile (default: linux)')
    @click.option('-o', '--out', 'output', type=click.Path(), help='Write the best authored playbook YAML to this path')
    def author_ai(session_id, goal, models, rounds, replay, os_key, output):
        """LLM-author a UI-action playbook from a screenshot of the session VM.

        A cloud vision model is shown the current screen and authors a robust
        ``actions:`` playbook for --goal; the harness validates it against the
        real schema and, with --replay, verifies it live on the VM and repairs
        on failure, picking the best model. See vlm/authoring/FLOW.md.

        Examples:
            adare dev author-ai -s <id> --goal "open the File menu"
            adare dev author-ai -s <id> --goal "type a sentence in Writer and save" --replay -o report.play.yaml
        """
        from adare.cli.dev import exec_dev_author_ai
        args = SimpleNamespace(
            session_id=session_id,
            goal=goal,
            models=models,
            rounds=rounds,
            replay=replay,
            os_key=os_key,
            output=output,
        )
        exec_with_error_printing(exec_dev_author_ai, args)

    @dev.command()
    @click.option('-s', '--session', 'session_id', default=None, help='Session ID (auto-detected if only one running)')
    @click.option('--host', default=None, help='Bind host (default: ADARE_GUI_MCP_HOST or 127.0.0.1)')
    @click.option('--port', type=int, default=None, help='Bind port (default: ADARE_GUI_MCP_PORT or 13110)')
    @click.option('-o', '--out-dir', 'output_dir', type=click.Path(), help='Directory for recorded playbooks (default: project dir)')
    def mcp(session_id, host, port, output_dir):
        """Serve the session VM as a GUI-automation MCP server (blocking).

        An external harness (OpenCode / Claude Code / any MCP client — including
        one driving a local Ollama model) connects and authors playbooks by
        natural language. ADARE grounds via CV/OCR and records crops + tests;
        replay is deterministic with no LLM. See the MCP authoring guide for
        harness connection snippets.

        Example:
            adare dev mcp -s <id> --port 13110

        Client setup (Claude Code / OpenCode): docs/mcp-clients.md
            Claude Code: claude mcp add --transport http adare-gui \\
                http://127.0.0.1:13110/mcp
        """
        from adare.cli.dev import exec_dev_mcp
        args = SimpleNamespace(
            session_id=session_id,
            host=host,
            port=port,
            output_dir=output_dir,
        )
        exec_with_error_printing(exec_dev_mcp, args)

    # Add dev command aliases
    dev.add_alias('l', 'list')
    dev.add_alias('res', 'reset')
    dev.add_alias('cp', 'checkpoint')


    @dev.command(name='update-testfunctions')
    @click.option('-s', '--session', 'session_id', default=None, help='Session ID (auto-detected if only one running)')
    def update_testfunctions(session_id):
        """Reload test functions in the running VM.

        This packages the current test files from the host and uploads them to the VM again.
        The adarevm agent will extract them to a new location and use them for subsequent tests.
        """
        from adare.cli.dev import exec_dev_update_testfunctions
        args = SimpleNamespace(session_id=session_id)
        exec_with_error_printing(exec_dev_update_testfunctions, args)


    @dev.command(name='playbook-batch')
    @click.argument('playbook_patterns', nargs=-1, required=True)
    @click.option('-s', '--session', 'session_id', default=None, help='Session ID (auto-detected if only one running)')
    @click.option('--checkpoint-name', default='batch_base', help='Base checkpoint name')
    @click.option('--timeout', default=120, type=int, help='Checkpoint restore timeout in seconds')
    def playbook_batch(session_id, playbook_patterns, checkpoint_name, timeout):
        """Execute multiple playbooks with checkpoint restoration.

        Supports both explicit paths and glob patterns:
        - adare dev playbook-batch playbook1.yml playbook2.yml
        - adare dev playbook-batch experiments/*/playbook.yml
        - adare dev playbook-batch playbooks/test_*.yml

        A base checkpoint is created before execution, and the VM is restored
        to this checkpoint after each playbook completes.
        """
        from adare.cli.dev import exec_dev_playbook_batch
        args = SimpleNamespace(
            session_id=session_id,
            playbook_patterns=list(playbook_patterns),
            checkpoint_name=checkpoint_name,
            timeout=timeout
        )
        exec_with_error_printing(exec_dev_playbook_batch, args)

    return dev
