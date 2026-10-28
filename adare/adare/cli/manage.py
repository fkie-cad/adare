# internal imports
# configure logging
import logging
import sys
from contextlib import contextmanager

from adare.api import AdareAPI
from adare.cli.utils import handle_api_error
from adare.console import print_success_message

log = logging.getLogger(__name__)


def exec_manage_reset_db(arguments):
    """Reset the database using AdareAPI."""
    api = AdareAPI()
    result = api.manage.reset_db()

    if result.success:
        if result.data.was_reset:
            print_success_message(title='Global database reset successfully!', location=str(result.data.location))
        else:
            print("No global database found to reset")
    else:
        handle_api_error(result)


def exec_manage_init_db(arguments):
    """Initialize the database system using AdareAPI."""
    print("Initializing database system...")

    api = AdareAPI()
    result = api.manage.init_db()

    if result.success:
        if result.data.global_db_initialized:
            print(f"✅ Global database initialized: {result.data.global_db_location}")
            print("✅ Database system initialization completed successfully")
        else:
            print("❌ Failed to initialize global database")
            for error in result.data.errors:
                print(f"  Error: {error}")
    else:
        handle_api_error(result)


def exec_manage_db_status(arguments):
    """Check database system status using AdareAPI."""
    from adare.run import get_formatter_from_context

    formatter, output_file, dual_output = get_formatter_from_context()

    api = AdareAPI()
    result = api.manage.get_db_status()

    if result.success:
        status = result.data

        if dual_output or formatter.format_type.value != 'rich':
            # Structured output
            status_dict = {
                'global_db_exists': status.global_db_exists,
                'global_db_accessible': status.global_db_accessible,
                'global_db_location': str(status.global_db_location) if status.global_db_location else None,
                'valid': status.valid,
                'pending_migrations': status.pending_migrations,
                'errors': status.errors,
            }
            formatter.print_or_save(status_dict, output_file, dual_output)
        else:
            # Rich console output
            print("Checking database system status...")
            print(f"Global database exists: {'✅' if status.global_db_exists else '❌'}")
            print(f"Global database accessible: {'✅' if status.global_db_accessible else '❌'}")
            print(f"System valid: {'✅' if status.valid else '❌'}")

            if status.pending_migrations:
                print(f"Pending schema migrations: {len(status.pending_migrations)}")
                for name in status.pending_migrations:
                    print(f"  ⏳ {name}")
                print("  → applied automatically on next use, or now via 'adare db migrate'")
            else:
                print("Pending schema migrations: none ✅")

            if status.errors:
                print("\nErrors found:")
                for error in status.errors:
                    print(f"  ❌ {error}")

            if status.valid:
                print("\n✅ Database system is healthy")
            else:
                print("\n❌ Database system has issues")
    else:
        handle_api_error(result)


def exec_manage_repair_db(arguments):
    """Repair the database system using AdareAPI."""
    print("Starting database system repair...")

    api = AdareAPI()
    result = api.manage.repair_db()

    if result.success:
        if result.data.actions_taken:
            print("Actions taken:")
            for action in result.data.actions_taken:
                print(f"  ✅ {action}")

        if result.data.errors:
            print("Errors encountered:")
            for error in result.data.errors:
                print(f"  ❌ {error}")

        if result.data.repaired:
            print("✅ Database system repair completed successfully")
        else:
            print("❌ Database system repair failed")
    else:
        handle_api_error(result)


def exec_manage_migrate_db(arguments):
    """Apply pending database schema migrations using AdareAPI."""
    print("Applying pending database schema migrations...")

    api = AdareAPI()
    result = api.manage.migrate_db(quiet=False)

    if result.success:
        if result.data.applied:
            print("Applied migrations:")
            for name in result.data.applied:
                print(f"  ✅ {name}")
        else:
            print("✅ Nothing pending — all databases are up to date")

        if result.data.errors:
            print("Errors encountered:")
            for error in result.data.errors:
                print(f"  ❌ {error}")

        if not result.data.migrated:
            print("❌ Database migration failed")
    else:
        handle_api_error(result)


