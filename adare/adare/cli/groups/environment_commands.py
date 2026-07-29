"""Environment management commands (`adare env ...`).

Extracted from ``run.py`` following the same ``register(cli, ...)`` pattern as
``vm_commands`` / ``experiment_commands`` / ``web_commands`` / ``dev_commands``:
``run.py`` was at 936 lines against this project's 1000-line ceiling, and the
recipe-provisioning + BYO-ISO options push the ``env`` group well past it.
"""

from types import SimpleNamespace

import click


def register(cli, AliasedGroup, exec_with_error_printing):
    """Register environment management commands with the CLI."""

    # ------------------------------
    # Environment commands
    # ------------------------------
    @cli.group(name='env', cls=AliasedGroup)
    def env():
        """Environment management commands."""
        pass

    @env.command()
    @click.argument('environment', type=click.Path(exists=False))
    @click.option('--project', '-p', help='Name of the project')
    @click.option('--force', '-f', is_flag=True, help='Force update of the environment. For a recipe environment this rebuilds BOTH the base disk and the provisioning stage.')
    @click.option('--no-copy', is_flag=True, help='Keep VM file at original location instead of copying to managed storage (local files only). WARNING: Do not move or delete the original file!')
    @click.option('--iso', type=click.Path(exists=True), help='[recipe] Path to the installer ISO, or a directory to search for it. Use this to supply the ISO for a consumer-supplied ("BYO") recipe that declares iso_name.')
    @click.option('--reprovision', is_flag=True, help='[recipe] Reuse the cached base disk but re-run build-time provisioning from scratch. The retry path after a failed provisioning step — minutes instead of a full OS reinstall.')
    @click.option('--allow-emulation', is_flag=True, help='[recipe] Allow QEMU TCG software emulation when the recipe profile\'s guest architecture does not match the host CPU (slow).')
    def load(environment, project, force, no_copy, iso, reprovision, allow_emulation):
        """Load an environment.

        ENVIRONMENT can be:
        - Simple name: ubuntu24
        - Relative path: environments/ubuntu24.yml
        - Relative path: ./environments/ubuntu24.yaml

        The --no-copy flag prevents copying VM files to managed storage (~/.adare/state/vms).
        This is useful for large VMs or when disk space is limited.
        Note: The VM file must remain at the original location for experiments to work.

        For a recipe environment the disk is BUILT here from the declared inputs.
        A consumer-supplied ("BYO") recipe needs the ISO on this machine: drop it
        in ~/.adare/isos/, point $ADARE_ISO_DIR at its directory, or pass --iso.
        """
        from adare.cli.environment import exec_environment_load
        args = SimpleNamespace(
            environment=environment, project=project, force=force, no_copy=no_copy,
            iso=iso, reprovision=reprovision, allow_emulation=allow_emulation,
        )
        exec_with_error_printing(exec_environment_load, args)

    @env.command()
    @click.argument('name', type=click.Path(exists=False))
    @click.option('--project', '-p', help='Name of the project')
    @click.option('--with-vm', type=click.Path(exists=True), help='VM file path (OVA) to load automatically during environment creation')
    def create(name, project, with_vm):
        """Create an environment.

        NAME can be:
        - Simple name: ubuntu24
        - Relative path: environments/ubuntu24
        """
        from adare.cli.environment import exec_environment_create
        args = SimpleNamespace(name=name, project=project, with_vm=with_vm)
        exec_with_error_printing(exec_environment_create, args)

    @env.command(name='publish-prepare')
    @click.argument('name')
    @click.option('--vm-url', required=True, help='Published http(s) URL where the disk image is hosted (any host, incl. owncloud/Nextcloud share links)')
    @click.option('--vm-format', type=click.Choice(['qcow2', 'ova', 'vmdk', 'vdi', 'img', 'raw']), help='Disk format hint (inferred from the local disk extension when omitted; required if neither the local disk nor the URL names a recognized format)')
    @click.option('--verify-url', is_flag=True, help='Download the hosted URL and confirm its bytes hash-match the published disk (catches a wrong/HTML share link or a changed upload)')
    @click.option('--compress', is_flag=True, help='qcow2 only: zstd-compress the disk into a "<name>-published.qcow2" sibling file before hashing, and publish that instead (transparent to readers, typically ~30-50% smaller; upload the compressed file, not the original)')
    @click.option('--source-profile', help='Optional provenance: the OS profile this disk was built from. Informational only -- not validated, not used to rebuild the disk.')
    @click.option('--source-iso-sha256', help='Optional provenance: sha256 of the installer ISO this disk was built from, if still known. Informational only.')
    @click.option('--project', '-p', help='Name of the project')
    def publish_prepare(name, vm_url, vm_format, verify_url, compress, source_profile, source_iso_sha256, project):
        """Prepare a local baked environment for sharing (local disk -> URL + sha256).

        Hashes the local disk referenced by the environment's "vm:" field, then
        rewrites the descriptor to reference VM_URL with vm_type=url, the disk format,
        and the computed vm_sha256. Consumers re-verify that hash after downloading.

        --source-profile / --source-iso-sha256 attach optional install-profile
        provenance (which OS profile and, if known, source ISO this disk was built
        from) for audit/reproducibility purposes only -- they never make the
        environment rebuildable and are never required.

        NAME is the environment name (its descriptor lives in the project's
        environments directory).
        """
        from adare.cli.environment import exec_environment_publish_prepare
        args = SimpleNamespace(
            name=name, vm_url=vm_url, vm_format=vm_format,
            verify_url=verify_url, compress=compress, project=project,
            source_profile=source_profile, source_iso_sha256=source_iso_sha256,
        )
        exec_with_error_printing(exec_environment_publish_prepare, args)

    @env.command(name='recipe-byo')
    @click.argument('name')
    @click.option('--iso-name', help='Bare ISO filename the consumer must supply (defaults to the basename of the current "iso" path)')
    @click.option('--iso-notes', help='Plain-text download pointer for the consumer (defaults to the OS profile\'s iso_notes)')
    @click.option('--project', '-p', help='Name of the project')
    def recipe_byo(name, iso_name, iso_notes, project):
        """Convert a recipe environment's local ISO path into a consumer-supplied ISO.

        The publish-prepare analogue for recipe environments: rewrites the
        descriptor's "recipe.iso: /some/local/path.iso" into "recipe.iso_name" +
        "recipe.iso_notes", so the environment is publishable without rehosting a
        Windows ISO you are not licensed to redistribute.

        Windows profiles only — a Linux ISO is freely redistributable and must be
        published as an http(s) URL instead.

        The recipe hash is unchanged: how the consumer obtains the ISO is not a
        build input, so an already-built disk stays a cache hit.
        """
        from adare.cli.environment import exec_environment_recipe_byo
        args = SimpleNamespace(
            name=name, iso_name=iso_name, iso_notes=iso_notes, project=project,
        )
        exec_with_error_printing(exec_environment_recipe_byo, args)

    @env.command()
    @click.argument('source')
    @click.option('--name', '-n', required=True, help='Name for the new environment (must be unique)')
    @click.option('--install', '-i', multiple=True, help='Post-setup install as "name:command" (repeatable)')
    @click.option('--from-file', type=click.Path(exists=True), help='YAML file with post-setup installations to add')
    @click.option('--shell', is_flag=True, help='Run --install commands through a shell')
    @click.option('--cwd', help='Working directory for --install commands')
    @click.option('--interactive', '--manual', 'interactive', is_flag=True, help='Boot the base in a GUI window for manual, GUI-only customization (QEMU only)')
    @click.option('--console', is_flag=True, help='[interactive mode] Also open a terminal REPL that records typed commands as installs (requires --interactive)')
    @click.option('--ram', type=int, help='[interactive mode] RAM in MB for the boot window')
    @click.option('--cpus', type=int, help='[interactive mode] CPU count for the boot window')
    @click.option('--disk-name', help='[interactive mode] Name for the new flattened disk (defaults to --name)')
    @click.option('--compress/--no-compress', 'compress', default=True, help='[interactive mode] Zstd-compress the flattened disk. Default: on.')
    @click.option('--allow-emulation', is_flag=True, help='[interactive mode] Allow QEMU TCG software emulation when the base disk\'s guest architecture does not match the host CPU (slow).')
    @click.option('--description', '-d', help='Description for the new environment')
    @click.option('--tag', '-t', multiple=True, help='Tag to attach to the new environment (repeatable)')
    @click.option('--force', '-f', is_flag=True, help='Force overwrite if the new name already exists')
    @click.option('--project', '-p', help='Name of the project')
    def extend(source, name, install, from_file, shell, cwd, interactive, console,
               ram, cpus, disk_name, compress, allow_emulation, description, tag,
               force, project):
        """Extend an environment (or VM) into a new environment that reuses the same base disk.

        SOURCE can be an environment name, environment ULID, or VM name.

        Declarative mode (default): pass --install/--from-file to add post-setup
        installations on top of the source's existing ones; the new environment
        is a strict superset and shares the same underlying VM disk (no new VM
        is created).

        Interactive mode (--interactive, QEMU only): boots a throwaway overlay of
        the base disk in a GUI window so you can install software by hand. By
        default this is a GUI-only window; add --console to also open a terminal
        REPL that records the commands you type as reproducible installs. On
        shutdown you choose whether to store or discard the session; when stored,
        the overlay is flattened into a new standalone disk and registered as a
        NEW base VM + environment. May be combined with --install.
        """
        from adare.cli.environment_extend import exec_environment_extend
        args = SimpleNamespace(
            source=source, name=name, install=install, from_file=from_file,
            shell=shell, cwd=cwd, interactive=interactive, console=console,
            ram=ram, cpus=cpus, disk_name=disk_name, compress=compress,
            allow_emulation=allow_emulation, description=description, tag=tag,
            force=force, project=project,
        )
        exec_with_error_printing(exec_environment_extend, args)

    @env.command()
    @click.argument('name')
    @click.option('--project', '-p', help='Name of the project')
    def verify(name, project):
        """Verify an environment by running the built-in verify_vm experiment.

        Idempotently registers the verify_vm example experiment, attaches the
        environment, and runs it in the foreground with live progress."""
        from adare.cli.environment import exec_environment_verify
        args = SimpleNamespace(name=name, project=project)
        exec_with_error_printing(exec_environment_verify, args)

    @env.command()
    @click.argument('identifier')
    @click.option('--force', '-f', is_flag=True, help='Force deletion of the environment and any orphaned experiments')
    def remove(identifier, force):
        """Remove an environment.

        IDENTIFIER can be:
        - Environment name: ubuntu24
        - Environment ULID: 01K72Q25GDNHWMEZB97N9RDPG0

        WARNING: If this environment is the only one used by experiments,
        those experiments will become orphaned and be removed when using --force.
        Without --force, removal will fail to prevent data loss."""
        from adare.cli.environment import exec_environment_delete
        args = SimpleNamespace(identifier=identifier, force=force)
        exec_with_error_printing(exec_environment_delete, args)

    @env.command(name='list')
    def list_environments():
        """List all environments in a project."""
        from adare.cli.show import exec_show_environments
        args = SimpleNamespace()
        exec_with_error_printing(exec_show_environments, args)

    @env.command()
    @click.argument('environment_name')
    def info(environment_name):
        """Show detailed information about a specific environment."""
        from adare.cli.show import exec_show_environment
        args = SimpleNamespace(
            environment_name=environment_name,
        )
        exec_with_error_printing(exec_show_environment, args)

    # Add aliases for environment commands
    env.add_alias('l', 'list')
    env.add_alias('rm', 'remove')
    env.add_alias('ext', 'extend')

    return env
