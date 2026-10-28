import logging
import sys
import time
from types import SimpleNamespace

import click

from adare.cli.deprecated import deprecated_alias
from adare.cli.errors import report_exception
from adare.cli.groups.db_commands import register as register_db_commands
from adare.cli.groups.system_commands import register as register_system_commands
from adare.cli.output import FORMAT_CHOICES, FORMAT_ENV_VAR, output_options
from adare.cli.output import get_formatter_from_context as _get_formatter_from_context
from adare.cli.tui import tui
from adare.config.configdirectory import ensure_directories
from adare.exceptions import LoggedException
from adare.setup_logging import setup_logging

# Upper bound for one-line command summaries in group listings (see format_commands).
_SHORT_HELP_LIMIT = 200


class AliasedGroup(click.Group):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.aliases = {}

    def add_alias(self, alias, command_name):
        self.aliases[alias] = command_name

    def get_command(self, ctx, cmd_name):
        real = self.aliases.get(cmd_name, cmd_name)
        return super().get_command(ctx, real)

    def list_commands(self, ctx):
        # Only the canonical command names
        return sorted(super().list_commands(ctx))

    def add_command(self, cmd, name=None):
        # Commands decorated with @output_options advertise --json in their help
        # footer. Done here because the Command object does not exist yet when
        # the decorator runs.
        from adare.cli.output import OUTPUT_EPILOG, has_output_options

        if has_output_options(cmd) and not cmd.epilog:
            cmd.epilog = OUTPUT_EPILOG
        super().add_command(cmd, name)

    def format_commands(self, ctx, formatter):
        entries = []
        for name in self.list_commands(ctx):
            cmd = self.get_command(ctx, name)
            if cmd is None or cmd.hidden:
                continue
            # collect aliases pointing to this command
            alias_list = [a for a, target in self.aliases.items() if target == name]
            suffix = f" (aliases: {', '.join(alias_list)})" if alias_list else ""
            entries.append((name, cmd, suffix))
        if not entries:
            return
        # get_short_help_str() defaults to 45 characters, which cut most one-line
        # summaries mid-sentence. Show the whole first sentence instead and let
        # write_dl wrap it onto continuation lines on narrow terminals.
        rows = [(name, cmd.get_short_help_str(limit=_SHORT_HELP_LIMIT) + suffix) for name, cmd, suffix in entries]
        with formatter.section("Commands"):
            formatter.write_dl(rows)


def get_formatter_from_context():
    """Get the output formatter for the running command.

    Kept here because most commands import it from ``adare.run``; the format
    resolution itself (subcommand flag > global flag > $ADARE_FORMAT > auto)
    lives in ``adare.cli.output``.
    """
    return _get_formatter_from_context()


def exec_with_error_printing(func, args):
    """Run a command implementation; report a LoggedException once and exit.

    Exit codes: 0 ok (or an informational message), 1 error, 2 usage error,
    3 not found -- see ``adare.cli.errors``. The message goes to stderr (a JSON
    ``{"error": {...}}`` document in json mode); the traceback only with
    --very-verbose.
    """
    import asyncio
    import inspect

    try:
        if inspect.iscoroutinefunction(func):
            asyncio.run(func(args))
        else:
            func(args)
    except LoggedException as e:
        sys.exit(report_exception(e))


# Global start time for runtime logging
START_TIME = time.time()


