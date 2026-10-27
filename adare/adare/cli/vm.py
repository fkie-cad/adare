# internal imports
# configure logging
import logging
from pathlib import Path

from adare.api import AdareAPI
from adare.cli.utils import handle_api_error
from adare.console import print_error_message, print_success_message
from adare.exceptions import DataStructuringError

log = logging.getLogger(__name__)


def exec_vm_list(arguments):
    """List all VMs and instances in the system."""
    from adare.frontend.terminal.vm_list import print_vm_and_instances_list
    from adare.run import get_formatter_from_context

    formatter, output_file, dual_output = get_formatter_from_context()
    print_vm_and_instances_list(formatter, output_file, dual_output)


def exec_vm_info(arguments):
    """Get detailed information about a VM or instance (auto-detected)."""
    from adare.frontend.terminal.vm import print_vm_or_instance_info
    from adare.run import get_formatter_from_context

    formatter, output_file, dual_output = get_formatter_from_context()
    print_vm_or_instance_info(arguments.vm_id, formatter, output_file, dual_output)


def exec_vm_publish(arguments):
    """Record where a registered image is hosted, in its image record."""
    from adare.backend.vm import image_record
    from adare.backend.vm.exceptions import VMNotFoundError

    found = image_record.record_of(arguments.vm)
    if found is None:
        raise VMNotFoundError(log, f'No registered VM "{arguments.vm}" (list them: adare vm list)')
    image, _ = found
    if arguments.verify_url:
        from adare.services.environment_service import verify_hosted_url

        result = verify_hosted_url(arguments.vm_url, image['hash'])
        if not result.success:
            handle_api_error(result)
    image_record.add_published(image['id'], arguments.vm_url, image['hash'])
    print_success_message(
        title=f'Image "{image["name"]}" recorded as published',
        location=arguments.vm_url,
        next_steps=[
            'Share an environment on it: adare env publish-prepare <environment> --vm-url ' + arguments.vm_url,
        ],
        tip='The environment file then carries this image record, so whoever loads it sees how the image was made.',
    )


def exec_vm_list_snapshots(arguments):
    """List all snapshots, optionally filtered by VM instance.

    Reads the snapshot records from the database (VmService.list_snapshots). The
    old path queried VirtualBox directly through a module that no longer exists,
    so the command crashed with ModuleNotFoundError on every host.
    """
    from rich.panel import Panel
    from rich.table import Table

    from adare.cli.output import emit

    api = AdareAPI()
    result = api.vm.list_snapshots(arguments.instance_id)
    if not result.success:
        handle_api_error(result)
        return
    snapshots = result.data or []

    def _panel():
        if not snapshots:
            return Panel(
                '[yellow]No snapshots found[/yellow]',
                title='[b gold3]snapshots[/b gold3]',
                border_style='blue',
                title_align='left',
            )
        table = Table(expand=True)
        table.add_column('name', style='yellow', no_wrap=True)
        table.add_column('type', style='cyan', no_wrap=True)
        table.add_column('instance', style='cyan', no_wrap=True)
        table.add_column('created', style='dim', no_wrap=True)
        table.add_column('description', style='dim')
        for snap in snapshots:
            table.add_row(
                snap.name,
                snap.snapshot_type,
                snap.vm_instance_id or '-',
                snap.created_at.strftime('%Y-%m-%d %H:%M:%S') if snap.created_at else '-',
                snap.description or '',
            )
        return Panel(
            table,
            title=f'[b gold3]snapshots ({len(snapshots)} total)[/b gold3]',
            border_style='blue',
            title_align='left',
        )

    emit({'snapshots': snapshots}, rich=_panel)


def exec_vm_delete_snapshot(arguments):
    """Delete a single snapshot from a specific VM instance using AdareAPI."""
    api = AdareAPI()
    result = api.vm.delete_snapshot(arguments.instance_id, arguments.snapshot_name)

    if result.success:
        print_success_message(title=f'Snapshot "{arguments.snapshot_name}" deleted successfully!')
    else:
        handle_api_error(result)


