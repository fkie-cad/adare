"""Classification of playbook commands for the host-side backend (class a/b/c/d)."""

import pytest

from adare.backend.hostside.commands import (
    CLASS_GUEST,
    CLASS_GUI,
    CLASS_INJECT,
    CLASS_PROVISION,
    CommandPlanner,
    guest_tzinfo,
    parse_touch_stamp,
)

pytestmark = pytest.mark.unit


@pytest.fixture
def planner():
    return CommandPlanner(uid=1000, gid=1000, now=1_700_000_000.0, users={'adare': (1000, 1000)})


def test_echo_redirect_becomes_a_write(planner):
    plan = planner.plan("echo 'This is test text' > /home/adare/Documents/adare.txt", shell=True)
    assert plan.category == CLASS_INJECT
    (op,) = plan.ops
    assert (op.kind, op.path, op.content, op.uid) == (
        'write',
        '/home/adare/Documents/adare.txt',
        b'This is test text\n',
        1000,
    )


def test_admin_command_is_owned_by_root(planner):
    (op,) = planner.plan('echo x > /etc/motd', admin=True).ops
    assert (op.uid, op.gid) == (0, 0)


def test_rm_f_and_mkdir(planner):
    assert [o.kind for o in planner.plan('rm -f /a/b').ops] == ['remove']
    assert [o.kind for o in planner.plan('mkdir -p /a/b').ops] == ['mkdir']


def test_recursive_rm_is_not_stageable(planner):
    plan = planner.plan('rm -rf /a')
    assert plan.category == CLASS_GUEST and not plan.ops


def test_touch_atime_uses_the_guest_time_zone():
    cet = guest_tzinfo('Europe/Berlin')
    planner = CommandPlanner(tz=cet, now=1.0)
    (op,) = planner.plan('touch -a -t 200001010000 /f').ops
    assert op.atime == 946681200.0  # 2000-01-01 00:00 CET == 1999-12-31 23:00 UTC
    assert op.mtime is None


def test_touch_stamp_forms():
    utc = guest_tzinfo('UTC')
    assert parse_touch_stamp('200001010000', utc) == 946684800.0
    assert parse_touch_stamp('0001010000', utc) == 946684800.0
    assert parse_touch_stamp('200001010000.30', utc) == 946684830.0


def test_chain_with_chown_noop_and_echo(planner):
    command = (
        'mkdir -p /home/adare/.config && echo yes > /home/adare/.config/done && chown -R adare:adare /home/adare/.config '
        '&& (pkill -f "[g]nome-initial-setup" || true) && echo "flag=$(cat /home/adare/.config/done)"'
    )
    plan = planner.plan(command, shell=True)
    assert plan.category == CLASS_INJECT
    assert [(o.kind, o.path) for o in plan.ops] == [
        ('mkdir', '/home/adare/.config'),
        ('write', '/home/adare/.config/done'),
    ]
    assert all((o.uid, o.gid) == (1000, 1000) for o in plan.ops)


def test_chown_of_a_base_image_path_is_refused(planner):
    plan = planner.plan('chown adare:adare /etc/passwd')
    assert plan.category == CLASS_GUEST


@pytest.mark.parametrize(
    ('command', 'category'),
    [
        ('apt-get install -y vim', CLASS_PROVISION),
        ('systemctl enable foo', CLASS_PROVISION),
        ('xdg-open /home/adare/a.txt', CLASS_GUI),
        ('ls /tmp', CLASS_GUEST),
        ('cat /etc/passwd | grep adare', CLASS_GUEST),
        ('cp /a /b', CLASS_GUEST),
    ],
)
def test_classes(planner, command, category):
    assert planner.plan(command).category == category


def test_relative_path_needs_cwd(planner):
    assert planner.plan('rm -f x').category == CLASS_GUEST
    assert planner.plan('rm -f x', cwd='/tmp').ops[0].path == '/tmp/x'


def test_echo_e_and_printf_decode_escapes(planner):
    (op,) = planner.plan("echo -e '[DEFAULT]\\nPrompt=never' > /etc/update-manager/release-upgrades", admin=True).ops
    assert op.content == b'[DEFAULT]\nPrompt=never\n' and (op.uid, op.gid) == (0, 0)
    (op,) = planner.plan("printf 'a\\nb\\n' > /tmp/x").ops
    assert op.content == b'a\nb\n'
    assert planner.plan("printf '%s\\n' hi > /tmp/x").category == CLASS_GUEST
    (op,) = planner.plan('echo -n hi > /tmp/y').ops
    assert op.content == b'hi'