# Global CLI group with logging and version options
@tui()
@click.group(
    cls=AliasedGroup,
    context_settings={'max_content_width': 120},
    epilog='Output: list/info/status commands take --json or --format '
    '[rich|plain|json|yaml] after the subcommand (adare env list --json). '
    f'Precedence: subcommand flag > adare --format > ${FORMAT_ENV_VAR} > auto '
    '(rich on a terminal, plain tab-separated text when piped). Data goes to '
    'stdout, logs and errors to stderr. Exit codes: 0 ok, 1 error, 2 usage, '
    '3 not found.',
)
@click.option('--logfile', type=click.Path(), help='Path to logfile')
@click.option('--verbose', is_flag=True, help='Verbose output (loglevel=INFO)')
@click.option('--very-verbose', is_flag=True, help='Very verbose output (loglevel=DEBUG, tracebacks on errors)')
@click.option('--log-level', help='Log level for logfile')
@click.option(
    '--output-format',
    '--format',
    'output_format',
    type=click.Choice(FORMAT_CHOICES, case_sensitive=False),
    default=None,
    help='Output format for commands that support structured data '
    f'(default: ${FORMAT_ENV_VAR}, else rich on a terminal and plain when piped)',
)
@click.option('--output-file', type=click.Path(), help='Save output to file instead of printing to console')
@click.version_option()  # Uses the package version if configured
@click.pass_context
def cli(ctx, logfile, verbose, very_verbose, log_level, output_format, output_file):
    """
    ADARE - the Automated Desktop Analysis framework for Reproducible Experiments.
    """
    ctx.ensure_object(SimpleNamespace)
    ctx.obj.logfile = logfile
    ctx.obj.verbose = verbose
    ctx.obj.very_verbose = very_verbose
    ctx.obj.log_level = log_level
    ctx.obj.output_format = output_format.lower() if output_format else None
    ctx.obj.output_file = output_file
    ctx.obj.command_output_format = None  # set by a subcommand's --json/--format
    ensure_directories()
    setup_logging(ctx.obj, sys.argv)


# Add aliases after CLI group is defined
cli.add_alias('exp', 'experiment')
cli.add_alias('environment', 'env')
cli.add_alias('tf', 'test')
cli.add_alias('testfunction', 'test')


# ------------------------------
# Database commands (extracted to cli/groups/db_commands.py)
# ------------------------------
db = register_db_commands(cli, AliasedGroup, exec_with_error_printing)


# ------------------------------
# Windows icon library commands
# ------------------------------
@cli.group(cls=AliasedGroup)
def icons():
    """Windows icon library: inspect the registry and dump icons from a target."""


@icons.command(name='list')
@output_options
@click.option('--os-key', default='windows', help='OS profile / build key (cache separation)')
def icons_list(os_key):
    """List every icon term in the registry with its resolver spec."""
    from adare.cli.icons import exec_icons_list

    exec_with_error_printing(exec_icons_list, SimpleNamespace(os_key=os_key))


@icons.command(name='dump-all')
@click.option('--host', default='127.0.0.1', help='adarevm host')
@click.option('--port', default=18765, type=int, help='adarevm WebSocket port')
@click.option('--os-key', default='windows', help='OS profile / build key (cache separation)')
@click.option('--force', is_flag=True, help='Re-extract even if a cached PNG exists')
@click.option('--token', envvar='ADARE_AGENT_TOKEN', help='Agent token (agent_token in the run config.json)')
def icons_dump_all(host, port, os_key, force, token):
    """Resolve every registry term on a connected target; write PNGs + contact sheet."""
    from adare.cli.icons import exec_icons_dump_all

    exec_with_error_printing(
        exec_icons_dump_all,
        SimpleNamespace(host=host, port=port, os_key=os_key, force=force, token=token),
    )


icons.add_alias('l', 'list')
icons.add_alias('dump', 'dump-all')


# ------------------------------
# Runtime commands (was: manage vm-runtime)
# ------------------------------
@cli.group(cls=AliasedGroup)
def runtime():
    """VM runtime management for current project."""


@runtime.command(name='refresh')
def runtime_refresh():
    """Refresh VM runtime files in current project, ensuring they are up-to-date."""
    from adare.cli.manage import exec_manage_vm_runtime_refresh

    args = SimpleNamespace()
    exec_with_error_printing(exec_manage_vm_runtime_refresh, args)


@runtime.command(name='build')
def runtime_build():
    """Build fresh VM runtime wheels (adarelib, adarevm) for current project."""
    from adare.cli.manage import exec_manage_vm_runtime_build

    args = SimpleNamespace()
    exec_with_error_printing(exec_manage_vm_runtime_build, args)


