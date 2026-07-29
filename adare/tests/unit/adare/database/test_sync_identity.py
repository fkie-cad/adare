"""Remote identity must round-trip through a real commit, on **both** bases.

The bug this covers: ``sync_experiment`` / ``sync_environment`` /
``sync_testfunction_file`` assigned ``remote_ulid`` / ``remote_url`` /
``published`` / ``in_request`` directly onto the model. None is a mapped column, so
SQLAlchemy took each as an ordinary instance attribute and ``commit()`` wrote
nothing — the server identity was gone as soon as the session closed.

The global and project databases are separate SQLite files, so each base needs its
own ``SyncMetadata`` table; ``RemoteIdentityMixin`` is plain Python and serves both.
Both are exercised here against a real engine, because an in-memory object would
have passed the whole time the bug was live.
"""

import pytest
import sqlalchemy
from sqlalchemy.orm import sessionmaker

pytestmark = pytest.mark.unit

from adare.database.models import global_models, project_models
from adare.database.models.sync_identity import (
    SYNC_STATUS_IN_REQUEST,
    SYNC_STATUS_PUBLISHED,
    apply_remote_identity,
)

REMOTE_ULID = '01JQREMOTE00000000000000AA'
REMOTE_URL = 'https://adare.example/org/repo'


def _session(tmp_path, base, name):
    engine = sqlalchemy.create_engine(f'sqlite:///{tmp_path / name}')
    base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)(), engine


@pytest.fixture
def global_session(tmp_path):
    session, engine = _session(tmp_path, global_models.GlobalBase, 'global.sqlite3')
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def project_session(tmp_path):
    session, engine = _session(tmp_path, project_models.ProjectBase, 'project.sqlite3')
    yield session
    session.close()
    engine.dispose()


class TestGlobalEnvironment:
    """Environment lives in the global DB and already had a sync_metadata FK — the
    designated home the write side was bypassing."""

    def _environment(self, session, **overrides):
        env = global_models.Environment(name=overrides.pop('name', 'env-1'), **overrides)
        session.add(env)
        session.flush()
        return env

    def test_published_identity_survives_a_commit(self, global_session):
        env = self._environment(global_session)
        apply_remote_identity(
            global_session, env, global_models.SyncMetadata,
            remote_ulid=REMOTE_ULID, remote_url=REMOTE_URL, is_published=True,
        )
        global_session.commit()
        global_session.expunge_all()

        reloaded = global_session.query(global_models.Environment).one()
        assert reloaded.remote_ulid == REMOTE_ULID
        assert reloaded.remote_url == REMOTE_URL
        assert reloaded.published is True
        assert reloaded.in_request is False

    def test_submitted_but_unmerged_reads_as_in_request(self, global_session):
        env = self._environment(global_session)
        apply_remote_identity(
            global_session, env, global_models.SyncMetadata,
            remote_ulid=REMOTE_ULID, remote_url=REMOTE_URL, is_published=False,
        )
        global_session.commit()
        global_session.expunge_all()

        reloaded = global_session.query(global_models.Environment).one()
        assert reloaded.published is False
        assert reloaded.in_request is True
        assert reloaded.sync_metadata.sync_status == SYNC_STATUS_IN_REQUEST

    def test_resync_updates_the_same_row(self, global_session):
        """A second sync must not orphan a SyncMetadata row per call."""
        env = self._environment(global_session)
        for published in (False, True):
            apply_remote_identity(
                global_session, env, global_models.SyncMetadata,
                remote_ulid=REMOTE_ULID, remote_url=REMOTE_URL, is_published=published,
            )
            global_session.commit()

        assert global_session.query(global_models.SyncMetadata).count() == 1
        assert env.sync_metadata.sync_status == SYNC_STATUS_PUBLISHED

    def test_never_synced_environment_reads_false_not_error(self, global_session):
        env = self._environment(global_session)
        global_session.commit()
        assert env.remote_ulid is None
        assert env.remote_url is None
        assert env.published is False
        assert env.in_request is False

    def test_testfunction_file_uses_the_same_row(self, global_session):
        """TestFunctionFile had the identical bug and the identical FK."""
        tf_file = global_models.TestFunctionFile(
            name='standard', path='/tmp/standard.py', sha256hash='0' * 64,
        )
        global_session.add(tf_file)
        apply_remote_identity(
            global_session, tf_file, global_models.SyncMetadata,
            remote_ulid='7', remote_url=REMOTE_URL, is_published=True,
        )
        global_session.commit()
        global_session.expunge_all()

        reloaded = global_session.query(global_models.TestFunctionFile).one()
        assert reloaded.remote_ulid == '7'
        assert reloaded.published is True


class TestProjectExperiment:
    """Experiment lives in the project DB, which needed its own SyncMetadata table
    (a cross-database foreign key is impossible)."""

    def _experiment(self, session):
        experiment = project_models.Experiment(name='exp-1', sha256='0' * 64)
        session.add(experiment)
        session.flush()
        return experiment

    def test_published_identity_survives_a_commit(self, project_session):
        experiment = self._experiment(project_session)
        apply_remote_identity(
            project_session, experiment, project_models.SyncMetadata,
            remote_ulid=REMOTE_ULID, remote_url=REMOTE_URL, is_published=True,
        )
        project_session.commit()
        project_session.expunge_all()

        reloaded = project_session.query(project_models.Experiment).one()
        assert reloaded.remote_ulid == REMOTE_ULID
        assert reloaded.remote_url == REMOTE_URL
        assert reloaded.published is True

    def test_abstract_test_remote_ulid_is_a_real_column(self, project_session):
        """The test ULID is a plain column, not a SyncMetadata row: a test has no
        publish state of its own. It still has to persist."""
        test = project_models.AbstractTest(
            name='file_exists', testfunction_id='tf-1', remote_ulid=REMOTE_ULID,
        )
        project_session.add(test)
        project_session.commit()
        project_session.expunge_all()

        assert project_session.query(project_models.AbstractTest).one().remote_ulid == REMOTE_ULID

    def test_experiment_run_published_is_untouched(self, project_session):
        """`ExperimentRun.published` was always a real column — it must stay one and
        must not be shadowed by the mixin."""
        column_names = {c.name for c in project_models.ExperimentRun.__table__.columns}
        assert 'published' in column_names

        run = project_models.ExperimentRun(published=True)
        project_session.add(run)
        project_session.commit()
        project_session.expunge_all()
        assert project_session.query(project_models.ExperimentRun).one().published is True


class TestBothBasesAgree:

    def test_sync_metadata_columns_match_across_bases(self):
        """The project twin must not drift from the global original."""
        def columns(cls):
            return {c.name: str(c.type) for c in cls.__table__.columns}

        assert columns(project_models.SyncMetadata) == columns(global_models.SyncMetadata)

    def test_status_constants_map_to_the_enum_values(self):
        allowed = set(global_models.SyncStatusEnum.enums)
        assert SYNC_STATUS_PUBLISHED in allowed
        assert SYNC_STATUS_IN_REQUEST in allowed