def exec_vm_clear_all(arguments):
    """Clear all VMs from the system using AdareAPI."""
    from adare.frontend.terminal.vm_cleanup import print_vm_clear_all_confirmation, print_vm_clear_all_results

    if not arguments.force:
        print_vm_clear_all_confirmation()
        return

    api = AdareAPI()
    result = api.vm.clear_all(force=arguments.force)

    if result.success:
        # Convert VmClearResult to dict format expected by print function
        results = {
            'deleted_count': result.data.deleted_count,
            'deleted_vms': result.data.deleted_vms,
            'failed_count': result.data.failed_count,
            'failed_vms': result.data.failed_vms,
        }
        print_vm_clear_all_results(results)
    else:
        handle_api_error(result)


def exec_vm_clear_by_environment(arguments):
    """Clear VMs associated with a specific environment using AdareAPI."""
    from adare.frontend.terminal.vm_cleanup import (
        print_vm_clear_environment_confirmation,
        print_vm_clear_environment_results,
    )

    if not arguments.force:
        print_vm_clear_environment_confirmation(arguments.environment_ulid)
        return

    api = AdareAPI()
    result = api.vm.clear_by_environment(arguments.environment_ulid, force=arguments.force)

    if result.success:
        # Convert VmClearResult to dict format expected by print function
        results = {
            'deleted_count': result.data.deleted_count,
            'deleted_vms': result.data.deleted_vms,
            'failed_count': result.data.failed_count,
            'failed_vms': result.data.failed_vms,
        }
        print_vm_clear_environment_results(results, arguments.environment_ulid)
    else:
        handle_api_error(result)


def exec_vm_watch(arguments):
    """Open a running VM's live screen in the browser via VirtualSpice.

    Resolves the VM name to a VirtualSpice uuid and opens its standalone display
    page. Read-only by default (safe for forensic runs); the observer can still
    toggle control from VirtualSpice's own toolbar.
    """
    import webbrowser
    from urllib.parse import quote

    from adare.webapi.vm_watch import resolve_vm_uuid

    # ADARE web server port (default of `adare ui start`); the in-app viewer is
    # served here, so the live view opens same-origin, not on VirtualSpice's :8081.
    ADARE_WEB_PORT = 8089

    name = arguments.name
    view_only = getattr(arguments, 'view_only', True)

    uuid = resolve_vm_uuid(name)
    if uuid is None:
        print_error_message(
            title=f"Could not open a live view for '{name}'",
            next_steps=[
                "Is VirtualSpice running?  Start it with:  adare ui start",
                f"Is the VM running?  Check:  adare vm list  (name must match '{name}')",
            ],
        )
        return

    url = f"http://127.0.0.1:{ADARE_WEB_PORT}/vm/watch?name={quote(name)}&view_only={'true' if view_only else 'false'}"
    webbrowser.open(url)
    print_success_message(
        title=f"Opening live view for '{name}'" + (" (view-only)" if view_only else " (interactive)"),
        next_steps=[f"If no tab opened, visit:  {url}"],
    )


def _vm_test_logfile_path(target: str) -> Path:
    """Default log path for 'adare vm test': the working directory, named after the target."""
    import re
    from datetime import datetime

    name = re.sub(r'[^A-Za-z0-9._-]+', '_', Path(target).stem) or 'vm'
    return Path.cwd() / f"adare-vm-test-{name}-{datetime.now():%Y%m%d-%H%M%S}.log"


def _attach_vm_test_log(arguments) -> Path | None:
    """Start the vm test's own log file unless disabled or already logging to one.

    Returns the path being written, or None when there is no file log.
    """
    import sys

    from adare.logger.logger import attach_logfile, get_current_logfile

    if getattr(arguments, 'no_log', False):
        return None
    current = get_current_logfile()
    if current is not None:  # the global --logfile already captures everything
        return Path(current)

    path = Path(arguments.log_file) if getattr(arguments, 'log_file', None) else _vm_test_logfile_path(arguments.target)
    try:
        attach_logfile(path)
    except OSError as e:
        print(f"Warning: cannot write vm test log to {path}: {e}", file=sys.stderr)
        return None
    log.info(f"COMMAND: {' '.join(sys.argv)}")
    return path