# ------------------------------
# Project commands
# ------------------------------
@cli.group(cls=AliasedGroup)
def project():
    """Project-related commands."""


@project.command()
@click.argument('name')
@click.option('--description', '-d', help='Description of the project')
def create(name, description):
    """Create a new project."""
    from adare.cli.project import exec_create_project

    args = SimpleNamespace(name=name, description=description)
    exec_with_error_printing(exec_create_project, args)


@project.command()
@click.argument('name')
def remove(name):
    """Remove a project."""
    from adare.cli.project import exec_remove_project

    args = SimpleNamespace(name=name)
    exec_with_error_printing(exec_remove_project, args)


@project.command(name='list')
@output_options
def list_projects():
    """List all projects."""
    from adare.cli.project import exec_list_projects

    args = SimpleNamespace()
    exec_with_error_printing(exec_list_projects, args)


# Add aliases for project commands
project.add_alias('l', 'list')
project.add_alias('rm', 'remove')


# ------------------------------
# Environment commands (extracted to cli/groups/environment_commands.py)
# ------------------------------
from adare.cli.groups.environment_commands import register as register_environment_commands

register_environment_commands(cli, AliasedGroup, exec_with_error_printing)


# ------------------------------
# Experiment commands (extracted to cli/groups/experiment_commands.py)
# ------------------------------
from adare.cli.groups.experiment_commands import register as register_experiment_commands

register_experiment_commands(cli, AliasedGroup, exec_with_error_printing)


# ------------------------------
# Development mode commands (extracted to cli/groups/dev_commands.py)
# ------------------------------
from adare.cli.groups.dev_commands import register as register_dev_commands

dev = register_dev_commands(cli, AliasedGroup, exec_with_error_printing)

# ------------------------------
# VLM provider config (cli/groups/vlm_commands.py)
# ------------------------------
from adare.cli.groups.vlm_commands import register as register_vlm_commands

vlm = register_vlm_commands(cli, AliasedGroup, exec_with_error_printing)


# ------------------------------
# Test commands (was: testfunction)
# ------------------------------
@cli.group(name='test', cls=AliasedGroup)
def test():
    """Test function management commands."""


@test.command(name='create')
@click.argument('name', type=click.Path(exists=False))
@click.option('--project', '-p', help='Name of the project')
def test_create(name, project):
    """Create a new testfunction.

    \b
    NAME can be:
    - Simple name: my_test
    - Relative path: testfunctions/my_test
    """
    from adare.cli.testfunction import exec_create_testfunction

    args = SimpleNamespace(name=name, project=project)
    exec_with_error_printing(exec_create_testfunction, args)


@test.command(name='remove')
@click.argument('name')
@click.option('--project', '-p', help='Name of the project')
def test_remove(name, project):
    """Remove a testfunction file by name.

    NAME is the testfunction file name (e.g., xml, json, csv).
    This will remove the entire testfunction file and all functions within it.
    """
    from adare.cli.testfunction import exec_remove_testfunction

    args = SimpleNamespace(name=name, project=project)
    exec_with_error_printing(exec_remove_testfunction, args)


@test.command()
@click.argument('name', type=click.Path(exists=False))
@click.option(
    '--force',
    '-f',
    is_flag=True,
    help='Force overwrite if testfunction is used in experiments (will delete associated runs)',
)
def load(name, force):
    """Load a testfunction.

    \b
    NAME can be:
    - Testfunction name from appdata: standard, json, csv
    - Absolute path: /path/to/testfunction
    - Relative path: ./testfunctions/my_test

    By default, loading will skip testfunctions that are currently used in experiment runs.
    Use --force to overwrite and delete associated experiment runs.
    """
    from adare.cli.testfunction import exec_load_testfunction

    args = SimpleNamespace(name=name, force=force)
    exec_with_error_printing(exec_load_testfunction, args)


@test.command()
def sync():
    """Sync all testfunctions from appdata: create new, update changed, skip unchanged."""
    from adare.cli.testfunction import exec_sync_testfunctions

    args = SimpleNamespace()
    exec_with_error_printing(exec_sync_testfunctions, args)


