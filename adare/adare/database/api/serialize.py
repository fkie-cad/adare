"""Turn a local ``ExperimentRun`` into the payload ``/api/run/publish/`` accepts.

This is the client half of a two-sided contract; the server half is
``experiments/views.py::ExperimentRunPublishViewSet.create`` plus the event
serializers in ``experiments/serializers.py``. The pairing is exercised by
``tests/unit/adare/database/test_serialize.py`` — keep it that way, because every
mismatch here surfaces to the user as an opaque HTTP 400/500 from the server.

Contract points that are easy to get wrong:

* **Statuses travel as lowercase names, not numbers.** The server does
  ``Status.objects.get(name=...)`` against rows named ``finished`` / ``success`` /
  ``failed``; the local table names the same rows in UPPERCASE and keys them by
  the ``StatusEnum`` value. So the wire form is ``StatusEnum(...).name.lower()``.
* **Every event needs a ``category``.** The server dispatches on it
  (``_CATEGORY_SERIALIZER_MAP``: ``command`` / ``action`` / ``test`` / ``error``)
  and a missing one is an uncaught server-side 500, so this module refuses to
  emit an event without one.
* **The real event identities are** ``event``, ``test_event``, ``error_event`` and
  ``action_event`` — the polymorphic identities declared in
  ``models/project_models.py``. There is no ``command_event`` or ``gui_*_event``.
"""

# external imports
# configure logging
import logging
from pathlib import Path

from adare.config import TIMESTAMP_FORMAT
from adare.database.api.base import ProjectDatabaseApi

# internal imports
from adare.database.models.project_models import Event, ExperimentRun, Result
from adarelib.constants import StatusEnum

log = logging.getLogger(__name__)


class RunSerializationError(Exception):
    """The run cannot be represented in the shape the server accepts.

    Raised instead of quietly emitting a wrong value: a bad payload comes back
    from the server as an unexplained 400 (or a 500), which is far harder to
    diagnose than a local failure naming the offending field.
    """


def status_wire_name(value) -> str:
    """Return the server-side status name for a local status value.

    Accepts a :class:`StatusEnum`, or the numeric id used by the local ``status``
    table (``Result.status`` returns that id). Raises
    :class:`RunSerializationError` for anything unmappable, including ``None``.
    """
    if value is None:
        raise RunSerializationError('status is not set; the server rejects a null status')
    if isinstance(value, StatusEnum):
        return value.name.lower()
    try:
        return StatusEnum(int(value)).name.lower()
    except (TypeError, ValueError) as e:
        raise RunSerializationError(f'cannot map status {value!r} to a server status name') from e


def _remote_ulid(entity, kind: str, local_id: str) -> str:
    """Return *entity*'s server-side ULID, or explain why publishing cannot proceed.

    Deliberately NOT ``getattr(entity, 'remote_ulid', None) or local_id``: that
    fallback silently published a run against a *local* ULID the server has never
    seen, and the failure then looked like the entity was unpublished.
    """
    if entity is None:
        raise RunSerializationError(f'run has no {kind} (local id {local_id!r})')
    remote = entity.remote_ulid
    if not remote:
        raise RunSerializationError(
            f'{kind} {local_id!r} has no server ULID recorded — it is not published yet. '
            f'Publish/submit the {kind} first, then sync (adare web sync).'
        )
    return remote