async def exec_vm_test(arguments):
    """Test ADARE compatibility of a VM: OVA file path OR registered VM name.

    Auto-detects the target:
    - existing file -> OVA compatibility test (--platform required)
    - otherwise -> resolve as a registered VM name and run the hypervisor-
      appropriate compatibility test (platform auto-derived from osinfo).

    Writes a debug log to the working directory unless --no-log (see
    ``_attach_vm_test_log``); its path is printed when the test ends, also on failure.
    """
    import sys

    logfile = _attach_vm_test_log(arguments)
    try:
        await _run_vm_test(arguments)
    finally:
        if logfile is not None:
            print(f"Log: {logfile}", file=sys.stderr)


async def _run_vm_test(arguments):
    import sys

    from adare.core.dto.vm import VmRegisteredTestRequest, VmTestRequest

    vm_cleanup_mode = getattr(arguments, 'vm_cleanup_mode', 'prompt')
    target_path = Path(arguments.target)

    api = AdareAPI()

    if target_path.is_file():
        # OVA flow (existing behavior) - platform is required here
        if not arguments.platform:
            print("Error: --platform is required when testing an OVA file", file=sys.stderr)
            sys.exit(1)

        result = await api.vm.test_ova(
            VmTestRequest(
                ova_file_path=target_path.resolve(),
                guest_platform=arguments.platform,
                verbose=arguments.verbose,
                vm_cleanup_mode=vm_cleanup_mode,
            )
        )
    else:
        # Registered-VM flow - resolve by name
        from adare.database.api.vm import VmApi

        vm = VmApi().get_vm_by_name(arguments.target)
        if vm is None:
            print(
                f"Error: '{arguments.target}' is neither an existing file nor a registered VM. Run 'adare vm list'.",
                file=sys.stderr,
            )
            sys.exit(1)

        # Derive platform from osinfo unless overridden on the command line
        if vm.osinfo is None and not arguments.platform:
            print(
                f"Error: cannot determine platform for VM '{vm.name}' - it has no OS info; pass --platform",
                file=sys.stderr,
            )
            sys.exit(1)

        platform = arguments.platform or vm.osinfo.platform
        architecture = (vm.osinfo.architecture or 'x86_64') if vm.osinfo is not None else 'x86_64'

        result = await api.vm.test_registered_vm(
            VmRegisteredTestRequest(
                vm_name=vm.name,
                disk_path=vm.file,
                guest_platform=platform,
                hypervisor=vm.hypervisor,
                architecture=architecture,
                verbose=arguments.verbose,
                vm_cleanup_mode=vm_cleanup_mode,
            )
        )

    if result.success:
        if result.data.success:
            print(f"✅ {result.data.message}")
            sys.exit(0)
        else:
            print(f"❌ {result.data.message}")
            sys.exit(1)
    else:
        handle_api_error(result)


# ==========================================
# VM INSTANCE MANAGEMENT COMMANDS
# ==========================================


def exec_vm_list_instances(arguments):
    """List all VM instances in the system."""
    from adare.frontend.terminal.vm_instances import print_vm_instances_list

    print_vm_instances_list()


def exec_vm_instance_info(arguments):
    """Get detailed information about a specific VM instance."""
    from adare.frontend.terminal.vm_instances import print_vm_instance_info

    print_vm_instance_info(arguments.instance_id)


def _clear_results_dict(data) -> dict:
    """VmClearResult -> the dict the cleanup printers expect."""
    return {
        'deleted_count': data.deleted_count,
        'deleted_vms': data.deleted_vms,
        'failed_count': data.failed_count,
        'failed_vms': data.failed_vms,
    }