@test.command()
@click.argument('path', type=click.Path(exists=False))
def validate(path):
    """Validate a testfunction collection offline (no VM, no DB).

    PATH is a collection directory (or .py file). Reports every authoring-contract
    violation — filename≠dirname, missing 'ctx', unannotated params, duplicate
    testnames, import/syntax errors, missing dependencies — with fix hints.
    """
    from adare.cli.testfunction import exec_validate_testfunction

    args = SimpleNamespace(path=path)
    exec_with_error_printing(exec_validate_testfunction, args)


@test.command(name='dry-run')
@click.argument('target')
@click.option('--param', '-P', multiple=True, help='Parameter as key=value (repeatable)')
@click.option('--file', '-f', 'file', help='Local sample file used as the dst parameter')
@click.option('--path', help='Collection dir/.py to load (else resolved from known locations)')
def dry_run(target, param, file, path):
    """Execute one testfunction against a local sample file (no VM).

    TARGET is <collection>.<function> (e.g. mycollection.file_contains_word).
    Scope: FILE_BASED / FILE_CONTENT tests only.
    """
    from adare.cli.testfunction import exec_dry_run_testfunction

    args = SimpleNamespace(target=target, param=param, file=file, path=path)
    exec_with_error_printing(exec_dry_run_testfunction, args)


_catalog_filters = [
    click.option('--collection', '--set', 'collection', help='Only this collection (e.g. standard, windows)'),
    click.option('--category', help='Only this host-mode category (e.g. FILE_BASED, HOST_NATIVE)'),
    click.option(
        '--os',
        'os_name',
        type=click.Choice(['windows', 'linux', 'any'], case_sensitive=False),
        help='Only testfunctions usable on this guest OS',
    ),
]


def catalog_filters(func):
    for option in reversed(_catalog_filters):
        func = option(func)
    return func


@test.command(name='list')
@output_options
@catalog_filters
@click.option('--full', is_flag=True, help='Structured output with every field (default: compact)')
def list_testfunctions(collection, category, os_name, full):
    """List every testfunction with its parameters (no project needed).

    \b
    Examples:
      adare test list --collection standard
      adare --format json test list --os windows
    """
    from adare.cli.testfunction_catalog import exec_catalog_list

    args = SimpleNamespace(collection=collection, category=category, os=os_name, full=full)
    exec_with_error_printing(exec_catalog_list, args)


@test.command()
@output_options
@click.argument('query')
@catalog_filters
@click.option('--limit', '-n', default=8, show_default=True, help='Maximum number of results')
def search(query, collection, category, os_name, limit):
    """Find the testfunction for a goal, e.g. "deleted file is gone".

    Ranks by name, summary and parameter docs, with synonyms (deleted/gone/
    removed, registry/hive, ...). Results include a ready-to-paste example.

    \b
    Examples:
      adare test search "file was deleted"
      adare --format json test search "registry value" --os windows
    """
    from adare.cli.testfunction_catalog import exec_catalog_search

    args = SimpleNamespace(query=query, collection=collection, category=category, os=os_name, limit=limit)
    exec_with_error_printing(exec_catalog_search, args)


@test.command(hidden=True)
@click.option('--file-name', '-n', help='Collection name')
def show(file_name):
    """Deprecated alias of `adare test list --collection`."""
    from adare.cli.testfunction_catalog import exec_catalog_list

    args = SimpleNamespace(collection=file_name, category=None, os=None, full=False)
    exec_with_error_printing(exec_catalog_list, args)


@test.command()
@output_options
@click.argument('dotnotation')
@click.option('--example', is_flag=True, help='Print only a ready-to-paste `tests:` YAML block')
def info(dotnotation, example):
    """Signature, parameter docs and an example for one testfunction.

    DOTNOTATION is <collection>.<function> (e.g. standard.file_exists); a bare
    function name works when it is unique.
    """
    from adare.cli.testfunction_catalog import exec_catalog_info

    args = SimpleNamespace(dotnotation=dotnotation, example=example)
    exec_with_error_printing(exec_catalog_info, args)


