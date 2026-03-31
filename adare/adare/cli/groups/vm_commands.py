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

    @vm.command()
    @click.argument('ova_file', type=click.Path(exists=True))
    @click.option('--platform', '-p', required=True, type=click.Choice(['linux', 'windows']), help='VM platform (required)')
    @click.option('--verbose', '-v', is_flag=True, help='Enable verbose output with detailed error information')
    @click.option('--keep-vm', is_flag=True, help='Keep the test VM after completion (for further testing)')
    @click.option('--remove-vm', is_flag=True, help='Automatically remove the test VM after completion')
    def test(ova_file, platform, verbose, keep_vm, remove_vm):
        """Test OVA file compatibility with ADARE.

        This command validates an .ova file by:
        - Importing the VM temporarily
        - Setting up shared directories and mounting them
        - Installing dependencies and starting adarevm
        - Establishing WebSocket connection
        - Taking a screenshot and performing a test click
        - Cleaning up all temporary resources

        Example: adare vm test ubuntu22.ova --platform linux
        Example: adare vm test windows11.ova --platform windows --verbose
        Example: adare vm test ubuntu22.ova --platform linux --keep-vm
        Example: adare vm test ubuntu22.ova --platform linux --remove-vm
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
            ova_file=ova_file,
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
    @click.option('--bare', is_flag=True, default=False, help='Skip ADARE agent software (Miniforge3, qemu-guest-agent)')
    @click.option('--env-name', default=None, help='Environment file name (defaults to VM name)')
    @click.option('--interactive', is_flag=True, default=False, help='Boot VM after install for manual software installation')
    @click.option('--arch', type=click.Choice(['x86_64', 'aarch64']), default=None, help='Override CPU architecture (default: from OS profile)')
    def vm_create(os_name, iso, name, disk_size, ram, cpus, force, vm_dir, bare, env_name, interactive, arch):
        """Create a new ADARE-ready VM from scratch.

        OS_NAME is the target OS: ubuntu2404, ubuntu2204, windows11, windows11arm64, windows10

        \b
        Examples:
          adare vm create ubuntu2404
          adare vm create ubuntu2404 --bare
          adare vm create ubuntu2404 --interactive
          adare vm create windows11 --iso /path/to/Win11.iso
          adare vm create windows11arm64 --iso /path/to/Win11_ARM64.iso
          adare vm create windows11 --arch aarch64 --iso /path/to/Win11_ARM64.iso
          adare vm create ubuntu2204 --name my-ubuntu --disk-size 100G --ram 8192
          adare vm create ubuntu2404 --name my-vm --env-name my-env
          adare vm create ubuntu2404 --vm-dir /tmp/my-vms
        """
        from adare.cli.vm_create import exec_vm_create
        args = SimpleNamespace(os_name=os_name, iso=iso, name=name, disk_size=disk_size, ram=ram, cpus=cpus, force=force, vm_dir=vm_dir, bare=bare, env_name=env_name, interactive=interactive, arch=arch)
        exec_with_error_printing(exec_vm_create, args)

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