def exec_vm_remove(arguments):
    """Remove a registered VM or a VM instance (auto-detected), or instances in bulk."""
    from adare.backend.vm.database import run_blocking
    from adare.cli.errors import EXIT_USAGE, fail
    from adare.frontend.terminal.vm_cleanup import (
        print_vm_clear_all_results,
        print_vm_clear_environment_confirmation,
        print_vm_clear_environment_results,
    )
    from adare.frontend.terminal.vm_instances import print_vm_instance_cleanup_results

    api = AdareAPI()

    if getattr(arguments, 'target', None):
        from adare.backend.vm.resolve import resolve_vm_target

        target = resolve_vm_target(arguments.target)
        if target.kind == 'vm':
            _remove_registered_vm(target, force=arguments.force, assume_yes=getattr(arguments, 'yes', False))
            return
        result = run_blocking(api.vm.remove_instance(target.id, force=arguments.force))
        if not result.success:
            handle_api_error(result)
        print_vm_instance_cleanup_results([target.name], "specific instance")

    elif arguments.all and arguments.force:
        # Remove ALL instances (running or not) — replaces 'vm clear all --force'
        result = api.vm.clear_all(force=True)
        if not result.success:
            handle_api_error(result)
        print_vm_clear_all_results(_clear_results_dict(result.data))

    elif arguments.all:
        fail(
            'USAGE',
            '--all requires --force',
            [
                'Use --all --force to remove ALL instances (including running ones)',
                'Use --stopped to remove only stopped instances',
            ],
            exit_code=EXIT_USAGE,
        )

    elif getattr(arguments, 'environment_ulid', None):
        # Remove the instances of an environment's VM — replaces 'vm clear environment'
        if not arguments.force:
            print_vm_clear_environment_confirmation(arguments.environment_ulid)
            return
        result = api.vm.clear_by_environment(arguments.environment_ulid, force=True)
        if not result.success:
            handle_api_error(result)
        print_vm_clear_environment_results(_clear_results_dict(result.data), arguments.environment_ulid)

    elif getattr(arguments, 'stopped', False):
        # Remove all stopped instances — replaces old '--all' behavior
        if not _confirm_removal("all stopped instances"):
            log.info("Operation cancelled by user")
            return
        result = run_blocking(api.vm.remove_all_stopped_instances())
        if not result.success:
            handle_api_error(result)
        print_vm_instance_cleanup_results(result.data.removed_instances, "all stopped instances")

    elif arguments.experiment_id:
        from adare.backend.vm.commands import cleanup_vm_instances_for_experiment

        run_blocking(cleanup_vm_instances_for_experiment(arguments.experiment_id))
        print_vm_instance_cleanup_results([arguments.experiment_id], "experiment instances")

    else:
        fail(
            'USAGE',
            'Nothing to remove: name a VM or instance, or pick instances to remove',
            [
                'adare vm remove <name-or-id>  (see `adare vm list` and `adare vm usage`)',
                'Or one of --stopped, --experiment <id>, --all --force, --env <ulid> --force',
            ],
            exit_code=EXIT_USAGE,
        )


def _stdin_is_terminal() -> bool:
    import sys

    return sys.stdin.isatty()


def _remove_registered_vm(target, force: bool, assume_yes: bool) -> None:
    """Remove a registered VM with its environments, after showing what goes and asking."""
    import click

    from adare.backend.vm.removal import plan_vm_removal, remove_vm
    from adare.cli.errors import EXIT_USAGE, fail
    from adare.frontend.terminal.vm_cleanup import print_vm_removal_plan

    plan = plan_vm_removal(target.id)
    plan.check(force=force)  # refuse before asking
    print_vm_removal_plan(plan, force)
    if not assume_yes:
        if not _stdin_is_terminal():
            fail(
                'USAGE',
                f'Refusing to remove VM {plan.vm_name} without confirmation (stdin is not a terminal)',
                ['Pass --yes to remove it without asking'],
                exit_code=EXIT_USAGE,
            )
        if not click.confirm('Remove it? This cannot be undone.', default=False):
            click.echo('Cancelled; nothing removed.')
            return

    outcome = remove_vm(target.id, force=force)
    details = [f'Removed environment {name}' for name in outcome.environments]
    if outcome.disk is not None:
        details.append(
            f'Deleted disk {outcome.disk}' if outcome.disk_deleted else f'Kept disk {outcome.disk} (not ADARE-managed)'
        )
    print_success_message(title=f'Removed VM {outcome.vm_name}')
    for detail in details:
        click.echo(f'   {detail}')