@test.command()
@output_options
@click.option('--markdown', is_flag=True, help='Render a Markdown reference instead of structured output')
def catalog(markdown):
    """Export the bundled testfunction catalog (for docs and agent skills).

    Machine-independent: only collections shipped with ADARE, not local ones.

    \b
    Example:
      adare test catalog --markdown > skills/adare-testfunction/references/catalog.md
    """
    from adare.cli.testfunction_catalog import exec_catalog_export

    args = SimpleNamespace(markdown=markdown)
    exec_with_error_printing(exec_catalog_export, args)


@test.command()
@click.argument('target')
def versions(target):
    """List the version history of a testfunction library.

    TARGET is a library name (e.g. mycollection) or <library>.<function>
    (e.g. mycollection.file_contains_word) for per-method history.
    """
    from adare.cli.testfunction import exec_testfunction_versions

    args = SimpleNamespace(target=target)
    exec_with_error_printing(exec_testfunction_versions, args)


# Add aliases for test commands
test.add_alias('l', 'list')
test.add_alias('ls', 'list')
test.add_alias('find', 'search')
test.add_alias('rm', 'remove')
test.add_alias('v', 'versions')


# ------------------------------
# VM management commands (extracted to cli/groups/vm_commands.py)
# ------------------------------
from adare.cli.groups.vm_commands import register as register_vm_commands

vm = register_vm_commands(cli, AliasedGroup, exec_with_error_printing)


# ------------------------------
# Run management commands
# ------------------------------
@cli.group(name='runs', cls=AliasedGroup)
def runs():
    """Experiment runs: list, inspect and remove them (start one with `adare experiment run`)."""


@runs.command(name='list')
@output_options
@click.option('--filter', help='Filter by dotnotation: [project][.environment][.experiment]')
def list_runs(filter):
    """List all experiment runs. Use --filter with dotnotation for advanced filtering."""
    from adare.cli.show import exec_show_runs

    args = SimpleNamespace(filter=filter)
    exec_with_error_printing(exec_show_runs, args)


@runs.command(name='info')
@output_options
@click.argument('ulid', required=False)
def run_info(ulid):
    """Show detailed information about a run. Shows latest run if no ULID provided."""
    from adare.cli.show import exec_show_run

    args = SimpleNamespace(ulid=ulid)
    exec_with_error_printing(exec_show_run, args)


@runs.command(name='remove')
@click.argument('ulid', required=True)
def run_remove(ulid):
    """Remove a single experiment run by its ULID."""
    from adare.cli.show import exec_remove_run

    args = SimpleNamespace(ulid=ulid)
    exec_with_error_printing(exec_remove_run, args)


# Add aliases for run commands
runs.add_alias('l', 'list')
runs.add_alias('rm', 'remove')

# ------------------------------
# Web interface commands (extracted to cli/groups/web_commands.py)
# ------------------------------
from adare.cli.groups.web_commands import register as register_web_commands

web = register_web_commands(cli, AliasedGroup, exec_with_error_printing)


# ------------------------------
# Local web UI (start, status, build, install-spice)
# ------------------------------
@cli.group(name='ui', cls=AliasedGroup)
def ui():
    """Local web UI: start it, check its services, build the frontend.

    The shared ADARE Web platform (login, publish, download) is `adare web`.
    """


from adare.cli.web_cmd import (
    web_build,
    web_install_spice,
    web_services,
    web_start,
)

ui.add_command(web_start, 'start')
ui.add_command(web_services, 'status')
ui.add_command(web_build, 'build')
ui.add_command(web_install_spice, 'install-spice')


# ------------------------------
# Control-plane MCP server (adare mcp serve)
# ------------------------------
@cli.group(name='mcp', cls=AliasedGroup)
def mcp():
    """ADARE control-plane MCP server (drive all of ADARE from an MCP client)."""


