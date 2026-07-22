# internal imports
# configure logging
import logging
from pathlib import Path

from adare.api import AdareAPI
from adare.cli.utils import handle_api_error
from adare.console import print_error_message, print_success_message

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


def exec_vm_list_snapshots(arguments):
    """List all snapshots, optionally filtered by VM instance."""
    from adare.frontend.terminal.vm import print_all_snapshots
    from adare.run import get_formatter_from_context

    formatter, output_file, dual_output = get_formatter_from_context()
    print_all_snapshots(arguments.instance_id, formatter, output_file, dual_output)


def exec_vm_delete_snapshot(arguments):
    """Delete a single snapshot from a specific VM instance using AdareAPI."""
    api = AdareAPI()
    result = api.vm.delete_snapshot(arguments.instance_id, arguments.snapshot_name)

    if result.success:
        print_success_message(
            title=f'Snapshot "{arguments.snapshot_name}" deleted successfully!'
        )
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

    from adare.webapi.vm_watch import DEFAULT_SPICE_PORT, resolve_vm_uuid

    # ADARE web server port (default of `adare web start`); the in-app viewer is
    # served here, so the live view opens same-origin, not on VirtualSpice's :8081.
    ADARE_WEB_PORT = 8089

    name = arguments.name
    view_only = getattr(arguments, 'view_only', True)

    uuid = resolve_vm_uuid(name, spice_port=DEFAULT_SPICE_PORT)
    if uuid is None:
        print_error_message(
            title=f"Could not open a live view for '{name}'",
            next_steps=[
                "Is VirtualSpice running?  Start it with:  adare web start",
                f"Is the VM running?  Check:  adare vm list  (name must match '{name}')",
            ],
        )
        return

    url = (
        f"http://127.0.0.1:{ADARE_WEB_PORT}/vm/watch"
        f"?name={quote(name)}&view_only={'true' if view_only else 'false'}"
    )
    webbrowser.open(url)
    print_success_message(
        title=f"Opening live view for '{name}'"
        + (" (view-only)" if view_only else " (interactive)"),
        next_steps=[f"If no tab opened, visit:  {url}"],
    )


async def exec_vm_test(arguments):
    """Test ADARE compatibility of a VM: OVA file path OR registered VM name.

    Auto-detects the target:
    - existing file -> OVA compatibility test (--platform required)
    - otherwise -> resolve as a registered VM name and run the hypervisor-
      appropriate compatibility test (platform auto-derived from osinfo).
    """
    import sys
    from pathlib import Path

    from adare.core.dto.vm import VmRegisteredTestRequest, VmTestRequest

    vm_cleanup_mode = getattr(arguments, 'vm_cleanup_mode', 'prompt')
    target_path = Path(arguments.target)

    api = AdareAPI()

    if target_path.is_file():
        # OVA flow (existing behavior) - platform is required here
        if not arguments.platform:
            print("Error: --platform is required when testing an OVA file", file=sys.stderr)
            sys.exit(1)

        result = await api.vm.test_ova(VmTestRequest(
            ova_file_path=target_path.resolve(),
            guest_platform=arguments.platform,
            verbose=arguments.verbose,
            vm_cleanup_mode=vm_cleanup_mode
        ))
    else:
        # Registered-VM flow - resolve by name
        from adare.database.api.vm import VmApi

        vm = VmApi().get_vm_by_name(arguments.target)
        if vm is None:
            print(
                f"Error: '{arguments.target}' is neither an existing file nor a registered VM. "
                "Run 'adare vm list'.",
                file=sys.stderr
            )
            sys.exit(1)

        # Derive platform from osinfo unless overridden on the command line
        if vm.osinfo is None and not arguments.platform:
            print(
                f"Error: cannot determine platform for VM '{vm.name}' - it has no OS info; "
                "pass --platform",
                file=sys.stderr
            )
            sys.exit(1)

        platform = arguments.platform or vm.osinfo.platform
        architecture = (vm.osinfo.architecture or 'x86_64') if vm.osinfo is not None else 'x86_64'

        result = await api.vm.test_registered_vm(VmRegisteredTestRequest(
            vm_name=vm.name,
            disk_path=vm.file,
            guest_platform=platform,
            hypervisor=vm.hypervisor,
            architecture=architecture,
            verbose=arguments.verbose,
            vm_cleanup_mode=vm_cleanup_mode
        ))

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


