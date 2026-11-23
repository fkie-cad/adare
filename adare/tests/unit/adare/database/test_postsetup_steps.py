"""Post-setup steps in the global database: option columns, step order, migration."""

import sqlite3
from pathlib import Path
from unittest.mock import patch

import attrs
import pytest
import sqlalchemy
from sqlalchemy import text

from adare.database.api.environment import EnvironmentDbApi
from adare.database.migrations import add_postsetup_step_options
from adare.database.migrations.runner import MIGRATIONS
from adare.database.models.global_models import Environment, GlobalBase, PostSetupInstallation
from adare.types.environment import PostsetupInstallations

pytestmark = pytest.mark.unit


@pytest.fixture
def global_db(tmp_path):
    db_file = tmp_path / 'global.db'
    with patch('adare.config.database.get_global_database_location', return_value=db_file):
        yield db_file


def _step(name: str, **overrides) -> dict:
    return attrs.asdict(PostsetupInstallations(name=name, command=f'run-{name}', **overrides))


def _save(name: str, steps: list[dict], sha: str = '1') -> str:
    with EnvironmentDbApi() as db:
        env = db.create_environment_version(
            name=name,
            description='',
            vm_id=None,
            vm_hash=None,
            tags=[],
            installations=steps,
            environment_file=Path(f'/envs/{name}.yml'),
            sha256hash=sha * 64,
            hypervisor='qemu',
        )
        return env.id


def _names(env_id: str) -> list[str]:
    with EnvironmentDbApi() as db:
        return [step.name for step in db.get_environment_by_ulid(env_id).installations]


# --- order ---


def test_steps_come_back_in_file_order(global_db):
    env_id = _save('ordered', [_step('c'), _step('a'), _step('b')])

    assert _names(env_id) == ['c', 'a', 'b']


def test_a_step_shared_between_environments_keeps_its_own_position_in_each(global_db):
    first = _save('first', [_step('a'), _step('b')], sha='1')
    second = _save('second', [_step('b'), _step('a')], sha='2')

    assert _names(first) == ['a', 'b']
    assert _names(second) == ['b', 'a']
    with EnvironmentDbApi() as db:
        assert db._session.query(PostSetupInstallation).count() == 2  # rows are shared


def test_a_repeated_identical_step_is_stored_once_at_its_first_position(global_db):
    env_id = _save('twice', [_step('a'), _step('b'), _step('a')])

    assert _names(env_id) == ['a', 'b']


def test_deleting_an_environment_removes_its_mapping_rows(global_db):
    env_id = _save('gone', [_step('a'), _step('b')])
    with EnvironmentDbApi() as db:
        db.delete_environment(db.get_environment_by_ulid(env_id))
        remaining = db._session.execute(
            text('SELECT COUNT(*) FROM mapping_postsetupinstallation_environment')
        ).scalar_one()

    assert remaining == 0


# --- option columns ---


def test_step_options_are_stored_and_read_back(global_db):
    env_id = _save('opts', [_step('a', admin=True, allow_failure=True, timeout=42.5), _step('b')])

    with EnvironmentDbApi() as db:
        a, b = db.get_environment_by_ulid(env_id).installations

    assert (a.admin, a.allow_failure, a.timeout) == (True, True, 42.5)
    assert (b.admin, b.allow_failure, b.timeout) == (False, False, None)


def test_steps_differing_only_in_an_option_are_distinct_rows(global_db):
    env_id = _save('distinct', [_step('a'), _step('a', admin=True), _step('a', timeout=5)])

    with EnvironmentDbApi() as db:
        installations = db.get_environment_by_ulid(env_id).installations
        assert len({step.id for step in installations}) == 3


# --- migration ---

_OLD_SCHEMA = """
CREATE TABLE post_setup_installation (
    id CHAR(26) NOT NULL PRIMARY KEY,
    name VARCHAR NOT NULL,
    description VARCHAR,
    command VARCHAR NOT NULL,
    shell BOOLEAN,
    cwd VARCHAR
);
CREATE TABLE mapping_postsetupinstallation_environment (
    postsetupinstallation_id CHAR(26),
    environment_id CHAR(26)
);
"""