def exec_manage_clean_install_db(arguments):
    """Perform clean database installation using AdareAPI."""
    print("⚠️  WARNING: This will delete all existing database data!")

    if not arguments.force:
        response = input("Are you sure you want to proceed? (yes/no): ").strip().lower()
        if response != 'yes':
            print("Operation cancelled")
            return

    print("Starting clean database installation...")

    api = AdareAPI()
    result = api.manage.clean_install_db(force=True)

    if result.success:
        if result.data.actions_taken:
            print("Actions taken:")
            for action in result.data.actions_taken:
                print(f"  ✅ {action}")

        if result.data.errors:
            print("Errors encountered:")
            for error in result.data.errors:
                print(f"  ❌ {error}")

        if result.data.installed:
            print("✅ Clean database installation completed successfully")
        else:
            print("❌ Clean database installation failed")
    else:
        handle_api_error(result)


def exec_manage_reset_vm(arguments):
    """Reset all VMs in the system using AdareAPI."""
    api = AdareAPI()

    # First list VMs to show what will be deleted
    vm_result = api.vm.list_all()
    if vm_result.success:
        vms = vm_result.data
        print(f"⚠️  This will remove the instances of ALL {len(vms)} VMs (the VMs stay registered)!")

        if vms:
            print("\nVMs whose instances are removed:")
            for vm in vms[:10]:  # Show max 10 VMs
                print(f"  - {vm.name} ({vm.id})")

            if len(vms) > 10:
                print(f"  ... and {len(vms) - 10} more")
        else:
            print("No VMs found")
            return

        # Ask for confirmation
        if not arguments.force:
            response = input("\nAre you sure you want to remove the instances of all VMs? (yes/no): ").strip().lower()
            if response not in ['yes', 'y']:
                print("Operation cancelled.")
                return

    # Delete VMs
    print("\nRemoving VM instances...")
    result = api.manage.reset_all_vms(force=True)

    if result.success:
        print(f"✅ Removed: {result.data.deleted_count} VM instance(s)")
        if result.data.failed_count > 0:
            print(f"❌ Failed to remove: {result.data.failed_count} VM instance(s)")
            for error in result.data.failed_vms[:3]:
                print(f"  - {error}")
    else:
        handle_api_error(result)


def exec_manage_vm_runtime_refresh(arguments):
    """Refresh VM runtime files in current project using AdareAPI."""
    api = AdareAPI()
    result = api.manage.refresh_vm_runtime()

    if result.success:
        print_success_message(
            title='VM runtime refreshed successfully!',
            location=str(result.data.project_path) if result.data.project_path else None,
        )
        print("VM runtime files are now up-to-date")
    else:
        handle_api_error(result)


def exec_manage_vm_runtime_build(arguments):
    """Build VM runtime wheels in current project using AdareAPI."""
    api = AdareAPI()
    print("Building VM runtime wheels...")
    result = api.manage.build_vm_runtime_wheels()

    if result.success:
        print_success_message(
            title='VM runtime wheels built successfully!',
            location=str(result.data.wheels_dir) if result.data.wheels_dir else None,
        )
        if result.data.adarelib_wheel:
            print(f"  - {result.data.adarelib_wheel}")
        if result.data.adarevm_wheel:
            print(f"  - {result.data.adarevm_wheel}")
    else:
        handle_api_error(result)


# ---------------------------------------------------------------------------
# adare db compact / adare db check
# ---------------------------------------------------------------------------

# Labels of the orphan counts `adare db check` reports (keys: maintenance.ORPHAN_QUERIES).
_ORPHAN_LABELS = {
    'action_execution_without_run': 'action executions whose run no longer exists',
    'experiment_run_files_unreferenced': 'run-files rows no run references',
    'log_file_unreferenced': 'log-file rows only unreferenced run-files rows point at',
    'action_execution_dangling_playbook_item': 'action executions whose playbook item is gone',
}


def _size(num_bytes: float) -> str:
    value = float(num_bytes)
    for unit in ('B', 'KiB', 'MiB', 'GiB'):
        if abs(value) < 1024:
            return f'{value:.0f} {unit}' if unit in ('B', 'KiB') else f'{value:.1f} {unit}'
        value /= 1024
    return f'{value:.1f} TiB'


@contextmanager
def _compact_progress(enabled: bool):
    """A transient progress bar on stderr, as a ``(label, rowid, max rowid)`` callback; None when disabled."""
    if not enabled:
        yield None
        return
    from rich.console import Console
    from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn, TimeElapsedColumn

    tasks = {}  # label -> rich TaskID
    with Progress(
        TextColumn('{task.description}'),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=Console(stderr=True),
        transient=True,
    ) as bar:

        def update(label: str, reached: int, total: int) -> None:
            if label not in tasks:
                tasks[label] = bar.add_task(f'scanning {label}', total=max(total, 1))
            bar.update(tasks[label], completed=reached)

        yield update


