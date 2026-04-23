from types import SimpleNamespace

import click


def register(cli, AliasedGroup, exec_with_error_printing):
    """Register web interface commands with the CLI."""

    # ------------------------------
    # Web interface commands
    # ------------------------------
    @cli.group()
    def web():
        """Web interface commands."""
        pass

    @web.command()
    def login():
        """Login to the web interface."""
        from adare.cli.web import exec_web_login
        args = SimpleNamespace()
        exec_with_error_printing(exec_web_login, args)

    @web.command()
    def logout():
        """Logout from the web interface."""
        from adare.cli.web import exec_web_logout
        args = SimpleNamespace()
        exec_with_error_printing(exec_web_logout, args)

    @web.command()
    def status():
        """Show the web login status."""
        from adare.cli.web import exec_web_status
        args = SimpleNamespace()
        exec_with_error_printing(exec_web_status, args)

    # Nested group for web download commands
    @web.group()
    def download():
        """Download experiments, testfunctions, or environments from the web."""
        pass

    @download.command(name='experiment')
    @click.argument('ulid')
    def download_experiment(ulid):
        """Download an experiment."""
        from adare.cli.web import exec_download_experiment
        args = SimpleNamespace(ulid=ulid)
        exec_with_error_printing(exec_download_experiment, args)

    @download.command(name='testfunction')
    @click.argument('name')
    @click.option('--version', '-v', type=int, default=None, help='Specific version to download (default: latest)')
    def download_testfunction(name, version):
        """Download a testfunction."""
        from adare.cli.web import exec_download_testfunction
        args = SimpleNamespace(name=name, version=version)
        exec_with_error_printing(exec_download_testfunction, args)

    @download.command(name='environment')
    @click.argument('name')
    def download_environment(name):
        """Download an environment."""
        from adare.cli.web import exec_download_environment
        args = SimpleNamespace(name=name)
        exec_with_error_printing(exec_download_environment, args)

    @download.command(name='bundle')
    @click.argument('ulid')
    @click.option('--include-disk-images', is_flag=True, default=False, help='Also download disk images')
    @click.option('--project', '-p', help='Name of the project')
    def download_bundle(ulid, include_disk_images, project):
        """Download an experiment bundle (experiment + all dependencies)."""
        from adare.cli.web import exec_download_bundle
        args = SimpleNamespace(ulid=ulid, include_disk_images=include_disk_images, project=project)
        exec_with_error_printing(exec_download_bundle, args)

    @web.command()
    @click.argument('ulid')
    @click.option('--project', '-p', help='Name of the project')
    def publish(ulid, project):
        """Publish an experiment run to the server with progress tracking."""
        from adare.cli.web import exec_web_publish_run
        args = SimpleNamespace(ulid=ulid, project=project)
        exec_with_error_printing(exec_web_publish_run, args)

    # Nested group for web check commands
    @web.group()
    def check():
        """Check if resources exist on the server."""
        pass

    @check.command(name='experiment')
    @click.argument('ulid')
    def check_experiment(ulid):
        """Check if an experiment exists on the server."""
        from adare.cli.web import exec_web_check_experiment
        args = SimpleNamespace(ulid=ulid)
        exec_with_error_printing(exec_web_check_experiment, args)

    @check.command(name='run')
    @click.argument('ulid')
    def check_run(ulid):
        """Check if an experiment run exists on the server."""
        from adare.cli.web import exec_web_check_run
        args = SimpleNamespace(ulid=ulid)
        exec_with_error_printing(exec_web_check_run, args)

    @web.command()
    @click.option('--project', '-p', help='Name of the project')
    def sync(project):
        """Sync all environments and experiments with the web interface."""
        from adare.cli.web import exec_web_sync
        args = SimpleNamespace(project=project)
        exec_with_error_printing(exec_web_sync, args)

    # Nested group for web submit commands
    @web.group()
    def submit():
        """Submit experiments, testfunctions, or environments as PRs."""
        pass

    @submit.command(name='experiment')
    @click.argument('name')
    @click.option('--project', '-p', help='Name of the project')
    def submit_experiment(name, project):
        """Submit an experiment as a PR to the shared repository."""
        from adare.cli.web import exec_submit_experiment
        args = SimpleNamespace(name=name, project=project)
        exec_with_error_printing(exec_submit_experiment, args)

    @submit.command(name='testfunction')
    @click.argument('name')
    @click.option('--project', '-p', help='Name of the project')
    def submit_testfunction(name, project):
        """Submit a testfunction as a PR to the shared repository."""
        from adare.cli.web import exec_submit_testfunction
        args = SimpleNamespace(name=name, project=project)
        exec_with_error_printing(exec_submit_testfunction, args)

    @submit.command(name='environment')
    @click.argument('name')
    @click.option('--project', '-p', help='Name of the project')
    def submit_environment(name, project):
        """Submit an environment as a PR to the shared repository."""
        from adare.cli.web import exec_submit_environment
        args = SimpleNamespace(name=name, project=project)
        exec_with_error_printing(exec_submit_environment, args)

    return web
