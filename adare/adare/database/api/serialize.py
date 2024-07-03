# external imports
import attrs
import sqlalchemy
import pandas as pd
from pathlib import Path

# internal imports
from adare.database.models.experiment import Project, Result, Environment, Experiment, ExperimentRun, OsInfo, StageInRun, Stage, Event, Status, TestFunction, TestFunctionFile, TestParameter, AbstractTest
from adare.database.api.database import DatabaseApi
import adare.config.database as config_database
from adarelib.config import TIMESTAMP_FORMAT
from adarelib.exceptions import EnvironmentNotFoundError, ProjectNotFoundError, ExperimentNotFoundError, TestFunctionNotFoundError, ArgumentsError

# configure logging
import logging
log = logging.getLogger(__name__)


class SerializeApi(DatabaseApi):

    def __init__(self, db_path: Path = config_database.get_database_location()):
        super().__init__(db_path)

    def serialize_result(self, result: Result) -> dict:
        if not result:
            return {}
        result_dict = {
            'status': result.status,
            'details': result.details,
        }
        return result_dict

    def serialize_event(self, event: Event) -> dict:
        event_type = event.event_type
        event_dict = {
            'ulid': event.ulid,
            'timestamp': event.timestamp.strftime(TIMESTAMP_FORMAT),
            'event_type': event_type,
            'category': event.category,
            'status': event.status,
            'error': event.error,
            'group_id': event.group_id,
        }
        if event_type == 'command_event':
            event_dict['command'] = event.command
            event_dict['returncode'] = event.returncode
            event_dict['stdout'] = event.stdout
        elif event_type == 'test_event':
            event_dict['abstract_test_ulid'] = event.abstract_test.ulid
            event_dict['result'] = self.serialize_result(event.result)
        elif event_type == 'error_event':
            event_dict['error_name'] = event.error_name
            event_dict['error_msg'] = event.error_msg
        elif event_type == 'gui_find_event':
            event_dict['text'] = event.text
            event_dict['objective'] = event.objective
            event_dict['success'] = event.success
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

    def serialize_run(self, run: ExperimentRun) -> dict:
        run_dict = {
            'ulid': run.ulid,
            'status': run.status,
            'timestamp_start': run.timestamp_start.strftime(TIMESTAMP_FORMAT),
            'timestamp_end': run.timestamp_end.strftime(TIMESTAMP_FORMAT),
            'events': [self.serialize_event(event) for event in run.events],
        }
        return run_dict

    def serialize_run_by_ulid(self, run_ulid: str) -> dict:
        run = self._session.query(ExperimentRun).filter(ExperimentRun.ulid == run_ulid).first()
        return self.serialize_run(run)