def _details_table(entry):
    from rich.table import Table

    table = Table(title=f'{entry.label}  ({entry.path})', title_justify='left', show_header=False, box=None)
    table.add_column('field', style='bold')
    table.add_column('value')
    return table


def _compact_renderable(result):
    from rich.console import Group

    parts = []
    verb = 'would strip' if result.dry_run else 'stripped'
    for entry in result.databases:
        table = _details_table(entry)
        table.add_row('status', entry.status + (f' - {entry.message}' if entry.message else ''))
        if entry.status in ('compacted', 'dry-run'):
            table.add_row('rows examined', str(entry.rows_examined))
            table.add_row(f'rows {verb} (identical screenshot on disk)', str(entry.rows_stripped))
            table.add_row('rows kept (screenshot file missing)', str(entry.rows_kept_missing_file))
            table.add_row('rows kept (screenshot file differs)', str(entry.rows_kept_mismatch))
            table.add_row('rows with oversized non-image text (kept)', str(entry.rows_non_image_kept))
            table.add_row('reclaimable by the row rewrite', _size(entry.reclaimable_bytes))
            table.add_row('free pages (reclaimed by VACUUM)', _size(entry.free_pages_bytes))
            if not result.dry_run:
                table.add_row('vacuum', 'done' if entry.vacuumed else 'not done')
                if entry.vacuum_message:
                    table.add_row('', entry.vacuum_message)
        table.add_row('size before', f'{_size(entry.size_before)} (+ {_size(entry.wal_size_before)} WAL)')
        if not result.dry_run:
            table.add_row('size after', f'{_size(entry.size_after)} (+ {_size(entry.wal_size_after)} WAL)')
        table.add_row('duration', f'{entry.duration_seconds:.1f} s')
        parts.append(table)
    if result.dry_run:
        parts.append('Dry run: nothing was written. Run without --dry-run to compact.')
    return Group(*parts)


def exec_manage_compact_db(arguments):
    """Strip screenshot copies from old action results and VACUUM (``adare db compact``).

    Exits 1 when a database could not be compacted (in use, unreadable).
    """
    from adare.cli.output import emit, is_structured_output

    api = AdareAPI()
    with _compact_progress(not is_structured_output() and sys.stderr.isatty()) as progress:
        result = api.manage.compact_db(
            project=arguments.project,
            all_databases=arguments.all,
            dry_run=arguments.dry_run,
            progress=progress,
        )
    if not result.success:
        handle_api_error(result)
        return
    emit(result.data.to_dict(), rich=lambda: _compact_renderable(result.data))
    if not result.data.ok:
        sys.exit(1)


def _check_renderable(result):
    from rich.console import Group

    parts = []
    for entry in result.databases:
        table = _details_table(entry)
        if entry.status == 'missing':
            table.add_row('status', f'missing - {entry.message}')
            parts.append(table)
            continue
        if entry.message:
            table.add_row('note', entry.message)
        table.add_row('quick_check', 'ok' if entry.integrity_ok else 'FAILED')
        for problem in entry.problems[:20]:
            table.add_row('', problem)
        if len(entry.problems) > 20:
            table.add_row('', f'... {len(entry.problems) - 20} more (see --json)')
        for violation in entry.foreign_key_violations:
            table.add_row('foreign key', f'{violation.table} -> {violation.parent}: {violation.count} row(s)')
        if not entry.foreign_key_violations:
            table.add_row('foreign keys', 'no violations')
        for name, count in entry.orphans.items():
            table.add_row(_ORPHAN_LABELS.get(name, name.replace('_', ' ')), str(count))
        parts.append(table)
    if not result.ok:
        parts.append('Database corruption found: restore the database from a backup.')
    return Group(*parts)


def exec_manage_check_db(arguments):
    """Read-only database health check (``adare db check``); exits 1 when a database is corrupt."""
    from adare.cli.output import emit

    api = AdareAPI()
    result = api.manage.check_db(project=arguments.project, all_databases=arguments.all)
    if not result.success:
        handle_api_error(result)
        return
    emit(result.data.to_dict(), rich=lambda: _check_renderable(result.data))
    if not result.data.ok:
        sys.exit(1)
