"""Host-side backend: environment post-setup steps are planned with the step's own rights and cwd."""

from types import SimpleNamespace

import pytest

from adare.backend.hostside.commands import CLASS_PROVISION
from adare.backend.hostside.session import HostsideSession

pytestmark = pytest.mark.unit


class _FS:
    def read_text(self, path):
        return 'root:x:0:0:root:/root:/bin/bash\nadare:x:1000:1000::/home/adare:/bin/bash\n'


def _session(tmp_path, monkeypatch, rows):
    import adare.backend.environment.database as environment_database

    monkeypatch.setattr(environment_database, 'get_environment_installations', lambda ulid: rows)
    context = SimpleNamespace(
        environment_ulid='env',
        guest_platform=None,
        playbook=SimpleNamespace(actions=[], variables=None),
        experiment_run_directory=SimpleNamespace(path=tmp_path, log_directory=tmp_path / 'logs'),
    )
    return HostsideSession(context)


def _row(name, command, **kw):
    return SimpleNamespace(name=name, command=command, description='', cwd=kw.pop('cwd', ''), shell=False, **kw)


def test_files_follow_admin_and_cwd(tmp_path, monkeypatch):
    rows = [
        _row('as-user', 'echo a > user.txt', cwd='/home/adare'),
        _row('as-admin', 'echo b > /etc/admin.txt', admin=True),
    ]
    session = _session(tmp_path, monkeypatch, rows)
    session.analyze(_FS())
    user_op, admin_op = session.staged_ops
    assert (user_op.path, user_op.uid) == ('/home/adare/user.txt', 1000)  # VM user by default, cwd honoured
    assert (admin_op.path, admin_op.uid) == ('/etc/admin.txt', 0)


def test_unsupported_step_is_still_rejected_even_with_allow_failure(tmp_path, monkeypatch):
    session = _session(tmp_path, monkeypatch, [_row('pkg', 'apt-get install -y x', allow_failure=True)])
    session.analyze(_FS())
    assert [p.category for p in session.unsupported] == [CLASS_PROVISION]
    assert "environment installation 'pkg'" in session.preflight_report()


def test_postsetup_log_records_planned_steps(tmp_path, monkeypatch):
    rows = [_row('write', 'echo a > /tmp/x', admin=True), _row('pkg', 'apt-get install -y x')]
    session = _session(tmp_path, monkeypatch, rows)
    session.analyze(_FS())
    session._write_postsetup_log()
    text = (tmp_path / 'logs' / 'postsetup.log').read_text()
    assert 'rights  : admin (root-owned files)' in text
    assert 'staged offline as 1 operation(s)' in text
    assert 'rejected before boot' in text and 'rights  : user (VM-user-owned files)' in text