@mcp.command(name='serve')
@click.option(
    '--transport',
    type=click.Choice(['stdio', 'http']),
    default='stdio',
    show_default=True,
    help='MCP transport: stdio (client launches this process) or http',
)
@click.option('--host', default='127.0.0.1', show_default=True, help='[http] Bind host')
@click.option('--port', type=int, default=None, help='[http] Bind port (default: ADARE_MCP_PORT or 13112)')
def mcp_serve(transport, host, port):
    """Serve the whole ADARE lifecycle as MCP tools.

    Exposes projects, environments, experiments, runs, VMs, dev sessions, and
    LLM playbook authoring over MCP. Distinct from the session-scoped
    `adare dev mcp`. Point Claude Code / Claude Desktop at it and drive ADARE
    conversationally.

    \b
    Examples:
        adare mcp serve                       # stdio (for a client to launch)
        adare mcp serve --transport http --port 13112

    \b
    Client setup (Claude Code / OpenCode) and the playbook fix loop:
        docsrc/mcp-clients.md   ·   skill: .claude/skills/adare-playbook/SKILL.md
        Claude Code: claude mcp add adare -- adare mcp serve
    """
    from adare.cli.mcp_control import exec_mcp_serve

    args = SimpleNamespace(transport=transport, host=host, port=port)
    exec_with_error_printing(exec_mcp_serve, args)


# ------------------------------
# Debugging tools (cv, ws)
# ------------------------------
@cli.group(name='debug', cls=AliasedGroup)
def debug():
    """Low-level debugging: CV detection on screenshots, raw guest-agent actions."""


@debug.group(cls=AliasedGroup)
def cv():
    """CV server testing commands for icon/text recognition."""


@cv.command(name='test-icon')
@click.option('--icon', required=True, type=click.Path(exists=True), help='Path to icon image file')
@click.option('--screenshot', required=True, type=click.Path(exists=True), help='Path to screenshot image file')
@click.option('--output', type=click.Path(), help='Path to save marked image with found locations')
@click.option('--host', default='localhost', help='CV server host (default: localhost)')
@click.option('--port', type=int, default=13109, help='CV server port (default: 13109)')
@click.option('--threshold', type=float, default=0.6, help='Match threshold (0.0-1.0, default: 0.6)')
@click.option('--mcplog', type=click.Path(), help='Path to save CV server logs')
def cv_test_icon(icon, screenshot, output, host, port, threshold, mcplog):
    """Test CV server icon finding functionality.

    Automatically starts CV server, finds an icon in a screenshot,
    prints coordinates of all matches, and stops the server.
    Optionally saves a marked image showing found locations.
    """
    from adare.cli.mcp import exec_mcp_test_icon

    args = SimpleNamespace(
        icon_path=icon,
        screenshot_path=screenshot,
        output_path=output,
        host=host,
        port=port,
        threshold=threshold,
        mcplog_path=mcplog,
    )
    exec_with_error_printing(exec_mcp_test_icon, args)


@cv.command(name='test-text')
@click.argument('text')
@click.option('--screenshot', required=True, type=click.Path(exists=True), help='Path to screenshot image file')
@click.option('--format', default='json', help='Output format: json or csv (default: json)')
@click.option('--host', default='localhost', help='CV server host (default: localhost)')
@click.option('--port', type=int, default=13109, help='CV server port (default: 13109)')
def cv_test_text(text, screenshot, format, host, port):
    """Test CV server text finding functionality.

    TEXT is the text string to search for in the screenshot.
    Automatically starts CV server, finds text matches,
    prints coordinates, and stops the server.
    """
    from adare.cli.mcp import exec_mcp_test_text

    args = SimpleNamespace(text=text, screenshot_path=screenshot, format=format, host=host, port=port)
    exec_with_error_printing(exec_mcp_test_text, args)


@cv.command(name='get-all-text')
@click.option('--screenshot', required=True, type=click.Path(exists=True), help='Path to screenshot image file')
@click.option('--format', default='json', help='Output format: json or csv (default: json)')
@click.option('--host', default='localhost', help='CV server host (default: localhost)')
@click.option('--port', type=int, default=13109, help='CV server port (default: 13109)')
def cv_get_all_text(screenshot, format, host, port):
    """Get all detected text from screenshot using OCR.

    Automatically starts CV server, runs OCR on the screenshot,
    returns all detected text with coordinates and confidence scores,
    then stops the server.
    """
    from adare.cli.mcp import exec_mcp_get_all_text

    args = SimpleNamespace(screenshot_path=screenshot, format=format, host=host, port=port)
    exec_with_error_printing(exec_mcp_get_all_text, args)


