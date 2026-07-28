"""Client half of the run-publish contract.

``SerializeApi`` produces the payload ``POST /api/run/publish/`` consumes. Nothing
used to check the two agreed, and they did not: statuses went out as bare ints
where the server looks up lowercase names, action events lost every field that
carried their content, and two of the three log-file paths read attributes that do
not exist on ``ExperimentRunFiles``.

The contract is pinned as a JSON fixture. This module asserts the client still
*produces* it; ``adare-server``'s ``tests/api/test_run_publish_contract.py``
asserts the server still *accepts* it. Both repos hold a byte-identical copy and
:func:`test_server_fixture_copy_is_identical` checks that when the sibling
checkout is present.

Regenerate after an intentional contract change:

    ADARE_UPDATE_CONTRACT_FIXTURE=1 pytest adare/tests/unit/adare/database/test_serialize.py

then copy the file to the server repo (the test above prints the destination).
"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from adare.database.api.serialize import RunSerializationError, SerializeApi, status_wire_name
from adarelib.constants import StatusEnum

# The pinned payload, shared with the server repo.
CONTRACT_FIXTURE = (
    Path(__file__).resolve().parents[4] / 'tests' / 'fixtures' / 'run_publish_payload.json'
)
SERVER_FIXTURE_RELATIVE = Path(
    'adare-server/backend_django/tests/fixtures/run_publish_payload.json'
)

# Fixed identifiers so the payload is byte-stable across runs.
RUN_ULID = '01JQRUN0000000000000000000'
EXP_LOCAL_ULID = '01JQEXPLOCAL00000000000000'
EXP_REMOTE_ULID = '01JQEXPREMOTE0000000000000'
ENV_ULID = '01JQENV000000000000000000A'
ENV_REMOTE_ULID = '01JQENVREMOTE0000000000000'
TEST_LOCAL_ULID = '01JQTESTLOCAL0000000000000'
TEST_REMOTE_ULID = '01JQTESTREMOTE000000000000'
ACTION_EVENT_ULID = '01JQEVACTION00000000000000'
TEST_EVENT_ULID = '01JQEVTEST0000000000000000'

START = datetime(2026, 7, 27, 10, 0, 0, tzinfo=UTC)
END = datetime(2026, 7, 27, 10, 1, 0, tzinfo=UTC)

# Categories the server dispatches on (experiments/serializers._CATEGORY_SERIALIZER_MAP).
SERVER_CATEGORIES = {'command', 'action', 'test', 'error'}
# Status names in the server's status fixture (experiments/fixtures/status.yaml).
SERVER_STATUS_NAMES = {
    'none', 'success', 'failed', 'warning', 'error', 'running', 'pending',
    'interrupted', 'finished', 'breakpoint_hit', 'breakpoint_resolved',
    'test_missing', 'test_failed', 'pause',
}


@pytest.fixture
def published_project(tmp_path):
    """A project DB holding one finished run whose experiment/env are published.

    Built through the real APIs — including ``sync_experiment`` /
    ``sync_environment``, so the test also proves the remote identity survives a
    commit, which is the defect that made publish unreachable.
    """
    from adare.database.api.serialize import SerializeApi as _SerializeApi
    from adare.database.models.project_models import (
        AbstractTest,
        EventFactory,
        Experiment,
        ExperimentRun,
        Status,
        SyncMetadata,
    )
    from adare.database.models.project_models import Result as ModelResult
    from adare.database.models.sync_identity import apply_remote_identity

    project = tmp_path / 'proj'
    project.mkdir()

    with _SerializeApi(project) as api:
        session = api._session
        for status in StatusEnum:
            session.add(Status(id=str(status.value), name=status.name))
        session.flush()

        abstract_test = AbstractTest(
            id=TEST_LOCAL_ULID,
            name='file_exists',
            testfunction_id='01JQTF0000000000000000000A',
            remote_ulid=TEST_REMOTE_ULID,
        )
        experiment = Experiment(
            id=EXP_LOCAL_ULID,
            name='autopsy_webhistory',
            sha256='0' * 64,
            abstract_tests=[abstract_test],
            environment_ids=[ENV_ULID],
        )
        session.add(experiment)
        apply_remote_identity(
            session, experiment, SyncMetadata,
            remote_ulid=EXP_REMOTE_ULID,
            remote_url='https://adare.example/exp',
            is_published=True,
        )

        run = ExperimentRun(
            id=RUN_ULID,
            experiment=experiment,
            environment_id=ENV_ULID,
            start_time=START,
            end_time=END,
            status=StatusEnum.FINISHED,
        )
        session.add(run)

        session.add(EventFactory.create_event(
            'action',
            id=ACTION_EVENT_ULID,
            event_type='action_event',
            experiment_run_id=RUN_ULID,
            timestamp=START,
            action_type='command',
            action_id='install-packages',
            event_group_id='install-packages',
            event_type_specific='COMMAND_COMPLETE',
            success=True,
            execution_time=1234,
            action_data='{"command": "dir", "returncode": 0}',
        ))
        # Result.status is the numeric status id, matching what the running code
        # stores (see EventDbApi.get_or_create_test_result).
        result = ModelResult(status=str(StatusEnum.SUCCESS.value), details='file found')
        session.add(result)
        session.add(EventFactory.create_event(
            'test',
            id=TEST_EVENT_ULID,
            event_type='test_event',
            experiment_run_id=RUN_ULID,
            timestamp=END,
            event_group_id='file_exists',
            event_type_specific='TEST_COMPLETE',
            success=True,
            execution_time=42,
            abstract_test=abstract_test,
            result=result,
        ))
        session.commit()

    return project


@pytest.fixture
def payload(published_project, monkeypatch):
    """The serialized run, with the environment's remote ULID stubbed in.

    ``ExperimentRun.environment`` resolves through the *global* database via the
    reference manager. The test owns only a project DB, so the lookup is replaced
    with a stand-in carrying the one field the serializer reads.
    """
    class _Env:
        remote_ulid = ENV_REMOTE_ULID

    from adare.database import reference_manager as reference_manager_module

    monkeypatch.setattr(
        reference_manager_module.reference_manager,
        'get_environment_object',
        lambda _env_id: _Env(),
    )
    with SerializeApi(published_project) as api:
        run_data, files = api.serialize_run_by_ulid(RUN_ULID)
    assert files == {}, 'this run has no ExperimentRunFiles row'
    return run_data


# --------------------------------------------------------------------------- #
# status mapping
# --------------------------------------------------------------------------- #

class TestStatusWireName:
    """Statuses must go out as the server's lowercase Status names."""

    @pytest.mark.parametrize('value,expected', [
        (StatusEnum.FINISHED, 'finished'),
        (StatusEnum.SUCCESS, 'success'),
        (StatusEnum.FAILED, 'failed'),
        (StatusEnum.TEST_MISSING, 'test_missing'),
        # Result.status returns the numeric status id, as str or int.
        (3, 'failed'),
        ('2', 'success'),
    ])
    def test_maps_to_server_name(self, value, expected):
        assert status_wire_name(value) == expected

    def test_every_local_status_exists_on_the_server(self):
        for status in StatusEnum:
            assert status_wire_name(status) in SERVER_STATUS_NAMES

    def test_none_raises_instead_of_sending_null(self):
        with pytest.raises(RunSerializationError, match='not set'):
            status_wire_name(None)

    def test_unmappable_raises(self):
        with pytest.raises(RunSerializationError, match='cannot map status'):
            status_wire_name('finished')  # a name, not an id — not the wire direction


