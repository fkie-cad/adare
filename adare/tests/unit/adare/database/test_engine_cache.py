"""Process-wide engine cache, once-per-file schema setup and nested `with` blocks."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest

from adare.database.api import base
from adare.database.api.base import GlobalDatabaseApi, ProjectDatabaseApi, dispose_engines
from adare.database.models.project_models import Experiment

pytestmark = pytest.mark.unit


def test_instances_share_one_engine_per_file(tmp_path):
    first, second = ProjectDatabaseApi(tmp_path / 'a'), ProjectDatabaseApi(tmp_path / 'a')
    other = ProjectDatabaseApi(tmp_path / 'b')

    assert first.engine is second.engine
    assert first.engine is not other.engine


def test_schema_is_created_and_migrated_once_per_file(tmp_path):
    with patch('adare.database.migrations.runner.apply_pending') as apply_pending:
        for _ in range(3):
            ProjectDatabaseApi(tmp_path)

    assert apply_pending.call_count == 1


def test_deleted_database_file_is_recreated_with_schema(tmp_path):
    api = ProjectDatabaseApi(tmp_path)
    old_engine = api.engine
    old_engine.dispose()  # the file must be closable before it is deleted (Windows)
    api.db_path.unlink()

    again = ProjectDatabaseApi(tmp_path)

    assert again.engine is not old_engine
    with again:
        assert again.list_entities(Experiment) == []  # tables exist again


def test_dispose_engines_forgets_everything(tmp_path):
    api = ProjectDatabaseApi(tmp_path)
    dispose_engines()

    assert str(api.db_path) not in base._ENGINES
    assert str(api.db_path) not in base._SCHEMA_READY
    assert ProjectDatabaseApi(tmp_path).engine is not api.engine


def _experiment_count(path):
    with ProjectDatabaseApi(path) as api:
        return api.count_entities(Experiment)


def test_inner_with_does_not_commit_when_outer_fails(tmp_path):
    api = ProjectDatabaseApi(tmp_path)

    with pytest.raises(RuntimeError), api:
        with api:
            api.create_entity(Experiment, name='half-done', sha256='x')
        assert api._session is not None  # the inner exit kept the outer session open
        raise RuntimeError('outer step failed')

    assert _experiment_count(tmp_path) == 0


def test_outermost_with_commits_nested_work(tmp_path):
    api = ProjectDatabaseApi(tmp_path)

    with api:
        with api:
            api.create_entity(Experiment, name='inner', sha256='x')
        api.create_entity(Experiment, name='outer', sha256='y')

    assert api._session is None
    assert _experiment_count(tmp_path) == 2


def test_user_sessions_live_in_the_global_database():
    from adare.database.api.usersession import UserSessionApi
    from adare.database.models import GlobalBase

    assert {'token', 'user_session'} <= set(GlobalBase.metadata.tables)
    later = datetime.now(UTC) + timedelta(hours=1)

    with UserSessionApi() as db:
        db.add_user_session('alice', 'gitea', later, 'refresh', 'django', later)
    with UserSessionApi() as db:
        session = db.get_user_session('alice')
        assert session.gitea_token.token == 'gitea'
        assert db.db_path == GlobalDatabaseApi().db_path
