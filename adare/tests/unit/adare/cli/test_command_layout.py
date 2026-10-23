"""Command tree layout: moved commands, their hidden old names, and help rendering."""

import re

import click
import pytest
from click.testing import CliRunner

pytestmark = pytest.mark.unit


def _walk(cmd, path, parent=None):
    ctx = click.Context(cmd, info_name=path[-1], parent=parent, terminal_width=100)
    yield path, cmd, ctx
    if isinstance(cmd, click.Group):
        for name, sub in cmd.commands.items():
            if not sub.hidden:
                yield from _walk(sub, [*path, name], ctx)


def test_removed_groups_are_gone():
    from adare.run import cli

    assert 'server' not in cli.commands
    assert 'help' not in cli.commands


@pytest.mark.parametrize(
    ('old', 'new'),
    [
        (['os-profile'], ['vm', 'profile']),
        (['vm', 'gui-doctor'], ['vlm', 'doctor']),
        (['dev', 'grounding-pull'], ['vlm', 'pull-grounding']),
        (['run'], ['runs']),
        (['agent'], ['skills']),
        (['cv'], ['debug', 'cv']),
        (['ws'], ['debug', 'ws']),
        (['web', 'start'], ['ui', 'start']),
        (['web', 'services'], ['ui', 'status']),
        (['web', 'build'], ['ui', 'build']),
        (['web', 'install-spice'], ['ui', 'install-spice']),
    ],
)
def test_moved_command_is_visible_at_new_path_and_hidden_at_old(old, new):
    from adare.run import cli

    def resolve(path):
        cmd = cli
        for name in path:
            cmd = cmd.get_command(click.Context(cmd), name)
        return cmd

    new_cmd, old_cmd = resolve(new), resolve(old)
    assert not new_cmd.hidden
    assert old_cmd.hidden
    assert [p.name for p in old_cmd.params] == [p.name for p in new_cmd.params]
    assert f'adare {" ".join(new)}' in old_cmd.help


def test_old_os_profile_name_runs_and_points_to_new_name_on_stderr():
    from adare.run import cli

    old = CliRunner().invoke(cli, ['os-profile', 'list', '--json'], prog_name='adare')
    new = CliRunner().invoke(cli, ['vm', 'profile', 'list', '--json'])

    assert old.exit_code == 0, old.output
    assert old.stdout == new.stdout
    assert 'adare os-profile` has moved to `adare vm profile' in old.stderr
    assert new.stderr == ''


def test_old_agent_setup_path_still_resolves_through_the_alias():
    from adare.run import cli

    result = CliRunner().invoke(cli, ['agent', 'setup', '--help'])

    assert result.exit_code == 0, result.output
    assert 'Install ADARE' in result.stdout


def test_web_group_holds_only_platform_commands():
    from adare.run import cli

    visible = {name for name, cmd in cli.commands['web'].commands.items() if not cmd.hidden}
    assert visible == {'login', 'logout', 'status', 'download', 'publish', 'check', 'submit', 'sync'}


def test_vlm_remove_is_canonical_with_rm_alias():
    from adare.run import cli

    vlm = cli.commands['vlm']
    assert 'remove' in vlm.commands
    assert vlm.get_command(click.Context(vlm), 'rm') is vlm.commands['remove']
    assert vlm.get_command(click.Context(vlm), 'l') is vlm.commands['list']


def test_help_text_keeps_bullet_lists_and_examples_on_their_own_lines():
    """Click re-wraps paragraphs unless they start with \\b; a list then collapses into one line."""
    from adare.run import cli

    flattened = re.compile(r'\S:\s+- \S|Examples?:\s+adare ')
    offenders = [
        ' '.join(path)
        for path, cmd, ctx in _walk(cli, ['adare'])
        if any(flattened.search(line) for line in cmd.get_help(ctx).splitlines())
    ]
    assert offenders == []
