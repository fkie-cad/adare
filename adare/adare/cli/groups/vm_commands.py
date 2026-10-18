from types import SimpleNamespace

import click

from adare.cli.output import output_options


def register(cli, AliasedGroup, exec_with_error_printing):
    """Register VM management commands with the CLI."""

    # ------------------------------
    # VM management commands
    # ------------------------------
    @cli.group(cls=AliasedGroup)
    def vm():
        """VM management commands.

        \b
        Registered VMs (`list`) are the disks environments run on;
        `adare env load` registers them. Instances (`usage`, `snapshot`,
        `prune`, `reset`) are what experiment runs boot from them: on QEMU
        one throwaway instance per run, on VirtualBox a reusable pool.
        `info` and `remove` take either kind, by name or ID.
        """
        pass

    @vm.command(name='list')
    @output_options
    def vm_list():
        """List registered VMs (the disks environments run on)."""
        from adare.cli.vm import exec_vm_list

        args = SimpleNamespace()
        exec_with_error_printing(exec_vm_list, args)

    @vm.command()
    @output_options
    @click.argument('vm_id')
    def info(vm_id):
        """Show a registered VM or a VM instance (auto-detected from the id)."""
        from adare.cli.vm import exec_vm_info

        args = SimpleNamespace(vm_id=vm_id)
        exec_with_error_printing(exec_vm_info, args)

    @vm.command()
    @click.argument('vm')
    @click.option('--vm-url', required=True, help='http(s) URL where the disk is hosted (upload it first)')
    @click.option('--verify-url', is_flag=True, help='Download the URL and check it matches the disk')
    def publish(vm, vm_url, verify_url):
        """Record where a registered image is hosted (in its image record).

        \b
        Upload the disk yourself (e.g. Zenodo), then record the URL here.
        `adare env publish-prepare` embeds the image record in the
        environment file it publishes.
        """
        from adare.cli.vm import exec_vm_publish

        args = SimpleNamespace(vm=vm, vm_url=vm_url, verify_url=verify_url)
        exec_with_error_printing(exec_vm_publish, args)

    @vm.command()
    @click.argument('target', required=False, metavar='[NAME_OR_ID]')
    @click.option('--id', 'target_id', hidden=True, help='Same as NAME_OR_ID (kept for scripts)')
    @click.option('--stopped', is_flag=True, help='Remove all stopped instances')
    @click.option('--experiment', 'experiment_id', help='Remove the instances of an experiment')
    @click.option('--all', is_flag=True, help='Remove ALL instances including running (requires --force)')
    @click.option('--env', 'environment_ulid', help="Remove the instances of an environment's VM (requires --force)")
    @click.option(
        '-f',
        '--force',
        is_flag=True,
        help='Instance: remove it even if running. Registered VM: also delete the runs that used its environments.',
    )
    @click.option('-y', '--yes', is_flag=True, help='Skip the confirmation prompt (registered VMs)')
    def remove(target, target_id, stopped, experiment_id, all, environment_ulid, force, yes):
        """Remove a registered VM or a VM instance, or instances in bulk.

        NAME_OR_ID is a name or ID from `adare vm list` (registered VMs) or
        `adare vm usage` (instances); which kind it is is detected.

        \b
        A registered VM is the disk environments run on, so removing it also
        removes those environments with every version -- like `adare env remove`.
        It shows what goes and asks first (--yes skips that), and refuses while
        an experiment runs on it. Disks outside ADARE's managed storage are kept.

        \b
        Examples:
          adare vm remove ubuntu2404-20261023    # registered VM + its environment
          adare vm remove <instance-name>        # one instance
          adare vm remove --stopped              # all stopped instances
          adare vm remove --experiment <id>      # instances of an experiment
          adare vm remove --all --force          # ALL instances, running or not
          adare vm remove --env <ulid> --force   # instances of an environment's VM
        """
        from adare.cli.vm import exec_vm_remove

        if target and target_id and target != target_id:
            raise click.UsageError(f'two different targets given: {target!r} and --id {target_id!r}. Pass one.')
        target = target or target_id
        if target and (stopped or experiment_id or all or environment_ulid):
            raise click.UsageError('pass either NAME_OR_ID or one of --stopped/--experiment/--all/--env, not both')
        args = SimpleNamespace(
            target=target,
            stopped=stopped,
            experiment_id=experiment_id,
            all=all,
            environment_ulid=environment_ulid,
            force=force,
            yes=yes,
        )
        exec_with_error_printing(exec_vm_remove, args)

    @vm.command()
    @output_options
    def usage():
        """Show VM instances (running experiment runs; VirtualBox pool) and their usage."""
        from adare.cli.vm import exec_vm_instance_usage

        args = SimpleNamespace()
        exec_with_error_printing(exec_vm_instance_usage, args)

    @vm.command(name='prune')
    @click.option(
        '--dry-run/--force', 'dry_run', default=True, help='Dry-run (default) previews only; --force actually deletes.'
    )
    @click.option(
        '--sockets', is_flag=True, default=False, help='Also reap crash-orphaned dead QMP/QGA sockets in run/.'
    )
    def vm_prune(dry_run, sockets):
        """Reclaim what crashed runs and older versions left behind.

        Instances of runs whose process is gone (QEMU: domain, overlay, varstore,
        vTPM copy and row; VirtualBox: released to the pool), QEMU run files
        without an instance, pooled QEMU instances from before per-run overlays,
        and orphaned '<name>-base.qcow2' / '-nvram.fd' files, stale recipe base
        caches and (with --sockets) dead sockets.

        \b
        Examples:
          adare vm prune                    # preview orphans, delete nothing
          adare vm prune --force            # reclaim orphaned base/nvram files
          adare vm prune --force --sockets  # also reap dead QMP/QGA sockets
        """
        from adare.cli.vm import exec_vm_prune

        args = SimpleNamespace(dry_run=dry_run, sockets=sockets)
        exec_with_error_printing(exec_vm_prune, args)

    @vm.command(name='watch')
    @click.argument('name')
    @click.option(
        '--view-only/--interactive',
        'view_only',
        default=True,
        help='Read-only view (default) or allow input. Toggle live from VirtualSpice\'s own toolbar either way.',
    )
    def vm_watch(name, view_only):
        """Watch a running VM's live screen in the browser (via VirtualSpice).

        NAME is the VM/instance name (run 'adare vm list' to see names). Opens
        VirtualSpice's standalone display page pointed at that VM. Requires
        VirtualSpice to be running (started by 'adare ui start').

        \b
        Examples:
          adare vm watch my-vm                 # read-only live view
          adare vm watch my-vm --interactive   # allow input
        """
        from adare.cli.vm import exec_vm_watch

        args = SimpleNamespace(name=name, view_only=view_only)
        exec_with_error_printing(exec_vm_watch, args)

    @vm.command()
    @click.argument('target')
    @click.option(
        '--platform',
        '-p',
        required=False,
        type=click.Choice(['linux', 'windows']),
        help='VM platform (required for OVA files; auto-derived for registered VMs)',
    )
    @click.option('--verbose', '-v', is_flag=True, help='Enable verbose output with detailed error information')
    @click.option('--keep-vm', is_flag=True, help='Keep the test VM after completion (for further testing)')
    @click.option('--remove-vm', is_flag=True, help='Automatically remove the test VM after completion')
    @click.option(
        '--log-file',
        type=click.Path(dir_okay=False),
        help='Where to write the full debug log (default: ./adare-vm-test-<target>-<timestamp>.log)',
    )
    @click.option('--no-log', is_flag=True, help='Do not write a log file')
    def test(target, platform, verbose, keep_vm, remove_vm, log_file, no_log):
        """Test ADARE compatibility of a VM.

        \b
        TARGET may be either:
        - a path to an .ova/.ovf file (VirtualBox OVA import test), or
        - the name of a registered VM (run 'adare vm list' to see names).

        \b
        The command validates the VM by:
        - Preparing the VM (OVA import, or a QEMU overlay off the base disk)
        - Setting up shared directories and mounting them
        - Starting adarevm and establishing a WebSocket connection
        - Taking a screenshot and performing a test click
        - Cleaning up all temporary resources

        The registered-VM (QEMU) test requires a uv-based guest: it runs
        'uv run python -m adarevm.server' from source inside the guest.

        \b
        Examples:
          adare vm test ubuntu22.ova --platform linux
          adare vm test windows11.ova --platform windows --verbose
          adare vm test my-registered-vm            # platform auto-derived
          adare vm test my-registered-vm --platform windows   # override
          adare vm test my-registered-vm --keep-vm
          adare vm test my-registered-vm --no-log

        A debug-level log of the whole test is written to the current directory
        unless --no-log is given (or the global --logfile already captures it).
        """
        # Handle cleanup options
        if keep_vm and remove_vm:
            click.echo("Error: Cannot specify both --keep-vm and --remove-vm", err=True)
            return
        if log_file and no_log:
            click.echo("Error: Cannot specify both --log-file and --no-log", err=True)
            return

        vm_cleanup_mode = 'prompt'  # Default
        if keep_vm:
            vm_cleanup_mode = 'keep'
        elif remove_vm:
            vm_cleanup_mode = 'remove'

        from adare.cli.vm import exec_vm_test

        args = SimpleNamespace(
            target=target,
            platform=platform,
            verbose=verbose,
            vm_cleanup_mode=vm_cleanup_mode,
            log_file=log_file,
            no_log=no_log,
        )
        exec_with_error_printing(exec_vm_test, args)

    # Nested group for snapshot management
    @vm.group(cls=AliasedGroup)
    def snapshot():
        """Snapshot management commands."""
        pass

    @snapshot.command(name='list')
    @output_options
    @click.option('--instance', '-i', 'instance_id', help='Filter by specific VM instance ID')
    def snapshot_list(instance_id):
        """List all snapshots. Use --instance to filter by specific VM instance."""
        from adare.cli.vm import exec_vm_list_snapshots

        args = SimpleNamespace(instance_id=instance_id)
        exec_with_error_printing(exec_vm_list_snapshots, args)

    @snapshot.command(name='remove')
    @click.argument('instance_id')
    @click.argument('snapshot_name')
    def snapshot_remove(instance_id, snapshot_name):
        """Delete a single snapshot from a specific VM instance."""
        from adare.cli.vm import exec_vm_delete_snapshot

        args = SimpleNamespace(instance_id=instance_id, snapshot_name=snapshot_name)
        exec_with_error_printing(exec_vm_delete_snapshot, args)

    # Cross-process VM slot counter (adare.backend.vm.slots)
    @vm.group(cls=AliasedGroup)
    def slots():
        """Cross-process VM slots (ADARE_MAX_VMS, default 20)."""
        pass

    @slots.command(name='status')
    @click.option('--json', 'as_json', is_flag=True, help='Print machine-readable JSON')
    def slots_status(as_json):
        """Show how many VM slots exist, are taken and by which pids."""
        import json as _json

        from adare.backend.vm.slots import slot_status

        status = slot_status()
        if as_json:
            click.echo(_json.dumps(status))
            return
        click.echo(f"VM slots: {status['taken']} taken, {status['free']} free of {status['total']}")
        for index, pid in sorted(status['holders'].items()):
            click.echo(f"  slot {index}: pid {pid}")

    @slots.command(name='exclusive', context_settings={'ignore_unknown_options': True})
    @click.option('--timeout', type=float, default=None, help='Seconds to wait for running VMs (default 30)')
    @click.argument('command', nargs=-1, type=click.UNPROCESSED, required=True)
    def slots_exclusive(timeout, command):
        """Run COMMAND while holding every VM slot (no other adare process can start a VM).

        The exit status is the command's. The slots are released when it exits.

        \b
        Example:
            adare vm slots exclusive -- adare dev start ...
        """
        import subprocess
        import sys

        from adare.backend.vm.slots import VMSlotTimeout, acquire_all_slots, exclusive_env

        try:
            lease = acquire_all_slots(timeout)
        except VMSlotTimeout as exc:
            click.echo(f"error: {exc}", err=True)
            sys.exit(75)  # EX_TEMPFAIL: try again later
        with lease:
            click.echo(f"Holding all {len(lease)} VM slots", err=True)
            sys.exit(subprocess.call(list(command), env=exclusive_env()))

    @vm.command(name='create')
    @click.argument('os_name')
    @click.option('--iso', type=click.Path(exists=True), help='Path to OS ISO (required for Windows)')
    @click.option('--name', help='VM name (auto-generated if not set)')
    @click.option('--disk-size', default=None, help='Disk size (default: 60G Linux, 80G Windows)')
    @click.option('--ram', type=int, default=None, help='RAM in MB')
    @click.option('--cpus', type=int, default=None, help='CPU count')
    @click.option('--force', is_flag=True, default=False, help='Overwrite existing VM disk image')
    @click.option(
        '--vm-dir', type=click.Path(), default=None, help='Directory for VM disk image (default: ~/.adare/state/vms/)'
    )
    @click.option(
        '--setup',
        'setup_level',
        type=click.Choice(['bare', 'base', 'full', 'agent']),
        default=None,
        help='What ADARE adds to the guest: bare (nothing after the OS install; unattended '
        'answer files still create the adare user and autologin), base (+ guest agent, '
        'autologin, no screen lock; checked after a reboot), full (+ Python env, default), '
        'agent (+ pre-installed adarevm, not implemented).',
    )
    @click.option('--bare', is_flag=True, default=False, help='Deprecated alias for --setup bare.')
    @click.option('--env-name', default=None, help='Environment file name (defaults to VM name)')
    @click.option(
        '--interactive', is_flag=True, default=False, help='Boot VM after install for manual software installation'
    )
    @click.option(
        '--arch',
        type=click.Choice(['x86_64', 'aarch64']),
        default=None,
        help='Override CPU architecture (default: from OS profile)',
    )
    @click.option(
        '--allow-emulation',
        is_flag=True,
        default=False,
        help='Allow QEMU TCG software emulation when --arch does not match the host CPU (slow; hardware acceleration is used otherwise).',
    )
    @click.option(
        '--recipe/--no-recipe',
        'recipe',
        default=None,
        help='Emit a declarative recipe environment (build on load) instead of a baked disk. Default: recipe for Windows, baked for Linux.',
    )
    @click.option(
        '--byo-iso',
        is_flag=True,
        default=False,
        help='[recipe, Windows only] Emit "iso_name" instead of the local "iso" path, so consumers supply the ISO themselves. Makes the environment publishable without rehosting a Windows ISO you are not licensed to redistribute.',
    )
    @click.option(
        '--iso-notes',
        default=None,
        help='[--byo-iso] Plain-text download pointer for the consumer (defaults to the OS profile\'s iso_notes).',
    )
    @click.option(
        '--record',
        is_flag=True,
        default=False,
        help='GUI-auto: record a fresh playbook with the vision agent even if a cached one exists.',
    )
    @click.option(
        '--relearn',
        is_flag=True,
        default=False,
        help='GUI-auto: discard the cached playbook and re-record from scratch.',
    )
    @click.option(
        '--display',
        is_flag=True,
        default=False,
        help='GUI-auto/playbook: show the VM in a window while the installer is driven (watch only).',
    )
    @click.option(
        '--template', default=None, help='GUI-auto: explicit goal/spec template name (default: gui_<distribution>).'
    )
    @click.option(
        '--compress/--no-compress',
        'compress',
        default=True,
        help='Zstd-compress the finished base disk (~30-50% smaller, transparent to readers). Default: on.',
    )
    def vm_create(
        os_name,
        iso,
        name,
        disk_size,
        ram,
        cpus,
        force,
        vm_dir,
        setup_level,
        bare,
        env_name,
        interactive,
        arch,
        allow_emulation,
        recipe,
        byo_iso,
        iso_notes,
        record,
        relearn,
        display,
        template,
        compress,
    ):
        """Create a new ADARE-ready VM from scratch.

        OS_NAME is the target OS. Run `adare vm profile list` to see all entries.

        \b
        Common targets:
          Ubuntu (autoinstall):  ubuntu2004, ubuntu2204, ubuntu2404, ubuntu2510, ubuntu2604
          Ubuntu/Kubuntu ARM64:  ubuntu2004arm64, ubuntu2204arm64, ubuntu2404arm64,
                                 kubuntu2004arm64, kubuntu2204arm64, kubuntu2404arm64
          Kubuntu x86_64:        kubuntu2004, kubuntu2204 (ubiquity), kubuntu2404 (GUI-auto)
          Debian (preseed):      debian12, debian13, kali
          Fedora/RHEL (kickstart): fedora44, fedora44kde, fedora43, fedora43kde, fedora42,
                                 fedora42arm64, fedora42kde, fedora41, fedora41arm64,
                                 fedora41kde, rocky9, alma9
          openSUSE (autoyast):   opensuseleap156, opensusetumbleweed
          GUI manual install:    mint, popos, nixos, elementary
          Windows (unattend):    windows10, windows11, windows11arm64

        \b
        Kubuntu publishes no arm64 desktop ISO at all, and Ubuntu only from
        24.04.3 on, so every *arm64 profile installs the live-server ISO of the
        matching version and pulls in the desktop metapackage
        (ubuntu-desktop-minimal / kubuntu-desktop).
        The x86_64 kubuntu2004/kubuntu2204 profiles ship untested — see
        docs "VM image creation".

        \b
        Examples:
          adare vm create ubuntu2404
          adare vm create debian12 --iso /path/to/debian-12-netinst.iso
          adare vm create fedora42arm64 --iso /path/to/Fedora-Everything-netinst-aarch64-42.iso
          adare vm create kubuntu2204arm64 --iso /path/to/ubuntu-22.04.5-live-server-arm64.iso
          adare vm create fedora41 --iso /path/to/Fedora-Workstation-Live.iso
          adare vm create kali --iso /path/to/kali-linux-installer.iso
          adare vm create mint --iso /path/to/linuxmint.iso       # manual install
          adare vm create kubuntu2404 --iso /path/to/kubuntu.iso  # GUI-automated (record then replay)
          adare vm create ubuntu2404 --bare
          adare vm create ubuntu2404 --setup base
          adare vm create ubuntu2404 --interactive
          adare vm create windows11 --iso /path/to/Win11.iso
          adare vm create ubuntu2404 --iso /path/to/ubuntu.iso --recipe
          adare vm create windows11arm64 --iso /path/to/Win11_arm64.iso --byo-iso
          adare vm create ubuntu2204 --name my-ubuntu --disk-size 100G --ram 8192
        """
        from adare.cli.vm_create import exec_vm_create

        args = SimpleNamespace(
            os_name=os_name,
            iso=iso,
            name=name,
            disk_size=disk_size,
            ram=ram,
            cpus=cpus,
            force=force,
            vm_dir=vm_dir,
            setup_level=setup_level,
            bare=bare,
            env_name=env_name,
            interactive=interactive,
            arch=arch,
            allow_emulation=allow_emulation,
            recipe=recipe,
            byo_iso=byo_iso,
            iso_notes=iso_notes,
            record=record,
            relearn=relearn,
            display=display,
            template=template,
            compress=compress,
        )
        exec_with_error_printing(exec_vm_create, args)

    # ------------------------------
    # OS profiles (the OS_NAME targets of `vm create`)
    # ------------------------------
    @vm.group(name='profile', cls=AliasedGroup)
    def profile():
        """OS profiles: the OS_NAME targets `adare vm create` can install."""

    @profile.command(name='list')
    @output_options
    def profile_list():
        """List all available OS profiles."""
        from adare.cli.manage_os_profile import exec_os_profile_list

        exec_with_error_printing(exec_os_profile_list, SimpleNamespace())

    @profile.command(name='add')
    @click.argument('profile_file', type=click.Path(exists=True))
    def profile_add(profile_file):
        """Add a custom OS profile from a YAML file."""
        from adare.cli.manage_os_profile import exec_os_profile_add

        exec_with_error_printing(exec_os_profile_add, SimpleNamespace(profile_file=profile_file))

    @profile.command(name='show')
    @output_options
    @click.argument('name')
    def profile_show(name):
        """Show detailed information about an OS profile."""
        from adare.cli.manage_os_profile import exec_os_profile_show

        exec_with_error_printing(exec_os_profile_show, SimpleNamespace(name=name))

    @profile.command(name='remove')
    @click.argument('name')
    def profile_remove(name):
        """Remove a custom OS profile."""
        from adare.cli.manage_os_profile import exec_os_profile_remove

        exec_with_error_printing(exec_os_profile_remove, SimpleNamespace(name=name))

    @vm.command(name='doctor')
    @output_options
    def vm_doctor():
        """Report on system-level QEMU/VM-creation tool availability.

        Locates qemu-system/qemu-img, OVMF firmware, swtpm, the libvirt Python
        binding, and (on Apple Silicon) the wimlib/7z/xorriso trio used for the
        Win11-ARM64 legacy-boot workaround. Detect-and-report only — never
        installs anything and always exits 0.
        """
        from adare.cli.vm_doctor import exec_vm_doctor

        args = SimpleNamespace()
        exec_with_error_printing(exec_vm_doctor, args)

    @vm.command(name='reset')
    @click.option('--force', '-f', is_flag=True, help='Skip the confirmation prompt')
    def vm_reset(force):
        """Remove the instances of every VM, running or not (registered VMs stay)."""
        from adare.cli.manage import exec_manage_reset_vm

        args = SimpleNamespace(force=force)
        exec_with_error_printing(exec_manage_reset_vm, args)

    # Add aliases for vm commands
    vm.add_alias('l', 'list')
    vm.add_alias('rm', 'remove')

    # Add aliases for snapshot commands
    snapshot.add_alias('l', 'list')
    snapshot.add_alias('rm', 'remove')

    profile.add_alias('l', 'list')
    profile.add_alias('rm', 'remove')

    return vm