def _confirm_removal(target):
    """Ask user for confirmation before destructive operations."""
    try:
        response = input(f"Are you sure you want to remove {target}? This cannot be undone. [y/N]: ")
        return response.lower() in ['y', 'yes']
    except (EOFError, KeyboardInterrupt):
        return False


def exec_vm_instance_usage(arguments):
    """Show VM instance usage statistics."""
    from adare.frontend.terminal.vm_instances import print_vm_instance_usage
    from adare.run import get_formatter_from_context

    formatter, output_file, dual_output = get_formatter_from_context()
    print_vm_instance_usage(formatter, output_file, dual_output)


def _fmt_size(num_bytes: int) -> str:
    """Human-readable byte size (binary units)."""
    size = float(num_bytes)
    for unit in ('B', 'KiB', 'MiB', 'GiB', 'TiB'):
        if size < 1024 or unit == 'TiB':
            return f"{size:.1f} {unit}" if unit != 'B' else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} TiB"


def _physical_size(path: Path) -> int:
    """On-disk footprint of ``path`` in bytes.

    Uses allocated blocks (st_blocks * 512) so a CoW-cloned base that shares
    blocks with its template reports its true reclaimable cost, not its logical
    size. Falls back to st_size where st_blocks is unavailable (e.g. some
    non-POSIX filesystems).
    """
    try:
        st = path.stat()
    except OSError:
        return 0
    blocks = getattr(st, 'st_blocks', None)
    if blocks is None:
        return st.st_size
    return blocks * 512


def _live_recipe_base_hashes() -> set[str]:
    """Short base hashes still wanted by some registered recipe environment.

    A cached recipe base disk is never referenced by a ``Vm`` row (only the
    provisioned output is registered), so staleness cannot be read from the
    database. Instead every recipe environment on this host is re-hashed and its
    base hash collected; anything else in the cache is reclaimable.

    Deliberately conservative on error: an environment whose recipe can no longer
    be hashed (deleted file, unknown profile, edited provision block) contributes
    nothing, so at worst its base is reclaimed and the next load rebuilds it.
    """
    from adare.backend.environment.exceptions import EnvironmentLoadFailed
    from adare.backend.vm.recipe import compute_base_hash
    from adare.database.api.environment import EnvironmentDbApi
    from adare.types.environment import parse_environment_file

    with EnvironmentDbApi() as db:
        env_files = [env.file for env in db.get_environments(include_superseded=True) if env.file]

    hashes: set[str] = set()
    for env_file_str in env_files:
        env_file = Path(env_file_str)
        if not env_file.is_file():
            continue
        try:
            metadata = parse_environment_file(env_file)
        except (DataStructuringError, OSError, ValueError) as e:
            log.debug('vm prune: skipping unparsable environment %s: %s', env_file, e)
            continue
        if metadata is None or metadata.recipe is None:
            continue
        try:
            hashes.add(compute_base_hash(metadata)[:12])
        except (EnvironmentLoadFailed, KeyError, OSError) as e:
            log.debug('vm prune: could not hash recipe %s: %s', env_file, e)
    return hashes


def _print_reconcile_report(report, dry_run: bool) -> None:
    import click

    verb = 'Would remove' if dry_run else 'Removed'
    sections = [
        (f'{verb} crashed QEMU runs', report.removed_runs),
        (f'{"Would release" if dry_run else "Released"} instances of crashed runs', report.released_instances),
        (f'{verb} pooled QEMU instances (replaced by per-run overlays)', report.removed_pooled_qemu),
        (f'{verb} run files without an instance', report.orphaned_run_files),
    ]
    for title, names in sections:
        if names:
            click.echo(f"\n{title}:")
            for name in names:
                click.echo(f"                {name}")