# ------------------------------
# WebSocket commands (was: dev ws)
# ------------------------------
@debug.group(cls=AliasedGroup)
def ws():
    """WebSocket adarevm interaction commands."""


@ws.command()
@click.argument('action_file', type=click.Path(exists=True))
@click.option('--host', default='127.0.0.1', help='AdareVM host (default: 127.0.0.1)')
@click.option('--port', type=int, default=18765, help='AdareVM WebSocket port (default: 18765)')
@click.option('--vm-instance', help='VM instance name to look up WebSocket port (overrides --port)')
@click.option('--connect-timeout', type=float, default=10.0, help='Connection timeout in seconds (default: 10.0)')
@click.option('--default-timeout', type=float, default=30.0, help='Default action timeout in seconds (default: 30.0)')
@click.option('--continue-on-error', is_flag=True, help='Continue executing actions even if one fails')
@click.option('--token', envvar='ADARE_AGENT_TOKEN', help='Agent token (agent_token in the run config.json)')
@click.option(
    '--output-format',
    type=click.Choice(['json', 'yaml', 'summary', 'simple']),
    default='simple',
    help='Output format (default: simple)',
)
def action(
    action_file, host, port, vm_instance, connect_timeout, default_timeout, continue_on_error, token, output_format
):
    """Execute actions from YAML file on adarevm via WebSocket.

    ACTION_FILE: Path to YAML file containing actions to execute

    \b
    Examples:
        adare debug ws action test.yml --host 192.168.1.100 --port 18765
        adare debug ws action test.yml --vm-instance my-vm-instance
    """
    from adare.cli.ws import exec_ws_action

    args = SimpleNamespace(
        action_file=action_file,
        host=host,
        port=port,
        vm_instance=vm_instance,
        connect_timeout=connect_timeout,
        default_timeout=default_timeout,
        continue_on_error=continue_on_error,
        token=token,
        output_format=output_format,
    )
    exec_with_error_printing(exec_ws_action, args)


@ws.command(name='example')
@click.argument('output_file', type=click.Path())
def ws_create_example(output_file):
    """Create an example action YAML file."""
    from pathlib import Path

    from adare.cli.ws import create_example_action_file

    create_example_action_file(Path(output_file))


# ------------------------------
# Skills for AI coding agents
# ------------------------------
@cli.group(name='skills', cls=AliasedGroup)
def skills():
    """Install ADARE's workflow skills for AI coding agents (Claude Code, OpenCode)."""


_agent_client_option = click.option(
    '--client',
    type=click.Choice(['claude', 'opencode', 'all']),
    default='all',
    show_default=True,
    help='Which coding agent(s)',
)


@skills.command(name='install')
@output_options
@_agent_client_option
@click.option(
    '--scope',
    type=click.Choice(['user', 'project', 'all']),
    default='user',
    show_default=True,
    help='user = every project (~/.claude/skills, ~/.config/opencode/skills); project = this directory',
)
@click.option('--copy', is_flag=True, help='Copy the skills instead of symlinking (e.g. on Windows)')
@click.option('--force', is_flag=True, help='Re-point skill symlinks that currently point elsewhere')
@click.option('--dry-run', is_flag=True, help='Show what would change without touching anything')
def skills_install(client, scope, copy, force, dry_run):
    """Install ADARE's workflow skills for your coding agent(s).

    Symlinks every skills/adare-* skill so edits to the source propagate. Real
    directories are never touched; links pointing elsewhere need --force.

    \b
    Examples:
      adare skills install --dry-run
      adare skills install --client claude --scope all
    """
    from adare.cli.agent import exec_agent_setup

    args = SimpleNamespace(client=client, scope=scope, copy=copy, force=force, dry_run=dry_run)
    exec_with_error_printing(exec_agent_setup, args)