def _old_database(db_file: Path) -> None:
    """A global database as it was before step options: the two tables in their old shape."""
    with sqlite3.connect(db_file) as conn:
        conn.executescript(_OLD_SCHEMA)
        conn.executemany(
            'INSERT INTO post_setup_installation (id, name, description, command, shell, cwd) VALUES (?,?,?,?,?,?)',
            [
                ('s1', 'tool', '', 'run-tool', 0, ''),
                ('s2', 'second', 'd', 'run-second', 1, '/tmp'),
                ('s3', 'third', '', 'run-third', 0, ''),
            ],
        )
        # env-1: s3, s1, s2 (insertion order); env-2: s2, s1; interleaved on purpose.
        conn.executemany(
            'INSERT INTO mapping_postsetupinstallation_environment VALUES (?,?)',
            [('s3', 'env-1'), ('s2', 'env-2'), ('s1', 'env-1'), ('s1', 'env-2'), ('s2', 'env-1')],
        )


def _old_engine(tmp_path):
    db_file = tmp_path / 'old.db'
    _old_database(db_file)
    return sqlalchemy.create_engine(f'sqlite:///{db_file}')


def test_migration_adds_the_columns_with_old_meaning(tmp_path):
    engine = _old_engine(tmp_path)
    with engine.begin() as conn:
        add_postsetup_step_options.upgrade(conn)

    with engine.connect() as conn:
        step_columns = {row[1]: row for row in conn.execute(text('PRAGMA table_info(post_setup_installation)'))}
        mapping_columns = {
            row[1] for row in conn.execute(text('PRAGMA table_info(mapping_postsetupinstallation_environment)'))
        }
        rows = conn.execute(text('SELECT admin, allow_failure, timeout FROM post_setup_installation')).all()

    assert {'admin', 'allow_failure', 'timeout'} <= set(step_columns)
    assert 'position' in mapping_columns
    assert rows == [(0, 0, None)] * 3


def test_migration_backfills_position_per_environment_in_rowid_order(tmp_path):
    engine = _old_engine(tmp_path)
    with engine.begin() as conn:
        add_postsetup_step_options.upgrade(conn)

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                'SELECT environment_id, postsetupinstallation_id, position '
                'FROM mapping_postsetupinstallation_environment ORDER BY rowid'
            )
        ).all()

    assert rows == [
        ('env-1', 's3', 0),
        ('env-2', 's2', 0),
        ('env-1', 's1', 1),
        ('env-2', 's1', 1),
        ('env-1', 's2', 2),
    ]


def test_migration_is_idempotent_and_keeps_positions(tmp_path):
    engine = _old_engine(tmp_path)
    with engine.begin() as conn:
        add_postsetup_step_options.upgrade(conn)
        conn.execute(
            text(
                "UPDATE mapping_postsetupinstallation_environment SET position = 7 WHERE postsetupinstallation_id = 's3'"
            )
        )
    with engine.begin() as conn:
        add_postsetup_step_options.upgrade(conn)

    with engine.connect() as conn:
        position = conn.execute(
            text("SELECT position FROM mapping_postsetupinstallation_environment WHERE postsetupinstallation_id = 's3'")
        ).scalar_one()
    assert position == 7


def test_migration_skips_a_database_without_the_tables(tmp_path):
    engine = sqlalchemy.create_engine(f'sqlite:///{tmp_path / "empty.db"}')
    with engine.begin() as conn:
        add_postsetup_step_options.upgrade(conn)


def test_migration_is_a_no_op_on_a_new_database(tmp_path):
    engine = sqlalchemy.create_engine(f'sqlite:///{tmp_path / "new.db"}')
    GlobalBase.metadata.create_all(engine)
    with engine.begin() as conn:
        add_postsetup_step_options.upgrade(conn)
        add_postsetup_step_options.upgrade(conn)


def test_migration_is_registered_last_for_the_global_database():
    entry = next(m for m in MIGRATIONS if m.name == 'add_postsetup_step_options')

    assert entry.scope == 'global'
    assert entry.module == 'adare.database.migrations.add_postsetup_step_options'


def test_an_old_step_is_reused_not_duplicated_after_migration(global_db):
    _old_database(global_db)

    # Opening the database creates the missing tables and applies the migration.
    with EnvironmentDbApi():
        pass
    with sqlite3.connect(global_db) as conn:
        conn.execute("INSERT INTO environment (id, name, hypervisor) VALUES ('env-1', 'old-env', 'qemu')")
    with EnvironmentDbApi() as db:
        old = db._session.get(Environment, 'env-1')
        assert [step.name for step in old.installations] == ['third', 'tool', 'second']

    # The same step as an environment file spells it today (all option defaults).
    env_id = _save('new-env', [_step('tool', description='', cwd='', shell=False)])
    with EnvironmentDbApi() as db:
        assert db._session.query(PostSetupInstallation).count() == 3
        assert db.get_environment_by_ulid(env_id).installations[0].id == 's1'