# --------------------------------------------------------------------------- #
# payload shape
# --------------------------------------------------------------------------- #

class TestRunPayloadShape:

    def test_statuses_are_server_names_not_ints(self, payload):
        assert payload['status'] == 'finished'
        assert payload['result_status'] == 'success'
        assert payload['status'] in SERVER_STATUS_NAMES
        assert payload['result_status'] in SERVER_STATUS_NAMES

    def test_required_top_level_keys_present(self, payload):
        # Every field views.py reads before it can save the run.
        for key in ('ulid', 'experiment_ulid', 'environment_ulid', 'status',
                    'result_status', 'timestamp_start', 'timestamp_end',
                    'events', 'content_hash'):
            assert key in payload, key

    def test_remote_ulids_are_used_not_local_ones(self, payload):
        assert payload['experiment_ulid'] == EXP_REMOTE_ULID
        assert payload['environment_ulid'] == ENV_REMOTE_ULID

    def test_content_hash_is_stable_and_populated(self, payload, published_project, monkeypatch):
        assert len(payload['content_hash']) == 64
        class _Env:
            remote_ulid = ENV_REMOTE_ULID
        from adare.database import reference_manager as rm
        monkeypatch.setattr(rm.reference_manager, 'get_environment_object', lambda _i: _Env())
        with SerializeApi(published_project) as api:
            again, _ = api.serialize_run_by_ulid(RUN_ULID)
        assert again['content_hash'] == payload['content_hash']

    def test_every_event_has_a_category_the_server_dispatches_on(self, payload):
        assert payload['events']
        for event in payload['events']:
            assert event['category'] in SERVER_CATEGORIES, event

    def test_action_event_carries_its_content(self, payload):
        action = next(e for e in payload['events'] if e['event_type'] == 'action_event')
        # These were all dropped by the old dead `command_event` / `gui_*_event` branches.
        assert action['action_type'] == 'command'
        assert action['action_id'] == 'install-packages'
        assert action['action_data'] == '{"command": "dir", "returncode": 0}'
        assert action['success'] is True
        assert action['event_group_id'] == 'install-packages'
        assert action['execution_time'] == 1234
        assert action['event_type_specific'] == 'COMMAND_COMPLETE'

    def test_test_event_uses_the_tests_remote_ulid(self, payload):
        test_event = next(e for e in payload['events'] if e['event_type'] == 'test_event')
        assert test_event['abstract_test_ulid'] == TEST_REMOTE_ULID
        assert test_event['result'] == {'status': 'success', 'details': 'file found'}

    def test_no_dead_event_types_emitted(self, payload):
        emitted = {e['event_type'] for e in payload['events']}
        assert not emitted & {'command_event', 'gui_find_event', 'gui_click_event',
                              'gui_keypress_event', 'gui_idle_event'}