def _print_unreferenced_vms() -> None:
    """List registered VMs no environment uses. Never deleted by prune: registering a disk
    without an environment is legitimate (the API does it), so removing one is a decision."""
    import click

    from adare.backend.vm.removal import find_unreferenced_vms

    unreferenced = find_unreferenced_vms()
    if not unreferenced:
        return
    click.echo("\nRegistered VMs no environment uses (kept; remove one with `adare vm remove <name>`):")
    for name, vm_id in unreferenced:
        click.echo(f"  {name}  ({vm_id})")


def _print_stopped_dev_sessions() -> None:
    """Point at the disk stopped dev sessions hold. Never deleted by prune: a stopped session
    can be resumed, so removing it is a decision (`adare dev remove --stopped`)."""
    import click

    from adare.backend.system.storage import group_disk_owners
    from adare.database.api.devmode import DevModeApi
    from adare.database.exceptions import DatabaseError
    from adare.hypervisor.qemu.mixins.configuration import get_qemu_disk_dir

    try:
        with DevModeApi() as api:
            names = {s.vm_name for s in api.list_sessions() if s.status in ('stopped', 'crashed')}
    except DatabaseError:
        return
    held = sum(o.bytes for o in group_disk_owners(get_qemu_disk_dir(), set(), {}) if o.name in names)
    if held:
        click.echo(
            f"\nStopped dev sessions keep {held / 1024**3:.1f} GiB of VM disks (kept; review and remove "
            "with `adare dev remove --stopped [--older-than 14d]`)."
        )


