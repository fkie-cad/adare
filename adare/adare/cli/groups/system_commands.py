"""`adare system` - host resources, storage, run capacity and measured run usage."""

from types import SimpleNamespace

import click

from adare.cli.output import output_options


def register(cli, AliasedGroup, exec_with_error_printing):
    """Register the system resource commands with the CLI."""

    @cli.group(name='system', cls=AliasedGroup)
    def system():
        """Host resources, storage, run capacity and measured run usage."""

    @system.command(name='resources')
    @output_options
    def system_resources():
        """Live CPU, memory, disk and the running VMs."""
        from adare.cli.system import exec_system_resources

        exec_with_error_printing(exec_system_resources, SimpleNamespace())

    @system.command(name='storage')
    @click.option('--refresh', is_flag=True, help='Re-measure instead of using the report cached for a few minutes.')
    @output_options
    def system_storage(refresh):
        """Where the disk space under ADARE's directories goes (incl. orphaned run disks)."""
        from adare.cli.system import exec_system_storage

        exec_with_error_printing(exec_system_storage, SimpleNamespace(refresh=refresh))

    @system.command(name='capacity')
    @output_options
    def system_capacity():
        """How many more runs of each environment fit on this host right now."""
        from adare.cli.system import exec_system_capacity

        exec_with_error_printing(exec_system_capacity, SimpleNamespace())

    @system.command(name='usage')
    @click.option('--environment', '-e', default=None, help='Only runs of this environment.')
    @click.option('--limit', default=50, show_default=True, help='Number of runs to show.')
    @output_options
    def system_usage(environment, limit):
        """Measured CPU, RAM and disk of recent experiment runs."""
        from adare.cli.system import exec_system_usage

        exec_with_error_printing(exec_system_usage, SimpleNamespace(environment=environment, limit=limit))

    @system.group(name='settings', cls=AliasedGroup, invoke_without_command=True)
    @click.pass_context
    def settings(ctx):
        """Host limits ADARE keeps to (VMs at once, free disk, dev-session expiry).

        Each resolves: environment variable > saved setting > default.

        \b
        Example:
            adare system settings set ADARE_DEV_SESSION_MAX_AGE_DAYS 30
        """
        if ctx.invoked_subcommand is None:
            ctx.invoke(settings_list)

    @settings.command(name='list')
    @output_options
    def settings_list():
        """Every setting with its value, where the value comes from, and its default."""
        from adare.cli.settings import exec_settings_list

        exec_with_error_printing(exec_settings_list, SimpleNamespace())

    @settings.command(name='get')
    @click.argument('name')
    def settings_get(name):
        """Show one setting (NAME with or without the ADARE_ prefix)."""
        from adare.cli.settings import exec_settings_get

        exec_with_error_printing(exec_settings_get, SimpleNamespace(name=name))

    @settings.command(name='set')
    @click.argument('name')
    @click.argument('value')
    def settings_set(name, value):
        """Save a setting for this host."""
        from adare.cli.settings import exec_settings_set

        exec_with_error_printing(exec_settings_set, SimpleNamespace(name=name, value=value))

    @settings.command(name='unset')
    @click.argument('name')
    def settings_unset(name):
        """Remove a saved setting (back to its default)."""
        from adare.cli.settings import exec_settings_unset

        exec_with_error_printing(exec_settings_unset, SimpleNamespace(name=name))

    return system
