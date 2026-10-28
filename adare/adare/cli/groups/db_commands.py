"""`adare db` - database management commands (was: manage *-db)."""

from types import SimpleNamespace

import click

from adare.cli.output import output_options


def register(cli, AliasedGroup, exec_with_error_printing):
    """Register the ``db`` group with the CLI and return it."""

    @cli.group(cls=AliasedGroup)
    def db():
        """Database management commands."""

    @db.command(name='init')
    def db_init():
        """Initialize the database system."""
        from adare.cli.manage import exec_manage_init_db

        args = SimpleNamespace()
        exec_with_error_printing(exec_manage_init_db, args)

    @db.command(name='status')
    @output_options
    def db_status():
        """Check database system status."""
        from adare.cli.manage import exec_manage_db_status

        args = SimpleNamespace()
        exec_with_error_printing(exec_manage_db_status, args)

    @db.command(name='reset')
    def db_reset():
        """Reset the database (use with caution)."""
        from adare.cli.manage import exec_manage_reset_db

        args = SimpleNamespace()
        exec_with_error_printing(exec_manage_reset_db, args)

    @db.command(name='repair')
    def db_repair():
        """Repair the database system."""
        from adare.cli.manage import exec_manage_repair_db

        args = SimpleNamespace()
        exec_with_error_printing(exec_manage_repair_db, args)

    @db.command(name='migrate')
    def db_migrate():
        """Apply pending database schema migrations (global + all projects)."""
        from adare.cli.manage import exec_manage_migrate_db

        args = SimpleNamespace()
        exec_with_error_printing(exec_manage_migrate_db, args)

    @db.command(name='clean-install')
    @click.option('--force', '-f', is_flag=True, help='Force clean installation without confirmation')
    def db_clean_install(force):
        """Perform clean database installation (DANGER: deletes all data)."""
        from adare.cli.manage import exec_manage_clean_install_db

        args = SimpleNamespace(force=force)
        exec_with_error_printing(exec_manage_clean_install_db, args)

    @db.command(name='compact')
    @output_options
    @click.option('--project', '-p', help='Project name or path (default: the project of the current directory)')
    @click.option('--all', 'all_databases', is_flag=True, help='Every registered project and the global database')
    @click.option('--dry-run', is_flag=True, help='Report what would be reclaimed; write nothing')
    def db_compact(project, all_databases, dry_run):
        """Shrink a database: drop screenshot copies from old action results, then VACUUM.

        Old action results keep a base64 copy of every screenshot, which the PNG in
        the run's reporting/screenshots folder already holds; new results are stored
        without it. A copy is only removed when that PNG is on disk and byte-for-byte
        identical -- rows whose screenshot file is missing or differs are left
        unchanged, and nothing but image copies is ever removed. VACUUM needs free
        space of about twice the remaining data (next to the database and in the
        temporary directory). Refuses to run while another process holds the write
        lock, a run of the project was active in the last 30 minutes, or a dev
        session is live.
        """
        from adare.cli.manage import exec_manage_compact_db

        args = SimpleNamespace(project=project, all=all_databases, dry_run=dry_run)
        exec_with_error_printing(exec_manage_compact_db, args)

    @db.command(name='check')
    @output_options
    @click.option('--project', '-p', help='Project name or path (default: the project of the current directory)')
    @click.option('--all', 'all_databases', is_flag=True, help='Every registered project and the global database')
    def db_check(project, all_databases):
        """Read-only health check: quick_check, foreign keys and orphaned rows.

        Exits 1 when a database is corrupt. Orphaned rows are only counted, never
        changed: action executions without a run row come from dev-session consoles
        or from runs older versions deleted, and are kept.
        """
        from adare.cli.manage import exec_manage_check_db

        args = SimpleNamespace(project=project, all=all_databases)
        exec_with_error_printing(exec_manage_check_db, args)

    return db