def exec_vm_prune(arguments):
    """Reclaim orphaned QEMU base disks / NVRAM (and optionally dead sockets).

    Mirrors the validated manual sweep: an orphan is a managed '-base.qcow2'
    (plus its '-nvram.fd' sibling) whose instance/VM is no longer registered
    in the database. Also sweeps cached recipe BASE disks
    (`~/.adare/qemu/cache/recipe-bases`) that no recipe environment still wants —
    those are pure cache, so reclaiming one only costs a rebuild.
    Deletes nothing unless --force is given.
    """
    import click

    from adare.backend.vm.database import run_blocking
    from adare.backend.vm.run_instances import reconcile_instances
    from adare.config.configdirectory import RECIPE_BASE_CACHE_DIR
    from adare.database.api.vm import VmApi
    from adare.hypervisor.qemu.mixins.configuration import (
        find_stale_sockets,
        get_qemu_disk_dir,
    )

    dry_run = getattr(arguments, 'dry_run', True)
    include_sockets = getattr(arguments, 'sockets', False)

    # 0. Instances: crashed runs, run files without a row, pooled QEMU leftovers.
    _print_reconcile_report(run_blocking(reconcile_instances(dry_run=dry_run)), dry_run)
    _print_unreferenced_vms()
    _print_stopped_dev_sessions()

    # 1. Referenced set: every registered VM + instance name from the DB.
    referenced: set[str] = set()
    with VmApi() as api:
        for vm in api.get_all_vms():
            referenced.add(vm.name)
        for instance in api.get_all_vm_instances():
            referenced.add(instance.instance_name)

    disk_dir = get_qemu_disk_dir()

    # 2. Scan for orphaned base disks + their nvram siblings.
    orphan_files: list[Path] = []
    seen: set[Path] = set()

    def _add(path: Path):
        if path.exists() and path not in seen:
            seen.add(path)
            orphan_files.append(path)

    for base_file in sorted(disk_dir.glob('*-base.qcow2')):
        name = base_file.name
        # Final backstop: never touch overlay/dev artifacts.
        if '-overlay-' in name or '-dev-' in name:
            continue
        stem = name[: -len('-base.qcow2')]
        if stem in referenced:
            continue  # still referenced — keep
        _add(base_file)
        _add(base_file.with_name(f"{stem}-nvram.fd"))

    # Also catch orphaned nvram whose base was already reclaimed.
    for nvram_file in sorted(disk_dir.glob('*-nvram.fd')):
        name = nvram_file.name
        if '-overlay-' in name or '-dev-' in name:
            continue
        stem = name[: -len('-nvram.fd')]
        if stem in referenced:
            continue
        _add(nvram_file)

    # 2b. Cached recipe BASE disks (Stage 1 of a recipe build). These are pure
    #     cache: they are never referenced by a VM row — only the *provisioned*
    #     disk is registered — so "orphaned" cannot be decided from the database.
    #     Instead, a base is reclaimable once no recipe environment currently
    #     resolves to its base hash. Losing one only costs a rebuild.
    stale_bases: list[Path] = []
    if RECIPE_BASE_CACHE_DIR.is_dir():
        live_base_hashes = _live_recipe_base_hashes()
        for base_file in sorted(RECIPE_BASE_CACHE_DIR.glob('*-recipebase-*.qcow2')):
            # Never touch an in-progress install. This glob also matches the
            # per-attempt `<hash>.partial-<pid>-<token>.qcow2` a running Stage 1 is
            # installing into, and its "hash" then reads as `<hash>.partial-…`,
            # which can never be in `live_base_hashes` — so EVERY running install
            # used to be classified stale and unlinked, dropping its QEMU onto an
            # unlinked inode and losing a 30-minute install with no error anywhere.
            # Leftovers from dead attempts are reclaimed by the next build of the
            # same base, which does it while holding that base's lock.
            if '.partial' in base_file.name:
                continue
            short_hash = base_file.stem.rsplit('-recipebase-', 1)[-1]
            if short_hash in live_base_hashes:
                continue
            _add(base_file)
            stale_bases.append(base_file)

    # 3. Optionally scan for crash-orphaned dead sockets (no running QEMU owns
    #    them). find_stale_sockets() cross-checks live libvirt domains, so a
    #    live-but-occupied QGA socket is never flagged.
    dead_sockets: list[Path] = []
    if include_sockets:
        dead_sockets = sorted(find_stale_sockets())

    # 4. Report.
    if not orphan_files and not dead_sockets:
        print_success_message(title="No orphaned QEMU disks or sockets found — nothing to reclaim.")
        return

    total_bytes = 0
    if orphan_files:
        click.echo("\nOrphaned base disks / NVRAM" + (" + stale recipe base cache" if stale_bases else "") + ":")
        click.echo(f"  {'SIZE':>12}  FILE")
        for path in orphan_files:
            size = _physical_size(path)
            total_bytes += size
            click.echo(f"  {_fmt_size(size):>12}  {path.name}")
        click.echo(f"  {'-' * 12}")
        click.echo(f"  {_fmt_size(total_bytes):>12}  ({len(orphan_files)} file(s))")

    if dead_sockets:
        click.echo("\nDead sockets (no live listener):")
        for sock_path in dead_sockets:
            click.echo(f"                {sock_path.name}")

    # 5. Delete (only with --force).
    if dry_run:
        click.echo(
            f"\nDry-run: nothing deleted. Re-run with --force to reclaim "
            f"{_fmt_size(total_bytes)} across {len(orphan_files)} file(s)"
            + (f" + {len(dead_sockets)} dead socket(s)." if dead_sockets else ".")
        )
        return

    reclaimed_bytes = 0
    reclaimed_files = 0
    for path in orphan_files:
        name = path.name
        # Backstop before every unlink.
        if '-overlay-' in name or '-dev-' in name:
            continue
        size = _physical_size(path)
        try:
            path.unlink()
            reclaimed_bytes += size
            reclaimed_files += 1
        except OSError as e:
            log.warning(f"Failed to remove {path}: {e}")

    reaped_sockets = 0
    for sock_path in dead_sockets:
        try:
            sock_path.unlink()
            reaped_sockets += 1
        except OSError as e:
            log.warning(f"Failed to remove socket {sock_path}: {e}")

    summary = f"Reclaimed {_fmt_size(reclaimed_bytes)} across {reclaimed_files} file(s)"
    if include_sockets:
        summary += f"; reaped {reaped_sockets} dead socket(s)"
    print_success_message(title=summary + ".")