async def exec_vm_instance_remove(arguments):
    """Remove VM instances based on criteria using AdareAPI."""
    from adare.frontend.terminal.vm_instances import print_vm_instance_cleanup_results

    api = AdareAPI()

    if arguments.instance_id:
        # Remove specific instance by ULID
        if not _is_valid_ulid(arguments.instance_id):
            print_error_message(
                title="Invalid instance ID format",
                next_steps=[f"Instance ID '{arguments.instance_id}' is not a valid ULID format"]
            )
            return

        result = await api.vm.remove_instance(arguments.instance_id)
        if result.success:
            print_vm_instance_cleanup_results([arguments.instance_id], "specific instance")
        else:
            handle_api_error(result)

    elif arguments.all and arguments.force:
        # Remove ALL instances (running or not) — replaces 'vm clear all --force'
        result = api.vm.clear_all(force=True)
        if result.success:
            from adare.frontend.terminal.vm_cleanup import print_vm_clear_all_results
            results = {
                'deleted_count': result.data.deleted_count,
                'deleted_vms': result.data.deleted_vms,
                'failed_count': result.data.failed_count,
                'failed_vms': result.data.failed_vms,
            }
            print_vm_clear_all_results(results)
        else:
            handle_api_error(result)

    elif arguments.all and not arguments.force:
        print_error_message(
            title="--all requires --force",
            next_steps=["Use --all --force to remove ALL instances (including running ones)",
                        "Use --stopped to remove only stopped instances"]
        )

    elif getattr(arguments, 'environment_ulid', None):
        # Remove all VMs for environment — replaces 'vm clear environment'
        if not arguments.force:
            from adare.frontend.terminal.vm_cleanup import print_vm_clear_environment_confirmation
            print_vm_clear_environment_confirmation(arguments.environment_ulid)
            return

        result = api.vm.clear_by_environment(arguments.environment_ulid, force=True)
        if result.success:
            from adare.frontend.terminal.vm_cleanup import print_vm_clear_environment_results
            results = {
                'deleted_count': result.data.deleted_count,
                'deleted_vms': result.data.deleted_vms,
                'failed_count': result.data.failed_count,
                'failed_vms': result.data.failed_vms,
            }
            print_vm_clear_environment_results(results, arguments.environment_ulid)
        else:
            handle_api_error(result)

    elif getattr(arguments, 'stopped', False):
        # Remove all stopped instances — replaces old '--all' behavior
        if not _confirm_removal("all stopped instances"):
            log.info("Operation cancelled by user")
            return

        result = await api.vm.remove_all_stopped_instances()
        if result.success:
            print_vm_instance_cleanup_results(result.data.removed_instances, "all stopped instances")
        else:
            handle_api_error(result)

    elif arguments.experiment_id:
        from adare.backend.vm.commands import cleanup_vm_instances_for_experiment
        await cleanup_vm_instances_for_experiment(arguments.experiment_id)
        print_vm_instance_cleanup_results([arguments.experiment_id], "experiment instances")

    else:
        print_error_message(
            title="No removal criteria specified",
            next_steps=["Use --id, --stopped, --experiment, --all --force, or --env --force"]
        )


def _is_valid_ulid(ulid_string):
    """Validate ULID format."""
    import re
    # ULID format: 26 characters, base32 encoded (0-9, A-Z excluding I, L, O, U)
    ulid_pattern = r'^[0-9A-HJKMNP-TV-Z]{26}$'
    return bool(re.match(ulid_pattern, ulid_string))


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


def exec_vm_prune(arguments):
    """Reclaim orphaned QEMU base disks / NVRAM (and optionally dead sockets).

    Mirrors the validated manual sweep: an orphan is a managed '-base.qcow2'
    (plus its '-nvram.fd' sibling) whose instance/VM is no longer registered
    in the database. Deletes nothing unless --force is given.
    """
    import click

    from adare.database.api.vm import VmApi
    from adare.hypervisor.qemu.mixins.configuration import (
        find_stale_sockets,
        get_qemu_disk_dir,
    )

    dry_run = getattr(arguments, 'dry_run', True)
    include_sockets = getattr(arguments, 'sockets', False)

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
        stem = name[:-len('-base.qcow2')]
        if stem in referenced:
            continue  # still referenced — keep
        _add(base_file)
        _add(base_file.with_name(f"{stem}-nvram.fd"))

    # Also catch orphaned nvram whose base was already reclaimed.
    for nvram_file in sorted(disk_dir.glob('*-nvram.fd')):
        name = nvram_file.name
        if '-overlay-' in name or '-dev-' in name:
            continue
        stem = name[:-len('-nvram.fd')]
        if stem in referenced:
            continue
        _add(nvram_file)

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
        click.echo("\nOrphaned base disks / NVRAM:")
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