@skills.command(name='status')
@output_options
@_agent_client_option
@click.option('--scope', type=click.Choice(['user', 'project', 'all']), default='all', show_default=True)
def skills_status(client, scope):
    """Show where ADARE's skills are installed and whether the links are current."""
    from adare.cli.agent import exec_agent_status

    args = SimpleNamespace(client=client, scope=scope)
    exec_with_error_printing(exec_agent_status, args)


skills.add_alias('setup', 'install')


# ------------------------------
# Chat — embedded agentic REPL
# ------------------------------
@cli.command(name='chat')
@click.option('--model', default=None, help='Chat model id (default: $ADARE_CHAT_MODEL, else the vlm model)')
@click.option('--base-url', default=None, help='OpenAI-compatible endpoint (default: the active `adare vlm` provider)')
@click.option(
    '--tool-protocol',
    type=click.Choice(['native', 'json', 'auto']),
    default='auto',
    help='Tool-call protocol: native function-calling, JSON-in-text, or auto (default)',
)
@click.option('--max-tokens', type=int, default=None, help='Max tokens per assistant turn')
def cli_chat(model, base_url, tool_protocol, max_tokens):
    """Control ADARE conversationally in an embedded agentic REPL.

    A terminal console with its own agent loop and a provider-agnostic brain that
    reuses whatever OpenAI-compatible endpoint you configured for `adare vlm`
    (vLLM / Ollama-cloud / custom — select one with `adare vlm use`). It drives
    ADARE by calling the same tool registry the MCP control server exposes:
    environments, experiments, runs, VMs, dev sessions, and LLM playbook
    authoring.

    The default model is often a vision model; for the best tool-caller set a
    tool-capable text model via `--model` or $ADARE_CHAT_MODEL. `--tool-protocol
    auto` tries native function-calling and falls back to a JSON-in-text contract
    when the endpoint rejects it.

    \b
    Example:
        adare vlm use ollama-cloud
        adare chat
    """
    from adare.cli.chat import exec_chat

    args = SimpleNamespace(model=model, base_url=base_url, tool_protocol=tool_protocol, max_tokens=max_tokens)
    exec_with_error_printing(exec_chat, args)


# ------------------------------
# System resources (extracted to cli/groups/system_commands.py)
# ------------------------------
register_system_commands(cli, AliasedGroup, exec_with_error_printing)


# ------------------------------
# Status command
# ------------------------------
@cli.command(name='status')
@output_options
def cli_status():
    """Show quick overview: current project, active sessions, VM count, db status."""
    from adare.cli.status import exec_status

    args = SimpleNamespace()
    exec_with_error_printing(exec_status, args)


# ------------------------------
# Moved commands keep working under their old names: hidden, with a pointer on stderr.
# ------------------------------
cli.add_command(deprecated_alias(vm.commands['profile'], 'os-profile', 'adare vm profile'))
vm.add_command(deprecated_alias(vlm.commands['doctor'], 'gui-doctor', 'adare vlm doctor'))
dev.add_command(deprecated_alias(vlm.commands['pull-grounding'], 'grounding-pull', 'adare vlm pull-grounding'))
cli.add_command(deprecated_alias(runs, 'run', 'adare runs'))
cli.add_command(deprecated_alias(skills, 'agent', 'adare skills'))
cli.add_command(deprecated_alias(cv, 'cv', 'adare debug cv'))
cli.add_command(deprecated_alias(ws, 'ws', 'adare debug ws'))
for _old, _new in (('start', 'start'), ('services', 'status'), ('build', 'build'), ('install-spice', 'install-spice')):
    web.add_command(deprecated_alias(ui.commands[_new], _old, f'adare ui {_new}'))


def main():
    cli()
    runtime = (time.time() - START_TIME) / 60
    logging.getLogger(__name__).debug(f"--- Runtime {runtime} minutes ---")
    logging.shutdown()


if __name__ == '__main__':
    main()
