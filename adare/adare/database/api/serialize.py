# external imports
# configure logging
import logging
from pathlib import Path

import adare.config.database as config_database
from adare.config import TIMESTAMP_FORMAT
from adare.database.api.database import DatabaseApi

# internal imports
from adare.database.models.project_models import Event, ExperimentRun, Result

log = logging.getLogger(__name__)


class SerializeApi(DatabaseApi):

    def __init__(self, db_path: Path = config_database.get_database_location()):
        super().__init__(db_path)

    def serialize_result(self, result: Result) -> dict:
        if not result:
            return {}
        return {
            'status': result.status,
            'details': result.details,
        }

    def serialize_event(self, event: Event) -> dict:
        event_type = event.event_type
        event_dict = {
            'ulid': event.ulid,
            'timestamp': event.timestamp.strftime(TIMESTAMP_FORMAT),
            'event_type': event_type,
            'category': event.category,
            'error': event.error,
        }
        if event_type == 'command_event':
            event_dict['name'] = event.name
            event_dict['command'] = event.command
            event_dict['returncode'] = event.returncode
            event_dict['stdout'] = event.stdout
        elif event_type == 'test_event':
            # Use remote_ulid if available, fallback to id
            test_ulid = getattr(event.abstract_test, 'remote_ulid', None) or event.abstract_test.id
            event_dict['abstract_test_ulid'] = test_ulid
            event_dict['result'] = self.serialize_result(event.result)
        elif event_type == 'error_event':
            event_dict['error_name'] = event.error_name
            event_dict['error_msg'] = event.error_msg
        elif event_type == 'gui_find_event':
            event_dict['text'] = event.text
            event_dict['objective'] = event.objective
            event_dict['success'] = event.success
            event_dict['positions'] = event.positions
        elif event_type == 'gui_click_event':
            event_dict['clicktype'] = event.clicktype
            event_dict['modifiers'] = event.modifiers
            event_dict['target'] = event.target
        elif event_type == 'gui_keypress_event':
            event_dict['keys'] = event.keys
        elif event_type == 'gui_idle_event':
            event_dict['seconds'] = event.seconds
        else:
            log.warning(f'Unknown event type: {event_type}')

        return event_dict

    def serialize_run(self, run: ExperimentRun) -> (dict, dict):
        """
        Serialize an experiment run for API upload.

        Returns:
            Tuple of (run_data, files_dict) where run_data contains metadata
            and files_dict contains paths to log files.
        """
        # Use remote_ulid if available (after experiment is published), fallback to local id
        experiment_ulid = getattr(run.experiment, 'remote_ulid', None) or run.experiment.id

        # Environment is accessed via property, use remote_ulid if available
        env = run.environment
        environment_ulid = getattr(env, 'remote_ulid', None) or run.environment_id

        run_dict = {
            'ulid': run.id,
            'status': run.status,
            'result_status': run.result_status,
            'timestamp_start': run.start_time.strftime(TIMESTAMP_FORMAT),
            'timestamp_end': run.end_time.strftime(TIMESTAMP_FORMAT),
            'events': [self.serialize_event(event) for event in run.events],
            'experiment_ulid': experiment_ulid,
            'environment_ulid': environment_ulid,
        }
        files_dict = {
            'adarevm_log': run.files.log_adarevm.path,
            'installations_log': run.files.log_installations.path,
            'packagedump_log': run.files.package_dump.path,
        }
        return run_dict, files_dict

    def serialize_run_by_ulid(self, run_ulid: str) -> dict:
        run = self._session.query(ExperimentRun).filter(ExperimentRun.id == run_ulid).first()
        return self.serialize_run(run)