class SerializeApi(ProjectDatabaseApi):
    """Serialize runs out of one project's database.

    Takes a **project** path on purpose. ``ExperimentRun`` is a ``ProjectBase``
    model living in ``<project>/.adare/project.db.sqlite3``; this class used to
    default to the *global* database, where the query died with
    ``no such table: experiment_run`` — swallowed upstream as a generic
    SQLAlchemyError and shown to the user as "check your internet connection".
    """

    def __init__(self, project_path: Path):
        super().__init__(project_path)

    def serialize_result(self, result: Result) -> dict:
        if not result:
            return {}
        return {
            'status': status_wire_name(result.status),
            'details': result.details,
        }

    def serialize_event(self, event: Event) -> dict:
        event_type = event.event_type
        if not event.category:
            raise RunSerializationError(
                f'event {event.ulid} ({event_type}) has no category; the server '
                f'dispatches on it and rejects the payload without one'
            )
        event_dict = {
            'ulid': event.ulid,
            'timestamp': event.timestamp.strftime(TIMESTAMP_FORMAT),
            'event_type': event_type,
            'category': event.category,
            'error': event.error or '',
            # Fields the server accepts on every event serializer. All are
            # populated locally, and all were previously dropped.
            'success': event.success,
            'event_group_id': event.event_group_id,
            'event_type_specific': event.event_type_specific or '',
            'execution_time': event.execution_time,
        }
        if event_type == 'action_event':
            event_dict['action_type'] = event.action_type
            event_dict['action_id'] = event.action_id
            event_dict['action_data'] = event.action_data
        elif event_type == 'test_event':
            event_dict['abstract_test_ulid'] = _remote_ulid(
                event.abstract_test, 'abstract test',
                event.abstract_test.id if event.abstract_test else '?',
            )
            event_dict['result'] = self.serialize_result(event.result)
        elif event_type == 'error_event':
            # The local ErrorEvent adds no columns of its own — the message lives in
            # Event.error. The server splits it into name + message, both optional
            # (blank=True), so the name is left to the server's default rather than
            # invented here.
            event_dict['error_msg'] = event.error or ''
        elif event_type != 'event':
            raise RunSerializationError(
                f'event {event.ulid} has unknown event_type {event_type!r}; expected one of '
                f"'event', 'action_event', 'test_event', 'error_event'"
            )

        return event_dict

    def serialize_run(self, run: ExperimentRun) -> tuple[dict, dict]:
        """
        Serialize an experiment run for API upload.

        Returns:
            Tuple of (run_data, files_dict) where run_data contains metadata
            and files_dict contains paths to log files.
        """
        if run is None:
            raise RunSerializationError('no such run in this project database')

        experiment_ulid = _remote_ulid(run.experiment, 'experiment',
                                      run.experiment.id if run.experiment else '?')
        environment_ulid = _remote_ulid(run.environment, 'environment', run.environment_id or '?')

        run_dict = {
            'ulid': run.id,
            'status': status_wire_name(run.status),
            'result_status': status_wire_name(run.result_status),
            'timestamp_start': run.start_time.strftime(TIMESTAMP_FORMAT),
            'timestamp_end': run.end_time.strftime(TIMESTAMP_FORMAT),
            'events': [self.serialize_event(event) for event in run.events],
            'experiment_ulid': experiment_ulid,
            'environment_ulid': environment_ulid,
            # Lets the server reject a byte-identical re-upload under a new ULID
            # (409 content_duplicate) instead of storing it twice.
            'content_hash': self.content_hash(run),
        }
        return run_dict, self.serialize_run_files(run)

    @staticmethod
    def serialize_run_files(run: ExperimentRun) -> dict:
        """Map the run's log files to the upload field names the server expects.

        ``files_id`` is nullable and is in fact NULL for interrupted runs, so the
        whole relationship may be absent.

        Only ``adarevm_log`` is sent. ``ExperimentRunFiles`` has just ``log_adare``
        and ``log_adarevm``, and of the four upload fields the server reads
        (``adarevm_log``, ``installations_log``, ``packagedump_log``,
        ``networkdrives_log``) only the first has a local counterpart — the host-side
        ``log_adare`` has no field to land in, and anything else would be silently
        discarded. (The removed ``files.log_installations`` / ``files.package_dump``
        attributes never existed at all: reading them raised AttributeError, which
        neither caller caught, so the user got a raw traceback.)
        """
        files = run.files
        if files is None:
            log.info('run %s has no ExperimentRunFiles row; publishing without logs', run.id)
            return {}
        if files.log_adarevm is None or not files.log_adarevm.path:
            return {}
        return {'adarevm_log': files.log_adarevm.path}

    @staticmethod
    def content_hash(run: ExperimentRun) -> str:
        """Stable digest of the run's identity + event stream.

        Only what the server stores is hashed, so the same run serialized twice
        hashes the same. Timestamps are included: two runs of the same experiment
        on the same environment are legitimately distinct.
        """
        from adare.helperfunctions.hash import hash_string_sha256

        parts = [
            run.id,
            run.experiment_id or '',
            run.environment_id or '',
            run.start_time.isoformat() if run.start_time else '',
            run.end_time.isoformat() if run.end_time else '',
        ]
        parts.extend(
            f'{event.ulid}|{event.event_type}|{event.category}|{event.event_type_specific or ""}'
            for event in run.events
        )
        return hash_string_sha256('\n'.join(parts))

    def serialize_run_by_ulid(self, run_ulid: str) -> tuple[dict, dict]:
        run = self._session.query(ExperimentRun).filter(ExperimentRun.id == run_ulid).first()
        if run is None:
            raise RunSerializationError(f'run {run_ulid!r} not found in {self.db_path}')
        return self.serialize_run(run)
