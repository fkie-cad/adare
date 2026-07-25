from types import SimpleNamespace

import click


def register(cli, AliasedGroup, exec_with_error_printing):
    """Register VM management commands with the CLI."""

    # ------------------------------
    # VM management commands
    # ------------------------------
    @cli.group(cls=AliasedGroup)
    def vm():
        """VM management commands."""
        pass

    @vm.command(name='list')
    def vm_list():
        """List all VMs in the system."""
        from adare.cli.vm import exec_vm_list
        args = SimpleNamespace()
        exec_with_error_printing(exec_vm_list, args)

    @vm.command()
    @click.argument('vm_id')
    def info(vm_id):
        """Get detailed information about a VM."""
        from adare.cli.vm import exec_vm_info
        args = SimpleNamespace(vm_id=vm_id)
        exec_with_error_printing(exec_vm_info, args)

    @vm.command()
    @click.option('--id', 'instance_id', help='Remove specific instance by ULID')
    @click.option('--stopped', is_flag=True, help='Remove all stopped instances')
    @click.option('--experiment', 'experiment_id', help='Remove instances for specific experiment')
    @click.option('--all', is_flag=True, help='Remove ALL instances including running (requires --force)')
    @click.option('--env', 'environment_ulid', help='Remove all VMs for a specific environment (requires --force)')
    @click.option('--force', is_flag=True, help='Force removal of running instances')
    def remove(instance_id, stopped, experiment_id, all, environment_ulid, force):
        """Remove VM instances.

        Examples:
            adare vm remove --id <ulid>              # specific instance
            adare vm remove --stopped                 # all stopped instances
            adare vm remove --experiment <id>         # instances for experiment
            adare vm remove --all --force             # ALL instances (running or not)
            adare vm remove --env <ulid> --force      # all VMs for environment
        """
        from adare.cli.vm import exec_vm_instance_remove
        args = SimpleNamespace(
            instance_id=instance_id,
            stopped=stopped,
            experiment_id=experiment_id,
            all=all,
            environment_ulid=environment_ulid,
            force=force
        )
        exec_with_error_printing(exec_vm_instance_remove, args)

    @vm.command()
    def usage():
        """Show VM instance usage statistics."""
        from adare.cli.vm import exec_vm_instance_usage
        args = SimpleNamespace()
        exec_with_error_printing(exec_vm_instance_usage, args)

    @vm.command(name='prune')
    @click.option('--dry-run/--force', 'dry_run', default=True,
                  help='Dry-run (default) previews only; --force actually deletes.')
    @click.option('--sockets', is_flag=True, default=False,
                  help='Also reap crash-orphaned dead QMP/QGA sockets in run/.')
    def vm_prune(dry_run, sockets):
        """Reclaim orphaned QEMU base disks (and, with --sockets, dead sockets).

        An orphan is a '<name>-base.qcow2' (plus its '-nvram.fd' sibling) whose
        instance/VM is no longer registered in the database. This is the
        garbage collector for debris left by older removal paths or crashes.

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
    @click.option('--view-only/--interactive', 'view_only', default=True,
                  help='Read-only view (default) or allow input. Toggle live from '
                       "VirtualSpice's own toolbar either way.")
    def vm_watch(name, view_only):
        """Watch a running VM's live screen in the browser (via VirtualSpice).

        NAME is the VM/instance name (run 'adare vm list' to see names). Opens
        VirtualSpice's standalone display page pointed at that VM. Requires
        VirtualSpice to be running (started by 'adare web start').

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
    @click.option('--platform', '-p', required=False, type=click.Choice(['linux', 'windows']), help='VM platform (required for OVA files; auto-derived for registered VMs)')
    @click.option('--verbose', '-v', is_flag=True, help='Enable verbose output with detailed error information')
    @click.option('--keep-vm', is_flag=True, help='Keep the test VM after completion (for further testing)')
    @click.option('--remove-vm', is_flag=True, help='Automatically remove the test VM after completion')
    def test(target, platform, verbose, keep_vm, remove_vm):
        """Test ADARE compatibility of a VM.

        TARGET may be either:
        - a path to an .ova/.ovf file (VirtualBox OVA import test), or
        - the name of a registered VM (run 'adare vm list' to see names).

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
        """
        # Handle cleanup options
        if keep_vm and remove_vm:
            click.echo("Error: Cannot specify both --keep-vm and --remove-vm", err=True)
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
            vm_cleanup_mode=vm_cleanup_mode
        )
        exec_with_error_printing(exec_vm_test, args)

    # Nested group for snapshot management
    @vm.group(cls=AliasedGroup)
    def snapshot():
        """Snapshot management commands."""
        pass

    @snapshot.command(name='list')
    @click.option('--instance', '-i', 'instance_id', help='Filter by specific VM instance ID')
    def snapshot_list(instance_id):
        """List all snapshots. Use --instance to filter by specific VM instance."""
        from adare.cli.vm import exec_vm_list_snapshots
        args = SimpleNamespace(instance_id=instance_id)
        exec_with_error_printing(exec_vm_list_snapshots, args)

    @snapshot.command()
    @click.argument('instance_id')
    @click.argument('snapshot_name')
    def remove(instance_id, snapshot_name):
        """Delete a single snapshot from a specific VM instance."""
        from adare.cli.vm import exec_vm_delete_snapshot
        args = SimpleNamespace(instance_id=instance_id, snapshot_name=snapshot_name)
        exec_with_error_printing(exec_vm_delete_snapshot, args)

    @vm.command(name='create')
    @click.argument('os_name')
    @click.option('--iso', type=click.Path(exists=True), help='Path to OS ISO (required for Windows)')
    @click.option('--name', help='VM name (auto-generated if not set)')
    @click.option('--disk-size', default=None, help='Disk size (default: 60G Linux, 80G Windows)')
    @click.option('--ram', type=int, default=None, help='RAM in MB')
    @click.option('--cpus', type=int, default=None, help='CPU count')
    @click.option('--force', is_flag=True, default=False, help='Overwrite existing VM disk image')
    @click.option('--vm-dir', type=click.Path(), default=None, help='Directory for VM disk image (default: ~/.adare/state/vms/)')
    @click.option('--setup', 'setup_level', type=click.Choice(['bare', 'base', 'full', 'agent']),
                  default=None,
                  help='What to install during creation: bare (OS only), base (+ guest tools), '
                       'full (+ Python env, default), agent (+ pre-installed adarevm, '
                       'not implemented).')
    @click.option('--bare', is_flag=True, default=False,
                  help='Deprecated alias for --setup bare.')
    @click.option('--env-name', default=None, help='Environment file name (defaults to VM name)')
    @click.option('--interactive', is_flag=True, default=False, help='Boot VM after install for manual software installation')
    @click.option('--arch', type=click.Choice(['x86_64', 'aarch64']), default=None, help='Override CPU architecture (default: from OS profile)')
    @click.option('--allow-emulation', is_flag=True, default=False, help='Allow QEMU TCG software emulation when --arch does not match the host CPU (slow; hardware acceleration is used otherwise).')
    @click.option('--recipe/--no-recipe', 'recipe', default=None, help='Emit a declarative recipe environment (build on load) instead of a baked disk. Default: recipe for Windows, baked for Linux.')
    @click.option('--record', is_flag=True, default=False, help='GUI-auto: record a fresh playbook with the vision agent even if a cached one exists.')
    @click.option('--relearn', is_flag=True, default=False, help='GUI-auto: discard the cached playbook and re-record from scratch.')
    @click.option('--display', is_flag=True, default=False, help='GUI-auto: show the VM window while the agent drives the installer.')
    @click.option('--template', default=None, help='GUI-auto: explicit goal/spec template name (default: gui_<distribution>).')
    @click.option('--compress/--no-compress', 'compress', default=True, help='Zstd-compress the finished base disk (~30-50% smaller, transparent to readers). Default: on.')
    def vm_create(os_name, iso, name, disk_size, ram, cpus, force, vm_dir, setup_level, bare, env_name, interactive, arch, allow_emulation, recipe, record, relearn, display, template, compress):
        """Create a new ADARE-ready VM from scratch.

        OS_NAME is the target OS. Run `adare os-profile list` to see all entries.

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
        Neither Ubuntu nor Kubuntu publishes an arm64 desktop ISO, so every
        *arm64 profile installs the live-server ISO of the matching version and
        pulls in the desktop metapackage (ubuntu-desktop-minimal / kubuntu-desktop).
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
          adare vm create ubuntu2204 --name my-ubuntu --disk-size 100G --ram 8192
        """
        from adare.cli.vm_create import exec_vm_create
        args = SimpleNamespace(os_name=os_name, iso=iso, name=name, disk_size=disk_size, ram=ram, cpus=cpus, force=force, vm_dir=vm_dir, setup_level=setup_level, bare=bare, env_name=env_name, interactive=interactive, arch=arch, allow_emulation=allow_emulation, recipe=recipe, record=record, relearn=relearn, display=display, template=template, compress=compress)
        exec_with_error_printing(exec_vm_create, args)

    @vm.command(name='gui-doctor')
    def vm_gui_doctor():
        """Preflight the vision-LLM used for GUI automation (ADARE_VLLM_*).

        Confirms the endpoint (e.g. Ollama Cloud) is reachable and detects which
        coordinate convention the model returns, recommending ADARE_VLLM_COORD_SPACE.
        """
        from adare.cli.vm_gui_doctor import exec_vm_gui_doctor
        args = SimpleNamespace()
        exec_with_error_printing(exec_vm_gui_doctor, args)

    @vm.command(name='doctor')
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
    @click.option('--force', '-f', is_flag=True, help='Force reset of all VMs (required for confirmation)')
    def vm_reset(force):
        """Reset all VMs in the system (use with caution)."""
        from adare.cli.manage import exec_manage_reset_vm
        args = SimpleNamespace(force=force)
        exec_with_error_printing(exec_manage_reset_vm, args)

    # Add aliases for vm commands
    vm.add_alias('l', 'list')
    vm.add_alias('rm', 'remove')

    # Add aliases for snapshot commands
    snapshot.add_alias('l', 'list')
    snapshot.add_alias('rm', 'remove')

    return vm
