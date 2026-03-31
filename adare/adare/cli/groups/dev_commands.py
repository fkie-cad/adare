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
    @click.option('--gui-mode', type=click.Choice(['auto', 'agent', 'host']),
                  help='GUI execution mode: auto (default), agent (WebSocket), or host (QMP for QEMU)')
    @click.option('--test-mode', type=click.Choice(['auto', 'agent', 'host']),
                  help='Test execution mode: auto (default), agent (WebSocket), or host (QGA for QEMU)')
    @click.option('--vm-memory', type=int, help='VM RAM in MB (default: 4096 for Linux, 8192 for Windows)')
    @click.option('--vm-cpus', type=int, help='VM CPU count (default: 4)')
    @click.option('--shared-dir', multiple=True, help='Shared directories in format HOST_PATH:VM_PATH')
    @click.option('--debug-screenshots', is_flag=True, help='Save screenshots for debugging')
    def start(environment, project, gui_mode, test_mode, vm_memory, vm_cpus, shared_dir, debug_screenshots):
        """Start a new dev mode session."""
        from adare.cli.dev import exec_dev_start
        args = SimpleNamespace(
            environment=environment,
            project=project,
            gui_mode=gui_mode,
            test_mode=test_mode,
            vm_memory=vm_memory,
            vm_cpus=vm_cpus,
            shared_dir=shared_dir,
            debug_screenshots=debug_screenshots
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
    @click.option('-s', '--session', 'session_id', default=None, help='Session ID (auto-detected if only one running)')
    @click.option('--rm', is_flag=True, help='Remove all resources (VM, snapshots, database entries)')
    def stop(session_id, rm):
        """Stop a dev mode session.

        Without --rm: Stops the VM but keeps all resources for future restart.
        With --rm: Completely removes the session and all associated resources.
        """
        from adare.cli.dev import exec_dev_stop
        args = SimpleNamespace(session_id=session_id, remove_resources=rm)
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