class TestUnpublishedDependenciesFailLoudly:
    """A missing remote ULID must raise, never fall back to the local one."""

    def test_unpublished_experiment_raises(self, published_project, monkeypatch):
        from adare.database.models.project_models import Experiment

        class _Env:
            remote_ulid = ENV_REMOTE_ULID
        from adare.database import reference_manager as rm
        monkeypatch.setattr(rm.reference_manager, 'get_environment_object', lambda _i: _Env())

        with SerializeApi(published_project) as api:
            experiment = api._session.query(Experiment).one()
            experiment.sync_metadata.remote_id = None
            api._session.commit()
            with pytest.raises(RunSerializationError, match='no server ULID'):
                api.serialize_run_by_ulid(RUN_ULID)

    def test_unpublished_environment_raises(self, published_project, monkeypatch):
        class _Env:
            remote_ulid = None
        from adare.database import reference_manager as rm
        monkeypatch.setattr(rm.reference_manager, 'get_environment_object', lambda _i: _Env())

        with SerializeApi(published_project) as api:
            with pytest.raises(RunSerializationError, match='no server ULID'):
                api.serialize_run_by_ulid(RUN_ULID)

    def test_missing_run_raises(self, published_project):
        with SerializeApi(published_project) as api:
            with pytest.raises(RunSerializationError, match='not found'):
                api.serialize_run_by_ulid('01JQNOSUCHRUN0000000000000')


class TestRemoteIdentityPersists:
    """The regression itself: the remote identity must survive the session."""

    def test_experiment_remote_ulid_readable_after_reopen(self, published_project):
        from adare.database.models.project_models import Experiment

        with SerializeApi(published_project) as api:
            experiment = api._session.query(Experiment).one()
            assert experiment.remote_ulid == EXP_REMOTE_ULID
            assert experiment.remote_url == 'https://adare.example/exp'
            assert experiment.published is True
            assert experiment.in_request is False

    def test_in_request_when_submitted_but_not_merged(self, published_project):
        from adare.database.models.project_models import Experiment, SyncMetadata
        from adare.database.models.sync_identity import apply_remote_identity

        with SerializeApi(published_project) as api:
            experiment = api._session.query(Experiment).one()
            apply_remote_identity(
                api._session, experiment, SyncMetadata,
                remote_ulid=EXP_REMOTE_ULID, remote_url='u', is_published=False,
            )
            api._session.commit()

        with SerializeApi(published_project) as api:
            experiment = api._session.query(Experiment).one()
            assert experiment.published is False
            assert experiment.in_request is True


# --------------------------------------------------------------------------- #
# the pinned contract
# --------------------------------------------------------------------------- #

class TestPinnedContract:

    def test_payload_matches_pinned_fixture(self, payload):
        if os.environ.get('ADARE_UPDATE_CONTRACT_FIXTURE'):
            CONTRACT_FIXTURE.parent.mkdir(parents=True, exist_ok=True)
            CONTRACT_FIXTURE.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n')
            pytest.skip(f'regenerated {CONTRACT_FIXTURE}; copy it to {SERVER_FIXTURE_RELATIVE}')

        assert CONTRACT_FIXTURE.exists(), (
            f'{CONTRACT_FIXTURE} missing — regenerate with '
            f'ADARE_UPDATE_CONTRACT_FIXTURE=1'
        )
        expected = json.loads(CONTRACT_FIXTURE.read_text())
        assert payload == expected, (
            'the publish payload changed. If that is intentional, regenerate with '
            'ADARE_UPDATE_CONTRACT_FIXTURE=1 and copy the file to '
            f'{SERVER_FIXTURE_RELATIVE} so the server test checks the same bytes.'
        )

    def test_server_fixture_copy_is_identical(self):
        """Both repos must pin the same bytes, or the halves drift apart again."""
        # .../<workspace>/adare/adare/tests/fixtures/x.json -> <workspace>
        server_copy = CONTRACT_FIXTURE.resolve().parents[4] / SERVER_FIXTURE_RELATIVE
        if not server_copy.exists():
            pytest.skip(f'adare-server checkout not found at {server_copy}')
        assert server_copy.read_text() == CONTRACT_FIXTURE.read_text(), (
            f'{server_copy} differs from {CONTRACT_FIXTURE}; copy the client copy over it'
        )
